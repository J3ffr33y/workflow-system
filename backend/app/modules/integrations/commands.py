import secrets
import uuid
from fnmatch import fnmatchcase
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from app.core.config import get_settings
from app.core.errors import NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.integrations.models import WebhookEndpoint
from app.modules.workspaces.models import Workspace
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_SYSTEM_ADMIN

# Event types a webhook may receive. Business records only: users, tokens,
# memberships and webhook endpoints themselves never leave the system this way.
PUBLIC_EVENT_PATTERNS: tuple[str, ...] = (
    "item.*",
    "item_member.*",
    "task.*",
    "task_member.*",
    "comment.*",
    "client.*",
    "client_entity.*",
    "contact.*",
    "board.*",
    "file.*",
)


def is_public_event(event_type: str) -> bool:
    return any(fnmatchcase(event_type, p) for p in PUBLIC_EVENT_PATTERNS)


def _new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def _check_url(url: str) -> str:
    url = url.strip()
    u = urlparse(url)
    allowed = ("https",) if get_settings().env == "prod" else ("https", "http")
    if u.scheme not in allowed or not u.netloc:
        raise ValidationFailed(f"webhook URL must be {' or '.join(allowed)}", code="bad_url")
    return url


def _check_patterns(patterns: list[str]) -> list[str]:
    clean = sorted({p.strip() for p in patterns if p.strip()})
    if not clean:
        raise ValidationFailed("choose at least one event type", code="no_events")
    for p in clean:
        # A pattern must stay inside the public set: "item.*" is fine, "*" or
        # "user.*" are not.
        probe = p.replace("*", "x")
        if not is_public_event(probe):
            raise ValidationFailed(f"event type '{p}' is not available to webhooks", code="bad_event_type")
    return clean


class SaveWebhook(Command):
    """Create (webhook_id None) or update a webhook endpoint. On create the
    signing secret is returned once."""

    command_name = "integrations.save_webhook"
    permission = P_SYSTEM_ADMIN
    scoped = False
    log_result = False

    webhook_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    event_types: list[str]
    workspace_id: uuid.UUID | None = None
    include_quiet: bool = False
    is_enabled: bool = True


@handles(SaveWebhook)
def save_webhook(ctx: CommandContext, cmd: SaveWebhook) -> dict[str, Any]:
    s = ctx.session
    if cmd.workspace_id and s.get(Workspace, cmd.workspace_id) is None:
        raise NotFound("workspace not found")
    url = _check_url(cmd.url)
    patterns = _check_patterns(cmd.event_types)
    if cmd.webhook_id is None:
        ep = WebhookEndpoint(secret=_new_secret(), created_by=ctx.actor.user_id)
        s.add(ep)
        created = True
    else:
        found = s.get(WebhookEndpoint, cmd.webhook_id)
        if found is None or found.deleted_at is not None:
            raise NotFound("webhook not found")
        ep, created = found, False
    ep.name = cmd.name.strip()
    ep.url = url
    ep.event_types = patterns
    ep.workspace_id = cmd.workspace_id
    ep.include_quiet = cmd.include_quiet
    ep.is_enabled = cmd.is_enabled
    s.flush()
    return {"id": str(ep.id), **({"secret": ep.secret} if created else {})}


class RotateWebhookSecret(Command):
    """Issue a new signing secret (returned once). The old one stops working
    immediately, so update the receiver right after."""

    command_name = "integrations.rotate_webhook_secret"
    permission = P_SYSTEM_ADMIN
    scoped = False
    session_only = True
    log_result = False

    webhook_id: uuid.UUID


@handles(RotateWebhookSecret)
def rotate_secret(ctx: CommandContext, cmd: RotateWebhookSecret) -> dict[str, str]:
    ep = ctx.session.get(WebhookEndpoint, cmd.webhook_id)
    if ep is None or ep.deleted_at is not None:
        raise NotFound("webhook not found")
    ep.secret = _new_secret()
    return {"id": str(ep.id), "secret": ep.secret}


class DeleteWebhook(Command):
    command_name = "integrations.delete_webhook"
    permission = P_SYSTEM_ADMIN
    scoped = False

    webhook_id: uuid.UUID


@handles(DeleteWebhook)
def delete_webhook(ctx: CommandContext, cmd: DeleteWebhook) -> None:
    ep = ctx.session.get(WebhookEndpoint, cmd.webhook_id)
    if ep is None or ep.deleted_at is not None:
        raise NotFound("webhook not found")
    ep.deleted_at = utcnow()
    ep.is_enabled = False
