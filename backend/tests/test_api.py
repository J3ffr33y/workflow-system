import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.platform.events.dispatcher import drain
from tests.conftest import make_user

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def client(seeded: dict[str, str]) -> TestClient:
    make_user("admin@example.com", "Admin", {"accounting": "admin", "grants": "admin"}, superadmin=True)
    return TestClient(create_app())


def login(c: TestClient, email: str = "admin@example.com") -> dict[str, str]:
    r = c.post("/api/auth/login", json={"email": email, "password": "Sup3r-secret-pw"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf"]}


def test_login_me_and_bad_password(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_credentials"
    login(client)
    me = client.get("/api/auth/me").json()
    assert {w["key"] for w in me["workspaces"]} == {"accounting", "grants"}


def test_commands_require_csrf(client: TestClient) -> None:
    h = login(client)
    r = client.post("/api/commands/clients.create", json={"name": "No CSRF"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = client.post("/api/commands/clients.create", json={"name": "With CSRF"}, headers=h)
    assert r.status_code == 200 and r.json()["result"]["id"]


def test_internal_commands_are_not_exposed(client: TestClient) -> None:
    h = login(client)
    r = client.post("/api/commands/notifications.deliver", json={}, headers=h)
    assert r.status_code == 404


def test_board_flow_over_http(client: TestClient) -> None:
    h = login(client)
    me = client.get("/api/auth/me").json()
    ws = next(w for w in me["workspaces"] if w["key"] == "grants")
    schema = client.get(f"/api/workspaces/{ws['id']}/schema").json()
    board = next(b for b in schema["boards"] if b["name"] == "FY 2026")
    cid = client.post("/api/commands/clients.create", json={"name": "HTTP Client"}, headers=h).json()[
        "result"
    ]["id"]
    r = client.post(
        "/api/commands/items.create",
        json={
            "board_id": board["id"],
            "values": {"name": "HTTP item", "client": cid, "grants_priority": "s1"},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    item_id = r.json()["result"]["id"]
    r = client.post(
        "/api/commands/items.update_field",
        json={
            "item_id": item_id,
            "field": "status",
            "value": "hold",
            "expected": "not_started",
            "check_expected": True,
        },
        headers=h,
    )
    assert r.status_code == 200
    r = client.post(
        "/api/commands/items.update_field",
        json={
            "item_id": item_id,
            "field": "status",
            "value": "completed",
            "expected": "not_started",
            "check_expected": True,
        },
        headers=h,
    )
    assert r.status_code == 409 and r.json()["error"]["details"]["current"] == "hold"
    rows = client.post(
        "/api/items/query", json={"workspace_id": ws["id"], "board_ids": [board["id"]]}, headers=h
    ).json()
    assert rows["total"] == 1 and rows["rows"][0]["status"] == "hold"

    csv_resp = client.post(
        "/api/export/items.csv",
        json={
            "workspace_id": ws["id"],
            "board_ids": [board["id"]],
            "columns": ["name", "client", "status", "grants_priority"],
        },
        headers=h,
    )
    text = csv_resp.content.decode("utf-8")
    assert text.startswith("﻿Project Name,Client,Status,Grants Priority")
    assert "HTTP item,HTTP Client,Hold,S1" in text

    activity = client.get("/api/activity/entity", params={"entity_type": "item", "entity_id": item_id}).json()
    assert any(any(c["field"] == "status" for c in e["changes"]) for e in activity)


def test_migration_over_http(client: TestClient) -> None:
    h = login(client)
    me = client.get("/api/auth/me").json()
    ws = next(w for w in me["workspaces"] if w["key"] == "grants")
    board = next(
        b for b in client.get(f"/api/workspaces/{ws['id']}/schema").json()["boards"] if b["name"] == "FY 2026"
    )
    with open(os.path.join(FIX, "grants_export_gbk.csv"), "rb") as f:
        r = client.post(
            "/api/migration/upload-csv",
            data={"workspace_id": ws["id"], "board_id": board["id"]},
            files={"file": ("grants.csv", f, "text/csv")},
            headers=h,
        )
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    for cmd in ("migration.validate", "migration.prepare", "migration.validate", "migration.start_commit"):
        rr = client.post(f"/api/commands/{cmd}", json={"run_id": run_id}, headers=h)
        assert rr.status_code == 200, (cmd, rr.text)
    drain()
    detail = client.get(f"/api/migration/runs/{run_id}").json()
    assert detail["status"] == "committed"
    assert detail["stats"]["report"]["outcomes"] == {"created": 4}
