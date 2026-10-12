"""Convert Python values to JSON-safe primitives for audit, events and APIs."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def to_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")
