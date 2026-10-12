"""Data migration bookkeeping.

A migration run goes: draft -> analysed -> validated -> committed
(-> rolled_back). Rows are staged with their raw source values, the
normalised values and any issues, so a run can be inspected and re-run.
``external_refs`` maps legacy ids (ERPNext names, CSV row keys) to new ids;
it makes re-imports idempotent and will later power two-way sync with other
systems (Xero, mailboxes, drives).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.platform.audit.models import Audited


class ExternalRef(IdMixin, Audited, Base):
    __tablename__ = "external_refs"
    __entity_type__ = "external_ref"

    system: Mapped[str] = mapped_column(String(40))  # erpnext | csv | xero ...
    external_type: Mapped[str] = mapped_column(String(64))  # Project | Customer | csv:grants
    external_id: Mapped[str] = mapped_column(String(300))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (UniqueConstraint("system", "external_type", "external_id"),)


class MigrationRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "migration_runs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    board_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("boards.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(20))  # csv | erpnext
    source_meta: Mapped[dict[str, Any]] = mapped_column(default=dict)  # filename, encoding, headers
    mapping: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
    batch_id: Mapped[uuid.UUID | None]  # command batch used at commit; enables rollback
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    error: Mapped[str | None] = mapped_column(Text)


class MigrationRow(Base):
    __tablename__ = "migration_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"))
    row_no: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(300))
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)
    normalized: Mapped[dict[str, Any]] = mapped_column(default=dict)
    issues: Mapped[list[Any]] = mapped_column(default=list)
    outcome: Mapped[str | None] = mapped_column(String(20))  # created | updated | skipped | error
    item_id: Mapped[uuid.UUID | None]

    __table_args__ = (Index("ix_migration_rows_run", "run_id", "row_no"),)
