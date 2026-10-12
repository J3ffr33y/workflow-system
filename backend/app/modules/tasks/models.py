import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class Task(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "tasks"
    __entity_type__ = "task"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[str | None] = mapped_column(String(20))
    due_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fiscal_years.id"))
    period: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("item", self.item_id)


class TaskMember(IdMixin, Audited, Base):
    __tablename__ = "task_members"
    __entity_type__ = "task_member"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role_key: Mapped[str] = mapped_column(String(64))
    assigned_date: Mapped[date | None] = mapped_column(Date)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("task", self.task_id)
