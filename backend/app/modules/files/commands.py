import uuid

from pydantic import Field

from app.core.errors import NotFound
from app.modules.files.models import FileVersion, StoredFile
from app.platform.commands import Command, CommandContext, handles
from app.platform.permissions import P_ITEMS_UPDATE


class RegisterFile(Command):
    """Record bytes that the upload endpoint already stored. Internal: the
    caller (e.g. rdti.add_document) authorises against the owner."""

    command_name = "files.register"
    permission = None
    exposed = False

    owner_type: str
    owner_id: uuid.UUID
    workspace_id: uuid.UUID | None
    client_id: uuid.UUID | None
    purpose: str = "general"
    name: str = Field(min_length=1, max_length=300)
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    replaces_file_id: uuid.UUID | None = None


@handles(RegisterFile)
def register_file(ctx: CommandContext, cmd: RegisterFile) -> dict[str, object]:
    if cmd.workspace_id is not None:
        ctx.authorize(P_ITEMS_UPDATE, cmd.workspace_id)
    else:
        ctx.authorized = True
    if cmd.replaces_file_id:
        f = ctx.session.get(StoredFile, cmd.replaces_file_id)
        if f is None or f.deleted_at is not None or f.owner_id != cmd.owner_id:
            raise NotFound("file not found")
        f.current_version += 1
        f.name = cmd.name
    else:
        f = StoredFile(
            owner_type=cmd.owner_type,
            owner_id=cmd.owner_id,
            workspace_id=cmd.workspace_id,
            client_id=cmd.client_id,
            name=cmd.name,
            purpose=cmd.purpose,
            current_version=1,
        )
        ctx.session.add(f)
    ctx.session.flush()
    v = FileVersion(
        file_id=f.id,
        version=f.current_version,
        storage_key=cmd.storage_key,
        original_name=cmd.name,
        mime_type=cmd.mime_type,
        size_bytes=cmd.size_bytes,
        sha256=cmd.sha256,
        uploaded_by=ctx.actor.user_id,
    )
    ctx.session.add(v)
    ctx.session.flush()
    return {"file_id": f.id, "version_id": v.id, "version": v.version}
