import re
import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import NotFound, ValidationFailed
from app.core.time import business_today, utcnow
from app.modules.items.models import Item, ItemMember
from app.modules.items.service import _MISSING, ItemWriter, add_years, load_item, next_fiscal_year
from app.modules.tasks.models import Task
from app.modules.workspaces.models import Board, FiscalYear, Workspace
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import (
    P_ITEMS_ARCHIVE,
    P_ITEMS_CREATE,
    P_ITEMS_DELETE,
    P_ITEMS_ROLLOVER,
    P_ITEMS_UPDATE,
)

MAX_BULK = 2000


def _workspace(ctx: CommandContext, workspace_id: uuid.UUID) -> Workspace:
    ws = ctx.session.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("workspace not found")
    return ws


def _items_in_one_workspace(ctx: CommandContext, item_ids: list[uuid.UUID], permission: str) -> list[Item]:
    if not item_ids:
        raise ValidationFailed("no items selected", code="empty_selection")
    if len(item_ids) > MAX_BULK:
        raise ValidationFailed(f"at most {MAX_BULK} items at once", code="too_many")
    items = list(
        ctx.session.scalars(
            select(Item).where(Item.id.in_(item_ids), Item.deleted_at.is_(None)).order_by(Item.id)
        )
    )
    if not items:
        raise NotFound("items not found")
    ws_ids = {i.workspace_id for i in items}
    if len(ws_ids) != 1:
        raise ValidationFailed("items must belong to one workspace", code="mixed_workspaces")
    ctx.authorize(permission, ws_ids.pop())
    return items


# --- create / edit --------------------------------------------------------------
class CreateItem(Command):
    command_name = "items.create"
    permission = P_ITEMS_CREATE

    board_id: uuid.UUID
    values: dict[str, Any]


@handles(CreateItem)
def create_item(ctx: CommandContext, cmd: CreateItem) -> dict[str, str]:
    board = ctx.session.get(Board, cmd.board_id)
    if board is None or board.deleted_at is not None:
        raise NotFound("board not found")
    ctx.authorize(P_ITEMS_CREATE, board.workspace_id)
    writer = ItemWriter(ctx, _workspace(ctx, board.workspace_id))
    item = writer.create(board, cmd.values)
    ctx.session.flush()
    return {"id": str(item.id)}


class UpdateItemField(Command):
    """Single cell edit. ``expected`` is the value the user saw; if the stored
    value differs, the edit is rejected instead of silently overwriting."""

    command_name = "items.update_field"
    permission = P_ITEMS_UPDATE

    item_id: uuid.UUID
    field: str
    value: Any = None
    expected: Any = None
    check_expected: bool = False


@handles(UpdateItemField)
def update_item_field(ctx: CommandContext, cmd: UpdateItemField) -> dict[str, Any]:
    item = load_item(ctx, cmd.item_id)
    ctx.authorize(P_ITEMS_UPDATE, item.workspace_id)
    writer = ItemWriter(ctx, _workspace(ctx, item.workspace_id))
    v = writer.set(item, cmd.field, cmd.value, expected=cmd.expected if cmd.check_expected else _MISSING)
    item.version += 1
    return {"value": v, "version": item.version}


class UpdateItemFields(Command):
    """Several fields at once (detail form). Validates all before applying."""

    command_name = "items.update_fields"
    permission = P_ITEMS_UPDATE

    item_id: uuid.UUID
    values: dict[str, Any]


@handles(UpdateItemFields)
def update_item_fields(ctx: CommandContext, cmd: UpdateItemFields) -> dict[str, Any]:
    item = load_item(ctx, cmd.item_id)
    ctx.authorize(P_ITEMS_UPDATE, item.workspace_id)
    writer = ItemWriter(ctx, _workspace(ctx, item.workspace_id))
    errors: dict[str, str] = {}
    out: dict[str, Any] = {}
    for key, value in sorted(cmd.values.items(), key=lambda kv: {"client": 0, "entity": 1}.get(kv[0], 9)):
        try:
            out[key] = writer.set(item, key, value)
        except ValidationFailed as e:
            errors[key] = e.message
    if errors:
        raise ValidationFailed("invalid values", code="invalid_item", details={"fields": errors})
    item.version += 1
    return out


class SetPeriodValue(Command):
    """Edit one cell of a period grid without touching the other periods, so
    two people ticking different months never overwrite each other."""

    command_name = "items.set_period"
    permission = P_ITEMS_UPDATE

    item_id: uuid.UUID
    field: str
    period: int = Field(ge=1, le=53)
    value: str | None


@handles(SetPeriodValue)
def set_period_value(ctx: CommandContext, cmd: SetPeriodValue) -> None:
    item = load_item(ctx, cmd.item_id)
    ctx.authorize(P_ITEMS_UPDATE, item.workspace_id)
    writer = ItemWriter(ctx, _workspace(ctx, item.workspace_id))
    col = writer.column(cmd.field)
    if col.type != "period_grid":
        raise ValidationFailed("not a period field")
    grid = dict((item.data or {}).get(cmd.field) or {})
    if cmd.value:
        grid[str(cmd.period)] = cmd.value
    else:
        grid.pop(str(cmd.period), None)
    writer.set(item, cmd.field, grid)


class BulkUpdateField(Command):
    command_name = "items.bulk_update_field"
    permission = P_ITEMS_UPDATE

    item_ids: list[uuid.UUID]
    field: str
    value: Any = None
    # For multi-value fields and team roles: replace, add to, or remove from.
    mode: Literal["set", "add", "remove"] = "set"


@handles(BulkUpdateField)
def bulk_update_field(ctx: CommandContext, cmd: BulkUpdateField) -> dict[str, Any]:
    items = _items_in_one_workspace(ctx, cmd.item_ids, P_ITEMS_UPDATE)
    writer = ItemWriter(ctx, _workspace(ctx, items[0].workspace_id))
    col = writer.column(cmd.field)
    is_multi = col.kind == "multi"
    if cmd.mode != "set" and not is_multi:
        raise ValidationFailed("add/remove only apply to multi-value fields")
    failed: dict[str, str] = {}
    updated = 0
    for it in items:
        try:
            value = cmd.value
            if is_multi and cmd.mode != "set":
                current = writer.current(it, cmd.field) or []
                delta = cmd.value if isinstance(cmd.value, list) else [cmd.value]
                value = (
                    list(dict.fromkeys([*current, *delta]))
                    if cmd.mode == "add"
                    else [v for v in current if v not in set(delta)]
                )
            writer.set(it, cmd.field, value)
            it.version += 1
            updated += 1
        except ValidationFailed as e:
            failed[str(it.id)] = e.message
    if updated == 0 and failed:
        raise ValidationFailed("no item could be updated", details={"failed": failed})
    return {"updated": updated, "failed": failed}


class MoveItems(Command):
    command_name = "items.move"
    permission = P_ITEMS_UPDATE

    item_ids: list[uuid.UUID]
    board_id: uuid.UUID


@handles(MoveItems)
def move_items(ctx: CommandContext, cmd: MoveItems) -> dict[str, int]:
    items = _items_in_one_workspace(ctx, cmd.item_ids, P_ITEMS_UPDATE)
    writer = ItemWriter(ctx, _workspace(ctx, items[0].workspace_id))
    board = writer.board(cmd.board_id)
    if board.deleted_at is not None:
        raise ValidationFailed("target board is archived")
    allowed = {st.key for st in writer.allowed_statuses(board)}
    for it in items:
        it.board_id = board.id
        if it.status not in allowed:
            it.status = writer.default_status(board)
    return {"moved": len(items)}


# --- archive / restore / delete -------------------------------------------------------
class ArchiveItems(Command):
    command_name = "items.archive"
    permission = P_ITEMS_ARCHIVE

    item_ids: list[uuid.UUID]
    source: Literal["manual", "automation"] = "manual"
    ref: str | None = None


@handles(ArchiveItems)
def archive_items(ctx: CommandContext, cmd: ArchiveItems) -> dict[str, int]:
    items = _items_in_one_workspace(ctx, cmd.item_ids, P_ITEMS_ARCHIVE)
    now = utcnow()
    n = 0
    for it in items:
        if it.is_archived:
            continue
        it.is_archived = True
        it.archive_source = cmd.source
        it.archive_ref = cmd.ref
        it.archived_at = now
        n += 1
    return {"archived": n}


class RestoreItems(Command):
    """Restore archived items. Items whose board is archived need a target
    board in ``target_boards`` (item id -> board id); otherwise the whole
    request is rejected so nothing is half-restored."""

    command_name = "items.restore"
    permission = P_ITEMS_ARCHIVE

    item_ids: list[uuid.UUID]
    target_boards: dict[uuid.UUID, uuid.UUID] = {}


@handles(RestoreItems)
def restore_items(ctx: CommandContext, cmd: RestoreItems) -> dict[str, Any]:
    items = _items_in_one_workspace(ctx, cmd.item_ids, P_ITEMS_ARCHIVE)
    writer = ItemWriter(ctx, _workspace(ctx, items[0].workspace_id))
    needs_board = [
        str(it.id)
        for it in items
        if writer.board(it.board_id).deleted_at is not None and it.id not in cmd.target_boards
    ]
    if needs_board:
        raise ValidationFailed(
            "some items belong to an archived board; choose a board for them",
            code="needs_target_board",
            details={"item_ids": needs_board},
        )
    for it in items:
        target = cmd.target_boards.get(it.id)
        if target is not None:
            b = writer.board(target)
            if b.deleted_at is not None:
                raise ValidationFailed("target board is archived")
            it.board_id = b.id
        it.is_archived = False
        it.archive_source = None
        it.archive_ref = None
        it.archived_at = None
    return {"restored": len(items)}


class DeleteItems(Command):
    """Moves items (and their tasks) to the trash. Purging is a separate,
    admin-only operation; nothing is hard-deleted from the UI."""

    command_name = "items.delete"
    permission = P_ITEMS_DELETE

    item_ids: list[uuid.UUID]


@handles(DeleteItems)
def delete_items(ctx: CommandContext, cmd: DeleteItems) -> dict[str, int]:
    items = _items_in_one_workspace(ctx, cmd.item_ids, P_ITEMS_DELETE)
    now = utcnow()
    tasks = 0
    for it in items:
        for t in ctx.session.scalars(select(Task).where(Task.item_id == it.id, Task.deleted_at.is_(None))):
            t.deleted_at = now
            tasks += 1
        it.deleted_at = now
    return {"deleted": len(items), "tasks": tasks}


class RestoreDeletedItems(Command):
    command_name = "items.restore_deleted"
    permission = P_ITEMS_DELETE

    item_ids: list[uuid.UUID]


@handles(RestoreDeletedItems)
def restore_deleted_items(ctx: CommandContext, cmd: RestoreDeletedItems) -> dict[str, int]:
    items = list(
        ctx.session.scalars(select(Item).where(Item.id.in_(cmd.item_ids), Item.deleted_at.is_not(None)))
    )
    if not items:
        raise NotFound("no deleted items found")
    for ws_id in {i.workspace_id for i in items}:
        ctx.authorize(P_ITEMS_DELETE, ws_id)
    for it in items:
        deleted_at = it.deleted_at
        it.deleted_at = None
        for t in ctx.session.scalars(
            select(Task).where(Task.item_id == it.id, Task.deleted_at == deleted_at)
        ):
            t.deleted_at = None
    return {"restored": len(items)}


# --- rollover ------------------------------------------------------------------------------
class FieldAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["carry", "clear", "set", "add_year"]
    value: Any = None


class RolloverItems(Command):
    """Copy items into a new period (next FY board, or the same board).

    Per field: carry, clear, set to a value, or add one year (dates, fiscal
    year). Unspecified fields use the field's configured rollover default.
    """

    command_name = "items.rollover"
    permission = P_ITEMS_ROLLOVER

    item_ids: list[uuid.UUID]
    target_board_id: uuid.UUID | None = None  # None: workspace default rule
    field_actions: dict[str, FieldAction] = {}
    name_suffix: str | None = None
    archive_source_items: bool = False


_SUFFIX_RE = re.compile(r"\s*(\(Roll Over\)|\(\d+\)|FY\s?\d{2,4}|\d{4}\s?-\s?\d{4}|\d{4})\s*$", re.IGNORECASE)


def _strip_suffixes(name: str, extra: list[str]) -> str:
    prev = None
    while prev != name:
        prev = name
        name = _SUFFIX_RE.sub("", name).rstrip(" -\u2013")
        for e in extra:
            if e and name.lower().endswith(e.lower()):
                name = name[: -len(e)].rstrip(" -\u2013")
    return name.strip()


def default_rollover_target(ctx: CommandContext, ws: Workspace, board: Board) -> Board:
    rule = (ws.settings or {}).get("rollover", {}).get("default_target", "same")
    if rule == "next_period" and board.period_fiscal_year_id:
        nxt = next_fiscal_year(ctx.session, board.period_fiscal_year_id)
        if nxt is not None:
            target = ctx.session.scalar(
                select(Board).where(
                    Board.workspace_id == ws.id,
                    Board.period_fiscal_year_id == nxt.id,
                    Board.deleted_at.is_(None),
                )
            )
            if target is not None:
                return target
    return board


@handles(RolloverItems)
def rollover_items(ctx: CommandContext, cmd: RolloverItems) -> dict[str, Any]:
    items = _items_in_one_workspace(ctx, cmd.item_ids, P_ITEMS_ROLLOVER)
    ws = _workspace(ctx, items[0].workspace_id)
    ctx.authorize(P_ITEMS_CREATE, ws.id)
    writer = ItemWriter(ctx, ws)
    created: list[str] = []
    failed: dict[str, str] = {}
    fixed = {"name", "board", "client", "created_at", "updated_at", "archive_source"}

    for src in items:
        src_board = writer.board(src.board_id)
        target = (
            writer.board(cmd.target_board_id)
            if cmd.target_board_id
            else default_rollover_target(ctx, ws, src_board)
        )
        if target.deleted_at is not None:
            failed[str(src.id)] = "target board is archived"
            continue
        values: dict[str, Any] = {"client": str(src.client_id) if src.client_id else None}
        for key, col in writer.columns.items():
            if key in fixed or not col.editable:
                continue
            act = cmd.field_actions.get(key) or FieldAction(action=col.rollover)  # type: ignore[arg-type]
            current = writer.current(src, key)
            if act.action == "clear":
                continue
            if act.action == "set":
                values[key] = act.value
            elif act.action == "add_year":
                if key == "fiscal_year":
                    nxt = next_fiscal_year(ctx.session, src.fiscal_year_id)
                    values[key] = str(nxt.id) if nxt else current
                else:
                    values[key] = add_years(current, col.type)
            else:
                values[key] = current
        if target.period_fiscal_year_id and "fiscal_year" not in cmd.field_actions:
            values["fiscal_year"] = str(target.period_fiscal_year_id)
        values = {k: v for k, v in values.items() if v not in (None, [], {})}

        # Name: strip old period markers, add the new one.
        fy_label = None
        if values.get("fiscal_year"):
            fy = ctx.session.get(FiscalYear, uuid.UUID(values["fiscal_year"]))
            fy_label = fy.label if fy else None
        # Board names are only part of the period marker when the board changes.
        base = _strip_suffixes(src.name, [src_board.name, target.name] if target.id != src_board.id else [])
        if cmd.name_suffix:
            suffix = cmd.name_suffix
        elif target.id != src_board.id:
            suffix = target.name
        elif fy_label and src.fiscal_year_id and str(src.fiscal_year_id) != values.get("fiscal_year"):
            suffix = fy_label
        else:
            suffix = "(Roll Over)"
        values["name"] = f"{base} {suffix}".strip()

        try:
            with ctx.savepoint():
                new = writer.create(target, values)
                new.rolled_from_id = src.id
                ctx.session.flush()
            created.append(str(new.id))
        except ValidationFailed as e:
            failed[str(src.id)] = e.message
            continue
        if cmd.archive_source_items and not src.is_archived:
            src.is_archived = True
            src.archive_source = "rollover"
            src.archive_ref = str(new.id)
            src.archived_at = utcnow()
    if not created and failed:
        raise ValidationFailed("nothing was rolled over", details={"failed": failed})
    return {"created": created, "failed": failed}


# --- team convenience ----------------------------------------------------------------------
class AddItemMember(Command):
    command_name = "items.add_member"
    permission = P_ITEMS_UPDATE

    item_id: uuid.UUID
    user_id: uuid.UUID
    role_key: str
    assigned_date: date | None = None


@handles(AddItemMember)
def add_item_member(ctx: CommandContext, cmd: AddItemMember) -> None:
    item = load_item(ctx, cmd.item_id)
    ctx.authorize(P_ITEMS_UPDATE, item.workspace_id)
    writer = ItemWriter(ctx, _workspace(ctx, item.workspace_id))
    current = writer.current(item, f"role.{cmd.role_key}") or []
    if str(cmd.user_id) in current:
        return
    writer.set(item, f"role.{cmd.role_key}", [*current, str(cmd.user_id)])
    if cmd.assigned_date:
        for m in writer.members(item, cmd.role_key):
            if m.user_id == cmd.user_id:
                m.assigned_date = cmd.assigned_date


class UpdateMemberDate(Command):
    command_name = "items.update_member_date"
    permission = P_ITEMS_UPDATE

    member_id: uuid.UUID
    assigned_date: date | None


@handles(UpdateMemberDate)
def update_member_date(ctx: CommandContext, cmd: UpdateMemberDate) -> None:
    m = ctx.session.get(ItemMember, cmd.member_id)
    if m is None:
        raise NotFound("member not found")
    item = load_item(ctx, m.item_id)
    ctx.authorize(P_ITEMS_UPDATE, item.workspace_id)
    m.assigned_date = cmd.assigned_date or business_today()
