"""Read-only description of how the system stores its data.

Built from the live SQLAlchemy metadata rather than a hand-written document,
so the "data structure" page cannot drift from the real schema. It describes
shape only: table and column definitions, never row contents.
"""

from typing import Any

from sqlalchemy import Column, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql

from app.core.db import Base
from app.platform.audit.models import Audited

_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


def _module_of(cls: type) -> str:
    # "app.modules.items.models" -> "items"; anything under app.platform is
    # infrastructure the business modules share, so it is one group.
    parts = cls.__module__.split(".")
    if parts[:2] == ["app", "modules"] and len(parts) > 2:
        return parts[2]
    return "platform"


def _doc(cls: type) -> str | None:
    doc = cls.__dict__.get("__doc__")
    if not doc:
        return None
    return doc.strip().split("\n\n")[0].replace("\n", " ").strip() or None


def _column(col: Column[Any], unique_cols: set[str]) -> dict[str, Any]:
    fks = [
        {
            "table": fk.column.table.name,
            "column": fk.column.name,
            "on_delete": fk.ondelete,
        }
        for fk in col.foreign_keys
    ]
    return {
        "name": col.name,
        "type": col.type.compile(dialect=_DIALECT),
        "nullable": bool(col.nullable),
        "primary_key": bool(col.primary_key),
        "unique": bool(col.unique) or col.name in unique_cols,
        "indexed": bool(col.index),
        "has_default": col.default is not None or col.server_default is not None,
        "references": fks[0] if fks else None,
    }


def _table(cls: type, table: Table) -> dict[str, Any]:
    # Single-column unique constraints read as "unique" on the column; the
    # composite ones are listed separately because they carry business rules
    # (e.g. one field key per workspace and entity kind).
    single_unique: set[str] = set()
    composite_unique: list[list[str]] = []
    for c in table.constraints:
        if isinstance(c, UniqueConstraint):
            names = [col.name for col in c.columns]
            if len(names) == 1:
                single_unique.add(names[0])
            else:
                composite_unique.append(names)
    for ix in table.indexes:
        names = [col.name for col in ix.columns]
        if ix.unique and len(names) > 1:
            composite_unique.append(names)
        elif ix.unique and len(names) == 1:
            single_unique.add(names[0])
    # Mixins put ``id`` after the model's own columns; readers expect the key first.
    ordered = sorted(table.columns, key=lambda col: not col.primary_key)
    columns = [_column(col, single_unique) for col in ordered]
    column_names = {c["name"] for c in columns}
    return {
        "name": table.name,
        "module": _module_of(cls),
        "model": cls.__name__,
        "description": _doc(cls),
        "entity_type": getattr(cls, "__entity_type__", None),
        "audited": issubclass(cls, Audited),
        "soft_delete": "deleted_at" in column_names,
        "has_custom_data": "data" in column_names,
        "columns": columns,
        "unique_together": composite_unique,
        "indexes": sorted(
            ({"name": str(ix.name), "columns": [col.name for col in ix.columns]} for ix in table.indexes),
            key=lambda ix: ix["name"],
        ),
    }


def data_model() -> list[dict[str, Any]]:
    """Every mapped table, grouped-ready by module, sorted by module then name."""
    tables = [
        _table(m.class_, m.local_table) for m in Base.registry.mappers if isinstance(m.local_table, Table)
    ]
    return sorted(tables, key=lambda t: (t["module"], t["name"]))
