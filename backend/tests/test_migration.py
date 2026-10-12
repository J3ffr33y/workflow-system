import os
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.db import read_session
from app.core.errors import ValidationFailed
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.identity.models import User
from app.modules.migration.commands import (
    CreateRun,
    PrepareRun,
    RollbackRun,
    StartCommit,
    UpdateMapping,
    ValidateRun,
)
from app.modules.migration.models import MigrationRow, MigrationRun
from app.modules.migration.queries import run_detail
from app.modules.migration.sources import ErpNextClient, fetch_erpnext_projects, parse_csv
from app.platform.events.dispatcher import drain
from app.platform.permissions import SYSTEM_ACTOR
from tests.conftest import make_user, run
from tests.test_items import boards, rows

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> bytes:
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


def _people() -> None:
    for email, name, aliases in [
        ("alice@example.com", "Alice Partner", []),
        ("bob@example.com", "Bob Manager", []),
        ("carol@example.com", "Carol Prep", []),
        ("dan@example.com", "Dan Prep", []),
    ]:
        make_user(email, name, {"accounting": "member", "grants": "member"}, aliases=aliases)


def _create_run(ws: str, board: str, fixture: str) -> uuid.UUID:
    table = parse_csv(_load(fixture), key_columns=["Client Name"])
    return uuid.UUID(
        run(
            CreateRun(
                workspace_id=uuid.UUID(ws),
                board_id=uuid.UUID(board),
                name=fixture,
                source_meta={"filename": fixture, **table.meta},
                headers=table.headers,
                rows=table.rows,
                keys=table.keys,
            )
        )["id"]
    )


def _detail(run_id: uuid.UUID) -> dict[str, Any]:
    with read_session() as s:
        return run_detail(s, SYSTEM_ACTOR, run_id)


def test_csv_detects_gbk_and_excel_artefacts() -> None:
    t = parse_csv(_load("grants_export_gbk.csv"))
    assert t.meta["encoding"] == "gb18030"
    assert t.rows[0]["updates"] == "联系客户准备kickoff"
    assert "\n" in t.rows[1]["Primary Communication"]


def test_suggested_mapping_for_accounting_export(seeded: dict[str, str]) -> None:
    rid = _create_run(
        seeded["accounting"],
        boards(seeded["accounting"])["Financials & Tax Return"],
        "accounting_export_gbk.csv",
    )
    cols = _detail(rid)["mapping"]["columns"]
    assert cols["Client Name"] == "client.name"
    assert cols["Lodgement Due"] == "item.due_date"
    assert cols["Preparer"] == "item.role.preparer"
    assert cols["Entity"] == "entity.entity_type"
    assert cols["updates"] == "comment"
    assert cols["Last Updated"] == "ignore"
    assert cols["Software"] == "item.software"
    assert cols["Budget"] == "item.budget"


def test_full_accounting_import_and_rollback(seeded: dict[str, str]) -> None:
    _people()
    ws = seeded["accounting"]
    rid = _create_run(ws, boards(ws)["Financials & Tax Return"], "accounting_export_gbk.csv")
    d = _detail(rid)
    # Unknown status and unknown person are proposed for creation, not guessed.
    assert d["mapping"]["values"]["Status"]["Waiting for signed EL"] == "__new__"
    assert d["mapping"]["values"]["Preparer"]["Erin Newbie"] == "__new__"

    stats = run(ValidateRun(run_id=rid))
    assert stats["pending_new_values"]
    with pytest.raises(ValidationFailed):
        run(StartCommit(run_id=rid))  # must prepare first
    created = run(PrepareRun(run_id=rid))
    assert created == {"statuses": 1, "placeholder_users": 1}
    stats = run(ValidateRun(run_id=rid))
    assert stats.get("error_rows", 0) == 0
    run(StartCommit(run_id=rid))
    drain()

    d = _detail(rid)
    assert d["status"] == "committed"
    assert d["stats"]["report"]["outcomes"] == {"created": 5}
    due = next(c for c in d["stats"]["report"]["columns"] if c["header"] == "Lodgement Due")
    assert due["source_non_empty"] == due["imported_non_empty"] == 4

    items = rows(ws)
    assert len(items) == 5
    smith = [r for r in items if r["client_name"] == "SMITH, John"]
    assert len(smith) == 2  # duplicate client rows -> one client, two items
    nw = next(r for r in items if r["client_name"] == "Northwind Trading Pty Ltd")
    assert nw["due_date"] == "2027-05-15"
    assert len(nw["roles"]["preparer"]) == 2
    assert nw["data"]["year_end"] == 6 and nw["data"]["budget"] == 1500
    assert nw["name"] == "Northwind Trading Pty Ltd - Financials & Tax Return"
    with read_session() as s:
        assert (
            s.scalar(select(ClientEntity.entity_type).join(Client).where(Client.name == "Blue Gum Trust"))
            == "trust"
        )
        assert s.scalar(select(User.is_placeholder).where(User.full_name == "Erin Newbie")) is True
    assert any(r["last_comment"] and "客户已付款" in r["last_comment"]["body"] for r in items)

    # Re-running the same import updates instead of duplicating.
    rid2 = _create_run(ws, boards(ws)["Financials & Tax Return"], "accounting_export_gbk.csv")
    run(ValidateRun(run_id=rid2))
    run(StartCommit(run_id=rid2))
    drain()
    assert _detail(rid2)["stats"]["report"]["outcomes"] == {"updated": 5}
    assert len(rows(ws)) == 5

    run(RollbackRun(run_id=rid))
    assert rows(ws) == []
    with read_session() as s:
        assert s.scalar(select(MigrationRun.status).where(MigrationRun.id == rid)) == "rolled_back"


def test_grants_import_puts_client_facts_on_the_client(seeded: dict[str, str]) -> None:
    ws = seeded["grants"]
    rid = _create_run(ws, boards(ws)["FY 2026"], "grants_export_gbk.csv")
    cols = _detail(rid)["mapping"]["columns"]
    assert cols["Portal Access Expiry"] == "client.data.portal_access_expiry"
    assert cols["Contact Name"] == "contact.name"
    assert cols["Responsible Person"] == "item.role.responsible"
    run(UpdateMapping(run_id=rid, options={"name_template": "{client} R&D {fy/cy}"}))
    run(ValidateRun(run_id=rid))
    run(PrepareRun(run_id=rid))
    run(ValidateRun(run_id=rid))
    run(StartCommit(run_id=rid))
    drain()
    with read_session() as s:
        errors = [r.issues for r in s.scalars(select(MigrationRow).where(MigrationRow.outcome == "error"))]
    assert errors == []
    items = {r["client_name"]: r for r in rows(ws)}
    wattle = items["Wattle Labs Pty Ltd"]
    assert wattle["data"]["tg_tax_agent"] is True
    assert wattle["data"]["ap_submit_date"] == "2026-09-11"
    assert wattle["data"]["engagement_date"] == "2026-08"
    assert wattle["mirrors"]["portal_access_expiry"] == "2028-04-01"
    assert wattle["mirrors"]["contact_name"] == "璐璐"
    assert wattle["status"] == "reviewing_r_d_evidence"
    assert wattle["name"] == "Wattle Labs Pty Ltd R&D FY"
    assert "grants_priority" not in items["Quokka Robotics Pty Ltd"]["data"]  # "'-" means empty
    with read_session() as s:
        assert s.scalar(select(func_count()).select_from(Contact)) == 2


def func_count() -> Any:
    from sqlalchemy import func

    return func.count()


def test_erpnext_source_flattens_projects() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/resource/User":
            return httpx.Response(200, json={"data": [{"name": "alice@x.com", "full_name": "Alice Partner"}]})
        if p == "/api/resource/Project":
            return httpx.Response(200, json={"data": [{"name": "PROJ-0001"}]})
        if p == "/api/resource/Project/PROJ-0001":
            return httpx.Response(200, json={"data": {
                "name": "PROJ-0001", "project_name": "Northwind ITR", "customer": "CUST-1", "status": "Hold",
                "custom_lodgement_due_date": "2027-05-15",
                "custom_team_members": [{"user": "alice@x.com", "role": "Partner"}],
                "custom_softwares": [{"software": "Xero"}]}})  # fmt: skip
        if p == "/api/resource/Customer/CUST-1":
            return httpx.Response(200, json={"data": {
                "customer_name": "Northwind Trading", "custom_entities": [
                    {"entity_type": "Company", "abn": "51824753556", "is_primary": 1}]}})  # fmt: skip
        if p == "/api/resource/Comment":
            return httpx.Response(
                200, json={"data": [{"owner": "alice@x.com", "content": "hi", "creation": "x"}]}
            )
        if p == "/api/resource/Monthly Status":
            return httpx.Response(200, json={"data": [{"month_index": 1, "status": "Done"}]})
        return httpx.Response(404)

    client = ErpNextClient("https://erp.example", "k", "s", transport=httpx.MockTransport(handler))
    t = fetch_erpnext_projects(client, ["ITR"])
    row = t.rows[0]
    assert t.keys == ["PROJ-0001"]
    assert row["_customer_name"] == "Northwind Trading"
    assert row["_team:Partner"] == "Alice Partner"
    assert row["_softwares"] == "Xero"
    assert row["_comments"][0]["author"] == "Alice Partner"
    assert row["_monthly_status"] == {"1": "Done"}


def test_erpnext_empty_body_is_a_failure_not_no_data() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = ErpNextClient("https://erp.example", "k", "s", transport=transport)
    with pytest.raises(ValidationFailed) as e:
        fetch_erpnext_projects(client, ["ITR"])
    assert e.value.code == "erpnext_bad_response"
