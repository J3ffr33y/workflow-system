import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.views.models import SavedView
from app.platform.permissions import Actor


def list_views(
    s: Session, actor: Actor, workspace_id: uuid.UUID, board_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    q = select(SavedView).where(
        SavedView.workspace_id == workspace_id,
        or_(SavedView.scope == "shared", SavedView.owner_id == actor.user_id),
    )
    if board_id:
        q = q.where(or_(SavedView.board_id == board_id, SavedView.board_id.is_(None)))
    views = list(s.scalars(q.order_by(SavedView.scope.desc(), SavedView.position, SavedView.name)))
    return [
        {
            "id": str(v.id),
            "workspace_id": str(v.workspace_id),
            "board_id": str(v.board_id) if v.board_id else None,
            "name": v.name,
            "scope": v.scope,
            "is_default": v.is_default,
            "is_mine": v.owner_id == actor.user_id,
            "config": v.config,
        }
        for v in views
    ]
