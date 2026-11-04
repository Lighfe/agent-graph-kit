"""Fact tests for issue #259: the research notes line and the reason of the memory cap.

They read the sources and the built copies in plugin/templates/. No subprocess runs.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "plugin" / "templates"

PROCESS_FILES = [ROOT / "docs" / "process.md", TEMPLATES / "docs" / "process.md"]
ENGINEER_FILES = [
    ROOT / "docs" / "team" / "software-engineer.md",
    TEMPLATES / "docs" / "team" / "software-engineer.md",
]

REASON = (
    "an uncapped run can fill the memory of the machine and stop or kill "
    "other sessions and processes on it"
)


def research_entry(text):
    lines = [l for l in text.splitlines() if "research notes folder" in l]
    assert len(lines) == 1, lines
    return lines[0]


@pytest.mark.parametrize("path", PROCESS_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_process_names_research_notes_line(path):
    entry = research_entry(path.read_text(encoding="utf-8"))
    assert "`AGENTS.md`" in entry
    assert "starts with `Research notes:`" in entry
    assert "`Research notes: <folder>`" in entry
    assert "no such line" in entry
    assert "does not apply" in entry
    assert "readable; you may build on earlier research and cite it" in entry
    assert "docs/research/" not in entry


@pytest.mark.parametrize("path", ENGINEER_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_memory_section_gives_reason(path):
    text = path.read_text(encoding="utf-8")
    section = text.split("## Memory-heavy jobs", 1)[1].split("\n## ", 1)[0]
    flat = re.sub(r"\s+", " ", section)
    assert REASON in flat
    assert "the owner's work included" in flat


def test_kit_agents_names_its_research_folder():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    hits = [l for l in text.splitlines() if l.startswith("Research notes: docs/research/")]
    assert len(hits) == 1
    assert (ROOT / "docs" / "research").is_dir()


def test_template_has_no_research_notes_line():
    assert "Research notes" not in (TEMPLATES / "AGENTS.md.tmpl").read_text(encoding="utf-8")


def test_setup_skill_describes_optional_line():
    text = (ROOT / "plugin" / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")
    para = [l for l in text.splitlines() if "Research notes:" in l]
    assert len(para) == 1
    p = para[0]
    assert "does not write" in p
    assert "by hand" in p
    assert "existing project" in p
