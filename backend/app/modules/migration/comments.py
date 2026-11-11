"""Splitting updates that the old system merged into one cell.

ERPNext's report export joins the several updates of a row into one cell
with ", " (comma + space). A comma + space can also sit inside one update
("followed up, waiting for docs"), so a split is a best guess: we split on
", " and glue a piece back onto the previous one when it clearly continues
the same sentence. Chinese commas and commas without a space (1,000) are
never split points.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.collaboration.models import Comment
from app.modules.migration.models import MigrationRun
from app.platform.audit.models import AuditEntry
from app.platform.fields.types import clean_text

_SPLIT = re.compile(r",[ \t]+")
# The previous piece ends with a word that needs a continuation.
_CONTINUES = re.compile(r"(?:&|\band|\bor|\be\.g\.|\bi\.e\.|\bincl\.|\bincluding|\bsuch as)\s*$", re.I)
_YEAR = re.compile(r"^\d{4}\b")
_ENDS_WITH_DIGIT = re.compile(r"\d$")
# Includes full-width brackets used in Chinese text.
_PAIRS = (("(", ")"), ("[", "]"), ("{", "}"), ("\uff08", "\uff09"), ("【", "】"))


def _unbalanced(text: str) -> bool:
    if any(text.count(o) > text.count(c) for o, c in _PAIRS):
        return True
    return text.count('"') % 2 == 1 or (text.count("“") > text.count("”"))


def _glue(previous: str, piece: str) -> bool:
    """True when ``piece`` most likely continues ``previous`` (same update)."""
    # A lone "ok" or "2" is a fragment; two Chinese characters can be a whole update.
    if len(piece) <= 2 and piece.isascii():
        return True
    if _unbalanced(previous):
        return True
    if _CONTINUES.search(previous):
        return True
    # "Aug 5, 2026": a date, not two updates.
    return bool(_ENDS_WITH_DIGIT.search(previous) and _YEAR.match(piece))


def split_merged_comments(raw: str | None) -> list[str]:
    """The separate updates in one exported cell, in the cell's order."""
    text = clean_text(raw)
    if not text:
        return []
    out: list[str] = []
    for piece in (p.strip() for p in _SPLIT.split(text)):
        if not piece:
            continue
        if out and _glue(out[-1], piece):
            out[-1] = f"{out[-1]}, {piece}"
        else:
            out.append(piece)
    return out


def chronological(pieces: list[str], newest_first: bool) -> list[str]:
    """Oldest first, whatever order the export used."""
    return list(reversed(pieces)) if newest_first else list(pieces)


def imported_comments(s: Session, run: MigrationRun) -> list[Comment]:
    """Live, unedited updates this run created."""
    ids = select(AuditEntry.entity_id).where(
        AuditEntry.batch_id == run.batch_id,
        AuditEntry.entity_type == "comment",
        AuditEntry.op == "create",
    )
    return list(
        s.scalars(
            select(Comment)
            .where(Comment.id.in_(ids), Comment.deleted_at.is_(None), Comment.edited_at.is_(None))
            .order_by(Comment.created_at)
        )
    )
