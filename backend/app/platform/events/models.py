"""Transactional outbox.

Events are inserted in the same transaction as the data change, so a change
can never happen without its event (or vice versa). Each subscriber gets its
own delivery row: one failing subscriber retries alone and never blocks the
others.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None]
    workspace_id: Mapped[uuid.UUID | None]
    command_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    origin: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None]
    depth: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EventDelivery(Base):
    __tablename__ = "event_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"))
    subscriber: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|done|failed|dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_event_deliveries_pending",
            "next_attempt_at",
            postgresql_where=text("status IN ('pending', 'failed')"),
        ),
        Index("ix_event_deliveries_event", "event_id"),
    )
