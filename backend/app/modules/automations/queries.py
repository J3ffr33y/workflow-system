import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.automations.engine import preview_rule
from app.modules.automations.models import AutomationRule, AutomationRun
from app.modules.items.models import Item
from app.modules.workspaces.queries import require_workspace
from app.platform.audit.models import AuditEntry
from app.platform.permissions import P_AUTOMATIONS_MANAGE, P_ITEMS_READ, Actor


def rule_dict(r: AutomationRule) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "workspace_id": str(r.workspace_id),
        "name": r.name,
        "description": r.description,
        "enabled": r.enabled,
        "trigger": r.trigger,
        "conditions": r.conditions,
        "actions": r.actions,
        "board_ids": r.board_ids,
        "run_count": r.run_count,
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
    }


def list_rules(
    s: Session, actor: Actor, workspace_id: uuid.UUID, search: str | None = None
) -> list[dict[str, Any]]:
    require_workspace(s, actor, workspace_id, P_ITEMS_READ)
    q = select(AutomationRule).where(
        AutomationRule.workspace_id == workspace_id, AutomationRule.deleted_at.is_(None)
    )
    if search:
        q = q.where(AutomationRule.name.ilike(f"%{search}%"))
    return [rule_dict(r) for r in s.scalars(q.order_by(AutomationRule.name))]


def rule_preview(s: Session, actor: Actor, rule_id: uuid.UUID) -> list[dict[str, Any]]:
    r = s.get(AutomationRule, rule_id)
    if r is None or r.deleted_at is not None:
        raise NotFound("rule not found")
    require_workspace(s, actor, r.workspace_id, P_AUTOMATIONS_MANAGE)
    return preview_rule(s, r)


def list_runs(
    s: Session,
    actor: Actor,
    workspace_id: uuid.UUID,
    *,
    rule_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    require_workspace(s, actor, workspace_id, P_ITEMS_READ)
    q = (
        select(AutomationRun, AutomationRule.name, Item.name)
        .join(AutomationRule, AutomationRule.id == AutomationRun.rule_id)
        .outerjoin(Item, Item.id == AutomationRun.item_id)
        .where(AutomationRun.workspace_id == workspace_id)
    )
    if rule_id:
        q = q.where(AutomationRun.rule_id == rule_id)
    if item_id:
        q = q.where(AutomationRun.item_id == item_id)
    if status:
        q = q.where(AutomationRun.status == status)
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = s.execute(q.order_by(AutomationRun.id.desc()).offset(offset).limit(min(limit, 500))).all()
    cmd_ids = [r[0].command_id for r in rows if r[0].command_id]
    changes: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for e in s.scalars(select(AuditEntry).where(AuditEntry.command_id.in_(cmd_ids))):
        changes.setdefault(e.command_id, []).extend(
            {"entity_type": e.entity_type, **c} for c in (e.changes or [])
        )
    return {
        "total": total,
        "rows": [
            {
                "id": run.id,
                "rule_id": str(run.rule_id),
                "rule_name": rule_name,
                "item_id": str(run.item_id) if run.item_id else None,
                "item_name": item_name,
                "trigger_source": run.trigger_source,
                "status": run.status,
                "detail": run.detail,
                "error": run.error,
                "changes": changes.get(run.command_id, []) if run.command_id else [],
                "command_id": str(run.command_id) if run.command_id else None,
                "created_at": run.created_at.isoformat(),
            }
            for run, rule_name, item_name in rows
        ],
    }
