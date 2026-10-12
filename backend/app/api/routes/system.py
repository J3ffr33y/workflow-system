from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text

from app.api.deps import CurrentActor, ReadDB
from app.api.realtime import broadcaster
from app.core.config import get_settings
from app.core.errors import PermissionDenied
from app.core.time import utcnow
from app.modules.system import queries as system_q
from app.modules.workspaces import queries as ws_q
from app.platform.events.models import Event, EventDelivery
from app.platform.fields.types import field_types
from app.platform.jobs.models import JobRun
from app.platform.permissions import P_SYSTEM_ADMIN

router = APIRouter(tags=["system"])


@router.get("/health")
def health(s: ReadDB) -> dict[str, Any]:
    """Liveness + what is actually deployed (compare after every deploy)."""
    revision = s.scalar(text("SELECT version_num FROM alembic_version"))
    return {
        "status": "ok",
        "git_sha": get_settings().git_sha,
        "db_revision": revision,
        "time": utcnow().isoformat(),
    }


@router.get("/ready")
def ready(s: ReadDB) -> dict[str, Any]:
    s.execute(text("SELECT 1"))
    last_heartbeat = s.scalar(select(func.max(JobRun.started_at)).where(JobRun.job == "system.heartbeat"))
    worker_ok = last_heartbeat is not None and (utcnow() - last_heartbeat).total_seconds() < 300
    backlog = s.scalar(
        select(func.count()).select_from(EventDelivery).where(EventDelivery.status.in_(("pending", "failed")))
    )
    return {"database": True, "worker": worker_ok, "event_backlog": backlog}


@router.get("/meta/data-model")
def data_model(actor: CurrentActor, s: ReadDB) -> dict[str, Any]:
    """How data is stored: tables, columns, relations and configured fields.

    Open to every signed-in user on purpose: it shows structure only, never
    rows, so people curious about the system can learn it without admin rights.
    """
    tables = system_q.data_model()
    with_data = {t["name"] for t in tables if t["has_custom_data"]}
    catalog = ws_q.field_catalog(s, actor)
    for ws in catalog:
        for f in ws["fields"]:
            f["stored_in"] = None if f["mirror_of"] or f["table"] not in with_data else f"{f['table']}.data"
    types = {t.key: t.label for t in field_types.all()}
    return {"tables": tables, "custom_fields": catalog, "field_types": types}


@router.get("/realtime")
async def realtime(actor: CurrentActor) -> StreamingResponse:
    return StreamingResponse(
        broadcaster.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/system/deliveries")
def deliveries(
    actor: CurrentActor, s: ReadDB, status: str = "dead", limit: int = 100
) -> list[dict[str, Any]]:
    if not actor.can(P_SYSTEM_ADMIN):
        raise PermissionDenied("admins only")
    rows = s.execute(
        select(EventDelivery, Event.type, Event.entity_type, Event.entity_id)
        .join(Event, Event.id == EventDelivery.event_id)
        .where(EventDelivery.status == status)
        .order_by(EventDelivery.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": d.id,
            "event_id": d.event_id,
            "event_type": etype,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "subscriber": d.subscriber,
            "status": d.status,
            "attempts": d.attempts,
            "last_error": d.last_error,
            "updated_at": d.updated_at.isoformat(),
        }
        for d, etype, entity_type, entity_id in rows
    ]


@router.get("/system/jobs")
def job_runs(actor: CurrentActor, s: ReadDB, limit: int = 100) -> list[dict[str, Any]]:
    if not actor.can(P_SYSTEM_ADMIN):
        raise PermissionDenied("admins only")
    return [
        {
            "id": r.id,
            "job": r.job,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "duration_ms": r.duration_ms,
            "summary": r.summary,
            "error": r.error,
        }
        for r in s.scalars(
            select(JobRun).where(JobRun.job != "system.heartbeat").order_by(JobRun.id.desc()).limit(limit)
        )
    ]
