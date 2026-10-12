import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, PermissionDenied
from app.core.time import business_today
from app.modules.items.models import Item
from app.modules.tasks.models import Task, TaskMember
from app.modules.workspaces.models import Board, Status
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


# Closed work never shows on "My work"; anything else (including statuses
# whose category is unknown) does, so a misconfigured status can't hide a task.
_CLOSED = ("done", "cancelled")


def _bucket(due: date | None, today: date) -> str:
    if due is None:
        return "no_date"
    if due < today:
        return "overdue"
    # The business week ends on Sunday; "this week" never looks past it.
    if due <= today + timedelta(days=6 - today.weekday()):
        return "this_week"
    return "later"


def my_tasks(s: Session, actor: Actor, *, limit: int = 500) -> list[dict[str, Any]]:
    """Open tasks the signed-in user is a member of, with the item they belong to."""
    if actor.user_id is None:
        return []
    mine = select(TaskMember.task_id).where(TaskMember.user_id == actor.user_id)
    q = (
        select(Task, Item, Board.name)
        .join(Item, Item.id == Task.item_id)
        .join(Board, Board.id == Item.board_id)
        .where(
            Task.id.in_(mine),
            Task.deleted_at.is_(None),
            Item.deleted_at.is_(None),
            Item.is_archived.is_(False),
        )
        .order_by(Task.due_date.asc().nulls_last(), Task.created_at)
        .limit(limit)
    )
    ws_ids = actor.workspace_ids()
    if ws_ids is not None:
        q = q.where(Task.workspace_id.in_(ws_ids))
    rows = s.execute(q).all()
    statuses = {
        (st.workspace_id, st.key): st
        for st in s.scalars(
            select(Status).where(
                Status.scope == "task", Status.workspace_id.in_({t.workspace_id for t, _, _ in rows})
            )
        )
    }
    roles: dict[uuid.UUID, list[str]] = {}
    for m in s.scalars(
        select(TaskMember).where(
            TaskMember.user_id == actor.user_id, TaskMember.task_id.in_([t.id for t, _, _ in rows])
        )
    ):
        roles.setdefault(m.task_id, []).append(m.role_key)
    today = business_today()
    out = []
    for t, it, board_name in rows:
        st = statuses.get((t.workspace_id, t.status or ""))
        category = st.category if st else "todo"
        if category in _CLOSED:
            continue
        out.append(
            {
                "id": str(t.id),
                "title": t.title,
                "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
                "status": t.status,
                "status_label": st.label if st else (t.status or ""),
                "status_color": st.color if st else "gray",
                "status_category": category,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "bucket": _bucket(t.due_date, today),
                "my_roles": sorted(roles.get(t.id, [])),
                "workspace_id": str(t.workspace_id),
                "item_id": str(it.id),
                "item_name": it.name,
                "board_id": str(it.board_id),
                "board_name": board_name,
            }
        )
    return out
