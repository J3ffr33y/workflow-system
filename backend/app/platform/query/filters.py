"""One filter language for boards, saved views, automation conditions,
exports and (later) reports.

    {"op": "and", "rules": [
        {"field": "status", "operator": "in", "value": ["waiting_client"]},
        {"field": "lodgement_due", "operator": "before", "value": "today+14d"},
        {"op": "or", "rules": [...]}
    ]}

The caller supplies a resolver that turns a field key into a ``ColumnRef``
(typed SQL expression + kind). This module knows nothing about items.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Date, Numeric, and_, false, func, not_, or_, true
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.time import business_today
from app.platform.fields.types import Kind

OPERATORS: dict[Kind, set[str]] = {
    Kind.TEXT: {"eq", "neq", "contains", "not_contains", "starts_with", "in", "not_in", "empty", "not_empty"},
    Kind.NUMBER: {"eq", "neq", "gt", "gte", "lt", "lte", "between", "in", "empty", "not_empty"},
    Kind.DATE: {
        "eq",
        "neq",
        "before",
        "after",
        "on_or_before",
        "on_or_after",
        "between",
        "empty",
        "not_empty",
    },
    Kind.DATETIME: {"before", "after", "on_or_before", "on_or_after", "between", "empty", "not_empty"},
    Kind.BOOL: {"is_true", "is_false"},
    Kind.REF: {"eq", "neq", "in", "not_in", "empty", "not_empty"},
    Kind.MULTI: {"has_any", "has_all", "has_none", "empty", "not_empty"},
    Kind.JSON: {"empty", "not_empty"},
}


@dataclass(frozen=True)
class ColumnRef:
    """How to filter / sort on one field.

    ``text``: the value as SQL text (NULL when absent); used for emptiness and
    text operators. ``typed``: the value cast to its natural SQL type.
    ``multi``: a JSONB array expression for MULTI kinds.
    ``custom``: full override, e.g. team-role filters implemented as EXISTS.
    """

    # SQL expressions (ColumnElement or ORM attributes); typed loosely because
    # SQLAlchemy's generics do not model InstrumentedAttribute vs ColumnElement.
    key: str
    kind: Kind
    text: Any = None
    typed: Any = None
    multi: Any = None
    custom: Callable[[str, Any], ColumnElement[bool]] | None = None


Resolver = Callable[[str], ColumnRef]

_REL = re.compile(r"^today(?:([+-])(\d+)([dwmy]))?$")


def resolve_date_operand(value: Any) -> date:
    """Accepts 'YYYY-MM-DD', 'today', 'today+14d', 'today-1m', or
    {"relative": "today", "offset": 14, "unit": "d"}."""
    if isinstance(value, dict):
        sign = "-" if int(value.get("offset", 0)) < 0 else "+"
        value = f"today{sign}{abs(int(value.get('offset', 0)))}{value.get('unit', 'd')}"
    if not isinstance(value, str):
        raise ValidationFailed(f"bad date operand {value!r}")
    m = _REL.match(value.strip().lower())
    if m:
        today = business_today()
        if not m.group(1):
            return today
        n = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
        unit = m.group(3)
        if unit == "d":
            return today + timedelta(days=n)
        if unit == "w":
            return today + timedelta(weeks=n)
        from dateutil.relativedelta import relativedelta

        return today + (relativedelta(months=n) if unit == "m" else relativedelta(years=n))
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationFailed(f"bad date operand {value!r}") from None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _typed_operand(kind: Kind, value: Any) -> Any:
    if kind in (Kind.DATE, Kind.DATETIME):
        return resolve_date_operand(value)
    if kind == Kind.NUMBER:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValidationFailed(f"expected a number, got {value!r}") from None
    return value


def _rule(col: ColumnRef, op: str, value: Any) -> ColumnElement[bool]:
    if op not in OPERATORS[col.kind]:
        raise ValidationFailed(f"operator {op} not allowed for field {col.key}", code="bad_operator")
    if col.custom is not None:
        return col.custom(op, value)

    if op in ("empty", "not_empty"):
        if col.kind == Kind.MULTI:
            assert col.multi is not None
            cond = func.coalesce(func.jsonb_array_length(col.multi), 0) == 0
        elif col.kind == Kind.BOOL:
            assert col.typed is not None
            cond = func.coalesce(col.typed, false()).is_(false())
        else:
            assert col.text is not None
            cond = func.coalesce(col.text, "") == ""
        return cond if op == "empty" else not_(cond)

    if col.kind == Kind.BOOL:
        assert col.typed is not None
        return func.coalesce(col.typed, false()).is_(true() if op == "is_true" else false())

    if col.kind == Kind.MULTI:
        assert col.multi is not None
        items = [str(v) for v in _as_list(value)]
        if not items:
            return true()
        if op == "has_any":
            return or_(*[col.multi.contains([v]) for v in items])
        if op == "has_all":
            return col.multi.contains(items)
        return not_(or_(*[func.coalesce(col.multi.contains([v]), false()) for v in items]))

    if op in ("contains", "not_contains", "starts_with"):
        assert col.text is not None
        needle = str(value or "").replace("%", r"\%").replace("_", r"\_")
        pattern = f"{needle}%" if op == "starts_with" else f"%{needle}%"
        cond = col.text.ilike(pattern)
        return or_(not_(cond), col.text.is_(None)) if op == "not_contains" else cond

    expr = col.typed if col.typed is not None else col.text
    assert expr is not None
    if op in ("in", "not_in"):
        vals = [_typed_operand(col.kind, v) for v in _as_list(value)]
        if not vals:
            return true() if op == "not_in" else false()
        cond = expr.in_(vals)
        return or_(not_(cond), expr.is_(None)) if op == "not_in" else cond
    if op == "between":
        lo, hi = _as_list(value) + [None, None][: max(0, 2 - len(_as_list(value)))]
        parts = []
        if lo is not None:
            parts.append(expr >= _typed_operand(col.kind, lo))
        if hi is not None:
            parts.append(expr <= _typed_operand(col.kind, hi))
        return and_(*parts) if parts else true()

    operand = _typed_operand(col.kind, value)
    if col.kind == Kind.DATETIME:
        expr = func.date(func.timezone(get_settings().business_timezone, expr))
    match op:
        case "eq":
            return expr == operand
        case "neq":
            return or_(expr != operand, expr.is_(None))
        case "gt" | "after":
            return expr > operand
        case "gte" | "on_or_after":
            return expr >= operand
        case "lt" | "before":
            return expr < operand
        case "lte" | "on_or_before":
            return expr <= operand
    raise ValidationFailed(f"unsupported operator {op}")


def compile_filter(tree: dict[str, Any] | None, resolve: Resolver) -> ColumnElement[bool]:
    if not tree:
        return true()
    if "rules" in tree:
        op = tree.get("op", "and")
        parts = [compile_filter(r, resolve) for r in tree["rules"]]
        if not parts:
            return true()
        if op == "and":
            return and_(*parts)
        if op == "or":
            return or_(*parts)
        raise ValidationFailed(f"bad group op {op}")
    field = tree.get("field")
    operator = tree.get("operator")
    if not field or not operator:
        raise ValidationFailed("filter rule needs field and operator")
    return _rule(resolve(field), operator, tree.get("value"))


def jsonb_column(key: str, kind: Kind, data_col: Any) -> ColumnRef:
    """ColumnRef for a value stored in a JSONB ``data`` column."""
    raw = data_col[key]
    text_expr = raw.astext
    typed: ColumnElement[Any] | None
    if kind == Kind.NUMBER:
        typed = text_expr.cast(Numeric)
    elif kind == Kind.DATE:
        typed = text_expr.cast(Date)
    elif kind == Kind.DATETIME:
        from sqlalchemy import DateTime

        typed = text_expr.cast(DateTime(timezone=True))
    elif kind == Kind.BOOL:
        typed = raw.as_boolean()
    else:
        typed = text_expr
    return ColumnRef(
        key=key, kind=kind, text=text_expr, typed=typed, multi=raw if kind == Kind.MULTI else None
    )
