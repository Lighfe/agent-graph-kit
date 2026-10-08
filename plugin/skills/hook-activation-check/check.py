#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Check that the kit works in a project (issue #176). Read-only.

  uv run --script check.py --root <project root> [--home <home>]

Prints one line per check (`OK ...` or `FAILED ...`) and a last line with the result of the run.
Exit code 0 when all checks are OK, otherwise 1. It writes no file in the project and starts no
`gh` or `codex` process except the read-only login commands of Check 4.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
PLUGIN_NAME = "agk"
TIMEOUT = 60


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _events(config: dict) -> set[str]:
    hooks = config.get("hooks")
    return {k for k, v in hooks.items() if v} if isinstance(hooks, dict) else set()


def check_hooks(root: Path, home: Path) -> str:
    plugin_events = _events(_read_json(PLUGIN / "hooks" / "hooks.json"))
    if not plugin_events:
        return "FAILED check 1: the plugin hooks.json lists no events or cannot be read"
    required = sorted(plugin_events)
    configs = [_read_json(p) for p in (home / ".claude" / "settings.json", root / ".claude" / "settings.json",
                                       root / ".claude" / "settings.local.json")]
    if any(c.get("disableAllHooks") is True for c in configs):
        return "FAILED check 1: disableAllHooks is true in a settings file, so no hook runs: " + ", ".join(required)
    active: set[str] = set()
    for c in configs:
        active |= _events(c)
    disabled = any(isinstance(c.get("enabledPlugins"), dict) and any(
        k.split("@")[0] == PLUGIN_NAME and v is False for k, v in c["enabledPlugins"].items()) for c in configs)
    if not disabled:  # the plugin is loaded (this skill runs from it), so its hooks.json is active
        active |= plugin_events
    missing = [e for e in required if e not in active]
    if missing:
        return "FAILED check 1: hooks not registered: " + ", ".join(missing)
    return "OK check 1: hooks registered: " + ", ".join(required)


def check_guard() -> str:
    event = {"tool_name": "Bash", "tool_input": {"command": "gh issue close 1 && true"}}
    guard = PLUGIN / "hooks" / "guard.py"
    with tempfile.TemporaryDirectory() as empty:  # empty PATH and cwd: a GitHub call could not work anyway
        try:
            r = subprocess.run([sys.executable, str(guard)], input=json.dumps(event), capture_output=True, text=True,
                               cwd=empty, env={"PATH": empty, "HOME": empty, "PYTHONDONTWRITEBYTECODE": "1"},
                               timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"FAILED check 2: the guard did not run ({type(e).__name__})"
    try:
        spec = json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None
    except (ValueError, KeyError, TypeError):
        return "FAILED check 2: the guard printed output that is not a deny"
    if not spec or spec.get("permissionDecision") != "deny":
        return "FAILED check 2: the guard allowed 'gh issue close 1 && true' (no deny)"
    reason = str(spec.get("permissionDecisionReason", ""))
    if not reason.startswith("G1"):
        return f"FAILED check 2: the deny message does not start with G1: {reason[:80]}"
    return "OK check 2: the guard denies 'gh issue close 1 && true' (G1)"


def check_qa_codex(root: Path) -> str:
    wrapper = root / "scripts" / "qa-codex"
    if not wrapper.is_file():
        return "FAILED check 3: scripts/qa-codex is missing (run /agk:setup)"
    env = dict(os.environ, PATH=f"{PLUGIN / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
               PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([str(wrapper), "--self-check"], cwd=root, env=env, capture_output=True, text=True,
                           timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"FAILED check 3: scripts/qa-codex --self-check did not run ({type(e).__name__})"
    if r.returncode == 0:
        return "OK check 3: scripts/qa-codex loads all its modules"
    m = re.search(r"No module named '([^']+)'", r.stderr)
    why = f"module missing: {m.group(1)}" if m else (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1][:120]
    return f"FAILED check 3: scripts/qa-codex --self-check failed ({why})"


def check_tools() -> str:
    problems = [f"{t} not found on the path" for t in ("gh", "uv", "codex") if not shutil.which(t)]
    for tool, cmd in (("gh", ["gh", "auth", "status"]), ("codex", ["codex", "login", "status"])):
        if not shutil.which(tool):
            continue
        try:
            ok = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if not ok:
            problems.append(f"{tool} is not logged in")
    if problems:
        return "FAILED check 4: " + "; ".join(problems)
    return "OK check 4: gh, uv and codex found; gh and codex logged in"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--home", default=str(Path.home()))
    args = ap.parse_args(argv)
    root, home = Path(args.root).resolve(), Path(args.home)
    lines = [check_hooks(root, home), check_guard(), check_qa_codex(root), check_tools()]
    ok = all(line.startswith("OK") for line in lines)
    lines.append("OK all 4 checks passed" if ok else "FAILED at least one check failed")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
