"""Fact tests for the final report line on a blocker in another repo (issue #202). Read-only."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "orchestrator.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "orchestrator.md",
]


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_foreign_blocker_report_line_form():
    for p in COPIES:
        assert (
            "`Waiting for <owner/repo>#<n>: <title>. Close it, then the loop can start again.`"
        ) in flat(p), p


def test_foreign_blocker_line_once_per_blocker():
    for p in COPIES:
        t = flat(p)
        assert "The line appears once per blocker in the report, not once per waiting issue" in t, p
        assert "The loop stops and does not re-check the blocker" in t, p
