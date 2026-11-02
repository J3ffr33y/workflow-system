"""R&D report module: upload -> assess -> checklist -> report -> review -> export,
over HTTP with the offline AI provider. Material is fictional."""

import io
import tempfile
from typing import Any

import docx
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.modules.rdti import engine
from app.platform.docs.extract import extract
from tests.conftest import make_user

PARAGRAPHS = [
    "Project Thermo: technical notes for the 2025 income year.",
    "It was unknown whether a low-cost sensor could hold 0.1 degree accuracy above 80 degrees; no supplier "
    "datasheet or published literature covered that range, so the outcome could not be determined in advance.",
    "We hypothesised that model-predictive control with a thermal lag model would cut overshoot below 2%.",
    "We ran 40 experiment runs on a test rig at 60, 70 and 80 degrees with two sensor batches, sampling at 10 Hz.",
    "Measured results: overshoot fell from 6.4% to 1.7% across the 40 runs, while batch B failed above 78 degrees.",
    "We concluded the hypothesis was confirmed, and as a result we decided to drop batch B sensors.",
    "Overall the team successfully delivered an innovative and significantly improved product.",
]


def make_docx(paragraphs: list[str]) -> bytes:
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_pdf(paragraphs: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for p in paragraphs:
        page.insert_textbox(pymupdf.Rect(72, y, 520, y + 60), p, fontsize=10)
        y += 70
    return doc.tobytes()


@pytest.fixture(autouse=True)
def upload_dir() -> Any:
    with tempfile.TemporaryDirectory() as d:
        s = get_settings()
        old = s.upload_dir
        s.upload_dir = d
        yield d
        s.upload_dir = old


@pytest.fixture
def client(seeded: dict[str, str]) -> TestClient:
    make_user("admin@example.com", "Admin", {"accounting": "admin", "grants": "admin"}, superadmin=True)
    make_user("viewer@example.com", "Viewer", {"grants": "viewer"})
    return TestClient(create_app())


def login(c: TestClient, email: str = "admin@example.com") -> dict[str, str]:
    r = c.post("/api/auth/login", json={"email": email, "password": "Sup3r-secret-pw"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf"]}


def cmd(c: TestClient, h: dict[str, str], name: str, body: dict[str, Any], status: int = 200) -> Any:
    r = c.post(f"/api/commands/{name}", json=body, headers=h)
    assert r.status_code == status, r.text
    return r.json().get("result") if status == 200 else r.json()["error"]


def grants_item(c: TestClient, h: dict[str, str]) -> str:
    me = c.get("/api/auth/me").json()
    ws = next(w for w in me["workspaces"] if w["key"] == "grants")
    schema = c.get(f"/api/workspaces/{ws['id']}/schema").json()
    board = next(b for b in schema["boards"] if b["name"] == "FY 2026")
    cid = cmd(c, h, "clients.create", {"name": "Thermo Pty Ltd"})["id"]
    return cmd(
        c, h, "items.create", {"board_id": board["id"], "values": {"name": "Thermo RDTI", "client": cid}}
    )["id"]


def upload(c: TestClient, h: dict[str, str], item_id: str, name: str, data: bytes, **form: str) -> Any:
    r = c.post(f"/api/rdti/items/{item_id}/documents", files={"file": (name, data)}, data=form, headers=h)
    return r


# --- pure functions ------------------------------------------------------------------------


def test_locate_quote_ignores_typography_but_not_wording() -> None:
    text = "We ran 40 runs.\nOvershoot fell from 6.4% to 1.7% — a clear result."
    span = engine.locate_quote(text, "overshoot  fell from 6.4% to 1.7% - a clear")
    assert span is not None and text[span[0] : span[1]].startswith("Overshoot fell")
    assert engine.locate_quote(text, "overshoot dropped from 6.4% to 1.7%") is None
    assert engine.locate_quote(text, "short") is None  # too short to be a meaningful quote


def test_sentences_do_not_split_inside_numbers() -> None:
    text = (
        "Accuracy held at 0.1 degree. Overshoot fell from 6.4% to 1.7%! \u53ef\u4ee5\u3002\u4e0b\u4e00\u53e5"
    )
    got = [text[s:e] for s, e in engine.split_sentences(text)]
    assert got == [
        "Accuracy held at 0.1 degree.",
        "Overshoot fell from 6.4% to 1.7%!",
        "\u53ef\u4ee5\u3002",
        "\u4e0b\u4e00\u53e5",
    ]
    assert engine.split_sentences("") == []


def test_claim_status_rules() -> None:
    ok = engine.CitationCheck(verified=True, support="supports")
    assert engine.claim_status("polish", []) == "polish"
    assert engine.claim_status("fact", []) == "unsupported"
    assert engine.claim_status("fact", [ok]) == "supported"
    assert engine.claim_status("fact", [engine.CitationCheck(False, "supports")]) == "needs_review"
    assert engine.claim_status("fact", [ok, engine.CitationCheck(True, "contradicts")]) == "needs_review"
    assert engine.support_heuristic("fell to 1.7%", "fell to 1.7%")[0] == "supports"
    assert engine.support_heuristic("fell to 1.5%", "fell to 1.7%")[0] == "partial"


def test_extract_docx_and_pdf_keep_locations() -> None:
    d = extract(make_docx(PARAGRAPHS), "notes.docx")
    assert any("40 experiment runs" in p.text for p in d)
    assert all(p.location.startswith("¶") for p in d)
    pdf = extract(make_pdf(PARAGRAPHS), "notes.pdf")
    hit = next(p for p in pdf if "hypothesised" in p.text)
    assert hit.page == 1 and hit.bbox is not None and hit.location.startswith("p.1")


# --- full flow ----------------------------------------------------------------------------


def test_full_flow(client: TestClient) -> None:
    h = login(client)
    item = grants_item(client, h)

    bad = upload(client, h, item, "virus.exe", b"MZ")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unsupported_file"

    r = upload(client, h, item, "Thermo notes.docx", make_docx(PARAGRAPHS))
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]
    assert r.json()["passages"] >= 5

    ca = cmd(client, h, "rdti.create_activity", {"item_id": item, "title": "MPC control under heat"})
    assert ca["code"] == "CA1"
    sa = cmd(
        client,
        h,
        "rdti.create_activity",
        {"item_id": item, "title": "Thermal chamber", "kind": "supporting", "supports_activity_id": ca["id"]},
    )
    assert sa["code"] == "SA1"
    err = cmd(
        client,
        h,
        "rdti.create_activity",
        {"item_id": item, "title": "x", "kind": "supporting", "supports_activity_id": sa["id"]},
        status=422,
    )
    assert "core activity" in err["message"]

    wb = client.get(f"/api/rdti/items/{item}").json()
    assert wb["enabled"] and wb["can_write"] and wb["documents"][0]["passages"] >= 5
    assert wb["ai"]["provider"] == "fake"

    # Assign everything to the core activity, then assess.
    ps = client.get(f"/api/rdti/items/{item}/passages").json()
    cmd(
        client,
        h,
        "rdti.assign_passages",
        {"item_id": item, "chunk_ids": [p["id"] for p in ps], "activity_id": ca["id"]},
    )
    res = cmd(client, h, "rdti.assess_activity", {"activity_id": ca["id"]})
    assert res["assessed"] == 6
    wb = client.get(f"/api/rdti/items/{item}").json()
    cov = {a["element"]: a for a in wb["assessments"][ca["id"]]}
    assert cov["experiment"]["coverage"] in ("sufficient", "partial")
    assert cov["new_knowledge"]["coverage"] == "missing"

    # A human decision survives a re-run.
    cmd(
        client,
        h,
        "rdti.set_assessment",
        {
            "activity_id": ca["id"],
            "element": "new_knowledge",
            "coverage": "partial",
            "rationale": "Discussed in call",
        },
    )
    cmd(client, h, "rdti.assess_activity", {"activity_id": ca["id"]})
    wb = client.get(f"/api/rdti/items/{item}").json()
    nk = next(a for a in wb["assessments"][ca["id"]] if a["element"] == "new_knowledge")
    assert nk["source"] == "human" and nk["coverage"] == "partial"

    # Checklist: gaps become items, once.
    first = cmd(client, h, "rdti.generate_checklist", {"item_id": item})
    assert first["created"] >= 1
    again = cmd(client, h, "rdti.generate_checklist", {"item_id": item})
    assert again["created"] == 0 and again["skipped_existing"] == first["created"]
    mail = client.get(f"/api/rdti/items/{item}/email-draft").json()
    assert "R&D Tax Incentive" in mail["body"] and "Preferred:" in mail["body"]

    # Report: every fact claim is either sourced by a verbatim quote or flagged.
    res = cmd(client, h, "rdti.generate_report", {"activity_id": ca["id"]})
    assert res["sections"] == 6
    rep = client.get(f"/api/rdti/items/{item}/report").json()
    claims = [c for s in rep["sections"] for c in s["claims"]]
    assert rep["totals"]["supported"] >= 3
    for s in rep["sections"]:
        for c in s["claims"]:
            assert s["body"][c["start"] : c["end"]] == c["text"]
            for cit in c["citations"]:
                if cit["verified"]:
                    assert cit["passage"]["text"][cit["quote_start"] : cit["quote_end"]] == cit["quote"]
    assert any(c["status"] == "unsupported" for c in claims)  # new_knowledge has no evidence
    assert any(c["status"] == "polish" for c in claims)

    # Passage context shows what cites it (reverse lookup).
    cited = next(c for c in claims if c["citations"])
    ctx = client.get(f"/api/rdti/passages/{cited['citations'][0]['passage']['id']}").json()
    assert any(x["claim_id"] == cited["id"] for x in ctx["cited_by"])

    # Editing: unchanged claims keep sources, edited ones go to review, new ones are unsupported.
    sec = next(s for s in rep["sections"] if s["element"] == "evaluation")
    sourced = next(c for c in sec["claims"] if c["status"] == "supported")
    edited_text = sourced["text"].replace("fell", "dropped")
    body = sec["body"].replace(sourced["text"], edited_text) + " We also tested a third batch in March."
    res = cmd(
        client,
        h,
        "rdti.update_section",
        {"section_id": sec["id"], "body": body, "expected_version": sec["version"]},
    )
    assert res["edited_claims"] == 1 and res["new_claims"] == 1
    stale = cmd(
        client,
        h,
        "rdti.update_section",
        {"section_id": sec["id"], "body": body, "expected_version": sec["version"]},
        status=422,
    )
    assert stale["code"] == "stale_version"
    rep = client.get(f"/api/rdti/items/{item}/report").json()
    sec = next(s for s in rep["sections"] if s["id"] == sec["id"])
    by_text = {c["text"]: c for c in sec["claims"]}
    assert by_text[edited_text]["status"] == "needs_review" and by_text[edited_text]["citations"]
    new = by_text["We also tested a third batch in March."]
    assert new["status"] == "unsupported" and new["source"] == "human"

    # Marking a factual sentence as our wording needs acknowledgement.
    numeric = next(c for c in sec["claims"] if engine.has_facts(c["text"]))
    err = cmd(client, h, "rdti.review_claim", {"claim_id": numeric["id"], "action": "polish"}, status=422)
    assert err["code"] == "polish_has_facts"
    cmd(client, h, "rdti.review_claim", {"claim_id": new["id"], "action": "polish"})

    # Adding a source needs a quote that really is in the passage.
    target = by_text[edited_text]
    passage = target["citations"][0]["passage"]
    err = cmd(
        client,
        h,
        "rdti.add_citation",
        {"claim_id": target["id"], "chunk_id": passage["id"], "quote": "this sentence is not in the source"},
        status=422,
    )
    assert err["code"] == "quote_not_found"
    cmd(client, h, "rdti.review_claim", {"claim_id": target["id"], "action": "confirm"})

    # Recheck keeps the human confirmation when the source still matches.
    res = cmd(client, h, "rdti.recheck_section", {"section_id": sec["id"]})
    assert res["counts"].get("supported", 0) >= 1

    # Locking needs the approve permission and blocks edits and regeneration.
    cmd(client, h, "rdti.lock_section", {"section_id": sec["id"], "locked": True})
    err = cmd(client, h, "rdti.update_section", {"section_id": sec["id"], "body": "x"}, status=422)
    assert err["code"] == "section_locked"
    res = cmd(client, h, "rdti.generate_report", {"activity_id": ca["id"]})
    assert res["kept_locked"] == 1
    rep = client.get(f"/api/rdti/items/{item}/report").json()
    assert sum(1 for s in rep["sections"] if s["id"] == sec["id"]) == 1

    # A new version of the file puts claims relying on it back to review.
    r = upload(
        client,
        h,
        item,
        "Thermo notes.docx",
        make_docx([*PARAGRAPHS, "Added later."]),
        replaces_file_id=file_id,
    )
    assert r.status_code == 200, r.text
    rep = client.get(f"/api/rdti/items/{item}/report").json()
    locked = next(s for s in rep["sections"] if s["id"] == sec["id"])
    assert all(c["status"] != "supported" for c in locked["claims"] if c["citations"])
    wb = client.get(f"/api/rdti/items/{item}").json()
    assert wb["documents"][0]["version"] == 2
    assert wb["documents"][0]["assigned"] >= 5  # assignments carried over by text

    # Original file can be opened; export works in both modes.
    raw = client.get(f"/api/rdti/files/{file_id}/content?version=1")
    assert raw.status_code == 200 and raw.content[:2] == b"PK"
    for mode in ("clean", "review"):
        r = client.get(f"/api/rdti/items/{item}/export.docx?mode={mode}")
        assert r.status_code == 200
        text = "\n".join(p.text for p in docx.Document(io.BytesIO(r.content)).paragraphs)
        assert "Thermo RDTI" in text
        assert ("Evidence index" in text) == (mode == "review")

    # Activity shows the work.
    act = client.get("/api/activity/entity", params={"entity_type": "item", "entity_id": item}).json()
    assert any(e["entity_type"] == "rdti_activity" for e in act)


def test_permissions_and_consent(client: TestClient) -> None:
    h = login(client)
    item = grants_item(client, h)
    assert upload(client, h, item, "n.txt", "\n\n".join(PARAGRAPHS).encode()).status_code == 200
    ca = cmd(client, h, "rdti.create_activity", {"item_id": item, "title": "MPC"})

    viewer = TestClient(create_app())
    hv = login(viewer, "viewer@example.com")
    assert viewer.get(f"/api/rdti/items/{item}").json()["can_write"] is False
    err = cmd(viewer, hv, "rdti.create_activity", {"item_id": item, "title": "nope"}, status=403)
    assert err["code"] == "permission_denied"
    assert upload(viewer, hv, item, "n.txt", b"hello world text").status_code == 403

    # External model: refused without client consent, before anything is sent.
    s = get_settings()
    s.ai_provider = "anthropic"
    try:
        err = cmd(client, h, "rdti.assess_activity", {"activity_id": ca["id"]}, status=409)
        assert err["code"] == "ai_consent_required"
    finally:
        s.ai_provider = "fake"


def test_no_evidence_is_a_clear_error(client: TestClient) -> None:
    h = login(client)
    item = grants_item(client, h)
    ca = cmd(client, h, "rdti.create_activity", {"item_id": item, "title": "Empty"})
    err = cmd(client, h, "rdti.assess_activity", {"activity_id": ca["id"]}, status=422)
    assert err["code"] == "no_evidence"
