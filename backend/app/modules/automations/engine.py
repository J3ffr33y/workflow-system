"""Runs automation rules: on events (worker subscriber) and on schedule."""

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import read_session
from app.core.errors import AppError
from app.core.time import business_today
from app.modules.automations.commands import ExecuteRule, RecordRunFailure
from app.modules.automations.models import AutomationRule, AutomationRun
from app.modules.automations.registry import TRIGGERS, DateReached
from app.modules.items.models import Item
from app.modules.items.queries import ItemQueryContext
from app.modules.workspaces.models import Workspace
from app.platform.commands import Origin, bus
from app.platform.events.registry import EventRecord
from app.platform.permissions import Actor, ActorKind
from app.platform.query.filters import compile_filter

log = logging.getLogger("flow.automations")


def automation_actor(rule: AutomationRule) -> Actor:
    return Actor(kind=ActorKind.AUTOMATION, user_id=None, display=f"Automation: {rule.name}"[:200])


def _execute(
    rule: AutomationRule,
    item_id: uuid.UUID,
    *,
    source: str,
    depth: int,
    event_id: int | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any] | None:
    try:
        res = bus.execute(
            ExecuteRule(
                rule_id=rule.id,
                item_id=item_id,
                trigger_source=source,
                event_id=event_id,
                dedupe_key=dedupe_key,
            ),
            actor=automation_actor(rule),
            origin=Origin.AUTOMATION,
            depth=depth,
            idempotency_key=f"auto:{rule.id}:{item_id}:{event_id or dedupe_key}",
        )
        return res.result  # type: ignore[no-any-return]
    except Exception as e:
        message = e.message if isinstance(e, AppError) else repr(e)
        if not isinstance(e, AppError):
            log.exception("rule %s failed on item %s", rule.id, item_id)
        bus.execute(
            RecordRunFailure(
                rule_id=rule.id,
                workspace_id=rule.workspace_id,
                item_id=item_id,
                trigger_source=source,
                event_id=event_id,
                dedupe_key=dedupe_key,
                error=message,
            ),
            actor=automation_actor(rule),
            origin=Origin.AUTOMATION,
        )
        return None


def on_item_event(ev: EventRecord) -> None:
    """Subscriber for item.created / item.updated."""
    if ev.payload.get("quiet") or ev.workspace_id is None or ev.entity_id is None:
        return
    if ev.depth >= get_settings().automation_max_depth:
        log.warning("automation cascade stopped at depth %s (event %s)", ev.depth, ev.id)
        return
    changes = {c["field"]: [c["before"], c["after"]] for c in ev.payload.get("changes", [])}
    event_types = {t.type for t in TRIGGERS.values() if t.kind == "event"}
    with read_session() as s:
        rules = list(
            s.scalars(
                select(AutomationRule).where(
                    AutomationRule.workspace_id == ev.workspace_id,
                    AutomationRule.enabled.is_(True),
                    AutomationRule.deleted_at.is_(None),
                )
            )
        )
    for rule in rules:
        ttype = rule.trigger.get("type")
        if ttype not in event_types:
            continue
        if not TRIGGERS[ttype].matches_event(rule.trigger.get("config", {}), ev.type, changes):
            continue
        _execute(rule, ev.entity_id, source="event", depth=ev.depth + 1, event_id=ev.id)


def run_date_rules() -> str:
    """Hourly job: fire date-based rules for items whose date has arrived."""
    today = business_today()
    fired = skipped = 0
    with read_session() as s:
        rules = list(
            s.scalars(
                select(AutomationRule).where(
                    AutomationRule.enabled.is_(True), AutomationRule.deleted_at.is_(None)
                )
            )
        )
        work: list[tuple[AutomationRule, uuid.UUID, str]] = []
        for rule in rules:
            if rule.trigger.get("type") != DateReached.type:
                continue
            cfg = rule.trigger["config"]
            ws = s.get(Workspace, rule.workspace_id)
            if ws is None:
                continue
            qc = ItemQueryContext(s, ws)
            ref = qc.ref(cfg["field"])
            target = DateReached.target_date(cfg, today)
            cond = ref.typed == target if cfg.get("mode") == "on" else ref.typed <= target
            q = qc.base().where(Item.is_archived.is_(False), ref.typed.isnot(None), cond)
            if rule.board_ids:
                q = q.where(Item.board_id.in_([uuid.UUID(b) for b in rule.board_ids]))
            if rule.conditions:
                q = q.where(compile_filter(rule.conditions, qc.ref))
            for item_id, value in s.execute(q.with_only_columns(Item.id, ref.typed)):
                # Once per item per date value: pushing the date later re-arms the rule.
                key = f"{rule.id}:{item_id}:{value}"
                if s.scalar(select(AutomationRun.id).where(AutomationRun.dedupe_key == key)):
                    skipped += 1
                    continue
                work.append((rule, item_id, key))
    for rule, item_id, key in work:
        res = _execute(rule, item_id, source="schedule", depth=1, dedupe_key=key)
        if res and res.get("status") == "succeeded":
            fired += 1
    return f"fired {fired}, already done {skipped}"


def preview_rule(s: Any, rule: AutomationRule, limit: int = 200) -> list[dict[str, Any]]:
    """Items a rule would act on right now (dry run, no changes)."""
    ws = s.get(Workspace, rule.workspace_id)
    qc = ItemQueryContext(s, ws)
    q = qc.base().where(Item.is_archived.is_(False))
    if rule.board_ids:
        q = q.where(Item.board_id.in_([uuid.UUID(b) for b in rule.board_ids]))
    if rule.conditions:
        q = q.where(compile_filter(rule.conditions, qc.ref))
    if rule.trigger.get("type") == DateReached.type:
        cfg = rule.trigger["config"]
        ref = qc.ref(cfg["field"])
        target = DateReached.target_date(cfg, business_today())
        q = q.where(ref.typed == target if cfg.get("mode") == "on" else ref.typed <= target)
    return [{"id": str(i.id), "name": i.name} for i in s.scalars(q.limit(limit))]
