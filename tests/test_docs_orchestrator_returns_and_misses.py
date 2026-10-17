"""Fact tests for the escalation count, miss diagnosis and idle launch note (issue #206). Read-only."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "orchestrator.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "orchestrator.md",
]


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_escalation_for_returns_names_count():
    for p in COPIES:
        t = flat(p)
        assert "An escalation for returns names the count from the rule (3) in its comment." in t, p
        assert "Count the returns on the issue before you escalate" in t, p


def test_read_only_diagnosis_after_two_misses():
    for p in COPIES:
        t = flat(p)
        assert (
            "After two misses of the same step, you may diagnose read-only before you escalate "
            "(journal, `git log`, a memory-capped test run). Put the finding in the escalation comment."
        ) in t, p


def test_run_notes_list_idle_launch():
    for p in COPIES:
        assert (
            "a launch with no result for more than 30 minutes, with its issue and the time"
        ) in flat(p), p
