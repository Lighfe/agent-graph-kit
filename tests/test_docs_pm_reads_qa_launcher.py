"""Fact tests for the PM step that reads the QA launcher before NEEDS OWNER (issue #261). Read-only, no subprocess."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "pm.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "pm.md",
]


def section(path, heading):
    text = path.read_text(encoding="utf-8")
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return re.sub(r"\s+", " ", text[start:end if end != -1 else None])


def test_tool_problem_section_has_read_the_launcher_step():
    for p in COPIES:
        s = section(p, "A tool problem that an issue can fix")
        assert "Before you post `## PM: NEEDS OWNER` for a QA sandbox or QA tool problem, read the QA launcher and the project settings it reads" in s
        assert "`scripts/qa-codex`" in s
        assert "`qa-codex-launcher`" in s
        assert "`command -v qa-codex-launcher`" in s
        assert "the `QA groups:` line of `AGENTS.md`" in s
        assert "Name in your comment what you read" in s


def test_setting_cause_takes_fix_issue_path():
    for p in COPIES:
        s = section(p, "A tool problem that an issue can fix")
        assert (
            "When the cause is a project setting that a change in this repo fixes "
            "(for example a missing `QA groups:` line), follow the fix-issue path below "
            "and post `## PM: WAITING`, not `## PM: NEEDS OWNER`"
        ) in s


def test_unverifiable_case_c_points_to_the_step():
    for p in COPIES:
        s = section(p, "After `## QA: UNVERIFIABLE`")
        assert (
            "Before you post `## PM: NEEDS OWNER` here, read the QA launcher and its settings "
            "as \"A tool problem that an issue can fix\" says"
        ) in s


def test_both_copies_are_equal():
    assert COPIES[0].read_bytes() == COPIES[1].read_bytes()
