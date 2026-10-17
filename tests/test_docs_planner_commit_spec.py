"""Fact tests for the spec-and-plan commit in the planner file (issue #211).

Both copies of the planner file must carry the commit step and its rules.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "planner.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "planner.md",
]


def intake(path):
    text = path.read_text(encoding="utf-8")
    return text.split("## Intake\n", 1)[1].split("## Stage set-up", 1)[0]


def test_intake_has_commit_step_between_plan_and_stage_issue():
    for path in COPIES:
        text = intake(path)
        step3 = text.index("3. Write the plan")
        step4 = text.index("4. Commit the spec and the plan")
        step5 = text.index("5. Write one stage issue")
        assert step3 < step4 < step5, path
        assert "`git add <spec path> <plan path>`" in text, path
        assert "`Spec and plan for <name>`" in text, path
        assert "Add no other file. Do not push" in text, path


def test_commit_stays_without_confirmation():
    for path in COPIES:
        assert "The commit of step 4 stays" in intake(path), path


def test_ready_line_needs_clean_tree():
    for path in COPIES:
        text = path.read_text(encoding="utf-8")
        assert "only after `git status --porcelain` is empty" in text, path
        assert "name the files and ask the owner" in text, path
        assert "Do not end with the ready line" in text, path
        assert "only after `git status --porcelain` is empty" in intake(path), path


def test_only_two_planner_commits():
    for path in COPIES:
        text = path.read_text(encoding="utf-8")
        assert "are the only commits you make" in text, path
        assert "without asking the owner" in text, path
