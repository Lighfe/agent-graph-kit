from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
SECTION = README.split("## Update a plugin project")[1].split("\n## ")[0]
SKILL = (ROOT / "plugin/skills/drift/SKILL.md").read_text()
SPEC = (ROOT / "docs/specs/agent-graph-kit.md").read_text()


def test_readme_section_names_commands():
    for k in ["--accept", "--update", "/agk:drift", "/agk:update"]:
        assert k in SECTION


def test_readme_section_in_order():
    keys = ["claude plugin update", "restart Claude Code", "/agk:update", "merge proposal", "drift.py --update", "--accept"]
    pos = [SECTION.index(k) for k in keys]
    assert pos == sorted(pos)


def test_readme_single_update_heading():
    heads = [l for l in README.splitlines() if l.startswith("## Update")]
    assert heads == ["## Update a plugin project"]
    assert "Update the plugin in" + " a project" not in README


def test_readme_old_steps_gone():
    for k in ["--root . --update", "diff <plugin cache>", "by hand"]:
        assert k not in SECTION


def test_readme_no_hand_edit_of_lock():
    assert "by hand from the lock" not in SECTION
    assert "edit the lock" not in SECTION.lower()


def test_skill_names_accept_and_cleanup():
    assert "--accept" in SKILL
    assert "delete such an entry" not in SKILL
    assert "removed from the lock" in SKILL


def test_spec_names_update_accept():
    line = [l for l in SPEC.splitlines() if "/agk:drift" in l][0]
    assert "--update" in line and "--accept" in line
