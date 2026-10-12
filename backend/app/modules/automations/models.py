import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class AutomationRule(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    """When <trigger> and <conditions>, do <actions>.

    trigger:    {"type": "status_changed", "config": {"to": ["done"]}}
    conditions: filter tree (same language as board filters)
    actions:    [{"type": "set_status", "config": {"status": "not_started"}}, ...]
    board_ids:  limit to these boards; empty = all boards in the workspace
    """

    __tablename__ = "automation_rules"
    __entity_type__ = "automation_rule"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger: Mapped[dict[str, Any]] = mapped_column(default=dict)
    conditions: Mapped[dict[str, Any] | None]
    actions: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    board_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    __audit_exclude__ = frozenset({"created_at", "updated_at", "run_count", "last_run_at"})


class AutomationRun(Base):
    """One evaluation of a rule against one item. The field-level changes are
    in the audit trail under ``command_id``; they are not duplicated here."""

    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    trigger_source: Mapped[str] = mapped_column(String(20))  # event | schedule | manual | dry_run
    event_id: Mapped[int | None] = mapped_column(BigInteger)
    # For schedule triggers: "<rule>:<item>:<yyyy-mm-dd>" so a rule fires at
    # most once per item per business day no matter how often the job runs.
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))  # succeeded | failed | skipped
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)  # matched conditions, actions attempted
    command_id: Mapped[uuid.UUID | None]
    changes_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    __table_args__ = (Index("uq_automation_runs_dedupe", "dedupe_key", unique=True),)
