"""Due-date arithmetic, checked against the old Smart Board behaviour.

Expected values come from SmartAccounting's custom/project.py
(_roll_date_by_frequency, _resolve_special_quarterly_bas_ias_due_date,
_defer_date_if_in_bas_quarter, date_approaching). No database needed.
"""

from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from app.modules.automations.dates import (
    DEFAULT_ATO_QUARTERLY_DUE_DATES,
    add_period,
    clean_quarterly_table,
    lead_delta,
    next_quarterly_due,
    skip_bas_month,
    skip_bas_month_number,
)

M1 = relativedelta(months=1)


@pytest.mark.parametrize(
    ("start", "delta", "expected"),
    [
        (date(2026, 4, 30), M1, date(2026, 5, 31)),  # month end stays month end
        (date(2026, 1, 31), M1, date(2026, 2, 28)),
        (date(2028, 1, 31), M1, date(2028, 2, 29)),  # leap year
        (date(2026, 2, 28), M1, date(2026, 3, 31)),  # 28 Feb is a month end
        (date(2026, 1, 15), M1, date(2026, 2, 15)),
        (date(2026, 9, 30), relativedelta(months=3), date(2026, 12, 31)),
        (date(2026, 6, 30), relativedelta(months=6), date(2026, 12, 31)),
        (date(2028, 2, 29), relativedelta(years=1), date(2029, 2, 28)),
        (date(2026, 4, 30), relativedelta(weeks=2), date(2026, 5, 14)),  # weeks: plain addition
        (date(2026, 6, 30), relativedelta(days=1), date(2026, 7, 1)),
    ],
)
def test_add_period_keeps_month_end(start: date, delta: relativedelta, expected: date) -> None:
    assert add_period(start, delta) == expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (date(2026, 3, 1), date(2026, 5, 26)),
        (date(2026, 5, 26), date(2026, 8, 25)),  # on a table date: move to the next one
        (date(2026, 10, 28), date(2026, 11, 25)),
        (date(2027, 5, 24), date(2027, 5, 25)),
    ],
)
def test_next_quarterly_due_follows_table(current: date, expected: date) -> None:
    assert next_quarterly_due(current, DEFAULT_ATO_QUARTERLY_DUE_DATES) == (expected, "")


def test_next_quarterly_due_stops_at_end_of_table() -> None:
    nxt, message = next_quarterly_due(date(2027, 5, 25), DEFAULT_ATO_QUARTERLY_DUE_DATES)
    assert nxt is None
    assert "FY 2026-27 Q3" in message and "25 May 2027" in message


def test_next_quarterly_due_with_empty_table() -> None:
    nxt, message = next_quarterly_due(date(2026, 1, 1), [])
    assert nxt is None and message


def test_clean_quarterly_table() -> None:
    rows = [
        {"label": "Q2", "due_date": "2027-02-28"},
        {"label": "Q1", "due_date": "2026-11-25"},
        {"label": "Q1", "due_date": "2026-11-25"},  # duplicate
        {"label": "", "due_date": "2027-05-25"},  # no label
        {"label": "bad", "due_date": "28/02/2027"},  # not ISO
        "junk",
    ]
    assert clean_quarterly_table(rows) == [
        {"label": "Q1", "due_date": "2026-11-25"},
        {"label": "Q2", "due_date": "2027-02-28"},
    ]
    assert clean_quarterly_table(None) == []


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 7, 31), date(2026, 8, 31)),
        (date(2026, 10, 21), date(2026, 11, 21)),
        (date(2027, 1, 31), date(2027, 2, 28)),
        (date(2026, 8, 21), date(2026, 8, 21)),
    ],
)
def test_skip_bas_month(d: date, expected: date) -> None:
    assert skip_bas_month(d) == expected


def test_skip_bas_month_number() -> None:
    assert [skip_bas_month_number(m) for m in range(1, 13)] == [2, 2, 3, 5, 5, 6, 8, 8, 9, 11, 11, 12]


def test_lead_delta_forms() -> None:
    assert lead_delta({"amount": 2, "unit": "w"}) == relativedelta(weeks=2)
    assert lead_delta({"months": 1, "weeks": 2, "days": 3}) == relativedelta(months=1, days=17)
    assert lead_delta({"months": 0}) == relativedelta()
    with pytest.raises(ValueError):
        lead_delta({"amount": 1, "unit": "fortnight"})
