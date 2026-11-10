import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.core.time import utcnow
from app.modules.identity.models import ApiToken, AuthSession, User
from app.modules.workspaces.models import Workspace, WorkspaceMembership
from app.platform.permissions import Actor, ActorKind, WorkspaceRole


@dataclass(frozen=True)
class SessionInfo:
    actor: Actor
    user: User
    csrf_token: str
    session_id: uuid.UUID


def actor_for_user(s: Session, user: User) -> Actor:
    roles = {
        m.workspace_id: WorkspaceRole(m.role)
        for m in s.scalars(select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id))
    }
    return Actor(
        kind=ActorKind.USER,
        user_id=user.id,
        display=user.full_name,
        is_superadmin=user.is_superadmin,
        roles=roles,
    )


def resolve_session(s: Session, token: str) -> SessionInfo | None:
    row = s.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utcnow(),
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    sess, user = row
    return SessionInfo(
        actor=actor_for_user(s, user), user=user, csrf_token=sess.csrf_token, session_id=sess.id
    )


@dataclass(frozen=True)
class TokenInfo:
    actor: Actor
    user: User
    token_id: uuid.UUID
    read_only: bool


def resolve_api_token(s: Session, token: str) -> TokenInfo | None:
    now = utcnow()
    row = s.execute(
        select(ApiToken, User)
        .join(User, User.id == ApiToken.user_id)
        .where(
            ApiToken.token_hash == hash_token(token),
            ApiToken.revoked_at.is_(None),
            or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now),
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    tok, user = row
    return TokenInfo(actor=actor_for_user(s, user), user=user, token_id=tok.id, read_only=tok.read_only)


def list_api_tokens(s: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    now = utcnow()
    rows = s.scalars(select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at.desc()))
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "prefix": t.prefix,
            "read_only": t.read_only,
            "created_at": t.created_at.isoformat(),
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None,
            "active": t.revoked_at is None and (t.expires_at is None or t.expires_at > now),
        }
        for t in rows
    ]


def user_summary(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "aliases": u.aliases or [],
        "is_active": u.is_active,
        "is_superadmin": u.is_superadmin,
        "is_placeholder": u.is_placeholder,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


def list_users(
    s: Session, *, search: str | None = None, include_inactive: bool = True
) -> list[dict[str, Any]]:
    q = select(User).order_by(User.full_name)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if not include_inactive:
        q = q.where(User.is_active.is_(True))
    users = list(s.scalars(q))
    keys = {w.id: w.key for w in s.scalars(select(Workspace))}
    memberships: dict[uuid.UUID, dict[str, str]] = {}
    for m in s.scalars(select(WorkspaceMembership)):
        memberships.setdefault(m.user_id, {})[keys[m.workspace_id]] = m.role
    return [user_summary(u) | {"memberships": memberships.get(u.id, {})} for u in users]


def directory(s: Session) -> list[dict[str, Any]]:
    """Light list for pickers and @mentions (all authenticated users may read)."""
    return [
        {"id": str(u.id), "full_name": u.full_name, "email": u.email, "is_placeholder": u.is_placeholder}
        for u in s.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name))
    ]
