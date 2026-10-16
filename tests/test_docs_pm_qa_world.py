"""Fact tests for the PM rules on self-standing issues and criteria QA can check (issue #191).

They read the repo copies and the plugin copies of the PM and QA role files.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM_PATHS = [ROOT / "docs/team/pm.md", ROOT / "plugin/templates/docs/team/pm.md"]
QA_PATHS = [ROOT / "docs/team/qa-engineer.md", ROOT / "plugin/templates/docs/team/qa-engineer.md"]


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_pm_rules_are_in_both_copies():
    needles = [
        "The body states every fact the engineer needs in words. A link may point to background only.",
        'Do not use "see comment ..."',
        "a stage code or a line number as the only source of a reason",
        "checked by QA from the checkout, the newest `## Engineer: DONE` comment and the state files",
        "a) A fact outside QA's world",
        "the engineer states the fact inline in `## Engineer: DONE`",
        "b) A folder that git ignores",
        "write a command that creates the data",
        "c) An optional dependency group",
        "names the group with the install command, or is changed to need no group",
        "d) A browser check",
        "write a check that needs no browser, or the criterion says QA does not repeat it",
        "Do not write a criterion about telling the owner something",
        "states its reason in words, has at least one criterion that a result can show",
        '`gh issue edit <n> --add-blocked-by <m>`) for every "needs #m" line',
        "at most about 10 criteria",
        "not longer than about 5 KB",
        "state in the issue why it stays one issue",
    ]
    for path in PM_PATHS:
        text = flat(path)
        for needle in needles:
            assert needle in text, (path, needle)


def test_pm_copies_are_identical():
    assert PM_PATHS[0].read_text() == PM_PATHS[1].read_text()


def test_qa_browser_line_is_conditional_in_both_copies():
    for path in QA_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "If your tool list has a browser tool, start the app" in text, path
        assert "Without a browser tool, do not repeat a browser check." in text, path
        assert "\nStart the app and run the browser check in one command" not in text, path
