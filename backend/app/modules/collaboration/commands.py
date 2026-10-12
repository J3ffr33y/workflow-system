"""Comments ("Updates"), @mentions and in-app notifications."""

import re
import uuid
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.modules.clients.models import Client
from app.modules.collaboration.models import Comment, Notification
from app.modules.identity.models import User
from app.modules.items.models import Item
from app.modules.tasks.models import Task
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_CLIENTS_WRITE, P_COMMENTS_WRITE

# Mentions inserted by the editor: @[Display Name](user:<uuid>)
MENTION_RE = re.compile(r"@\[([^\]]+)\]\(user:([0-9a-fA-F-]{36})\)")

COMMENTABLE = {"item", "client", "task"}


def _target(ctx: CommandContext, entity_type: str, entity_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    """Authorise and return (workspace_id, display name) for the commented entity."""
    s = ctx.session
    if entity_type == "item":
        it = s.get(Item, entity_id)
        if it is None or it.deleted_at is not None:
            raise NotFound("item not found")
        ctx.authorize(P_COMMENTS_WRITE, it.workspace_id)
        return it.workspace_id, it.name
    if entity_type == "task":
        t = s.get(Task, entity_id)
        if t is None or t.deleted_at is not None:
            raise NotFound("task not found")
        ctx.authorize(P_COMMENTS_WRITE, t.workspace_id)
        return t.workspace_id, t.title
    if entity_type == "client":
        c = s.get(Client, entity_id)
        if c is None or c.deleted_at is not None:
            raise NotFound("client not found")
        ctx.authorize(P_CLIENTS_WRITE, None)
        return None, c.name
    raise ValidationFailed(f"cannot comment on {entity_type}")


def extract_mentions(ctx: CommandContext, body: str) -> list[str]:
    ids = list(dict.fromkeys(m.group(2).lower() for m in MENTION_RE.finditer(body)))
    if not ids:
        return []
    valid = {
        str(u) for u in ctx.session.scalars(select(User.id).where(User.id.in_([uuid.UUID(i) for i in ids])))
    }
    return [i for i in ids if i in valid]


class AddComment(Command):
    command_name = "comments.add"
    permission = P_COMMENTS_WRITE

    entity_type: Literal["item", "client", "task"]
    entity_id: uuid.UUID
    body: str = Field(min_length=1, max_length=20000)
    parent_comment_id: uuid.UUID | None = None


@handles(AddComment)
def add_comment(ctx: CommandContext, cmd: AddComment) -> dict[str, str]:
    workspace_id, name = _target(ctx, cmd.entity_type, cmd.entity_id)
    mentions = extract_mentions(ctx, cmd.body)
    c = Comment(
        entity_type=cmd.entity_type,
        entity_id=cmd.entity_id,
        workspace_id=workspace_id,
        parent_comment_id=cmd.parent_comment_id,
        author_id=ctx.actor.user_id,
        author_display=ctx.actor.display,
        body=cmd.body.strip(),
        mentions=mentions,
    )
    ctx.session.add(c)
    ctx.session.flush()
    _emit_mentions(ctx, c, mentions, name)
    return {"id": str(c.id)}


def _emit_mentions(ctx: CommandContext, c: Comment, user_ids: list[str], entity_name: str) -> None:
    recipients = [u for u in user_ids if u != str(ctx.actor.user_id)]
    if recipients:
        ctx.emit(
            "notify.requested",
            entity_type=c.entity_type,
            entity_id=c.entity_id,
            workspace_id=c.workspace_id,
            payload={
                "kind": "mention",
                "user_ids": recipients,
                "title": f"{ctx.actor.display} mentioned you on {entity_name}",
                "body": MENTION_RE.sub(r"@\1", c.body)[:500],
                "comment_id": str(c.id),
            },
        )


class EditComment(Command):
    command_name = "comments.edit"
    permission = P_COMMENTS_WRITE

    comment_id: uuid.UUID
    body: str = Field(min_length=1, max_length=20000)


@handles(EditComment)
def edit_comment(ctx: CommandContext, cmd: EditComment) -> None:
    c = ctx.session.get(Comment, cmd.comment_id)
    if c is None or c.deleted_at is not None:
        raise NotFound("comment not found")
    _, name = _target(ctx, c.entity_type, c.entity_id)
    if c.author_id != ctx.actor.user_id and not ctx.actor.is_superadmin:
        raise PermissionDenied("only the author can edit a comment")
    before = set(c.mentions or [])
    c.body = cmd.body.strip()
    c.mentions = extract_mentions(ctx, c.body)
    c.edited_at = utcnow()
    _emit_mentions(ctx, c, [u for u in c.mentions if u not in before], name)


class DeleteComment(Command):
    command_name = "comments.delete"
    permission = P_COMMENTS_WRITE

    comment_id: uuid.UUID


@handles(DeleteComment)
def delete_comment(ctx: CommandContext, cmd: DeleteComment) -> None:
    c = ctx.session.get(Comment, cmd.comment_id)
    if c is None or c.deleted_at is not None:
        raise NotFound("comment not found")
    _target(ctx, c.entity_type, c.entity_id)
    if c.author_id != ctx.actor.user_id and not ctx.actor.is_superadmin:
        raise PermissionDenied("only the author can delete a comment")
    c.deleted_at = utcnow()


# --- notifications -----------------------------------------------------------------
class DeliverNotifications(Command):
    """Executed by the notifications subscriber in the worker."""

    command_name = "notifications.deliver"
    scoped = False

    event_id: int
    kind: str
    user_ids: list[uuid.UUID]
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    actor_display: str | None = None
    data: dict[str, Any] = {}


@handles(DeliverNotifications)
def deliver_notifications(ctx: CommandContext, cmd: DeliverNotifications) -> int:
    active = set(
        ctx.session.scalars(select(User.id).where(User.id.in_(cmd.user_ids), User.is_active.is_(True)))
    )
    rows = [
        {
            "id": uuid.uuid4(),
            "user_id": uid,
            "kind": cmd.kind,
            "title": cmd.title[:300],
            "body": cmd.body,
            "entity_type": cmd.entity_type,
            "entity_id": cmd.entity_id,
            "workspace_id": cmd.workspace_id,
            "actor_display": cmd.actor_display,
            "source_event_id": cmd.event_id,
            "data": cmd.data,
        }
        for uid in cmd.user_ids
        if uid in active
    ]
    if rows:
        ctx.session.execute(insert(Notification).values(rows).on_conflict_do_nothing())
    return len(rows)


class MarkNotificationsRead(Command):
    command_name = "notifications.mark_read"
    scoped = False

    notification_ids: list[uuid.UUID] = []
    all: bool = False


@handles(MarkNotificationsRead)
def mark_read(ctx: CommandContext, cmd: MarkNotificationsRead) -> None:
    q = update(Notification).where(Notification.user_id == ctx.actor.user_id, Notification.read_at.is_(None))
    if not cmd.all:
        q = q.where(Notification.id.in_(cmd.notification_ids))
    ctx.session.execute(q.values(read_at=utcnow()))
