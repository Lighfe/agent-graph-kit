"""Tests for the plugin folder `plugin/` (issue #159).

The plugin copies come from the v1 files through scripts/build_plugin.py. All data is synthetic.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import build_plugin

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
FAKES = ROOT / "tests" / "fakes"
AGENTS = ["pm", "software-engineer", "frontend-engineer", "qa-engineer", "planner"]


def test_layout():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] and manifest["version"] and manifest["author"]
    for a in AGENTS:
        assert (PLUGIN / "agents" / f"{a}.md").is_file()
    for s in ("stage-start", "codex-review"):
        assert (PLUGIN / "skills" / s / "SKILL.md").is_file()


def test_hooks_json_runs_the_three_scripts_from_the_plugin_root():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {"PreToolUse", "SubagentStop", "PermissionDenied"}
    script = {"PreToolUse": "guard.py", "SubagentStop": "outage_stop.py", "PermissionDenied": "not_started.py"}
    for event, name in script.items():
        cmds = [h["command"] for block in hooks[event] for h in block["hooks"]]
        assert len(cmds) == 1
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/hooks/{name}"' in cmds[0]
        assert "CLAUDE_PROJECT_DIR" not in cmds[0]
        assert (PLUGIN / "hooks" / name).is_file()


def test_plugin_copies_match_the_v1_sources():
    """One source: the plugin copies are generated. Run scripts/build_plugin.py when this fails."""
    assert build_plugin.differences() == []


def test_the_check_notices_a_changed_copy(monkeypatch, tmp_path):
    copy = tmp_path / "plugin"
    shutil.copytree(PLUGIN, copy)
    monkeypatch.setattr(build_plugin, "PLUGIN", copy)
    (copy / "agents" / "pm.md").write_text("changed\n")
    (copy / "skills" / "codex-review" / "extra.txt").write_text("x\n")
    (copy / "agents" / "stray.md").write_text("x\n")
    got = build_plugin.differences()
    assert any(l.startswith("differs:") and l.endswith("agents/pm.md") for l in got)
    assert any(l.startswith("extra:") and l.endswith("skills/codex-review/extra.txt") for l in got)
    assert any(l.startswith("extra:") and l.endswith("agents/stray.md") for l in got)


def test_agents_use_no_front_matter_key_that_plugins_ignore():
    for p in (PLUGIN / "agents").glob("*.md"):
        front = p.read_text().split("---")[1]
        keys = set(re.findall(r"^([A-Za-z]+):", front, re.M))
        assert not keys & {"permissionMode", "hooks", "mcpServers"}, p.name


def test_plugin_guard_accepts_the_namespaced_agent_name(tmp_path):
    """The plugin's guard judges `<plugin name>:pm` like `pm` (a launch without a launch line is denied)."""
    name = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["name"]
    reasons = []
    for t in ("pm", f"{name}:pm"):
        event = {"tool_name": "Agent", "tool_input": {"subagent_type": t, "prompt": "no line"}}
        env = {**os.environ, "PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}"}
        p = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "guard.py")], input=json.dumps(event),
                           text=True, capture_output=True, env=env, cwd=tmp_path, timeout=60)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        reasons.append(out["permissionDecisionReason"])
    assert "has no launch line" in reasons[0]
    assert reasons[1] == reasons[0]


@pytest.mark.skipif(shutil.which("claude") is None, reason="the claude command is not available: plugin validate did not run")
def test_claude_plugin_validate_strict_passes():
    # No telemetry: the run needs no network beyond localhost (the QA sandbox blocks telemetry hosts).
    env = {**os.environ, "DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    p = subprocess.run(["claude", "plugin", "validate", str(PLUGIN), "--strict"], capture_output=True,
                       text=True, timeout=120, env=env)
    assert p.returncode == 0, p.stdout + p.stderr
