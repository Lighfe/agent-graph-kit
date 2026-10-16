"""Fact tests for the PM follow-up rule with needs-owner (issue #154). Read-only, no subprocess."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "pm.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "pm.md",
]


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_hook_settings_sandbox_money_followup_gets_needs_owner():
    for p in COPIES:
        t = flat(p)
        assert (
            "A follow-up whose change edits the hooks, the project settings files in `.claude/`, "
            "or the QA sandbox arguments of `scripts/qa-codex`, or whose work spends money or quota, "
            "gets the label `needs-owner` in addition to `later`, "
            "and its body states in words what the owner decides"
        ) in t


def test_other_followups_keep_only_later():
    for p in COPIES:
        t = flat(p)
        assert "Every other follow-up gets only `later`." in t
        assert "A follow-up never gets the label `needs-owner`" not in t


def test_both_copies_are_equal():
    assert COPIES[0].read_bytes() == COPIES[1].read_bytes()
