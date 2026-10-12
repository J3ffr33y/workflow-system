"""Background worker: delivers outbox events and runs scheduled jobs.

    python -m app.worker

Wakes up immediately on NOTIFY from the command bus, and at least every few
seconds to run due jobs and retries. Safe to run several copies.
"""

import logging
import signal
import time
from types import FrameType

import psycopg

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules import load_modules
from app.platform.commands.bus import NOTIFY_EVENTS
from app.platform.events.dispatcher import process_batch
from app.platform.jobs.scheduler import run_due_jobs

log = logging.getLogger("flow.worker")
_running = True


def _stop(signum: int, frame: FrameType | None) -> None:
    global _running
    _running = False


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_json)
    load_modules()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    log.info("worker started")
    while _running:
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(f"LISTEN {NOTIFY_EVENTS}")
                while _running:
                    while process_batch():
                        pass
                    run_due_jobs()
                    # Block until a NOTIFY arrives or 5 s pass.
                    for _ in conn.notifies(timeout=5.0, stop_after=1):
                        pass
        except Exception:
            log.exception("worker loop error; restarting in 3 s")
            time.sleep(3)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
