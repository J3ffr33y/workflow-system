"""The only place that knows what "now" and "today" mean.

Rule: store aware UTC, compute business dates in the business timezone.
A naive datetime written into a timestamptz column is silently off by the
server's offset, so nothing in the codebase should call datetime.now() or
date.today() directly.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

_override_now: datetime | None = None


def utcnow() -> datetime:
    if _override_now is not None:
        return _override_now
    return datetime.now(UTC)


def business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().business_timezone)


def business_today() -> date:
    return utcnow().astimezone(business_tz()).date()


def set_clock(value: datetime | None) -> None:
    """Freeze the clock (tests and automation dry-runs only)."""
    global _override_now
    if value is not None and value.tzinfo is None:
        raise ValueError("clock override must be timezone-aware")
    _override_now = value
