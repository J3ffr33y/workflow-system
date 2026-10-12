"""Where legacy data comes from.

* CSV exports from the old Smart Board (often re-saved by Excel, so the
  encoding may be GBK / GB18030 / CP1252 instead of UTF-8).
* The ERPNext REST API (preferred: complete, typed, stable ids).

Both produce the same thing: a list of flat ``dict[str, Any]`` rows plus a
stable ``source_key`` per row, which the mapping layer turns into items.
"""

import csv
import io
import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.errors import ValidationFailed

# Order matters: strict decoders first. GB18030 is a superset of GBK and
# decodes most byte strings, so it is tried only after UTF-8 fails; CP1252 is
# the last resort.
_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "cp1252")


@dataclass
class SourceTable:
    headers: list[str]
    rows: list[dict[str, Any]]
    keys: list[str]
    meta: dict[str, Any] = field(default_factory=dict)


def decode_bytes(data: bytes) -> tuple[str, str]:
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValidationFailed("could not detect the file encoding", code="bad_encoding")


def parse_csv(data: bytes, *, key_columns: list[str] | None = None) -> SourceTable:
    if not data.strip():
        raise ValidationFailed("the file is empty", code="empty_file")
    text, encoding = decode_bytes(data)
    sample = text[:5000]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    all_rows = [r for r in reader]
    if not all_rows:
        raise ValidationFailed("the file has no rows", code="empty_file")
    headers = _dedupe_headers([h.strip() for h in all_rows[0]])
    rows = []
    for raw in all_rows[1:]:
        if not any(c.strip() for c in raw):
            continue
        rows.append({h: (raw[i] if i < len(raw) else "") for i, h in enumerate(headers)})
    return SourceTable(
        headers=headers,
        rows=rows,
        keys=make_keys(rows, key_columns or _guess_key_columns(headers)),
        meta={"encoding": encoding, "delimiter": getattr(dialect, "delimiter", ",")},
    )


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: Counter[str] = Counter()
    out = []
    for h in headers:
        h = h or "column"
        seen[h] += 1
        out.append(h if seen[h] == 1 else f"{h} ({seen[h]})")
    return out


def _guess_key_columns(headers: list[str]) -> list[str]:
    lower = {h.lower(): h for h in headers}
    for candidates in (["id"], ["name"], ["project name"], ["client name"]):
        found = [lower[c] for c in candidates if c in lower]
        if found:
            return found
    return headers[:1]


def make_keys(rows: list[dict[str, Any]], key_columns: list[str]) -> list[str]:
    """Stable per-row keys. Duplicates get an occurrence suffix (#2, #3) so a
    client with two rows on one board still maps one-to-one on re-import."""
    seen: Counter[str] = Counter()
    keys = []
    for r in rows:
        base = " | ".join(str(r.get(c, "")).strip().lower() for c in key_columns)
        seen[base] += 1
        keys.append(base if seen[base] == 1 else f"{base}#{seen[base]}")
    return keys


# ---------------------------------------------------------------------------
# ERPNext / Frappe REST
# ---------------------------------------------------------------------------
class ErpNextClient:
    """Read-only client for the Frappe REST API (token auth)."""

    PAGE = 200

    def __init__(
        self, base_url: str, api_key: str, api_secret: str, transport: httpx.BaseTransport | None = None
    ):
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"token {api_key}:{api_secret}", "Accept": "application/json"},
            timeout=30.0,
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self.http.get(path, params=params)
        if r.status_code in (401, 403):
            raise ValidationFailed("ERPNext rejected the API credentials", code="erpnext_auth")
        r.raise_for_status()
        body = r.json()
        # Frappe answers 200 with an empty body when the session is broken;
        # "no data" must never be confused with "could not ask".
        if "data" not in body:
            raise ValidationFailed("unexpected ERPNext response (no data key)", code="erpnext_bad_response")
        return body["data"]

    def list(
        self, doctype: str, *, filters: list[Any] | None = None, fields: list[str] | None = None
    ) -> Iterator[dict[str, Any]]:
        start = 0
        while True:
            page = self._get(
                f"/api/resource/{doctype}",
                {
                    "fields": json.dumps(fields or ["name"]),
                    "filters": json.dumps(filters or []),
                    "limit_start": start,
                    "limit_page_length": self.PAGE,
                    "order_by": "creation asc",
                },
            )
            yield from page
            if len(page) < self.PAGE:
                return
            start += self.PAGE

    def get(self, doctype: str, name: str) -> dict[str, Any]:
        return self._get(f"/api/resource/{doctype}/{name}")  # type: ignore[no-any-return]


def fetch_erpnext_projects(client: ErpNextClient, project_types: list[str]) -> SourceTable:
    """Flatten ERPNext Projects (with their children and context) into rows.

    Synthesised columns (prefixed with ``_``) carry what a CSV export lacks:
    the customer's details, the team by role, software, comments and the
    monthly status grid.
    """
    rows: list[dict[str, Any]] = []
    customers: dict[str, dict[str, Any]] = {}
    users: dict[str, str] = {}
    for u in client.list("User", fields=["name", "full_name"]):
        users[u["name"]] = u.get("full_name") or u["name"]

    for ptype in project_types:
        for stub in client.list("Project", filters=[["project_type", "=", ptype]]):
            doc = client.get("Project", stub["name"])
            cust_name = doc.get("customer")
            if cust_name and cust_name not in customers:
                customers[cust_name] = client.get("Customer", cust_name)
            cust = customers.get(cust_name or "", {})
            team: dict[str, list[str]] = {}
            for m in doc.get("custom_team_members") or []:
                if m.get("user"):
                    team.setdefault(m.get("role") or "Preparer", []).append(users.get(m["user"], m["user"]))
            comments = [
                {
                    "author": users.get(c.get("owner", ""), c.get("owner")),
                    "body": c.get("content"),
                    "at": c.get("creation"),
                }
                for c in client.list(
                    "Comment",
                    filters=[
                        ["reference_doctype", "=", "Project"],
                        ["reference_name", "=", doc["name"]],
                        ["comment_type", "=", "Comment"],
                    ],
                    fields=["owner", "content", "creation"],
                )
            ]
            monthly = {
                str(ms.get("month_index")): ms.get("status")
                for ms in client.list(
                    "Monthly Status",
                    filters=[["reference_name", "=", doc["name"]]],
                    fields=["month_index", "status", "fiscal_year"],
                )
            }
            primary = next((e for e in cust.get("custom_entities") or [] if e.get("is_primary")), None)
            row = {k: v for k, v in doc.items() if not isinstance(v, (list, dict))}
            row.update(
                {
                    "_customer_name": cust.get("customer_name") or cust_name,
                    "_customer_type": cust.get("customer_type"),
                    "_customer_partner": users.get(
                        cust.get("custom_partner") or "", cust.get("custom_partner")
                    ),
                    "_customer_disabled": cust.get("disabled"),
                    "_entity_type": (primary or {}).get("entity_type"),
                    "_entity_abn": (primary or {}).get("abn"),
                    "_entity_year_end": (primary or {}).get("year_end"),
                    "_softwares": "; ".join(s.get("software", "") for s in doc.get("custom_softwares") or []),
                    "_comments": comments,
                    "_monthly_status": monthly,
                    **{f"_team:{role}": "; ".join(names) for role, names in team.items()},
                }
            )
            rows.append(row)
    headers = sorted({k for r in rows for k in r})
    return SourceTable(
        headers=headers,
        rows=rows,
        keys=[r["name"] for r in rows],
        meta={"project_types": project_types, "customers": len(customers)},
    )
