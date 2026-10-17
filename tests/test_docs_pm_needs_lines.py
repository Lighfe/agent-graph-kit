"""Fact tests for the PM rule on "needs #n" lines (issue #208). Read-only, no subprocess."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "pm.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "pm.md",
]


def flat(text):
    return re.sub(r"\s+", " ", text)


def test_rule_names_needs_lines_and_the_command():
    for p in COPIES:
        t = flat(p.read_text(encoding="utf-8"))
        assert "Before posting `## PM: GROOMED`, compare every \"needs #n\" line" in t, p
        assert "needs #" in t
        assert "`gh issue edit <n> --add-blocked-by <m>`" in t, p


def test_rule_covers_existing_links_and_other_repos():
    for p in COPIES:
        t = flat(p.read_text(encoding="utf-8"))
        assert "is already a native blocker needs no new link" in t, p
        assert "A blocker may be an issue in another repo (give the issue URL)" in t, p


def test_both_copies_are_equal():
    assert COPIES[0].read_bytes() == COPIES[1].read_bytes()
