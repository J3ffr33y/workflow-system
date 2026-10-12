"""Commands that change the *shape* of a workspace: boards, fields, statuses,
roles, fiscal years and lookup lists."""

import re
import uuid
from datetime import date
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import func, select, update

from app.core.errors import NotFound, ValidationFailed
from app.core.time import utcnow
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
from app.modules.workspaces.schema import is_reserved_key
from app.platform.commands import Command, CommandContext, handles
from app.platform.fields.types import field_types
from app.platform.permissions import P_BOARDS_MANAGE, P_SCHEMA_MANAGE, P_SYSTEM_ADMIN

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
STATUS_CATEGORIES = {"todo", "active", "waiting", "done", "cancelled"}


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    if not s or not s[0].isalpha():
        s = f"f_{s}"
    return s[:60]


def _check_key(key: str) -> str:
    if not KEY_RE.match(key):
        raise ValidationFailed(f"invalid key '{key}': lowercase letters, digits and _", code="bad_key")
    return key


def _ws(ctx: CommandContext, workspace_id: uuid.UUID, permission: str) -> Workspace:
    ws = ctx.session.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("workspace not found")
    ctx.authorize(permission, ws.id)
    return ws


# --- workspaces -----------------------------------------------------------------
class CreateWorkspace(Command):
    command_name = "workspaces.create"
    permission = P_SYSTEM_ADMIN
    scoped = False

    key: str
    name: str
    item_label: str = "Project"
    settings: dict[str, Any] = {}


@handles(CreateWorkspace)
def create_workspace(ctx: CommandContext, cmd: CreateWorkspace) -> dict[str, str]:
    _check_key(cmd.key)
    if ctx.session.scalar(select(Workspace.id).where(Workspace.key == cmd.key)):
        raise ValidationFailed("workspace key already used")
    pos = ctx.session.scalar(select(func.coalesce(func.max(Workspace.position), 0))) or 0
    ws = Workspace(
        key=cmd.key, name=cmd.name, item_label=cmd.item_label, settings=cmd.settings, position=pos + 1
    )
    ctx.session.add(ws)
    ctx.session.flush()
    return {"id": str(ws.id)}


class UpdateWorkspace(Command):
    command_name = "workspaces.update"
    permission = P_SCHEMA_MANAGE

    workspace_id: uuid.UUID
    name: str | None = None
    item_label: str | None = None
    settings: dict[str, Any] | None = None  # merged shallowly


@handles(UpdateWorkspace)
def update_workspace(ctx: CommandContext, cmd: UpdateWorkspace) -> None:
    ws = _ws(ctx, cmd.workspace_id, P_SCHEMA_MANAGE)
    if cmd.name is not None:
        ws.name = cmd.name
    if cmd.item_label is not None:
        ws.item_label = cmd.item_label
    if cmd.settings is not None:
        ws.settings = {**(ws.settings or {}), **cmd.settings}


# --- boards -------------------------------------------------------------------------
class CreateBoard(Command):
    command_name = "boards.create"
    permission = P_BOARDS_MANAGE

    workspace_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    icon: str | None = None
    period_fiscal_year_id: uuid.UUID | None = None
    settings: dict[str, Any] = {}


@handles(CreateBoard)
def create_board(ctx: CommandContext, cmd: CreateBoard) -> dict[str, str]:
    ws = _ws(ctx, cmd.workspace_id, P_BOARDS_MANAGE)
    s = ctx.session
    if s.scalar(
        select(Board.id).where(
            Board.workspace_id == ws.id, Board.name == cmd.name, Board.deleted_at.is_(None)
        )
    ):
        raise ValidationFailed("a board with this name already exists", code="duplicate_name")
    pos = s.scalar(select(func.coalesce(func.max(Board.position), 0)).where(Board.workspace_id == ws.id)) or 0
    b = Board(
        workspace_id=ws.id,
        name=cmd.name.strip(),
        description=cmd.description,
        icon=cmd.icon,
        period_fiscal_year_id=cmd.period_fiscal_year_id,
        settings=cmd.settings,
        position=pos + 1,
    )
    s.add(b)
    s.flush()
    return {"id": str(b.id)}


class UpdateBoard(Command):
    command_name = "boards.update"
    permission = P_BOARDS_MANAGE

    board_id: uuid.UUID
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    period_fiscal_year_id: uuid.UUID | None = None
    clear_period: bool = False
    settings: dict[str, Any] | None = None


@handles(UpdateBoard)
def update_board(ctx: CommandContext, cmd: UpdateBoard) -> None:
    b = ctx.session.get(Board, cmd.board_id)
    if b is None or b.deleted_at is not None:
        raise NotFound("board not found")
    ctx.authorize(P_BOARDS_MANAGE, b.workspace_id)
    if cmd.name is not None:
        b.name = cmd.name.strip()
    if cmd.description is not None:
        b.description = cmd.description
    if cmd.icon is not None:
        b.icon = cmd.icon
    if cmd.period_fiscal_year_id is not None:
        b.period_fiscal_year_id = cmd.period_fiscal_year_id
    if cmd.clear_period:
        b.period_fiscal_year_id = None
    if cmd.settings is not None:
        b.settings = {**(b.settings or {}), **cmd.settings}


class ReorderBoards(Command):
    command_name = "boards.reorder"
    permission = P_BOARDS_MANAGE

    workspace_id: uuid.UUID
    board_ids: list[uuid.UUID]


@handles(ReorderBoards)
def reorder_boards(ctx: CommandContext, cmd: ReorderBoards) -> None:
    _ws(ctx, cmd.workspace_id, P_BOARDS_MANAGE)
    boards = {
        b.id: b for b in ctx.session.scalars(select(Board).where(Board.workspace_id == cmd.workspace_id))
    }
    for pos, bid in enumerate(cmd.board_ids):
        if bid in boards:
            boards[bid].position = pos


class ArchiveBoard(Command):
    """Soft-deletes a board. Its active items are archived (source
    ``board_archived``) and keep their board_id, so restoring the board
    restores exactly those items. No more "Archived (Holding)" board."""

    command_name = "boards.archive"
    permission = P_BOARDS_MANAGE

    board_id: uuid.UUID


@handles(ArchiveBoard)
def archive_board(ctx: CommandContext, cmd: ArchiveBoard) -> dict[str, int]:
    from app.modules.items.models import Item

    s = ctx.session
    b = s.get(Board, cmd.board_id)
    if b is None or b.deleted_at is not None:
        raise NotFound("board not found")
    ctx.authorize(P_BOARDS_MANAGE, b.workspace_id)
    now = utcnow()
    items = list(
        s.scalars(
            select(Item).where(Item.board_id == b.id, Item.is_archived.is_(False), Item.deleted_at.is_(None))
        )
    )
    for it in items:
        it.is_archived = True
        it.archive_source = "board_archived"
        it.archive_ref = str(b.id)
        it.archived_at = now
    b.deleted_at = now
    return {"archived_items": len(items)}


class RestoreBoard(Command):
    command_name = "boards.restore"
    permission = P_BOARDS_MANAGE

    board_id: uuid.UUID


@handles(RestoreBoard)
def restore_board(ctx: CommandContext, cmd: RestoreBoard) -> dict[str, int]:
    from app.modules.items.models import Item

    s = ctx.session
    b = s.get(Board, cmd.board_id)
    if b is None or b.deleted_at is None:
        raise NotFound("archived board not found")
    ctx.authorize(P_BOARDS_MANAGE, b.workspace_id)
    b.deleted_at = None
    items = list(
        s.scalars(
            select(Item).where(
                Item.board_id == b.id, Item.archive_source == "board_archived", Item.archive_ref == str(b.id)
            )
        )
    )
    for it in items:
        it.is_archived = False
        it.archive_source = None
        it.archive_ref = None
        it.archived_at = None
    return {"restored_items": len(items)}


# --- fields ---------------------------------------------------------------------------
def validate_field_config(s: Any, type_: str, config: dict[str, Any]) -> dict[str, Any]:
    ft = field_types.get(type_)
    cfg = dict(config)
    if ft.key in ("select", "multi_select", "period_grid"):
        opts = cfg.get("options") or []
        seen: set[str] = set()
        clean = []
        for o in opts:
            label = str(o.get("label", "")).strip()
            key = o.get("key") or slugify(label)
            _check_key(key)
            if key in seen:
                raise ValidationFailed(f"duplicate option {key}")
            seen.add(key)
            clean.append(
                {
                    "key": key,
                    "label": label or key,
                    "color": o.get("color", "gray"),
                    **({"aliases": o["aliases"]} if o.get("aliases") else {}),
                }
            )
        cfg["options"] = clean
    if ft.key in ("lookup", "lookup_multi") and (
        not cfg.get("list") or not s.scalar(select(LookupList.id).where(LookupList.key == cfg["list"]))
    ):
        raise ValidationFailed("lookup fields need an existing list", code="bad_config")
    if ft.key == "mirror" and (cfg.get("of") not in ("client", "entity", "contact") or not cfg.get("field")):
        raise ValidationFailed("mirror needs of=client|entity|contact and field", code="bad_config")
    return cfg


class CreateField(Command):
    command_name = "fields.create"
    permission = P_SCHEMA_MANAGE

    workspace_id: uuid.UUID
    entity_kind: Literal["item", "task", "client", "entity", "contact"] = "item"
    label: str = Field(min_length=1, max_length=120)
    key: str | None = None
    type: str
    config: dict[str, Any] = {}
    description: str | None = None
    group: str | None = None
    is_required: bool = False
    rollover: Literal["carry", "clear", "add_year"] = "carry"
    track_changes: bool = True


@handles(CreateField)
def create_field(ctx: CommandContext, cmd: CreateField) -> dict[str, str]:
    ws = _ws(ctx, cmd.workspace_id, P_SCHEMA_MANAGE)
    s = ctx.session
    key = _check_key(cmd.key or slugify(cmd.label))
    if is_reserved_key(key):
        raise ValidationFailed(f"'{key}' is reserved", code="reserved_key")
    exists = s.scalar(
        select(FieldDefinition.id).where(
            FieldDefinition.workspace_id == ws.id,
            FieldDefinition.entity_kind == cmd.entity_kind,
            FieldDefinition.key == key,
        )
    )
    if exists:
        raise ValidationFailed(f"field key '{key}' already exists", code="duplicate_key")
    cfg = validate_field_config(s, cmd.type, cmd.config)
    pos = (
        s.scalar(
            select(func.coalesce(func.max(FieldDefinition.position), 0)).where(
                FieldDefinition.workspace_id == ws.id
            )
        )
        or 0
    )
    f = FieldDefinition(
        workspace_id=ws.id,
        entity_kind=cmd.entity_kind,
        key=key,
        label=cmd.label.strip(),
        type=cmd.type,
        config=cfg,
        description=cmd.description,
        group=cmd.group,
        is_required=cmd.is_required,
        rollover=cmd.rollover,
        track_changes=cmd.track_changes,
        position=pos + 1,
    )
    s.add(f)
    s.flush()
    return {"id": str(f.id), "key": key}


class UpdateField(Command):
    """Changes everything except ``key`` and ``type`` (those are referenced by
    stored values, views, rules and migrations)."""

    command_name = "fields.update"
    permission = P_SCHEMA_MANAGE

    field_id: uuid.UUID
    label: str | None = None
    config: dict[str, Any] | None = None
    description: str | None = None
    group: str | None = None
    is_required: bool | None = None
    rollover: Literal["carry", "clear", "add_year"] | None = None
    track_changes: bool | None = None
    is_archived: bool | None = None


@handles(UpdateField)
def update_field(ctx: CommandContext, cmd: UpdateField) -> None:
    f = ctx.session.get(FieldDefinition, cmd.field_id)
    if f is None or f.workspace_id is None:
        raise NotFound("field not found")
    ctx.authorize(P_SCHEMA_MANAGE, f.workspace_id)
    if cmd.label is not None:
        f.label = cmd.label.strip()
    if cmd.config is not None:
        new_cfg = validate_field_config(ctx.session, f.type, {**f.config, **cmd.config})
        if f.type in ("select", "multi_select", "period_grid"):
            removed = {o["key"] for o in f.config.get("options", [])} - {o["key"] for o in new_cfg["options"]}
            if removed:
                # Removing an option would orphan stored values; archive it instead.
                raise ValidationFailed(
                    f"options in use cannot be removed: {sorted(removed)}", code="option_removed"
                )
        f.config = new_cfg
    for attr in ("description", "group", "is_required", "rollover", "track_changes", "is_archived"):
        v = getattr(cmd, attr)
        if v is not None:
            setattr(f, attr, v)


class ReorderFields(Command):
    command_name = "fields.reorder"
    permission = P_SCHEMA_MANAGE

    workspace_id: uuid.UUID
    field_ids: list[uuid.UUID]


@handles(ReorderFields)
def reorder_fields(ctx: CommandContext, cmd: ReorderFields) -> None:
    _ws(ctx, cmd.workspace_id, P_SCHEMA_MANAGE)
    fields = {
        f.id: f
        for f in ctx.session.scalars(
            select(FieldDefinition).where(FieldDefinition.workspace_id == cmd.workspace_id)
        )
    }
    for pos, fid in enumerate(cmd.field_ids):
        if fid in fields:
            fields[fid].position = pos


# --- statuses ---------------------------------------------------------------------------
class UpsertStatus(Command):
    command_name = "statuses.upsert"
    permission = P_SCHEMA_MANAGE

    workspace_id: uuid.UUID
    scope: Literal["item", "task"] = "item"
    key: str | None = None  # existing key = update
    label: str
    color: str = "gray"
    category: str = "todo"
    is_default: bool | None = None
    is_archived: bool | None = None


@handles(UpsertStatus)
def upsert_status(ctx: CommandContext, cmd: UpsertStatus) -> dict[str, str]:
    ws = _ws(ctx, cmd.workspace_id, P_SCHEMA_MANAGE)
    s = ctx.session
    if cmd.category not in STATUS_CATEGORIES:
        raise ValidationFailed(f"category must be one of {sorted(STATUS_CATEGORIES)}")
    key = _check_key(cmd.key or slugify(cmd.label))
    st = s.scalar(
        select(Status).where(Status.workspace_id == ws.id, Status.scope == cmd.scope, Status.key == key)
    )
    if st is None:
        pos = (
            s.scalar(
                select(func.coalesce(func.max(Status.position), 0)).where(
                    Status.workspace_id == ws.id, Status.scope == cmd.scope
                )
            )
            or 0
        )
        st = Status(workspace_id=ws.id, scope=cmd.scope, key=key, label=cmd.label, position=pos + 1)
        s.add(st)
    st.label = cmd.label
    st.color = cmd.color
    st.category = cmd.category
    if cmd.is_archived is not None:
        st.is_archived = cmd.is_archived
    if cmd.is_default:
        s.execute(
            update(Status)
            .where(Status.workspace_id == ws.id, Status.scope == cmd.scope, Status.key != key)
            .values(is_default=False)
        )
        st.is_default = True
    elif cmd.is_default is False:
        st.is_default = False
    s.flush()
    return {"key": key}


class ReorderStatuses(Command):
    command_name = "statuses.reorder"
    permission = P_SCHEMA_MANAGE

    workspace_id: uuid.UUID
    scope: Literal["item", "task"] = "item"
    keys: list[str]


@handles(ReorderStatuses)
def reorder_statuses(ctx: CommandContext, cmd: ReorderStatuses) -> None:
    _ws(ctx, cmd.workspace_id, P_SCHEMA_MANAGE)
    rows = {
        st.key: st
        for st in ctx.session.scalars(
            select(Status).where(Status.workspace_id == cmd.workspace_id, Status.scope == cmd.scope)
        )
    }
    for pos, k in enumerate(cmd.keys):
        if k in rows:
            rows[k].position = pos


# --- member roles -----------------------------------------------------------------------
class UpsertMemberRole(Command):
    command_name = "member_roles.upsert"
    permission = P_SCHEMA_MANAGE

    workspace_id: uuid.UUID
    key: str | None = None
    label: str
    allow_multiple: bool = True
    is_archived: bool | None = None


@handles(UpsertMemberRole)
def upsert_member_role(ctx: CommandContext, cmd: UpsertMemberRole) -> dict[str, str]:
    ws = _ws(ctx, cmd.workspace_id, P_SCHEMA_MANAGE)
    s = ctx.session
    key = _check_key(cmd.key or slugify(cmd.label))
    r = s.scalar(select(MemberRole).where(MemberRole.workspace_id == ws.id, MemberRole.key == key))
    if r is None:
        pos = (
            s.scalar(
                select(func.coalesce(func.max(MemberRole.position), 0)).where(
                    MemberRole.workspace_id == ws.id
                )
            )
            or 0
        )
        r = MemberRole(workspace_id=ws.id, key=key, label=cmd.label, position=pos + 1)
        s.add(r)
    r.label = cmd.label
    r.allow_multiple = cmd.allow_multiple
    if cmd.is_archived is not None:
        r.is_archived = cmd.is_archived
    s.flush()
    return {"key": key}


# --- fiscal years ---------------------------------------------------------------------------
class UpsertFiscalYear(Command):
    command_name = "fiscal_years.upsert"
    permission = P_SYSTEM_ADMIN
    scoped = False

    label: str
    start_date: date
    end_date: date


@handles(UpsertFiscalYear)
def upsert_fiscal_year(ctx: CommandContext, cmd: UpsertFiscalYear) -> dict[str, str]:
    if cmd.end_date <= cmd.start_date:
        raise ValidationFailed("end date must be after start date")
    fy = ctx.session.scalar(select(FiscalYear).where(FiscalYear.label == cmd.label))
    if fy is None:
        fy = FiscalYear(label=cmd.label, start_date=cmd.start_date, end_date=cmd.end_date)
        ctx.session.add(fy)
    fy.start_date, fy.end_date = cmd.start_date, cmd.end_date
    ctx.session.flush()
    return {"id": str(fy.id)}


# --- lookup lists -----------------------------------------------------------------------------
class UpsertLookupList(Command):
    command_name = "lookups.upsert_list"
    permission = P_SCHEMA_MANAGE
    scoped = False

    key: str
    label: str
    is_hierarchical: bool = False


@handles(UpsertLookupList)
def upsert_lookup_list(ctx: CommandContext, cmd: UpsertLookupList) -> dict[str, str]:
    _check_key(cmd.key)
    lst = ctx.session.scalar(select(LookupList).where(LookupList.key == cmd.key))
    if lst is None:
        lst = LookupList(key=cmd.key, label=cmd.label, is_hierarchical=cmd.is_hierarchical)
        ctx.session.add(lst)
    lst.label = cmd.label
    lst.is_hierarchical = cmd.is_hierarchical
    ctx.session.flush()
    return {"id": str(lst.id)}


class UpsertLookupValue(Command):
    command_name = "lookups.upsert_value"
    permission = P_SCHEMA_MANAGE
    scoped = False

    list_key: str
    value_id: uuid.UUID | None = None
    label: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    aliases: list[str] | None = None
    is_active: bool | None = None


@handles(UpsertLookupValue)
def upsert_lookup_value(ctx: CommandContext, cmd: UpsertLookupValue) -> dict[str, str]:
    s = ctx.session
    lst = s.scalar(select(LookupList).where(LookupList.key == cmd.list_key))
    if lst is None:
        raise NotFound(f"lookup list {cmd.list_key} not found")
    if cmd.value_id:
        v = s.get(LookupValue, cmd.value_id)
        if v is None or v.list_id != lst.id:
            raise NotFound("value not found")
    else:
        v = s.scalar(
            select(LookupValue).where(LookupValue.list_id == lst.id, LookupValue.label == cmd.label.strip())
        )
        if v is None:
            pos = (
                s.scalar(
                    select(func.coalesce(func.max(LookupValue.position), 0)).where(
                        LookupValue.list_id == lst.id
                    )
                )
                or 0
            )
            v = LookupValue(list_id=lst.id, label=cmd.label.strip(), position=pos + 1)
            s.add(v)
    v.label = cmd.label.strip()
    if cmd.parent_id is not None:
        v.parent_id = cmd.parent_id
    if cmd.aliases is not None:
        v.aliases = [a.strip() for a in cmd.aliases if a.strip()]
    if cmd.is_active is not None:
        v.is_active = cmd.is_active
    s.flush()
    return {"id": str(v.id)}
