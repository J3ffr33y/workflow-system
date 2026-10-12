"""Item write logic shared by item commands, rollover, automations and
migration. Everything here runs inside a CommandContext (one transaction).
"""

import uuid
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.time import business_today
from app.modules.clients.models import Client, ClientEntity
from app.modules.items.models import Item, ItemMember
from app.modules.workspaces.models import Board, FiscalYear, MemberRole, Status, Workspace
from app.modules.workspaces.schema import ColumnSpec, FieldResolver, columns_by_key, item_columns
from app.platform.commands import CommandContext
from app.platform.fields.types import FieldValueError, field_types
from app.platform.jsonvalue import to_json

_MISSING: Any = object()


class ItemWriter:
    """Validates and applies field values to items of one workspace."""

    def __init__(self, ctx: CommandContext, workspace: Workspace) -> None:
        self.ctx = ctx
        self.s = ctx.session
        self.ws = workspace
        self.columns = columns_by_key(item_columns(self.s, workspace))
        self.resolver = FieldResolver(self.s)
        self._statuses = {
            st.key: st
            for st in self.s.scalars(
                select(Status).where(Status.workspace_id == workspace.id, Status.scope == "item")
            )
        }
        self._roles = {
            r.key: r
            for r in self.s.scalars(select(MemberRole).where(MemberRole.workspace_id == workspace.id))
        }
        self._boards: dict[uuid.UUID, Board] = {}

    # ---- lookups ---------------------------------------------------------
    def column(self, key: str) -> ColumnSpec:
        col = self.columns.get(key)
        if col is None:
            raise ValidationFailed(f"unknown field '{key}'", code="unknown_field", details={"field": key})
        return col

    def board(self, board_id: uuid.UUID) -> Board:
        if board_id not in self._boards:
            b = self.s.get(Board, board_id)
            if b is None or b.workspace_id != self.ws.id:
                raise NotFound("board not found in this workspace")
            self._boards[board_id] = b
        return self._boards[board_id]

    def allowed_statuses(self, board: Board) -> list[Status]:
        active = sorted(
            (st for st in self._statuses.values() if not st.is_archived), key=lambda st: st.position
        )
        allowed = (board.settings or {}).get("statuses")
        if allowed:
            keep = set(allowed)
            return [st for st in active if st.key in keep]
        return active

    def default_status(self, board: Board) -> str | None:
        allowed = self.allowed_statuses(board)
        for st in allowed:
            if st.is_default:
                return st.key
        return allowed[0].key if allowed else None

    def members(self, item: Item, role_key: str) -> list[ItemMember]:
        return list(
            self.s.scalars(
                select(ItemMember)
                .where(ItemMember.item_id == item.id, ItemMember.role_key == role_key)
                .order_by(ItemMember.created_at)
            )
        )

    # ---- reading ---------------------------------------------------------
    def current(self, item: Item, key: str) -> Any:
        col = self.column(key)
        if col.source == "core":
            attr = {
                "client": "client_id",
                "entity": "entity_id",
                "board": "board_id",
                "fiscal_year": "fiscal_year_id",
            }
            return to_json(getattr(item, attr.get(key, key)))
        if col.source == "role":
            return [str(m.user_id) for m in self.members(item, col.config["role"])]
        if col.source == "data":
            return (item.data or {}).get(key)
        return None

    # ---- writing ---------------------------------------------------------
    def set(
        self, item: Item, key: str, value: Any, *, expected: Any = _MISSING, parse_text: bool = False
    ) -> Any:
        col = self.column(key)
        if not col.editable:
            raise ValidationFailed(f"'{col.label}' is read-only", code="read_only", details={"field": key})
        if expected is not _MISSING:
            current = self.current(item, key)
            if _norm_cmp(current) != _norm_cmp(expected):
                raise Conflict(
                    f"'{col.label}' was changed by someone else",
                    code="stale_value",
                    details={"field": key, "current": current},
                )
        try:
            if col.source == "core":
                return self._set_core(item, col, value, parse_text)
            if col.source == "role":
                return self._set_role(item, col, value, parse_text)
            return self._set_data(item, col, value, parse_text)
        except FieldValueError as e:
            raise ValidationFailed(
                f"{col.label}: {e}", code=e.code, details={"field": key, "value": to_json(value)}
            ) from None

    def _set_data(self, item: Item, col: ColumnSpec, value: Any, parse_text: bool) -> Any:
        ft = field_types.get(col.type)
        v = (
            ft.parse_text(value, col.config, self.resolver)
            if parse_text
            else ft.normalize(value, col.config, self.resolver)
        )
        if col.required and ft.is_empty(v):
            raise ValidationFailed(f"'{col.label}' is required", code="required", details={"field": col.key})
        item.set_data(col.key, v)
        return v

    def _set_role(self, item: Item, col: ColumnSpec, value: Any, parse_text: bool) -> Any:
        ft = field_types.get("users")
        users: list[str] = (
            ft.parse_text(value, {}, self.resolver) if parse_text else ft.normalize(value, {}, self.resolver)
        )
        role = col.config["role"]
        if not col.config.get("allow_multiple", True) and len(users) > 1:
            raise ValidationFailed(
                f"'{col.label}' allows one person", code="single_only", details={"field": col.key}
            )
        existing = {str(m.user_id): m for m in self.members(item, role)}
        for uid, m in existing.items():
            if uid not in users:
                self.s.delete(m)
        for uid in users:
            if uid not in existing:
                self.s.add(
                    ItemMember(
                        item_id=item.id, user_id=uuid.UUID(uid), role_key=role, assigned_date=business_today()
                    )
                )
        return users

    def _set_core(self, item: Item, col: ColumnSpec, value: Any, parse_text: bool) -> Any:
        key = col.key
        if isinstance(value, str) and parse_text:
            value = value.strip() or None
        if key == "name":
            v = field_types.get("text").normalize(value, {"max_length": 300})
            if not v:
                raise ValidationFailed("name is required", code="required", details={"field": "name"})
            item.name = v
            return v
        if key == "status":
            if value is None:
                item.status = None
                return None
            board = self.board(item.board_id)
            allowed = {st.key: st for st in self.allowed_statuses(board)}
            if value not in allowed and parse_text:
                match = [k for k, st in allowed.items() if st.label.lower() == str(value).lower()]
                value = match[0] if match else value
            if value not in allowed:
                raise ValidationFailed(
                    f"status '{value}' is not allowed on this board",
                    code="bad_status",
                    details={"field": "status"},
                )
            item.status = value
            return value
        if key == "due_date":
            ft = field_types.get("date")
            v = ft.parse_text(value, {}) if parse_text else ft.normalize(value, {})
            item.due_date = date.fromisoformat(v) if v else None
            return v
        if key == "client":
            if value is None:
                item.client_id = None
                item.entity_id = None
                return None
            client = self.s.get(Client, uuid.UUID(str(value)))
            if client is None or client.deleted_at is not None:
                raise ValidationFailed("unknown client", code="unknown_client", details={"field": "client"})
            if item.client_id != client.id:
                item.client_id = client.id
                item.entity_id = None
            return str(client.id)
        if key == "entity":
            if value is None:
                item.entity_id = None
                return None
            ent = self.s.get(ClientEntity, uuid.UUID(str(value)))
            if ent is None or ent.client_id != item.client_id or ent.deleted_at is not None:
                raise ValidationFailed("entity does not belong to the client", code="bad_entity")
            item.entity_id = ent.id
            return str(ent.id)
        if key == "fiscal_year":
            if value is None:
                item.fiscal_year_id = None
                return None
            fy = self._fiscal_year(value)
            item.fiscal_year_id = fy.id
            return str(fy.id)
        raise ValidationFailed(f"'{key}' cannot be set directly", code="read_only")

    def _fiscal_year(self, value: Any) -> FiscalYear:
        try:
            fy = self.s.get(FiscalYear, uuid.UUID(str(value)))
        except ValueError:
            fy = self.s.scalar(select(FiscalYear).where(FiscalYear.label == str(value).strip()))
        if fy is None:
            raise ValidationFailed(f"unknown fiscal year '{value}'", code="unknown_fiscal_year")
        return fy

    # ---- create ----------------------------------------------------------
    def create(self, board: Board, values: dict[str, Any], *, parse_text: bool = False) -> Item:
        if board.deleted_at is not None:
            raise ValidationFailed("board is archived", code="board_archived")
        item = Item(workspace_id=self.ws.id, board_id=board.id, name="", data={})
        if board.period_fiscal_year_id and "fiscal_year" not in values:
            item.fiscal_year_id = board.period_fiscal_year_id
        self.s.add(item)
        # Core links first: entity validation depends on client.
        ordered = sorted(values.items(), key=lambda kv: {"client": 0, "entity": 1, "name": 2}.get(kv[0], 9))
        errors: dict[str, str] = {}
        self.s.flush()
        for key, value in ordered:
            try:
                self.set(item, key, value, parse_text=parse_text)
            except ValidationFailed as e:
                errors[key] = e.message
        if not item.name:
            errors.setdefault("name", "name is required")
        for key, col in self.columns.items():
            if col.required and col.source == "data" and key not in values:
                errors[key] = f"'{col.label}' is required"
        if errors:
            raise ValidationFailed("invalid values", code="invalid_item", details={"fields": errors})
        if item.status is None:
            item.status = self.default_status(board)
        self._apply_autofill(item, values)
        return item

    def _apply_autofill(self, item: Item, values: dict[str, Any]) -> None:
        """Workspace-configured defaults from the client, e.g.

        settings.autofill = {
          "entity": "primary",                         # pick primary entity
          "data": {"year_end": "entity.year_end_month"},
          "roles": {"partner": "client.partner_user_id"}
        }
        """
        rules = (self.ws.settings or {}).get("autofill", {})
        if not rules or item.client_id is None:
            return
        client = self.s.get(Client, item.client_id)
        if client is None:
            return
        if rules.get("entity") == "primary" and item.entity_id is None and "entity" not in values:
            item.entity_id = self.s.scalar(
                select(ClientEntity.id).where(
                    ClientEntity.client_id == client.id,
                    ClientEntity.is_primary.is_(True),
                    ClientEntity.deleted_at.is_(None),
                )
            )
        entity = self.s.get(ClientEntity, item.entity_id) if item.entity_id else None
        for key, src in rules.get("data", {}).items():
            if key in values or (item.data or {}).get(key) is not None or key not in self.columns:
                continue
            obj, attr = src.split(".", 1)
            source = entity if obj == "entity" else client
            v = getattr(source, attr, None) if source is not None else None
            if v is not None:
                self.set(item, key, v)
        for role, src in rules.get("roles", {}).items():
            col_key = f"role.{role}"
            if col_key in values or col_key not in self.columns or self.members(item, role):
                continue
            uid = getattr(client, src.split(".", 1)[1], None)
            if uid is not None:
                self.s.add(
                    ItemMember(item_id=item.id, user_id=uid, role_key=role, assigned_date=business_today())
                )


def _norm_cmp(v: Any) -> Any:
    if v in (None, "", [], {}):
        return None
    if isinstance(v, list):
        return sorted(str(x) for x in v)
    return v


def load_item(ctx: CommandContext, item_id: uuid.UUID, *, include_archived: bool = True) -> Item:
    item = ctx.session.get(Item, item_id)
    if item is None or item.deleted_at is not None:
        raise NotFound("item not found")
    if not include_archived and item.is_archived:
        raise ValidationFailed("item is archived", code="item_archived")
    return item


def next_fiscal_year(s: Any, fy_id: uuid.UUID | None) -> FiscalYear | None:
    if fy_id is None:
        return None
    cur = s.get(FiscalYear, fy_id)
    if cur is None:
        return None
    nxt = s.scalar(
        select(FiscalYear).where(FiscalYear.start_date > cur.end_date).order_by(FiscalYear.start_date)
    )
    if nxt is None:
        nxt = s.scalar(
            select(FiscalYear).where(FiscalYear.start_date > cur.start_date).order_by(FiscalYear.start_date)
        )
    return nxt


def add_years(value: Any, type_: str, years: int = 1) -> Any:
    if value in (None, ""):
        return value
    if type_ == "date":
        return (date.fromisoformat(value) + relativedelta(years=years)).isoformat()
    if type_ == "year_month":
        y, m = value.split("-")
        return f"{int(y) + years:04d}-{m}"
    return value
