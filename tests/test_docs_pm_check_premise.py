"""Fact tests for the PM rule "Check the premise" (issue #198). Read-only, no subprocess."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "pm.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "pm.md",
]
HEADING = "## Check the premise"


def flat(text):
    return re.sub(r"\s+", " ", text)


def section(path):
    t = path.read_text(encoding="utf-8")
    start = t.find(HEADING + "\n")
    assert start >= 0, f"section not found in {path}"
    end = t.find("\n## ", start + len(HEADING))
    return flat(t[start : end if end >= 0 else len(t)])


def test_rule_names_the_premise_check():
    for p in COPIES:
        s = section(p)
        assert "an equality, the behavior of a library, a dependency, or a count over a set that may be empty" in s
        assert "read the code or run a one-line check before you pass the issue on" in s


def test_rule_gives_the_wording_examples():
    for p in COPIES:
        s = section(p)
        assert 'write "ignoring the fields `request_id` and `created_at`" instead of "identical records"' in s
        assert 'write "for each finding that names a problem" instead of "each finding"' in s


def test_rule_forbids_criteria_on_unrun_library_output():
    for p in COPIES:
        s = section(p)
        assert "Do not write a criterion on the logging or output of a library that nobody has run" in s
        assert "Run it first, or state the observed behavior in the issue" in s


def test_rule_bounds_full_scale_runs():
    for p in COPIES:
        s = section(p)
        assert "also asks for a smaller run as the check" in s
        assert "the measured peak memory in `## Engineer: DONE`" in s
        assert 'as a bound (for example "at most 5,000 rows"), not as "at least"' in s


def test_both_copies_are_equal():
    assert COPIES[0].read_bytes() == COPIES[1].read_bytes()
