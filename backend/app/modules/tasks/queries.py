import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, PermissionDenied
from app.modules.items.models import Item
from app.modules.tasks.models import Task, TaskMember
from app.platform.permissions import P_ITEMS_READ, Actor


def task_dict(t: Task, members: dict[uuid.UUID, dict[str, list[str]]]) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "item_id": str(t.item_id),
        "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "fiscal_year_id": str(t.fiscal_year_id) if t.fiscal_year_id else None,
        "period": t.period,
        "position": t.position,
        "members": members.get(t.id, {}),
        "created_at": t.created_at.isoformat(),
    }


def tasks_for_item(s: Session, actor: Actor, item_id: uuid.UUID) -> list[dict[str, Any]]:
    it = s.get(Item, item_id)
    if it is None or it.deleted_at is not None:
        raise NotFound("item not found")
    if not actor.can(P_ITEMS_READ, it.workspace_id):
        raise PermissionDenied("no access")
    tasks = list(
        s.scalars(
            select(Task)
            .where(Task.item_id == item_id, Task.deleted_at.is_(None))
            .order_by(Task.position, Task.created_at)
        )
    )
    members: dict[uuid.UUID, dict[str, list[str]]] = {}
    for m in s.scalars(select(TaskMember).where(TaskMember.task_id.in_([t.id for t in tasks]))):
        members.setdefault(m.task_id, {}).setdefault(m.role_key, []).append(str(m.user_id))
    return [task_dict(t, members) for t in tasks]
