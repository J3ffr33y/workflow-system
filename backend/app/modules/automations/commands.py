import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.core.errors import NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.automations.models import AutomationRule, AutomationRun
from app.modules.automations.registry import ACTIONS, TRIGGERS, ActionContext
from app.modules.items.models import Item
from app.modules.items.queries import ItemQueryContext
from app.modules.items.service import ItemWriter
from app.modules.workspaces.models import Board, Workspace
from app.modules.workspaces.schema import columns_by_key, item_columns
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_AUTOMATIONS_MANAGE
from app.platform.query.filters import compile_filter


class TriggerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    config: dict[str, Any] = {}


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    config: dict[str, Any] = {}


class SaveRule(Command):
    command_name = "automations.save_rule"
    permission = P_AUTOMATIONS_MANAGE

    rule_id: uuid.UUID | None = None
    workspace_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    enabled: bool = True
    trigger: TriggerSpec
    conditions: dict[str, Any] | None = None
    actions: list[ActionSpec] = Field(min_length=1, max_length=20)
    board_ids: list[uuid.UUID] = []


def validate_rule(
    ctx: CommandContext, ws: Workspace, cmd: SaveRule
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cols = columns_by_key(item_columns(ctx.session, ws))
    trig = TRIGGERS.get(cmd.trigger.type)
    if trig is None:
        raise ValidationFailed(f"unknown trigger {cmd.trigger.type}")
    trigger = {"type": trig.type, "config": trig.validate(cmd.trigger.config, cols)}
    actions = []
    for a in cmd.actions:
        act = ACTIONS.get(a.type)
        if act is None:
            raise ValidationFailed(f"unknown action {a.type}")
        actions.append({"type": act.type, "config": act.validate(a.config, cols)})
    if cmd.conditions:
        # Compile once to reject unknown fields/operators at save time.
        compile_filter(cmd.conditions, ItemQueryContext(ctx.session, ws).ref)
    for bid in cmd.board_ids:
        b = ctx.session.get(Board, bid)
        if b is None or b.workspace_id != ws.id:
            raise ValidationFailed("board is not in this workspace")
    return trigger, actions


@handles(SaveRule)
def save_rule(ctx: CommandContext, cmd: SaveRule) -> dict[str, str]:
    ws = ctx.session.get(Workspace, cmd.workspace_id)
    if ws is None:
        raise NotFound("workspace not found")
    ctx.authorize(P_AUTOMATIONS_MANAGE, ws.id)
    trigger, actions = validate_rule(ctx, ws, cmd)
    if cmd.rule_id:
        r = ctx.session.get(AutomationRule, cmd.rule_id)
        if r is None or r.deleted_at is not None or r.workspace_id != ws.id:
            raise NotFound("rule not found")
    else:
        r = AutomationRule(workspace_id=ws.id, created_by=ctx.actor.user_id)
        ctx.session.add(r)
    r.name = cmd.name.strip()
    r.description = cmd.description
    r.enabled = cmd.enabled
    r.trigger = trigger
    r.conditions = cmd.conditions
    r.actions = actions
    r.board_ids = [str(b) for b in cmd.board_ids]
    ctx.session.flush()
    return {"id": str(r.id)}


class SetRuleEnabled(Command):
    command_name = "automations.set_enabled"
    permission = P_AUTOMATIONS_MANAGE

    rule_id: uuid.UUID
    enabled: bool


@handles(SetRuleEnabled)
def set_rule_enabled(ctx: CommandContext, cmd: SetRuleEnabled) -> None:
    r = ctx.session.get(AutomationRule, cmd.rule_id)
    if r is None or r.deleted_at is not None:
        raise NotFound("rule not found")
    ctx.authorize(P_AUTOMATIONS_MANAGE, r.workspace_id)
    r.enabled = cmd.enabled


class DeleteRule(Command):
    command_name = "automations.delete_rule"
    permission = P_AUTOMATIONS_MANAGE

    rule_id: uuid.UUID


@handles(DeleteRule)
def delete_rule(ctx: CommandContext, cmd: DeleteRule) -> None:
    r = ctx.session.get(AutomationRule, cmd.rule_id)
    if r is None or r.deleted_at is not None:
        raise NotFound("rule not found")
    ctx.authorize(P_AUTOMATIONS_MANAGE, r.workspace_id)
    r.deleted_at = utcnow()
    r.enabled = False


class ExecuteRule(Command):
    """Apply a rule's actions to one item (worker, scheduler or "run now").

    Conditions are re-checked inside the transaction, so a rule never acts on
    an item that stopped matching between selection and execution.
    """

    command_name = "automations.execute"
    permission = P_AUTOMATIONS_MANAGE

    rule_id: uuid.UUID
    item_id: uuid.UUID
    trigger_source: str = "event"
    event_id: int | None = None
    dedupe_key: str | None = None


@handles(ExecuteRule)
def execute_rule(ctx: CommandContext, cmd: ExecuteRule) -> dict[str, Any]:
    s = ctx.session
    rule = s.get(AutomationRule, cmd.rule_id)
    if rule is None or rule.deleted_at is not None:
        raise NotFound("rule not found")
    ctx.authorize(P_AUTOMATIONS_MANAGE, rule.workspace_id)
    item = s.get(Item, cmd.item_id)
    if item is None or item.deleted_at is not None:
        raise NotFound("item not found")
    ws = s.get(Workspace, rule.workspace_id)
    assert ws is not None

    if cmd.dedupe_key and s.scalar(
        select(AutomationRun.id).where(AutomationRun.dedupe_key == cmd.dedupe_key)
    ):
        return {"status": "skipped", "reason": "already ran"}

    detail: dict[str, Any] = {"trigger": rule.trigger, "actions": []}
    matched = rule_matches_item(ctx, ws, rule, item)
    if not matched:
        return {"status": "skipped", "reason": "conditions not met"}

    writer = ItemWriter(ctx, ws)
    a = ActionContext(ctx=ctx, writer=writer, item=item, rule_id=rule.id, rule_name=rule.name)
    for spec in rule.actions:
        result = ACTIONS[spec["type"]].run(a, spec.get("config", {}))
        detail["actions"].append({"type": spec["type"], "result": result})
    s.flush()
    changes = sum(len(c.changes) for c in ctx._changes.values())
    s.add(
        AutomationRun(
            rule_id=rule.id,
            workspace_id=rule.workspace_id,
            item_id=item.id,
            trigger_source=cmd.trigger_source,
            event_id=cmd.event_id,
            dedupe_key=cmd.dedupe_key,
            status="succeeded",
            detail=detail,
            command_id=ctx.command_id,
            changes_count=changes,
        )
    )
    rule.run_count = (rule.run_count or 0) + 1
    rule.last_run_at = utcnow()
    return {"status": "succeeded", "changes": changes, "actions": detail["actions"]}


def rule_matches_item(ctx: CommandContext, ws: Workspace, rule: AutomationRule, item: Item) -> bool:
    if item.is_archived and not any(a["type"] == "clear_highlight" for a in rule.actions):
        return False
    if rule.board_ids and str(item.board_id) not in rule.board_ids:
        return False
    if not rule.conditions:
        return True
    qc = ItemQueryContext(ctx.session, ws)
    q = (
        qc.base()
        .with_only_columns(func.count())
        .where(Item.id == item.id, compile_filter(rule.conditions, qc.ref))
    )
    return bool(ctx.session.scalar(q))


class RecordRunFailure(Command):
    """Failures are recorded in their own transaction (the failed one rolled back)."""

    command_name = "automations.record_failure"
    exposed = False
    scoped = False

    rule_id: uuid.UUID
    workspace_id: uuid.UUID
    item_id: uuid.UUID | None
    trigger_source: str
    event_id: int | None = None
    dedupe_key: str | None = None
    error: str


@handles(RecordRunFailure)
def record_failure(ctx: CommandContext, cmd: RecordRunFailure) -> None:
    ctx.session.add(
        AutomationRun(
            rule_id=cmd.rule_id,
            workspace_id=cmd.workspace_id,
            item_id=cmd.item_id,
            trigger_source=cmd.trigger_source,
            event_id=cmd.event_id,
            dedupe_key=None,  # leave the key free so the next run retries
            status="failed",
            error=cmd.error[:4000],
            detail={"dedupe_key": cmd.dedupe_key},
        )
    )
