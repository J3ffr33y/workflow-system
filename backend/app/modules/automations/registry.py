"""Automation building blocks.

Triggers decide *when* a rule is considered, conditions (the shared filter
language) decide *whether* it applies to an item, actions decide *what*
happens. Each block is registered here; a new trigger or action is one class
and becomes available to every workspace.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, ClassVar

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from app.core.errors import ValidationFailed
from app.core.time import business_today, utcnow
from app.modules.items.models import Item, ItemMember
from app.modules.items.service import ItemWriter
from app.modules.tasks.commands import CreateTask, create_task_for
from app.platform.commands import CommandContext

FREQUENCY_STEPS: dict[str, relativedelta] = {
    "yearly": relativedelta(years=1),
    "half_yearly": relativedelta(months=6),
    "quarterly": relativedelta(months=3),
    "monthly": relativedelta(months=1),
    "fortnightly": relativedelta(weeks=2),
    "weekly": relativedelta(weeks=1),
}


def step(amount: int, unit: str) -> relativedelta:
    match unit:
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
    raise ValidationFailed(f"unknown unit {unit}")


# --- triggers ----------------------------------------------------------------------
class Trigger:
    type: ClassVar[str]
    label: ClassVar[str]
    kind: ClassVar[str]  # "event" | "schedule"

    def validate(self, config: dict[str, Any], writer_columns: dict[str, Any]) -> dict[str, Any]:
        return config

    def matches_event(self, config: dict[str, Any], event_type: str, changes: dict[str, list[Any]]) -> bool:
        return False


class ItemCreated(Trigger):
    type = "item_created"
    label = "Item is created"
    kind = "event"

    def matches_event(self, config: dict[str, Any], event_type: str, changes: dict[str, list[Any]]) -> bool:
        return event_type == "item.created"


class FieldChanged(Trigger):
    """A field changes, optionally from / to specific values.

    config: {"field": "status", "to": ["completed"], "from": [...]}
    """

    type = "field_changed"
    label = "Field changes"
    kind = "event"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        if config.get("field") not in cols:
            raise ValidationFailed("trigger needs a valid field")
        return {"field": config["field"], "to": config.get("to") or [], "from": config.get("from") or []}

    def matches_event(self, config: dict[str, Any], event_type: str, changes: dict[str, list[Any]]) -> bool:
        if event_type != "item.updated":
            return False
        f = config["field"]
        key = f if f in changes else f"data.{f}"
        if key not in changes:
            return False
        before, after = changes[key]
        if config.get("to") and after not in config["to"]:
            return False
        return not (config.get("from") and before not in config["from"])


class StatusChanged(FieldChanged):
    type = "status_changed"
    label = "Status changes to"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        if not config.get("to"):
            raise ValidationFailed("choose at least one status")
        return {"field": "status", "to": config["to"], "from": config.get("from") or []}


class DateReached(Trigger):
    """A date field reaches today, optionally offset ("30 days before").

    config: {"field": "due_date", "offset": {"amount": 30, "unit": "d", "direction": "before"},
             "mode": "on" | "on_or_after"}
    """

    type = "date_reached"
    label = "Date arrives / is approaching"
    kind = "schedule"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        col = cols.get(config.get("field", ""))
        if col is None or col.kind != "date":
            raise ValidationFailed("trigger needs a date field")
        off = config.get("offset") or {}
        amount = int(off.get("amount", 0))
        if amount < 0:
            raise ValidationFailed("offset must be positive; use direction")
        return {
            "field": config["field"],
            "offset": {
                "amount": amount,
                "unit": off.get("unit", "d"),
                "direction": off.get("direction", "before"),
            },
            "mode": config.get("mode", "on_or_after"),
        }

    @staticmethod
    def target_date(config: dict[str, Any], today: date) -> date:
        """The field value that counts as "reached" today.

        "30 days before the date" fires when date - 30d == today, i.e. the
        field equals today + 30d.
        """
        off = config["offset"]
        delta = step(int(off["amount"]), off["unit"])
        return today + delta if off["direction"] == "before" else today - delta


TRIGGERS: dict[str, Trigger] = {
    t.type: t for t in (ItemCreated(), FieldChanged(), StatusChanged(), DateReached())
}


# --- actions -------------------------------------------------------------------------
@dataclass
class ActionContext:
    ctx: CommandContext
    writer: ItemWriter
    item: Item
    rule_id: uuid.UUID
    rule_name: str


class Action:
    type: ClassVar[str]
    label: ClassVar[str]

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        return config

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        raise NotImplementedError


class SetField(Action):
    type = "set_field"
    label = "Set a field"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        col = cols.get(config.get("field", ""))
        if col is None or not col.editable:
            raise ValidationFailed("choose an editable field")
        return {"field": config["field"], "value": config.get("value")}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        a.writer.set(a.item, config["field"], config.get("value"))
        return f"set {config['field']}"


class SetStatus(Action):
    type = "set_status"
    label = "Reset / set status"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        if not config.get("status"):
            raise ValidationFailed("choose a status")
        return {"status": config["status"]}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        a.writer.set(a.item, "status", config["status"])
        return f"status -> {config['status']}"


class ClearField(Action):
    type = "clear_field"
    label = "Clear a field"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        col = cols.get(config.get("field", ""))
        if col is None or not col.editable:
            raise ValidationFailed("choose an editable field")
        return {"field": config["field"]}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        a.writer.set(a.item, config["field"], None)
        return f"cleared {config['field']}"


class AdvanceDate(Action):
    """Push a date forward by the item's frequency or a fixed interval.

    config: {"field": "due_date", "by": "frequency", "frequency_field": "frequency"}
         or {"field": "reset_date", "by": {"amount": 1, "unit": "m"}}
    Month fields (1-12) advance modulo 12.
    """

    type = "advance_date"
    label = "Push a date forward"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        col = cols.get(config.get("field", ""))
        if col is None or col.type not in ("date", "month", "year_month"):
            raise ValidationFailed("choose a date or month field")
        by = config.get("by", "frequency")
        if by == "frequency":
            if config.get("frequency_field", "frequency") not in cols:
                raise ValidationFailed("frequency field not found")
        elif not isinstance(by, dict) or "unit" not in by:
            raise ValidationFailed("by must be 'frequency' or {amount, unit}")
        return {
            "field": config["field"],
            "by": by,
            "frequency_field": config.get("frequency_field", "frequency"),
        }

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        by = config["by"]
        if by == "frequency":
            freq = a.writer.current(a.item, config["frequency_field"])
            delta = FREQUENCY_STEPS.get(str(freq or ""))
            if delta is None:
                return f"skipped: frequency '{freq}' has no interval"
        else:
            delta = step(int(by.get("amount", 1)), by["unit"])
        col = a.writer.column(config["field"])
        current = a.writer.current(a.item, config["field"])
        if current in (None, ""):
            return "skipped: no date"
        if col.type == "month":
            months = delta.months + delta.years * 12
            new: Any = (int(current) - 1 + months) % 12 + 1
        elif col.type == "year_month":
            y, m = (int(x) for x in current.split("-"))
            d = date(y, m, 1) + delta
            new = f"{d.year:04d}-{d.month:02d}"
        else:
            new = (date.fromisoformat(current) + delta).isoformat()
        a.writer.set(a.item, config["field"], new)
        return f"{config['field']}: {current} -> {new}"


class NotifyRoles(Action):
    type = "notify_roles"
    label = "Notify people in a role"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        roles = config.get("roles") or []
        if not roles:
            raise ValidationFailed("choose at least one role")
        return {"roles": roles, "message": config.get("message") or ""}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        users = {
            str(u)
            for u in a.ctx.session.scalars(
                select(ItemMember.user_id).where(
                    ItemMember.item_id == a.item.id, ItemMember.role_key.in_(config["roles"])
                )
            )
        }
        if not users:
            return "nobody in those roles"
        a.ctx.emit(
            "notify.requested",
            entity_type="item",
            entity_id=a.item.id,
            workspace_id=a.item.workspace_id,
            payload={
                "kind": "automation",
                "user_ids": sorted(users),
                "title": config["message"] or f"{a.rule_name}: {a.item.name}",
                "body": a.item.name,
                "actor_display": f"Automation: {a.rule_name}",
            },
        )
        return f"notified {len(users)}"


class NotifyUsers(Action):
    type = "notify_users"
    label = "Notify specific people"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        if not config.get("user_ids"):
            raise ValidationFailed("choose at least one person")
        return {"user_ids": [str(u) for u in config["user_ids"]], "message": config.get("message") or ""}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        a.ctx.emit(
            "notify.requested",
            entity_type="item",
            entity_id=a.item.id,
            workspace_id=a.item.workspace_id,
            payload={
                "kind": "automation",
                "user_ids": config["user_ids"],
                "title": config["message"] or f"{a.rule_name}: {a.item.name}",
                "body": a.item.name,
                "actor_display": f"Automation: {a.rule_name}",
            },
        )
        return f"notified {len(config['user_ids'])}"


class ArchiveItem(Action):
    type = "archive"
    label = "Archive the item"

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        if a.item.is_archived:
            return "already archived"
        a.item.is_archived = True
        a.item.archive_source = "automation"
        a.item.archive_ref = a.rule_name[:200]
        a.item.archived_at = utcnow()
        return "archived"


class Highlight(Action):
    type = "highlight"
    label = "Highlight the row"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        return {"color": config.get("color") or "yellow"}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        a.item.highlight_color = config["color"]
        a.item.highlight_rule_id = a.rule_id
        return f"highlight {config['color']}"


class ClearHighlight(Action):
    type = "clear_highlight"
    label = "Clear row highlight"

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        a.item.highlight_color = None
        a.item.highlight_rule_id = None
        return "highlight cleared"


class CreateTaskAction(Action):
    type = "create_task"
    label = "Create a task"

    def validate(self, config: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
        if not config.get("title"):
            raise ValidationFailed("task title is required")
        return {"title": config["title"], "due_in_days": config.get("due_in_days")}

    def run(self, a: ActionContext, config: dict[str, Any]) -> str:
        due = None
        if config.get("due_in_days") is not None:
            due = business_today() + timedelta(days=int(config["due_in_days"]))
        create_task_for(a.ctx, a.item, CreateTask(item_id=a.item.id, title=config["title"], due_date=due))
        return f"task '{config['title']}'"


ACTIONS: dict[str, Action] = {
    a.type: a
    for a in (
        SetField(), SetStatus(), ClearField(), AdvanceDate(), NotifyRoles(), NotifyUsers(),
        ArchiveItem(), Highlight(), ClearHighlight(), CreateTaskAction(),
    )
}  # fmt: skip


def catalog() -> dict[str, Any]:
    return {
        "triggers": [{"type": t.type, "label": t.label, "kind": t.kind} for t in TRIGGERS.values()],
        "actions": [{"type": a.type, "label": a.label} for a in ACTIONS.values()],
    }
