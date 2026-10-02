"""Fact tests for the planner relabel allow entry (issue #123).

They read README.md and docs/team/planner.md and check the facts the issue
asks for. No test runs gh, git or another subprocess.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
PLANNER = (ROOT / "docs" / "team" / "planner.md").read_text(encoding="utf-8")

RELABEL = "gh issue edit <n> --remove-label later --add-label ready"
OUTAGES = (
    "Classifier unavailable",
    "Auto mode could not evaluate this action and is blocking it for safety",
    "Auto mode unavailable",
)


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


ALLOW = section(README, "### Auto mode allow entries")


def entry3_text():
    m = re.search(
        r"^Entry 3 \(planner relabel\): copy this text as is:\n\n```text\n(.*?)\n```$",
        ALLOW,
        re.S | re.M,
    )
    assert m, "entry 3 with a fenced text block"
    return m.group(1)


def test_readme_says_three_entries_and_never_two():
    assert "Three agent calls need an allow entry" in ALLOW
    assert "Two agent calls" not in ALLOW
    assert not re.search(r"\b[Tt]wo (agent calls|entries)\b", ALLOW)
    headings = re.findall(r"^Entry (\d) \(", ALLOW, re.M)
    assert headings == ["1", "2", "3"]


def test_entry3_allows_only_the_relabel_after_confirmation():
    text = entry3_text()
    assert "\n" not in text  # one line, copyable as is
    assert RELABEL in text
    assert "/stage-start" in text
    assert "planner" in text
    assert "stage" in text and "sub-issue" in text
    assert "confirmed" in text
    assert "docs/team/planner.md" in text
    assert "owner's instruction" in text
    # exactly one command, nothing else allowed
    assert text.count("gh issue edit <n>") == 1
    assert len(re.findall(r"--[a-z-]+", text)) == 2  # only --remove-label and --add-label
    for banned in ("--add-sub-issue", "--add-blocked-by", "--body-file", "--title", "--remove-label ready"):
        assert banned not in text
    assert "only this command" in text
    for word in ("no other label", "no other gh issue edit flag", "gh issue close", "no sub-issue or blocker link"):
        assert word in text, word


def test_readme_names_limit_and_what_happens_without_entry3():
    after = ALLOW.split(entry3_text(), 1)[1]
    assert "Without entry 3" in after
    assert "relabel by hand" in after
    assert "The limit: entry 3 holds for every repo of the user" in after
    assert "cannot check that the owner confirmed the stage" in after
    assert '"Intake"' in after and '"Stage set-up"' in after


def test_planner_has_one_denied_relabel_rule_referenced_from_both_jobs():
    rule = section(PLANNER, "### Denied relabel")
    intake = section(PLANNER, "## Intake")
    setup = section(PLANNER, "## Stage set-up")
    assert '"Denied relabel"' in intake.split("### Denied relabel")[0]
    assert '"Denied relabel"' in setup
    assert '"Denied action"' in rule and "docs/process.md" in rule
    assert "no issue comment" in rule
    assert "in the session" in rule


def test_denied_relabel_rule_covers_verdict_partial_check_and_outage():
    rule = section(PLANNER, "### Denied relabel")
    # deny with a verdict
    assert "quote the deny message" in rule
    assert "secrets redacted" in rule
    assert "still has `later`" in rule
    assert RELABEL in rule
    assert '"Auto mode allow entries"' in rule and "entry 3" in rule
    assert "Do not retry in a loop" in rule
    assert "another command form" in rule
    # partial deny
    assert "only the sub-issues that still have `later`" in rule
    # check after the owner says the labels are set
    assert "gh issue view <n> --json labels" in rule
    assert "lacks `ready`" in rule
    assert "once" in rule
    assert '"Then"' in rule
    assert 'last line of "Stage set-up"' in rule
    # outage deny
    for reason in OUTAGES:
        assert f"`{reason}`" in rule
    assert "outage" in rule
    assert "do not point to the allow entry" in rule
    assert "only when the owner asks" in rule


def test_relabel_still_only_after_confirmation():
    intake = section(PLANNER, "## Intake")
    setup = section(PLANNER, "## Stage set-up")
    assert "The sub-issues carry `later` until the owner confirms the stage." in intake
    assert "When the owner confirms in the session: on each sub-issue, remove `later` and add `ready`" in intake
    assert "Without confirmation: the sub-issues stay `later`." in intake
    assert "7. Only after the owner has chosen and, when step 5 named permissions, has confirmed the stage with them" in setup
