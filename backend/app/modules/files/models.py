"""Uploaded files, attached to an item or a client.

A file keeps every version: re-uploading replaces what is current but old
versions stay, because evidence and report citations point at the exact
version they were checked against.
"""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.platform.audit.models import Audited


class StoredFile(IdMixin, TimestampMixin, SoftDeleteMixin, Audited, Base):
    __tablename__ = "files"
    __entity_type__ = "file"

    owner_type: Mapped[str] = mapped_column(String(20))  # item | client
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    # What the file is for inside its owner, e.g. "rdti_evidence".
    purpose: Mapped[str] = mapped_column(String(40), default="general")
    current_version: Mapped[int] = mapped_column(Integer, default=1)

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return (self.owner_type, self.owner_id)


class FileVersion(IdMixin, TimestampMixin, Audited, Base):
    __tablename__ = "file_versions"
    __entity_type__ = "file_version"

    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    # Path relative to settings.upload_dir; never a user-supplied name.
    storage_key: Mapped[str] = mapped_column(String(200))
    original_name: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    def audit_parent(self) -> tuple[str, uuid.UUID] | None:
        return ("file", self.file_id)
