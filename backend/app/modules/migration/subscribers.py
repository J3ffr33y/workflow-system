import uuid

from app.modules.migration.executor import commit_run
from app.platform.events.registry import EventRecord, Subscriber, subscribers


def on_commit_requested(ev: EventRecord) -> None:
    commit_run(uuid.UUID(ev.payload["run_id"]))


# One attempt: a partially imported run is resumed by re-requesting the
# commit (already imported rows are skipped by their idempotency keys).
subscribers.register(
    Subscriber(
        name="migration.commit",
        patterns=("migration.commit_requested",),
        handler=on_commit_requested,
        max_attempts=1,
    )
)
