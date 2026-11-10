"""Request-scoped dependencies: session, actor, CSRF, command execution.

Two ways in: the browser's session cookie (CSRF-checked on writes) or a
personal API token in ``Authorization: Bearer …`` (no CSRF: browsers never
attach that header by themselves). Both end up as the same ``Actor`` and go
through the same command bus, so permissions and audit do not depend on
which door was used.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import read_session
from app.core.errors import NotAuthenticated, PermissionDenied
from app.modules.identity.queries import SessionInfo, resolve_api_token, resolve_session
from app.platform.commands import Command, CommandResult, Origin, bus
from app.platform.permissions import Actor

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def db() -> Iterator[Session]:
    with read_session() as s:
        yield s


ReadDB = Annotated[Session, Depends(db)]


def current_session(request: Request, s: ReadDB) -> SessionInfo:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise NotAuthenticated("login required")
    info = resolve_session(s, token)
    if info is None:
        raise NotAuthenticated("session expired")
    if request.method in UNSAFE_METHODS:
        sent = request.headers.get(settings.csrf_header_name)
        if not sent or sent != info.csrf_token:
            raise PermissionDenied("missing or invalid CSRF token", code="csrf_failed")
    return info


CurrentSession = Annotated[SessionInfo, Depends(current_session)]


@dataclass(frozen=True)
class Principal:
    actor: Actor
    via: str  # "session" | "token"
    read_only: bool = False


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, value = auth.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def current_principal(request: Request, s: ReadDB) -> Principal:
    token = _bearer(request)
    if token is not None:
        info = resolve_api_token(s, token)
        if info is None:
            raise NotAuthenticated("invalid, expired or revoked API token", code="bad_token")
        return Principal(actor=info.actor, via="token", read_only=info.read_only)
    return Principal(actor=current_session(request, s).actor, via="session")


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def current_actor(p: CurrentPrincipal) -> Actor:
    return p.actor


CurrentActor = Annotated[Actor, Depends(current_actor)]


@dataclass
class Executor:
    principal: Principal
    idempotency_key: str | None

    @property
    def actor(self) -> Actor:
        return self.principal.actor

    def __call__(self, cmd: Command, *, batch_id: Any = None) -> CommandResult:
        p = self.principal
        if p.via == "token":
            if p.read_only:
                raise PermissionDenied("this API token is read-only", code="token_read_only")
            if cmd.session_only:
                raise PermissionDenied(
                    f"{cmd.command_name} needs a signed-in session, not an API token", code="session_only"
                )
        return bus.execute(
            cmd,
            actor=p.actor,
            origin=Origin.API if p.via == "token" else Origin.UI,
            idempotency_key=self.idempotency_key,
            batch_id=batch_id,
        )


def executor(p: CurrentPrincipal, idempotency_key: Annotated[str | None, Header()] = None) -> Executor:
    return Executor(principal=p, idempotency_key=idempotency_key)


Exec = Annotated[Executor, Depends(executor)]
