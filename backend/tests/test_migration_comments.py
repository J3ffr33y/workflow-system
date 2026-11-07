import uuid

from sqlalchemy import select

from app.core.db import read_session
from app.modules.collaboration.models import Comment
from app.modules.migration.commands import (
    PrepareRun,
    RollbackRun,
    SplitImportedComments,
    StartCommit,
    UpdateMapping,
    ValidateRun,
)
from app.modules.migration.comments import chronological, split_merged_comments
from app.modules.migration.queries import comment_split_preview
from app.platform.events.dispatcher import drain
from app.platform.permissions import SYSTEM_ACTOR
from tests.conftest import run
from tests.test_items import boards
from tests.test_migration import _create_run


def test_split_on_comma_space_only() -> None:
    assert split_merged_comments("followed up, @Win Yang Follow up") == ["followed up", "@Win Yang Follow up"]
    # Chinese comma and comma without space are not separators.
    cn = "客户已付款\uff0c 等报表"  # full-width comma, even followed by a space
    assert split_merged_comments(cn) == [cn]
    assert split_merged_comments("Rebate 1,000 approved") == ["Rebate 1,000 approved"]
    assert split_merged_comments("  ") == [] and split_merged_comments(None) == []


def test_split_keeps_one_sentence_together() -> None:
    assert split_merged_comments("Sent checklist (R&D, EMDG) to client") == [
        "Sent checklist (R&D, EMDG) to client"
    ]
    assert split_merged_comments("Need payslips, invoices and, bank statements") == [
        "Need payslips",
        "invoices and, bank statements",
    ]
    assert split_merged_comments("Lodged on Aug 5, 2026") == ["Lodged on Aug 5, 2026"]
    assert split_merged_comments("Waiting, ok") == ["Waiting, ok"]
    # Two Chinese characters can be a whole update.
    assert split_merged_comments("等待客户, 已付") == ["等待客户", "已付"]
    assert split_merged_comments("R&amp;D evidence, kickoff booked") == ["R&D evidence", "kickoff booked"]


def test_chronological_order() -> None:
    assert chronological(["a", "b"], newest_first=True) == ["b", "a"]
    assert chronological(["a", "b"], newest_first=False) == ["a", "b"]


def _bodies(item_comments: list[Comment]) -> list[str]:
    return [c.body for c in sorted(item_comments, key=lambda c: c.created_at)]


def _live_comments() -> list[Comment]:
    with read_session() as s:
        return list(s.scalars(select(Comment).where(Comment.deleted_at.is_(None))))


def _import(seeded: dict[str, str], **options: object) -> uuid.UUID:
    ws = seeded["grants"]
    rid = _create_run(ws, boards(ws)["FY 2026"], "grants_export_gbk.csv")
    if options:
        run(UpdateMapping(run_id=rid, options=options))
    run(ValidateRun(run_id=rid))
    run(PrepareRun(run_id=rid))
    run(ValidateRun(run_id=rid))
    run(StartCommit(run_id=rid))
    drain()
    return rid


def test_new_imports_split_merged_updates(seeded: dict[str, str]) -> None:
    _import(seeded)
    bodies = sorted(c.body for c in _live_comments())
    assert "followed up" in bodies and "@Win Yang Follow up" in bodies
    assert "followed up, @Win Yang Follow up" not in bodies


def test_split_an_earlier_import_preview_apply_and_rollback(seeded: dict[str, str]) -> None:
    rid = _import(seeded, split_comments=False)
    before = sorted(c.body for c in _live_comments())
    assert "followed up, @Win Yang Follow up" in before

    with read_session() as s:
        preview = comment_split_preview(s, SYSTEM_ACTOR, rid, newest_first=True)
    assert preview["to_split"] == 2 and preview["checked"] == 3
    ex = next(e for e in preview["examples"] if e["before"].startswith("followed up"))
    assert ex["after"] == ["@Win Yang Follow up", "followed up"]  # oldest first
    assert _live_comments() and sorted(c.body for c in _live_comments()) == before  # preview writes nothing

    assert run(SplitImportedComments(run_id=rid, newest_first=True)) == {"split": 2, "created": 4}
    live = _live_comments()
    assert len(live) == 5
    same_item = [c for c in live if c.body in ("followed up", "@Win Yang Follow up")]
    assert _bodies(same_item) == ["@Win Yang Follow up", "followed up"]
    # Running it again finds nothing more to split.
    assert run(SplitImportedComments(run_id=rid))["split"] == 0

    run(RollbackRun(run_id=rid))
    assert _live_comments() == []
