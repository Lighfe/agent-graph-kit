"""Tests for .claude/settings.json (hook registration and permission rules).

The tests only read the file. No network, no `uv` subprocess.
"""

import json
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".claude" / "settings.json"

# Path syntax: https://code.claude.com/docs/en/permissions ("Read and Edit").
# A leading "/" anchors the pattern at the project root for project settings.
DENY_PATTERN = "/.claude/settings*.json"
DENY_RULES = {f"Edit({DENY_PATTERN})", f"Write({DENY_PATTERN})"}
ALLOW_RULES = {"Bash(scripts/qa-codex ROLE=qa ISSUE=*)", "Bash(gh issue close *)"}


def load():
    return json.loads(SETTINGS.read_text())


def guard_hook():
    entry = load()["hooks"]["PreToolUse"][0]
    assert len(entry["hooks"]) == 1
    return entry, entry["hooks"][0]


def test_matcher_covers_agent_bash_and_sendmessage():
    entry, _ = guard_hook()
    assert set(entry["matcher"].split("|")) >= {"Agent", "Bash", "SendMessage"}


def test_guard_command_runs_guard_with_sh_failure_wrapper():
    _, hook = guard_hook()
    assert hook["type"] == "command"
    assert hook["timeout"] == 120
    cmd = hook["command"]
    assert cmd.startswith('uv run --script "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"')
    assert "guard.py" in cmd and "exit 2" in cmd
    assert cmd.rstrip().endswith("exit 2; }")
    assert "|| {" in cmd and ">&2" in cmd


def test_allow_rules_are_exactly_the_two_guarded_forms():
    assert set(load()["permissions"]["allow"]) == ALLOW_RULES
    assert len(load()["permissions"]["allow"]) == 2


def test_deny_rules_protect_both_settings_files():
    deny = load()["permissions"]["deny"]
    assert DENY_RULES <= set(deny)
    anchored = DENY_PATTERN.lstrip("/")
    for name in (".claude/settings.json", ".claude/settings.local.json"):
        assert fnmatchcase(name, anchored), name
    assert not fnmatchcase(".claude/hooks/guard.py", anchored)


def test_permission_denied_hook_runs_not_started():
    entries = load()["hooks"]["PermissionDenied"]
    assert len(entries) == 1
    entry = entries[0]
    assert set(entry["matcher"].split("|")) == {"Agent", "Bash", "SendMessage"}
    assert len(entry["hooks"]) == 1
    hook = entry["hooks"][0]
    assert hook["type"] == "command"
    assert hook["timeout"] == 120
    assert "uv run --script" in hook["command"]
    assert ".claude/hooks/not_started.py" in hook["command"]


def test_pre_tool_use_entry_is_unchanged():
    assert load()["hooks"]["PreToolUse"] == [{
        "matcher": "Agent|Bash|SendMessage",
        "hooks": [{
            "type": "command",
            "command": "uv run --script \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py\" "
                       "|| { echo 'guard hook failed: call denied' >&2; exit 2; }",
            "timeout": 120,
        }],
    }]


def test_readme_merge_note_names_every_hook_event():
    """The README tells a project with its own settings file what to merge.

    It must name every event of the kit's hooks block, so no hook is lost.
    """
    readme = (ROOT / "README.md").read_text()
    notes = [line for line in readme.splitlines() if "do not overwrite it" in line]
    assert len(notes) == 1
    for event in load()["hooks"]:
        assert f"`{event}`" in notes[0], event


def test_subagent_stop_hook_runs_outage_stop_and_never_blocks():
    entries = load()["hooks"]["SubagentStop"]
    assert len(entries) == 1
    entry = entries[0]
    assert "matcher" not in entry  # runs for every subagent
    assert len(entry["hooks"]) == 1
    hook = entry["hooks"][0]
    assert hook["type"] == "command"
    assert hook["timeout"] == 120
    cmd = hook["command"]
    assert "uv run --script" in cmd
    assert ".claude/hooks/outage_stop.py" in cmd
    assert cmd.rstrip().endswith("|| true")  # exit code 2 would keep the subagent running


def test_permission_denied_entry_is_unchanged():
    assert load()["hooks"]["PermissionDenied"] == [{
        "matcher": "Agent|Bash|SendMessage",
        "hooks": [{
            "type": "command",
            "command": "uv run --script \"$CLAUDE_PROJECT_DIR/.claude/hooks/not_started.py\"",
            "timeout": 120,
        }],
    }]
