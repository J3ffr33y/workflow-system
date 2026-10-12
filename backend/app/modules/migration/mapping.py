"""Mapping legacy columns onto the new model.

A mapping is plain JSON stored on the run, so it can be reviewed, edited in
the UI, saved as a profile and re-used for the next export:

    {
      "columns": {"Client Name": "client.name", "Lodgement Due": "item.due_date", ...},
      "values":  {"Status": {"Waiting for client": "waiting_for_client", ...},
                  "Preparer": {"Joe Liu": "<user id>", "Jo": "__new__"}},
      "options": {"name_template": "{client} - {board}", "create_clients": true, ...}
    }

Targets:
  item.<column key>          any item column (core, custom, role.<key>)
  client.name / client.partner / client.client_type / client.data.<key>
  entity.entity_type / entity.abn / entity.year_end_month
  contact.name / contact.email / contact.phone
  comment                    imported as an update on the item
  ignore
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.workspaces.models import Board, FieldDefinition, FiscalYear, Status, Workspace
from app.modules.workspaces.schema import FieldResolver, item_columns
from app.platform.fields.types import (
    FieldValueError,
    clean_text,
    field_types,
    match_option,
)

NEW = "__new__"
EMPTY = "__empty__"

ENTITY_TYPE_OPTIONS = [
    {"key": "individual", "label": "Individual"},
    {"key": "company", "label": "Company"},
    {"key": "partnership", "label": "Partnership"},
    {"key": "trust", "label": "Trust"},
    {"key": "smsf", "label": "SMSF"},
    {"key": "other_incorporated", "label": "Other Incorporated Entity"},
    {"key": "other", "label": "Other"},
]

# Old Smart Board labels / ERPNext fieldnames -> new targets, where the label
# alone would not match. Keys are normalised (lowercase, alphanumerics only).
SYNONYMS: dict[str, list[str]] = {
    "clientname": ["client.name"],
    "customer": ["client.name"],
    "customername": ["client.name"],
    "projectname": ["item.name"],
    "updates": ["comment"],
    "comments": ["comment"],
    "lodgementdue": ["item.due_date"],
    "customlodgementduedate": ["item.due_date"],
    "fiscalyear": ["item.fiscal_year"],
    "customfiscalyear": ["item.fiscal_year"],
    "entity": ["entity.entity_type"],
    "entitytype": ["entity.entity_type"],
    "abn": ["item.abn", "entity.abn"],
    "customgrantsabnsnapshot": ["entity.abn"],
    "entityabn": ["entity.abn"],
    "entityyearend": ["entity.year_end_month"],
    "budget": ["item.budget"],
    "estimatedcosting": ["item.budget"],
    "lastupdated": ["ignore"],
    "modified": ["ignore"],
    "creation": ["ignore"],
    "software": ["item.software"],
    "softwares": ["item.software"],
    "customprojectfrequency": ["item.frequency"],
    "customtargetmonth": ["item.target_month"],
    "customyearend": ["item.year_end"],
    "partner": ["item.role.partner"],
    "customerpartner": ["client.partner"],
    "manager": ["item.role.manager"],
    "preparer": ["item.role.preparer"],
    "assignedperson": ["item.role.assigned"],
    "teampartner": ["item.role.partner"],
    "teammanager": ["item.role.manager"],
    "teampreparer": ["item.role.preparer"],
    "teamassignedperson": ["item.role.assigned"],
    "responsibleperson": ["item.role.responsible"],
    "customgrantsownername": ["item.role.responsible"],
    "salesperson": ["item.role.salesperson"],
    "customgrantssalesperson": ["item.role.salesperson"],
    "fycy": ["item.fy_cy"],
    "customgrantsfylabel": ["item.fy_cy"],
    "grantspriority": ["item.grants_priority"],
    "customgrantspriority": ["item.grants_priority"],
    "grantstype": ["item.grant_type"],
    "customgrantstype": ["item.grant_type"],
    "taxagent": ["item.tg_tax_agent"],
    "customtgtaxagent": ["item.tg_tax_agent"],
    "portalaccessexpiry": ["client.data.portal_access_expiry"],
    "customportalaccessexpirydate": ["client.data.portal_access_expiry"],
    "portalaccessreceived": ["client.data.portal_access_received"],
    "customportalaccessreceived": ["client.data.portal_access_received"],
    "primarycommunication": ["client.data.primary_communication"],
    "customgrantsprimarycommunication": ["client.data.primary_communication"],
    "address": ["client.data.address"],
    "customgrantsaddresssnapshot": ["client.data.address"],
    "state": ["client.data.state"],
    "customgrantsstate": ["client.data.state"],
    "industry": ["client.data.industry"],
    "customgrantsindustrycategory": ["client.data.industry"],
    "contactname": ["contact.name"],
    "customgrantscontactname": ["contact.name"],
    "applicationprogress": ["item.application_progress"],
    "customgrantsstatus": ["item.application_progress"],
    "apsubmitdate": ["item.ap_submit_date"],
    "customapsubmitdate": ["item.ap_submit_date"],
    "industryapprovaldate": ["item.industry_approval_date"],
    "customindustryapprovaldate": ["item.industry_approval_date"],
    "taxlodgementdate": ["item.tax_lodgement_date"],
    "customtaxlodgementdate": ["item.tax_lodgement_date"],
    "rebateamount": ["item.rebate_amount"],
    "customrebateamounttext": ["item.rebate_amount"],
    "feepercentage": ["item.fee_percentage"],
    "customfeepercentagetext": ["item.fee_percentage"],
    "feearrangement": ["item.fee_arrangement"],
    "customfeearrangement": ["item.fee_arrangement"],
    "referral": ["item.referral"],
    "customgrantsreferraltext": ["item.referral"],
    "engagementdate": ["item.engagement_date"],
    "customengagementdate": ["item.engagement_date"],
    "ato": ["item.ato_status"],
    "customatostatus": ["item.ato_status"],
    "lodgeit": ["item.lodgeit_status"],
    "customlodgeitstatus": ["item.lodgeit_status"],
    "companyagent": ["item.company_agent_status"],
    "customcompanyagentstatus": ["item.company_agent_status"],
    "xeroquickbooks": ["item.xero_qb_status"],
    "customxeroquickbooksstatus": ["item.xero_qb_status"],
    "monthlystatus": ["item.monthly_status"],
}


def norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


@dataclass
class Target:
    key: str
    label: str
    type: str
    config: dict[str, Any] = field(default_factory=dict)
    group: str = "Item"

    @property
    def value_mapped(self) -> bool:
        return self.type in {
            "status", "select", "multi_select", "lookup", "lookup_multi", "user", "users",
            "fiscal_year", "entity_type", "period_grid",
        }  # fmt: skip

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"value_mapped": self.value_mapped}


class MappingContext:
    """Everything needed to map rows for one workspace + board."""

    def __init__(self, s: Session, workspace: Workspace, board: Board) -> None:
        self.s = s
        self.ws = workspace
        self.board = board
        self.resolver = FieldResolver(s)
        self.columns = {c.key: c for c in item_columns(s, workspace)}
        self.statuses = list(
            s.scalars(
                select(Status)
                .where(
                    Status.workspace_id == workspace.id, Status.scope == "item", Status.is_archived.is_(False)
                )
                .order_by(Status.position)
            )
        )
        self.fiscal_years = {f.label.lower(): f for f in s.scalars(select(FiscalYear))}
        self.client_fields = {
            f.key: f
            for f in s.scalars(
                select(FieldDefinition).where(
                    FieldDefinition.entity_kind == "client", FieldDefinition.is_archived.is_(False)
                )
            )
        }
        self.targets = self._targets()

    def _targets(self) -> dict[str, Target]:
        t: dict[str, Target] = {}
        for c in self.columns.values():
            if not c.editable or c.key == "board":
                continue
            type_ = {
                "client": "text",
                "entity": "text",
                "status": "status",
                "fiscal_year": "fiscal_year",
            }.get(c.key, c.type)
            if c.key in ("client", "entity"):
                continue  # clients/entities are mapped through client.* and entity.*
            t[f"item.{c.key}"] = Target(f"item.{c.key}", c.label, type_, c.config, "Item")
        t["client.name"] = Target("client.name", "Client name", "text", {}, "Client")
        t["client.partner"] = Target("client.partner", "Client partner", "user", {}, "Client")
        for key, f in self.client_fields.items():
            t[f"client.data.{key}"] = Target(f"client.data.{key}", f.label, f.type, f.config, "Client")
        t["entity.entity_type"] = Target(
            "entity.entity_type", "Entity type", "entity_type", {"options": ENTITY_TYPE_OPTIONS}, "Entity"
        )
        t["entity.abn"] = Target("entity.abn", "ABN", "text", {}, "Entity")
        t["entity.year_end_month"] = Target("entity.year_end_month", "Entity year end", "month", {}, "Entity")
        t["contact.name"] = Target("contact.name", "Contact name", "text", {}, "Contact")
        t["contact.email"] = Target("contact.email", "Contact email", "email", {}, "Contact")
        t["contact.phone"] = Target("contact.phone", "Contact phone", "phone", {}, "Contact")
        t["comment"] = Target("comment", "Update / comment", "long_text", {}, "Other")
        return t

    # ---- suggestion -----------------------------------------------------
    def suggest(self, headers: list[str]) -> dict[str, str]:
        by_label: dict[str, str] = {}
        for key, tg in self.targets.items():
            by_label.setdefault(norm(tg.label), key)
            by_label.setdefault(norm(key.split(".")[-1]), key)
        out: dict[str, str] = {}
        used: set[str] = set()
        for h in headers:
            n = norm(h.lstrip("_").replace(":", ""))
            choice = "ignore"
            for cand in SYNONYMS.get(n, []):
                if cand == "ignore" or (cand in self.targets and cand not in used):
                    choice = cand
                    break
            else:
                label_match = by_label.get(n)
                if label_match and label_match not in used:
                    choice = label_match
            if choice not in ("ignore", "comment", "item.role.partner"):
                used.add(choice)
            out[h] = choice
        return out

    # ---- value parsing ------------------------------------------------------
    def parse_value(self, target: Target, raw: Any, value_map: dict[str, Any]) -> Any:
        """Raw cell -> canonical value for ``target``. Raises FieldValueError."""
        if isinstance(raw, dict) and target.type == "period_grid":
            out_grid = {}
            for period, label in raw.items():
                key = match_option(target.config, str(label)) if label else None
                if key:
                    out_grid[str(period)] = key
            return out_grid
        if isinstance(raw, (dict, list)):
            return raw
        text = clean_text(raw)
        if text is None:
            return None if target.type not in ("multi_select", "lookup_multi", "users") else []
        if target.type in ("multi_select", "lookup_multi", "users"):
            parts = [p.strip() for p in re.split(r"[;,\n/]", text) if p.strip()]
            single = {"multi_select": "select", "lookup_multi": "lookup", "users": "user"}[target.type]
            out = []
            for p in parts:
                v = self._single(Target(target.key, target.label, single, target.config), p, value_map)
                if v is not None:
                    out.append(v)
            return list(dict.fromkeys(out))
        return self._single(target, text, value_map)

    def _single(self, target: Target, text: str, value_map: dict[str, Any]) -> Any:
        if text in value_map:
            mapped = value_map[text]
            if mapped == EMPTY:
                return None
            if mapped == NEW:
                raise FieldValueError(
                    f"'{text}' will be created when the run is prepared", code="pending_new"
                )
            return mapped
        match target.type:
            case "status":
                t = text.lower()
                for st in self.statuses:
                    if t in (st.key, st.label.lower()):
                        return st.key
                raise FieldValueError(f"unknown status '{text}'", code="unknown_option")
            case "fiscal_year":
                fy = self.fiscal_years.get(text.lower().replace("fy", "").strip()) or self.fiscal_years.get(
                    text.lower()
                )
                if fy is None:
                    raise FieldValueError(f"unknown fiscal year '{text}'", code="unknown_option")
                return str(fy.id)
            case "entity_type":
                key = match_option({"options": ENTITY_TYPE_OPTIONS}, text)
                if key is None:
                    raise FieldValueError(f"unknown entity type '{text}'", code="unknown_option")
                return key
            case _:
                return field_types.get(target.type).parse_text(text, target.config, self.resolver)


def distinct_values(rows: list[dict[str, Any]], header: str, multi: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        v = r.get(header)
        if isinstance(v, (dict, list)):
            continue
        text = clean_text(v)
        if text is None:
            continue
        parts = [p.strip() for p in re.split(r"[;,\n/]", text) if p.strip()] if multi else [text]
        for p in parts:
            counts[p] = counts.get(p, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())))


def render_name(template: str, values: dict[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        return str(values.get(m.group(1), "") or "")

    return re.sub(r"\s+", " ", re.sub(r"\{([^}]+)\}", repl, template)).strip(" -")
