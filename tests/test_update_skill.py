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


# Issue #253: merge proposals and finish


def test_merge_reads_three_things_and_no_base():
    t = text()
    assert "the project file, the plugin template" in t and "the diff between them" in t
    assert "${CLAUDE_SKILL_DIR}/../../templates/<path>" in t and "CLAUDE.md.tmpl" in t
    assert "only a sha256" in t and "no common base" in t


def test_merge_three_change_kinds_and_recommendation():
    t = text()
    assert "a kit change to carry into the project file" in t
    assert "a project change made on purpose to keep" in t
    assert "names a file or command the project does not have" in t and "scripts/build_plugin.py" in t
    assert "one sentence of reason" in t
    for k in ["take the template", "keep the project file", "merge"]:
        assert k in t


def test_owner_answer_before_write_and_no_keeps_file():
    t = text()
    assert "yes, no, or a change" in t
    assert "Write a file only after a yes" in t
    assert "shows `changed in both` again at the next update" in t


def test_finish_steps():
    t = text()
    assert "--accept <path>" in t and "hook-activation-check" in t and "FAILED" in t
    assert "`.agent-graph-kit.lock` together" in t


def test_no_push_and_no_agents_md_or_settings():
    t = text()
    assert "Never push" in t and "never pushes" in t
    assert "`AGENTS.md`" in t and "never touches them" in t
    assert "git push" not in t


def test_drift_skill_and_spec_agree():
    drift = (ROOT / "plugin" / "skills" / "drift" / "SKILL.md").read_text()
    spec = (ROOT / "docs" / "specs" / "agent-graph-kit.md").read_text()
    assert "low-level commands" in drift and "/agk:update" in drift
    assert "low-level commands" in spec
    assert "the merge step is not built yet" not in spec
