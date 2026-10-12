import uuid
from datetime import timedelta
from typing import Any

from pydantic import Field
from sqlalchemy import delete, func, select, update

from app.core.config import get_settings
from app.core.errors import NotAuthenticated, NotFound, RateLimited, ValidationFailed
from app.core.security import hash_password, hash_token, new_token, password_problems, verify_password
from app.core.time import utcnow
from app.modules.identity.models import AuthSession, LoginAttempt, User
from app.modules.workspaces.models import Workspace, WorkspaceMembership
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_USERS_MANAGE, WorkspaceRole


def _check_password(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise ValidationFailed(
            "password too weak: " + ", ".join(problems), code="weak_password", details={"problems": problems}
        )


def _normalise_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email:
        raise ValidationFailed("invalid email", code="invalid_email")
    return email


# --- authentication -------------------------------------------------------
class Login(Command):
    command_name = "identity.login"
    exposed = False
    scoped = False
    secret_fields = frozenset({"password"})
    log_result = False

    email: str
    password: str
    ip: str | None = None
    user_agent: str | None = None


@handles(Login)
def login(ctx: CommandContext, cmd: Login) -> dict[str, Any]:
    s = ctx.session
    settings = get_settings()
    email = cmd.email.strip().lower()
    window_start = utcnow() - timedelta(minutes=settings.login_lockout_minutes)
    failures = (
        s.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.email == email,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.created_at > window_start,
            )
        )
        or 0
    )
    if failures >= settings.login_max_failures:
        raise RateLimited("too many failed attempts, try again later", code="login_locked")

    user = s.scalar(select(User).where(User.email == email))
    ok = (
        user is not None
        and user.is_active
        and not user.is_placeholder
        and verify_password(cmd.password, user.password_hash)
    )
    s.add(LoginAttempt(email=email, ip=cmd.ip, succeeded=ok))
    if not ok or user is None:
        # Commit the failed attempt; the bus would roll it back on an exception.
        return {"ok": False}

    token, csrf = new_token(), new_token()
    s.add(
        AuthSession(
            token_hash=hash_token(token),
            csrf_token=csrf,
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
            ip=cmd.ip,
            user_agent=(cmd.user_agent or "")[:500],
        )
    )
    s.execute(update(User).where(User.id == user.id).values(last_login_at=utcnow()))
    return {"ok": True, "token": token, "csrf": csrf, "user_id": str(user.id)}


class Logout(Command):
    command_name = "identity.logout"
    exposed = False
    scoped = False
    secret_fields = frozenset({"token"})

    token: str


@handles(Logout)
def logout(ctx: CommandContext, cmd: Logout) -> None:
    ctx.session.execute(
        update(AuthSession).where(AuthSession.token_hash == hash_token(cmd.token)).values(revoked_at=utcnow())
    )


# --- self service -----------------------------------------------------------
class ChangeOwnPassword(Command):
    command_name = "identity.change_own_password"
    scoped = False
    secret_fields = frozenset({"current_password", "new_password"})

    current_password: str
    new_password: str


@handles(ChangeOwnPassword)
def change_own_password(ctx: CommandContext, cmd: ChangeOwnPassword) -> None:
    if ctx.actor.user_id is None:
        raise NotAuthenticated("login required")
    user = ctx.session.get(User, ctx.actor.user_id)
    if user is None or not verify_password(cmd.current_password, user.password_hash):
        raise ValidationFailed("current password is incorrect", code="wrong_password")
    _check_password(cmd.new_password)
    user.password_hash = hash_password(cmd.new_password)


class UpdateMyProfile(Command):
    command_name = "identity.update_my_profile"
    scoped = False

    full_name: str | None = None
    locale: str | None = Field(default=None, pattern="^(en|zh-CN)$")
    preferences: dict[str, Any] | None = None


@handles(UpdateMyProfile)
def update_my_profile(ctx: CommandContext, cmd: UpdateMyProfile) -> None:
    if ctx.actor.user_id is None:
        raise NotAuthenticated("login required")
    user = ctx.session.get(User, ctx.actor.user_id)
    assert user is not None
    if cmd.full_name is not None:
        if not cmd.full_name.strip():
            raise ValidationFailed("name is required")
        user.full_name = cmd.full_name.strip()
    if cmd.locale is not None:
        user.locale = cmd.locale
    if cmd.preferences is not None:
        user.preferences = {**(user.preferences or {}), **cmd.preferences}


# --- user administration ------------------------------------------------------
class CreateUser(Command):
    command_name = "identity.create_user"
    permission = P_USERS_MANAGE
    scoped = False
    secret_fields = frozenset({"password"})

    email: str
    full_name: str
    password: str | None = None
    is_superadmin: bool = False
    is_placeholder: bool = False
    aliases: list[str] = []
    # workspace key -> role
    memberships: dict[str, WorkspaceRole] = {}


@handles(CreateUser)
def create_user(ctx: CommandContext, cmd: CreateUser) -> dict[str, str]:
    s = ctx.session
    email = _normalise_email(cmd.email)
    if s.scalar(select(User.id).where(User.email == email)):
        raise ValidationFailed("a user with this email already exists", code="duplicate_email")
    if not cmd.full_name.strip():
        raise ValidationFailed("name is required")
    if cmd.password:
        _check_password(cmd.password)
    user = User(
        email=email,
        full_name=cmd.full_name.strip(),
        password_hash=hash_password(cmd.password) if cmd.password else None,
        is_superadmin=cmd.is_superadmin,
        is_placeholder=cmd.is_placeholder,
        aliases=_clean_aliases(cmd.aliases),
    )
    s.add(user)
    s.flush()
    _apply_memberships(ctx, user.id, cmd.memberships)
    return {"id": str(user.id)}


class UpdateUser(Command):
    command_name = "identity.update_user"
    permission = P_USERS_MANAGE
    scoped = False

    user_id: uuid.UUID
    email: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_superadmin: bool | None = None
    is_placeholder: bool | None = None
    aliases: list[str] | None = None
    memberships: dict[str, WorkspaceRole | None] | None = None  # role None removes access


@handles(UpdateUser)
def update_user(ctx: CommandContext, cmd: UpdateUser) -> None:
    s = ctx.session
    user = s.get(User, cmd.user_id)
    if user is None:
        raise NotFound("user not found")
    if cmd.email is not None:
        email = _normalise_email(cmd.email)
        if email != user.email and s.scalar(select(User.id).where(User.email == email)):
            raise ValidationFailed("a user with this email already exists", code="duplicate_email")
        user.email = email
    if cmd.full_name is not None:
        user.full_name = cmd.full_name.strip()
    if cmd.is_active is not None:
        if not cmd.is_active and cmd.user_id == ctx.actor.user_id:
            raise ValidationFailed("you cannot deactivate yourself")
        user.is_active = cmd.is_active
        if not cmd.is_active:
            s.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
    if cmd.is_superadmin is not None:
        if not cmd.is_superadmin and cmd.user_id == ctx.actor.user_id:
            raise ValidationFailed("you cannot remove your own admin rights")
        user.is_superadmin = cmd.is_superadmin
    if cmd.is_placeholder is not None:
        user.is_placeholder = cmd.is_placeholder
    if cmd.aliases is not None:
        user.aliases = _clean_aliases(cmd.aliases)
    if cmd.memberships is not None:
        _apply_memberships(ctx, user.id, cmd.memberships)


class SetUserPassword(Command):
    command_name = "identity.set_user_password"
    permission = P_USERS_MANAGE
    scoped = False
    secret_fields = frozenset({"password"})

    user_id: uuid.UUID
    password: str


@handles(SetUserPassword)
def set_user_password(ctx: CommandContext, cmd: SetUserPassword) -> None:
    user = ctx.session.get(User, cmd.user_id)
    if user is None:
        raise NotFound("user not found")
    _check_password(cmd.password)
    user.password_hash = hash_password(cmd.password)
    user.is_placeholder = False
    # A password reset by an admin logs the user out everywhere.
    ctx.session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


class PurgeExpiredSessions(Command):
    command_name = "identity.purge_expired_sessions"
    exposed = False
    scoped = False


@handles(PurgeExpiredSessions)
def purge_expired_sessions(ctx: CommandContext, cmd: PurgeExpiredSessions) -> int:
    cutoff = utcnow() - timedelta(days=30)
    r1 = ctx.session.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    ctx.session.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    return int(r1.rowcount or 0)  # type: ignore[attr-defined]


# --- helpers ------------------------------------------------------------------
def _clean_aliases(aliases: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for a in aliases:
        a = a.strip()
        if a and a.lower() not in seen:
            seen[a.lower()] = a
    return list(seen.values())


def _apply_memberships(ctx: CommandContext, user_id: uuid.UUID, memberships: dict[str, Any]) -> None:
    s = ctx.session
    if not memberships:
        return
    workspaces = {w.key: w for w in s.scalars(select(Workspace))}
    for key, role in memberships.items():
        ws = workspaces.get(key)
        if ws is None:
            raise ValidationFailed(f"unknown workspace {key}")
        existing = s.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == ws.id, WorkspaceMembership.user_id == user_id
            )
        )
        if role is None:
            if existing is not None:
                s.delete(existing)
        elif existing is None:
            s.add(WorkspaceMembership(workspace_id=ws.id, user_id=user_id, role=WorkspaceRole(role).value))
        else:
            existing.role = WorkspaceRole(role).value
