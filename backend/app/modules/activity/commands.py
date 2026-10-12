"""Undo, built on the audit trail.

Reverting is itself a command (origin=undo), so it is audited and can be
reverted again. A field is only written back if it still holds the value the
original change produced; otherwise a later edit would be clobbered, so that
field is skipped and reported.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapper

from app.core.db import Base
from app.core.errors import NotFound, ValidationFailed
from app.platform.audit.models import Audited, AuditEntry
from app.platform.commands import Command, CommandContext, handles
from app.platform.jsonvalue import to_json
from app.platform.permissions import P_AUDIT_REVERT

REVERTIBLE = {"item", "item_member", "task", "task_member", "client", "client_entity", "contact"}
NEVER_REVERT_FIELDS = {
    "id",
    "highlight_color",
    "highlight_rule_id",
    "version",
    "archive_source",
    "archive_ref",
}


def _model_for(entity_type: str) -> type[Any]:
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if issubclass(cls, Audited) and cls.__entity_type__ == entity_type:
            return cls
    raise ValidationFailed(f"cannot revert {entity_type}")


def _to_python(mapper: Mapper[Any], attr: str, value: Any) -> Any:
    if value is None:
        return None
    col = mapper.columns[attr]
    if isinstance(col.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(col.type, Date) and isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(col.type, PG_UUID) and isinstance(value, str):
        return uuid.UUID(value)
    return value


class RevertChanges(Command):
    """Revert audit entries selected by entry ids, a command id, or a batch."""

    command_name = "activity.revert"
    permission = P_AUDIT_REVERT

    entry_ids: list[int] = []
    command_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    fields: list[str] | None = None  # limit to these fields (single-cell undo)


@handles(RevertChanges)
def revert_changes(ctx: CommandContext, cmd: RevertChanges) -> dict[str, Any]:
    s = ctx.session
    q = select(AuditEntry).where(AuditEntry.reverted_by_command_id.is_(None))
    if cmd.entry_ids:
        q = q.where(AuditEntry.id.in_(cmd.entry_ids))
    elif cmd.command_id:
        q = q.where(AuditEntry.command_id == cmd.command_id)
    elif cmd.batch_id:
        q = q.where(AuditEntry.batch_id == cmd.batch_id)
    else:
        raise ValidationFailed("nothing selected to revert")
    entries = list(s.scalars(q.order_by(AuditEntry.id.desc())))  # newest first
    if not entries:
        raise NotFound("no revertible changes found")

    ws_ids = {e.workspace_id for e in entries}
    for wid in ws_ids:
        ctx.authorize(P_AUDIT_REVERT, wid)

    reverted, skipped = 0, []
    for e in entries:
        if e.entity_type not in REVERTIBLE:
            skipped.append({"entry": e.id, "reason": "not revertible"})
            continue
        model = _model_for(e.entity_type)
        mapper: Mapper[Any] = model.__mapper__
        obj = s.get(model, e.entity_id)
        if e.op == "create":
            if obj is None:
                continue
            if hasattr(obj, "deleted_at"):
                obj.deleted_at = ctx_now()
            else:
                s.delete(obj)
            reverted += 1
        elif e.op == "delete":
            if obj is not None:
                skipped.append({"entry": e.id, "reason": "record exists again"})
                continue
            values = {
                c["field"]: _to_python(mapper, c["field"], c["before"])
                for c in e.changes
                if not c["field"].startswith("data.")
            }
            data = {c["field"][5:]: c["before"] for c in e.changes if c["field"].startswith("data.")}
            if "data" in mapper.columns:
                values["data"] = data
            values["id"] = e.entity_id
            s.add(model(**values))
            reverted += 1
        else:
            if obj is None:
                skipped.append({"entry": e.id, "reason": "record no longer exists"})
                continue
            changed_any = False
            for c in e.changes:
                f = c["field"]
                if f in NEVER_REVERT_FIELDS or (cmd.fields and f not in cmd.fields):
                    continue
                if f.startswith("data."):
                    key = f[5:]
                    current = (obj.data or {}).get(key)  # type: ignore[attr-defined]
                    if to_json(current) != c["after"]:
                        skipped.append({"entry": e.id, "field": f, "reason": "changed since"})
                        continue
                    obj.set_data(key, c["before"])  # type: ignore[attr-defined]
                else:
                    current = getattr(obj, f)
                    if to_json(current) != c["after"]:
                        skipped.append({"entry": e.id, "field": f, "reason": "changed since"})
                        continue
                    setattr(obj, f, _to_python(mapper, f, c["before"]))
                changed_any = True
            if changed_any:
                reverted += 1
        e.reverted_by_command_id = ctx.command_id
    if reverted == 0:
        raise ValidationFailed(
            "nothing could be reverted", code="nothing_reverted", details={"skipped": skipped}
        )
    return {"reverted": reverted, "skipped": skipped}


def ctx_now() -> datetime:
    from app.core.time import utcnow

    return utcnow()
