"""R&D report endpoints that move files or read the workbench. Writes are
commands (POST /api/commands/rdti.*), except upload, which must receive the
bytes first."""

import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentActor, Exec, ReadDB
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.modules.files import storage
from app.modules.rdti import export, queries
from app.modules.rdti.commands import AddDocument, passages_from_extract
from app.platform.docs.extract import SUPPORTED, extract, file_kind

router = APIRouter(prefix="/rdti", tags=["rdti"])


@router.get("/items/{item_id}")
def workbench(item_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return queries.workbench(s, actor, item_id)


@router.get("/items/{item_id}/passages")
def passages(
    item_id: uuid.UUID,
    actor: CurrentActor,
    s: ReadDB,
    file_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    unassigned: bool = False,
    search: str | None = None,
    ids: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    id_list = [uuid.UUID(x) for x in ids.split(",") if x] if ids else None
    return queries.passages(
        s,
        actor,
        item_id,
        file_id=file_id,
        activity_id=activity_id,
        unassigned=unassigned,
        search=search,
        ids=id_list,
        limit=limit,
    )


@router.get("/passages/{chunk_id}")
def passage(chunk_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return queries.passage_context(s, actor, chunk_id)


@router.get("/items/{item_id}/report")
def report(
    item_id: uuid.UUID, actor: CurrentActor, s: ReadDB, activity_id: uuid.UUID | None = None
) -> dict[str, Any]:
    return queries.report(s, actor, item_id, activity_id)


@router.get("/items/{item_id}/email-draft")
def email_draft(item_id: uuid.UUID, actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    return queries.email_draft(s, actor, item_id)


@router.post("/items/{item_id}/documents")
async def upload_document(
    item_id: uuid.UUID,
    run: Exec,
    actor: CurrentActor,
    s: ReadDB,
    file: UploadFile = File(...),
    replaces_file_id: uuid.UUID | None = Form(None),
    activity_id: uuid.UUID | None = Form(None),
) -> dict[str, Any]:
    queries.require_item(s, actor, item_id)
    name = (file.filename or "upload").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:300]
    kind = file_kind(name)
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise ValidationFailed("file too large", code="file_too_large")
    found = extract(data, name)
    key, sha = storage.save_bytes(data)
    try:
        res = run(
            AddDocument(
                item_id=item_id,
                name=name,
                storage_key=key,
                mime_type=SUPPORTED[kind],
                size_bytes=len(data),
                sha256=sha,
                passages=passages_from_extract(found),
                replaces_file_id=replaces_file_id,
                activity_id=activity_id,
            )
        )
    except Exception:
        storage.remove(key)  # nothing points at the bytes if the command failed
        raise
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in res.result.items()}


@router.get("/files/{file_id}/content")
def file_content(file_id: uuid.UUID, actor: CurrentActor, s: ReadDB, version: int | None = None) -> Response:
    v = queries.file_version_for_download(s, actor, file_id, version)
    return Response(
        storage.read_bytes(v.storage_key),
        media_type=v.mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(v.original_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/items/{item_id}/export.docx")
def export_docx(item_id: uuid.UUID, actor: CurrentActor, s: ReadDB, mode: str = "clean") -> Response:
    if mode not in ("clean", "review"):
        raise ValidationFailed("mode must be clean or review")
    data, totals = export.build_docx(s, actor, item_id, mode)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="rdti-report-{mode}.docx"',
            "X-Unsourced-Claims": str(totals.get("unsupported", 0)),
        },
    )
