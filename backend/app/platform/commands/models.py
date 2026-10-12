import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CommandLog(Base):
    """One row per executed command, successful or not."""

    __tablename__ = "command_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(16))  # succeeded | failed
    origin: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None]
    actor_display: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any] | None]
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    parent_command_id: Mapped[uuid.UUID | None]
    depth: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    __table_args__ = (
        # Idempotency only binds successful commands: a failed attempt must be
        # retryable with the same key.
        Index(
            "uq_command_log_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("status = 'succeeded' AND idempotency_key IS NOT NULL"),
        ),
    )
