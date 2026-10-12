import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class Comment(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    """An update / comment on any entity (item, client, task...)."""

    __tablename__ = "comments"
    __entity_type__ = "comment"

    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID]
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id"))
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Imported comments keep the original author's name when no user matches.
    author_display: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    edited_at: Mapped[datetime | None]

    __table_args__ = (Index("ix_comments_entity", "entity_type", "entity_id", "created_at"),)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return (self.entity_type, self.entity_id)


class Notification(Base):
    """In-app notification. Not audited: it is itself a consequence of an
    audited change. Delivery to other channels (email, Teams) is a separate
    subscriber reading the same events."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))  # mention | automation | assignment ...
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None]
    workspace_id: Mapped[uuid.UUID | None]
    actor_display: Mapped[str | None] = mapped_column(String(200))
    source_event_id: Mapped[int | None]
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "read_at", "created_at"),
        # One notification per (event, user, kind): worker retries stay idempotent.
        Index("uq_notifications_event_user", "source_event_id", "user_id", "kind", unique=True),
    )
