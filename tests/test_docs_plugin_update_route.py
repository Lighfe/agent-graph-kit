from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
SECTION = README.split("## Update a plugin project")[1].split("\n## ")[0]
SKILL = (ROOT / "plugin/skills/drift/SKILL.md").read_text()
SPEC = (ROOT / "docs/specs/agent-graph-kit.md").read_text()


def test_readme_section_names_commands():
    for k in ["--accept", "--update", "/agk:drift"]:
        assert k in SECTION


def test_readme_steps_in_order():
    keys = ["templates/", "2. Run `/agk:drift`", "--root . --update", "nothing updated", "Merge each `changed in both`",
            "--accept", "no `changed in both` and no `dropped`", "`.agent-graph-kit.lock` together"]
    pos = []
    for k in keys:
        pos.append(SECTION.index(k))
    assert pos == sorted(pos)


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
