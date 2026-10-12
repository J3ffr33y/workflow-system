from sqlalchemy import update

from app.core.errors import NotFound
from app.core.time import utcnow
from app.platform.commands import Command, CommandContext, handles
from app.platform.events.models import EventDelivery
from app.platform.permissions import P_SYSTEM_ADMIN


class RetryDelivery(Command):
    """Re-queue a dead event delivery after the underlying problem is fixed."""

    command_name = "system.retry_delivery"
    permission = P_SYSTEM_ADMIN
    scoped = False

    delivery_id: int


@handles(RetryDelivery)
def retry_delivery(ctx: CommandContext, cmd: RetryDelivery) -> None:
    res = ctx.session.execute(
        update(EventDelivery)
        .where(EventDelivery.id == cmd.delivery_id, EventDelivery.status.in_(("dead", "failed")))
        .values(status="pending", next_attempt_at=utcnow(), attempts=0)
    )
    if not res.rowcount:  # type: ignore[attr-defined]
        raise NotFound("no retryable delivery with that id")
