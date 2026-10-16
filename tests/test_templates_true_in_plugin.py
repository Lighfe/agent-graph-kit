"""Issue #199: the files a plugin project receives name nothing that only the kit repo has."""
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
