"""Fact tests for the stage issue with a wrong `ready` label (issue #195).

They read doc files and check the list command and the removal rule.
No test runs gh, git or another subprocess.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEW_COMMAND = (
    'gh issue list --state open --label ready '
    '--search "-label:later -label:needs-owner -label:stage"'
)
OLD_SEARCH = '-label:later -label:needs-owner"'
LIST_FILES = (
    "AGENTS.md",
    "plugin/templates/AGENTS.md.tmpl",
    "docs/team/orchestrator.md",
    "plugin/templates/docs/team/orchestrator.md",
)
ORCHESTRATOR_FILES = LIST_FILES[2:]
PROCESS_FILES = ("docs/process.md", "plugin/templates/docs/process.md")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", LIST_FILES)
def test_list_command_excludes_stage_issues(rel):
    text = read(rel)
    assert NEW_COMMAND in text
    assert OLD_SEARCH not in text


@pytest.mark.parametrize("rel", ORCHESTRATOR_FILES)
def test_orchestrator_removes_ready_from_stage_issue(rel):
    text = read(rel)
    assert "gh issue edit <n> --remove-label ready" in text
    assert "stage issue with a wrong label" in text
    assert "When no open stage issue has `ready`, do nothing." in text


@pytest.mark.parametrize("rel", PROCESS_FILES)
def test_process_stop_condition_skips_stage_issues(rel):
    text = read(rel)
    assert "stage issues are not counted among the `ready` issues" in text
    assert "(stage issues are not counted)" in text


def test_process_copy_equal_in_changed_lines():
    keys = ("Stop condition for `/goal`", "9. Repeat until")
    a, b = (read(f).splitlines() for f in PROCESS_FILES)
    for key in keys:
        assert [l for l in a if l.startswith(key)] == [l for l in b if l.startswith(key)]
