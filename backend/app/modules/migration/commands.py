"""Migration runs: stage -> map -> validate -> prepare -> import -> reconcile.

Every step is a command, so a run leaves a complete audit trail, and the
import itself shares one batch id: rolling back a run is "revert batch".
"""

import re
import uuid
from collections import Counter
from typing import Any

from pydantic import Field
from sqlalchemy import func, insert, select

from app.core.errors import NotFound, ValidationFailed
from app.modules.activity.commands import RevertChanges
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.collaboration.models import Comment
from app.modules.identity.models import User
from app.modules.items.models import Item
from app.modules.items.service import ItemWriter
from app.modules.migration.mapping import EMPTY, NEW, MappingContext, Target, distinct_values, render_name
from app.modules.migration.models import ExternalRef, MigrationRow, MigrationRun
from app.modules.workspaces.commands import slugify
from app.modules.workspaces.models import Board, FieldDefinition, LookupList, LookupValue, Status, Workspace
from app.platform.commands import Command, CommandContext, handles
from app.platform.fields.types import FieldValueError, clean_text
from app.platform.permissions import P_MIGRATION_RUN

DEFAULT_OPTIONS: dict[str, Any] = {
    "name_template": "{client} - {board}",
    "create_clients": True,
    "create_placeholder_users": True,
    "client_fields": "fill_empty",  # fill_empty | overwrite
    "comment_author": "Imported",
    "update_existing_items": True,
}


def _run(ctx: CommandContext, run_id: uuid.UUID) -> MigrationRun:
    run = ctx.session.get(MigrationRun, run_id)
    if run is None:
        raise NotFound("migration run not found")
    ctx.authorize(P_MIGRATION_RUN, run.workspace_id)
    return run


def _mctx(ctx: CommandContext, run: MigrationRun) -> MappingContext:
    ws = ctx.session.get(Workspace, run.workspace_id)
    board = ctx.session.get(Board, run.board_id) if run.board_id else None
    if ws is None or board is None:
        raise ValidationFailed("the run needs a workspace and a target board")
    return MappingContext(ctx.session, ws, board)


# --- 1. stage ---------------------------------------------------------------------------
class CreateRun(Command):
    command_name = "migration.create_run"
    permission = P_MIGRATION_RUN

    workspace_id: uuid.UUID
    board_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    source_kind: str = "csv"
    source_meta: dict[str, Any] = {}
    headers: list[str]
    rows: list[dict[str, Any]] = Field(max_length=50000)
    keys: list[str]


@handles(CreateRun)
def create_run(ctx: CommandContext, cmd: CreateRun) -> dict[str, Any]:
    ws = ctx.session.get(Workspace, cmd.workspace_id)
    board = ctx.session.get(Board, cmd.board_id)
    if ws is None or board is None or board.workspace_id != ws.id:
        raise NotFound("workspace/board not found")
    ctx.authorize(P_MIGRATION_RUN, ws.id)
    if len(cmd.keys) != len(cmd.rows):
        raise ValidationFailed("keys and rows differ in length")
    run = MigrationRun(
        workspace_id=ws.id,
        board_id=board.id,
        name=cmd.name,
        source_kind=cmd.source_kind,
        source_meta={**cmd.source_meta, "headers": cmd.headers, "row_count": len(cmd.rows)},
        mapping={},
        status="draft",
        created_by=ctx.actor.user_id,
        batch_id=uuid.uuid4(),
    )
    ctx.session.add(run)
    ctx.session.flush()
    mctx = MappingContext(ctx.session, ws, board)
    run.mapping = {"columns": mctx.suggest(cmd.headers), "values": {}, "options": dict(DEFAULT_OPTIONS)}
    if cmd.rows:
        ctx.session.execute(
            insert(MigrationRow),
            [
                {"run_id": run.id, "row_no": i + 1, "source_key": k[:300], "raw": r}
                for i, (r, k) in enumerate(zip(cmd.rows, cmd.keys, strict=True))
            ],
        )
    _auto_value_maps(ctx, run, mctx)
    return {"id": str(run.id)}


def _rows(ctx: CommandContext, run: MigrationRun) -> list[MigrationRow]:
    return list(
        ctx.session.scalars(
            select(MigrationRow).where(MigrationRow.run_id == run.id).order_by(MigrationRow.row_no)
        )
    )


def _auto_value_maps(ctx: CommandContext, run: MigrationRun, mctx: MappingContext) -> None:
    """Pre-fill value maps: existing matches are left implicit; unknown values
    are marked NEW (create) so the user only reviews what is genuinely new."""
    rows = [r.raw for r in _rows(ctx, run)]
    values = dict(run.mapping.get("values", {}))
    for header, tkey in run.mapping["columns"].items():
        tg = mctx.targets.get(tkey)
        if tg is None or not tg.value_mapped:
            continue
        vm = dict(values.get(header, {}))
        multi = tg.type in ("multi_select", "lookup_multi", "users")
        for raw in distinct_values(rows, header, multi):
            if raw in vm:
                continue
            try:
                mctx.parse_value(tg, raw, {})
            except FieldValueError:
                vm[raw] = NEW if _can_create(tg, run) else EMPTY
        values[header] = vm
    run.mapping = {**run.mapping, "values": values}


def _can_create(tg: Target, run: MigrationRun) -> bool:
    if tg.type in ("user", "users"):
        return bool(run.mapping.get("options", {}).get("create_placeholder_users", True))
    return tg.type in ("status", "select", "multi_select", "lookup", "lookup_multi")


# --- 2. map -----------------------------------------------------------------------------
class UpdateMapping(Command):
    command_name = "migration.update_mapping"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID
    columns: dict[str, str] | None = None
    values: dict[str, dict[str, Any]] | None = None
    options: dict[str, Any] | None = None


@handles(UpdateMapping)
def update_mapping(ctx: CommandContext, cmd: UpdateMapping) -> None:
    run = _run(ctx, cmd.run_id)
    if run.status in ("committing", "committed"):
        raise ValidationFailed("run already imported")
    mctx = _mctx(ctx, run)
    m = dict(run.mapping)
    if cmd.columns is not None:
        bad = {h: t for h, t in cmd.columns.items() if t != "ignore" and t not in mctx.targets}
        if bad:
            raise ValidationFailed("unknown targets", details={"columns": bad})
        m["columns"] = {**m.get("columns", {}), **cmd.columns}
    if cmd.values is not None:
        m["values"] = {**m.get("values", {}), **cmd.values}
    if cmd.options is not None:
        m["options"] = {**m.get("options", {}), **cmd.options}
    run.mapping = m
    run.status = "draft"
    _auto_value_maps(ctx, run, mctx)


# --- 3. validate ----------------------------------------------------------------------------
def plan_row(
    mctx: MappingContext, mapping: dict[str, Any], raw: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan: dict[str, Any] = {"client": {"data": {}}, "entity": {}, "contact": {}, "item": {}, "comments": []}
    issues: list[dict[str, Any]] = []
    for header, tkey in mapping.get("columns", {}).items():
        if tkey == "ignore" or header not in raw:
            continue
        value = raw[header]
        if tkey == "comment":
            if isinstance(value, list):
                plan["comments"] += [c for c in value if c.get("body")]
            else:
                text = clean_text(value)
                if text:
                    plan["comments"].append({"body": text})
            continue
        tg = mctx.targets.get(tkey)
        if tg is None:
            issues.append({"column": header, "level": "error", "message": f"unknown target {tkey}"})
            continue
        try:
            v = mctx.parse_value(tg, value, mapping.get("values", {}).get(header, {}))
        except FieldValueError as e:
            level = "warning" if e.code == "pending_new" else "error"
            issues.append({"column": header, "level": level, "message": str(e), "value": str(value)[:200]})
            continue
        if v in (None, [], {}):
            continue
        group, _, rest = tkey.partition(".")
        if group == "item":
            plan["item"][rest] = v
        elif group == "client":
            if rest.startswith("data."):
                plan["client"]["data"][rest[5:]] = v
            else:
                plan["client"][rest] = v
        else:
            plan[group][rest] = v
    if not plan["client"].get("name"):
        issues.append({"column": None, "level": "error", "message": "no client name"})
    return plan, issues


class ValidateRun(Command):
    command_name = "migration.validate"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID


@handles(ValidateRun)
def validate_run(ctx: CommandContext, cmd: ValidateRun) -> dict[str, Any]:
    run = _run(ctx, cmd.run_id)
    if run.status in ("committing", "committed"):
        raise ValidationFailed("run already imported")
    mctx = _mctx(ctx, run)
    stats: Counter[str] = Counter()
    clients_existing = {
        n.lower() for n in ctx.session.scalars(select(Client.name).where(Client.deleted_at.is_(None)))
    }
    new_clients: set[str] = set()
    for row in _rows(ctx, run):
        plan, issues = plan_row(mctx, run.mapping, row.raw)
        row.normalized = plan
        row.issues = issues
        row.outcome = None
        if any(i["level"] == "error" for i in issues):
            stats["error_rows"] += 1
        elif issues:
            stats["warning_rows"] += 1
        else:
            stats["ok_rows"] += 1
        name = (plan["client"].get("name") or "").lower()
        if name and name not in clients_existing:
            new_clients.add(name)
    pending_new = {
        h: [v for v, t in vm.items() if t == NEW] for h, vm in run.mapping.get("values", {}).items()
    }
    run.stats = {
        **dict(stats),
        "rows": sum(stats.values()),
        "new_clients": len(new_clients),
        "pending_new_values": {h: v for h, v in pending_new.items() if v},
    }
    run.status = "validated"
    return run.stats


# --- 4. prepare (create options / users / statuses that are marked NEW) ----------------------
class PrepareRun(Command):
    command_name = "migration.prepare"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID


@handles(PrepareRun)
def prepare_run(ctx: CommandContext, cmd: PrepareRun) -> dict[str, int]:
    run = _run(ctx, cmd.run_id)
    mctx = _mctx(ctx, run)
    s = ctx.session
    created: Counter[str] = Counter()
    values = {h: dict(vm) for h, vm in run.mapping.get("values", {}).items()}
    for header, vm in values.items():
        tkey = run.mapping["columns"].get(header)
        tg = mctx.targets.get(tkey or "")
        if tg is None:
            continue
        for raw, target in list(vm.items()):
            if target != NEW:
                continue
            if tg.type == "status":
                key = _unique_key(slugify(raw), {st.key for st in mctx.statuses})
                pos = (max((st.position for st in mctx.statuses), default=0)) + 1
                st = Status(
                    workspace_id=run.workspace_id,
                    scope="item",
                    key=key,
                    label=raw,
                    category="active",
                    position=pos,
                )
                s.add(st)
                mctx.statuses.append(st)
                vm[raw] = key
                created["statuses"] += 1
            elif tg.type in ("select", "multi_select"):
                fd = s.scalar(
                    select(FieldDefinition).where(
                        FieldDefinition.workspace_id == run.workspace_id,
                        FieldDefinition.entity_kind
                        == ("client" if tkey and tkey.startswith("client.") else "item"),
                        FieldDefinition.key == tkey.split(".")[-1],  # type: ignore[union-attr]
                    )
                )
                if fd is None:
                    continue
                opts = list(fd.config.get("options", []))
                key = _unique_key(slugify(raw), {o["key"] for o in opts})
                opts.append({"key": key, "label": raw, "color": "gray"})
                fd.config = {**fd.config, "options": opts}
                tg.config = fd.config
                vm[raw] = key
                created["options"] += 1
            elif tg.type in ("lookup", "lookup_multi"):
                lst = s.scalar(select(LookupList).where(LookupList.key == tg.config["list"]))
                if lst is None:
                    continue
                v = LookupValue(list_id=lst.id, label=raw)
                s.add(v)
                s.flush()
                vm[raw] = str(v.id)
                created["lookup_values"] += 1
            elif tg.type in ("user", "users"):
                email = f"{slugify(raw).replace('_', '.')}.{uuid.uuid4().hex[:6]}@placeholder.invalid"
                u = User(email=email, full_name=raw, is_placeholder=True, is_active=True, aliases=[raw])
                s.add(u)
                s.flush()
                vm[raw] = str(u.id)
                created["placeholder_users"] += 1
    run.mapping = {**run.mapping, "values": values}
    run.status = "prepared"
    return dict(created)


def _unique_key(base: str, existing: set[str]) -> str:
    key, n = base, 2
    while key in existing:
        key = f"{base}_{n}"
        n += 1
    return key


# --- 5. import --------------------------------------------------------------------------------
class ImportRow(Command):
    command_name = "migration.import_row"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID
    row_id: int


@handles(ImportRow)
def import_row(ctx: CommandContext, cmd: ImportRow) -> dict[str, Any]:
    run = _run(ctx, cmd.run_id)
    s = ctx.session
    row = s.get(MigrationRow, cmd.row_id)
    if row is None or row.run_id != run.id:
        raise NotFound("row not found")
    mctx = _mctx(ctx, run)
    opts = {**DEFAULT_OPTIONS, **run.mapping.get("options", {})}
    plan, issues = plan_row(mctx, run.mapping, row.raw)
    if any(i["level"] == "error" for i in issues):
        row.outcome, row.issues = "error", issues
        return {"outcome": "error"}

    client = _upsert_client(ctx, plan, opts)
    entity = _upsert_entity(ctx, client, plan["entity"])
    _upsert_contact(ctx, client, plan["contact"])

    ext_type = f"{run.source_kind}:item:{run.board_id}"
    ref = s.scalar(
        select(ExternalRef).where(
            ExternalRef.system == run.source_kind,
            ExternalRef.external_type == ext_type,
            ExternalRef.external_id == row.source_key,
        )
    )
    writer = ItemWriter(ctx, mctx.ws)
    values = dict(plan["item"])
    values["client"] = str(client.id)
    if entity is not None and "entity" not in values:
        values["entity"] = str(entity.id)
    if not values.get("name"):
        fy_label = None
        if values.get("fiscal_year"):
            fy_label = next(
                (f.label for f in mctx.fiscal_years.values() if str(f.id) == values["fiscal_year"]), None
            )
        values["name"] = render_name(
            opts["name_template"],
            {
                "client": client.name,
                "board": mctx.board.name,
                "fiscal_year": fy_label or "",
                **{k.lower(): v for k, v in row.raw.items() if isinstance(v, str)},
            },
        )
    existing = s.get(Item, ref.entity_id) if ref else None
    if existing is not None and existing.deleted_at is None:
        if not opts["update_existing_items"]:
            row.outcome, row.item_id = "skipped", existing.id
            return {"outcome": "skipped"}
        for k, v in values.items():
            writer.set(existing, k, v)
        row.outcome, row.item_id, row.issues = "updated", existing.id, issues
        return {"outcome": "updated", "item_id": str(existing.id)}

    item = writer.create(mctx.board, values)
    s.flush()
    if ref is None:
        s.add(ExternalRef(system=run.source_kind, external_type=ext_type, external_id=row.source_key,
                          entity_type="item", entity_id=item.id))  # fmt: skip
    else:
        ref.entity_id = item.id
    for c in plan["comments"]:
        s.add(
            Comment(
                entity_type="item",
                entity_id=item.id,
                workspace_id=item.workspace_id,
                author_id=_user_by_name(ctx, c.get("author")),
                author_display=c.get("author") or opts["comment_author"],
                body=str(c["body"])[:20000],
                mentions=[],
            )
        )
    row.outcome, row.item_id, row.issues = "created", item.id, issues
    return {"outcome": "created", "item_id": str(item.id)}


def _user_by_name(ctx: CommandContext, name: str | None) -> uuid.UUID | None:
    if not name:
        return None
    from app.modules.workspaces.schema import FieldResolver

    uid = FieldResolver(ctx.session).find_user(name)
    return uuid.UUID(uid) if uid else None


def _upsert_client(ctx: CommandContext, plan: dict[str, Any], opts: dict[str, Any]) -> Client:
    s = ctx.session
    cp = plan["client"]
    name = cp["name"].strip()
    client = s.scalar(
        select(Client).where(func.lower(Client.name) == name.lower(), Client.deleted_at.is_(None))
    )
    if client is None:
        if not opts["create_clients"]:
            raise ValidationFailed(f"client '{name}' does not exist", code="unknown_client")
        client = Client(name=name, client_type="individual", data={})
        s.add(client)
        s.flush()
    if cp.get("partner") and client.partner_user_id is None:
        client.partner_user_id = uuid.UUID(cp["partner"])
    if cp["data"]:
        current = dict(client.data or {})
        for k, v in cp["data"].items():
            if opts["client_fields"] == "overwrite" or current.get(k) in (None, "", [], False):
                current[k] = v
        client.data = current
    return client


def _upsert_entity(ctx: CommandContext, client: Client, ep: dict[str, Any]) -> ClientEntity | None:
    s = ctx.session
    entity = s.scalar(
        select(ClientEntity).where(
            ClientEntity.client_id == client.id,
            ClientEntity.is_primary.is_(True),
            ClientEntity.deleted_at.is_(None),
        )
    )
    if not ep:
        return entity
    abn = re.sub(r"\D", "", str(ep.get("abn") or "")) or None
    if abn and len(abn) != 11:
        abn = None  # malformed legacy ABN: keep the row, drop the value
    if entity is None:
        entity = ClientEntity(
            client_id=client.id,
            name=client.name,
            entity_type=ep.get("entity_type", "individual"),
            abn=abn,
            year_end_month=ep.get("year_end_month"),
            is_primary=True,
        )
        s.add(entity)
        s.flush()
        if (
            ep.get("entity_type") in ("company", "trust", "partnership", "smsf")
            and client.client_type == "individual"
        ):
            client.client_type = ep["entity_type"]
        return entity
    if abn and not entity.abn:
        entity.abn = abn
    if ep.get("year_end_month") and not entity.year_end_month:
        entity.year_end_month = ep["year_end_month"]
    return entity


def _upsert_contact(ctx: CommandContext, client: Client, cp: dict[str, Any]) -> None:
    if not cp.get("name"):
        return
    s = ctx.session
    exists = s.scalar(
        select(Contact).where(
            Contact.client_id == client.id,
            func.lower(Contact.name) == cp["name"].lower(),
            Contact.deleted_at.is_(None),
        )
    )
    if exists is not None:
        return
    has_primary = s.scalar(
        select(Contact.id).where(
            Contact.client_id == client.id, Contact.is_primary.is_(True), Contact.deleted_at.is_(None)
        )
    )
    s.add(
        Contact(
            client_id=client.id,
            name=cp["name"],
            email=cp.get("email"),
            phone=cp.get("phone"),
            is_primary=not has_primary,
        )
    )


class FinishRun(Command):
    """Compute the reconciliation report after all rows were attempted."""

    command_name = "migration.finish"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID


@handles(FinishRun)
def finish_run(ctx: CommandContext, cmd: FinishRun) -> dict[str, Any]:
    run = _run(ctx, cmd.run_id)
    rows = _rows(ctx, run)
    outcomes = Counter(r.outcome or "not_attempted" for r in rows)
    headers = run.source_meta.get("headers", [])
    filled_source = {h: sum(1 for r in rows if clean_text(r.raw.get(h)) is not None) for h in headers}
    imported_items = {
        it.id: it
        for it in ctx.session.scalars(select(Item).where(Item.id.in_([r.item_id for r in rows if r.item_id])))
    }
    mctx = _mctx(ctx, run)
    writer = ItemWriter(ctx, mctx.ws)
    filled_target: dict[str, int] = {}
    for h, tkey in run.mapping.get("columns", {}).items():
        if not tkey.startswith("item."):
            continue
        key = tkey[5:]
        filled_target[h] = sum(
            1 for r in rows if r.item_id in imported_items
            and writer.current(imported_items[r.item_id], key) not in (None, "", [], {})
        )  # fmt: skip
    report = {
        "outcomes": dict(outcomes),
        "columns": [
            {
                "header": h,
                "target": run.mapping["columns"].get(h),
                "source_non_empty": filled_source.get(h, 0),
                "imported_non_empty": filled_target.get(h),
            }
            for h in headers
        ],
    }
    run.stats = {**(run.stats or {}), "report": report}
    run.status = "committed" if outcomes.get("error", 0) == 0 else "committed_with_errors"
    return report


class StartCommit(Command):
    """Hand the import to the worker (it can take minutes for big runs)."""

    command_name = "migration.start_commit"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID


@handles(StartCommit)
def start_commit(ctx: CommandContext, cmd: StartCommit) -> None:
    run = _run(ctx, cmd.run_id)
    if run.status not in ("validated", "prepared"):
        raise ValidationFailed("validate the run before importing", code="not_validated")
    pending = (run.stats or {}).get("pending_new_values") or {}
    if pending and run.status != "prepared":
        raise ValidationFailed("new values must be prepared first", code="not_prepared", details=pending)
    run.status = "committing"
    ctx.emit("migration.commit_requested", entity_type="migration_run", entity_id=run.id,
             workspace_id=run.workspace_id, payload={"run_id": str(run.id)})  # fmt: skip


class MarkRowError(Command):
    command_name = "migration.mark_row_error"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID
    row_id: int
    message: str


@handles(MarkRowError)
def mark_row_error(ctx: CommandContext, cmd: MarkRowError) -> None:
    run = _run(ctx, cmd.run_id)
    row = ctx.session.get(MigrationRow, cmd.row_id)
    if row is None or row.run_id != run.id:
        raise NotFound("row not found")
    row.outcome = "error"
    row.issues = [*(row.issues or []), {"column": None, "level": "error", "message": cmd.message[:1000]}]


class RollbackRun(Command):
    command_name = "migration.rollback"
    permission = P_MIGRATION_RUN

    run_id: uuid.UUID


@handles(RollbackRun)
def rollback_run(ctx: CommandContext, cmd: RollbackRun) -> dict[str, Any]:
    run = _run(ctx, cmd.run_id)
    if run.status not in ("committed", "committed_with_errors"):
        raise ValidationFailed("only imported runs can be rolled back")
    ctx.quiet = True  # reverting an import must not fire automations
    result = ctx.run(RevertChanges(batch_id=run.batch_id))
    run.status = "rolled_back"
    return result  # type: ignore[no-any-return]
