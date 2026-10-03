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


def test_step_files_parked_follow_ups_with_source():
    step = unchosen_step()
    assert "to be filed" in step
    assert '"New:"' in step
    assert "every option the owner did not choose" in step
    assert "parked follow-up" in step
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


def test_step_never_adds_needs_owner_and_reads_on_its_own():
    step = unchosen_step()
    assert "never gets `needs-owner`" in step
    assert "says so in words" in step
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
    assert "parked follow-ups" in line
    assert "Before the close" in line
    assert "docs/team/planner.md" in line
