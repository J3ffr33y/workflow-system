import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.core.db import read_session
from app.core.time import set_clock
from app.modules.clients.commands import CreateClient
from app.modules.items.commands import CreateItem
from app.modules.tasks.commands import CreateTask, DeleteTask, UpdateTask
from app.modules.tasks.queries import my_tasks
from app.platform.permissions import Actor
from tests.conftest import make_user, run
from tests.test_items import boards


@pytest.fixture(autouse=True)
def reset_clock() -> Any:
    yield
    set_clock(None)


def _item(board: str, name: str = "Job") -> uuid.UUID:
    client = run(CreateClient(name=f"Client {name}"))["id"]
    return uuid.UUID(
        run(CreateItem(board_id=uuid.UUID(board), values={"name": name, "client": client}))["id"]
    )


def _task(item: uuid.UUID, title: str, who: Actor | None, due: date | None = None) -> uuid.UUID:
    members = {"preparer": [who.user_id]} if who else {}
    return uuid.UUID(run(CreateTask(item_id=item, title=title, due_date=due, members=members))["id"])  # type: ignore[dict-item]


def _mine(actor: Actor) -> list[dict[str, Any]]:
    with read_session() as s:
        return my_tasks(s, actor)


def test_my_tasks_buckets_and_excludes_closed_and_others(seeded: dict[str, str]) -> None:
    # Thursday 15 Oct 2026, midday Sydney: the week ends Sunday 18 Oct.
    set_clock(datetime(2026, 10, 15, 1, 0, tzinfo=UTC))
    me = make_user("me@example.com", "Me", {"accounting": "member"})
    other = make_user("other@example.com", "Other", {"accounting": "member"})
    item = _item(boards(seeded["accounting"])["ITR"])

    _task(item, "late", me, date(2026, 10, 14))
    _task(item, "sunday", me, date(2026, 10, 18))
    _task(item, "monday", me, date(2026, 10, 19))
    _task(item, "whenever", me)
    done = _task(item, "finished", me, date(2026, 10, 1))
    run(UpdateTask(task_id=done, status="done"))
    gone = _task(item, "deleted", me)
    run(DeleteTask(task_id=gone))
    _task(item, "not mine", other)

    got = {t["title"]: t["bucket"] for t in _mine(me)}
    assert got == {"late": "overdue", "sunday": "this_week", "monday": "later", "whenever": "no_date"}
    first = _mine(me)[0]
    assert first["item_name"] == "Job" and first["board_name"] == "ITR" and first["my_roles"] == ["preparer"]
    assert [t["title"] for t in _mine(other)] == ["not mine"]


def test_my_tasks_respects_workspace_access(seeded: dict[str, str]) -> None:
    me = make_user("me@example.com", "Me", {"accounting": "member", "grants": "member"})
    _task(_item(boards(seeded["grants"])["FY 2026"], "G"), "grant task", me)
    _task(_item(boards(seeded["accounting"])["ITR"], "A"), "acct task", me)
    assert sorted(t["title"] for t in _mine(me)) == ["acct task", "grant task"]

    # Same person seen through an accounting-only membership no longer sees grants work.
    acct_only = replace(me, roles={k: v for k, v in me.roles.items() if k == uuid.UUID(seeded["accounting"])})
    assert [t["title"] for t in _mine(acct_only)] == ["acct task"]


def test_my_tasks_empty_for_new_user(seeded: dict[str, str]) -> None:
    assert _mine(make_user("new@example.com", "New", {"accounting": "member"})) == []
