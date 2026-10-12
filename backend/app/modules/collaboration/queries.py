import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, PermissionDenied
from app.modules.collaboration.models import Comment, Notification
from app.modules.identity.models import User
from app.modules.items.models import Item
from app.modules.tasks.models import Task
from app.platform.permissions import P_CLIENTS_READ, P_ITEMS_READ, Actor


def _check_read(s: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID) -> None:
    if entity_type == "item":
        it = s.get(Item, entity_id)
        if it is None:
            raise NotFound("item not found")
        ok = actor.can(P_ITEMS_READ, it.workspace_id)
    elif entity_type == "task":
        t = s.get(Task, entity_id)
        if t is None:
            raise NotFound("task not found")
        ok = actor.can(P_ITEMS_READ, t.workspace_id)
    else:
        ok = actor.can(P_CLIENTS_READ)
    if not ok:
        raise PermissionDenied("no access")


def comments_for(s: Session, actor: Actor, entity_type: str, entity_id: uuid.UUID) -> list[dict[str, Any]]:
    _check_read(s, actor, entity_type, entity_id)
    rows = s.execute(
        select(Comment, User.full_name)
        .outerjoin(User, User.id == Comment.author_id)
        .where(
            Comment.entity_type == entity_type, Comment.entity_id == entity_id, Comment.deleted_at.is_(None)
        )
        .order_by(Comment.created_at.desc())
    ).all()
    return [
        {
            "id": str(c.id),
            "parent_comment_id": str(c.parent_comment_id) if c.parent_comment_id else None,
            "author_id": str(c.author_id) if c.author_id else None,
            "author": name or c.author_display,
            "body": c.body,
            "mentions": c.mentions or [],
            "created_at": c.created_at.isoformat(),
            "edited_at": c.edited_at.isoformat() if c.edited_at else None,
            "is_mine": c.author_id == actor.user_id,
        }
        for c, name in rows
    ]


def notifications_for(
    s: Session, actor: Actor, *, unread_only: bool = False, limit: int = 50
) -> dict[str, Any]:
    q = select(Notification).where(Notification.user_id == actor.user_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    unread = s.scalar(
        select(func.count()).where(Notification.user_id == actor.user_id, Notification.read_at.is_(None))
    )
    return {
        "unread": unread or 0,
        "rows": [
            {
                "id": str(n.id),
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "entity_type": n.entity_type,
                "entity_id": str(n.entity_id) if n.entity_id else None,
                "workspace_id": str(n.workspace_id) if n.workspace_id else None,
                "actor": n.actor_display,
                "read": n.read_at is not None,
                "created_at": n.created_at.isoformat(),
            }
            for n in s.scalars(q.order_by(Notification.created_at.desc()).limit(limit))
        ],
    }
