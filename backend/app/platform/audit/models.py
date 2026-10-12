"""Audit trail: one row per entity touched by a command.

This table is the single source for activity feeds, undo, automation run
change-lists and migration rollback. It is append-only; the only column ever
updated is ``reverted_by_command_id``.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import BigInteger, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Audited:
    """Mixin marker. Every insert/update/delete of an Audited model is captured
    automatically at flush time, so no handler can forget to log a change.

    Subclasses set ``__entity_type__`` and may override ``audit_parent`` so the
    change also shows up in the parent's activity (e.g. a team member change
    appears on the item).
    """

    __entity_type__: ClassVar[str]
    __audit_exclude__: ClassVar[frozenset[str]] = frozenset({"created_at", "updated_at", "version"})

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return None

    def audit_workspace_id(self) -> uuid.UUID | None:
        return getattr(self, "workspace_id", None)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    command_id: Mapped[uuid.UUID] = mapped_column(index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    origin: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_display: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID]
    parent_type: Mapped[str | None] = mapped_column(String(64))
    parent_id: Mapped[uuid.UUID | None]
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    op: Mapped[str] = mapped_column(String(16))  # create | update | delete
    # [{"field": "status", "before": "a", "after": "b"}]; JSONB keys appear as "data.<key>"
    changes: Mapped[list[Any]] = mapped_column(default=list)
    reverted_by_command_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", "id"),
        Index("ix_audit_parent", "parent_type", "parent_id", "id"),
    )
