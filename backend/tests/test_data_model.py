from fastapi.testclient import TestClient

import app.models  # noqa: F401  (registers every table on the metadata)
from app.core.db import Base
from app.main import create_app
from app.modules.clients.commands import CreateClient
from app.modules.system.queries import data_model
from tests.conftest import make_user, run
from tests.test_api import login


def test_describes_every_table_from_the_live_schema() -> None:
    tables = {t["name"]: t for t in data_model()}
    assert set(tables) == set(Base.metadata.tables)

    items = tables["items"]
    assert items["module"] == "items"
    assert items["soft_delete"] and items["audited"] and items["has_custom_data"]
    client_id = next(c for c in items["columns"] if c["name"] == "client_id")
    assert client_id["references"]["table"] == "clients" and client_id["nullable"]

    assert tables["audit_entries"]["module"] == "platform"
    assert not tables["contacts"]["has_custom_data"]
    # Composite uniqueness carries a business rule: one key per workspace and entity kind.
    assert ["workspace_id", "entity_kind", "key"] in tables["field_definitions"]["unique_together"]


def test_endpoint_shows_structure_scoped_to_workspaces_and_no_rows(seeded: dict[str, str]) -> None:
    make_user("grants@example.com", "Grants Only", {"grants": "member"})
    run(CreateClient(name="Zebra Secret Pty Ltd"))
    c = TestClient(create_app())
    assert c.get("/api/meta/data-model").status_code == 401

    login(c, "grants@example.com")
    r = c.get("/api/meta/data-model")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Zebra Secret" not in r.text
    assert {t["name"] for t in body["tables"]} == set(Base.metadata.tables)
    assert [w["workspace"]["key"] for w in body["custom_fields"]] == ["grants"]
    assert body["field_types"]["mirror"]

    fields = body["custom_fields"][0]["fields"]
    client_field = next(f for f in fields if f["entity_kind"] == "client")
    assert client_field["stored_in"] == "clients.data"
    mirror = next(f for f in fields if f["type"] == "mirror")
    assert mirror["stored_in"] is None and mirror["mirror_of"]["of"] in ("client", "entity", "contact")
