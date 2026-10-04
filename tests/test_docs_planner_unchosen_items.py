"""Fact tests for filing the to-be-filed items of options not chosen (issue #129).

They read docs/team/planner.md and docs/specs/agent-graph-kit.md and check
the facts the issue asks for. No test runs gh, git or another subprocess.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANNER = (ROOT / "docs" / "team" / "planner.md").read_text(encoding="utf-8")
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


SETUP = section(PLANNER, "## Stage set-up")


def then_entries():
    """The top-level entries of the "Then:" list, each with its sub-bullets."""
    m = re.search(r"^Then:\n\n(.*?)\n\n", SETUP, re.S | re.M)
    assert m, 'a "Then:" list in "Stage set-up"'
    entries = []
    for line in m.group(1).splitlines():
        if line.startswith("- "):
            entries.append(line)
        else:
            assert line.startswith("  "), line
            entries[-1] += "\n" + line
    return entries


def unchosen_step():
    hits = [e for e in then_entries() if "did not choose" in e]
    assert len(hits) == 1, "one Then entry for the options not chosen"
    return hits[0]


def test_step_comes_before_the_close():
    entries = then_entries()
    step = unchosen_step()
    close = [i for i, e in enumerate(entries) if "Close the finished stage issue" in e]
    assert len(close) == 1
    assert entries.index(step) < close[0]


def test_step_files_follow_ups_with_source():
    step = unchosen_step()
    assert "to be filed" in step
    assert '"New:"' in step
    assert "every option the owner did not choose" in step
    assert "as a follow-up in" in step
    assert "`docs/task-template.md` format" in step
    assert "`later`" in step
    assert "no parent issue" in step
    assert "`Source: <URL of the review comment>`" in step


def test_step_checks_duplicates_and_skips():
    step = unchosen_step()
    assert "no open issue already covers" in step
    assert "instead of filing a duplicate" in step
    assert "already a sub-issue of the new stage" in step
    assert "the owner says not to file" in step


def test_step_no_longer_says_never_needs_owner():
    assert "never gets `needs-owner`" not in PLANNER


def test_step_does_not_call_every_follow_up_parked():
    step = unchosen_step()
    assert "as a parked follow-up" not in step
    assert "a parked follow-up)" not in PLANNER
    # A follow-up with needs-owner is not a parked issue.
    assert "is not a parked issue" in step
    assert '"Follow-ups and parked issues" in `docs/process.md`' in step


def needs_owner_bullet():
    hits = [l for l in unchosen_step().splitlines()
            if "gets the label `needs-owner` in addition to `later`" in l]
    assert len(hits) == 1, "one sub-bullet with the needs-owner rule"
    return hits[0]


def test_needs_owner_cases_and_source():
    rule = needs_owner_bullet()
    for case in (
        "`.claude/hooks/`",
        "the project settings files in `.claude/`",
        "`QA_SANDBOX` in `scripts/qa-codex`",
        "spends money or quota",
    ):
        assert case in rule, case
    assert '"Escalation" in `docs/process.md`' in rule
    assert "states in words what the owner decides" in rule


def test_every_other_follow_up_gets_only_later():
    step = unchosen_step()
    assert "Every other follow-up filed here gets only `later` (no `needs-owner`)" in step
    assert "for another reason (for example a scope question)" in step
    assert "also gets only `later`" in step
    assert "its body says in words what the owner must decide" in step


def test_label_only_on_issues_the_planner_files():
    step = unchosen_step()
    assert "only to issues you file" in step
    assert "do not change the labels of that issue" in step


def test_approval_points_to_escalation_without_restating():
    step = unchosen_step()
    assert 'For the owner\'s approval, see "Escalation" in `docs/process.md`' in step
    assert "remove `needs-owner` to approve" not in step
    assert "not planned" not in step


def test_step_reads_on_its_own():
    step = unchosen_step()
    assert "reads on its own" in step
    assert '"Option 2"' in step and '"point 3"' in step
    assert "restate" in step


def test_step_reports_filed_and_not_filed_to_the_owner():
    step = unchosen_step()
    assert "number and title" in step
    assert "did not file" in step
    for reason in ("covered by an open issue", "already in the new stage", "the owner said not to file it"):
        assert reason in step, reason


def test_denied_relabel_resumes_at_then_so_the_step_still_runs():
    rule = section(PLANNER, "### Denied relabel")
    assert 'in "Stage set-up" with the steps under "Then"' in rule


def test_spec_closing_bullet_names_the_filing():
    lines = [l for l in SPEC.splitlines() if l.startswith("- **Closing**:")]
    assert len(lines) == 1
    line = lines[0]
    assert "options not chosen" in line
    assert "parked follow-ups" not in line
    assert "as follow-ups" in line
    assert "`needs-owner`" in line
    assert "Before the close" in line
    assert "docs/team/planner.md" in line
