"""Field type registry.

Every value stored in a ``data`` JSONB column, and every core column exposed
on a board, has a field type. The type owns:

* ``normalize``   strict validation for API writes -> canonical JSON value
* ``parse_text``  tolerant parsing of human / spreadsheet text (imports, paste)
* ``to_text``     plain-text rendering for CSV export
* ``kind``        drives which filter operators and SQL casts apply

The frontend has a mirror registry keyed by the same ``key``. Adding a field
type = one class here + one component set there; boards, filters, bulk edit,
export, automations and migration then support it automatically.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, ClassVar, Protocol

from app.core.time import business_tz


class FieldValueError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_value") -> None:
        super().__init__(message)
        self.code = code


class Kind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    BOOL = "bool"
    REF = "ref"  # single key / id
    MULTI = "multi"  # list of keys / ids
    JSON = "json"  # structured, not filterable generically


class Resolver(Protocol):
    """Lookups a field type needs. Implemented by the items/migration layers."""

    def user_ids(self) -> set[str]: ...
    def find_user(self, text: str) -> str | None: ...
    def lookup_ids(self, list_key: str) -> set[str]: ...
    def find_lookup(self, list_key: str, text: str) -> str | None: ...
    def user_label(self, user_id: str) -> str: ...
    def lookup_label(self, value_id: str) -> str: ...


MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]  # fmt: skip
_MONTH_LOOKUP = {m: i + 1 for i, m in enumerate(MONTHS)} | {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
_EMPTY_MARKERS = {"", "-", "'-", "—", "n/a", "na", "null", "none"}


def clean_text(raw: Any) -> str | None:
    """Undo common spreadsheet artefacts: Excel's leading apostrophe, HTML
    entities from web exports, surrounding whitespace, placeholder dashes."""
    if raw is None:
        return None
    s = str(raw)
    if s.startswith("'"):
        s = s[1:]
    s = (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    s = s.strip()
    return None if s.lower() in _EMPTY_MARKERS else s


def _split_multi(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,\n/]", raw) if p.strip()]


class FieldType:
    key: ClassVar[str]
    kind: ClassVar[Kind]
    label: ClassVar[str]
    editable: ClassVar[bool] = True

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        raise NotImplementedError

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        return None if text is None else self.normalize(text, config, r)

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "" if value is None else str(value)

    def is_empty(self, value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}


# --- text family -----------------------------------------------------------
class TextType(FieldType):
    key = "text"
    kind = Kind.TEXT
    label = "Text"
    default_max = 500

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None:
            return None
        if not isinstance(value, (str, int, float)):
            raise FieldValueError("expected text")
        s = str(value).strip()
        if not s:
            return None
        limit = int(config.get("max_length", self.default_max))
        if len(s) > limit:
            raise FieldValueError(f"longer than {limit} characters", code="too_long")
        return s

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if raw is None:
            return None
        s = str(raw)
        if s.startswith("'"):
            s = s[1:]
        s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
        return self.normalize(s or None, config, r)


class LongTextType(TextType):
    key = "long_text"
    label = "Long text"
    default_max = 20000


class EmailType(TextType):
    key = "email"
    label = "Email"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        s = super().normalize(value, config, r)
        if s is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s):
            raise FieldValueError("not an email address")
        return s.lower() if s else s


class PhoneType(TextType):
    key = "phone"
    label = "Phone"


class UrlType(TextType):
    key = "url"
    label = "URL"
    default_max = 2000


class ColorType(TextType):
    key = "color"
    label = "Colour"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        s = super().normalize(value, config, r)
        if s is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}|[a-z]+", s):
            raise FieldValueError("expected #RRGGBB or a palette name")
        return s


# --- numbers ---------------------------------------------------------------
class NumberType(FieldType):
    key = "number"
    kind = Kind.NUMBER
    label = "Number"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise FieldValueError("expected a number")
        try:
            d = Decimal(str(value).replace(",", "").replace("$", "").replace("%", "").strip())
        except InvalidOperation:
            raise FieldValueError("expected a number") from None
        if not d.is_finite():
            raise FieldValueError("expected a finite number")
        places = config.get("decimals")
        if places is not None:
            d = round(d, int(places))
        return int(d) if d == d.to_integral_value() and places in (None, 0) else float(d)


class MoneyType(NumberType):
    key = "money"
    label = "Money"

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "" if value is None else f"{Decimal(str(value)):.2f}"


class PercentType(NumberType):
    key = "percent"
    label = "Percent"


# --- dates -----------------------------------------------------------------
def parse_date_text(s: str, order: str = "DMY") -> date:
    s = s.strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)  # 20260911
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T].*)?", s)  # 2026/5/15, ISO
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)  # 15/5/2026 (AU default)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y = y + 2000 if y < 100 else y
        day, month = (a, b) if order == "DMY" else (b, a)
        return date(y, month, day)
    m = re.fullmatch(r"(\d{1,2})[ -]([A-Za-z]{3,9})[ -](\d{2,4})", s)  # 15 May 2026
    if m and m[2].lower() in _MONTH_LOOKUP:
        y = int(m[3])
        return date(y + 2000 if y < 100 else y, _MONTH_LOOKUP[m[2].lower()], int(m[1]))
    raise FieldValueError(f"unrecognised date '{s}'", code="bad_date")


class DateType(FieldType):
    key = "date"
    kind = Kind.DATE
    label = "Date"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                raise FieldValueError("expected YYYY-MM-DD", code="bad_date") from None
        raise FieldValueError("expected a date", code="bad_date")

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return None
        try:
            return parse_date_text(text, config.get("date_order", "DMY")).isoformat()
        except ValueError as e:
            raise FieldValueError(str(e), code="bad_date") from None

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        if not value:
            return ""
        d = date.fromisoformat(value)
        return d.strftime("%d/%m/%Y")


class DateTimeType(FieldType):
    key = "datetime"
    kind = Kind.DATETIME
    label = "Date & time"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                raise FieldValueError("expected ISO datetime") from None
        if not isinstance(value, datetime):
            raise FieldValueError("expected a datetime")
        if value.tzinfo is None:
            # Human-entered times are business-local, never UTC.
            value = value.replace(tzinfo=business_tz())
        return value.isoformat()


class MonthType(FieldType):
    """A month of the year (1-12), e.g. year end or target month."""

    key = "month"
    kind = Kind.NUMBER
    label = "Month"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            v = value.strip().lower()
            if v in _MONTH_LOOKUP:
                return _MONTH_LOOKUP[v]
            if v.isdigit():
                value = int(v)
            else:
                raise FieldValueError(f"unknown month '{value}'")
        if isinstance(value, int) and 1 <= value <= 12:
            return value
        raise FieldValueError("expected a month 1-12")

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "" if not value else MONTHS[int(value) - 1].capitalize()


class YearMonthType(FieldType):
    key = "year_month"
    kind = Kind.TEXT  # 'YYYY-MM' sorts and compares correctly as text
    label = "Year & month"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        s = str(value).strip()
        m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
        if m and 1 <= int(m[2]) <= 12:
            return f"{int(m[1]):04d}-{int(m[2]):02d}"
        m = re.fullmatch(r"([A-Za-z]{3,9})[- ']?(\d{2}|\d{4})", s)  # Aug-26, August 2026
        if m and m[1].lower() in _MONTH_LOOKUP:
            y = int(m[2])
            return f"{y + 2000 if y < 100 else y:04d}-{_MONTH_LOOKUP[m[1].lower()]:02d}"
        try:
            d = parse_date_text(s)
            return f"{d.year:04d}-{d.month:02d}"
        except FieldValueError:
            raise FieldValueError(f"unrecognised month '{s}'") from None

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        if not value:
            return ""
        y, m = value.split("-")
        return f"{MONTHS[int(m) - 1][:3].capitalize()}-{y[2:]}"


# --- boolean ---------------------------------------------------------------
class CheckboxType(FieldType):
    key = "checkbox"
    kind = Kind.BOOL
    label = "Checkbox"
    _TRUE = {"true", "yes", "y", "1", "x", "✓", "checked"}
    _FALSE = {"false", "no", "n", "0", "", "unchecked"}

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        raise FieldValueError("expected true/false")

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        s = (clean_text(raw) or "").lower()
        true_values = {v.lower() for v in config.get("true_values", [])} | self._TRUE
        false_values = {v.lower() for v in config.get("false_values", [])} | self._FALSE
        if s in true_values:
            return True
        if s in false_values:
            return False
        raise FieldValueError(f"cannot read '{raw}' as yes/no")

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "Yes" if value else "No"

    def is_empty(self, value: Any) -> bool:
        return not value


# --- options ---------------------------------------------------------------
def _options(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list(config.get("options", []))


def match_option(config: dict[str, Any], text: str) -> str | None:
    t = text.strip().lower()
    for o in _options(config):
        if t in (o["key"].lower(), str(o.get("label", "")).lower()):
            return str(o["key"])
        if t in [a.lower() for a in o.get("aliases", [])]:
            return str(o["key"])
    return None


class SelectType(FieldType):
    key = "select"
    kind = Kind.REF
    label = "Single select"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        keys = {o["key"] for o in _options(config)}
        if value not in keys:
            raise FieldValueError(f"'{value}' is not an option", code="unknown_option")
        return value

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return None
        key = match_option(config, text)
        if key is None:
            raise FieldValueError(f"'{text}' is not an option", code="unknown_option")
        return key

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        for o in _options(config):
            if o["key"] == value:
                return str(o.get("label", value))
        return "" if value is None else str(value)


class MultiSelectType(FieldType):
    key = "multi_select"
    kind = Kind.MULTI
    label = "Multi select"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value in (None, "", []):
            return []
        if not isinstance(value, list):
            raise FieldValueError("expected a list")
        keys = {o["key"] for o in _options(config)}
        bad = [v for v in value if v not in keys]
        if bad:
            raise FieldValueError(f"not options: {bad}", code="unknown_option")
        return list(dict.fromkeys(value))

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return []
        out = []
        for part in _split_multi(text):
            key = match_option(config, part)
            if key is None:
                raise FieldValueError(f"'{part}' is not an option", code="unknown_option")
            out.append(key)
        return list(dict.fromkeys(out))

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        labels = {o["key"]: o.get("label", o["key"]) for o in _options(config)}
        return "; ".join(str(labels.get(v, v)) for v in value or [])


# --- references --------------------------------------------------------------
def _uuid_str(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise FieldValueError("expected an id") from None


class UserType(FieldType):
    key = "user"
    kind = Kind.REF
    label = "Person"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        v = _uuid_str(value)
        if r is not None and v not in r.user_ids():
            raise FieldValueError("unknown user", code="unknown_user")
        return v

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return None
        found = r.find_user(text) if r else None
        if found is None:
            raise FieldValueError(f"no user matches '{text}'", code="unknown_user")
        return found

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "" if not value else (r.user_label(value) if r else str(value))


class UsersType(FieldType):
    key = "users"
    kind = Kind.MULTI
    label = "People"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value in (None, "", []):
            return []
        if not isinstance(value, list):
            raise FieldValueError("expected a list")
        out = [UserType().normalize(v, config, r) for v in value]
        return list(dict.fromkeys(out))

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return []
        return list(dict.fromkeys(UserType().parse_text(p, config, r) for p in _split_multi(text)))

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "; ".join(UserType().to_text(v, config, r) for v in value or [])


class LookupType(FieldType):
    """A value from a managed master-data list (Software, Company, Referral...)."""

    key = "lookup"
    kind = Kind.REF
    label = "Lookup"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value is None or value == "":
            return None
        v = _uuid_str(value)
        if r is not None and v not in r.lookup_ids(config["list"]):
            raise FieldValueError("unknown list value", code="unknown_lookup")
        return v

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return None
        found = r.find_lookup(config["list"], text) if r else None
        if found is None:
            raise FieldValueError(f"'{text}' is not in list {config['list']}", code="unknown_lookup")
        return found

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "" if not value else (r.lookup_label(value) if r else str(value))


class LookupMultiType(FieldType):
    key = "lookup_multi"
    kind = Kind.MULTI
    label = "Lookup (multiple)"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value in (None, "", []):
            return []
        if not isinstance(value, list):
            raise FieldValueError("expected a list")
        return list(dict.fromkeys(LookupType().normalize(v, config, r) for v in value))

    def parse_text(self, raw: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        text = clean_text(raw)
        if text is None:
            return []
        return list(dict.fromkeys(LookupType().parse_text(p, config, r) for p in _split_multi(text)))

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "; ".join(LookupType().to_text(v, config, r) for v in value or [])


# --- structured ------------------------------------------------------------
class PeriodGridType(FieldType):
    """Per-period status (e.g. monthly completion across a fiscal year).

    Value: {"1": "done", "2": "working", ...}; period 1 is the first month of
    the item's fiscal year. Options come from config like a select.
    """

    key = "period_grid"
    kind = Kind.JSON
    label = "Period grid"

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        if value in (None, "", {}):
            return {}
        if not isinstance(value, dict):
            raise FieldValueError("expected an object of period -> option")
        periods = int(config.get("periods", 12))
        keys = {o["key"] for o in _options(config)}
        out: dict[str, str] = {}
        for p, v in value.items():
            if not str(p).isdigit() or not 1 <= int(p) <= periods:
                raise FieldValueError(f"bad period {p}")
            if v in (None, ""):
                continue
            if v not in keys:
                raise FieldValueError(f"'{v}' is not an option", code="unknown_option")
            out[str(int(p))] = v
        return out

    def to_text(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> str:
        return "; ".join(f"{k}:{v}" for k, v in sorted((value or {}).items(), key=lambda kv: int(kv[0])))


class MirrorType(FieldType):
    """Read-only view of a field on a related record (client, entity).

    Keeps one source of truth: e.g. portal access lives on the client and is
    *shown* on every item of that client, instead of being copied around.
    """

    key = "mirror"
    kind = Kind.JSON
    label = "Mirror"
    editable = False

    def normalize(self, value: Any, config: dict[str, Any], r: Resolver | None = None) -> Any:
        raise FieldValueError("mirror fields are read-only", code="read_only")


@dataclass
class FieldTypeRegistry:
    types: dict[str, FieldType]

    def get(self, key: str) -> FieldType:
        try:
            return self.types[key]
        except KeyError:
            raise FieldValueError(f"unknown field type {key}") from None

    def register(self, ft: FieldType) -> None:
        if ft.key in self.types:
            raise ValueError(f"duplicate field type {ft.key}")
        self.types[ft.key] = ft

    def all(self) -> Iterable[FieldType]:
        return self.types.values()


field_types = FieldTypeRegistry({})
for _t in (
    TextType(), LongTextType(), EmailType(), PhoneType(), UrlType(), ColorType(),
    NumberType(), MoneyType(), PercentType(),
    DateType(), DateTimeType(), MonthType(), YearMonthType(),
    CheckboxType(), SelectType(), MultiSelectType(),
    UserType(), UsersType(), LookupType(), LookupMultiType(),
    PeriodGridType(), MirrorType(),
):  # fmt: skip
    field_types.register(_t)
