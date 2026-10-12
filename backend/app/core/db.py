"""Database engines, sessions and the declarative base.

Two engines on purpose:

* ``write_engine`` is used only by the command bus (and by the worker's
  bookkeeping of its own queue tables).
* ``read_engine`` opens every transaction READ ONLY at the PostgreSQL level.
  Query code that accidentally writes fails loudly instead of creating
  un-audited changes.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        uuid.UUID: UUID(as_uuid=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


_write_engine: Engine | None = None
_read_engine: Engine | None = None


def write_engine() -> Engine:
    global _write_engine
    if _write_engine is None:
        _write_engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)
    return _write_engine


def read_engine() -> Engine:
    global _read_engine
    if _read_engine is None:
        _read_engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=10,
            connect_args={"options": "-c default_transaction_read_only=on"},
        )
    return _read_engine


def reset_engines() -> None:
    """Dispose cached engines (tests switch databases)."""
    global _write_engine, _read_engine
    for e in (_write_engine, _read_engine):
        if e is not None:
            e.dispose()
    _write_engine = _read_engine = None


def _write_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=write_engine(), expire_on_commit=False, autoflush=True)


def _read_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=read_engine(), expire_on_commit=False, autoflush=False)


@contextmanager
def write_session() -> Iterator[Session]:
    """Only the command bus and queue bookkeeping may use this."""
    session = _write_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def read_session() -> Iterator[Session]:
    session = _read_sessionmaker()()
    try:
        yield session
    finally:
        # close() (not rollback()) so loaded objects stay readable after the
        # block; the pool rolls the connection back on return anyway.
        session.close()


def get_read_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with read_session() as s:
        yield s
