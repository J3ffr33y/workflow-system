"""Delivers business events to webhook endpoints.

One outbox subscriber fans out to every matching endpoint. Each endpoint has
its own ``webhook_deliveries`` row, so when one receiver is down the event is
retried (outbox backoff) only for the endpoints that have not yet accepted it.
Receivers must still be idempotent: delivery is at-least-once. They can use
``X-Flow-Event-Id`` to de-duplicate.

Signature: ``X-Flow-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of
"<t>.<raw body>" with the endpoint secret>``. Receivers should reject
timestamps older than a few minutes.
"""

import hashlib
import hmac
import json
import logging
import time
from fnmatch import fnmatchcase
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.db import read_session, write_session
from app.modules.integrations.commands import PUBLIC_EVENT_PATTERNS, is_public_event
from app.modules.integrations.models import WebhookDelivery, WebhookEndpoint
from app.platform.events.registry import EventRecord, Subscriber, subscribers

log = logging.getLogger("flow.webhooks")

TIMEOUT_SECONDS = 10.0

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def event_body(ev: EventRecord) -> dict[str, Any]:
    return {
        "id": ev.id,
        "type": ev.type,
        "occurred_at": ev.occurred_at.isoformat(),
        "workspace_id": str(ev.workspace_id) if ev.workspace_id else None,
        "entity_type": ev.entity_type,
        "entity_id": str(ev.entity_id) if ev.entity_id else None,
        "origin": ev.origin,
        "actor_id": str(ev.actor_id) if ev.actor_id else None,
        "data": ev.payload,
    }


def _matches(ep: WebhookEndpoint, ev: EventRecord) -> bool:
    if ep.workspace_id is not None and ev.workspace_id != ep.workspace_id:
        return False
    if ev.payload.get("quiet") and not ep.include_quiet:
        return False
    return any(fnmatchcase(ev.type, p) for p in ep.event_types)


def _record(ep_id: Any, ev: EventRecord, status: str, code: int | None, error: str | None) -> None:
    # Queue bookkeeping, not business data: written directly (ADR-0010).
    with write_session() as s, s.begin():
        stmt = insert(WebhookDelivery).values(
            endpoint_id=ep_id,
            event_id=ev.id,
            event_type=ev.type,
            status=status,
            attempts=1,
            response_status=code,
            last_error=error,
        )
        s.execute(
            stmt.on_conflict_do_update(
                index_elements=["endpoint_id", "event_id"],
                set_={
                    "status": status,
                    "attempts": WebhookDelivery.attempts + 1,
                    "response_status": code,
                    "last_error": error,
                },
            )
        )


def dispatch(ev: EventRecord) -> None:
    if not is_public_event(ev.type):
        return
    with read_session() as s:
        endpoints = [
            ep
            for ep in s.scalars(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.is_enabled.is_(True), WebhookEndpoint.deleted_at.is_(None)
                )
            )
            if _matches(ep, ev)
        ]
        if not endpoints:
            return
        done = set(
            s.scalars(
                select(WebhookDelivery.endpoint_id).where(
                    WebhookDelivery.event_id == ev.id, WebhookDelivery.status == "done"
                )
            )
        )
        targets = [(ep.id, ep.url, ep.secret) for ep in endpoints if ep.id not in done]
    if not targets:
        return
    body = json.dumps(event_body(ev), separators=(",", ":"), ensure_ascii=False).encode()
    failures = []
    with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport, follow_redirects=False) as http:
        for ep_id, url, secret in targets:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"flow-webhooks/{get_settings().git_sha}",
                "X-Flow-Event": ev.type,
                "X-Flow-Event-Id": str(ev.id),
                "X-Flow-Signature": sign(secret, int(time.time()), body),
            }
            try:
                r = http.post(url, content=body, headers=headers)
            except httpx.HTTPError as e:
                _record(ep_id, ev, "failed", None, repr(e)[:2000])
                failures.append(str(ep_id))
                continue
            if 200 <= r.status_code < 300:
                _record(ep_id, ev, "done", r.status_code, None)
            else:
                _record(ep_id, ev, "failed", r.status_code, r.text[:2000])
                failures.append(str(ep_id))
    if failures:
        # A plain exception (not AppError) so the outbox retries with backoff.
        raise RuntimeError(f"webhook delivery failed for endpoints {failures}")


subscribers.register(Subscriber(name="webhooks.dispatch", patterns=PUBLIC_EVENT_PATTERNS, handler=dispatch))
