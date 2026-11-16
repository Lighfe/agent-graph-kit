"""Fact tests for the PM rules on recorded evidence and a self-standing DONE comment (issue #341)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM_PATHS = [ROOT / "docs/team/pm.md", ROOT / "plugin/templates/docs/team/pm.md"]


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_pm_names_recorded_evidence_in_both_copies():
    needles = [
        "needs Docker, a running monitoring stack or another live system that the QA sandbox does not have",
        "the engineer records the evidence in a committed file `docs/evidence/<issue>-<name>.md`",
        "the commands, their outputs and the commit they ran on",
        "QA checks that file and the code",
    ]
    for path in PM_PATHS:
        text = flat(path)
        for needle in needles:
            assert needle in text, (path, needle)


def test_pm_says_newest_done_is_complete_on_its_own_in_both_copies():
    needle = (
        "the newest `## Engineer: DONE` is complete on its own: it does not point to older comments "
        "for facts that QA needs"
    )
    for path in PM_PATHS:
        assert needle in flat(path), path
