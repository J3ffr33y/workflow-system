"""Writes for the R&D report module. All go through the command bus, so every
human and AI change shows in activity and can be traced."""

import difflib
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.core.errors import NotFound, ValidationFailed
from app.core.time import utcnow
from app.modules.clients.models import Client
from app.modules.files.commands import RegisterFile
from app.modules.files.models import StoredFile
from app.modules.items.models import Item
from app.modules.rdti import engine, rules
from app.modules.rdti.models import (
    RdtiActivity,
    RdtiAssessment,
    RdtiChecklistItem,
    RdtiChunk,
    RdtiCitation,
    RdtiClaim,
    RdtiReportSection,
)
from app.platform.ai_gateway import AiTask, run_task
from app.platform.commands import Command, CommandContext, handles
from app.platform.docs.extract import Passage
from app.platform.permissions import P_RDTI_APPROVE, P_RDTI_WRITE

MAX_PASSAGES = 400


# --- helpers ---------------------------------------------------------------------------
def _item(ctx: CommandContext, item_id: uuid.UUID, permission: str = P_RDTI_WRITE) -> Item:
    it = ctx.session.get(Item, item_id)
    if it is None or it.deleted_at is not None:
        raise NotFound("item not found")
    ctx.authorize(permission, it.workspace_id)
    return it


def _activity(ctx: CommandContext, activity_id: uuid.UUID, permission: str = P_RDTI_WRITE) -> RdtiActivity:
    a = ctx.session.get(RdtiActivity, activity_id)
    if a is None or a.deleted_at is not None:
        raise NotFound("activity not found")
    _item(ctx, a.item_id, permission)
    return a


def _section(ctx: CommandContext, section_id: uuid.UUID, permission: str = P_RDTI_WRITE) -> RdtiReportSection:
    s = ctx.session.get(RdtiReportSection, section_id)
    if s is None or s.deleted_at is not None:
        raise NotFound("section not found")
    _item(ctx, s.item_id, permission)
    return s


def _claim(ctx: CommandContext, claim_id: uuid.UUID) -> tuple[RdtiClaim, RdtiReportSection]:
    c = ctx.session.get(RdtiClaim, claim_id)
    if c is None:
        raise NotFound("claim not found")
    return c, _section(ctx, c.section_id)


def _consent(ctx: CommandContext, it: Item) -> tuple[uuid.UUID | None, bool]:
    if it.client_id is None:
        return None, False
    c = ctx.session.get(Client, it.client_id)
    return it.client_id, bool(c and (c.data or {}).get("ai_consent") is True)


def _passages(ctx: CommandContext, a: RdtiActivity) -> list[dict[str, Any]]:
    """Passages assigned to the activity, plus unassigned ones (material often
    arrives before anyone sorts it)."""
    rows = ctx.session.execute(
        select(RdtiChunk, StoredFile.name)
        .join(StoredFile, StoredFile.id == RdtiChunk.file_id)
        .where(
            RdtiChunk.item_id == a.item_id,
            RdtiChunk.is_current.is_(True),
            StoredFile.deleted_at.is_(None),
            (RdtiChunk.activity_id == a.id) | (RdtiChunk.activity_id.is_(None)),
        )
        .order_by(RdtiChunk.activity_id.is_(None), StoredFile.name, RdtiChunk.seq)
        .limit(MAX_PASSAGES)
    ).all()
    return [{"id": str(c.id), "text": c.text, "file": name, "location": c.location} for c, name in rows]


def _activity_dict(a: RdtiActivity) -> dict[str, Any]:
    return {"code": a.code, "title": a.title, "kind": a.kind, "description": a.description}


# --- documents -------------------------------------------------------------------------
class PassageIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    page: int | None = None
    location: str = ""
    bbox: list[float] | None = None


class AddDocument(Command):
    """Register an uploaded evidence file and its extracted passages. Called
    by the upload endpoint, which stores the bytes and extracts the text."""

    command_name = "rdti.add_document"
    permission = P_RDTI_WRITE
    exposed = False

    item_id: uuid.UUID
    name: str
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    passages: list[PassageIn]
    replaces_file_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None


@handles(AddDocument)
def add_document(ctx: CommandContext, cmd: AddDocument) -> dict[str, Any]:
    it = _item(ctx, cmd.item_id)
    if cmd.activity_id:
        _activity(ctx, cmd.activity_id)
    reg = ctx.run(
        RegisterFile(
            owner_type="item",
            owner_id=it.id,
            workspace_id=it.workspace_id,
            client_id=it.client_id,
            purpose="rdti_evidence",
            name=cmd.name,
            storage_key=cmd.storage_key,
            mime_type=cmd.mime_type,
            size_bytes=cmd.size_bytes,
            sha256=cmd.sha256,
            replaces_file_id=cmd.replaces_file_id,
        )
    )
    file_id, version_id = reg["file_id"], reg["version_id"]
    previous: dict[str, uuid.UUID | None] = {}
    if cmd.replaces_file_id:
        # Older passages stay (citations point at them) but stop being current;
        # their activity assignment carries over by matching text.
        for old in ctx.session.scalars(
            select(RdtiChunk).where(RdtiChunk.file_id == file_id, RdtiChunk.is_current)
        ):
            previous[old.text] = old.activity_id
            old.is_current = False
        _flag_citations_of_file(ctx, file_id, version_id)
    for i, p in enumerate(cmd.passages):
        ctx.session.add(
            RdtiChunk(
                item_id=it.id,
                file_id=file_id,
                file_version_id=version_id,
                seq=i,
                page=p.page,
                location=p.location[:60],
                bbox=p.bbox,
                text=p.text,
                activity_id=cmd.activity_id or previous.get(p.text),
            )
        )
    ctx.emit(
        "rdti.document_added",
        entity_type="item",
        entity_id=it.id,
        workspace_id=it.workspace_id,
        payload={"file_id": str(file_id), "passages": len(cmd.passages)},
    )
    return {"file_id": file_id, "version_id": version_id, "passages": len(cmd.passages)}


def _flag_citations_of_file(ctx: CommandContext, file_id: uuid.UUID, new_version_id: uuid.UUID) -> None:
    """A new file version means quotes were checked against old text: put
    the claims that rely on it back to review."""
    claim_ids = ctx.session.scalars(
        select(RdtiCitation.claim_id)
        .join(RdtiChunk, RdtiChunk.id == RdtiCitation.chunk_id)
        .where(RdtiChunk.file_id == file_id, RdtiCitation.file_version_id != new_version_id)
    ).all()
    for c in ctx.session.scalars(select(RdtiClaim).where(RdtiClaim.id.in_(set(claim_ids)))):
        if c.status == "supported":
            c.status = "needs_review"
            c.note = "Source file has a newer version; re-check this claim."
            c.confirmed_by = None
            c.confirmed_at = None


class RemoveDocument(Command):
    command_name = "rdti.remove_document"
    permission = P_RDTI_WRITE

    file_id: uuid.UUID


@handles(RemoveDocument)
def remove_document(ctx: CommandContext, cmd: RemoveDocument) -> None:
    f = ctx.session.get(StoredFile, cmd.file_id)
    if f is None or f.deleted_at is not None or f.owner_type != "item":
        raise NotFound("file not found")
    _item(ctx, f.owner_id)
    f.deleted_at = utcnow()
    for c in ctx.session.scalars(
        select(RdtiClaim)
        .join(RdtiCitation, RdtiCitation.claim_id == RdtiClaim.id)
        .join(RdtiChunk, RdtiChunk.id == RdtiCitation.chunk_id)
        .where(RdtiChunk.file_id == f.id)
    ):
        c.status = "needs_review"
        c.note = "A cited file was removed."
        c.confirmed_by = None


class AssignPassages(Command):
    command_name = "rdti.assign_passages"
    permission = P_RDTI_WRITE

    item_id: uuid.UUID
    chunk_ids: list[uuid.UUID] = Field(min_length=1, max_length=2000)
    activity_id: uuid.UUID | None


@handles(AssignPassages)
def assign_passages(ctx: CommandContext, cmd: AssignPassages) -> dict[str, int]:
    it = _item(ctx, cmd.item_id)
    if cmd.activity_id:
        a = _activity(ctx, cmd.activity_id)
        if a.item_id != it.id:
            raise ValidationFailed("activity belongs to another item")
    chunks = list(
        ctx.session.scalars(
            select(RdtiChunk).where(RdtiChunk.id.in_(cmd.chunk_ids), RdtiChunk.item_id == it.id)
        )
    )
    for c in chunks:
        c.activity_id = cmd.activity_id
    return {"updated": len(chunks)}


# --- activities ------------------------------------------------------------------------
class CreateActivity(Command):
    command_name = "rdti.create_activity"
    permission = P_RDTI_WRITE

    item_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["core", "supporting"] = "core"
    code: str | None = Field(default=None, max_length=20)
    supports_activity_id: uuid.UUID | None = None
    description: str | None = None


@handles(CreateActivity)
def create_activity(ctx: CommandContext, cmd: CreateActivity) -> dict[str, Any]:
    it = _item(ctx, cmd.item_id)
    _check_supports(ctx, it.id, cmd.kind, cmd.supports_activity_id)
    n = (
        ctx.session.scalar(
            select(func.count()).where(
                RdtiActivity.item_id == it.id,
                RdtiActivity.kind == cmd.kind,
                RdtiActivity.deleted_at.is_(None),
            )
        )
        or 0
    )
    a = RdtiActivity(
        item_id=it.id,
        workspace_id=it.workspace_id,
        code=(cmd.code or f"{'CA' if cmd.kind == 'core' else 'SA'}{n + 1}").strip(),
        title=cmd.title.strip(),
        kind=cmd.kind,
        supports_activity_id=cmd.supports_activity_id,
        description=cmd.description,
        position=n,
    )
    ctx.session.add(a)
    ctx.session.flush()
    return {"id": a.id, "code": a.code}


def _check_supports(ctx: CommandContext, item_id: uuid.UUID, kind: str, supports: uuid.UUID | None) -> None:
    if kind == "core" and supports:
        raise ValidationFailed("a core activity does not support another activity")
    if supports:
        target = ctx.session.get(RdtiActivity, supports)
        if target is None or target.item_id != item_id or target.kind != "core" or target.deleted_at:
            raise ValidationFailed("a supporting activity must point at a core activity of the same project")


class UpdateActivity(Command):
    command_name = "rdti.update_activity"
    permission = P_RDTI_WRITE

    activity_id: uuid.UUID
    title: str | None = Field(default=None, min_length=1, max_length=300)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    supports_activity_id: uuid.UUID | None = None
    clear_supports: bool = False
    description: str | None = None


@handles(UpdateActivity)
def update_activity(ctx: CommandContext, cmd: UpdateActivity) -> None:
    a = _activity(ctx, cmd.activity_id)
    if cmd.title is not None:
        a.title = cmd.title.strip()
    if cmd.code is not None:
        a.code = cmd.code.strip()
    if cmd.description is not None:
        a.description = cmd.description
    if cmd.clear_supports:
        a.supports_activity_id = None
    elif cmd.supports_activity_id:
        _check_supports(ctx, a.item_id, a.kind, cmd.supports_activity_id)
        a.supports_activity_id = cmd.supports_activity_id


class DeleteActivity(Command):
    command_name = "rdti.delete_activity"
    permission = P_RDTI_WRITE

    activity_id: uuid.UUID


@handles(DeleteActivity)
def delete_activity(ctx: CommandContext, cmd: DeleteActivity) -> None:
    a = _activity(ctx, cmd.activity_id)
    a.deleted_at = utcnow()
    for c in ctx.session.scalars(select(RdtiChunk).where(RdtiChunk.activity_id == a.id)):
        c.activity_id = None


# --- assessment ------------------------------------------------------------------------
class AssessActivity(Command):
    """Ask the model (or the offline stand-in) how well the material evidences
    each element. Elements a person has set by hand are left alone."""

    command_name = "rdti.assess_activity"
    permission = P_RDTI_WRITE

    activity_id: uuid.UUID
    overwrite_human: bool = False


@handles(AssessActivity)
def assess_activity(ctx: CommandContext, cmd: AssessActivity) -> dict[str, Any]:
    a = _activity(ctx, cmd.activity_id)
    it = ctx.session.get(Item, a.item_id)
    assert it is not None
    passages = _passages(ctx, a)
    if not passages:
        raise ValidationFailed("upload evidence for this project first", code="no_evidence")
    client_id, consent = _consent(ctx, it)
    system, user = engine.assess_prompt(_activity_dict(a), passages)
    answer = run_task(
        ctx.session,
        AiTask("rdti.assess", system, user, engine.ASSESS_SCHEMA, client_id, consent),
        lambda: engine.fake_assessment(a.kind, passages),
        command_id=ctx.command_id,
    )
    valid_ids = {p["id"] for p in passages}
    wanted = {e["key"] for e in rules.elements_for(a.kind)}
    existing = {
        x.element: x
        for x in ctx.session.scalars(select(RdtiAssessment).where(RdtiAssessment.activity_id == a.id))
    }
    written = 0
    for row in answer.data.get("elements", []):
        key = row.get("element")
        if key not in wanted or row.get("coverage") not in rules.COVERAGE:
            continue
        cur = existing.get(key)
        if cur is not None and cur.source == "human" and not cmd.overwrite_human:
            continue
        values = {
            "coverage": row["coverage"],
            "rationale": str(row.get("rationale", ""))[:4000],
            "summary_only": bool(row.get("summary_only")),
            "chunk_ids": [c for c in row.get("chunk_ids", []) if c in valid_ids][:20],
            "source": "ai",
            "rule_version": rules.RULESET_VERSION,
        }
        if cur is None:
            ctx.session.add(RdtiAssessment(activity_id=a.id, element=key, **values))
        else:
            for k, v in values.items():
                setattr(cur, k, v)
        written += 1
    return {"assessed": written, "provider": answer.provider}


class SetAssessment(Command):
    command_name = "rdti.set_assessment"
    permission = P_RDTI_WRITE

    activity_id: uuid.UUID
    element: str
    coverage: Literal["sufficient", "partial", "missing"]
    rationale: str = ""


@handles(SetAssessment)
def set_assessment(ctx: CommandContext, cmd: SetAssessment) -> None:
    a = _activity(ctx, cmd.activity_id)
    if cmd.element not in {e["key"] for e in rules.elements_for(a.kind)}:
        raise ValidationFailed("element does not apply to this activity")
    cur = ctx.session.scalar(
        select(RdtiAssessment).where(
            RdtiAssessment.activity_id == a.id, RdtiAssessment.element == cmd.element
        )
    )
    if cur is None:
        cur = RdtiAssessment(
            activity_id=a.id,
            element=cmd.element,
            chunk_ids=[],
            rule_version=rules.RULESET_VERSION,
            summary_only=False,
            coverage=cmd.coverage,
            rationale="",
            source="human",
        )
        ctx.session.add(cur)
    cur.coverage = cmd.coverage
    if cmd.rationale:
        cur.rationale = cmd.rationale
    cur.source = "human"


# --- checklist -------------------------------------------------------------------------
class GenerateChecklist(Command):
    """One checklist item per element that is missing or partial, built from
    the rule set. Items already open for the same gap are not repeated."""

    command_name = "rdti.generate_checklist"
    permission = P_RDTI_WRITE

    item_id: uuid.UUID


@handles(GenerateChecklist)
def generate_checklist(ctx: CommandContext, cmd: GenerateChecklist) -> dict[str, int]:
    it = _item(ctx, cmd.item_id)
    acts = list(
        ctx.session.scalars(
            select(RdtiActivity)
            .where(RdtiActivity.item_id == it.id, RdtiActivity.deleted_at.is_(None))
            .order_by(RdtiActivity.kind, RdtiActivity.position)
        )
    )
    open_keys = {
        (c.activity_id, c.element)
        for c in ctx.session.scalars(
            select(RdtiChecklistItem).where(
                RdtiChecklistItem.item_id == it.id,
                RdtiChecklistItem.deleted_at.is_(None),
                RdtiChecklistItem.status != "closed",
            )
        )
    }
    pos = ctx.session.scalar(select(func.count()).where(RdtiChecklistItem.item_id == it.id)) or 0
    created = skipped = 0
    for a in acts:
        for x in ctx.session.scalars(select(RdtiAssessment).where(RdtiAssessment.activity_id == a.id)):
            if x.coverage == "sufficient":
                continue
            if (a.id, x.element) in open_keys:
                skipped += 1
                continue
            el = rules.element(x.element)
            gap = "is missing" if x.coverage == "missing" else "needs more detail"
            ctx.session.add(
                RdtiChecklistItem(
                    item_id=it.id,
                    activity_id=a.id,
                    element=x.element,
                    question=f"{a.code} {a.title}: the {el['label'].lower()} {gap}. {el['question']}",
                    preferred=el["preferred"],
                    alternatives=list(el["alternatives"]),
                    example=el["example"],
                    status="draft",
                    position=pos,
                )
            )
            pos += 1
            created += 1
    return {"created": created, "skipped_existing": skipped}


class UpdateChecklistItem(Command):
    command_name = "rdti.update_checklist_item"
    permission = P_RDTI_WRITE

    checklist_item_id: uuid.UUID
    question: str | None = None
    preferred: str | None = None
    alternatives: list[str] | None = None
    example: str | None = None
    status: Literal["draft", "sent", "received", "closed"] | None = None
    delete: bool = False


@handles(UpdateChecklistItem)
def update_checklist_item(ctx: CommandContext, cmd: UpdateChecklistItem) -> None:
    c = ctx.session.get(RdtiChecklistItem, cmd.checklist_item_id)
    if c is None or c.deleted_at is not None:
        raise NotFound("checklist item not found")
    _item(ctx, c.item_id)
    if cmd.delete:
        c.deleted_at = utcnow()
        return
    for f in ("question", "preferred", "alternatives", "example", "status"):
        v = getattr(cmd, f)
        if v is not None:
            setattr(c, f, v)


class AddChecklistItem(Command):
    command_name = "rdti.add_checklist_item"
    permission = P_RDTI_WRITE

    item_id: uuid.UUID
    question: str = Field(min_length=1)
    activity_id: uuid.UUID | None = None
    preferred: str = ""
    alternatives: list[str] = []
    example: str = ""


@handles(AddChecklistItem)
def add_checklist_item(ctx: CommandContext, cmd: AddChecklistItem) -> dict[str, Any]:
    it = _item(ctx, cmd.item_id)
    pos = ctx.session.scalar(select(func.count()).where(RdtiChecklistItem.item_id == it.id)) or 0
    c = RdtiChecklistItem(
        item_id=it.id,
        activity_id=cmd.activity_id,
        element=None,
        question=cmd.question,
        preferred=cmd.preferred,
        alternatives=cmd.alternatives,
        example=cmd.example,
        status="draft",
        position=pos,
    )
    ctx.session.add(c)
    ctx.session.flush()
    return {"id": c.id}


# --- report ----------------------------------------------------------------------------
def _store_claims(
    ctx: CommandContext,
    section: RdtiReportSection,
    claims: list[dict[str, Any]],
    chunks: dict[str, RdtiChunk],
) -> None:
    parts: list[str] = []
    cursor = 0
    for cl in claims:
        text = " ".join(str(cl.get("text", "")).split())
        if not text:
            continue
        if parts:
            cursor += 1
        start, end = cursor, cursor + len(text)
        parts.append(text)
        cursor = end
        kind = "polish" if cl.get("kind") == "polish" else "fact"
        claim = RdtiClaim(
            section_id=section.id,
            start=start,
            end=end,
            text=text,
            status="unsupported",
            source="ai",
            fact_warning=kind == "polish" and engine.has_facts(text),
        )
        ctx.session.add(claim)
        ctx.session.flush()
        checks: list[engine.CitationCheck] = []
        if kind == "fact":
            for ci in cl.get("citations", [])[:5]:
                chunk = chunks.get(str(ci.get("chunk_id")))
                if chunk is None:
                    continue
                quote = str(ci.get("quote", ""))
                span = engine.locate_quote(chunk.text, quote)
                support, why = (
                    engine.support_heuristic(text, quote)
                    if span
                    else ("partial", "Quote not found verbatim in the source.")
                )
                ctx.session.add(
                    RdtiCitation(
                        claim_id=claim.id,
                        chunk_id=chunk.id,
                        quote=chunk.text[span[0] : span[1]] if span else quote,
                        quote_start=span[0] if span else None,
                        quote_end=span[1] if span else None,
                        verified=span is not None,
                        support=support,
                        rationale=why,
                        file_version_id=chunk.file_version_id,
                    )
                )
                checks.append(engine.CitationCheck(verified=span is not None, support=support))
        claim.status = engine.claim_status(kind, checks)
    section.body = " ".join(parts)


class GenerateReport(Command):
    """Draft the report sections of one activity. Locked sections are kept;
    every other section of the activity is replaced."""

    command_name = "rdti.generate_report"
    permission = P_RDTI_WRITE

    activity_id: uuid.UUID


@handles(GenerateReport)
def generate_report(ctx: CommandContext, cmd: GenerateReport) -> dict[str, Any]:
    a = _activity(ctx, cmd.activity_id)
    it = ctx.session.get(Item, a.item_id)
    assert it is not None
    passages = _passages(ctx, a)
    if not passages:
        raise ValidationFailed("upload evidence for this project first", code="no_evidence")
    assessments = {
        x.element: {"coverage": x.coverage, "chunk_ids": x.chunk_ids}
        for x in ctx.session.scalars(select(RdtiAssessment).where(RdtiAssessment.activity_id == a.id))
    }
    client_id, consent = _consent(ctx, it)
    system, user = engine.report_prompt(_activity_dict(a), passages, assessments)
    answer = run_task(
        ctx.session,
        AiTask("rdti.report", system, user, engine.REPORT_SCHEMA, client_id, consent),
        lambda: engine.fake_report(_activity_dict(a), passages, assessments),
        command_id=ctx.command_id,
    )
    existing = list(
        ctx.session.scalars(
            select(RdtiReportSection).where(
                RdtiReportSection.activity_id == a.id, RdtiReportSection.deleted_at.is_(None)
            )
        )
    )
    locked = {s.element for s in existing if s.locked}
    now = utcnow()
    for s in existing:
        if not s.locked:
            s.deleted_at = now
    chunk_rows = ctx.session.scalars(
        select(RdtiChunk).where(RdtiChunk.id.in_([uuid.UUID(p["id"]) for p in passages]))
    )
    chunks = {str(c.id): c for c in chunk_rows}
    order = {e["key"]: i for i, e in enumerate(rules.ELEMENTS)}
    wanted = {e["key"] for e in rules.elements_for(a.kind)}
    made = 0
    for sec in answer.data.get("sections", []):
        key = sec.get("element")
        if key not in wanted or key in locked:
            continue
        wanted.discard(key)
        section = RdtiReportSection(
            item_id=a.item_id,
            activity_id=a.id,
            element=key,
            heading=str(sec.get("heading") or rules.element(key)["label"])[:200],
            body="",
            position=order.get(key, 99),
        )
        ctx.session.add(section)
        ctx.session.flush()
        _store_claims(ctx, section, sec.get("claims", []), chunks)
        made += 1
    return {"sections": made, "kept_locked": len(locked), "provider": answer.provider}


class UpdateSection(Command):
    """Save a person's edit. Claims whose text is unchanged keep their
    sources; edited sentences keep their sources but go back to review; new
    sentences start as unsupported until a source is added or they are marked
    as our own wording."""

    command_name = "rdti.update_section"
    permission = P_RDTI_WRITE

    section_id: uuid.UUID
    body: str
    heading: str | None = Field(default=None, max_length=200)
    expected_version: int | None = None


@handles(UpdateSection)
def update_section(ctx: CommandContext, cmd: UpdateSection) -> dict[str, Any]:
    s = _section(ctx, cmd.section_id)
    if s.locked:
        raise ValidationFailed("this section is locked; unlock it first", code="section_locked")
    if cmd.expected_version is not None and cmd.expected_version != s.version:
        raise ValidationFailed("someone else changed this section; reload it", code="stale_version")
    if cmd.heading:
        s.heading = cmd.heading
    body = cmd.body.strip()
    claims = list(
        ctx.session.scalars(select(RdtiClaim).where(RdtiClaim.section_id == s.id).order_by(RdtiClaim.start))
    )
    covered: list[tuple[int, int]] = []
    unmatched: list[RdtiClaim] = []
    cursor = 0
    for c in claims:
        pos = body.find(c.text, cursor)
        if pos < 0:
            pos = body.find(c.text)
        if pos >= 0 and not _overlaps(covered, pos, pos + len(c.text)):
            c.start, c.end = pos, pos + len(c.text)
            covered.append((c.start, c.end))
            cursor = c.end
        else:
            unmatched.append(c)
    new_spans = [sp for sp in engine.split_sentences(body) if not _overlaps(covered, *sp)]
    edited = changed = 0
    for sp in new_spans:
        text = body[sp[0] : sp[1]]
        best, ratio = None, 0.0
        for c in unmatched:
            r = difflib.SequenceMatcher(None, c.text, text).ratio()
            if r > ratio:
                best, ratio = c, r
        if best is not None and ratio >= 0.6:
            unmatched.remove(best)
            best.start, best.end, best.text = sp[0], sp[1], text
            best.source = "human"
            best.confirmed_by = None
            best.confirmed_at = None
            if best.status != "polish":
                best.status = "needs_review"
                best.note = "Edited by hand; check the source still says this."
            else:
                best.fact_warning = engine.has_facts(text)
            edited += 1
        else:
            ctx.session.add(
                RdtiClaim(
                    section_id=s.id,
                    start=sp[0],
                    end=sp[1],
                    text=text,
                    status="unsupported",
                    source="human",
                    note="Added by hand; add a source or mark as our wording.",
                    fact_warning=False,
                )
            )
            changed += 1
        covered.append(sp)
    for c in unmatched:
        ctx.session.delete(c)
    s.body = body
    s.version += 1
    return {
        "version": s.version,
        "edited_claims": edited,
        "new_claims": changed,
        "removed_claims": len(unmatched),
    }


def _overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < e and s < end for s, e in spans)


class LockSection(Command):
    command_name = "rdti.lock_section"
    permission = P_RDTI_APPROVE

    section_id: uuid.UUID
    locked: bool


@handles(LockSection)
def lock_section(ctx: CommandContext, cmd: LockSection) -> None:
    s = _section(ctx, cmd.section_id, P_RDTI_APPROVE)
    s.locked = cmd.locked


class ReviewClaim(Command):
    """A reviewer's decision on one claim.

    * confirm: the sources say this (needs at least one verified source)
    * polish: this is our own connecting wording, no source needed; refused
      when the sentence contains numbers or dates unless acknowledged
    * recompute: drop the manual decision and derive status from sources
    """

    command_name = "rdti.review_claim"
    permission = P_RDTI_WRITE

    claim_id: uuid.UUID
    action: Literal["confirm", "polish", "recompute"]
    acknowledge_facts: bool = False


@handles(ReviewClaim)
def review_claim(ctx: CommandContext, cmd: ReviewClaim) -> dict[str, str]:
    c, _s = _claim(ctx, cmd.claim_id)
    cites = list(ctx.session.scalars(select(RdtiCitation).where(RdtiCitation.claim_id == c.id)))
    if cmd.action == "confirm":
        if not any(x.verified for x in cites):
            raise ValidationFailed(
                "add a source whose quote is found in the material first", code="no_verified_source"
            )
        c.status = "supported"
        c.confirmed_by = ctx.actor.user_id
        c.confirmed_at = utcnow()
        c.note = None
    elif cmd.action == "polish":
        facts = engine.has_facts(c.text)
        if facts and not cmd.acknowledge_facts:
            raise ValidationFailed(
                "this sentence contains numbers or dates; facts need a source", code="polish_has_facts"
            )
        c.status = "polish"
        c.fact_warning = facts
        c.confirmed_by = ctx.actor.user_id
        c.confirmed_at = utcnow()
    else:
        c.status = engine.claim_status("fact", [engine.CitationCheck(x.verified, x.support) for x in cites])
        c.confirmed_by = None
        c.confirmed_at = None
    return {"status": c.status}


class AddCitation(Command):
    command_name = "rdti.add_citation"
    permission = P_RDTI_WRITE

    claim_id: uuid.UUID
    chunk_id: uuid.UUID
    quote: str = Field(min_length=8)


@handles(AddCitation)
def add_citation(ctx: CommandContext, cmd: AddCitation) -> dict[str, Any]:
    c, s = _claim(ctx, cmd.claim_id)
    chunk = ctx.session.get(RdtiChunk, cmd.chunk_id)
    if chunk is None or chunk.item_id != s.item_id:
        raise NotFound("passage not found")
    span = engine.locate_quote(chunk.text, cmd.quote)
    if span is None:
        raise ValidationFailed("the quote was not found in that passage", code="quote_not_found")
    support, why = engine.support_heuristic(c.text, cmd.quote)
    cit = RdtiCitation(
        claim_id=c.id,
        chunk_id=chunk.id,
        quote=chunk.text[span[0] : span[1]],
        quote_start=span[0],
        quote_end=span[1],
        verified=True,
        support=support,
        rationale=why,
        file_version_id=chunk.file_version_id,
    )
    ctx.session.add(cit)
    ctx.session.flush()
    if c.status in ("unsupported", "needs_review"):
        cites = list(ctx.session.scalars(select(RdtiCitation).where(RdtiCitation.claim_id == c.id)))
        c.status = engine.claim_status("fact", [engine.CitationCheck(x.verified, x.support) for x in cites])
        if c.status == "supported":
            c.note = None  # the "add a source" hint is answered now
    return {"id": cit.id, "support": support, "status": c.status}


class RemoveCitation(Command):
    command_name = "rdti.remove_citation"
    permission = P_RDTI_WRITE

    citation_id: uuid.UUID


@handles(RemoveCitation)
def remove_citation(ctx: CommandContext, cmd: RemoveCitation) -> dict[str, str]:
    cit = ctx.session.get(RdtiCitation, cmd.citation_id)
    if cit is None:
        raise NotFound("citation not found")
    c, _s = _claim(ctx, cit.claim_id)
    ctx.session.delete(cit)
    ctx.session.flush()
    if c.status != "polish":
        cites = list(ctx.session.scalars(select(RdtiCitation).where(RdtiCitation.claim_id == c.id)))
        c.status = engine.claim_status("fact", [engine.CitationCheck(x.verified, x.support) for x in cites])
        if c.status != "supported":
            c.confirmed_by = None
    return {"status": c.status}


class RecheckSection(Command):
    """Re-verify every quote against the current passage text and re-run the
    support check for claims that are not confirmed by a person."""

    command_name = "rdti.recheck_section"
    permission = P_RDTI_WRITE

    section_id: uuid.UUID


@handles(RecheckSection)
def recheck_section(ctx: CommandContext, cmd: RecheckSection) -> dict[str, Any]:
    s = _section(ctx, cmd.section_id)
    it = ctx.session.get(Item, s.item_id)
    assert it is not None
    claims = list(ctx.session.scalars(select(RdtiClaim).where(RdtiClaim.section_id == s.id)))
    items: list[dict[str, Any]] = []
    cites_by_claim: dict[uuid.UUID, list[RdtiCitation]] = {}
    for c in claims:
        for cit in ctx.session.scalars(select(RdtiCitation).where(RdtiCitation.claim_id == c.id)):
            chunk = ctx.session.get(RdtiChunk, cit.chunk_id)
            span = engine.locate_quote(chunk.text, cit.quote) if chunk else None
            cit.verified = span is not None and bool(chunk and chunk.is_current)
            if span:
                cit.quote_start, cit.quote_end = span
            cites_by_claim.setdefault(c.id, []).append(cit)
            if cit.verified and c.status != "polish":
                items.append({"citation_id": str(cit.id), "claim": c.text, "quote": cit.quote})
    if items:
        client_id, consent = _consent(ctx, it)
        system, user = engine.support_prompt(items)

        def fallback() -> dict[str, Any]:
            return {
                "checks": [
                    dict(
                        zip(
                            ("support", "rationale"),
                            engine.support_heuristic(i["claim"], i["quote"]),
                            strict=True,
                        )
                    )
                    | {"citation_id": i["citation_id"]}
                    for i in items
                ]
            }

        answer = run_task(
            ctx.session,
            AiTask("rdti.support_check", system, user, engine.SUPPORT_SCHEMA, client_id, consent),
            fallback,
            command_id=ctx.command_id,
        )
        by_id = {str(x.id): x for xs in cites_by_claim.values() for x in xs}
        for chk in answer.data.get("checks", []):
            target = by_id.get(str(chk.get("citation_id")))
            if target is not None and chk.get("support") in ("supports", "partial", "contradicts"):
                target.support = chk["support"]
                target.rationale = str(chk.get("rationale", ""))[:1000]
    counts: dict[str, int] = {}
    for c in claims:
        if c.status != "polish":
            new = engine.claim_status(
                "fact", [engine.CitationCheck(x.verified, x.support) for x in cites_by_claim.get(c.id, [])]
            )
            if new != "supported" or c.confirmed_by is None:
                if new != c.status:
                    c.confirmed_by = None
                c.status = new
                if new == "supported":
                    c.note = None
        counts[c.status] = counts.get(c.status, 0) + 1
    return {"counts": counts}


class DeleteReport(Command):
    command_name = "rdti.delete_report"
    permission = P_RDTI_WRITE

    activity_id: uuid.UUID


@handles(DeleteReport)
def delete_report(ctx: CommandContext, cmd: DeleteReport) -> dict[str, int]:
    a = _activity(ctx, cmd.activity_id)
    n = 0
    now = utcnow()
    for s in ctx.session.scalars(
        select(RdtiReportSection).where(
            RdtiReportSection.activity_id == a.id, RdtiReportSection.deleted_at.is_(None)
        )
    ):
        if not s.locked:
            s.deleted_at = now
            n += 1
    return {"deleted": n}


def passages_from_extract(passages: list[Passage]) -> list[PassageIn]:
    return [PassageIn(text=p.text, page=p.page, location=p.location, bbox=p.bbox) for p in passages]
