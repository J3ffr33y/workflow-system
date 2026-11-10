import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.integrations.commands import PUBLIC_EVENT_PATTERNS
from app.modules.integrations.models import WebhookDelivery, WebhookEndpoint


def event_catalog() -> list[str]:
    return list(PUBLIC_EVENT_PATTERNS)


def list_webhooks(s: Session) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.deleted_at.is_(None)).order_by(WebhookEndpoint.name)
    )
    return [
        {
            "id": str(ep.id),
            "name": ep.name,
            "url": ep.url,
            "event_types": ep.event_types,
            "workspace_id": str(ep.workspace_id) if ep.workspace_id else None,
            "include_quiet": ep.include_quiet,
            "is_enabled": ep.is_enabled,
            "created_at": ep.created_at.isoformat(),
        }
        for ep in rows
    ]


def list_deliveries(s: Session, endpoint_id: uuid.UUID, limit: int = 100) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.id.desc())
        .limit(limit)
    )
    return [
        {
            "event_id": d.event_id,
            "event_type": d.event_type,
            "status": d.status,
            "attempts": d.attempts,
            "response_status": d.response_status,
            "last_error": d.last_error,
            "updated_at": d.updated_at.isoformat(),
        }
        for d in rows
    ]
