import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class WebhookEndpoint(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    """A URL that receives business events as signed JSON POSTs."""

    __tablename__ = "webhook_endpoints"
    __entity_type__ = "webhook_endpoint"
    __audit_exclude__ = frozenset({"created_at", "updated_at", "secret"})

    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2000))
    # Stored in clear because we must be able to sign with it. Never returned
    # by queries; shown once on create / rotate.
    secret: Mapped[str] = mapped_column(String(128))
    # fnmatch patterns over event types, e.g. ["item.*", "comment.created"].
    event_types: Mapped[list[str]] = mapped_column(ARRAY(String(80)))
    # None: events from every workspace (and global ones such as clients).
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    # Quiet changes are undo, migration and cascades. Most receivers want only
    # what people and automations did, so they are skipped unless asked for.
    include_quiet: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class WebhookDelivery(Base):
    """One attempt record per (endpoint, event). Queue bookkeeping like
    ``event_deliveries``, so it is written outside the command bus (ADR-0010)."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[int] = mapped_column(BigInteger, index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16))  # done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    response_status: Mapped[int | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("endpoint_id", "event_id"),)
