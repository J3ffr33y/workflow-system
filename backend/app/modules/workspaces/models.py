"""The configurable shape of the business.

A workspace is a product line (Accounting, Grants, later CRM...). Everything
that differs between lines is data here, not code: which fields exist, which
statuses, which team roles, which boards.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import ARRAY, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class Workspace(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "workspaces"
    __entity_type__ = "workspace"

    key: Mapped[str] = mapped_column(String(50), unique=True)  # immutable, e.g. "grants"
    name: Mapped[str] = mapped_column(String(100))
    item_label: Mapped[str] = mapped_column(String(50), default="Project")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Feature switches and behaviour knobs, e.g. {"rollover": {"default": "next_period"}}
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)

    def audit_workspace_id(self) -> uuid.UUID | None:
        return self.id


class WorkspaceMembership(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "workspace_memberships"
    __entity_type__ = "workspace_membership"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # WorkspaceRole

    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("user", self.user_id)


class FieldDefinition(IdMixin, TimestampMixin, Audited, Base):
    """A custom field on an entity kind within a workspace.

    ``entity_kind``: item | task | client | entity | contact. Client-level
    fields use the workspace that "owns" them but are visible everywhere.
    ``key`` is immutable once created; ``label`` may change freely.
    """

    __tablename__ = "field_definitions"
    __entity_type__ = "field_definition"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    entity_kind: Mapped[str] = mapped_column(String(20), default="item")
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[str | None] = mapped_column(String(60))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # Rollover default for this field: carry | clear | add_year
    rollover: Mapped[str] = mapped_column(String(20), default="carry")
    # Undo / activity can be switched off for machine-maintained fields (e.g. highlight)
    track_changes: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("workspace_id", "entity_kind", "key"),)


class Status(IdMixin, TimestampMixin, Audited, Base):
    """A status option. ``category`` gives statuses shared meaning across
    workspaces so reports and rules can say "anything done" or "anything
    waiting" without knowing every label."""

    __tablename__ = "statuses"
    __entity_type__ = "status"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(10), default="item")  # item | task
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(20), default="gray")
    category: Mapped[str] = mapped_column(String(20), default="todo")  # todo|active|waiting|done|cancelled
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("workspace_id", "scope", "key"),)


class MemberRole(IdMixin, TimestampMixin, Audited, Base):
    """Team roles on an item (Preparer, Manager, Partner, Salesperson...)."""

    __tablename__ = "member_roles"
    __entity_type__ = "member_role"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)
    allow_multiple: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("workspace_id", "key"),)


class FiscalYear(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "fiscal_years"
    __entity_type__ = "fiscal_year"

    label: Mapped[str] = mapped_column(String(30), unique=True)  # "2025-2026"
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)


class Board(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    """A board within a workspace.

    Accounting: one board per job type (ITR, BAS...). Grants: one per FY.
    ``period_fiscal_year_id`` lets rollover find "the next board" by fiscal
    year instead of parsing names.

    ``settings`` (validated by the workspaces module):
      {"fields": [keys enabled on this board, ordered] | null (= all),
       "statuses": [status keys allowed] | null (= all),
       "pinned_left": ["client"]}
    """

    __tablename__ = "boards"
    __entity_type__ = "board"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    period_fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fiscal_years.id"))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)


class LookupList(IdMixin, TimestampMixin, Audited, Base):
    """Managed master data: Software, Company, Referral source, Industry..."""

    __tablename__ = "lookup_lists"
    __entity_type__ = "lookup_list"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    is_hierarchical: Mapped[bool] = mapped_column(Boolean, default=False)


class LookupValue(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "lookup_values"
    __entity_type__ = "lookup_value"

    list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lookup_lists.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lookup_values.id"))
    label: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("list_id", "label"),)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("lookup_list", self.list_id)
