from datetime import timedelta

from sqlalchemy import delete

from app.core.db import write_session
from app.core.time import utcnow
from app.platform.events.models import EventDelivery
from app.platform.jobs.scheduler import scheduled


@scheduled("system.heartbeat", every=timedelta(minutes=1))
def heartbeat() -> str:
    """Lets /api/ready tell whether the worker is alive."""
    return "ok"


@scheduled("system.prune_deliveries", every=timedelta(days=1))
def prune_deliveries() -> str:
    # Queue bookkeeping only; events themselves are kept (they are cheap and
    # useful for replays). Delivered rows older than 30 days carry no value.
    with write_session() as s, s.begin():
        res = s.execute(
            delete(EventDelivery).where(
                EventDelivery.status == "done", EventDelivery.updated_at < utcnow() - timedelta(days=30)
            )
        )
        return f"pruned {res.rowcount} deliveries"  # type: ignore[attr-defined]
