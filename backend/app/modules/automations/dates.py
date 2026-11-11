"""Date arithmetic for automations, matching the old Smart Board rules.

Kept free of database access so the rules can be tested on their own. Each
rule below reproduces a behaviour of SmartAccounting's ``custom/project.py``
that staff rely on; the comments name the original function.
"""

import calendar
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

# Months already covered by a quarterly BAS lodgement. A monthly IAS that lands
# on one of them is pushed one month later so the two are not scheduled side
# by side (old: _BAS_QUARTER_MONTHS / _defer_date_if_in_bas_quarter).
BAS_QUARTER_MONTHS = frozenset({1, 4, 7, 10})

# Board-level rule keys (boards.settings["due_date_rules"], a list).
RULE_ATO_QUARTERLY = "ato_quarterly"
RULE_SKIP_BAS_MONTHS = "skip_bas_months"
DUE_DATE_RULES = (RULE_ATO_QUARTERLY, RULE_SKIP_BAS_MONTHS)

# The old system's built-in ATO quarterly table, used until an admin edits it
# (old: DEFAULT_QUARTERLY_DUE_DATE_RULES in api/board_settings.py).
DEFAULT_ATO_QUARTERLY_DUE_DATES: list[dict[str, str]] = [
    {"label": "FY 2025-26 Q3", "due_date": "2026-05-26"},
    {"label": "FY 2025-26 Q4", "due_date": "2026-08-25"},
    {"label": "FY 2026-27 Q1", "due_date": "2026-11-25"},
    {"label": "FY 2026-27 Q2", "due_date": "2027-02-28"},
    {"label": "FY 2026-27 Q3", "due_date": "2027-05-25"},
]


def is_month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_period(d: date, delta: relativedelta) -> date:
    """``d + delta``, keeping month-end dates at month end.

    30 April + 1 month is 31 May, not 30 May: a lodgement due "at the end of
    the month" must stay there (old: _roll_date_by_frequency EOM rule). Only
    whole-month steps keep month end; week and day steps are plain addition.
    """
    result = d + delta
    month_step = bool(delta.months or delta.years) and not (delta.days or delta.weeks)
    if month_step and is_month_end(d):
        return month_end(result)
    return result


def skip_bas_month(d: date) -> date:
    """Push a date landing in a BAS quarter month one month on (month-end safe)."""
    if d.month not in BAS_QUARTER_MONTHS:
        return d
    return add_period(d, relativedelta(months=1))


def skip_bas_month_number(month: int) -> int:
    return month % 12 + 1 if month in BAS_QUARTER_MONTHS else month


def clean_quarterly_table(rows: Any) -> list[dict[str, str]]:
    """Validate an admin-edited table: drop blanks, bad dates and duplicates; sort by date."""
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label") or "").strip()
        raw = str(row.get("due_date") or "").strip()
        if not label or not raw:
            continue
        try:
            due = date.fromisoformat(raw).isoformat()
        except ValueError:
            continue
        if (label, due) in seen:
            continue
        seen.add((label, due))
        out.append({"label": label, "due_date": due})
    return sorted(out, key=lambda r: r["due_date"])


def next_quarterly_due(current: date, table: Iterable[Mapping[str, str]]) -> tuple[date | None, str]:
    """The first table date after ``current``.

    Past the last date the old system refused to guess and told the user the
    table needs extending; we return ``(None, message)`` the same way (old:
    _resolve_special_quarterly_bas_ias_due_date).
    """
    rows = clean_quarterly_table(list(table))
    if not rows:
        return None, "no ATO quarterly due dates are configured"
    for r in rows:
        due = date.fromisoformat(r["due_date"])
        if current < due:
            return due, ""
    last = rows[-1]
    last_date = date.fromisoformat(last["due_date"])
    return None, (
        f"the quarterly due-date table cannot go beyond {last['label']} "
        f"({last_date.day} {last_date:%B %Y}); add the next quarters in Settings"
    )


def lead_delta(offset: Mapping[str, Any]) -> relativedelta:
    """An offset as a relativedelta.

    Accepts the single-unit form ``{"amount": 1, "unit": "m"}`` and the Grants
    form ``{"months": 1, "weeks": 2, "days": 3}`` (old: date_approaching).
    """
    if any(k in offset for k in ("months", "weeks", "days")):
        return relativedelta(
            months=int(offset.get("months") or 0),
            weeks=int(offset.get("weeks") or 0),
            days=int(offset.get("days") or 0),
        )
    amount = int(offset.get("amount") or 0)
    match offset.get("unit", "d"):
        case "d" | "day" | "days":
            return relativedelta(days=amount)
        case "w" | "week" | "weeks":
            return relativedelta(weeks=amount)
        case "m" | "month" | "months":
            return relativedelta(months=amount)
        case "q" | "quarter" | "quarters":
            return relativedelta(months=3 * amount)
        case "y" | "year" | "years":
            return relativedelta(years=amount)
    raise ValueError(f"unknown unit {offset.get('unit')}")
