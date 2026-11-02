"""Turn an uploaded document into citable passages.

Each passage keeps where it came from (PDF page and block rectangle, or Word
paragraph number) so a report sentence can point back to the exact place in
the original file. Passages are paragraph-sized: small enough to quote, large
enough to carry a full statement.
"""

import io
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import ValidationFailed

MAX_CHARS = 1200
MIN_CHARS = 40

SUPPORTED = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
}


@dataclass
class Passage:
    text: str
    page: int | None = None
    location: str = ""
    bbox: list[float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def file_kind(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED:
        raise ValidationFailed(
            f"unsupported file type .{ext}; supported: {', '.join(sorted(SUPPORTED))}",
            code="unsupported_file",
        )
    return ext


def extract(data: bytes, filename: str) -> list[Passage]:
    kind = file_kind(filename)
    if kind == "pdf":
        raw = _pdf(data)
    elif kind == "docx":
        raw = _docx(data)
    else:
        raw = _text(data)
    return _merge_small([p for p in raw if p.text.strip()])


def _clean(text: str) -> str:
    text = text.replace("­", "")
    # PDF lines are hard-wrapped; join them, keep paragraph breaks.
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _pdf(data: bytes) -> list[Passage]:
    import pymupdf

    try:
        doc: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as e:
        raise ValidationFailed("could not read this PDF", code="unreadable_file") from e
    out: list[Passage] = []
    with doc:
        for page in doc:
            for i, block in enumerate(page.get_text("blocks", sort=True)):
                x0, y0, x1, y1, text, _no, kind = block[:7]
                if kind != 0:  # 1 = image block
                    continue
                for piece in _split_long(_clean(text)):
                    out.append(
                        Passage(
                            text=piece,
                            page=page.number + 1,
                            location=f"p.{page.number + 1} ¶{i + 1}",
                            bbox=[round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                        )
                    )
    if not out:
        raise ValidationFailed(
            "no text found in this PDF (scanned images need OCR, which is not supported yet)",
            code="no_text",
        )
    return out


def _docx(data: bytes) -> list[Passage]:
    import docx

    try:
        d: Any = docx.Document(io.BytesIO(data))  # type: ignore[no-untyped-call]
    except Exception as e:
        raise ValidationFailed("could not read this Word file", code="unreadable_file") from e
    out: list[Passage] = []
    n = 0
    for para in d.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        n += 1
        style = (para.style.name if para.style is not None else "") or ""
        for piece in _split_long(_clean(text)):
            out.append(Passage(text=piece, location=f"¶{n}", meta={"heading": style.startswith("Heading")}))
    for t_index, table in enumerate(d.tables):
        for r_index, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                out.append(
                    Passage(
                        text=" | ".join(dict.fromkeys(cells)),
                        location=f"table {t_index + 1} row {r_index + 1}",
                    )
                )
    return out


def _text(data: bytes) -> list[Passage]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("gb18030", errors="replace")
    out: list[Passage] = []
    for n, block in enumerate(re.split(r"\n\s*\n", text), start=1):
        for piece in _split_long(_clean(block)):
            out.append(Passage(text=piece, location=f"¶{n}"))
    return out


_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")  # noqa: RUF001


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts: list[str] = []
    cur = ""
    for sentence in _SENTENCE_END.split(text):
        if cur and len(cur) + len(sentence) + 1 > MAX_CHARS:
            parts.append(cur)
            cur = sentence
        else:
            cur = f"{cur} {sentence}".strip()
    if cur:
        parts.append(cur)
    return parts


def _merge_small(passages: list[Passage]) -> list[Passage]:
    """Headings and one-line fragments are folded into the next passage on the
    same page, so every passage can stand alone as evidence."""
    out: list[Passage] = []
    carry: Passage | None = None
    for p in passages:
        if carry is not None and carry.page == p.page and len(carry.text) + len(p.text) < MAX_CHARS:
            p = Passage(
                text=f"{carry.text} {p.text}",
                page=p.page,
                location=carry.location,
                bbox=_union(carry.bbox, p.bbox),
                meta=p.meta,
            )
            carry = None
        elif carry is not None:
            out.append(carry)
            carry = None
        if len(p.text) < MIN_CHARS:
            carry = p
        else:
            out.append(p)
    if carry is not None:
        out.append(carry)
    return out


def _union(a: list[float] | None, b: list[float] | None) -> list[float] | None:
    if a is None or b is None:
        return a or b
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
