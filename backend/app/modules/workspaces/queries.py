import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, PermissionDenied
from app.modules.workspaces.models import (
    Board,
    FieldDefinition,
    FiscalYear,
    LookupList,
    LookupValue,
    MemberRole,
    Status,
    Workspace,
)
from app.modules.workspaces.schema import item_columns
from app.platform.permissions import P_ITEMS_READ, Actor


def visible_workspaces(s: Session, actor: Actor) -> list[Workspace]:
    ids = actor.workspace_ids()
    q = select(Workspace).where(Workspace.is_active.is_(True)).order_by(Workspace.position)
    if ids is not None:
        q = q.where(Workspace.id.in_(ids))
    return list(s.scalars(q))


def require_workspace(
    s: Session, actor: Actor, workspace_id: uuid.UUID, permission: str = P_ITEMS_READ
) -> Workspace:
    ws = s.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("workspace not found")
    if not actor.can(permission, ws.id):
        raise PermissionDenied("no access to this workspace")
    return ws


def board_dict(b: Board) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "workspace_id": str(b.workspace_id),
        "name": b.name,
        "description": b.description,
        "icon": b.icon,
        "position": b.position,
        "period_fiscal_year_id": str(b.period_fiscal_year_id) if b.period_fiscal_year_id else None,
        "settings": b.settings or {},
        "archived": b.deleted_at is not None,
    }


def status_dict(st: Status) -> dict[str, Any]:
    return {
        "key": st.key,
        "label": st.label,
        "color": st.color,
        "category": st.category,
        "position": st.position,
        "is_default": st.is_default,
        "is_archived": st.is_archived,
        "scope": st.scope,
    }


def fiscal_years(s: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": str(f.id),
            "label": f.label,
            "start_date": f.start_date.isoformat(),
            "end_date": f.end_date.isoformat(),
        }
        for f in s.scalars(select(FiscalYear).order_by(FiscalYear.start_date))
    ]


def lookups(s: Session) -> list[dict[str, Any]]:
    lists = list(s.scalars(select(LookupList).order_by(LookupList.label)))
    values: dict[uuid.UUID, list[LookupValue]] = {}
    for v in s.scalars(select(LookupValue).order_by(LookupValue.position, LookupValue.label)):
        values.setdefault(v.list_id, []).append(v)
    return [
        {
            "id": str(lst.id),
            "key": lst.key,
            "label": lst.label,
            "is_hierarchical": lst.is_hierarchical,
            "values": [
                {
                    "id": str(v.id),
                    "label": v.label,
                    "parent_id": str(v.parent_id) if v.parent_id else None,
                    "aliases": v.aliases or [],
                    "is_active": v.is_active,
                }
                for v in values.get(lst.id, [])
            ],
        }
        for lst in lists
    ]


def workspace_schema(s: Session, actor: Actor, workspace_id: uuid.UUID) -> dict[str, Any]:
    """Everything the UI needs to render boards of this workspace."""
    ws = require_workspace(s, actor, workspace_id)
    boards = list(
        s.scalars(select(Board).where(Board.workspace_id == ws.id).order_by(Board.position, Board.name))
    )
    statuses = list(s.scalars(select(Status).where(Status.workspace_id == ws.id).order_by(Status.position)))
    roles = list(
        s.scalars(select(MemberRole).where(MemberRole.workspace_id == ws.id).order_by(MemberRole.position))
    )
    fields = list(
        s.scalars(
            select(FieldDefinition)
            .where(FieldDefinition.workspace_id == ws.id)
            .order_by(FieldDefinition.position)
        )
    )
    return {
        "workspace": {
            "id": str(ws.id),
            "key": ws.key,
            "name": ws.name,
            "item_label": ws.item_label,
            "settings": ws.settings or {},
        },
        "permissions": sorted(actor.permissions_in(ws.id)),
        "boards": [board_dict(b) for b in boards],
        "columns": [c.to_dict() for c in item_columns(s, ws)],
        "statuses": [status_dict(st) for st in statuses if st.scope == "item"],
        "task_statuses": [status_dict(st) for st in statuses if st.scope == "task"],
        "roles": [
            {"key": r.key, "label": r.label, "allow_multiple": r.allow_multiple, "is_archived": r.is_archived}
            for r in roles
        ],
        "field_definitions": [
            {
                "id": str(f.id),
                "entity_kind": f.entity_kind,
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "config": f.config,
                "group": f.group,
                "description": f.description,
                "is_required": f.is_required,
                "rollover": f.rollover,
                "track_changes": f.track_changes,
                "is_archived": f.is_archived,
                "position": f.position,
            }
            for f in fields
        ],
        "fiscal_years": fiscal_years(s),
        "lookups": lookups(s),
    }
