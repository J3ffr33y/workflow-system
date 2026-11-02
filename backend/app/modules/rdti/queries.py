"""Reads for the R&D report workbench."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, PermissionDenied
from app.modules.clients.models import Client, Contact
from app.modules.files.models import FileVersion, StoredFile
from app.modules.identity.models import User
from app.modules.items.models import Item
from app.modules.rdti import rules
from app.modules.rdti.models import (
    RdtiActivity,
    RdtiAssessment,
    RdtiChecklistItem,
    RdtiChunk,
    RdtiCitation,
    RdtiClaim,
    RdtiReportSection,
)
from app.modules.workspaces.models import Workspace
from app.platform.ai_gateway import provider_info
from app.platform.permissions import P_ITEMS_READ, P_RDTI_APPROVE, P_RDTI_WRITE, Actor

CLAIM_STATUSES = ("supported", "needs_review", "polish", "unsupported")


def enabled_for(ws: Workspace) -> bool:
    return ws.key == "grants" or bool((ws.settings or {}).get("rdti_enabled"))


def require_item(s: Session, actor: Actor, item_id: uuid.UUID) -> Item:
    it = s.get(Item, item_id)
    if it is None or it.deleted_at is not None:
        raise NotFound("item not found")
    if not actor.can(P_ITEMS_READ, it.workspace_id):
        raise PermissionDenied("no access")
    return it


def _id(v: Any) -> str | None:
    return str(v) if v is not None else None


def activity_dict(a: RdtiActivity) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "code": a.code,
        "title": a.title,
        "kind": a.kind,
        "supports_activity_id": _id(a.supports_activity_id),
        "description": a.description,
    }


def workbench(s: Session, actor: Actor, item_id: uuid.UUID) -> dict[str, Any]:
    it = require_item(s, actor, item_id)
    ws = s.get(Workspace, it.workspace_id)
    assert ws is not None
    client = s.get(Client, it.client_id) if it.client_id else None
    acts = list(
        s.scalars(
            select(RdtiActivity)
            .where(RdtiActivity.item_id == it.id, RdtiActivity.deleted_at.is_(None))
            .order_by(RdtiActivity.kind, RdtiActivity.position, RdtiActivity.created_at)
        )
    )
    act_ids = [a.id for a in acts]

    files = list(
        s.scalars(
            select(StoredFile)
            .where(
                StoredFile.owner_type == "item",
                StoredFile.owner_id == it.id,
                StoredFile.purpose == "rdti_evidence",
                StoredFile.deleted_at.is_(None),
            )
            .order_by(StoredFile.created_at)
        )
    )
    counts = {
        fid: (total, assigned)
        for fid, total, assigned in s.execute(
            select(RdtiChunk.file_id, func.count(), func.count(RdtiChunk.activity_id))
            .where(RdtiChunk.item_id == it.id, RdtiChunk.is_current.is_(True))
            .group_by(RdtiChunk.file_id)
        )
    }
    versions = {
        (v.file_id, v.version): v
        for v in s.scalars(select(FileVersion).where(FileVersion.file_id.in_([f.id for f in files])))
    }
    documents = []
    for f in files:
        v = versions.get((f.id, f.current_version))
        total, assigned = counts.get(f.id, (0, 0))
        documents.append(
            {
                "file_id": str(f.id),
                "name": f.name,
                "version": f.current_version,
                "version_id": _id(v.id if v else None),
                "mime_type": v.mime_type if v else None,
                "size_bytes": v.size_bytes if v else None,
                "uploaded_at": f.updated_at.isoformat(),
                "passages": total,
                "assigned": assigned,
            }
        )

    assessments: dict[str, list[dict[str, Any]]] = {str(a): [] for a in act_ids}
    for x in s.scalars(select(RdtiAssessment).where(RdtiAssessment.activity_id.in_(act_ids))):
        assessments[str(x.activity_id)].append(
            {
                "element": x.element,
                "coverage": x.coverage,
                "rationale": x.rationale,
                "summary_only": x.summary_only,
                "chunk_ids": x.chunk_ids,
                "source": x.source,
                "rule_version": x.rule_version,
                "updated_at": x.updated_at.isoformat(),
            }
        )

    checklist = [
        {
            "id": str(c.id),
            "activity_id": _id(c.activity_id),
            "element": c.element,
            "question": c.question,
            "preferred": c.preferred,
            "alternatives": c.alternatives,
            "example": c.example,
            "status": c.status,
        }
        for c in s.scalars(
            select(RdtiChecklistItem)
            .where(RdtiChecklistItem.item_id == it.id, RdtiChecklistItem.deleted_at.is_(None))
            .order_by(RdtiChecklistItem.position)
        )
    ]

    report: dict[str, dict[str, Any]] = {
        str(a): {"sections": 0, "counts": dict.fromkeys(CLAIM_STATUSES, 0)} for a in act_ids
    }
    for sec_act, status, n in s.execute(
        select(RdtiReportSection.activity_id, RdtiClaim.status, func.count())
        .join(RdtiClaim, RdtiClaim.section_id == RdtiReportSection.id)
        .where(RdtiReportSection.item_id == it.id, RdtiReportSection.deleted_at.is_(None))
        .group_by(RdtiReportSection.activity_id, RdtiClaim.status)
    ):
        report[str(sec_act)]["counts"][status] = n
    for sec_act, n in s.execute(
        select(RdtiReportSection.activity_id, func.count())
        .where(RdtiReportSection.item_id == it.id, RdtiReportSection.deleted_at.is_(None))
        .group_by(RdtiReportSection.activity_id)
    ):
        report[str(sec_act)]["sections"] = n

    return {
        "item": {
            "id": str(it.id),
            "name": it.name,
            "workspace_id": str(it.workspace_id),
            "workspace_key": ws.key,
            "client_id": _id(it.client_id),
            "client_name": client.name if client else None,
            "ai_consent": bool(client and (client.data or {}).get("ai_consent") is True),
        },
        "enabled": enabled_for(ws),
        "can_write": actor.can(P_RDTI_WRITE, it.workspace_id),
        "can_approve": actor.can(P_RDTI_APPROVE, it.workspace_id),
        "ai": provider_info(),
        "rules": rules.public(),
        "activities": [activity_dict(a) for a in acts],
        "documents": documents,
        "assessments": assessments,
        "checklist": checklist,
        "report": report,
    }


def passages(
    s: Session,
    actor: Actor,
    item_id: uuid.UUID,
    *,
    file_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    unassigned: bool = False,
    search: str | None = None,
    ids: list[uuid.UUID] | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    it = require_item(s, actor, item_id)
    q = (
        select(RdtiChunk, StoredFile.name)
        .join(StoredFile, StoredFile.id == RdtiChunk.file_id)
        .where(RdtiChunk.item_id == it.id, StoredFile.deleted_at.is_(None))
    )
    q = q.where(RdtiChunk.id.in_(ids)) if ids else q.where(RdtiChunk.is_current.is_(True))
    if file_id:
        q = q.where(RdtiChunk.file_id == file_id)
    if activity_id:
        q = q.where(RdtiChunk.activity_id == activity_id)
    if unassigned:
        q = q.where(RdtiChunk.activity_id.is_(None))
    if search:
        q = q.where(RdtiChunk.text.ilike(f"%{search}%"))
    rows = s.execute(q.order_by(StoredFile.name, RdtiChunk.seq).limit(min(limit, 1000))).all()
    return [chunk_dict(c, name) for c, name in rows]


def chunk_dict(c: RdtiChunk, file_name: str) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "file_id": str(c.file_id),
        "file_version_id": str(c.file_version_id),
        "file_name": file_name,
        "seq": c.seq,
        "page": c.page,
        "location": c.location,
        "bbox": c.bbox,
        "text": c.text,
        "activity_id": _id(c.activity_id),
        "is_current": c.is_current,
    }


def passage_context(s: Session, actor: Actor, chunk_id: uuid.UUID) -> dict[str, Any]:
    c = s.get(RdtiChunk, chunk_id)
    if c is None:
        raise NotFound("passage not found")
    require_item(s, actor, c.item_id)
    f = s.get(StoredFile, c.file_id)
    assert f is not None
    near = (
        s.execute(
            select(RdtiChunk)
            .where(
                RdtiChunk.file_version_id == c.file_version_id, RdtiChunk.seq.between(c.seq - 1, c.seq + 1)
            )
            .order_by(RdtiChunk.seq)
        )
        .scalars()
        .all()
    )
    return {
        "passage": chunk_dict(c, f.name),
        "before": next((chunk_dict(x, f.name) for x in near if x.seq == c.seq - 1), None),
        "after": next((chunk_dict(x, f.name) for x in near if x.seq == c.seq + 1), None),
        "file": {
            "id": str(f.id),
            "name": f.name,
            "current_version": f.current_version,
            "deleted": f.deleted_at is not None,
        },
        "cited_by": cited_by(s, c.id),
    }


def cited_by(s: Session, chunk_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = s.execute(
        select(RdtiClaim, RdtiReportSection)
        .join(RdtiCitation, RdtiCitation.claim_id == RdtiClaim.id)
        .join(RdtiReportSection, RdtiReportSection.id == RdtiClaim.section_id)
        .where(RdtiCitation.chunk_id == chunk_id, RdtiReportSection.deleted_at.is_(None))
    ).all()
    return [
        {
            "claim_id": str(c.id),
            "section_id": str(sec.id),
            "heading": sec.heading,
            "text": c.text,
            "status": c.status,
        }
        for c, sec in rows
    ]


def report(
    s: Session, actor: Actor, item_id: uuid.UUID, activity_id: uuid.UUID | None = None
) -> dict[str, Any]:
    it = require_item(s, actor, item_id)
    q = select(RdtiReportSection).where(
        RdtiReportSection.item_id == it.id, RdtiReportSection.deleted_at.is_(None)
    )
    if activity_id:
        q = q.where(RdtiReportSection.activity_id == activity_id)
    sections = list(s.scalars(q))
    acts = {a.id: a for a in s.scalars(select(RdtiActivity).where(RdtiActivity.item_id == it.id))}
    sections.sort(key=lambda x: (acts[x.activity_id].kind, acts[x.activity_id].position, x.position))
    sec_ids = [x.id for x in sections]
    claims = list(
        s.scalars(select(RdtiClaim).where(RdtiClaim.section_id.in_(sec_ids)).order_by(RdtiClaim.start))
    )
    cites = s.execute(
        select(RdtiCitation, RdtiChunk, StoredFile)
        .join(RdtiChunk, RdtiChunk.id == RdtiCitation.chunk_id)
        .join(StoredFile, StoredFile.id == RdtiChunk.file_id)
        .where(RdtiCitation.claim_id.in_([c.id for c in claims]))
        .order_by(RdtiCitation.created_at)
    ).all()
    by_claim: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for cit, chunk, f in cites:
        by_claim.setdefault(cit.claim_id, []).append(
            {
                "id": str(cit.id),
                "quote": cit.quote,
                "quote_start": cit.quote_start,
                "quote_end": cit.quote_end,
                "verified": cit.verified,
                "support": cit.support,
                "rationale": cit.rationale,
                "passage": chunk_dict(chunk, f.name) | {"file_deleted": f.deleted_at is not None},
            }
        )
    names = {
        u.id: u.full_name
        for u in s.scalars(
            select(User).where(User.id.in_({c.confirmed_by for c in claims if c.confirmed_by}))
        )
    }
    by_section: dict[uuid.UUID, list[dict[str, Any]]] = {}
    totals = dict.fromkeys(CLAIM_STATUSES, 0)
    for c in claims:
        totals[c.status] = totals.get(c.status, 0) + 1
        by_section.setdefault(c.section_id, []).append(
            {
                "id": str(c.id),
                "start": c.start,
                "end": c.end,
                "text": c.text,
                "status": c.status,
                "source": c.source,
                "note": c.note,
                "fact_warning": c.fact_warning,
                "confirmed_by": names.get(c.confirmed_by) if c.confirmed_by else None,
                "confirmed_at": c.confirmed_at.isoformat() if c.confirmed_at else None,
                "citations": by_claim.get(c.id, []),
            }
        )
    return {
        "sections": [
            {
                "id": str(x.id),
                "activity_id": str(x.activity_id),
                "activity_code": acts[x.activity_id].code,
                "activity_title": acts[x.activity_id].title,
                "element": x.element,
                "heading": x.heading,
                "body": x.body,
                "locked": x.locked,
                "version": x.version,
                "claims": by_section.get(x.id, []),
            }
            for x in sections
        ],
        "totals": totals,
    }


def email_draft(s: Session, actor: Actor, item_id: uuid.UUID) -> dict[str, Any]:
    it = require_item(s, actor, item_id)
    items = list(
        s.scalars(
            select(RdtiChecklistItem)
            .where(
                RdtiChecklistItem.item_id == it.id,
                RdtiChecklistItem.deleted_at.is_(None),
                RdtiChecklistItem.status.in_(["draft", "sent"]),
            )
            .order_by(RdtiChecklistItem.position)
        )
    )
    contact = None
    if it.client_id:
        contact = s.scalar(
            select(Contact)
            .where(Contact.client_id == it.client_id, Contact.deleted_at.is_(None))
            .order_by(Contact.is_primary.desc(), Contact.created_at)
        )
    lines = []
    for n, c in enumerate(items, start=1):
        alt = "; ".join(c.alternatives) if c.alternatives else ""
        lines.append(
            f"{n}. {c.question}\n   Preferred: {c.preferred}"
            + (f"\n   Alternatives: {alt}" if alt else "")
            + (f"\n   Example: {c.example}" if c.example else "")
        )
    user = s.get(User, actor.user_id) if actor.user_id else None
    text = rules.EMAIL_TEMPLATE.format(
        contact=(contact.name if contact else "client"),
        project=it.name,
        items="\n\n".join(lines) if lines else "(no open checklist items)",
        sender=user.full_name if user else "",
    )
    return {
        "subject": f"R&D Tax Incentive: information needed for {it.name}",
        "body": text,
        "to": contact.email if contact else None,
        "items": len(items),
    }


def file_version_for_download(
    s: Session, actor: Actor, file_id: uuid.UUID, version: int | None
) -> FileVersion:
    f = s.get(StoredFile, file_id)
    if f is None or f.owner_type != "item":
        raise NotFound("file not found")
    require_item(s, actor, f.owner_id)
    v = s.scalar(
        select(FileVersion).where(
            FileVersion.file_id == f.id, FileVersion.version == (version or f.current_version)
        )
    )
    if v is None:
        raise NotFound("file version not found")
    return v
