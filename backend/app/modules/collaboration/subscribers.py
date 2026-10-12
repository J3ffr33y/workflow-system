"""Turns ``notify.requested`` events into notifications.

Any module can ask for a notification by emitting ``notify.requested`` with
``{"kind", "user_ids", "title", "body"}``. Future channels (email, Teams)
are additional subscribers on the same event; producers don't change.
"""

import uuid

from app.modules.collaboration.commands import DeliverNotifications
from app.platform.commands import Origin, bus
from app.platform.events.registry import EventRecord, Subscriber, subscribers
from app.platform.permissions import SYSTEM_ACTOR


def deliver_in_app(ev: EventRecord) -> None:
    p = ev.payload
    user_ids = [uuid.UUID(u) for u in p.get("user_ids", [])]
    if not user_ids:
        return
    bus.execute(
        DeliverNotifications(
            event_id=ev.id,
            kind=p.get("kind", "info"),
            user_ids=user_ids,
            title=p.get("title", "Notification"),
            body=p.get("body"),
            entity_type=ev.entity_type,
            entity_id=ev.entity_id,
            workspace_id=ev.workspace_id,
            actor_display=p.get("actor_display"),
            data={k: v for k, v in p.items() if k not in {"user_ids", "title", "body", "kind"}},
        ),
        actor=SYSTEM_ACTOR,
        origin=Origin.SYSTEM,
        idempotency_key=f"notify:{ev.id}",
    )


subscribers.register(
    Subscriber(name="notifications.in_app", patterns=("notify.requested",), handler=deliver_in_app)
)
