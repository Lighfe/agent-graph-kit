"""Fact tests for the engineer's test runs, background commands and clean hand-back (issue #141).

They read docs/team/software-engineer.md and docs/specs/agent-graph-kit.md and
check the facts the issue asks for. No test runs gh, git or another subprocess.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINEER = (ROOT / "docs" / "team" / "software-engineer.md").read_text(encoding="utf-8")
SPEC = (ROOT / "docs" / "specs" / "agent-graph-kit.md").read_text(encoding="utf-8")


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


def flat(text):
    return re.sub(r"\s+", " ", text)


TESTS = flat(section(ENGINEER, "## Test runs and background commands"))
HANDBACK = flat(section(ENGINEER, "## Clean hand-back"))
GO_ON = flat(section(ENGINEER, "## Going on after a launch without a result"))
FRONTEND = flat(section(ENGINEER, "## Lane `frontend`"))


def test_foreground_test_run_with_600000_timeout():
    assert "`uv run --with pytest pytest`" in TESTS
    assert "foreground" in TESTS
    assert "600000 ms" in TESTS


def test_timeout_rerun_in_background_and_wait():
    assert "`run_in_background`" in TESTS
    assert re.search(r"hits the timeout.*run it again.*`run_in_background`", TESTS)
    assert re.search(r"wait (for it )?until it (has )?end", TESTS) or "wait for it to end" in TESTS
    assert "before you read the result" in TESTS


def test_background_commands_end_or_stop_before_hand_back():
    assert re.search(r"wait for it to end.*or stop it", TESTS)
    assert "does not end by itself" in TESTS
    assert "Never hand back while a test run is still going" in TESTS


def test_hand_back_defined_with_all_three_ends():
    assert "## Engineer: DONE" in HANDBACK
    assert "## Engineer: BLOCKED" in HANDBACK
    assert "without a result marker" in HANDBACK


def test_clean_tree_before_every_hand_back():
    assert "`git status --porcelain` is empty" in HANDBACK
    assert "Commit the work that belongs to the issue, or reset it" in HANDBACK
    assert "changed tracked files" in HANDBACK
    assert "new untracked files" in HANDBACK


def test_go_on_after_miss_reads_status_and_log_first():
    assert "ended without a result" in GO_ON
    assert "`git status`" in GO_ON and "`git log`" in GO_ON
    assert "first" in GO_ON


def test_go_on_after_miss_keeps_and_finishes_or_resets():
    assert re.search(r"review it, test it,? (and )?commit it", GO_ON)
    assert re.search(r"[Rr]eset (the )?work you cannot account for", GO_ON)


def test_go_on_after_miss_commit_range_starts_before_earlier_commits():
    assert "`Commits: <base>..<head>`" in GO_ON
    assert "before the first commit" in GO_ON
    assert "not simply `HEAD`" in GO_ON


def test_frontend_lane_names_the_new_rules():
    for name in ("Test runs and background commands", "Clean hand-back",
                 "Going on after a launch without a result"):
        assert name in FRONTEND, name
    assert "`git submodule update frontend`" in FRONTEND


def test_existing_rules_kept():
    assert "`git rev-parse HEAD`" in ENGINEER
    assert "## Body files" in ENGINEER
    assert "first line of the comment is exactly `## Engineer: BLOCKED`" in ENGINEER


def test_spec_g1_clean_tree_reason_kept():
    # issue #142 adds the exception for a role that ended early to the reason
    assert ("5. The working tree is clean (`git status --porcelain` is empty). This works because no role "
            "may leave uncommitted work, except a role that ended without a result") in SPEC
