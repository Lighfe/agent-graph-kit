"""Fact tests for who closes which issue (issue #118).

They read AGENTS.md and docs/team/orchestrator.md and check the facts the
issue asks for. No test runs gh, git or another subprocess.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
ORCH = (ROOT / "docs" / "team" / "orchestrator.md").read_text(encoding="utf-8")


def section(text, heading):
    """The text from a heading line to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    start = lines.index(heading)
    out = []
    for line in lines[start + 1:]:
        m = re.match(r"^(#+) ", line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return "\n".join(out)


def close_line():
    lines = [
        line
        for line in section(AGENTS, "## Commands").splitlines()
        if line.startswith("- `gh issue close <number>`")
    ]
    assert len(lines) == 1
    return lines[0]


def test_agents_close_line_drops_orchestrator_only():
    assert "orchestrator only" not in close_line()


def test_agents_close_line_names_both_closers():
    line = close_line()
    assert "## QA: PASS" in line
    assert "task issue" in line
    assert "stage issue" in line
    assert "all its sub-issues closed" in line
    assert "stage set-up" in line
    assert "docs/team/orchestrator.md" in line
    assert "docs/team/planner.md" in line


def test_orchestrator_close_section_task_issues_only():
    text = section(ORCH, "## Close an issue")
    assert "task issues only" in text
    assert "does not close a stage issue" in text
    assert "The planner closes it at stage set-up" in text
    # The hook statement for a stage issue stays, applied to the planner's close.
    assert "all its sub-issues are closed instead of the verified SHA" in text
    assert "planner" in text


def test_stage_end_sentence_kept():
    assert "Do not close the stage issue. The planner closes it at stage set-up" in ORCH
