"""Integration endpoints: webhook management and external ID lookup.

Inbound integrations need nothing special: they call the normal query routes
and ``POST /api/commands/<name>`` with an API token.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentActor, ReadDB
from app.modules.integrations import queries as integrations_q
from app.modules.migration import queries as migration_q
from app.platform.permissions import P_SYSTEM_ADMIN

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/events")
def event_catalog(actor: CurrentActor) -> list[str]:
    """Event type patterns a webhook can subscribe to."""
    return integrations_q.event_catalog()


@router.get("/webhooks")
def webhooks(actor: CurrentActor, s: ReadDB) -> list[dict[str, Any]]:
    actor.require(P_SYSTEM_ADMIN)
    return integrations_q.list_webhooks(s)


@router.get("/webhooks/{webhook_id}/deliveries")
def webhook_deliveries(
    webhook_id: uuid.UUID, actor: CurrentActor, s: ReadDB, limit: int = Query(100, ge=1, le=500)
) -> list[dict[str, Any]]:
    actor.require(P_SYSTEM_ADMIN)
    return integrations_q.list_deliveries(s, webhook_id, limit)


@router.get("/external-refs")
def external_refs(
    actor: CurrentActor,
    s: ReadDB,
    system: str | None = None,
    external_type: str | None = None,
    external_id: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    return migration_q.find_external_refs(
        s,
        actor,
        system=system,
        external_type=external_type,
        external_id=external_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
