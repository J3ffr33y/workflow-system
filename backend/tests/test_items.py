import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.core.db import read_session
from app.core.errors import Conflict, ValidationFailed
from app.modules.activity.commands import RevertChanges
from app.modules.clients.commands import (
    ArchiveClient,
    CreateClient,
    EntityInput,
    RestoreClient,
    UpdateClient,
    UpsertContact,
)
from app.modules.items.commands import (
    ArchiveItems,
    BulkUpdateField,
    CreateItem,
    DeleteItems,
    RestoreItems,
    RolloverItems,
    SetPeriodValue,
    UpdateItemField,
)
from app.modules.items.queries import item_detail, list_items
from app.modules.workspaces.commands import ArchiveBoard, RestoreBoard
from app.modules.workspaces.models import Board, FiscalYear, LookupValue
from app.platform.commands import Origin
from app.platform.permissions import SYSTEM_ACTOR
from tests.conftest import make_user, run, run_full


def boards(ws: str) -> dict[str, str]:
    with read_session() as s:
        return {
            b.name: str(b.id) for b in s.scalars(select(Board).where(Board.workspace_id == uuid.UUID(ws)))
        }


def fy(label: str) -> str:
    with read_session() as s:
        return str(s.scalar(select(FiscalYear.id).where(FiscalYear.label == label)))


def lookup(label: str) -> str:
    with read_session() as s:
        return str(s.scalar(select(LookupValue.id).where(LookupValue.label == label)))


def rows(ws: str, **kw: Any) -> list[dict[str, Any]]:
    return list_items_for(ws, **kw)["rows"]


def list_items_for(ws: str, **kw: Any) -> dict[str, Any]:
    with read_session() as s:
        return list_items(s, SYSTEM_ACTOR, workspace_id=uuid.UUID(ws), **kw)


@pytest.fixture
def partner() -> Any:
    return make_user(
        "cathy@example.com", "Cathy Lau", {"accounting": "admin", "grants": "admin"}, aliases=["CL"]
    )


@pytest.fixture
def client_id(partner: Any) -> str:
    return run(
        CreateClient(
            name="Roboworks Global Pty Ltd",
            client_type="company",
            partner_user_id=partner.user_id,
            primary_entity=EntityInput(entity_type="company", abn="51 824 753 556", year_end_month=6),
        )
    )["id"]


def test_create_item_applies_defaults_and_autofill(
    seeded: dict[str, str], client_id: str, partner: Any
) -> None:
    b = boards(seeded["accounting"])["ITR"]
    iid = run(
        CreateItem(
            board_id=uuid.UUID(b),
            values={
                "name": "Roboworks ITR",
                "client": client_id,
                "fiscal_year": fy("2025-2026"),
                "company": lookup("Top Figures"),
            },
        ),
        actor=partner,
    )["id"]
    with read_session() as s:
        d = item_detail(s, partner, uuid.UUID(iid))
    assert d["status"] == "not_started"  # default status
    assert d["data"]["year_end"] == 6  # from primary entity
    assert d["entity"] is not None
    assert d["roles"]["partner"] == [str(partner.user_id)]  # from client partner
    assert d["mirrors"]["entity_type"] == "company"


def test_status_must_be_allowed_on_board(seeded: dict[str, str], client_id: str) -> None:
    b = boards(seeded["accounting"])["ITR"]
    with pytest.raises(ValidationFailed):
        run(CreateItem(board_id=uuid.UUID(b), values={"name": "x", "client": client_id, "status": "nope"}))


def test_cell_edit_detects_concurrent_change(seeded: dict[str, str], client_id: str) -> None:
    b = boards(seeded["grants"])["FY 2026"]
    iid = uuid.UUID(run(CreateItem(board_id=uuid.UUID(b), values={"name": "G1", "client": client_id}))["id"])
    run(
        UpdateItemField(
            item_id=iid, field="status", value="hold", expected="not_started", check_expected=True
        )
    )
    with pytest.raises(Conflict) as e:
        run(
            UpdateItemField(
                item_id=iid, field="status", value="completed", expected="not_started", check_expected=True
            )
        )
    assert e.value.details["current"] == "hold"


def test_bulk_update_roles_add_and_remove(seeded: dict[str, str], client_id: str) -> None:
    a = make_user("a@example.com", "Violet Ma", {"accounting": "member"})
    c = make_user("c@example.com", "Eva Ren", {"accounting": "member"})
    b = uuid.UUID(boards(seeded["accounting"])["BAS"])
    ids = [
        uuid.UUID(run(CreateItem(board_id=b, values={"name": f"BAS {i}", "client": client_id}))["id"])
        for i in range(3)
    ]
    run(BulkUpdateField(item_ids=ids, field="role.preparer", value=[str(a.user_id)], mode="add"))
    run(BulkUpdateField(item_ids=ids[:1], field="role.preparer", value=[str(c.user_id)], mode="add"))
    run(BulkUpdateField(item_ids=ids, field="role.preparer", value=[str(a.user_id)], mode="remove"))
    r = {x["id"]: x for x in rows(seeded["accounting"])}
    assert r[str(ids[0])]["roles"]["preparer"] == [str(c.user_id)]
    assert "preparer" not in r[str(ids[1])]["roles"]


def test_period_grid_cells_are_independent(seeded: dict[str, str], client_id: str) -> None:
    b = uuid.UUID(boards(seeded["accounting"])["Bookkeeping"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "BK", "client": client_id}))["id"])
    run(SetPeriodValue(item_id=iid, field="monthly_status", period=1, value="done"))
    run(SetPeriodValue(item_id=iid, field="monthly_status", period=2, value="working"))
    run(SetPeriodValue(item_id=iid, field="monthly_status", period=1, value=None))
    assert rows(seeded["accounting"])[0]["data"]["monthly_status"] == {"2": "working"}


def test_filters_sort_and_search(seeded: dict[str, str], client_id: str) -> None:
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    for name, prio, date_ in [("A", "s1", "2026-08-01"), ("B", "s2", "2026-09-11"), ("C", None, None)]:
        vals: dict[str, Any] = {"name": name, "client": client_id}
        if prio:
            vals["grants_priority"] = prio
        if date_:
            vals["ap_submit_date"] = date_
        run(CreateItem(board_id=b, values=vals))
    ws = seeded["grants"]
    got = rows(
        ws,
        filter_tree={"field": "grants_priority", "operator": "in", "value": ["s1", "s2"]},
        sort=[{"field": "ap_submit_date", "dir": "desc"}],
    )
    assert [r["name"] for r in got] == ["B", "A"]
    assert [r["name"] for r in rows(ws, filter_tree={"field": "ap_submit_date", "operator": "empty"})] == [
        "C"
    ]
    assert [
        r["name"]
        for r in rows(
            ws, filter_tree={"field": "ap_submit_date", "operator": "before", "value": "2026-09-01"}
        )
    ] == ["A"]
    assert len(rows(ws, search="roboworks")) == 3


def test_archive_restore_and_board_archive(seeded: dict[str, str], client_id: str) -> None:
    bs = boards(seeded["grants"])
    b = uuid.UUID(bs["FY 2025"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "Old", "client": client_id}))["id"])
    run(ArchiveItems(item_ids=[iid]))
    assert rows(seeded["grants"]) == []
    assert rows(seeded["grants"], archived=True)[0]["archive_source"] == "manual"
    run(RestoreItems(item_ids=[iid]))
    run(ArchiveBoard(board_id=b))
    archived = rows(seeded["grants"], archived=True)
    assert archived[0]["archive_source"] == "board_archived"
    with pytest.raises(ValidationFailed) as e:
        run(RestoreItems(item_ids=[iid]))
    assert e.value.code == "needs_target_board"
    run(RestoreBoard(board_id=b))
    assert rows(seeded["grants"])[0]["id"] == str(iid)


def test_client_archive_cascades_only_its_own_archives(seeded: dict[str, str], client_id: str) -> None:
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    keep = uuid.UUID(run(CreateItem(board_id=b, values={"name": "manual", "client": client_id}))["id"])
    other = uuid.UUID(run(CreateItem(board_id=b, values={"name": "cascade", "client": client_id}))["id"])
    run(ArchiveItems(item_ids=[keep]))
    res = run(ArchiveClient(client_id=uuid.UUID(client_id)))
    assert res == {"archived_items": 1, "skipped_items": 0}
    run(RestoreClient(client_id=uuid.UUID(client_id)))
    active = {r["id"] for r in rows(seeded["grants"])}
    assert active == {str(other)}  # the manually archived one stays archived


def test_rollover_to_next_fy_board(seeded: dict[str, str], client_id: str) -> None:
    bs = boards(seeded["grants"])
    src = uuid.UUID(run(CreateItem(board_id=uuid.UUID(bs["FY 2026"]), values={
        "name": "Roboworks FY 2026", "client": client_id, "status": "completed",
        "grants_priority": "s1", "ap_submit_date": "2026-09-11", "notes": "old notes"}))["id"])  # fmt: skip
    res = run(RolloverItems(item_ids=[src], archive_source_items=True))
    new_id = res["created"][0]
    new = next(r for r in rows(seeded["grants"]) if r["id"] == new_id)
    assert new["board_id"] == bs["FY 2027"]
    assert new["name"] == "Roboworks FY 2027"
    assert new["status"] == "not_started"
    assert new["data"].get("grants_priority") == "s1"  # carried
    assert "ap_submit_date" not in new["data"] and "notes" not in new["data"]  # cleared by default
    assert new["fiscal_year"] == fy("2026-2027")
    assert new["rolled_from_id"] == str(src)
    old = rows(seeded["grants"], archived=True)[0]
    assert old["archive_source"] == "rollover" and old["archive_ref"] == new_id


def test_rollover_accounting_same_board_adds_a_year(seeded: dict[str, str], client_id: str) -> None:
    b = uuid.UUID(boards(seeded["accounting"])["ITR"])
    src = uuid.UUID(run(CreateItem(board_id=b, values={
        "name": "Roboworks ITR 2025-2026", "client": client_id, "fiscal_year": fy("2025-2026"),
        "due_date": "2027-05-15", "frequency": "yearly"}))["id"])  # fmt: skip
    new_id = run(RolloverItems(item_ids=[src]))["created"][0]
    new = next(r for r in rows(seeded["accounting"]) if r["id"] == new_id)
    assert new["board_id"] == str(b)
    assert new["fiscal_year"] == fy("2026-2027")
    assert new["due_date"] == "2028-05-15"
    assert new["name"] == "Roboworks ITR 2026-2027"


def test_undo_reverts_and_refuses_to_clobber(seeded: dict[str, str], client_id: str) -> None:
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "U", "client": client_id}))["id"])
    first = run_full(UpdateItemField(item_id=iid, field="notes", value="first"))
    run(RevertChanges(command_id=first.command_id), origin=Origin.UNDO)
    assert "notes" not in rows(seeded["grants"])[0]["data"]

    second = run_full(UpdateItemField(item_id=iid, field="notes", value="second"))
    run(UpdateItemField(item_id=iid, field="notes", value="third"))
    with pytest.raises(ValidationFailed) as e:
        run(RevertChanges(command_id=second.command_id))
    assert e.value.code == "nothing_reverted"


def test_delete_moves_to_trash(seeded: dict[str, str], client_id: str) -> None:
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    iid = uuid.UUID(run(CreateItem(board_id=b, values={"name": "D", "client": client_id}))["id"])
    run(DeleteItems(item_ids=[iid]))
    assert rows(seeded["grants"]) == [] and rows(seeded["grants"], archived=True) == []


def test_mirrors_show_client_facts(seeded: dict[str, str], client_id: str) -> None:
    run(
        UpdateClient(
            client_id=uuid.UUID(client_id), data={"portal_access_expiry": "2028-04-01", "state": "nsw"}
        )
    )
    run(UpsertContact(client_id=uuid.UUID(client_id), name="Lulu", is_primary=True))
    b = uuid.UUID(boards(seeded["grants"])["FY 2026"])
    run(CreateItem(board_id=b, values={"name": "M", "client": client_id}))
    r = rows(seeded["grants"])[0]
    assert r["mirrors"]["portal_access_expiry"] == "2028-04-01"
    assert r["mirrors"]["contact_name"] == "Lulu"
    assert r["mirrors"]["abn"] == "51824753556"
    got = rows(
        seeded["grants"],
        filter_tree={"field": "portal_access_expiry", "operator": "after", "value": "2028-01-01"},
    )
    assert len(got) == 1
