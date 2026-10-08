"""Tests for the skill `plugin/skills/hook-activation-check` and `qa-codex --self-check` (issue #176).

`gh` and `codex` are stubbed (exit 0), so no network and no quota is used. All data is synthetic.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import build_plugin

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
SETUP = PLUGIN / "skills" / "setup" / "setup.py"


def _stubs(tmp_path):
    b = tmp_path / "stubs"
    b.mkdir()
    for name in ("gh", "codex"):
        (b / name).write_text("#!/bin/sh\nexit 0\n")
        (b / name).chmod(0o755)
    return b


def _env(tmp_path, stubs):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "HOME": str(home)}


def _project(tmp_path, env):
    proj = tmp_path / "project"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    r = subprocess.run([sys.executable, str(SETUP), "--root", str(proj), "--name", "example-app",
                        "--test-command", "make test", "--home", env["HOME"]],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    return proj


def _snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and ".git/" not in p.as_posix()}


def _check(plugin, proj, env):
    script = plugin / "skills" / "hook-activation-check" / "check.py"
    r = subprocess.run([sys.executable, str(script), "--root", str(proj), "--home", env["HOME"]],
                       capture_output=True, text=True, env=env, timeout=300)
    return r, r.stdout.splitlines()


def test_skill_is_built_and_named():
    skill = PLUGIN / "skills" / "hook-activation-check" / "SKILL.md"
    assert "name: hook-activation-check" in skill.read_text()
    assert build_plugin.differences() == []


def test_all_checks_ok_in_a_set_up_project_and_nothing_is_written(tmp_path):
    env = _env(tmp_path, _stubs(tmp_path))
    proj = _project(tmp_path, env)
    before = _snapshot(proj)
    r, lines = _check(PLUGIN, proj, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(lines) == 5
    assert [l.split()[0] for l in lines] == ["OK"] * 5
    assert [l.split(":")[0] for l in lines[:4]] == [f"OK check {i}" for i in range(1, 5)]
    assert _snapshot(proj) == before


def test_missing_module_fails_check_3_and_the_last_line(tmp_path):
    env = _env(tmp_path, _stubs(tmp_path))
    proj = _project(tmp_path, env)
    plugin = tmp_path / "plugin-copy"
    shutil.copytree(PLUGIN, plugin, ignore=shutil.ignore_patterns("__pycache__"))
    (plugin / "bin" / "codex_exec.py").unlink()
    r, lines = _check(plugin, proj, env)
    assert r.returncode == 1
    assert lines[2].startswith("FAILED check 3") and "codex_exec" in lines[2]
    assert [l.split()[0] for l in lines[:2]] == ["OK", "OK"]
    assert lines[-1].startswith("FAILED")


def test_disabled_plugin_fails_check_1_and_missing_codex_fails_check_4(tmp_path):
    env = _env(tmp_path, _stubs(tmp_path))
    proj = _project(tmp_path, env)
    local = proj / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"enabledPlugins": {"agk@kit": False}}))
    no_codex = {**env, "PATH": os.pathsep.join(
        p for p in env["PATH"].split(os.pathsep) if not (Path(p) / "codex").exists())}
    r, lines = _check(PLUGIN, proj, no_codex)
    assert lines[0].startswith("FAILED check 1")
    for event in ("PreToolUse", "SubagentStop", "PermissionDenied"):
        assert event in lines[0]
    assert lines[3].startswith("FAILED check 4") and "codex" in lines[3]
    assert lines[-1].startswith("FAILED") and r.returncode == 1


@pytest.mark.parametrize("where", ["home", "project", "local"])
def test_disable_all_hooks_fails_check_1(tmp_path, where):
    env = _env(tmp_path, _stubs(tmp_path))
    proj = _project(tmp_path, env)
    folder = Path(env["HOME"]) / ".claude" if where == "home" else proj / ".claude"
    folder.mkdir(parents=True, exist_ok=True)
    name = "settings.local.json" if where == "local" else "settings.json"
    target = folder / name
    cfg = json.loads(target.read_text()) if target.exists() else {}
    target.write_text(json.dumps({**cfg, "disableAllHooks": True}))
    r, lines = _check(PLUGIN, proj, env)
    assert lines[0].startswith("FAILED check 1") and "disableAllHooks" in lines[0]
    for event in ("PreToolUse", "SubagentStop", "PermissionDenied"):
        assert event in lines[0]
    assert lines[-1].startswith("FAILED") and r.returncode == 1


def test_self_check_mode_ends_without_gh_or_codex(tmp_path):
    # gh and codex that record a call: none may run
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    log = tmp_path / "calls.log"
    for name in ("gh", "codex"):
        (stubs / name).write_text(f"#!/bin/sh\necho {name} >> {log}\nexit 0\n")
        (stubs / name).chmod(0o755)
    env = {"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(PLUGIN / "bin" / "qa-codex-launcher"), "--self-check"],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "self-check ok" in r.stdout
    assert not log.exists()
