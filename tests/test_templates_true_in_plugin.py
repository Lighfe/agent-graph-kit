"""Issue #199: the files a plugin project receives name nothing that only the kit repo has."""
import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / "plugin" / "templates"
KIT_ONLY = [
    "docs/specs/agent-graph-kit.md",
    "docs/research/",
    ".claude/agents/planner.md",
    "Auto mode allow entries",
    "entry 3",
    "QA_SANDBOX",
    ".claude/hooks",
]


def scan(root: Path) -> list[str]:
    found = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            text = p.read_text(errors="replace")
            found += [f"{p.relative_to(root).as_posix()}: kit-only string {s!r}" for s in KIT_ONLY if s in text]
    return found


def test_templates_have_files():
    assert any(TEMPLATES.rglob("*.md"))


def test_templates_name_no_kit_only_thing():
    assert not scan(TEMPLATES), "\n".join(scan(TEMPLATES))


def test_scan_reports_file_and_string(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("see QA_SANDBOX here")
    assert scan(tmp_path) == ["docs/x.md: kit-only string 'QA_SANDBOX'"]


# Issue #251: a plugin project gets only one script from /agk:setup.
SCRIPT_PATH = re.compile(r"scripts/[A-Za-z0-9_.-]+")
COPIED_SCRIPTS = {"scripts/" + "qa-codex"}


def script_paths(root: Path) -> list[str]:
    found = []
    for p in sorted((root / "docs" / "team").glob("*.md")):
        for m in SCRIPT_PATH.findall(p.read_text(errors="replace")):
            if m not in COPIED_SCRIPTS:
                found.append(f"{p.name}: names {m}")
    return found


def test_role_files_name_no_script_a_project_lacks():
    assert not script_paths(TEMPLATES), "\n".join(script_paths(TEMPLATES))


def test_script_scan_examples(tmp_path):
    (tmp_path / "docs" / "team").mkdir(parents=True)
    f = tmp_path / "docs" / "team" / "x.md"
    f.write_text("run scripts/qa-codex ROLE=qa ISSUE=12 and look in the scripts/ folder")
    assert script_paths(tmp_path) == []
    for bad in ["scripts/build_plugin.py --release-status", "uv run scripts/bump_plugin_version.py", "scripts/plugin-release.json"]:
        f.write_text(bad)
        assert script_paths(tmp_path), bad
