"""Clients are global: one client can have work in several workspaces.

Facts about the client (ABN, address, portal access, contacts) live here
once. Boards *show* them through mirror columns instead of copying them onto
every item, which is what made the old system drift.
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class Client(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "clients"
    __entity_type__ = "client"

    name: Mapped[str] = mapped_column(String(300), index=True)
    client_type: Mapped[str] = mapped_column(String(40), default="individual")  # individual|company|...
    partner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    referred_by_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", use_alter=True, ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    # Values of client-level custom fields (field_definitions.entity_kind='client')
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)

    __table_args__ = (
        Index(
            "ix_clients_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}
        ),
    )


class ClientEntity(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    """A legal/tax entity under a client (the person, their company, trust...)."""

    __tablename__ = "client_entities"
    __entity_type__ = "client_entity"

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    entity_type: Mapped[str] = mapped_column(String(40), default="individual")
    abn: Mapped[str | None] = mapped_column(String(20))
    acn: Mapped[str | None] = mapped_column(String(20))
    year_end_month: Mapped[int | None] = mapped_column(Integer)  # 1-12
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("client", self.client_id)


class Contact(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "contacts"
    __entity_type__ = "contact"

    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(60))
    role: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_billing: Mapped[bool] = mapped_column(Boolean, default=False)
    is_referrer: Mapped[bool] = mapped_column(Boolean, default=False)
    # Free-form channels: {"wechat_group": "...", "linkedin": "..."}
    channels: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[str | None] = mapped_column(Text)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("client", self.client_id) if self.client_id else None
