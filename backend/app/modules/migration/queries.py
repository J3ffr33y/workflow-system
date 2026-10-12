import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.migration.mapping import MappingContext, distinct_values
from app.modules.migration.models import MigrationRow, MigrationRun
from app.modules.workspaces.models import Board, Workspace
from app.modules.workspaces.queries import require_workspace
from app.platform.permissions import P_MIGRATION_RUN, Actor


def run_dict(r: MigrationRun) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "workspace_id": str(r.workspace_id),
        "board_id": str(r.board_id) if r.board_id else None,
        "name": r.name,
        "source_kind": r.source_kind,
        "source_meta": r.source_meta,
        "mapping": r.mapping,
        "status": r.status,
        "stats": r.stats,
        "batch_id": str(r.batch_id) if r.batch_id else None,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


def list_runs(s: Session, actor: Actor, workspace_id: uuid.UUID) -> list[dict[str, Any]]:
    require_workspace(s, actor, workspace_id, P_MIGRATION_RUN)
    return [
        run_dict(r)
        for r in s.scalars(
            select(MigrationRun)
            .where(MigrationRun.workspace_id == workspace_id)
            .order_by(MigrationRun.created_at.desc())
        )
    ]


def run_detail(s: Session, actor: Actor, run_id: uuid.UUID) -> dict[str, Any]:
    r = s.get(MigrationRun, run_id)
    if r is None:
        raise NotFound("run not found")
    require_workspace(s, actor, r.workspace_id, P_MIGRATION_RUN)
    ws = s.get(Workspace, r.workspace_id)
    board = s.get(Board, r.board_id) if r.board_id else None
    out = run_dict(r)
    if ws and board:
        mctx = MappingContext(s, ws, board)
        out["targets"] = [t.to_dict() for t in mctx.targets.values()]
        raws = [row.raw for row in s.scalars(select(MigrationRow).where(MigrationRow.run_id == r.id))]
        out["distinct"] = {}
        for header, tkey in (r.mapping.get("columns") or {}).items():
            tg = mctx.targets.get(tkey)
            if tg is not None and tg.value_mapped:
                multi = tg.type in ("multi_select", "lookup_multi", "users")
                out["distinct"][header] = distinct_values(raws, header, multi)
        out["outcomes"] = dict(
            s.execute(
                select(MigrationRow.outcome, func.count())
                .where(MigrationRow.run_id == r.id)
                .group_by(MigrationRow.outcome)
            ).all()
        )
    return out


def run_rows(
    s: Session,
    actor: Actor,
    run_id: uuid.UUID,
    *,
    only_issues: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    r = s.get(MigrationRun, run_id)
    if r is None:
        raise NotFound("run not found")
    require_workspace(s, actor, r.workspace_id, P_MIGRATION_RUN)
    q = select(MigrationRow).where(MigrationRow.run_id == run_id)
    if only_issues:
        q = q.where(func.jsonb_array_length(MigrationRow.issues) > 0)
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = s.scalars(q.order_by(MigrationRow.row_no).offset(offset).limit(min(limit, 1000)))
    return {
        "total": total,
        "rows": [
            {
                "id": row.id,
                "row_no": row.row_no,
                "source_key": row.source_key,
                "raw": row.raw,
                "normalized": row.normalized,
                "issues": row.issues,
                "outcome": row.outcome,
                "item_id": str(row.item_id) if row.item_id else None,
            }
            for row in rows
        ],
    }
