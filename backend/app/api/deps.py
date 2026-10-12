"""Request-scoped dependencies: session, actor, CSRF, command execution."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import read_session
from app.core.errors import NotAuthenticated, PermissionDenied
from app.modules.identity.queries import SessionInfo, resolve_session
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


def current_actor(info: CurrentSession) -> Actor:
    return info.actor


CurrentActor = Annotated[Actor, Depends(current_actor)]


@dataclass
class Executor:
    actor: Actor
    idempotency_key: str | None

    def __call__(self, cmd: Command, *, batch_id: Any = None) -> CommandResult:
        return bus.execute(
            cmd, actor=self.actor, origin=Origin.UI, idempotency_key=self.idempotency_key, batch_id=batch_id
        )


def executor(actor: CurrentActor, idempotency_key: Annotated[str | None, Header()] = None) -> Executor:
    return Executor(actor=actor, idempotency_key=idempotency_key)


Exec = Annotated[Executor, Depends(executor)]
