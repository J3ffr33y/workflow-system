"""Pure functions behind the R&D report: no database, no network.

* quote verification (is the cited text really in the passage?)
* sentence segmentation for claims
* claim status rules
* the deterministic "fake" answers used when no model is configured. They
  are deliberately simple (keyword matching, sentence picking) but follow the
  same output shapes as the model, so the whole flow can be demonstrated and
  tested offline.

Kept free of app.modules imports so it can be extracted as its own package
(see ADR-0009).
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.modules.rdti import rules

# --- text normalisation and quote matching ---------------------------------------------

_QUOTES = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "}
)


def _norm_char_map(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each normalised character, its index in the
    original. Normalising quotes, dashes, case and whitespace lets a quote
    that differs only in typography still match, while offsets stay exact."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        c = unicodedata.normalize("NFKC", ch).translate(_QUOTES).lower()
        for cc in c:
            if cc.isspace():
                if prev_space:
                    continue
                out.append(" ")
                idx.append(i)
                prev_space = True
            else:
                out.append(cc)
                idx.append(i)
                prev_space = False
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def locate_quote(haystack: str, quote: str) -> tuple[int, int] | None:
    """Character span of ``quote`` inside ``haystack`` or None. Matching
    ignores case, whitespace runs and curly-vs-straight punctuation, nothing
    else: a paraphrase is not a quote."""
    q, _ = _norm_char_map(quote.strip().strip("\"'"))
    if len(q) < 8:
        return None
    h, hidx = _norm_char_map(haystack)
    pos = h.find(q)
    if pos < 0:
        return None
    return hidx[pos], hidx[pos + len(q) - 1] + 1


# --- sentences -----------------------------------------------------------------------

# A full stop only ends a sentence when whitespace or the end follows it, so
# "0.1 degree" and "6.4%" stay inside one claim. CJK stops need no space.
_SENT_END = re.compile(r"[.!?]+[\"'\u201d\u2019)]*(?=\s|$)|[\u3002\uff01\uff1f]+[\u201d\u2019)]*")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Spans of sentences in ``text`` (surrounding whitespace excluded)."""
    spans: list[tuple[int, int]] = []
    cuts = [m.end() for m in _SENT_END.finditer(text)]
    if not cuts or cuts[-1] < len(text):
        cuts.append(len(text))
    start = 0
    for end in cuts:
        s, e = start, end
        start = end
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e - s >= 2:
            spans.append((s, e))
    return spans


def has_facts(text: str) -> bool:
    return any(re.search(p, text) for p in rules.FACT_PATTERNS)


# --- claim status --------------------------------------------------------------------


@dataclass
class CitationCheck:
    verified: bool
    support: str  # supports | partial | contradicts


def claim_status(kind: str, citations: list[CitationCheck]) -> str:
    if kind == "polish":
        return "polish"
    if not citations:
        return "unsupported"
    trusted = [c for c in citations if c.verified]
    if any(c.support == "contradicts" for c in trusted):
        return "needs_review"
    if any(c.support == "supports" for c in trusted):
        return "supported"
    return "needs_review"


def numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def support_heuristic(claim: str, quote: str) -> tuple[str, str]:
    """Offline support check: numbers in the claim must appear in the quote."""
    missing = numbers_in(claim) - numbers_in(quote)
    if missing:
        return "partial", f"The source does not contain: {', '.join(sorted(missing))}."
    return "supports", "The quoted source states this."


# --- fake model answers ----------------------------------------------------------------

SUMMARY_MARKERS = [
    "successfully",
    "significant",
    "innovative",
    "cutting-edge",
    "overall",
    "in summary",
    "various",
    "improved",
    "enhanced",
    "state-of-the-art",
]


def _score(text: str, keywords: list[str]) -> int:
    t = text.lower()
    return sum(1 for k in keywords if k in t)


def fake_assessment(kind: str, passages: list[dict[str, Any]]) -> dict[str, Any]:
    out = []
    for el in rules.elements_for(kind):
        hits = [p for p in passages if _score(p["text"], el["keywords"]) > 0]
        hits.sort(key=lambda p: -_score(p["text"], el["keywords"]))
        with_numbers = [p for p in hits if has_facts(p["text"])]
        summary_only = bool(hits) and not with_numbers and el["key"] in ("experiment", "evaluation")
        if not hits:
            coverage, why = "missing", "No passage in the material addresses this element."
        elif len(hits) >= 2 and not summary_only:
            coverage, why = "sufficient", f"{len(hits)} passages address this element with specifics."
        else:
            coverage = "partial"
            why = (
                "Mentioned, but only in summary terms without measurements or dates."
                if summary_only
                else "Only one passage addresses this element; details are thin."
            )
        out.append(
            {
                "element": el["key"],
                "coverage": coverage,
                "rationale": why,
                "summary_only": summary_only,
                "chunk_ids": [p["id"] for p in hits[:6]],
            }
        )
    return {"elements": out}


def fake_report(
    activity: dict[str, Any], passages: list[dict[str, Any]], assessments: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    by_id = {p["id"]: p for p in passages}
    sections = []
    for el in rules.elements_for(activity["kind"]):
        a = assessments.get(el["key"])
        ids = (a or {}).get("chunk_ids") or [
            p["id"] for p in passages if _score(p["text"], el["keywords"]) > 0
        ][:4]
        claims: list[dict[str, Any]] = [
            {
                "text": f"This section sets out the {el['label'].lower()} for {activity['title']}.",
                "kind": "polish",
                "citations": [],
            }
        ]
        used = 0
        for cid in ids:
            p = by_id.get(cid)
            if p is None:
                continue
            for s, e in split_sentences(p["text"]):
                sentence = p["text"][s:e]
                if len(sentence) < 30 or _score(sentence, el["keywords"]) == 0:
                    continue
                claims.append(
                    {"text": sentence, "kind": "fact", "citations": [{"chunk_id": cid, "quote": sentence}]}
                )
                used += 1
                break
            if used >= 3:
                break
        if used == 0:
            claims.append(
                {
                    "text": f"[To be completed: no evidence yet for the {el['label'].lower()}.]",
                    "kind": "fact",
                    "citations": [],
                }
            )
        sections.append({"element": el["key"], "heading": el["label"], "claims": claims})
    return {"sections": sections}


# --- prompts and schemas for the real model ---------------------------------------------


def passages_block(passages: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f'<passage id="{p["id"]}" file="{p["file"]}" location="{p["location"]}">\n{p["text"]}\n</passage>'
        for p in passages
    )


ASSESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string", "enum": rules.ELEMENT_KEYS},
                    "coverage": {"type": "string", "enum": list(rules.COVERAGE)},
                    "rationale": {"type": "string"},
                    "summary_only": {"type": "boolean"},
                    "chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["element", "coverage", "rationale", "summary_only", "chunk_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["elements"],
    "additionalProperties": False,
}

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string", "enum": rules.ELEMENT_KEYS},
                    "heading": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "kind": {"type": "string", "enum": ["fact", "polish"]},
                                "citations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "chunk_id": {"type": "string"},
                                            "quote": {"type": "string"},
                                        },
                                        "required": ["chunk_id", "quote"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["text", "kind", "citations"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["element", "heading", "claims"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}

SUPPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "citation_id": {"type": "string"},
                    "support": {"type": "string", "enum": ["supports", "partial", "contradicts"]},
                    "rationale": {"type": "string"},
                },
                "required": ["citation_id", "support", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["checks"],
    "additionalProperties": False,
}


def assess_prompt(activity: dict[str, Any], passages: list[dict[str, Any]]) -> tuple[str, str]:
    els = rules.elements_for(activity["kind"])
    system = (
        "You review evidence for an Australian R&D Tax Incentive (RDTI) claim on behalf of a consultant. "
        "For each element, judge how well the supplied passages evidence it: 'sufficient', 'partial' or "
        "'missing'. Set summary_only when the material only describes the work in general or promotional "
        "terms without concrete experiments, measurements or dates. List the passage ids you relied on. "
        "Judge only from the passages; do not assume facts that are not written there. Your output is a "
        "draft the consultant will review."
    )
    criteria = "\n".join(
        f"- {e['key']} ({e['label']}): {e['question']} Sufficient means: {e['sufficient']}" for e in els
    )
    user = (
        f"Activity {activity['code']}: {activity['title']} ({activity['kind']} activity)\n"
        f"{activity.get('description') or ''}\n\nElements to assess:\n{criteria}\n\n"
        f"Evidence passages:\n{passages_block(passages)}"
    )
    return system, user


def report_prompt(
    activity: dict[str, Any], passages: list[dict[str, Any]], assessments: dict[str, dict[str, Any]]
) -> tuple[str, str]:
    els = rules.elements_for(activity["kind"])
    system = (
        "You draft the technical section of an Australian R&D Tax Incentive report for one R&D activity, "
        "for a consultant to review and edit. Write one section per element, as a list of claims. A claim "
        "is one sentence or a few sentences making one point. Mark each claim 'fact' (it states something "
        "that was unknown, done, measured, decided or learned) or 'polish' (it only introduces or connects). "
        "Every fact claim must cite at least one passage with an exact quote copied character for character "
        "from that passage; if no passage supports a point, leave the point out or write a fact claim with no "
        "citations that starts with '[To be completed:' so the gap is visible.\n\nWriting rules:\n"
        + "\n".join(f"- {r}" for r in rules.WRITING_RULES)
    )
    notes = "\n".join(
        f"- {e['key']} ({e['label']}): coverage {assessments.get(e['key'], {}).get('coverage', 'unknown')}. "
        f"{e['question']}"
        for e in els
    )
    user = (
        f"Activity {activity['code']}: {activity['title']} ({activity['kind']} activity)\n"
        f"{activity.get('description') or ''}\n\nSections to write, in this order:\n{notes}\n\n"
        f"Evidence passages:\n{passages_block(passages)}"
    )
    return system, user


def support_prompt(items: list[dict[str, Any]]) -> tuple[str, str]:
    system = (
        "You check whether quoted evidence supports a sentence from an R&D report. Answer 'supports' only if "
        "the quote states what the sentence says, including every number, date and name; 'partial' if it "
        "supports part of it; 'contradicts' if it says something different. Give a one-sentence reason."
    )
    body = "\n\n".join(
        f'<check citation_id="{i["citation_id"]}">\n<sentence>{i["claim"]}</sentence>\n'
        f"<quote>{i['quote']}</quote>\n</check>"
        for i in items
    )
    return system, body
