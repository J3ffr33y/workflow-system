"""The command bus: the only way data changes.

    result = bus.execute(UpdateItemField(...), actor=actor, origin=Origin.UI)

What happens, in one write transaction:

1. idempotency check (same key already succeeded -> return the stored result)
2. handler runs; handlers call ``ctx.authorize(...)`` for scoped permissions
3. every flush is inspected by the audit capture hook (see ``_capture``)
4. audit rows, outbox events and per-subscriber deliveries are written
5. a ``command_log`` row is written
6. commit, then NOTIFY so the worker and realtime listeners wake up

Failures roll everything back and are recorded in ``command_log`` in a
separate transaction.
"""

import copy
import json
import logging
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import chain
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import event as sa_event
from sqlalchemy import insert, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import write_session
from app.core.errors import AppError, Conflict, PermissionDenied
from app.platform.audit.models import Audited, AuditEntry
from app.platform.commands.models import CommandLog
from app.platform.events.models import Event, EventDelivery
from app.platform.events.registry import subscribers
from app.platform.jsonvalue import to_json
from app.platform.permissions import Actor

log = logging.getLogger("flow.commands")

NOTIFY_EVENTS = "flow_events"
NOTIFY_CHANGES = "flow_changes"


class Origin(StrEnum):
    UI = "ui"
    API = "api"
    AUTOMATION = "automation"
    MIGRATION = "migration"
    SYSTEM = "system"
    UNDO = "undo"


class Command(BaseModel):
    """Base class for commands. Subclasses are plain pydantic payloads.

    ``permission``: checked by the bus before the handler when ``scoped`` is
    False (global resources). When ``scoped`` is True, the handler must call
    ``ctx.authorize(permission, workspace_id)`` once it knows the workspace;
    the bus refuses to commit a scoped command that never authorised.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    command_name: ClassVar[str]
    permission: ClassVar[str | None] = None  # None: any authenticated actor
    scoped: ClassVar[bool] = True
    # Never written to command_log (passwords, tokens).
    secret_fields: ClassVar[frozenset[str]] = frozenset()
    # False for commands whose result is itself a secret (login tokens).
    log_result: ClassVar[bool] = True
    # False for internal commands (worker, migration engine): not published
    # as HTTP endpoints.
    exposed: ClassVar[bool] = True

    def loggable_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for f in self.secret_fields:
            if f in data:
                data[f] = "***"
        return data


C = TypeVar("C", bound=Command)
Handler = Callable[["CommandContext", Any], Any]


@dataclass
class _Change:
    entity_type: str
    entity_id: uuid.UUID
    op: str
    parent: tuple[str, uuid.UUID] | None
    workspace_id: uuid.UUID | None
    changes: dict[str, list[Any]]  # field -> [before, after]


@dataclass
class _PendingEvent:
    type: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    payload: dict[str, Any]


@dataclass
class CommandContext:
    session: Session
    actor: Actor
    origin: Origin
    command_id: uuid.UUID
    batch_id: uuid.UUID | None
    depth: int
    reason: str | None
    bus: "CommandBus"
    authorized: bool = False
    # Quiet changes do not trigger automations (undo, migration, cascades such
    # as "archive client -> archive its items"). They are still audited.
    quiet: bool = False
    _changes: dict[tuple[str, uuid.UUID], _Change] = field(default_factory=dict)
    _events: list[_PendingEvent] = field(default_factory=list)

    # -- authorisation -----------------------------------------------------
    def authorize(self, permission: str, workspace_id: uuid.UUID | None) -> None:
        self.actor.require(permission, workspace_id)
        self.authorized = True

    # -- events -------------------------------------------------------------
    def emit(
        self,
        type: str,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._events.append(_PendingEvent(type, entity_type, entity_id, workspace_id, to_json(payload or {})))

    # -- nesting ------------------------------------------------------------
    def run(self, cmd: Command) -> Any:
        """Run another command inside this transaction (same command_id).

        Permissions of the inner command are still enforced.
        """
        handler = self.bus.handler_for(cmd)
        inner = CommandContext(
            session=self.session,
            actor=self.actor,
            origin=self.origin,
            command_id=self.command_id,
            batch_id=self.batch_id,
            depth=self.depth,
            reason=self.reason,
            bus=self.bus,
            quiet=self.quiet,
            _changes=self._changes,
            _events=self._events,
        )
        if not cmd.scoped and cmd.permission:
            self.actor.require(cmd.permission)
            inner.authorized = True
        result = handler(inner, cmd)
        if cmd.scoped and cmd.permission and not inner.authorized:
            raise RuntimeError(f"scoped command {cmd.command_name} never called ctx.authorize")
        return result

    # -- savepoints -----------------------------------------------------------
    @contextmanager
    def savepoint(self) -> Iterator[None]:
        """Run a block in a SAVEPOINT. If it raises, both the database work and
        the captured audit changes / events of that block are discarded, so
        audit never mentions rows that were rolled back."""
        changes = copy.deepcopy(self._changes)
        events = list(self._events)
        try:
            with self.session.begin_nested():
                yield
        except Exception:
            self._changes.clear()
            self._changes.update(changes)
            self._events[:] = events
            raise

    # -- change capture (called by the flush hook) -------------------------
    def _record(self, obj: Audited, op: str, diff: dict[str, list[Any]]) -> None:
        entity_id = obj.id  # type: ignore[attr-defined]
        key = (obj.__entity_type__, entity_id)
        existing = self._changes.get(key)
        if existing is None:
            self._changes[key] = _Change(
                entity_type=obj.__entity_type__,
                entity_id=entity_id,
                op=op,
                parent=obj.audit_parent(),
                workspace_id=obj.audit_workspace_id(),
                changes=diff,
            )
            return
        # Several flushes in one command: keep the first "before", last "after".
        if op == "delete":
            existing.op = "delete" if existing.op != "create" else "noop"
        for f, (before, after) in diff.items():
            if f in existing.changes:
                existing.changes[f][1] = after
            else:
                existing.changes[f] = [before, after]


@dataclass
class CommandResult:
    command_id: uuid.UUID
    result: Any
    replayed: bool = False


class CommandBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Command], Handler] = {}

    def register(self, cmd_type: type[C], handler: Callable[[CommandContext, C], Any]) -> None:
        if cmd_type in self._handlers:
            raise ValueError(f"duplicate handler for {cmd_type.__name__}")
        if not getattr(cmd_type, "command_name", None):
            raise ValueError(f"{cmd_type.__name__} must define command_name")
        self._handlers[cmd_type] = handler

    def handler_for(self, cmd: Command) -> Handler:
        try:
            return self._handlers[type(cmd)]
        except KeyError:
            raise RuntimeError(f"no handler registered for {type(cmd).__name__}") from None

    def registered(self) -> list[type[Command]]:
        return list(self._handlers)

    def execute(
        self,
        cmd: Command,
        *,
        actor: Actor,
        origin: Origin = Origin.UI,
        reason: str | None = None,
        idempotency_key: str | None = None,
        batch_id: uuid.UUID | None = None,
        parent_command_id: uuid.UUID | None = None,
        depth: int = 0,
    ) -> CommandResult:
        if depth > get_settings().automation_max_depth:
            raise Conflict("command cascade too deep", code="cascade_depth_exceeded")
        handler = self.handler_for(cmd)
        command_id = uuid.uuid4()
        started = time.monotonic()
        payload = cmd.loggable_payload()

        try:
            with write_session() as s, s.begin():
                if idempotency_key:
                    prior = s.scalar(
                        select(CommandLog).where(
                            CommandLog.idempotency_key == idempotency_key, CommandLog.status == "succeeded"
                        )
                    )
                    if prior is not None:
                        return CommandResult(prior.id, (prior.result or {}).get("value"), replayed=True)

                ctx = CommandContext(
                    session=s,
                    actor=actor,
                    origin=origin,
                    command_id=command_id,
                    batch_id=batch_id,
                    depth=depth,
                    reason=reason,
                    bus=self,
                    quiet=origin in (Origin.UNDO, Origin.MIGRATION),
                )
                if not cmd.scoped and cmd.permission:
                    actor.require(cmd.permission)
                    ctx.authorized = True
                s.info["command_ctx"] = ctx
                try:
                    value = handler(ctx, cmd)
                    s.flush()
                finally:
                    s.info.pop("command_ctx", None)

                if cmd.scoped and cmd.permission and not ctx.authorized:
                    raise RuntimeError(f"scoped command {cmd.command_name} never called ctx.authorize")

                self._persist_side_effects(s, ctx)
                s.add(
                    CommandLog(
                        id=command_id,
                        name=cmd.command_name,
                        status="succeeded",
                        origin=origin.value,
                        actor_id=actor.user_id,
                        actor_display=actor.display,
                        payload=payload,
                        result={"value": to_json(value)} if cmd.log_result else None,
                        reason=reason,
                        idempotency_key=idempotency_key,
                        batch_id=batch_id,
                        parent_command_id=parent_command_id,
                        depth=depth,
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                )
                s.flush()
                self._notify(s, ctx)
            return CommandResult(command_id, value)
        except Exception as exc:
            self._log_failure(
                cmd, payload, exc, actor, origin, reason, idempotency_key, batch_id, depth, started
            )
            raise

    # ------------------------------------------------------------------
    def _persist_side_effects(self, s: Session, ctx: CommandContext) -> None:
        audit_rows = []
        for ch in ctx._changes.values():
            if ch.op == "noop":
                continue
            changes = [
                {"field": f, "before": to_json(b), "after": to_json(a)}
                for f, (b, a) in ch.changes.items()
                if ch.op != "update" or b != a
            ]
            if ch.op == "update" and not changes:
                continue
            audit_rows.append(
                {
                    "command_id": ctx.command_id,
                    "batch_id": ctx.batch_id,
                    "origin": ctx.origin.value,
                    "actor_id": ctx.actor.user_id,
                    "actor_display": ctx.actor.display,
                    "entity_type": ch.entity_type,
                    "entity_id": ch.entity_id,
                    "parent_type": ch.parent[0] if ch.parent else None,
                    "parent_id": ch.parent[1] if ch.parent else None,
                    "workspace_id": ch.workspace_id,
                    "op": ch.op,
                    "changes": changes,
                }
            )
            ctx._events.append(
                _PendingEvent(
                    type=f"{ch.entity_type}.{ch.op}d",
                    entity_type=ch.entity_type,
                    entity_id=ch.entity_id,
                    workspace_id=ch.workspace_id,
                    payload={
                        "changes": changes,
                        "parent": [ch.parent[0], str(ch.parent[1])] if ch.parent else None,
                        "quiet": ctx.quiet,
                    },
                )
            )
        if audit_rows:
            s.execute(insert(AuditEntry), audit_rows)

        for ev in ctx._events:
            event_id = s.scalar(
                insert(Event)
                .values(
                    type=ev.type,
                    entity_type=ev.entity_type,
                    entity_id=ev.entity_id,
                    workspace_id=ev.workspace_id,
                    command_id=ctx.command_id,
                    origin=ctx.origin.value,
                    actor_id=ctx.actor.user_id,
                    depth=ctx.depth,
                    payload=ev.payload,
                )
                .returning(Event.id)
            )
            targets = subscribers.for_event(ev.type)
            if targets:
                s.execute(
                    insert(EventDelivery),
                    [{"event_id": event_id, "subscriber": t.name} for t in targets],
                )

    def _notify(self, s: Session, ctx: CommandContext) -> None:
        if ctx._events:
            s.execute(text("SELECT pg_notify(:c, '')"), {"c": NOTIFY_EVENTS})
        if ctx._changes:
            types = sorted({c.entity_type for c in ctx._changes.values()})
            ids = [str(c.entity_id) for c in list(ctx._changes.values())[:50]]
            payload = json.dumps({"types": types, "ids": ids, "actor": str(ctx.actor.user_id or "")})
            # NOTIFY payloads are capped at 8000 bytes.
            if len(payload) > 7900:
                payload = json.dumps({"types": types, "ids": []})
            s.execute(text("SELECT pg_notify(:c, :p)"), {"c": NOTIFY_CHANGES, "p": payload})

    def _log_failure(
        self,
        cmd: Command,
        payload: dict[str, Any],
        exc: Exception,
        actor: Actor,
        origin: Origin,
        reason: str | None,
        idempotency_key: str | None,
        batch_id: uuid.UUID | None,
        depth: int,
        started: float,
    ) -> None:
        if isinstance(exc, PermissionDenied | AppError):
            code, message = exc.code, exc.message
        else:
            code, message = "internal_error", repr(exc)
            log.exception("command %s failed", cmd.command_name)
        try:
            with write_session() as s, s.begin():
                s.add(
                    CommandLog(
                        id=uuid.uuid4(),
                        name=cmd.command_name,
                        status="failed",
                        origin=origin.value,
                        actor_id=actor.user_id,
                        actor_display=actor.display,
                        payload=payload,
                        reason=reason,
                        idempotency_key=idempotency_key,
                        batch_id=batch_id,
                        depth=depth,
                        error_code=code,
                        error_message=message[:2000],
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                )
        except Exception:  # never mask the original error
            log.exception("could not record failed command")


bus = CommandBus()


def handles(
    cmd_type: type[C],
) -> Callable[[Callable[[CommandContext, C], Any]], Callable[[CommandContext, C], Any]]:
    def deco(fn: Callable[[CommandContext, C], Any]) -> Callable[[CommandContext, C], Any]:
        bus.register(cmd_type, fn)
        return fn

    return deco


# ---------------------------------------------------------------------------
# Change capture
# ---------------------------------------------------------------------------
def _diff(obj: Audited, op: str) -> dict[str, list[Any]]:
    state = inspect(obj)
    assert state is not None
    out: dict[str, list[Any]] = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in obj.__audit_exclude__:
            continue
        if op == "create":
            value = getattr(obj, key)
            if key == "data" and isinstance(value, dict):
                for k, v in value.items():
                    if v is not None:
                        out[f"data.{k}"] = [None, v]
            elif value is not None:
                out[key] = [None, value]
            continue
        if op == "delete":
            value = getattr(obj, key)
            if key == "data" and isinstance(value, dict):
                for k, v in value.items():
                    out[f"data.{k}"] = [v, None]
            else:
                out[key] = [value, None]
            continue
        hist = state.attrs[key].history
        if not hist.has_changes():
            continue
        before = hist.deleted[0] if hist.deleted else None
        after = hist.added[0] if hist.added else None
        if key == "data":
            b = before or {}
            a = after or {}
            for k in set(b) | set(a):
                if b.get(k) != a.get(k):
                    out[f"data.{k}"] = [b.get(k), a.get(k)]
        else:
            out[key] = [before, after]
    return out


@sa_event.listens_for(Session, "after_flush")
def _capture(session: Session, _flush_ctx: Any) -> None:
    ctx: CommandContext | None = session.info.get("command_ctx")
    if ctx is None:
        touched = [o for o in chain(session.new, session.dirty, session.deleted) if isinstance(o, Audited)]
        if touched and not session.info.get("allow_unaudited"):
            raise RuntimeError(f"write to audited model outside the command bus: {type(touched[0]).__name__}")
        return
    for obj in session.new:
        if isinstance(obj, Audited):
            ctx._record(obj, "create", _diff(obj, "create"))
    for obj in session.dirty:
        if isinstance(obj, Audited) and session.is_modified(obj, include_collections=False):
            diff = _diff(obj, "update")
            if diff:
                ctx._record(obj, "update", diff)
    for obj in session.deleted:
        if isinstance(obj, Audited):
            ctx._record(obj, "delete", _diff(obj, "delete"))
