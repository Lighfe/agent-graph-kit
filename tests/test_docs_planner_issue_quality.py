"""Fact tests for self-standing issues and the spec coverage table (issue #197).

They read both copies of docs/team/planner.md. No test runs a subprocess.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "planner.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "planner.md",
]

SENTENCES = (
    "Each issue states the interfaces, the cases and the names it needs in its own body. The plan may be linked as background only",
    'Read every filed issue body. A body that says "implement Task N of the plan" (or the same in other words) without that content in the body is rewritten with `gh issue edit <n> --body-file <path>`',
    "Do this before the label check and before the owner is asked to confirm",
    "holds a coverage table with one row per requirement or section of the spec. Each row gives the number of the issue that covers it (`#<n>`), or \"not in this stage\" with the reason",
    "Read the coverage table in the `## Background` of the stage issue and the spec, and name every spec part that has no closed issue (or say that there is none)",
)


def test_issue_quality_sentences_in_both_copies():
    for path in COPIES:
        text = path.read_text(encoding="utf-8")
        for s in SENTENCES:
            assert s in text, f"{path}: missing {s!r}"


def test_copies_identical():
    assert COPIES[0].read_text(encoding="utf-8") == COPIES[1].read_text(encoding="utf-8")
