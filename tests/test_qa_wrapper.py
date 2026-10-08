"""Tests for the thin wrapper of the Codex QA launcher (issue #165).

A project set up the plugin way holds only `scripts/qa-codex` (two lines). The real launcher
`qa-codex-launcher` and its helpers live in the plugin `bin/`, the hooks in the plugin `hooks/`.
All data is synthetic. No real `gh`, `codex` or network is used.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import build_plugin
import guard

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
WRAPPER = PLUGIN / "templates" / "scripts" / "qa-codex"


def _project(tmp_path, plugin_dir):
    """A temporary project with the wrapper only: no .claude/hooks/, no launcher copy."""
    proj = tmp_path / "project"
    (proj / "scripts").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    shutil.copy2(WRAPPER, proj / "scripts" / "qa-codex")
    assert not (proj / ".claude").exists()
    env = {"PATH": f"{plugin_dir / 'bin'}:{os.environ['PATH']}", "HOME": str(tmp_path / "home")}
    (tmp_path / "home").mkdir()
    return proj, env


def _plugin_copy(tmp_path):
    dst = tmp_path / "plugin-cache" / "agk"
    shutil.copytree(PLUGIN, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def test_wrapper_loads_all_modules_with_the_hooks_only_in_the_plugin(tmp_path):
    proj, env = _project(tmp_path, _plugin_copy(tmp_path))
    r = subprocess.run(["scripts/qa-codex"], cwd=proj, env=env, capture_output=True, text=True, timeout=120)
    assert "ModuleNotFoundError" not in r.stderr, r.stderr
    assert "usage: qa-codex ROLE=qa ISSUE=<n>" in r.stderr + r.stdout
    assert r.returncode != 0


def test_launcher_in_plugin_bin_finds_the_project_root_not_the_plugin(tmp_path):
    plugin = _plugin_copy(tmp_path)
    proj, env = _project(tmp_path, plugin)
    code = (
        "import importlib.util, sys\n"
        "from importlib.machinery import SourceFileLoader\n"
        "l = SourceFileLoader('q', sys.argv[1]); s = importlib.util.spec_from_loader('q', l)\n"
        "m = importlib.util.module_from_spec(s); l.exec_module(m)\n"
        "print(m.ROOT); print(m.ROLE_FILE); print(m.SCHEMA)\n"
    )
    r = subprocess.run([sys.executable, "-c", code, str(plugin / "bin" / "qa-codex-launcher")], cwd=proj, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    root, role_file, schema = (Path(x) for x in r.stdout.split())
    assert root == proj.resolve()
    assert role_file == proj.resolve() / "docs" / "team" / "qa-engineer.md"
    assert schema == (plugin / "bin" / "qa-result.schema.json").resolve() and schema.is_file()


def test_wrapper_is_two_lines_and_executable():
    text = WRAPPER.read_text()
    assert text == '#!/bin/sh\nexec qa-codex-launcher "$@"\n'
    assert WRAPPER.stat().st_mode & 0o100


def test_plugin_bin_holds_the_launcher_and_helpers_built_from_the_sources():
    assert build_plugin.differences() == []
    assert (PLUGIN / "bin" / "qa-codex-launcher").stat().st_mode & 0o100
    for name in ("codex_exec.py", "qa-result.schema.json"):
        assert (PLUGIN / "bin" / name).read_bytes() == (ROOT / "scripts" / name).read_bytes()
    assert not (PLUGIN / "templates" / "scripts" / "codex_exec.py").exists()


def test_build_check_reports_a_stray_file_in_bin(monkeypatch, tmp_path):
    copy = tmp_path / "plugin"
    shutil.copytree(PLUGIN, copy)
    monkeypatch.setattr(build_plugin, "PLUGIN", copy)
    (copy / "bin" / "stray.py").write_text("x\n")
    (copy / "bin" / "codex_exec.py").unlink()
    got = build_plugin.differences()
    assert "extra: plugin/bin/stray.py" in got
    assert "missing: plugin/bin/codex_exec.py" in got


def test_the_guard_form_still_passes_the_guard_with_the_wrapper():
    """The guard reads only the command text; the wrapper does not change it."""
    call = guard.classify({"tool_name": "Bash", "tool_input": {"command": "scripts/qa-codex ROLE=qa ISSUE=165"}})
    assert call is not None and call.issue == 165
