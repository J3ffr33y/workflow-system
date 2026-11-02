"""R&D report (RDTI) data, attached to a Grants item. See docs/RDTI.md."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class RdtiActivity(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "rdti_activities"
    __entity_type__ = "rdti_activity"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    code: Mapped[str] = mapped_column(String(20))  # e.g. "CA1", "SA1"
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))  # core | supporting
    supports_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rdti_activities.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("item", self.item_id)


class RdtiChunk(IdMixin, Base):
    """A citable passage of an uploaded document. Derived from the file, so
    not audited one by one: the add_document command's audit names the file
    and the passage count."""

    __tablename__ = "rdti_chunks"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    file_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_versions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(60))
    bbox: Mapped[list[Any] | None] = mapped_column(default=None)
    text: Mapped[str] = mapped_column(Text)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rdti_activities.id", ondelete="SET NULL"), index=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (Index("ix_rdti_chunks_file_seq", "file_version_id", "seq"),)


class RdtiAssessment(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "rdti_assessments"
    __entity_type__ = "rdti_assessment"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rdti_activities.id", ondelete="CASCADE"), index=True
    )
    element: Mapped[str] = mapped_column(String(40))
    coverage: Mapped[str] = mapped_column(String(20))  # sufficient | partial | missing
    rationale: Mapped[str] = mapped_column(Text, default="")
    summary_only: Mapped[bool] = mapped_column(Boolean, default=False)
    chunk_ids: Mapped[list[Any]] = mapped_column(default=list)
    source: Mapped[str] = mapped_column(String(10))  # ai | human
    rule_version: Mapped[str] = mapped_column(String(20))

    __table_args__ = (UniqueConstraint("activity_id", "element"),)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("rdti_activity", self.activity_id)


class RdtiChecklistItem(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "rdti_checklist_items"
    __entity_type__ = "rdti_checklist_item"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rdti_activities.id", ondelete="CASCADE")
    )
    element: Mapped[str | None] = mapped_column(String(40))
    question: Mapped[str] = mapped_column(Text)
    preferred: Mapped[str] = mapped_column(Text, default="")
    alternatives: Mapped[list[Any]] = mapped_column(default=list)
    example: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | sent | received | closed
    received_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("item", self.item_id)


class RdtiReportSection(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "rdti_report_sections"
    __entity_type__ = "rdti_report_section"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rdti_activities.id", ondelete="CASCADE"), index=True
    )
    element: Mapped[str] = mapped_column(String(40))
    heading: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("item", self.item_id)


class RdtiClaim(IdMixin, TimestampMixin, Audited, Base):
    """A span of a report section that states one thing. Offsets are
    character positions in the section body."""

    __tablename__ = "rdti_claims"
    __entity_type__ = "rdti_claim"

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rdti_report_sections.id", ondelete="CASCADE"), index=True
    )
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # supported | needs_review | polish | unsupported
    status: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(10))  # ai | human
    note: Mapped[str | None] = mapped_column(Text)
    fact_warning: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None]

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("rdti_report_section", self.section_id)


class RdtiCitation(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "rdti_citations"
    __entity_type__ = "rdti_citation"

    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rdti_claims.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rdti_chunks.id", ondelete="CASCADE"), index=True)
    quote: Mapped[str] = mapped_column(Text)
    # Position of the quote inside the chunk text; null when it could not be
    # found verbatim (then the citation is not trusted).
    quote_start: Mapped[int | None] = mapped_column(Integer)
    quote_end: Mapped[int | None] = mapped_column(Integer)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    support: Mapped[str] = mapped_column(String(20), default="supports")  # supports | partial | contradicts
    rationale: Mapped[str | None] = mapped_column(Text)
    file_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_versions.id", ondelete="CASCADE"))

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("rdti_claim", self.claim_id)
