"""API tokens, webhooks, external IDs and field defaults: the extension points
other systems will use."""

import hashlib
import hmac
import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.integrations import subscribers as webhooks
from app.platform.events.dispatcher import drain
from tests.conftest import make_user

PW = "Sup3r-secret-pw"


@pytest.fixture
def api(seeded: dict[str, str]) -> TestClient:
    make_user("admin@example.com", "Admin", {"accounting": "admin", "grants": "admin"}, superadmin=True)
    make_user("member@example.com", "Member", {"grants": "member"})
    return TestClient(create_app())


def login(c: TestClient, email: str) -> dict[str, str]:
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf"]}


def new_token(c: TestClient, email: str, **kw: Any) -> str:
    h = login(c, email)
    r = c.post("/api/commands/identity.create_api_token", json={"name": "script", **kw}, headers=h)
    assert r.status_code == 200, r.text
    c.cookies.clear()  # what follows must work on the token alone
    token: str = r.json()["result"]["token"]
    return token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def grants_board(c: TestClient, h: dict[str, str]) -> tuple[str, str]:
    ws = next(w for w in c.get("/api/auth/whoami", headers=h).json()["workspaces"] if w["key"] == "grants")
    schema = c.get(f"/api/workspaces/{ws['id']}/schema", headers=h).json()
    return ws["id"], next(b["id"] for b in schema["boards"] if b["name"] == "FY 2026")


# --- API tokens ---------------------------------------------------------------------
def test_token_reads_and_writes_without_csrf_and_is_audited_as_api(api: TestClient) -> None:
    h = bearer(new_token(api, "member@example.com"))
    me = api.get("/api/auth/whoami", headers=h).json()
    assert me["via"] == "token" and me["display"] == "Member"
    assert [w["key"] for w in me["workspaces"]] == ["grants"]

    _, board = grants_board(api, h)
    cid = api.post("/api/commands/clients.create", json={"name": "Token Co"}, headers=h).json()["result"][
        "id"
    ]
    r = api.post(
        "/api/commands/items.create",
        json={"board_id": board, "values": {"name": "Via API", "client": cid}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    act = api.get(
        "/api/activity/entity",
        params={"entity_type": "item", "entity_id": r.json()["result"]["id"]},
        headers=h,
    ).json()
    assert act and act[0]["origin"] == "api"


def test_token_keeps_owner_permissions(api: TestClient) -> None:
    h = bearer(new_token(api, "member@example.com"))
    r = api.get("/api/integrations/webhooks", headers=h)
    assert r.status_code == 403


def test_bad_revoked_and_expired_tokens_are_rejected(api: TestClient) -> None:
    assert api.get("/api/auth/whoami", headers=bearer("flow_pat_nope")).status_code == 401
    token = new_token(api, "member@example.com")
    hs = login(api, "member@example.com")
    tokens = api.get("/api/auth/api-tokens").json()
    assert len(tokens) == 1 and tokens[0]["active"] and token.startswith(tokens[0]["prefix"])
    assert "token" not in tokens[0] and "token_hash" not in tokens[0]
    r = api.post("/api/commands/identity.revoke_api_token", json={"token_id": tokens[0]["id"]}, headers=hs)
    assert r.status_code == 200
    api.cookies.clear()
    r = api.get("/api/auth/whoami", headers=bearer(token))
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_token"


def test_read_only_token_cannot_run_commands(api: TestClient) -> None:
    h = bearer(new_token(api, "member@example.com", read_only=True))
    assert api.get("/api/clients", headers=h).status_code == 200
    r = api.post("/api/commands/clients.create", json={"name": "Nope"}, headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "token_read_only"


def test_token_cannot_mint_tokens_or_change_password(api: TestClient) -> None:
    h = bearer(new_token(api, "member@example.com"))
    r = api.post("/api/commands/identity.create_api_token", json={"name": "more"}, headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "session_only"
    r = api.post(
        "/api/commands/identity.change_own_password",
        json={"current_password": PW, "new_password": "An0ther-secret-pw"},
        headers=h,
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "session_only"


def test_deactivating_a_user_revokes_their_tokens(api: TestClient) -> None:
    token = new_token(api, "member@example.com")
    h = login(api, "admin@example.com")
    uid = api.get("/api/auth/whoami", headers=bearer(token)).json()["user_id"]
    for active in (False, True):
        r = api.post(
            "/api/commands/identity.update_user", json={"user_id": uid, "is_active": active}, headers=h
        )
        assert r.status_code == 200, r.text
    api.cookies.clear()
    assert api.get("/api/auth/whoami", headers=bearer(token)).status_code == 401


def test_required_on_create_is_enforced_for_api_callers(api: TestClient) -> None:
    h = bearer(new_token(api, "admin@example.com"))
    ws = next(
        w for w in api.get("/api/auth/whoami", headers=h).json()["workspaces"] if w["key"] == "accounting"
    )
    schema = api.get(f"/api/workspaces/{ws['id']}/schema", headers=h).json()
    board = next(b["id"] for b in schema["boards"] if b["name"] == "ITR")
    cid = api.post("/api/commands/clients.create", json={"name": "Req Co"}, headers=h).json()["result"]["id"]
    r = api.post(
        "/api/commands/items.create",
        json={"board_id": board, "values": {"name": "x", "client": cid}},
        headers=h,
    )
    assert r.status_code == 422
    assert set(r.json()["error"]["details"]["fields"]) == {"company", "fiscal_year"}


# --- field defaults -------------------------------------------------------------------
def test_field_default_applies_on_new_item_only_when_left_out(api: TestClient) -> None:
    h = bearer(new_token(api, "admin@example.com"))
    ws, board = grants_board(api, h)
    schema = api.get(f"/api/workspaces/{ws}/schema", headers=h).json()
    field = next(f for f in schema["field_definitions"] if f["key"] == "grants_priority")
    r = api.post(
        "/api/commands/fields.update",
        json={"field_id": field["id"], "config": {"default": "nope"}},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_default"
    r = api.post(
        "/api/commands/fields.update", json={"field_id": field["id"], "config": {"default": "S3"}}, headers=h
    )
    assert r.status_code == 200, r.text

    cid = api.post("/api/commands/clients.create", json={"name": "Def Co"}, headers=h).json()["result"]["id"]
    for name, values in [("defaulted", {}), ("explicit", {"grants_priority": "s1"})]:
        r = api.post(
            "/api/commands/items.create",
            json={"board_id": board, "values": {"name": name, "client": cid, **values}},
            headers=h,
        )
        assert r.status_code == 200, r.text
    rows = api.post("/api/items/query", json={"workspace_id": ws, "board_ids": [board]}, headers=h).json()
    got = {row["name"]: row["data"].get("grants_priority") for row in rows["rows"]}
    assert got == {"defaulted": "s3", "explicit": "s1"}


# --- webhooks ---------------------------------------------------------------------
@pytest.fixture
def receiver() -> Iterator[list[httpx.Request]]:
    seen: list[httpx.Request] = []
    state = {"fail": False}

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if "down" in str(req.url) or state["fail"]:
            return httpx.Response(503, text="maintenance")
        return httpx.Response(204)

    webhooks.transport = httpx.MockTransport(handle)
    yield seen
    webhooks.transport = None


def save_hook(api: TestClient, h: dict[str, str], **kw: Any) -> dict[str, Any]:
    body = {"name": "hook", "url": "https://example.test/hook", "event_types": ["item.*"], **kw}
    r = api.post("/api/commands/integrations.save_webhook", json=body, headers=h)
    assert r.status_code == 200, r.text
    result: dict[str, Any] = r.json()["result"]
    return result


def test_webhook_receives_signed_events(api: TestClient, receiver: list[httpx.Request]) -> None:
    h = login(api, "admin@example.com")
    hook = save_hook(api, h)
    assert hook["secret"].startswith("whsec_")
    _, board = grants_board(api, h)
    cid = api.post("/api/commands/clients.create", json={"name": "Hook Co"}, headers=h).json()["result"]["id"]
    api.post(
        "/api/commands/items.create",
        json={"board_id": board, "values": {"name": "Hooked", "client": cid}},
        headers=h,
    )
    drain()
    item_events = [r for r in receiver if r.headers["X-Flow-Event"].startswith("item.")]
    assert item_events, "item.created should reach the endpoint"
    assert not [r for r in receiver if r.headers["X-Flow-Event"].startswith("client.")]
    req = item_events[0]
    t, v1 = (p.split("=", 1)[1] for p in req.headers["X-Flow-Signature"].split(","))
    expected = hmac.new(hook["secret"].encode(), f"{t}.".encode() + req.content, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(v1, expected)
    body = json.loads(req.content)
    assert body["type"] == req.headers["X-Flow-Event"] and body["entity_type"] == "item"
    assert str(body["id"]) == req.headers["X-Flow-Event-Id"]

    deliveries = api.get(f"/api/integrations/webhooks/{hook['id']}/deliveries").json()
    assert deliveries and all(d["status"] == "done" for d in deliveries)
    assert "secret" not in api.get("/api/integrations/webhooks").json()[0]


def test_one_failing_endpoint_does_not_resend_to_the_healthy_one(
    api: TestClient, receiver: list[httpx.Request]
) -> None:
    h = login(api, "admin@example.com")
    ok = save_hook(api, h, name="ok", event_types=["client.created"])
    down = save_hook(api, h, name="down", url="https://down.example.test/", event_types=["client.created"])
    api.post("/api/commands/clients.create", json={"name": "Retry Co"}, headers=h)
    drain()
    from sqlalchemy import text

    from app.core.db import write_session
    from app.platform.events.dispatcher import process_batch

    # Make the failed outbox delivery due now instead of waiting for backoff.
    with write_session() as s, s.begin():
        s.execute(
            text("UPDATE event_deliveries SET next_attempt_at = now() WHERE subscriber = 'webhooks.dispatch'")
        )
    process_batch()
    to_ok = [r for r in receiver if "down" not in str(r.url)]
    to_down = [r for r in receiver if "down" in str(r.url)]
    assert len(to_ok) == 1 and len(to_down) == 2
    d_ok = api.get(f"/api/integrations/webhooks/{ok['id']}/deliveries").json()
    d_down = api.get(f"/api/integrations/webhooks/{down['id']}/deliveries").json()
    assert d_ok[0]["status"] == "done" and d_ok[0]["attempts"] == 1
    assert (
        d_down[0]["status"] == "failed" and d_down[0]["attempts"] == 2 and d_down[0]["response_status"] == 503
    )


def test_webhook_rules(api: TestClient, receiver: list[httpx.Request]) -> None:
    h = login(api, "admin@example.com")
    for bad in (["*"], ["user.*"], ["api_token.created"], []):
        r = api.post(
            "/api/commands/integrations.save_webhook",
            json={"name": "x", "url": "https://example.test/", "event_types": bad},
            headers=h,
        )
        assert r.status_code == 422, bad
    hook = save_hook(api, h, event_types=["client.*"])
    api.post("/api/commands/integrations.save_webhook",
             json={"webhook_id": hook["id"], "name": "hook", "url": "https://example.test/hook",
                   "event_types": ["client.*"], "is_enabled": False}, headers=h)  # fmt: skip
    api.post("/api/commands/clients.create", json={"name": "Silent Co"}, headers=h)
    drain()
    assert receiver == []
    r = api.post(
        "/api/commands/integrations.rotate_webhook_secret", json={"webhook_id": hook["id"]}, headers=h
    )
    assert r.json()["result"]["secret"] != hook["secret"]
    api.post("/api/commands/integrations.delete_webhook", json={"webhook_id": hook["id"]}, headers=h)
    assert api.get("/api/integrations/webhooks").json() == []


def test_webhook_management_is_admin_only(api: TestClient) -> None:
    h = login(api, "member@example.com")
    r = api.post(
        "/api/commands/integrations.save_webhook",
        json={"name": "x", "url": "https://example.test/", "event_types": ["item.*"]},
        headers=h,
    )
    assert r.status_code == 403


# --- external refs ------------------------------------------------------------------
def test_external_refs_link_lookup_and_move(api: TestClient) -> None:
    h = bearer(new_token(api, "member@example.com"))
    a = api.post("/api/commands/clients.create", json={"name": "A"}, headers=h).json()["result"]["id"]
    b = api.post("/api/commands/clients.create", json={"name": "B"}, headers=h).json()["result"]["id"]
    link = {"system": "xero", "external_type": "Contact", "external_id": "x-123", "entity_type": "client"}
    r = api.post("/api/commands/external_refs.link", json={**link, "entity_id": a}, headers=h)
    assert r.status_code == 200, r.text
    found = api.get(
        "/api/integrations/external-refs", params={"system": "xero", "external_id": "x-123"}, headers=h
    )
    assert [x["entity_id"] for x in found.json()] == [a]
    api.post("/api/commands/external_refs.link", json={**link, "entity_id": b}, headers=h)
    by_entity = api.get("/api/integrations/external-refs", params={"entity_id": b}, headers=h).json()
    assert [x["external_id"] for x in by_entity] == ["x-123"]
    assert api.get("/api/integrations/external-refs", params={"entity_id": a}, headers=h).json() == []
    r = api.post(
        "/api/commands/external_refs.link",
        json={**link, "entity_type": "user", "entity_id": str(uuid.uuid4())},
        headers=h,
    )
    assert r.status_code == 422
