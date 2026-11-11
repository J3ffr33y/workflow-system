import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.core.errors import NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.workspaces.models import FieldDefinition
from app.modules.workspaces.schema import FieldResolver
from app.platform.commands import Command, CommandContext, handles
from app.platform.fields.types import FieldValueError, field_types
from app.platform.permissions import (
    P_CLIENTS_ARCHIVE,
    P_CLIENTS_DELETE,
    P_CLIENTS_WRITE,
    P_ITEMS_ARCHIVE,
)

CLIENT_TYPES = {"individual", "company", "partnership", "trust", "smsf", "other"}
ENTITY_TYPES = {"individual", "company", "partnership", "trust", "smsf", "other_incorporated", "other"}


def _client(ctx: CommandContext, client_id: uuid.UUID) -> Client:
    c = ctx.session.get(Client, client_id)
    if c is None or c.deleted_at is not None:
        raise NotFound("client not found")
    return c


def validate_custom_data(
    ctx: CommandContext, entity_kind: str, current: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """Validate a partial update of custom field values for clients/entities/contacts."""
    if not patch:
        return current
    defs = {
        f.key: f
        for f in ctx.session.scalars(
            select(FieldDefinition).where(
                FieldDefinition.entity_kind == entity_kind, FieldDefinition.is_archived.is_(False)
            )
        )
    }
    resolver = FieldResolver(ctx.session)
    out = dict(current or {})
    errors = {}
    for key, value in patch.items():
        fd = defs.get(key)
        if fd is None:
            errors[key] = "unknown field"
            continue
        try:
            v = field_types.get(fd.type).normalize(value, fd.config, resolver)
        except FieldValueError as e:
            errors[key] = str(e)
            continue
        if v in (None, [], {}):
            out.pop(key, None)
        else:
            out[key] = v
    if errors:
        raise ValidationFailed("invalid field values", details={"fields": errors})
    return out


def name_taken(ctx: CommandContext, name: str, exclude_id: uuid.UUID | None = None) -> bool:
    q = select(Client.id).where(func.lower(Client.name) == name.strip().lower(), Client.deleted_at.is_(None))
    if exclude_id:
        q = q.where(Client.id != exclude_id)
    return ctx.session.scalar(q) is not None


class EntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    entity_type: str = "individual"
    abn: str | None = None
    acn: str | None = None
    year_end_month: int | None = Field(default=None, ge=1, le=12)


class CreateClient(Command):
    command_name = "clients.create"
    permission = P_CLIENTS_WRITE
    scoped = False

    name: str = Field(min_length=1, max_length=300)
    client_type: str = "individual"
    partner_user_id: uuid.UUID | None = None
    notes: str | None = None
    data: dict[str, Any] = {}
    primary_entity: EntityInput | None = None


@handles(CreateClient)
def create_client(ctx: CommandContext, cmd: CreateClient) -> dict[str, str]:
    name = cmd.name.strip()
    if name_taken(ctx, name):
        raise ValidationFailed("a client with this name already exists", code="duplicate_name")
    if cmd.client_type not in CLIENT_TYPES:
        raise ValidationFailed(f"client_type must be one of {sorted(CLIENT_TYPES)}")
    c = Client(
        name=name,
        client_type=cmd.client_type,
        partner_user_id=cmd.partner_user_id,
        notes=cmd.notes,
        data=validate_custom_data(ctx, "client", {}, cmd.data),
    )
    ctx.session.add(c)
    ctx.session.flush()
    if cmd.primary_entity is not None:
        e = cmd.primary_entity
        if e.entity_type not in ENTITY_TYPES:
            raise ValidationFailed(f"entity_type must be one of {sorted(ENTITY_TYPES)}")
        ctx.session.add(
            ClientEntity(
                client_id=c.id,
                name=(e.name or name).strip(),
                entity_type=e.entity_type,
                abn=_clean_abn(e.abn),
                acn=e.acn,
                year_end_month=e.year_end_month,
                is_primary=True,
            )
        )
    ctx.session.flush()
    return {"id": str(c.id)}


class UpdateClient(Command):
    command_name = "clients.update"
    permission = P_CLIENTS_WRITE
    scoped = False

    client_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=300)
    client_type: str | None = None
    partner_user_id: uuid.UUID | None = None
    clear_partner: bool = False
    referred_by_contact_id: uuid.UUID | None = None
    notes: str | None = None
    data: dict[str, Any] = {}


@handles(UpdateClient)
def update_client(ctx: CommandContext, cmd: UpdateClient) -> None:
    c = _client(ctx, cmd.client_id)
    if cmd.name is not None and cmd.name.strip() != c.name:
        new = cmd.name.strip()
        if name_taken(ctx, new, exclude_id=c.id):
            raise ValidationFailed("a client with this name already exists", code="duplicate_name")
        # The primary entity is usually named after the client; keep them in step.
        for e in ctx.session.scalars(select(ClientEntity).where(ClientEntity.client_id == c.id)):
            if e.name == c.name:
                e.name = new
        c.name = new
    if cmd.client_type is not None:
        if cmd.client_type not in CLIENT_TYPES:
            raise ValidationFailed(f"client_type must be one of {sorted(CLIENT_TYPES)}")
        c.client_type = cmd.client_type
    if cmd.partner_user_id is not None:
        c.partner_user_id = cmd.partner_user_id
    if cmd.clear_partner:
        c.partner_user_id = None
    if cmd.referred_by_contact_id is not None:
        c.referred_by_contact_id = cmd.referred_by_contact_id
    if cmd.notes is not None:
        c.notes = cmd.notes
    if cmd.data:
        c.data = validate_custom_data(ctx, "client", c.data, cmd.data)


class ArchiveClient(Command):
    """Archive a client and the active items under it.

    Items are tagged ``client_archive`` + client id so that restoring the
    client restores exactly these items, never ones archived for other reasons.
    Items in workspaces where the actor lacks archive rights are skipped.
    """

    command_name = "clients.archive"
    permission = P_CLIENTS_ARCHIVE
    scoped = False

    client_id: uuid.UUID


@handles(ArchiveClient)
def archive_client(ctx: CommandContext, cmd: ArchiveClient) -> dict[str, int]:
    from app.modules.items.models import Item

    c = _client(ctx, cmd.client_id)
    c.is_archived = True
    archived = skipped = 0
    now = utcnow()
    for it in ctx.session.scalars(
        select(Item).where(Item.client_id == c.id, Item.is_archived.is_(False), Item.deleted_at.is_(None))
    ):
        if not ctx.actor.can(P_ITEMS_ARCHIVE, it.workspace_id):
            skipped += 1
            continue
        it.is_archived = True
        it.archive_source = "client_archive"
        it.archive_ref = str(c.id)
        it.archived_at = now
        archived += 1
    return {"archived_items": archived, "skipped_items": skipped}


class RestoreClient(Command):
    command_name = "clients.restore"
    permission = P_CLIENTS_ARCHIVE
    scoped = False

    client_id: uuid.UUID


@handles(RestoreClient)
def restore_client(ctx: CommandContext, cmd: RestoreClient) -> dict[str, int]:
    from app.modules.items.models import Item

    c = _client(ctx, cmd.client_id)
    c.is_archived = False
    restored = 0
    for it in ctx.session.scalars(
        select(Item).where(
            Item.client_id == c.id,
            Item.is_archived.is_(True),
            Item.archive_source == "client_archive",
            Item.archive_ref == str(c.id),
            Item.deleted_at.is_(None),
        )
    ):
        if not ctx.actor.can(P_ITEMS_ARCHIVE, it.workspace_id):
            continue
        it.is_archived = False
        it.archive_source = None
        it.archive_ref = None
        it.archived_at = None
        restored += 1
    return {"restored_items": restored}


class DeleteClient(Command):
    command_name = "clients.delete"
    permission = P_CLIENTS_DELETE
    scoped = False

    client_id: uuid.UUID


@handles(DeleteClient)
def delete_client(ctx: CommandContext, cmd: DeleteClient) -> None:
    from app.modules.items.models import Item

    c = _client(ctx, cmd.client_id)
    n = ctx.session.scalar(
        select(func.count()).select_from(Item).where(Item.client_id == c.id, Item.deleted_at.is_(None))
    )
    if n:
        raise ValidationFailed(
            f"client still has {n} item(s); archive or move them first",
            code="client_has_items",
            details={"items": n},
        )
    now = utcnow()
    c.deleted_at = now
    for e in ctx.session.scalars(select(ClientEntity).where(ClientEntity.client_id == c.id)):
        e.deleted_at = now
    for ct in ctx.session.scalars(select(Contact).where(Contact.client_id == c.id)):
        ct.deleted_at = now


# --- entities ---------------------------------------------------------------------------
def _clean_abn(abn: str | None) -> str | None:
    if not abn:
        return None
    digits = "".join(ch for ch in abn if ch.isdigit())
    if digits and len(digits) != 11:
        raise ValidationFailed("ABN must have 11 digits", code="bad_abn")
    return digits or None


class UpsertEntity(Command):
    command_name = "clients.upsert_entity"
    permission = P_CLIENTS_WRITE
    scoped = False

    client_id: uuid.UUID
    entity_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=300)
    entity_type: str = "individual"
    abn: str | None = None
    acn: str | None = None
    year_end_month: int | None = Field(default=None, ge=1, le=12)
    is_primary: bool | None = None
    data: dict[str, Any] = {}


@handles(UpsertEntity)
def upsert_entity(ctx: CommandContext, cmd: UpsertEntity) -> dict[str, str]:
    c = _client(ctx, cmd.client_id)
    if cmd.entity_type not in ENTITY_TYPES:
        raise ValidationFailed(f"entity_type must be one of {sorted(ENTITY_TYPES)}")
    s = ctx.session
    if cmd.entity_id:
        e = s.get(ClientEntity, cmd.entity_id)
        if e is None or e.client_id != c.id or e.deleted_at is not None:
            raise NotFound("entity not found")
    else:
        e = ClientEntity(client_id=c.id, name=cmd.name)
        s.add(e)
        has_primary = s.scalar(
            select(ClientEntity.id).where(
                ClientEntity.client_id == c.id,
                ClientEntity.is_primary.is_(True),
                ClientEntity.deleted_at.is_(None),
            )
        )
        if not has_primary and cmd.is_primary is None:
            e.is_primary = True
    e.name = cmd.name.strip()
    e.entity_type = cmd.entity_type
    e.abn = _clean_abn(cmd.abn)
    e.acn = cmd.acn
    e.year_end_month = cmd.year_end_month
    if cmd.data:
        e.data = validate_custom_data(ctx, "entity", e.data, cmd.data)
    s.flush()
    if cmd.is_primary:
        for other in s.scalars(
            select(ClientEntity).where(ClientEntity.client_id == c.id, ClientEntity.id != e.id)
        ):
            other.is_primary = False
        e.is_primary = True
    elif cmd.is_primary is False:
        e.is_primary = False
    return {"id": str(e.id)}


class DeleteEntity(Command):
    command_name = "clients.delete_entity"
    permission = P_CLIENTS_WRITE
    scoped = False

    entity_id: uuid.UUID


@handles(DeleteEntity)
def delete_entity(ctx: CommandContext, cmd: DeleteEntity) -> None:
    from app.modules.items.models import Item

    e = ctx.session.get(ClientEntity, cmd.entity_id)
    if e is None or e.deleted_at is not None:
        raise NotFound("entity not found")
    used = ctx.session.scalar(
        select(func.count()).select_from(Item).where(Item.entity_id == e.id, Item.deleted_at.is_(None))
    )
    if used:
        raise ValidationFailed(f"entity is used by {used} item(s)", code="entity_in_use")
    e.deleted_at = utcnow()


# --- contacts --------------------------------------------------------------------------
class UpsertContact(Command):
    command_name = "clients.upsert_contact"
    permission = P_CLIENTS_WRITE
    scoped = False

    contact_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    role: str | None = None
    is_primary: bool = False
    is_billing: bool = False
    is_referrer: bool = False
    channels: dict[str, Any] = {}
    notes: str | None = None


@handles(UpsertContact)
def upsert_contact(ctx: CommandContext, cmd: UpsertContact) -> dict[str, str]:
    s = ctx.session
    if cmd.client_id:
        _client(ctx, cmd.client_id)
    if cmd.contact_id:
        ct = s.get(Contact, cmd.contact_id)
        if ct is None or ct.deleted_at is not None:
            raise NotFound("contact not found")
    else:
        ct = Contact(name=cmd.name)
        s.add(ct)
    ct.client_id = cmd.client_id
    ct.name = cmd.name.strip()
    ct.email = cmd.email.strip().lower() if cmd.email else None
    ct.phone = cmd.phone
    ct.role = cmd.role
    ct.is_primary = cmd.is_primary
    ct.is_billing = cmd.is_billing
    ct.is_referrer = cmd.is_referrer
    ct.channels = {k: v for k, v in cmd.channels.items() if v not in (None, "")}
    ct.notes = cmd.notes
    s.flush()
    if cmd.is_primary and ct.client_id:
        # At most one primary contact per client (mirror columns rely on it).
        for other in s.scalars(
            select(Contact).where(
                Contact.client_id == ct.client_id, Contact.id != ct.id, Contact.is_primary.is_(True)
            )
        ):
            other.is_primary = False
    return {"id": str(ct.id)}


class DeleteContact(Command):
    command_name = "clients.delete_contact"
    permission = P_CLIENTS_WRITE
    scoped = False

    contact_id: uuid.UUID


@handles(DeleteContact)
def delete_contact(ctx: CommandContext, cmd: DeleteContact) -> None:
    ct = ctx.session.get(Contact, cmd.contact_id)
    if ct is None or ct.deleted_at is not None:
        raise NotFound("contact not found")
    ct.deleted_at = utcnow()


# --- single linked value (edited from a board's mirror column) ----------------------------
# Record fields a board may edit through a mirror column. Custom ``data.*``
# fields are always allowed; they are validated by their field definition.
ENTITY_EDITABLE = {"name", "abn", "acn", "entity_type", "year_end_month"}
CONTACT_EDITABLE = {"name", "email", "phone"}


class SetLinkedValue(Command):
    """Set one value on a client, its entity or its primary contact.

    Boards show client facts through mirror columns; editing such a cell lands
    here so the client record stays the single source of truth and every board
    and the client page see the change.
    """

    command_name = "clients.set_linked_value"
    permission = P_CLIENTS_WRITE
    scoped = False

    client_id: uuid.UUID
    of: str  # client | entity | contact
    field: str
    value: Any = None
    # Entity to change; defaults to the client's primary entity.
    entity_id: uuid.UUID | None = None


def primary_entity(ctx: CommandContext, client_id: uuid.UUID) -> ClientEntity | None:
    return ctx.session.scalar(
        select(ClientEntity)
        .where(
            ClientEntity.client_id == client_id,
            ClientEntity.deleted_at.is_(None),
        )
        .order_by(ClientEntity.is_primary.desc(), ClientEntity.created_at)
        .limit(1)
    )


def _primary_contact(ctx: CommandContext, client_id: uuid.UUID) -> Contact | None:
    return ctx.session.scalar(
        select(Contact)
        .where(Contact.client_id == client_id, Contact.is_primary.is_(True), Contact.deleted_at.is_(None))
        .order_by(Contact.created_at.desc())
        .limit(1)
    )


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@handles(SetLinkedValue)
def set_linked_value(ctx: CommandContext, cmd: SetLinkedValue) -> dict[str, Any]:
    c = _client(ctx, cmd.client_id)
    s = ctx.session
    if cmd.of == "client":
        if not cmd.field.startswith("data."):
            raise ValidationFailed(f"client field '{cmd.field}' cannot be edited here", code="read_only")
        key = cmd.field[5:]
        c.data = validate_custom_data(ctx, "client", c.data, {key: cmd.value})
        return {"value": c.data.get(key), "client_id": str(c.id)}

    if cmd.of == "entity":
        e: ClientEntity | None
        if cmd.entity_id:
            e = s.get(ClientEntity, cmd.entity_id)
            if e is None or e.client_id != c.id or e.deleted_at is not None:
                raise NotFound("entity not found")
        else:
            e = primary_entity(ctx, c.id)
        if e is None:
            if _blank(cmd.value):
                return {"value": None, "client_id": str(c.id)}
            # Typing an ABN for a client without an entity creates its primary entity.
            e = ClientEntity(
                client_id=c.id,
                name=c.name,
                entity_type=c.client_type if c.client_type in ENTITY_TYPES else "other",
                is_primary=True,
            )
            s.add(e)
        if cmd.field.startswith("data."):
            key = cmd.field[5:]
            e.data = validate_custom_data(ctx, "entity", e.data, {key: cmd.value})
            value: Any = e.data.get(key)
        elif cmd.field not in ENTITY_EDITABLE:
            raise ValidationFailed(f"entity field '{cmd.field}' cannot be edited here", code="read_only")
        elif cmd.field == "abn":
            e.abn = value = _clean_abn(cmd.value)
        elif cmd.field == "acn":
            e.acn = value = None if _blank(cmd.value) else str(cmd.value).strip()
        elif cmd.field == "name":
            if _blank(cmd.value):
                raise ValidationFailed("entity name is required", code="required")
            e.name = value = str(cmd.value).strip()
        elif cmd.field == "entity_type":
            if cmd.value not in ENTITY_TYPES:
                raise ValidationFailed(f"entity_type must be one of {sorted(ENTITY_TYPES)}")
            e.entity_type = value = cmd.value
        else:  # year_end_month
            try:
                month = None if _blank(cmd.value) else int(cmd.value)
            except (TypeError, ValueError):
                raise ValidationFailed("year end must be a month number 1-12") from None
            if month is not None and not 1 <= month <= 12:
                raise ValidationFailed("year end must be a month number 1-12")
            e.year_end_month = value = month
        s.flush()
        return {"value": value, "client_id": str(c.id), "entity_id": str(e.id)}

    if cmd.of == "contact":
        if cmd.field not in CONTACT_EDITABLE:
            raise ValidationFailed(f"contact field '{cmd.field}' cannot be edited here", code="read_only")
        ct = _primary_contact(ctx, c.id)
        text = None if _blank(cmd.value) else str(cmd.value).strip()
        if ct is None:
            if text is None:
                return {"value": None, "client_id": str(c.id)}
            if cmd.field != "name":
                raise ValidationFailed(
                    "this client has no primary contact yet; enter the contact name first",
                    code="no_contact",
                )
            ct = Contact(client_id=c.id, name=text, is_primary=True)
            s.add(ct)
        elif cmd.field == "name":
            if text is None:
                raise ValidationFailed("contact name is required", code="required")
            ct.name = text
        elif cmd.field == "email":
            ct.email = text.lower() if text else None
        else:
            ct.phone = text
        s.flush()
        return {"value": getattr(ct, cmd.field), "client_id": str(c.id)}

    raise ValidationFailed("of must be client, entity or contact", code="bad_config")
