"""Read endpoints. Writes go through /api/commands/*."""

import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentActor, ReadDB
from app.core.errors import PermissionDenied
from app.modules.activity import queries as activity_q
from app.modules.automations import queries as automations_q
from app.modules.automations.registry import catalog as automation_catalog
from app.modules.clients import queries as clients_q
from app.modules.collaboration import queries as collab_q
from app.modules.identity import queries as identity_q
from app.modules.items import queries as items_q
from app.modules.tasks import queries as tasks_q
from app.modules.views import queries as views_q
from app.modules.workspaces import queries as ws_q
from app.platform.fields.types import field_types
from app.platform.permissions import P_USERS_MANAGE

router = APIRouter(tags=["queries"])


# --- workspaces --------------------------------------------------------------------
@router.get("/workspaces")
def workspaces(actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return [
        {"id": str(w.id), "key": w.key, "name": w.name, "item_label": w.item_label}
        for w in ws_q.visible_workspaces(s, actor)
    ]


@router.get("/workspaces/{workspace_id}/schema")
def workspace_schema(workspace_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return ws_q.workspace_schema(s, actor, workspace_id)


@router.get("/meta/field-types")
def meta_field_types(actor: CurrentActor) -> list[dict[str, Any]]:
    return [
        {"key": t.key, "label": t.label, "kind": t.kind.value, "editable": t.editable}
        for t in field_types.all()
    ]


@router.get("/fiscal-years")
def fiscal_years(actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return ws_q.fiscal_years(s)


@router.get("/lookups")
def lookups(actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return ws_q.lookups(s)


# --- items ----------------------------------------------------------------------------
class ItemQuery(BaseModel):
    workspace_id: uuid.UUID
    board_ids: list[uuid.UUID] | None = None
    archived: bool = False
    filter: dict[str, Any] | None = None
    search: str | None = None
    sort: list[dict[str, str]] | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=500)
    client_id: uuid.UUID | None = None


@router.post("/items/query")
def query_items(q: ItemQuery, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    """POST because filter trees do not fit in a URL. Read-only."""
    return items_q.list_items(
        s,
        actor,
        workspace_id=q.workspace_id,
        board_ids=q.board_ids,
        archived=q.archived,
        filter_tree=q.filter,
        search=q.search,
        sort=q.sort,
        offset=q.offset,
        limit=q.limit,
        client_id=q.client_id,
    )


@router.get("/items/{item_id}")
def item(item_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return items_q.item_detail(s, actor, item_id)


@router.get("/items/{item_id}/tasks")
def item_tasks(item_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return tasks_q.tasks_for_item(s, actor, item_id)


@router.get("/home")
def home(actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return items_q.home(s, actor)


@router.get("/home/tasks")
def home_tasks(actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return tasks_q.my_tasks(s, actor)


# --- clients ---------------------------------------------------------------------------
@router.get("/clients")
def clients(
    actor: CurrentActor,
    s: ReadDB,
    search: str | None = None,
    archived: bool = False,
    limit: int = Query(200, le=1000),
    offset: int = 0,
) -> dict[str, Any]:
    return clients_q.list_clients(s, actor, search=search, archived=archived, limit=limit, offset=offset)


@router.get("/clients/check-name")
def client_check_name(
    name: str, actor: CurrentActor, s: ReadDB, exclude_id: uuid.UUID | None = None
) -> dict[str, Any]:
    return clients_q.check_name(s, name, exclude_id)


@router.get("/clients/{client_id}")
def client(client_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return clients_q.client_detail(s, actor, client_id)


@router.get("/clients/{client_id}/entities")
def client_entities(client_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return clients_q.entities_for_clients(s, [client_id]).get(str(client_id), [])


# --- people ---------------------------------------------------------------------------------
@router.get("/users/directory")
def directory(actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return identity_q.directory(s)


@router.get("/users")
def users(actor: CurrentActor, s: ReadDB, search: str | None = None) -> list[dict[str, Any]]:
    if not actor.can(P_USERS_MANAGE):
        raise PermissionDenied("admins only")
    return identity_q.list_users(s, search=search)


# --- views / comments / notifications ----------------------------------------------------------
@router.get("/views")
def views(
    workspace_id: uuid.UUID, actor: CurrentActor, s: ReadDB, board_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    ws_q.require_workspace(s, actor, workspace_id)
    return views_q.list_views(s, actor, workspace_id, board_id)


@router.get("/comments")
def comments(
    entity_type: Literal["item", "client", "task"], entity_id: uuid.UUID, actor: CurrentActor, s: ReadDB
) -> list[dict[str, Any]]:
    return collab_q.comments_for(s, actor, entity_type, entity_id)


@router.get("/notifications")
def notifications(actor: CurrentActor, s: ReadDB, unread_only: bool = False) -> dict[str, Any]:
    return collab_q.notifications_for(s, actor, unread_only=unread_only)


# --- activity -----------------------------------------------------------------------------------
@router.get("/activity/entity")
def entity_activity(
    entity_type: str, entity_id: uuid.UUID, actor: CurrentActor, s: ReadDB
) -> list[dict[str, Any]]:
    return activity_q.entity_activity(s, actor, entity_type, entity_id)


@router.get("/activity")
def global_activity(
    actor: CurrentActor,
    s: ReadDB,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    op: str | None = None,
    origin: str | None = None,
    workspace_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    return activity_q.global_activity(
        s,
        actor,
        actor_id=actor_id,
        entity_type=entity_type,
        op=op,
        origin=origin,
        workspace_id=workspace_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# --- automations -------------------------------------------------------------------------------
@router.get("/automations/catalog")
def automations_catalog(actor: CurrentActor) -> dict[str, Any]:
    return automation_catalog()


@router.get("/automations/rules")
def automation_rules(
    workspace_id: uuid.UUID, actor: CurrentActor, s: ReadDB, search: str | None = None
) -> list[dict[str, Any]]:
    return automations_q.list_rules(s, actor, workspace_id, search)


@router.get("/automations/rules/{rule_id}/preview")
def automation_preview(rule_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return automations_q.rule_preview(s, actor, rule_id)


@router.get("/automations/runs")
def automation_runs(
    workspace_id: uuid.UUID,
    actor: CurrentActor,
    s: ReadDB,
    rule_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    return automations_q.list_runs(
        s, actor, workspace_id, rule_id=rule_id, item_id=item_id, status=status, limit=limit, offset=offset
    )
