"""The RDTI rule set: elements an R&D activity must evidence, what counts as
sufficient, and what to ask the client for when it is missing.

Kept as data (not logic) so assessment, checklist and report generation all
read the same definitions, and the writing conventions can change without
touching code. Version it: every assessment records the rule version it used.
EMDG or State Grants would be another rule set with the same shape.
"""

from typing import Any

RULESET_KEY = "rdti"
RULESET_VERSION = "2026.11-1"

# Order matters: it is the order of report sections.
ELEMENTS: list[dict[str, Any]] = [
    {
        "key": "technical_uncertainty",
        "label": "Technical uncertainty",
        "label_zh": "技术不确定性",
        "applies_to": ["core"],
        "question": "What outcome could not be known or determined in advance, by a competent professional, "
        "on the basis of current knowledge, information or experience?",
        "sufficient": "Names the specific technical unknown, explains why existing knowledge (literature, "
        "experts, prior products) could not resolve it, and dates when it was identified.",
        "keywords": [
            "uncertain",
            "unknown",
            "not known",
            "no existing",
            "could not be determined",
            "state of the art",
            "literature",
            "prior art",
            "challenge",
            "unclear whether",
        ],
        "preferred": "Technical design notes or meeting minutes from the start of the project that state the problem",
        "alternatives": [
            "Literature or patent search results",
            "Emails with suppliers or experts saying no solution existed",
            "Early project plan describing the risk",
        ],
        "example": "'We could not determine whether the sensor could hold ±0.1 °C accuracy above 80 °C; "
        "no supplier datasheet covered that range.'",
    },
    {
        "key": "hypothesis",
        "label": "Hypothesis",
        "label_zh": "假设",
        "applies_to": ["core"],
        "question": "What hypothesis was formed to resolve the uncertainty?",
        "sufficient": "A testable statement of the expected cause and effect, written before the experiment.",
        "keywords": [
            "hypothes",
            "we expected",
            "we predicted",
            "we believed",
            "proposed that",
            "if we",
            "should result in",
            "anticipated",
        ],
        "preferred": "Experiment plan or design document stating the expected result before testing",
        "alternatives": [
            "Sprint or ticket descriptions stating the expected outcome",
            "Lab notebook entries",
        ],
        "example": "'Replacing the PID loop with model-predictive control will cut overshoot below 2%.'",
    },
    {
        "key": "experiment",
        "label": "Experiment",
        "label_zh": "实验",
        "applies_to": ["core"],
        "question": "What systematic experiments were carried out to test the hypothesis?",
        "sufficient": "Describes method, variables, setup, iterations and dates, not just that testing happened.",
        "keywords": [
            "experiment",
            "test",
            "trial",
            "prototype",
            "iteration",
            "built",
            "measured",
            "benchmark",
            "simulation",
            "setup",
            "method",
        ],
        "preferred": "Test plans and test reports with dates, setup and parameters",
        "alternatives": [
            "Git commit history or pull requests for the prototype",
            "Photos of test rigs with dates",
            "Jira tickets showing iterations",
        ],
        "example": "Test report v3 (12 March): 40 runs at 60/70/80 °C, sample rate 10 Hz, two sensor batches.",
    },
    {
        "key": "evaluation",
        "label": "Evaluation",
        "label_zh": "评估",
        "applies_to": ["core"],
        "question": "How were the results observed and evaluated against the hypothesis?",
        "sufficient": "Contains measured results (numbers, metrics, pass/fail criteria) and compares them with "
        "the expected outcome.",
        "keywords": [
            "result",
            "measured",
            "%",
            "accuracy",
            "error",
            "performance",
            "compared",
            "analysis",
            "observed",
            "metric",
            "failed",
            "passed",
        ],
        "preferred": "Result tables, test logs or analysis reports with the measured values",
        "alternatives": ["Dashboards or screenshots of metrics with dates", "Bug reports with measurements"],
        "example": "'Overshoot fell from 6.4% to 1.7% across 40 runs; batch B failed above 78 °C.'",
    },
    {
        "key": "conclusion",
        "label": "Conclusion",
        "label_zh": "结论",
        "applies_to": ["core"],
        "question": "What logical conclusions were drawn from the results?",
        "sufficient": "States whether the hypothesis held and what was decided next because of it.",
        "keywords": [
            "conclud",
            "therefore",
            "as a result",
            "we decided",
            "confirmed",
            "disproved",
            "outcome",
            "next step",
            "abandoned",
        ],
        "preferred": "Review notes, retrospective or decision records after testing",
        "alternatives": ["Emails announcing the decision", "Updated design documents"],
        "example": "'MPC confirmed for production firmware; batch B sensors dropped.'",
    },
    {
        "key": "new_knowledge",
        "label": "New knowledge",
        "label_zh": "新知识",
        "applies_to": ["core"],
        "question": "What new knowledge was generated?",
        "sufficient": "Knowledge that did not exist before (not just a new product for the company), described "
        "concretely.",
        "keywords": [
            "new knowledge",
            "learned",
            "discovered",
            "insight",
            "novel",
            "first time",
            "now know",
            "generalis",
            "contribut",
        ],
        "preferred": "Final technical report or internal knowledge write-up",
        "alternatives": ["Conference talks, papers or patents", "Internal wiki page summarising findings"],
        "example": "'MPC tuned with a thermal lag model holds ±0.1 °C to 85 °C on low-cost sensors.'",
    },
    {
        "key": "support_link",
        "label": "Support of core activity",
        "label_zh": "对核心活动的支持",
        "applies_to": ["supporting"],
        "question": "How did this activity directly support a core R&D activity?",
        "sufficient": "Names the core activity and explains why this work was undertaken for it (dominant purpose "
        "where required).",
        "keywords": [
            "support",
            "enabled",
            "required for",
            "in order to",
            "to allow",
            "for the core",
            "data collection",
            "tooling",
            "test rig",
        ],
        "preferred": "Project plan linking this work to the core experiment",
        "alternatives": ["Timesheets or tickets referencing the core activity"],
        "example": "'Built the thermal chamber solely to run the core MPC experiments.'",
    },
]

ELEMENT_KEYS = [e["key"] for e in ELEMENTS]
COVERAGE = ("sufficient", "partial", "missing")

# Words that make a sentence a factual statement. A sentence marked as
# "polish" (our own wording) must not contain them unchecked.
FACT_PATTERNS = [r"\d", r"%", r"\b(19|20)\d{2}\b"]

WRITING_RULES = [
    "Write in the past tense, in plain professional English, as the claimant company ('we').",
    "Every factual sentence (what was unknown, done, measured, decided or learned) must be supported by "
    "a quote from the supplied evidence. Never invent numbers, dates, names or results.",
    "Sentences that only connect or introduce ideas are allowed without evidence, but must not add facts.",
    "Prefer specific measured results over general claims; do not use marketing language.",
    "Do not say the activity is eligible for RDTI; the consultant decides eligibility.",
]

EMAIL_TEMPLATE = (
    "Dear {contact},\n\n"
    "Thank you for the material you have sent for {project}. To finish the R&D Tax Incentive technical "
    "report we need a few more items. They serve two purposes: to fill gaps in the technical description, "
    "and to keep the records the ATO and AusIndustry expect as evidence of the R&D activities.\n\n"
    "{items}\n\n"
    "For each item, the first document listed is preferred; if you do not have it, the alternatives "
    "are fine. Please do not re-send anything you have already given us.\n\n"
    "Kind regards,\n{sender}"
)


def element(key: str) -> dict[str, Any]:
    for e in ELEMENTS:
        if e["key"] == key:
            return e
    raise KeyError(key)


def elements_for(kind: str) -> list[dict[str, Any]]:
    return [e for e in ELEMENTS if kind in e["applies_to"]]


def public() -> dict[str, Any]:
    return {
        "key": RULESET_KEY,
        "version": RULESET_VERSION,
        "elements": [
            {
                k: e[k]
                for k in (
                    "key",
                    "label",
                    "label_zh",
                    "applies_to",
                    "question",
                    "sufficient",
                    "preferred",
                    "alternatives",
                    "example",
                )
            }
            for e in ELEMENTS
        ],
        "writing_rules": WRITING_RULES,
    }
