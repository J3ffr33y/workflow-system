import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import InternalError

from app.core.db import read_session, write_session
from app.core.errors import PermissionDenied, ValidationFailed
from app.modules.clients.commands import CreateClient, UpdateClient
from app.modules.clients.models import Client
from app.platform.audit.models import AuditEntry
from app.platform.commands.models import CommandLog
from app.platform.events.models import Event
from tests.conftest import make_user, run, run_full


def test_every_change_is_audited_with_before_and_after() -> None:
    cid = run(CreateClient(name="Acme Pty Ltd", client_type="company"))["id"]
    run(UpdateClient(client_id=uuid.UUID(cid), name="Acme Holdings Pty Ltd", notes="moved"))

    with read_session() as s:
        entries = list(
            s.scalars(
                select(AuditEntry).where(AuditEntry.entity_id == uuid.UUID(cid)).order_by(AuditEntry.id)
            )
        )
    assert [e.op for e in entries] == ["create", "update"]
    changes = {c["field"]: (c["before"], c["after"]) for c in entries[1].changes}
    assert changes["name"] == ("Acme Pty Ltd", "Acme Holdings Pty Ltd")
    assert changes["notes"] == (None, "moved")


def test_events_are_written_in_the_same_transaction() -> None:
    res = run_full(CreateClient(name="Beta"))
    with read_session() as s:
        types = list(s.scalars(select(Event.type).where(Event.command_id == res.command_id)))
    assert "client.created" in types


def test_idempotency_key_replays_without_second_write() -> None:
    a = run_full(CreateClient(name="Gamma"), idempotency_key="k-1")
    b = run_full(CreateClient(name="Gamma"), idempotency_key="k-1")
    assert b.replayed and a.command_id == b.command_id
    with read_session() as s:
        assert s.scalar(select(text("count(*)")).select_from(Client)) == 1


def test_failed_command_rolls_back_and_is_logged() -> None:
    run(CreateClient(name="Delta"))
    with pytest.raises(ValidationFailed):
        run(CreateClient(name="delta"))  # duplicate (case-insensitive)
    with read_session() as s:
        failed = s.scalar(select(CommandLog).where(CommandLog.status == "failed"))
        assert failed is not None and failed.error_code == "duplicate_name"


def test_read_sessions_cannot_write() -> None:
    with read_session() as s, pytest.raises(InternalError):
        s.execute(
            text(
                "INSERT INTO lookup_lists (id, key, label, is_hierarchical) VALUES (gen_random_uuid(), 'x', 'x', false)"
            )
        )


def test_writes_outside_the_bus_are_refused() -> None:
    with write_session() as s, pytest.raises(RuntimeError, match="outside the command bus"):
        s.add(Client(name="Sneaky"))
        s.flush()


def test_permission_is_enforced(seeded: dict[str, str]) -> None:
    viewer = make_user("viewer@example.com", "Viewer", {"grants": "viewer"})
    with pytest.raises(PermissionDenied):
        run(CreateClient(name="Nope"), actor=viewer)


def test_secrets_are_not_logged() -> None:
    make_user("someone@example.com", "Someone")
    with read_session() as s:
        log = s.scalar(select(CommandLog).where(CommandLog.name == "identity.create_user"))
        assert log is not None
        assert log.payload["password"] == "***"
