"""Reference configuration reproducing the current Smart Board setup.

Everything here is ordinary data created through commands; after seeding it
can be changed in Settings like any other configuration. Running it twice is
safe: existing workspaces are left alone.
"""

from datetime import date
from typing import Any

from sqlalchemy import select

from app.core.db import read_session
from app.modules.workspaces.commands import (
    CreateBoard,
    CreateField,
    CreateWorkspace,
    UpdateWorkspace,
    UpsertFiscalYear,
    UpsertLookupList,
    UpsertLookupValue,
    UpsertMemberRole,
    UpsertStatus,
)
from app.modules.workspaces.models import FiscalYear, Workspace
from app.platform.commands import Command, Origin, bus
from app.platform.permissions import SYSTEM_ACTOR


def _run(cmd: Command) -> Any:
    return bus.execute(cmd, actor=SYSTEM_ACTOR, origin=Origin.SYSTEM).result


def _opts(*labels: str, colors: dict[str, str] | None = None) -> list[dict[str, str]]:
    colors = colors or {}
    return [{"label": label, "color": colors.get(label, "gray")} for label in labels]


TRACKING = _opts(
    "Not started", "Not applicable", "Done",
    colors={"Not started": "gray", "Not applicable": "dark", "Done": "green"},
)  # fmt: skip
MONTHLY = [
    {"key": "not_started", "label": "Not Started", "color": "gray"},
    {"key": "working", "label": "Working On It", "color": "orange"},
    {"key": "stuck", "label": "Stuck", "color": "red"},
    {"key": "done", "label": "Done", "color": "green"},
]

# (label, category, color)
ACCOUNTING_STATUSES = [
    ("Not started", "todo", "gray"),
    ("Working on it", "active", "orange"),
    ("Waiting for client", "waiting", "violet"),
    ("Ready for manager review", "active", "cyan"),
    ("Review points to be actioned", "active", "pink"),
    ("Ready for partner review", "active", "blue"),
    ("Ready to send to client", "active", "teal"),
    ("Sent to client for signature", "waiting", "indigo"),
    ("Waiting for CTR", "waiting", "grape"),
    ("Waiting for payment", "waiting", "yellow"),
    ("Hold", "waiting", "dark"),
    ("Completed", "done", "green"),
    ("Not to Proceed", "cancelled", "red"),
]
GRANTS_STATUSES = [
    ("Not started", "todo", "gray"),
    ("Hold", "waiting", "dark"),
    ("Waiting for kickoff", "waiting", "violet"),
    ("Waiting for tech meeting", "waiting", "violet"),
    ("Waiting for tech evidence", "waiting", "grape"),
    ("Reviewing R&D Evidence", "active", "orange"),
    ("Waiting for evidence review", "waiting", "indigo"),
    ("Preparing R&D report", "active", "orange"),
    ("Waiting for report review and signature", "waiting", "blue"),
    ("Preparing application form", "active", "cyan"),
    ("Waiting for AP review", "waiting", "blue"),
    ("Waiting for financial accounts", "waiting", "violet"),
    ("Preparing R&D exp calculation", "active", "orange"),
    ("Waiting for responses to fin queries", "waiting", "violet"),
    ("Final pack prep", "active", "teal"),
    ("Waiting for CTR", "waiting", "grape"),
    ("Waiting for payment", "waiting", "yellow"),
    ("Completed", "done", "green"),
    ("Not to Proceed", "cancelled", "red"),
]
TASK_STATUSES = [
    ("Not started yet", "todo", "gray"),
    ("Working on it", "active", "orange"),
    ("Stuck", "waiting", "red"),
    ("Done", "done", "green"),
]


def seed_reference_config() -> dict[str, str]:
    with read_session() as s:
        existing = {w.key: str(w.id) for w in s.scalars(select(Workspace))}
        fys = {f.label for f in s.scalars(select(FiscalYear))}
    if {"accounting", "grants"} <= set(existing):
        return existing

    # Australian financial years, 1 July - 30 June.
    for start in range(2022, 2030):
        label = f"{start}-{start + 1}"
        if label not in fys:
            _run(UpsertFiscalYear(label=label, start_date=date(start, 7, 1), end_date=date(start + 1, 6, 30)))

    for key, label, values in [
        ("company", "Company", ["Top Figures", "Top Grants", "VERITAX PARTNERS"]),
        ("software", "Software", ["Xero", "MYOB", "QuickBooks", "Excel", "Payroller", "Other"]),
    ]:
        _run(UpsertLookupList(key=key, label=label))
        for v in values:
            _run(
                UpsertLookupValue(
                    list_key=key, label=v, aliases=["Quickbooks"] if v == "QuickBooks" else None
                )
            )

    ids = {
        "accounting": existing.get("accounting") or _seed_accounting(),
        "grants": existing.get("grants") or _seed_grants(),
    }
    return ids


def _statuses(ws: str, rows: list[tuple[str, str, str]], scope: str = "item") -> None:
    for i, (label, cat, color) in enumerate(rows):
        _run(
            UpsertStatus(
                workspace_id=ws, scope=scope, label=label, category=cat, color=color, is_default=i == 0
            )
        )  # type: ignore[arg-type]


def _field(ws: str, label: str, type_: str, **kw: Any) -> None:
    _run(CreateField(workspace_id=ws, label=label, type=type_, **kw))  # type: ignore[arg-type]


def _seed_accounting() -> str:
    ws = _run(CreateWorkspace(key="accounting", name="Smart Accounting", item_label="Project"))["id"]
    _statuses(ws, ACCOUNTING_STATUSES)
    _statuses(ws, TASK_STATUSES, scope="task")
    for key, label in [("preparer", "Preparer"), ("manager", "Manager"), ("partner", "Partner"),
                       ("assigned", "Assigned Person")]:  # fmt: skip
        _run(UpsertMemberRole(workspace_id=ws, key=key, label=label))  # type: ignore[arg-type]

    _field(ws, "Company", "lookup", key="company", config={"list": "company"})
    _field(ws, "Entity Type", "mirror", key="entity_type",
           config={"of": "entity", "field": "entity_type", "display_type": "text"})  # fmt: skip
    _field(ws, "Year End", "month", key="year_end", rollover="carry")
    _field(ws, "Target Month", "month", key="target_month")
    _field(ws, "Frequency", "select", key="frequency", config={"options": _opts(
        "Yearly", "Half-Yearly", "Quarterly", "Monthly", "Fortnightly", "Weekly", "One-off")})  # fmt: skip
    _field(ws, "Reset Date", "date", key="reset_date", rollover="add_year")
    _field(ws, "Monthly Status", "period_grid", key="monthly_status", rollover="clear",
           config={"periods": 12, "options": MONTHLY})  # fmt: skip
    _field(ws, "Software", "lookup_multi", key="software", config={"list": "software"})
    for key, label in [("ato_status", "ATO"), ("lodgeit_status", "LodgeIT"),
                       ("company_agent_status", "Company Agent"), ("xero_qb_status", "Xero/QuickBooks")]:  # fmt: skip
        _field(ws, label, "select", key=key, config={"options": TRACKING}, group="Tracking", rollover="clear")
    _field(ws, "Priority", "select", key="priority", config={"options": _opts(
        "Low", "Medium", "High", "Urgent",
        colors={"Low": "gray", "Medium": "blue", "High": "orange", "Urgent": "red"})})  # fmt: skip
    _field(ws, "Budget", "money", key="budget")
    _field(ws, "Engagement Letter", "url", key="engagement_letter")
    _field(ws, "Notes", "long_text", key="notes", rollover="clear")

    _run(UpdateWorkspace(workspace_id=ws, settings={  # type: ignore[arg-type]
        "core_columns": {"due_date": {"label": "Lodgement Due"}, "name": {"label": "Project Name"}},
        "autofill": {
            "entity": "primary",
            "data": {"year_end": "entity.year_end_month"},
            "roles": {"partner": "client.partner_user_id"},
        },
        "rollover": {"default_target": "same"},
        "required_on_create": ["client", "company", "fiscal_year"],
    }))  # fmt: skip
    for name in ["Financials & Tax Return", "ITR", "BAS", "Payroll", "Payroll & Super", "Bookkeeping",
                 "SMSF", "Audit", "Financial Statements"]:  # fmt: skip
        _run(CreateBoard(workspace_id=ws, name=name))  # type: ignore[arg-type]
    return str(ws)


def _seed_grants() -> str:
    ws = _run(CreateWorkspace(key="grants", name="Smart Grants", item_label="Project"))["id"]
    _statuses(ws, GRANTS_STATUSES)
    _statuses(ws, TASK_STATUSES, scope="task")
    for key, label in [("responsible", "Responsible Person"), ("salesperson", "Salesperson"),
                       ("partner", "Partner")]:  # fmt: skip
        _run(UpsertMemberRole(workspace_id=ws, key=key, label=label))  # type: ignore[arg-type]

    # Client-level facts (one source of truth, mirrored on every board).
    _field(ws, "Portal Access Received", "checkbox", key="portal_access_received", entity_kind="client")
    _field(ws, "Portal Access Expiry", "date", key="portal_access_expiry", entity_kind="client")
    _field(ws, "Address", "long_text", key="address", entity_kind="client")
    _field(ws, "Primary Communication", "long_text", key="primary_communication", entity_kind="client")
    _field(ws, "State", "select", key="state", entity_kind="client",
           config={"options": _opts("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")})  # fmt: skip
    _field(ws, "Industry", "text", key="industry", entity_kind="client")

    _field(ws, "FY/CY", "select", key="fy_cy", config={"options": _opts("FY", "CY")})
    _field(ws, "Grant Type", "select", key="grant_type", config={"options": _opts("R&DTI", "EMDG")})
    _field(ws, "Grants Priority", "select", key="grants_priority", config={"options": _opts(
        "S1", "S2", "S3", "S4", colors={"S1": "red", "S2": "orange", "S3": "yellow", "S4": "gray"})})  # fmt: skip
    _field(ws, "Portal Access Received", "mirror", key="portal_access_received",
           config={"of": "client", "field": "data.portal_access_received", "display_type": "checkbox"})  # fmt: skip
    _field(ws, "Portal Access Expiry", "mirror", key="portal_access_expiry",
           config={"of": "client", "field": "data.portal_access_expiry", "display_type": "date"})  # fmt: skip
    _field(ws, "Tax Agent", "checkbox", key="tg_tax_agent", config={"true_values": ["TG - Yes", "TG"]})
    _field(ws, "AP Submit Date", "date", key="ap_submit_date", rollover="clear")
    _field(ws, "Industry Approval Date", "date", key="industry_approval_date", rollover="clear")
    _field(ws, "Tax Lodgement Date", "date", key="tax_lodgement_date", rollover="clear")
    _field(ws, "Contact Name", "mirror", key="contact_name",
           config={"of": "contact", "field": "name", "display_type": "text"})  # fmt: skip
    _field(ws, "Primary Communication", "mirror", key="primary_communication",
           config={"of": "client", "field": "data.primary_communication", "display_type": "long_text"})  # fmt: skip
    _field(ws, "ABN", "mirror", key="abn", config={"of": "entity", "field": "abn", "display_type": "text"})
    _field(
        ws,
        "State",
        "mirror",
        key="state",
        config={"of": "client", "field": "data.state", "display_type": "text"},
    )
    _field(ws, "Industry", "mirror", key="industry",
           config={"of": "client", "field": "data.industry", "display_type": "text"})  # fmt: skip
    _field(ws, "Engagement Date", "year_month", key="engagement_date")
    _field(ws, "Rebate Amount", "money", key="rebate_amount", rollover="clear")
    _field(ws, "Fee Arrangement", "long_text", key="fee_arrangement")
    _field(ws, "Fee Percentage", "text", key="fee_percentage")
    _field(ws, "Referral", "text", key="referral")
    _field(ws, "Application Progress", "long_text", key="application_progress", rollover="clear")
    _field(ws, "Notes", "long_text", key="notes", rollover="clear")

    _run(UpdateWorkspace(workspace_id=ws, settings={  # type: ignore[arg-type]
        "core_columns": {
            "due_date": {"hidden": True},
            "fiscal_year": {"hidden": True, "rollover": "carry"},
            "name": {"label": "Project Name"},
        },
        "autofill": {"entity": "primary", "roles": {"partner": "client.partner_user_id"}},
        "rollover": {"default_target": "next_period"},
        "board": {"pinned_left": ["client"]},
    }))  # fmt: skip
    with read_session() as s:
        fy_ids = {f.label: str(f.id) for f in s.scalars(select(FiscalYear))}
    for year in (2024, 2025, 2026, 2027):
        _run(
            CreateBoard(
                workspace_id=ws,
                name=f"FY {year}",  # type: ignore[arg-type]
                period_fiscal_year_id=fy_ids.get(f"{year - 1}-{year}"),
            )
        )  # type: ignore[arg-type]
    return str(ws)
