"""Word export of the report. The clean version is for the client; the review
version adds a numbered source note after every sourced statement and an
evidence index at the end, for the reviewer or Head of R&D."""

import io
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.rdti import queries
from app.platform.permissions import Actor

STATUS_LABEL = {
    "supported": "sourced",
    "needs_review": "needs review",
    "unsupported": "NO SOURCE",
    "polish": "our wording",
}


def build_docx(s: Session, actor: Actor, item_id: uuid.UUID, mode: str) -> tuple[bytes, dict[str, int]]:
    import docx
    from docx.shared import Pt, RGBColor

    data = queries.workbench(s, actor, item_id)
    rep = queries.report(s, actor, item_id)
    d: Any = docx.Document()  # type: ignore[no-untyped-call]
    d.add_heading(f"R&D technical report: {data['item']['name']}", level=0)
    if data["item"]["client_name"]:
        d.add_paragraph(data["item"]["client_name"])
    if mode == "review":
        t = rep["totals"]
        d.add_paragraph(
            f"Review copy. Sourced {t['supported']}, needs review {t['needs_review']}, "
            f"no source {t['unsupported']}, our wording {t['polish']}."
        )
    index: list[dict[str, Any]] = []
    current_activity = None
    for sec in rep["sections"]:
        if sec["activity_id"] != current_activity:
            current_activity = sec["activity_id"]
            d.add_heading(f"{sec['activity_code']} {sec['activity_title']}", level=1)
        d.add_heading(sec["heading"], level=2)
        p = d.add_paragraph()
        body = sec["body"]
        cursor = 0
        for c in sec["claims"]:
            if c["start"] > cursor:
                p.add_run(body[cursor : c["start"]])
            run = p.add_run(body[c["start"] : c["end"]])
            cursor = c["end"]
            if mode != "review":
                continue
            if c["status"] == "unsupported":
                run.font.color.rgb = RGBColor(0xC0, 0x1F, 0x1F)
            elif c["status"] == "needs_review":
                run.font.color.rgb = RGBColor(0xA6, 0x6A, 0x00)
            refs = []
            for cit in c["citations"]:
                index.append(cit)
                refs.append(str(len(index)))
            if refs:
                note = p.add_run(f" [{', '.join(refs)}]")
                note.font.size = Pt(8)
            elif c["status"] == "unsupported":
                note = p.add_run(" [no source]")
                note.font.size = Pt(8)
        if cursor < len(body):
            p.add_run(body[cursor:])
    if mode == "review" and index:
        d.add_page_break()  # type: ignore[no-untyped-call]
        d.add_heading("Evidence index", level=1)
        for n, cit in enumerate(index, start=1):
            ps = cit["passage"]
            where = f"{ps['file_name']}, {ps['location']}"
            flag = "" if cit["verified"] else " (quote not found in source)"
            d.add_paragraph(f"[{n}] {where}{flag}: “{cit['quote']}”")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue(), rep["totals"]
