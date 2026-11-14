"""Docs of the monitoring check on real data (issue #315): the living spec and the monitor SKILL.md."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _section(text: str, heading: str) -> str:
    start = text.index(heading + "\n")
    rest = text[start + len(heading) + 1:]
    m = re.search(r"^## ", rest, re.M)
    return rest[: m.start()] if m else rest


def test_living_spec_monitoring_section_describes_the_new_stack():
    spec = (ROOT / "docs/specs/agent-graph-kit.md").read_text()
    sec = _section(spec, "## Monitoring stack (optional)")
    for word in ("Collector", "Prometheus", "Loki", "Grafana", "`facts.py`", "otelHeadersHelper",
                 "~/.claude/settings.json", "Forward only", "back-filled", "live board", "history board"):
        assert word in sec, word
    assert "still to come" not in sec
    assert "names no project" in sec
    # The SQLite store is named only as removed.
    for line in sec.splitlines():
        if "SQLite" in line:
            assert "removed" in line


def test_skill_names_the_limits_found_on_real_data():
    skill = (ROOT / "plugin/skills/monitor/SKILL.md").read_text()
    sec = _section(skill, "## Checked on real data")
    for word in ("claude_code.active_time.total", "claude_code.tool_result", "agent_name",
                 "agk:tokens:1m", "export interval", "418 MiB"):
        assert word in sec, word
    assert "418 MiB" in _section(skill, "## Monitoring stack (optional)")
