"""Fact tests for the PM rule on criteria for a text-matching check (issue #144).

They read docs/team/pm.md and check the facts the issue asks for. No test runs gh, git or
another subprocess.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM = (ROOT / "docs" / "team" / "pm.md").read_text(encoding="utf-8")
SPEC = (ROOT / "docs" / "specs" / "agent-graph-kit.md").read_text(encoding="utf-8")

HEADING = "## Criteria for a text-matching check"


def flat(text):
    return re.sub(r"\s+", " ", text)


def section():
    start = PM.find(HEADING + "\n")
    assert start >= 0, "section not found"
    end = PM.find("\n## ", start + len(HEADING))
    return PM[start : end if end >= 0 else len(PM)]


def test_rule_asks_for_example_lists_not_a_rule_over_every_form():
    text = flat(section())
    assert "a list of concrete pass examples and a list of concrete deny examples" in text
    assert "not as a rule over every form" in text
    assert "every read-only form of a command" in text


def test_rule_asks_for_an_accepted_false_deny_clause():
    text = flat(section())
    assert "a clause that names which false denies are accepted" in text
    assert "without a QA FAIL" in text


def test_rule_never_accepts_a_false_pass_of_a_safety_relevant_input():
    text = flat(section())
    assert "A false pass of a safety-relevant input is never accepted" in text
    assert "has at least one deny example" in text


def example():
    m = re.search(r"Example criterion:\n\n((?:>.*\n)+)", section())
    assert m, "example criterion not found"
    return m.group(1)


def test_example_has_two_pass_two_deny_and_a_clause():
    text = example()
    assert len(re.findall(r"^>\s+- pass: ", text, re.M)) >= 2
    assert len(re.findall(r"^>\s+- deny: ", text, re.M)) >= 2
    assert "Accepted false denies:" in text


def test_example_is_synthetic():
    text = example()
    # made-up tool and path, not the G8 settings examples of #86 or the spec
    assert "tallyctl" in text and "ledger/" in text
    for word in ("settings", ".claude", "jq", "TYPESAFE_API_KEY"):
        assert word not in text


def test_plan_check_paragraph_names_the_rule():
    m = re.search(r"^If the issue comes from a plan .*$", PM, re.M)
    assert m
    text = m.group(0)
    assert "every form of a class fails the check" in text
    assert "rewrite it in the example-list form" in text


def test_spec_unchanged_on_pm_grooming():
    assert "text-matching" not in SPEC
