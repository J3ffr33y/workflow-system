import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.identity.models import User
from app.modules.items.models import Item
from app.modules.workspaces.models import Board, Workspace
from app.platform.permissions import Actor


def entity_dict(e: ClientEntity) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "name": e.name,
        "entity_type": e.entity_type,
        "abn": e.abn,
        "acn": e.acn,
        "year_end_month": e.year_end_month,
        "is_primary": e.is_primary,
        "data": e.data or {},
    }


def contact_dict(c: Contact) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "client_id": str(c.client_id) if c.client_id else None,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "role": c.role,
        "is_primary": c.is_primary,
        "is_billing": c.is_billing,
        "is_referrer": c.is_referrer,
        "channels": c.channels or {},
        "notes": c.notes,
    }


def list_clients(
    s: Session,
    actor: Actor,
    *,
    search: str | None = None,
    archived: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    ws_ids = actor.workspace_ids()
    item_filter = [Item.client_id == Client.id, Item.deleted_at.is_(None), Item.is_archived.is_(False)]
    if ws_ids is not None:
        item_filter.append(Item.workspace_id.in_(ws_ids))
    active_items = select(func.count()).where(*item_filter).correlate(Client).scalar_subquery()
    q = (
        select(Client, User.full_name, active_items.label("active_items"))
        .outerjoin(User, User.id == Client.partner_user_id)
        .where(Client.deleted_at.is_(None), Client.is_archived.is_(archived))
    )
    if search:
        term = search.strip()
        q = q.where(or_(Client.name.ilike(f"%{term}%"), func.similarity(Client.name, term) > 0.3))
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    rows = s.execute(q.order_by(Client.name).limit(limit).offset(offset)).all()
    primaries = {
        e.client_id: e
        for e in s.scalars(
            select(ClientEntity).where(
                ClientEntity.client_id.in_([r[0].id for r in rows]),
                ClientEntity.is_primary.is_(True),
                ClientEntity.deleted_at.is_(None),
            )
        )
    }
    out = []
    for c, partner_name, n_active in rows:
        pe = primaries.get(c.id)
        out.append(
            {
                "id": str(c.id),
                "name": c.name,
                "client_type": c.client_type,
                "partner_user_id": str(c.partner_user_id) if c.partner_user_id else None,
                "partner_name": partner_name,
                "active_items": n_active,
                "is_archived": c.is_archived,
                "primary_entity": entity_dict(pe) if pe else None,
                "data": c.data or {},
            }
        )
    return {"total": total, "rows": out}


def client_detail(s: Session, actor: Actor, client_id: uuid.UUID) -> dict[str, Any]:
    c = s.get(Client, client_id)
    if c is None or c.deleted_at is not None:
        raise NotFound("client not found")
    entities = s.scalars(
        select(ClientEntity)
        .where(ClientEntity.client_id == c.id, ClientEntity.deleted_at.is_(None))
        .order_by(ClientEntity.is_primary.desc(), ClientEntity.name)
    )
    contacts = s.scalars(
        select(Contact).where(Contact.client_id == c.id, Contact.deleted_at.is_(None)).order_by(Contact.name)
    )
    ws_ids = actor.workspace_ids()
    iq = (
        select(Item, Board.name, Workspace.key, Workspace.name)
        .join(Board, Board.id == Item.board_id)
        .join(Workspace, Workspace.id == Item.workspace_id)
        .where(Item.client_id == c.id, Item.deleted_at.is_(None))
        .order_by(Item.is_archived, Workspace.position, Board.position, Item.name)
    )
    if ws_ids is not None:
        iq = iq.where(Item.workspace_id.in_(ws_ids))
    partner = s.get(User, c.partner_user_id) if c.partner_user_id else None
    return {
        "id": str(c.id),
        "name": c.name,
        "client_type": c.client_type,
        "partner_user_id": str(c.partner_user_id) if c.partner_user_id else None,
        "partner_name": partner.full_name if partner else None,
        "referred_by_contact_id": str(c.referred_by_contact_id) if c.referred_by_contact_id else None,
        "notes": c.notes,
        "is_archived": c.is_archived,
        "data": c.data or {},
        "entities": [entity_dict(e) for e in entities],
        "contacts": [contact_dict(ct) for ct in contacts],
        "items": [
            {
                "id": str(it.id),
                "name": it.name,
                "status": it.status,
                "board_id": str(it.board_id),
                "board_name": bname,
                "workspace_id": str(it.workspace_id),
                "workspace_key": wkey,
                "workspace_name": wname,
                "is_archived": it.is_archived,
            }
            for it, bname, wkey, wname in s.execute(iq)
        ],
    }


def check_name(s: Session, name: str, exclude_id: uuid.UUID | None = None) -> dict[str, Any]:
    q = select(Client.id, Client.name, Client.is_archived).where(
        func.lower(Client.name) == name.strip().lower(), Client.deleted_at.is_(None)
    )
    if exclude_id:
        q = q.where(Client.id != exclude_id)
    row = s.execute(q).first()
    similar = [
        {"id": str(r.id), "name": r.name}
        for r in s.execute(
            select(Client.id, Client.name)
            .where(Client.deleted_at.is_(None), func.similarity(Client.name, name) > 0.45)
            .order_by(func.similarity(Client.name, name).desc())
            .limit(5)
        )
    ]
    return {
        "taken": row is not None,
        "existing": {"id": str(row.id), "name": row.name, "is_archived": row.is_archived} if row else None,
        "similar": similar,
    }


def entities_for_clients(s: Session, client_ids: list[uuid.UUID]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in s.scalars(
        select(ClientEntity).where(ClientEntity.client_id.in_(client_ids), ClientEntity.deleted_at.is_(None))
    ):
        out.setdefault(str(e.client_id), []).append(entity_dict(e))
    return out
