import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.core.db import read_session
from app.core.time import set_clock
from app.modules.automations.commands import ActionSpec, SaveRule, TriggerSpec
from app.modules.automations.engine import run_date_rules
from app.modules.automations.models import AutomationRun
from app.modules.clients.commands import CreateClient
from app.modules.collaboration.commands import AddComment
from app.modules.collaboration.queries import notifications_for
from app.modules.items.commands import CreateItem, UpdateItemField
from app.modules.tasks.commands import CreateTask, DeleteTask
from app.modules.tasks.queries import tasks_for_item
from app.platform.events.dispatcher import drain
from app.platform.permissions import SYSTEM_ACTOR
from tests.conftest import make_user, run
from tests.test_items import boards, rows


@pytest.fixture(autouse=True)
def reset_clock() -> Any:
    yield
    set_clock(None)


def _client() -> str:
    return run(CreateClient(name="Auto Client"))["id"]


def test_status_change_rolls_due_date_by_frequency(seeded: dict[str, str]) -> None:
    ws = uuid.UUID(seeded["accounting"])
    run(
        SaveRule(
            workspace_id=ws,
            name="Completed -> next period",
            trigger=TriggerSpec(type="status_changed", config={"to": ["completed"]}),
            actions=[
                ActionSpec(type="advance_date", config={"field": "due_date", "by": "frequency"}),
                ActionSpec(type="set_status", config={"status": "not_started"}),
            ],
        )
    )
    b = uuid.UUID(boards(seeded["accounting"])["BAS"])
    iid = uuid.UUID(
        run(
            CreateItem(
                board_id=b,
                values={
                    "name": "BAS Q1",
                    "client": _client(),
                    "due_date": "2026-10-28",
                    "frequency": "quarterly",
                },
            )
        )["id"]
    )
    run(UpdateItemField(item_id=iid, field="status", value="completed"))
    drain()
    r = rows(seeded["accounting"])[0]
    assert r["due_date"] == "2027-01-28"
    assert r["status"] == "not_started"
    with read_session() as s:
        runs = list(s.scalars(select(AutomationRun)))
    assert len(runs) == 1 and runs[0].status == "succeeded" and runs[0].changes_count >= 2


def test_rule_does_not_loop_on_its_own_changes(seeded: dict[str, str]) -> None:
    ws = uuid.UUID(seeded["grants"])
    run(
        SaveRule(
            workspace_id=ws,
            name="Ping-pong",
            trigger=TriggerSpec(type="field_changed", config={"field": "notes"}),
            actions=[ActionSpec(type="set_field", config={"field": "notes", "value": "touched"})],
        )
    )
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "Loop", "client": _client()}))["id"])
    run(UpdateItemField(item_id=iid, field="notes", value="hello"))
    drain()
    with read_session() as s:
        n = len(list(s.scalars(select(AutomationRun))))
    assert n <= 3  # bounded by the cascade depth limit, never infinite


def test_date_rule_highlights_once_per_date(seeded: dict[str, str]) -> None:
    ws = uuid.UUID(seeded["grants"])
    run(
        SaveRule(
            workspace_id=ws,
            name="Expiry approaching",
            trigger=TriggerSpec(
                type="date_reached",
                config={
                    "field": "ap_submit_date",
                    "offset": {"amount": 1, "unit": "m", "direction": "before"},
                },
            ),
            actions=[ActionSpec(type="highlight", config={"color": "red"})],
        )
    )
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    c = _client()
    run(CreateItem(board_id=b, values={"name": "soon", "client": c, "ap_submit_date": "2026-11-05"}))
    run(CreateItem(board_id=b, values={"name": "later", "client": c, "ap_submit_date": "2027-03-01"}))
    set_clock(datetime(2026, 10, 12, 1, 0, tzinfo=UTC))
    assert run_date_rules().startswith("fired 1")
    assert run_date_rules().startswith("fired 0")  # idempotent per date value
    hl = {r["name"]: r["highlight_color"] for r in rows(seeded["grants"])}
    assert hl == {"soon": "red", "later": None}


def test_mentions_create_notifications(seeded: dict[str, str]) -> None:
    author = make_user("author@example.com", "Author", {"grants": "member"})
    target = make_user("win@example.com", "Win Yang", {"grants": "member"})
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "N", "client": _client()}))["id"])
    run(
        AddComment(
            entity_type="item", entity_id=iid, body=f"@[Win Yang](user:{target.user_id}) please follow up"
        ),
        actor=author,
    )
    drain()
    drain()  # retries are idempotent
    with read_session() as s:
        n = notifications_for(s, target)
    assert n["unread"] == 1 and "mentioned you" in n["rows"][0]["title"]
    assert rows(seeded["grants"])[0]["last_comment"]["body"].endswith("please follow up")


def test_tasks_with_subtasks(seeded: dict[str, str]) -> None:
    b = uuid.UUID(boards(seeded["accounting"])["ITR"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "T", "client": _client()}))["id"])
    parent = uuid.UUID(run(CreateTask(item_id=iid, title="Prepare"))["id"])
    run(CreateTask(item_id=iid, title="Sub", parent_task_id=parent))
    with read_session() as s:
        ts = tasks_for_item(s, SYSTEM_ACTOR, iid)
    assert [t["status"] for t in ts] == ["not_started_yet", "not_started_yet"]
    assert rows(seeded["accounting"])[0]["task_count"] == 2
    assert run(DeleteTask(task_id=parent)) == {"deleted": 2}
