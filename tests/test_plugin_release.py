"""Tests for the plugin release state (issue #187). All data is synthetic."""

import json
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


def test_committed_repo_is_released():
    for flag, want in (("--release-status", "released"), ("--hash", build_plugin.plugin_hash())):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_plugin.py"), flag],
                           capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout.strip() == want


def test_skill_and_docs_rules():
    skill = (ROOT / ".agents" / "skills" / "bump-plugin-version" / "SKILL.md").read_text()
    assert "--release-status" in skill and "once" in skill and "last task" in skill
    assert not (ROOT / "plugin" / "skills" / "bump-plugin-version").exists()
    planner = (ROOT / "docs" / "team" / "planner.md").read_text()
    assert "Bump the plugin version" in planner and "--release-status" in planner
    assert "unreleased changes" in planner
    assert "Do not bump the plugin version in a task" in (ROOT / "docs" / "team" / "software-engineer.md").read_text()
