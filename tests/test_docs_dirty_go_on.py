"""Fact tests for the go-on after one miss with a dirty tree (issue #142).

They read docs/specs/agent-graph-kit.md and docs/team/orchestrator.md and check the facts the
issue asks for. No test runs gh, git or another subprocess.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs" / "specs" / "agent-graph-kit.md").read_text(encoding="utf-8")
ORCH = (ROOT / "docs" / "team" / "orchestrator.md").read_text(encoding="utf-8")

NOT_CLEAN = "`G1: working tree is not clean, expected a clean tree (git status --porcelain empty)`"


def flat(text):
    return re.sub(r"\s+", " ", text)


def step5():
    m = re.search(r"^5\. The working tree is clean.*$", SPEC, re.M)
    assert m, "G1 step 5 not found"
    return flat(m.group(0))


def test_spec_step5_names_the_exception():
    text = step5()
    assert "`pm`, `engineer` or `qa`" in text
    assert "pending after one miss of that same role" in text
    assert "the role match of step 7" in text
    assert "two misses in a row" in text and "two-misses message of step 7" in text
    assert "by issue state only, never by file content" in text
    assert NOT_CLEAN in text


def test_spec_step5_names_the_reason():
    text = step5()
    assert "a role that ended early may leave uncommitted work, and the go-on finishes or resets it" in text
    assert "This works because no role may leave uncommitted work." not in text
    assert "This works because no role may leave uncommitted work, except" in text


def one_miss_bullet():
    m = re.search(r"^- One miss: .*$", ORCH, re.M)
    assert m, "one-miss bullet not found"
    return flat(m.group(0))


def test_orchestrator_one_miss_bullet_says_a_dirty_tree_does_not_stop_the_go_on():
    text = one_miss_bullet()
    assert "A dirty tree does not stop this go-on of `pm`, `engineer` or `qa`" in text
    assert "you do not run your own clean-tree stop" in text
    assert "may have left uncommitted work, so the agent runs `git status` first" in text


def test_orchestrator_before_each_issue_names_the_go_on_exception():
    assert "This check does not apply to the go-on after one miss" in flat(ORCH)


def test_orchestrator_not_clean_deny_still_stops_the_loop():
    assert "- `G1` working tree not clean: stop the loop and ask the owner\n" in ORCH
