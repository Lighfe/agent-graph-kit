"""Fact tests for the README rework (issue #330): section order, the owner's text, monitoring, release."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

SECTIONS = [
    "Purpose",
    "What the kit does",
    "Set-up the Agent Graph Kit",
    "Update the kit",
    "Monitoring",
    "Development note",
    "Development and release",
    "Docs",
]


def outside_fences(text):
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return out


def section(name):
    return README.split(f"\n## {name}\n")[1].split("\n## ")[0]


def test_sections_are_exactly_these_in_this_order():
    heads = [l[3:] for l in outside_fences(README) if l.startswith("## ")]
    assert heads == SECTIONS


def test_title_then_picture_then_purpose():
    lines = [l for l in README.splitlines() if l.strip()]
    assert lines[0] == "# agent-graph-kit"
    assert lines[1].startswith("![") and lines[1].endswith("](docs/assets/agk-overview.png)")
    assert lines[2] == "## Purpose"


def test_no_version_words_and_no_removed_parts():
    assert not re.search(r"\bv[12]\b", README, re.I)
    for gone in ["Project set-up reference", "Start a new project", "Update a plugin project",
                 "monitor.sqlite", "SQLite", "work in progress", "Zoomcamp"]:
        assert gone not in README, gone


def test_purpose_has_the_three_spelling_fixes():
    purpose = section("Purpose")
    for good in ['"rogue"', "opposite", "lose focus"]:
        assert good in purpose, good
    for bad in ["rouge", "oppsosite", "loose"]:
        assert bad not in README, bad
    assert purpose.lstrip().startswith("When pursuing")
    assert purpose.rstrip().endswith("for brainstorming and writing the spec/plan.")
    for k in ["Alexey Grigorev (DataTalks.Club)", "Jesse Vincent's superpowers plugin",
              "How do I want to work with AI agents following a spec-driven development approach?",
              "An AI safety harness"]:
        assert k in purpose, k


def test_development_note_names_the_plugin_version():
    note = section("Development note")
    version = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())["version"]
    assert "dogfooding" in note and "https://github.com/Lighfe/quack-rl" in note
    assert "docs/archive" in note
    named = re.findall(r"version (\d+\.\d+\.\d+)", note)
    assert len(named) == 1
    # The note names the version at the time of writing; the plugin version only goes up.
    assert tuple(map(int, named[0].split("."))) <= tuple(map(int, version.split(".")))
    assert named[0] == "0.2.0"


def test_what_the_kit_does():
    what = section("What the kit does")
    assert what.index("/stage-start") < what.index("/goal") < what.index("What you see at the end")
    for k in ["planner", "spec", "plan", "issues", "orchestrator", "PM", "engineer", "QA",
              "Hooks check every handoff", "stage review", "closed issues", "released plugin version", "boards"]:
        assert k in what, k
    assert len(what) < 2500  # short


def test_monitoring_section():
    mon = section("Monitoring")
    for k in ['"Now"', '"Stages"', "board.py up", "board.py down", "http://127.0.0.1:3000", "`admin`",
              "grafana-admin", "`Runaway issue`", "`Stuck launch`", "`AGK_ALERT_ISSUE_TOKENS`",
              "`AGK_ALERT_STUCK_MINUTES`", "OTel Collector, Prometheus, Loki and Grafana", "Docker",
              "one command", "inside Claude Code", "](plugin/skills/monitor/SKILL.md)",
              "](docs/assets/monitoring-board.png)"]:
        assert k in mon, k
    skill = (ROOT / "plugin/skills/monitor/SKILL.md").read_text()
    # The defaults the README names are the defaults of the skill.
    assert "| `AGK_ALERT_ISSUE_TOKENS` | `23000000` |" in skill and "23 000 000" in mon
    assert "| `AGK_ALERT_STUCK_MINUTES` | `45` |" in skill and "default 45" in mon


def test_monitoring_image_is_a_png():
    data = (ROOT / "docs/assets/monitoring-board.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 10_000


def test_development_and_release_section():
    dev = section("Development and release")
    for k in ["uv run --with pytest pytest", "-m integration", '-m "not integration"', "integration tests cover",
              "every push and every pull request", "bump_plugin_version.py", "`dev`", "`stable`", "release-dev",
              "release-stable", "Rollback", "older tag", "](docs/checks/release-channels.md)"]:
        assert k in dev, k
    order = ["Version bump at the end of a stage", "runs the tests", "sets the tag", "moves the branch `dev`",
             "by hand", "moves the branch `stable`", "Rollback"]
    pos = [dev.index(k) for k in order]
    assert pos == sorted(pos)
    for wf in ["ci.yml", "release-dev.yml", "release-stable.yml"]:
        assert (ROOT / ".github/workflows" / wf).is_file()


def test_docs_section_links():
    docs = section("Docs")
    for target in ["docs/specs/agent-graph-kit.md", "docs/specs/", "docs/process.md", "docs/team/",
                   "docs/archive/", "docs/checks/hook-activation.md"]:
        assert f"]({target})" in docs, target
        assert (ROOT / target).exists(), target
    assert "How the hooks work" in docs


def test_local_anchor_links_point_to_headings():
    lines = outside_fences(README)
    slugs = {re.sub(r"[^\w\- ]", "", m.group(1).lower()).replace(" ", "-")
             for m in (re.match(r"^#+\s+(.*)$", l) for l in lines) if m}
    anchors = re.findall(r"\]\(#([^)\s]+)\)", "\n".join(lines))
    assert anchors
    assert [a for a in anchors if a not in slugs] == []


def test_no_file_outside_the_readme_names_a_removed_section():
    gone = re.compile(r"Start a new project|Project set-up reference|Update a plugin project|"
                      r"Monitoring board \(optional\)|README section on the run record")
    files = [ROOT / "AGENTS.md", ROOT / "docs/process.md", ROOT / "docs/specs/agent-graph-kit.md"]
    for folder in ["docs/team", "docs/checks", "plugin"]:
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    hits = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if gone.search(text):
            hits.append(str(p.relative_to(ROOT)))
    assert hits == []
