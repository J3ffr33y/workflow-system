"""The column catalog: what fields an item has in a given workspace.

Four sources, one shape (``ColumnSpec``):

* core    real columns on ``items`` (name, client, status, due_date...)
* data    custom field definitions, values in ``items.data``
* role    team members with a role, e.g. ``role.preparer``
* mirror  read-only view of a client / entity attribute

Boards, filters, bulk edit, export, rollover, automations and migration all
work from this catalog, so they automatically support new fields.
"""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.identity.models import User
from app.modules.workspaces.models import (
    FieldDefinition,
    LookupList,
    LookupValue,
    MemberRole,
    Workspace,
)
from app.platform.fields.types import Kind, field_types

# Reference types for core columns that are not stored in JSONB.
CORE_REF_TYPES = {"client", "client_entity", "board", "status", "fiscal_year"}


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    label: str
    type: str
    source: str  # core | data | role | mirror | computed
    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    editable: bool = True
    required: bool = False
    group: str | None = None
    position: int = 0
    rollover: str = "carry"  # carry | clear | add_year
    track_changes: bool = True
    hidden_by_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# key, label, type, kind, editable, rollover
_CORE: list[tuple[str, str, str, Kind, bool, str]] = [
    ("name", "Name", "text", Kind.TEXT, True, "carry"),
    ("client", "Client", "client", Kind.REF, True, "carry"),
    ("entity", "Entity", "client_entity", Kind.REF, True, "carry"),
    ("status", "Status", "status", Kind.REF, True, "clear"),
    ("fiscal_year", "Fiscal Year", "fiscal_year", Kind.REF, True, "add_year"),
    ("due_date", "Due Date", "date", Kind.DATE, True, "add_year"),
    ("board", "Board", "board", Kind.REF, False, "carry"),
    ("created_at", "Created", "datetime", Kind.DATETIME, False, "clear"),
    ("updated_at", "Last Updated", "datetime", Kind.DATETIME, False, "clear"),
    ("archive_source", "Archived By", "text", Kind.TEXT, False, "clear"),
]
CORE_KEYS = {c[0] for c in _CORE}
RESERVED_PREFIXES = ("role.", "client.", "entity.")


def is_reserved_key(key: str) -> bool:
    return key in CORE_KEYS or key.startswith(RESERVED_PREFIXES) or key in {"id", "data", "tasks"}


def item_columns(s: Session, workspace: Workspace) -> list[ColumnSpec]:
    settings = workspace.settings or {}
    core_overrides: dict[str, dict[str, Any]] = settings.get("core_columns", {})
    cols: list[ColumnSpec] = []
    for pos, (key, label, type_, kind, editable, rollover) in enumerate(_CORE):
        o = core_overrides.get(key, {})
        if o.get("disabled"):
            continue
        cols.append(
            ColumnSpec(
                key=key,
                label=o.get("label", label if key != "name" else f"{workspace.item_label} Name"),
                type=type_,
                source="core",
                kind=kind.value,
                editable=editable,
                required=key in ("name",) or bool(o.get("required")),
                position=pos - 100,
                rollover=o.get("rollover", rollover),
                hidden_by_default=bool(o.get("hidden", key in ("created_at", "archive_source", "board"))),
            )
        )

    for r in s.scalars(
        select(MemberRole)
        .where(MemberRole.workspace_id == workspace.id, MemberRole.is_archived.is_(False))
        .order_by(MemberRole.position)
    ):
        cols.append(
            ColumnSpec(
                key=f"role.{r.key}",
                label=r.label,
                type="users",
                source="role",
                kind=Kind.MULTI.value,
                config={"role": r.key, "allow_multiple": r.allow_multiple},
                group="Team",
                position=r.position,
            )
        )

    for f in s.scalars(
        select(FieldDefinition)
        .where(
            FieldDefinition.workspace_id == workspace.id,
            FieldDefinition.entity_kind == "item",
            FieldDefinition.is_archived.is_(False),
        )
        .order_by(FieldDefinition.position)
    ):
        ft = field_types.get(f.type)
        is_mirror = f.type == "mirror"
        display_type = f.config.get("display_type", "text") if is_mirror else f.type
        kind = (
            field_types.get(display_type).kind if is_mirror and display_type in field_types.types else ft.kind
        )
        if is_mirror and display_type in CORE_REF_TYPES | {"user"}:
            kind = Kind.REF
        cols.append(
            ColumnSpec(
                key=f.key,
                label=f.label,
                type=f.type,
                source="mirror" if is_mirror else "data",
                kind=kind.value,
                config=f.config,
                editable=ft.editable,
                required=f.is_required,
                group=f.group,
                position=f.position,
                rollover="clear" if is_mirror else f.rollover,
                track_changes=f.track_changes,
            )
        )
    return cols


def columns_by_key(cols: list[ColumnSpec]) -> dict[str, ColumnSpec]:
    return {c.key: c for c in cols}


def get_workspace(s: Session, workspace_id: uuid.UUID) -> Workspace:
    ws = s.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("workspace not found")
    return ws


class FieldResolver:
    """Implements the field-type Resolver protocol with per-instance caches.

    One instance per request/command; do not share across transactions.
    """

    def __init__(self, s: Session) -> None:
        self.s = s
        self._users: dict[str, User] | None = None
        self._user_index: dict[str, str] | None = None
        self._lookups: dict[str, dict[str, LookupValue]] = {}
        self._lookup_index: dict[str, dict[str, str]] = {}
        self._labels: dict[str, str] = {}

    # users -------------------------------------------------------------
    def _load_users(self) -> None:
        if self._users is not None:
            return
        self._users = {str(u.id): u for u in self.s.scalars(select(User))}
        index: dict[str, str] = {}
        for uid, u in self._users.items():
            keys = [u.full_name, u.email, u.email.split("@")[0], *(u.aliases or [])]
            first = u.full_name.split(" ")[0]
            keys.append(first)
            for k in keys:
                k = k.strip().lower()
                # Ambiguous short keys (two "Win"s) are dropped rather than guessed.
                if k in index and index[k] != uid:
                    index[k] = ""
                else:
                    index.setdefault(k, uid)
        self._user_index = {k: v for k, v in index.items() if v}

    def user_ids(self) -> set[str]:
        self._load_users()
        assert self._users is not None
        return set(self._users)

    def find_user(self, text: str) -> str | None:
        self._load_users()
        assert self._user_index is not None
        t = text.strip().lstrip("@").lower()
        return self._user_index.get(t)

    def user_label(self, user_id: str) -> str:
        self._load_users()
        assert self._users is not None
        u = self._users.get(str(user_id))
        return u.full_name if u else str(user_id)

    # lookups -------------------------------------------------------------
    def _load_list(self, list_key: str) -> None:
        if list_key in self._lookups:
            return
        lst = self.s.scalar(select(LookupList).where(LookupList.key == list_key))
        values = list(self.s.scalars(select(LookupValue).where(LookupValue.list_id == lst.id))) if lst else []
        self._lookups[list_key] = {str(v.id): v for v in values}
        idx: dict[str, str] = {}
        for v in values:
            for k in [v.label, *(v.aliases or [])]:
                idx.setdefault(k.strip().lower(), str(v.id))
            self._labels[str(v.id)] = v.label
        self._lookup_index[list_key] = idx

    def lookup_ids(self, list_key: str) -> set[str]:
        self._load_list(list_key)
        return set(self._lookups[list_key])

    def find_lookup(self, list_key: str, text: str) -> str | None:
        self._load_list(list_key)
        return self._lookup_index[list_key].get(text.strip().lower())

    def lookup_label(self, value_id: str) -> str:
        if value_id not in self._labels:
            v = self.s.get(LookupValue, uuid.UUID(value_id))
            self._labels[value_id] = v.label if v else value_id
        return self._labels[value_id]

    def invalidate(self) -> None:
        self._users = None
        self._user_index = None
        self._lookups.clear()
        self._lookup_index.clear()
