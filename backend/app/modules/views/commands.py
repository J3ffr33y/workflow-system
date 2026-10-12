import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.modules.views.models import SavedView
from app.modules.workspaces.models import Board, Workspace
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_VIEWS_PERSONAL, P_VIEWS_SHARED


class ViewColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    width: int | None = Field(default=None, ge=40, le=1200)
    hidden: bool = False
    pinned: Literal["left", "right"] | None = None


class ViewSort(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    dir: Literal["asc", "desc"] = "asc"


class ViewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[ViewColumn] = []
    filter: dict[str, Any] | None = None
    sort: list[ViewSort] = []
    search: str | None = None
    group_by: str | None = None
    row_height: Literal["compact", "normal", "tall"] = "normal"


def _check_scope(ctx: CommandContext, workspace_id: uuid.UUID, scope: str) -> None:
    ctx.authorize(P_VIEWS_SHARED if scope == "shared" else P_VIEWS_PERSONAL, workspace_id)


class SaveView(Command):
    """Create (view_id None) or update a saved view."""

    command_name = "views.save"
    permission = P_VIEWS_PERSONAL

    view_id: uuid.UUID | None = None
    workspace_id: uuid.UUID
    board_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    scope: Literal["personal", "shared"] = "personal"
    is_default: bool = False
    config: ViewConfig


@handles(SaveView)
def save_view(ctx: CommandContext, cmd: SaveView) -> dict[str, str]:
    s = ctx.session
    if s.get(Workspace, cmd.workspace_id) is None:
        raise NotFound("workspace not found")
    _check_scope(ctx, cmd.workspace_id, cmd.scope)
    if cmd.board_id:
        b = s.get(Board, cmd.board_id)
        if b is None or b.workspace_id != cmd.workspace_id:
            raise ValidationFailed("board is not in this workspace")
    if cmd.view_id:
        v = s.get(SavedView, cmd.view_id)
        if v is None:
            raise NotFound("view not found")
        if v.scope == "personal" and v.owner_id != ctx.actor.user_id:
            raise PermissionDenied("this is someone else's personal view")
        if v.scope == "shared":
            _check_scope(ctx, v.workspace_id, "shared")
    else:
        v = SavedView(workspace_id=cmd.workspace_id)
        s.add(v)
    v.board_id = cmd.board_id
    v.name = cmd.name.strip()
    v.scope = cmd.scope
    v.owner_id = ctx.actor.user_id if cmd.scope == "personal" else None
    v.config = cmd.config.model_dump(mode="json")
    s.flush()
    if cmd.is_default:
        # One default per (board, scope owner): shared defaults for everyone,
        # personal defaults override them for their owner.
        conds = [
            SavedView.workspace_id == cmd.workspace_id,
            SavedView.id != v.id,
            SavedView.scope == cmd.scope,
            SavedView.board_id.is_(None) if cmd.board_id is None else SavedView.board_id == cmd.board_id,
        ]
        if cmd.scope == "personal":
            conds.append(SavedView.owner_id == ctx.actor.user_id)
        for other in s.scalars(select(SavedView).where(*conds, SavedView.is_default.is_(True))):
            other.is_default = False
    v.is_default = cmd.is_default
    return {"id": str(v.id)}


class DeleteView(Command):
    command_name = "views.delete"
    permission = P_VIEWS_PERSONAL

    view_id: uuid.UUID


@handles(DeleteView)
def delete_view(ctx: CommandContext, cmd: DeleteView) -> None:
    v = ctx.session.get(SavedView, cmd.view_id)
    if v is None:
        raise NotFound("view not found")
    if v.scope == "personal":
        ctx.authorize(P_VIEWS_PERSONAL, v.workspace_id)
        if v.owner_id != ctx.actor.user_id:
            raise PermissionDenied("this is someone else's personal view")
    else:
        ctx.authorize(P_VIEWS_SHARED, v.workspace_id)
    ctx.session.delete(v)
