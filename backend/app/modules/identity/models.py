import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.platform.audit.models import Audited


class User(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "users"
    __entity_type__ = "user"
    __audit_exclude__ = frozenset({"created_at", "updated_at", "password_hash", "last_login_at"})

    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # Short names and spellings used in legacy data ("Win", "CL", "Jean Ren").
    # Used by imports and @mentions to resolve people.
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    password_hash: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Placeholder users are created by migrations for people who appear in
    # legacy data but have no login yet. They can be assigned, not log in.
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(10), default="en")
    preferences: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_login_at: Mapped[datetime | None]


class AuthSession(Base):
    """Server-side session. The cookie carries a random token; only its hash
    is stored, so a database leak does not leak live sessions."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None]


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320))
    ip: Mapped[str | None] = mapped_column(String(64))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (Index("ix_login_attempts_email_time", "email", "created_at"),)
