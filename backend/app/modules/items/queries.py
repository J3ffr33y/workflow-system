"""Read side for items: board listing (filter / sort / page), detail, home."""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, String, and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.core.time import business_today
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.collaboration.models import Comment
from app.modules.identity.models import User
from app.modules.items.models import Item, ItemMember
from app.modules.tasks.models import Task
from app.modules.workspaces.models import Board, FiscalYear, Status, Workspace
from app.modules.workspaces.schema import ColumnSpec, columns_by_key, item_columns
from app.platform.fields.types import Kind
from app.platform.permissions import P_ITEMS_READ, Actor
from app.platform.query.filters import ColumnRef, compile_filter, jsonb_column

MAX_PAGE = 500


class ItemQueryContext:
    """Builds SQL expressions for the columns of one workspace."""

    def __init__(self, s: Session, workspace: Workspace) -> None:
        self.s = s
        self.ws = workspace
        self.cols = columns_by_key(item_columns(s, workspace))
        self.client = aliased(Client, name="c")
        self.entity = aliased(ClientEntity, name="e")
        self.fy = aliased(FiscalYear, name="fy")

    def base(self) -> Select[Any]:
        return (
            select(Item)
            .outerjoin(self.client, self.client.id == Item.client_id)
            .outerjoin(self.entity, self.entity.id == Item.entity_id)
            .outerjoin(self.fy, self.fy.id == Item.fiscal_year_id)
            .where(Item.workspace_id == self.ws.id, Item.deleted_at.is_(None))
        )

    def _status_position(self) -> ColumnElement[Any]:
        return (
            select(Status.position)
            .where(
                Status.workspace_id == Item.workspace_id, Status.scope == "item", Status.key == Item.status
            )
            .scalar_subquery()
        )

    def ref(self, key: str) -> ColumnRef:
        col = self.cols.get(key)
        if col is None:
            raise ValidationFailed(f"unknown field '{key}'", code="unknown_field")
        kind = Kind(col.kind)
        if col.source == "core":
            match key:
                case "name":
                    return ColumnRef(key, kind, text=Item.name, typed=Item.name)
                case "client":
                    return ColumnRef(key, kind, text=self.client.name, typed=Item.client_id.cast(String))
                case "entity":
                    return ColumnRef(key, kind, text=self.entity.name, typed=Item.entity_id.cast(String))
                case "status":
                    return ColumnRef(key, kind, text=Item.status, typed=Item.status)
                case "fiscal_year":
                    return ColumnRef(key, kind, text=self.fy.label, typed=Item.fiscal_year_id.cast(String))
                case "board":
                    return ColumnRef(
                        key, kind, text=Item.board_id.cast(String), typed=Item.board_id.cast(String)
                    )
                case "due_date":
                    return ColumnRef(key, kind, text=Item.due_date.cast(String), typed=Item.due_date)
                case "created_at" | "updated_at":
                    c = getattr(Item, key)
                    return ColumnRef(key, kind, text=c.cast(String), typed=c)
                case "archive_source":
                    return ColumnRef(key, kind, text=Item.archive_source, typed=Item.archive_source)
        if col.source == "role":
            role = col.config["role"]

            def role_filter(op: str, value: Any) -> ColumnElement[bool]:
                ids = [str(v) for v in (value if isinstance(value, list) else [value]) if v]
                if op == "me":  # resolved by caller to has_any
                    op = "has_any"
                base = exists().where(ItemMember.item_id == Item.id, ItemMember.role_key == role)
                if op == "empty":
                    return not_(base)
                if op == "not_empty":
                    return base
                if not ids:
                    return Item.id.isnot(None)
                if op == "has_any":
                    return exists().where(
                        ItemMember.item_id == Item.id,
                        ItemMember.role_key == role,
                        ItemMember.user_id.cast(String).in_(ids),
                    )
                if op == "has_all":
                    return and_(
                        *[
                            exists().where(
                                ItemMember.item_id == Item.id,
                                ItemMember.role_key == role,
                                ItemMember.user_id.cast(String) == i,
                            )
                            for i in ids
                        ]
                    )
                return not_(
                    exists().where(
                        ItemMember.item_id == Item.id,
                        ItemMember.role_key == role,
                        ItemMember.user_id.cast(String).in_(ids),
                    )
                )

            first_name = (
                select(func.min(User.full_name))
                .join(ItemMember, ItemMember.user_id == User.id)
                .where(ItemMember.item_id == Item.id, ItemMember.role_key == role)
                .scalar_subquery()
            )
            return ColumnRef(key, kind, text=first_name, typed=first_name, custom=role_filter)
        if col.source == "mirror":
            return self._mirror_ref(col)
        return jsonb_column(key, kind, Item.data)

    def _mirror_ref(self, col: ColumnSpec) -> ColumnRef:
        kind = Kind(col.kind)
        field = col.config["field"]
        if col.config.get("of") == "contact":
            # Primary contact: correlated subquery (never multiplies rows).
            attr_c = getattr(Contact, field)
            sub = (
                select(attr_c.cast(String))
                .where(
                    Contact.client_id == Item.client_id,
                    Contact.is_primary.is_(True),
                    Contact.deleted_at.is_(None),
                )
                .order_by(Contact.created_at)
                .limit(1)
                .scalar_subquery()
            )
            return ColumnRef(col.key, kind, text=sub, typed=sub)
        target = self.client if col.config.get("of") == "client" else self.entity
        if field.startswith("data."):
            ref = jsonb_column(field[5:], kind, target.data)
            return ColumnRef(col.key, kind, text=ref.text, typed=ref.typed, multi=ref.multi)
        attr = getattr(target, field)
        typed: ColumnElement[Any] = attr
        if kind == Kind.REF:
            typed = attr.cast(String)
        return ColumnRef(col.key, kind, text=attr.cast(String), typed=typed)

    def sort_expr(self, key: str) -> ColumnElement[Any]:
        if key == "status":
            return self._status_position()
        ref = self.ref(key)
        if key in ("client", "entity", "fiscal_year"):
            assert ref.text is not None
            return ref.text
        if ref.kind == Kind.MULTI and ref.multi is not None:
            return ref.multi.cast(String)
        expr = ref.typed if ref.typed is not None else ref.text
        assert expr is not None
        return expr


def _resolve_me(tree: Any, user_id: uuid.UUID | None) -> Any:
    """Replace the "$me" placeholder in filter values with the viewer's id,
    so shared views like "My work" work for everyone."""
    if isinstance(tree, dict):
        return {k: _resolve_me(v, user_id) for k, v in tree.items()}
    if isinstance(tree, list):
        return [_resolve_me(v, user_id) for v in tree]
    if tree == "$me":
        return str(user_id) if user_id else None
    return tree


def list_items(
    s: Session,
    actor: Actor,
    *,
    workspace_id: uuid.UUID,
    board_ids: list[uuid.UUID] | None = None,
    archived: bool = False,
    filter_tree: dict[str, Any] | None = None,
    search: str | None = None,
    sort: list[dict[str, str]] | None = None,
    offset: int = 0,
    limit: int = 200,
    client_id: uuid.UUID | None = None,
    item_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    ws = s.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("workspace not found")
    if not actor.can(P_ITEMS_READ, ws.id):
        raise PermissionDenied("no access to this workspace")
    qc = ItemQueryContext(s, ws)
    q = qc.base().where(Item.is_archived.is_(archived))
    if board_ids:
        q = q.where(Item.board_id.in_(board_ids))
    if client_id:
        q = q.where(Item.client_id == client_id)
    if item_ids is not None:
        q = q.where(Item.id.in_(item_ids))
    if filter_tree:
        q = q.where(compile_filter(_resolve_me(filter_tree, actor.user_id), qc.ref))
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.where(or_(Item.name.ilike(term), qc.client.name.ilike(term)))

    total = s.scalar(select(func.count()).select_from(q.with_only_columns(Item.id).subquery())) or 0
    order: list[Any] = []
    for srt in sort or []:
        expr = qc.sort_expr(srt["field"])
        order.append(expr.desc().nulls_last() if srt.get("dir") == "desc" else expr.asc().nulls_last())
    order += [Item.position, func.lower(Item.name), Item.id]
    limit = max(1, min(limit, MAX_PAGE))
    items = list(s.scalars(q.order_by(*order).offset(offset).limit(limit)))
    return {"total": total, "offset": offset, "rows": hydrate(s, qc, items)}


def hydrate(s: Session, qc: ItemQueryContext, items: list[Item]) -> list[dict[str, Any]]:
    if not items:
        return []
    ids = [i.id for i in items]
    clients = {
        c.id: c
        for c in s.scalars(select(Client).where(Client.id.in_({i.client_id for i in items if i.client_id})))
    }
    entities = {
        e.id: e
        for e in s.scalars(
            select(ClientEntity).where(ClientEntity.id.in_({i.entity_id for i in items if i.entity_id}))
        )
    }
    members: dict[uuid.UUID, dict[str, list[str]]] = {}
    for m in s.scalars(select(ItemMember).where(ItemMember.item_id.in_(ids)).order_by(ItemMember.created_at)):
        members.setdefault(m.item_id, {}).setdefault(m.role_key, []).append(str(m.user_id))
    task_counts = {
        row.item_id: (row.total, row.open)
        for row in s.execute(
            select(
                Task.item_id,
                func.count().label("total"),
                func.count()
                .filter(
                    Task.status.notin_(
                        select(Status.key).where(
                            Status.workspace_id == qc.ws.id, Status.scope == "task", Status.category == "done"
                        )
                    )
                )
                .label("open"),
            )
            .where(Task.item_id.in_(ids), Task.deleted_at.is_(None))
            .group_by(Task.item_id)
        )
    }
    latest = (
        select(
            Comment.entity_id,
            Comment.body,
            Comment.created_at,
            func.coalesce(User.full_name, Comment.author_display).label("author"),
            func.row_number()
            .over(partition_by=Comment.entity_id, order_by=Comment.created_at.desc())
            .label("rn"),
        )
        .outerjoin(User, User.id == Comment.author_id)
        .where(Comment.entity_type == "item", Comment.entity_id.in_(ids), Comment.deleted_at.is_(None))
        .subquery()
    )
    last_comments = {
        r.entity_id: {"body": r.body[:500], "author": r.author, "created_at": r.created_at.isoformat()}
        for r in s.execute(select(latest).where(latest.c.rn == 1))
    }
    comment_counts = dict(
        s.execute(
            select(Comment.entity_id, func.count())
            .where(Comment.entity_type == "item", Comment.entity_id.in_(ids), Comment.deleted_at.is_(None))
            .group_by(Comment.entity_id)
        ).all()
    )
    mirror_cols = [c for c in qc.cols.values() if c.source == "mirror"]
    contacts: dict[uuid.UUID, Contact] = {}
    if any(c.config.get("of") == "contact" for c in mirror_cols):
        for ct in s.scalars(
            select(Contact)
            .where(
                Contact.client_id.in_(list(clients)),
                Contact.is_primary.is_(True),
                Contact.deleted_at.is_(None),
            )
            .order_by(Contact.created_at.desc())
        ):
            assert ct.client_id is not None
            contacts[ct.client_id] = ct

    rows = []
    for it in items:
        client = clients.get(it.client_id) if it.client_id else None
        entity = entities.get(it.entity_id) if it.entity_id else None
        mirrors: dict[str, Any] = {}
        for mc in mirror_cols:
            of = mc.config.get("of")
            target: Any = (
                client if of == "client" else entity if of == "entity" else contacts.get(it.client_id)  # type: ignore[arg-type]
            )
            if target is None:
                continue
            f = mc.config["field"]
            v = (target.data or {}).get(f[5:]) if f.startswith("data.") else getattr(target, f, None)
            mirrors[mc.key] = str(v) if isinstance(v, uuid.UUID) else v
        tc = task_counts.get(it.id, (0, 0))
        rows.append(
            {
                "id": str(it.id),
                "workspace_id": str(it.workspace_id),
                "board_id": str(it.board_id),
                "name": it.name,
                "client": str(it.client_id) if it.client_id else None,
                "client_name": client.name if client else None,
                "entity": str(it.entity_id) if it.entity_id else None,
                "entity_name": entity.name if entity else None,
                "status": it.status,
                "fiscal_year": str(it.fiscal_year_id) if it.fiscal_year_id else None,
                "due_date": it.due_date.isoformat() if it.due_date else None,
                "created_at": it.created_at.isoformat(),
                "updated_at": it.updated_at.isoformat(),
                "is_archived": it.is_archived,
                "archive_source": it.archive_source,
                "archive_ref": it.archive_ref,
                "archived_at": it.archived_at.isoformat() if it.archived_at else None,
                "highlight_color": it.highlight_color,
                "rolled_from_id": str(it.rolled_from_id) if it.rolled_from_id else None,
                "version": it.version,
                "data": it.data or {},
                "roles": members.get(it.id, {}),
                "mirrors": mirrors,
                "task_count": tc[0],
                "open_task_count": tc[1],
                "comment_count": comment_counts.get(it.id, 0),
                "last_comment": last_comments.get(it.id),
            }
        )
    return rows


def item_detail(s: Session, actor: Actor, item_id: uuid.UUID) -> dict[str, Any]:
    it = s.get(Item, item_id)
    if it is None or it.deleted_at is not None:
        raise NotFound("item not found")
    if not actor.can(P_ITEMS_READ, it.workspace_id):
        raise PermissionDenied("no access")
    ws = s.get(Workspace, it.workspace_id)
    assert ws is not None
    qc = ItemQueryContext(s, ws)
    row = hydrate(s, qc, [it])[0]
    row["members"] = [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "role_key": m.role_key,
            "assigned_date": m.assigned_date.isoformat() if m.assigned_date else None,
        }
        for m in s.scalars(
            select(ItemMember).where(ItemMember.item_id == it.id).order_by(ItemMember.created_at)
        )
    ]
    return row


def home(s: Session, actor: Actor) -> dict[str, Any]:
    """The signed-in user's work across workspaces."""
    if actor.user_id is None:
        return {"workspaces": []}
    ws_ids = actor.workspace_ids()
    mine = exists().where(ItemMember.item_id == Item.id, ItemMember.user_id == actor.user_id)
    q = (
        select(Item.workspace_id, Item.status, func.count())
        .where(Item.deleted_at.is_(None), Item.is_archived.is_(False), mine)
        .group_by(Item.workspace_id, Item.status)
    )
    if ws_ids is not None:
        q = q.where(Item.workspace_id.in_(ws_ids))
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for wid, status, n in s.execute(q):
        counts.setdefault(wid, {})[status or ""] = n
    today = business_today()
    due_soon = (
        select(Item, Board.name)
        .join(Board, Board.id == Item.board_id)
        .where(
            Item.deleted_at.is_(None),
            Item.is_archived.is_(False),
            mine,
            Item.due_date.isnot(None),
            Item.due_date <= today + timedelta(days=30),
        )
        .order_by(Item.due_date)
        .limit(50)
    )
    if ws_ids is not None:
        due_soon = due_soon.where(Item.workspace_id.in_(ws_ids))
    workspaces = s.scalars(select(Workspace).where(Workspace.id.in_(list(counts) or [uuid.uuid4()])))
    statuses = {
        (st.workspace_id, st.key): st for st in s.scalars(select(Status).where(Status.scope == "item"))
    }
    out = []
    for w in sorted(workspaces, key=lambda w: w.position):
        by_status = counts.get(w.id, {})
        out.append(
            {
                "workspace_id": str(w.id),
                "workspace_key": w.key,
                "workspace_name": w.name,
                "total": sum(by_status.values()),
                "by_status": [
                    {
                        "status": k,
                        "label": statuses[(w.id, k)].label if (w.id, k) in statuses else (k or "—"),
                        "color": statuses[(w.id, k)].color if (w.id, k) in statuses else "gray",
                        "category": statuses[(w.id, k)].category if (w.id, k) in statuses else "todo",
                        "count": n,
                    }
                    for k, n in sorted(
                        by_status.items(),
                        key=lambda kv: statuses[(w.id, kv[0])].position if (w.id, kv[0]) in statuses else 999,
                    )
                ],
            }
        )
    return {
        "workspaces": out,
        "due_soon": [
            {
                "id": str(it.id),
                "name": it.name,
                "workspace_id": str(it.workspace_id),
                "board_id": str(it.board_id),
                "board_name": bname,
                "status": it.status,
                "due_date": it.due_date.isoformat() if it.due_date else None,
                "overdue": bool(it.due_date and it.due_date < today),
            }
            for it, bname in s.execute(due_soon)
        ],
    }
