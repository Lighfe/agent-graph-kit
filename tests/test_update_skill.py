"""Tests for the update skill `plugin/skills/update/SKILL.md` (issue #252). The content is checked, nothing is run."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "update" / "SKILL.md"


def text():
    return SKILL.read_text()


def test_skill_exists_with_name_update():
    assert SKILL.is_file()
    m = re.match(r"---\nname: (\S+)\ndescription: (.+)\n---\n", text())
    assert m and m.group(1) == "update"
    assert "/agk:update" in m.group(2)


def test_skill_uses_skill_dir():
    assert "${CLAUDE_SKILL_DIR}" in text()


def test_skill_has_no_cache_path_or_version():
    t = text()
    assert ".claude/plugins" not in t and "/cache/" not in t and "~/.claude" not in t
    assert not re.search(r"\b\d+\.\d+\.\d+\b", t)


def test_skill_covers_the_steps():
    t = text()
    assert "--update" in t and "not set up:" in t and "/agk:setup" in t
    assert "changed in both" in t and "removed from the lock" in t
