"""Server-sent events: tells open browsers that data changed.

One background thread per API process LISTENs on PostgreSQL's
``flow_changes`` channel (NOTIFY is sent by the command bus after commit)
and fans the payload out to connected clients. Payloads carry only entity
types and ids; clients re-fetch through the normal, permission-checked API.
"""

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncIterator

import psycopg

from app.core.config import get_settings
from app.platform.commands.bus import NOTIFY_CHANGES

log = logging.getLogger("flow.realtime")


class Broadcaster:
    def __init__(self) -> None:
        self.clients: set[asyncio.Queue[str]] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread is not None:
            return
        self.loop = loop
        self._thread = threading.Thread(target=self._listen, name="realtime-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _dsn(self) -> str:
        return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")

    def _listen(self) -> None:
        while not self._stop.is_set():
            try:
                with psycopg.connect(self._dsn(), autocommit=True) as conn:
                    conn.execute(f"LISTEN {NOTIFY_CHANGES}")
                    for n in conn.notifies(timeout=5.0):
                        self._publish(n.payload)
                        if self._stop.is_set():
                            return
                    # notifies() returns after the timeout; loop to keep listening.
            except Exception:
                log.exception("realtime listener lost its connection; retrying")
                time.sleep(3)

    def _publish(self, payload: str) -> None:
        if self.loop is None:
            return
        for q in list(self.clients):
            self.loop.call_soon_threadsafe(_put_nowait, q, payload)

    async def stream(self) -> AsyncIterator[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
        self.clients.add(q)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"event: change\ndata: {payload}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.clients.discard(q)


def _put_nowait(q: "asyncio.Queue[str]", payload: str) -> None:
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        # A slow client just gets a "refresh everything" hint.
        while not q.empty():
            q.get_nowait()
        q.put_nowait(json.dumps({"types": ["*"], "ids": []}))


broadcaster = Broadcaster()
