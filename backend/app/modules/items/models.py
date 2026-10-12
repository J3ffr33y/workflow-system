"""Items: one row on a board (the old ERPNext ``Project``)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class Item(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    """Core columns are those business logic depends on. Everything else is in
    ``data`` and validated by the workspace's field definitions.

    Never mutate ``data`` in place: assign a new dict (``set_data``), otherwise
    the change is invisible to SQLAlchemy and to the audit trail.
    """

    __tablename__ = "items"
    __entity_type__ = "item"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    board_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("boards.id"), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("client_entities.id"))
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fiscal_years.id"))
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str | None] = mapped_column(String(64))
    due_date: Mapped[date | None] = mapped_column(Date)

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    # manual | automation | client_archive | board_archived | rollover
    archive_source: Mapped[str | None] = mapped_column(String(32))
    archive_ref: Mapped[str | None] = mapped_column(String(200))
    archived_at: Mapped[datetime | None]

    # Visual flag set by automations (Grants deadline highlight).
    highlight_color: Mapped[str | None] = mapped_column(String(20))
    highlight_rule_id: Mapped[uuid.UUID | None]

    rolled_from_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index(
            "ix_items_board_active", "board_id", "is_archived", postgresql_where=text("deleted_at IS NULL")
        ),
        Index("ix_items_data_gin", "data", postgresql_using="gin"),
        # Fuzzy name search (needs the pg_trgm extension, created in migration 0001).
        Index("ix_items_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
    )

    def set_data(self, key: str, value: Any) -> None:
        new = dict(self.data or {})
        if value is None or value == [] or value == {}:
            new.pop(key, None)
        else:
            new[key] = value
        self.data = new


class ItemMember(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "item_members"
    __entity_type__ = "item_member"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role_key: Mapped[str] = mapped_column(String(64))
    assigned_date: Mapped[date | None] = mapped_column(Date)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("item", self.item_id)
