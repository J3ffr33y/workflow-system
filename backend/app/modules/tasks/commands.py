import uuid
from datetime import date
from typing import Any

from pydantic import Field
from sqlalchemy import func, select

from app.core.errors import NotFound, ValidationFailed
from app.core.time import business_today, utcnow
from app.modules.items.models import Item
from app.modules.tasks.models import Task, TaskMember
from app.modules.workspaces.models import Status
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_TASKS_WRITE

UNSET: Any = "__unset__"


def _item(ctx: CommandContext, item_id: uuid.UUID) -> Item:
    it = ctx.session.get(Item, item_id)
    if it is None or it.deleted_at is not None:
        raise NotFound("item not found")
    ctx.authorize(P_TASKS_WRITE, it.workspace_id)
    return it


def _task(ctx: CommandContext, task_id: uuid.UUID) -> Task:
    t = ctx.session.get(Task, task_id)
    if t is None or t.deleted_at is not None:
        raise NotFound("task not found")
    ctx.authorize(P_TASKS_WRITE, t.workspace_id)
    return t


def _task_statuses(ctx: CommandContext, workspace_id: uuid.UUID) -> list[Status]:
    return list(
        ctx.session.scalars(
            select(Status)
            .where(Status.workspace_id == workspace_id, Status.scope == "task", Status.is_archived.is_(False))
            .order_by(Status.position)
        )
    )


def _check_status(ctx: CommandContext, workspace_id: uuid.UUID, status: str | None) -> str | None:
    statuses = _task_statuses(ctx, workspace_id)
    if status is None:
        defaults = [st.key for st in statuses if st.is_default]
        return defaults[0] if defaults else (statuses[0].key if statuses else None)
    if status not in {st.key for st in statuses}:
        raise ValidationFailed(f"unknown task status '{status}'", code="bad_status")
    return status


def _set_members(ctx: CommandContext, task: Task, role_key: str, user_ids: list[uuid.UUID]) -> None:
    existing = {
        m.user_id: m
        for m in ctx.session.scalars(
            select(TaskMember).where(TaskMember.task_id == task.id, TaskMember.role_key == role_key)
        )
    }
    for uid, m in existing.items():
        if uid not in user_ids:
            ctx.session.delete(m)
    for uid in user_ids:
        if uid not in existing:
            ctx.session.add(
                TaskMember(task_id=task.id, user_id=uid, role_key=role_key, assigned_date=business_today())
            )


class CreateTask(Command):
    command_name = "tasks.create"
    permission = P_TASKS_WRITE

    item_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    status: str | None = None
    priority: str | None = None
    due_date: date | None = None
    parent_task_id: uuid.UUID | None = None
    fiscal_year_id: uuid.UUID | None = None
    period: str | None = None
    members: dict[str, list[uuid.UUID]] = {}


def create_task_for(ctx: CommandContext, item: Item, cmd: CreateTask) -> Task:
    if cmd.parent_task_id:
        parent = _task(ctx, cmd.parent_task_id)
        if parent.item_id != item.id:
            raise ValidationFailed("parent task belongs to another item")
    pos = (
        ctx.session.scalar(select(func.coalesce(func.max(Task.position), 0)).where(Task.item_id == item.id))
        or 0
    )
    t = Task(
        workspace_id=item.workspace_id,
        item_id=item.id,
        parent_task_id=cmd.parent_task_id,
        title=cmd.title.strip(),
        status=_check_status(ctx, item.workspace_id, cmd.status),
        priority=cmd.priority,
        due_date=cmd.due_date,
        fiscal_year_id=cmd.fiscal_year_id or item.fiscal_year_id,
        period=cmd.period,
        position=pos + 1,
    )
    ctx.session.add(t)
    ctx.session.flush()
    for role, users in cmd.members.items():
        _set_members(ctx, t, role, users)
    return t


@handles(CreateTask)
def create_task(ctx: CommandContext, cmd: CreateTask) -> dict[str, str]:
    item = _item(ctx, cmd.item_id)
    return {"id": str(create_task_for(ctx, item, cmd).id)}


class CreateTasksForItems(Command):
    """The same task on several selected items (bulk action on a board)."""

    command_name = "tasks.create_for_items"
    permission = P_TASKS_WRITE

    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    status: str | None = None
    due_date: date | None = None
    members: dict[str, list[uuid.UUID]] = {}


@handles(CreateTasksForItems)
def create_tasks_for_items(ctx: CommandContext, cmd: CreateTasksForItems) -> dict[str, int]:
    n = 0
    for iid in cmd.item_ids:
        item = _item(ctx, iid)
        create_task_for(
            ctx,
            item,
            CreateTask(
                item_id=iid, title=cmd.title, status=cmd.status, due_date=cmd.due_date, members=cmd.members
            ),
        )
        n += 1
    return {"created": n}


class UpdateTask(Command):
    command_name = "tasks.update"
    permission = P_TASKS_WRITE

    task_id: uuid.UUID
    title: str | None = None
    status: str | None = None
    priority: Any = UNSET
    due_date: Any = UNSET
    period: Any = UNSET
    position: int | None = None
    members: dict[str, list[uuid.UUID]] | None = None


@handles(UpdateTask)
def update_task(ctx: CommandContext, cmd: UpdateTask) -> None:
    t = _task(ctx, cmd.task_id)
    if cmd.title is not None:
        if not cmd.title.strip():
            raise ValidationFailed("title is required")
        t.title = cmd.title.strip()
    if cmd.status is not None:
        t.status = _check_status(ctx, t.workspace_id, cmd.status)
    if cmd.priority != UNSET:
        t.priority = cmd.priority
    if cmd.due_date != UNSET:
        t.due_date = date.fromisoformat(cmd.due_date) if isinstance(cmd.due_date, str) else cmd.due_date
    if cmd.period != UNSET:
        t.period = cmd.period
    if cmd.position is not None:
        t.position = cmd.position
    for role, users in (cmd.members or {}).items():
        _set_members(ctx, t, role, users)


class DeleteTask(Command):
    command_name = "tasks.delete"
    permission = P_TASKS_WRITE

    task_id: uuid.UUID
    include_subtasks: bool = True


@handles(DeleteTask)
def delete_task(ctx: CommandContext, cmd: DeleteTask) -> dict[str, int]:
    t = _task(ctx, cmd.task_id)
    now = utcnow()
    n = 0
    if cmd.include_subtasks:
        frontier = [t.id]
        while frontier:
            children = list(
                ctx.session.scalars(
                    select(Task).where(Task.parent_task_id.in_(frontier), Task.deleted_at.is_(None))
                )
            )
            for c in children:
                c.deleted_at = now
                n += 1
            frontier = [c.id for c in children]
    else:
        for c in ctx.session.scalars(
            select(Task).where(Task.parent_task_id == t.id, Task.deleted_at.is_(None))
        ):
            c.parent_task_id = t.parent_task_id
    t.deleted_at = now
    return {"deleted": n + 1}
