"""Tests for the plugin release state (issue #187). All data is synthetic."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import build_plugin

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".claude-plugin/plugin.json"


def _copy(tmp_path):
    plugin = tmp_path / "plugin"
    shutil.copytree(ROOT / "plugin", plugin)
    release = tmp_path / "plugin-release.json"
    shutil.copy2(ROOT / "scripts" / "plugin-release.json", release)
    return plugin, release


def _store(plugin, release):
    version = json.loads((plugin / MANIFEST).read_text())["version"]
    release.write_text(json.dumps({"version": version, "sha256": build_plugin.plugin_hash(plugin)}))


def test_stored_version_matches_manifest():
    stored = json.loads((ROOT / "scripts" / "plugin-release.json").read_text())
    manifest = json.loads((ROOT / "plugin" / MANIFEST).read_text())
    assert set(stored) == {"version", "sha256"}
    assert stored["version"] == manifest["version"]
    assert tuple(map(int, manifest["version"].split("."))) > (0, 1, 0)
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in market["plugins"]:
        assert entry.get("version", manifest["version"]) == manifest["version"]


def test_changed_file_changes_hash(tmp_path):
    plugin, _ = _copy(tmp_path)
    before = build_plugin.plugin_hash(plugin)
    (plugin / "hooks" / "guard.py").write_text("# changed\n")
    assert build_plugin.plugin_hash(plugin) != before


def test_version_line_alone_does_not_change_hash(tmp_path):
    plugin, _ = _copy(tmp_path)
    before = build_plugin.plugin_hash(plugin)
    path = plugin / MANIFEST
    path.write_text(path.read_text().replace('"version": "0.1.1"', '"version": "9.9.9"'))
    assert build_plugin.plugin_hash(plugin) == before


def test_pycache_is_ignored(tmp_path):
    plugin, _ = _copy(tmp_path)
    before = build_plugin.plugin_hash(plugin)
    (plugin / "hooks" / "__pycache__").mkdir(exist_ok=True)
    (plugin / "hooks" / "__pycache__" / "x.pyc").write_bytes(b"x")
    (plugin / "hooks" / "y.pyc").write_bytes(b"y")
    assert build_plugin.plugin_hash(plugin) == before


def test_release_status_follows_stored_file(tmp_path):
    plugin, release = _copy(tmp_path)
    _store(plugin, release)
    assert build_plugin.release_status(plugin, release) == "released"
    (plugin / "hooks" / "guard.py").write_text("# changed\n")
    assert build_plugin.release_status(plugin, release) == "unreleased changes"
    _store(plugin, release)
    assert build_plugin.release_status(plugin, release) == "released"


def test_commands_run_on_the_repo():
    """Both commands exit 0. The status may be `unreleased changes` between two bumps: no test fails then."""
    script = str(ROOT / "scripts" / "build_plugin.py")
    r = subprocess.run([sys.executable, script, "--release-status"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() in {"released", "unreleased changes"}
    r = subprocess.run([sys.executable, script, "--hash"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == build_plugin.plugin_hash()


def test_skill_and_docs_rules():
    skill = (ROOT / ".agents" / "skills" / "bump-plugin-version" / "SKILL.md").read_text()
    assert "--release-status" in skill and "once" in skill and "last task" in skill
    assert not (ROOT / "plugin" / "skills" / "bump-plugin-version").exists()
    planner = (ROOT / "docs" / "team" / "planner.md").read_text()
    assert "Bump the plugin version" in planner and "--release-status" in planner
    assert "unreleased changes" in planner
    assert "Do not bump the plugin version in a task" in (ROOT / "docs" / "team" / "software-engineer.md").read_text()


def test_source_change_between_bumps_is_unreleased_and_tests_pass(tmp_path):
    """A plugin source changes and `build_plugin.py` copies it; the stored hash stays. The status is
    `unreleased changes`, and the copy-match test and the version-match test both pass.

    A change of a generated copy without its source is a different failure (the copy-match test
    `test_plugin_copies_match_the_v1_sources`) and not part of the release check."""
    repo = tmp_path / "repo"
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True)
    for rel in filter(None, tracked.stdout.split("\0")):
        if (ROOT / rel).is_file():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, repo / rel)
    script = repo / "scripts" / "build_plugin.py"
    run = lambda *a: subprocess.run([sys.executable, str(script), *a], cwd=repo, capture_output=True, text=True)
    assert run("--release-status").stdout.strip() == "released"
    with open(repo / ".claude" / "hooks" / "guard.py", "a") as f:
        f.write("\n# change between bumps\n")
    assert run().returncode == 0
    r = run("--release-status")
    assert r.returncode == 0 and r.stdout.strip() == "unreleased changes"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    t = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_plugin.py::test_plugin_copies_match_the_v1_sources",
         "tests/test_plugin_release.py::test_stored_version_matches_manifest"],
        cwd=repo, capture_output=True, text=True, env=env)
    assert t.returncode == 0, t.stdout + t.stderr
    assert "2 passed" in t.stdout
