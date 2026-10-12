"""Delivers outbox events to subscribers (runs in the worker process)."""

import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.db import write_session
from app.core.errors import AppError
from app.core.time import utcnow
from app.platform.events.models import Event, EventDelivery
from app.platform.events.registry import EventRecord, subscribers

log = logging.getLogger("flow.events")

BACKOFF = [5, 30, 120, 600, 1800, 3600, 7200, 14400]  # seconds


def _record(ev: Event) -> EventRecord:
    return EventRecord(
        id=ev.id,
        type=ev.type,
        entity_type=ev.entity_type,
        entity_id=ev.entity_id,
        workspace_id=ev.workspace_id,
        command_id=ev.command_id,
        origin=ev.origin,
        actor_id=ev.actor_id,
        depth=ev.depth,
        payload=ev.payload or {},
        occurred_at=ev.occurred_at,
    )


def process_batch(limit: int = 50) -> int:
    """Deliver up to ``limit`` due events. Returns how many were attempted.

    Rows are locked with SKIP LOCKED so several workers can run safely.
    """
    with write_session() as s, s.begin():
        rows = s.execute(
            select(EventDelivery, Event)
            .join(Event, Event.id == EventDelivery.event_id)
            .where(EventDelivery.status.in_(("pending", "failed")), EventDelivery.next_attempt_at <= utcnow())
            .order_by(EventDelivery.id)
            .limit(limit)
            .with_for_update(skip_locked=True, of=EventDelivery)
        ).all()
        for d, ev in rows:
            sub = subscribers.subscribers.get(d.subscriber)
            if sub is None:
                d.status, d.last_error = "dead", "subscriber no longer registered"
                continue
            try:
                sub.handler(_record(ev))
                d.status, d.last_error = "done", None
            except AppError as e:
                # Business-rule failures will not succeed on retry.
                d.attempts += 1
                d.status, d.last_error = "dead", f"{e.code}: {e.message}"
                log.warning("subscriber %s rejected event %s: %s", d.subscriber, ev.id, e.message)
            except Exception as e:
                d.attempts += 1
                d.last_error = repr(e)[:2000]
                if d.attempts >= sub.max_attempts:
                    d.status = "dead"
                    log.exception("subscriber %s gave up on event %s", d.subscriber, ev.id)
                else:
                    d.status = "failed"
                    d.next_attempt_at = utcnow() + timedelta(
                        seconds=BACKOFF[min(d.attempts, len(BACKOFF)) - 1]
                    )
                    log.warning(
                        "subscriber %s failed on event %s (attempt %s)", d.subscriber, ev.id, d.attempts
                    )
        return len(rows)


def drain(max_rounds: int = 100) -> int:
    """Process until nothing is due (tests and CLI)."""
    total = 0
    for _ in range(max_rounds):
        n = process_batch()
        total += n
        if n == 0:
            break
    return total
