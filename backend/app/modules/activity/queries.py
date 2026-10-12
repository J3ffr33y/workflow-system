import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import business_tz
from app.modules.clients.models import Client
from app.modules.items.models import Item
from app.platform.audit.models import AuditEntry
from app.platform.commands.models import CommandLog
from app.platform.permissions import P_AUDIT_VIEW_VALUES, Actor


def _entry(
    e: AuditEntry, show_values: bool, names: dict[uuid.UUID, str], command_names: dict[uuid.UUID, str]
) -> dict[str, Any]:
    changes = e.changes or []
    if not show_values:
        changes = [{"field": c["field"], "before": None, "after": None, "hidden": True} for c in changes]
    return {
        "id": e.id,
        "command_id": str(e.command_id),
        "command": command_names.get(e.command_id),
        "batch_id": str(e.batch_id) if e.batch_id else None,
        "origin": e.origin,
        "actor_id": str(e.actor_id) if e.actor_id else None,
        "actor": e.actor_display,
        "entity_type": e.entity_type,
        "entity_id": str(e.entity_id),
        "entity_name": names.get(e.entity_id) or (names.get(e.parent_id) if e.parent_id else None),
        "parent_type": e.parent_type,
        "parent_id": str(e.parent_id) if e.parent_id else None,
        "workspace_id": str(e.workspace_id) if e.workspace_id else None,
        "op": e.op,
        "changes": changes,
        "reverted": e.reverted_by_command_id is not None,
        "created_at": e.created_at.isoformat(),
    }


def _visible(actor: Actor) -> Any:
    ids = actor.workspace_ids()
    if ids is None:
        return True
    return or_(AuditEntry.workspace_id.is_(None), AuditEntry.workspace_id.in_(ids))


def _names(s: Session, entries: list[AuditEntry]) -> dict[uuid.UUID, str]:
    ids = {e.entity_id for e in entries} | {e.parent_id for e in entries if e.parent_id}
    out: dict[uuid.UUID, str] = {}
    for i, n in s.execute(select(Item.id, Item.name).where(Item.id.in_(ids))):
        out[i] = n
    for i, n in s.execute(select(Client.id, Client.name).where(Client.id.in_(ids))):
        out[i] = n
    return out


def _command_names(s: Session, entries: list[AuditEntry]) -> dict[uuid.UUID, str]:
    ids = {e.command_id for e in entries}
    return dict(s.execute(select(CommandLog.id, CommandLog.name).where(CommandLog.id.in_(ids))).all())


def entity_activity(
    s: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID, *, limit: int = 200
) -> list[dict[str, Any]]:
    entries = list(
        s.scalars(
            select(AuditEntry)
            .where(
                or_(
                    and_(AuditEntry.entity_type == entity_type, AuditEntry.entity_id == entity_id),
                    and_(AuditEntry.parent_type == entity_type, AuditEntry.parent_id == entity_id),
                ),
                _visible(actor),
            )
            .order_by(AuditEntry.id.desc())
            .limit(limit)
        )
    )
    # Values on a record's own history are visible to anyone who can see the record.
    return [_entry(e, True, _names(s, entries), _command_names(s, entries)) for e in entries]


def global_activity(
    s: Session,
    actor: Actor,
    *,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    op: str | None = None,
    workspace_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    origin: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    q = select(AuditEntry).where(_visible(actor))
    if actor_id:
        q = q.where(AuditEntry.actor_id == actor_id)
    if entity_type:
        q = q.where(AuditEntry.entity_type == entity_type)
    if op:
        q = q.where(AuditEntry.op == op)
    if origin:
        q = q.where(AuditEntry.origin == origin)
    if workspace_id:
        q = q.where(AuditEntry.workspace_id == workspace_id)
    tz = business_tz()
    if date_from:
        q = q.where(AuditEntry.created_at >= datetime.combine(date_from, time.min, tz))
    if date_to:
        q = q.where(AuditEntry.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tz))
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    entries = list(s.scalars(q.order_by(AuditEntry.id.desc()).offset(offset).limit(min(limit, 500))))
    names = _names(s, entries)
    cmds = _command_names(s, entries)
    rows = [_entry(e, actor.can(P_AUDIT_VIEW_VALUES, e.workspace_id), names, cmds) for e in entries]
    return {"total": total, "rows": rows}
