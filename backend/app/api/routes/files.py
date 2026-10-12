"""Endpoints that move files: CSV export and migration sources."""

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import CurrentActor, Exec, ReadDB
from app.core.config import get_settings
from app.core.db import read_session
from app.core.errors import ValidationFailed
from app.modules.items.queries import ItemQueryContext, list_items
from app.modules.migration import queries as migration_q
from app.modules.migration.commands import CreateRun
from app.modules.migration.sources import ErpNextClient, SourceTable, fetch_erpnext_projects, parse_csv
from app.modules.workspaces.models import Board, FiscalYear, Status
from app.modules.workspaces.queries import require_workspace
from app.modules.workspaces.schema import FieldResolver
from app.platform.fields.types import field_types
from app.platform.permissions import P_EXPORT, P_MIGRATION_RUN

router = APIRouter(tags=["files"])


class ExportBody(BaseModel):
    workspace_id: uuid.UUID
    board_ids: list[uuid.UUID] | None = None
    archived: bool = False
    filter: dict[str, Any] | None = None
    search: str | None = None
    sort: list[dict[str, str]] | None = None
    columns: list[str]


@router.post("/export/items.csv")
def export_items(body: ExportBody, actor: CurrentActor, s: ReadDB) -> StreamingResponse:
    """CSV of exactly the visible columns, UTF-8 with BOM so Excel opens
    Chinese text correctly (the old export's GBK round-trip problem)."""
    ws = require_workspace(s, actor, body.workspace_id, P_EXPORT)
    qc = ItemQueryContext(s, ws)
    holder: dict[str, FieldResolver] = {}
    cols = [qc.cols[c] for c in body.columns if c in qc.cols]
    statuses = {st.key: st.label for st in s.query(Status).filter(Status.workspace_id == ws.id)}
    fys = {str(f.id): f.label for f in s.query(FiscalYear)}
    boards = {str(b.id): b.name for b in s.query(Board).filter(Board.workspace_id == ws.id)}

    def cell(row: dict[str, Any], key: str) -> str:
        col = qc.cols[key]
        resolver = holder["r"]
        if col.source == "core":
            v = row.get(key)
            match key:
                case "client":
                    return row.get("client_name") or ""
                case "entity":
                    return row.get("entity_name") or ""
                case "status":
                    return statuses.get(v or "", v or "")
                case "fiscal_year":
                    return fys.get(v or "", "")
                case "board":
                    return boards.get(v or "", "")
            return "" if v is None else str(v)
        if col.source == "role":
            return "; ".join(resolver.user_label(u) for u in row["roles"].get(col.config["role"], []))
        if col.source == "mirror":
            v = row["mirrors"].get(key)
            return "" if v is None else str(v)
        v = row["data"].get(key)
        return field_types.get(col.type).to_text(v, col.config, resolver) if v is not None else ""

    def generate() -> Any:
        # Own session: the request-scoped one may already be closed while the
        # response streams.
        buf = io.StringIO()
        w = csv.writer(buf)
        buf.write("﻿")
        w.writerow([c.label for c in cols])
        offset = 0
        with read_session() as s2:
            holder["r"] = FieldResolver(s2)
            while True:
                page = list_items(
                    s2,
                    actor,
                    workspace_id=ws.id,
                    board_ids=body.board_ids,
                    archived=body.archived,
                    filter_tree=body.filter,
                    search=body.search,
                    sort=body.sort,
                    offset=offset,
                    limit=500,
                )
                for row in page["rows"]:
                    w.writerow([cell(row, c.key) for c in cols])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
                offset += 500
                if offset >= page["total"]:
                    break

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="export.csv"'},
    )


# --- migration sources -------------------------------------------------------------------
def _create_run(
    run: Exec, workspace_id: uuid.UUID, board_id: uuid.UUID, name: str, kind: str, t: SourceTable
) -> dict[str, Any]:
    res = run(
        CreateRun(
            workspace_id=workspace_id,
            board_id=board_id,
            name=name,
            source_kind=kind,
            source_meta=t.meta,
            headers=t.headers,
            rows=t.rows,
            keys=t.keys,
        )
    )
    return {"run_id": res.result["id"], "rows": len(t.rows), "headers": t.headers, "meta": t.meta}


@router.post("/migration/upload-csv")
async def migration_upload_csv(
    run: Exec,
    actor: CurrentActor,
    s: ReadDB,
    workspace_id: uuid.UUID = Form(...),
    board_id: uuid.UUID = Form(...),
    key_columns: str | None = Form(None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    require_workspace(s, actor, workspace_id, P_MIGRATION_RUN)
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise ValidationFailed("file too large", code="file_too_large")
    keys = [k.strip() for k in key_columns.split(",")] if key_columns else ["Client Name"]
    table = parse_csv(data, key_columns=keys)
    table.meta["filename"] = file.filename
    return _create_run(run, workspace_id, board_id, file.filename or "upload.csv", "csv", table)


class ErpNextPull(BaseModel):
    workspace_id: uuid.UUID
    board_id: uuid.UUID
    base_url: str
    api_key: str
    api_secret: str
    project_types: list[str]


@router.post("/migration/pull-erpnext")
def migration_pull_erpnext(body: ErpNextPull, run: Exec, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    """Credentials are used for this request only and never stored."""
    require_workspace(s, actor, body.workspace_id, P_MIGRATION_RUN)
    client = ErpNextClient(body.base_url, body.api_key, body.api_secret)
    try:
        table = fetch_erpnext_projects(client, body.project_types)
    finally:
        client.close()
    name = f"ERPNext: {', '.join(body.project_types)}"
    return _create_run(run, body.workspace_id, body.board_id, name, "erpnext", table)


@router.get("/migration/runs")
def migration_runs(workspace_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    return migration_q.list_runs(s, actor, workspace_id)


@router.get("/migration/runs/{run_id}")
def migration_run(run_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return migration_q.run_detail(s, actor, run_id)


@router.get("/migration/runs/{run_id}/rows")
def migration_rows(
    run_id: uuid.UUID,
    actor: CurrentActor,
    s: ReadDB,
    only_issues: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return migration_q.run_rows(s, actor, run_id, only_issues=only_issues, limit=limit, offset=offset)
