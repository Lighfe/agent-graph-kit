"""Fact tests for the planner label check and sibling references (issue #196).

They read both copies of docs/team/planner.md. No test runs a subprocess.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "planner.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "planner.md",
]

SENTENCES = (
    'replace every "task N" / "Task N" reference to a sibling',
    "the stage issue has `stage` and no `ready`, and every sub-issue has `later` and no `ready`",
    "every sub-issue has `ready` and no `later`, and the stage issue has no `ready`",
    "If the stage issue has `ready`, remove it",
    "also an existing issue linked in step 5",
    "Do this before the label check and before the owner is asked to confirm",
    '"Stage set-up" step 9',
)


def test_new_sentences_in_both_copies():
    for path in COPIES:
        text = path.read_text(encoding="utf-8")
        for s in SENTENCES:
            assert s in text, f"{path}: missing {s!r}"


def test_copies_are_identical():
    assert COPIES[0].read_text() == COPIES[1].read_text()


def test_old_step_numbering_gone():
    for path in COPIES:
        assert '"Stage set-up" step 7' not in path.read_text(encoding="utf-8")


def test_setup_asks_confirmation_only_after_label_check():
    for path in COPIES:
        text = path.read_text(encoding="utf-8")
        assert "with these permissions only in step 8, after the label check" in text
        assert "Fix a gap first. Then ask the owner to confirm the stage" in text
        assert "Fix a gap before you ask the owner to confirm the stage" not in text
