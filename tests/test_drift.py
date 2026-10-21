"""Tests for the drift skill `plugin/skills/drift/drift.py` (issue #161). All data is synthetic."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIFT_SRC = ROOT / "plugin" / "skills" / "drift" / "drift.py"
LOCK = ".agent-graph-kit.lock"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def env(tmp_path):
    """A fake plugin (templates + drift.py in place) and a project root with a lock for nothing yet."""
    plugin = tmp_path / "plugin"
    (plugin / "templates" / "docs").mkdir(parents=True)
    (plugin / "skills" / "drift").mkdir(parents=True)
    shutil.copy(DRIFT_SRC, plugin / "skills" / "drift" / "drift.py")
    project = tmp_path / "project"
    project.mkdir()
    return plugin, project


def setup_file(plugin, project, rel, lock_data, project_data, template_data):
    """Return the lock entry for rel; write the template and the project file (None = do not write)."""
    if template_data is not None:
        t = plugin / "templates" / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_bytes(template_data)
    if project_data is not None:
        p = project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(project_data)
    return sha(lock_data)


def write_lock(project, files):
    (project / LOCK).write_text(json.dumps({"version": 1, "files": files}))


def run(plugin, project, *extra):
    return subprocess.run([sys.executable, str(plugin / "skills" / "drift" / "drift.py"), "--root", str(project), *extra],
                          capture_output=True, text=True, timeout=60)


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def lines(r):
    return r.stdout.splitlines()


def full_case(env):
    plugin, project = env
    files = {
        "docs/a.md": setup_file(plugin, project, "docs/a.md", b"a", b"a", b"a"),
        "docs/b.md": setup_file(plugin, project, "docs/b.md", b"b", b"b2", b"b"),
        "docs/c.md": setup_file(plugin, project, "docs/c.md", b"c", b"c", b"c2"),
        "docs/d.md": setup_file(plugin, project, "docs/d.md", b"d", b"d2", b"d3"),
        "docs/e.md": setup_file(plugin, project, "docs/e.md", b"e", b"e2", b"e2"),
        "docs/f.md": setup_file(plugin, project, "docs/f.md", b"f", None, b"f"),
        "docs/g.md": setup_file(plugin, project, "docs/g.md", b"g", b"g", None),
        "AGENTS.md": setup_file(plugin, project, "AGENTS.md", b"x", b"x", None),
    }
    write_lock(project, files)
    return plugin, project


def test_all_states(env):
    plugin, project = full_case(env)
    r = run(plugin, project)
    assert r.returncode == 0
    assert sorted(lines(r)) == sorted([
        "unchanged: docs/a.md",
        "changed in this project: docs/b.md",
        "newer in the plugin: docs/c.md",
        "changed in both: docs/d.md",
        "changed in both: docs/e.md",
        "deleted from this project: docs/f.md",
        "no longer in the plugin: docs/g.md",
        "unchanged: AGENTS.md",
    ])


def test_deleted_wins_when_template_also_changed(env):
    plugin, project = env
    write_lock(project, {"docs/f.md": setup_file(plugin, project, "docs/f.md", b"f", None, b"f2")})
    assert lines(run(plugin, project)) == ["deleted from this project: docs/f.md"]


def test_agents_md_changed_never_newer_in_plugin(env):
    plugin, project = env
    write_lock(project, {"AGENTS.md": setup_file(plugin, project, "AGENTS.md", b"x", b"y", None)})
    (plugin / "templates" / "AGENTS.md.tmpl").write_bytes(b"other")
    r = run(plugin, project)
    assert lines(r) == ["changed in this project: AGENTS.md"]
    assert r.returncode == 0


def test_agents_md_unchanged_even_with_template(env):
    plugin, project = env
    write_lock(project, {"AGENTS.md": setup_file(plugin, project, "AGENTS.md", b"x", b"x", b"different")})
    assert lines(run(plugin, project)) == ["unchanged: AGENTS.md"]


def test_claude_md_untouched_is_unchanged(env):
    plugin, project = env
    write_lock(project, {"CLAUDE.md": setup_file(plugin, project, "CLAUDE.md.tmpl", b"@AGENTS.md\n", None, b"@AGENTS.md\n")})
    (project / "CLAUDE.md").write_bytes(b"@AGENTS.md\n")
    assert lines(run(plugin, project)) == ["unchanged: CLAUDE.md"]


def test_claude_md_changed_in_project(env):
    plugin, project = env
    write_lock(project, {"CLAUDE.md": setup_file(plugin, project, "CLAUDE.md.tmpl", b"@AGENTS.md\n", None, b"@AGENTS.md\n")})
    (project / "CLAUDE.md").write_bytes(b"@AGENTS.md\nmore\n")
    assert lines(run(plugin, project)) == ["changed in this project: CLAUDE.md"]


def test_dropped_gone_from_both(env):
    plugin, project = env
    write_lock(project, {"scripts/old.py": sha(b"old")})
    assert lines(run(plugin, project)) == ["dropped (gone from both): scripts/old.py"]


def test_no_template_prints_one_line_only(env):
    plugin, project = env
    write_lock(project, {"docs/g.md": setup_file(plugin, project, "docs/g.md", b"g", b"changed", None)})
    assert lines(run(plugin, project)) == ["no longer in the plugin: docs/g.md"]


def test_missing_lock(env):
    plugin, project = env
    r = run(plugin, project)
    assert r.returncode == 1
    assert lines(r) == [l for l in lines(r) if l.startswith("not set up:")] and len(lines(r)) == 1
    assert LOCK in r.stdout
    assert "unchanged" not in r.stdout
    assert not (project / LOCK).exists()


@pytest.mark.parametrize("content", ["not json{", "[]", '{"version": 1}', '{"files": []}', ""])
def test_invalid_lock(env, content):
    plugin, project = env
    (project / LOCK).write_text(content)
    r = run(plugin, project)
    assert r.returncode == 1
    assert len(lines(r)) == 1 and lines(r)[0].startswith("not set up:") and LOCK in lines(r)[0]


def test_empty_files_map_is_valid_and_prints_nothing(env):
    plugin, project = env
    write_lock(project, {})
    r = run(plugin, project)
    assert r.returncode == 0 and r.stdout == ""


@pytest.mark.parametrize("case", ["full", "missing", "invalid"])
def test_writes_nothing(env, case):
    plugin, project = env
    if case == "full":
        full_case(env)
        (project / "docs" / "a.md").chmod(0o755)
    elif case == "invalid":
        (project / LOCK).write_text("nope")
    before = snapshot(project)
    run(plugin, project)
    assert snapshot(project) == before


def test_update_replaces_newer_file_and_keeps_mode(env):
    plugin, project = env
    files = {"docs/a.md": setup_file(plugin, project, "docs/a.md", b"a", b"a", b"a2"),
             "docs/z.md": setup_file(plugin, project, "docs/z.md", b"z", b"z", b"z")}
    write_lock(project, files)
    (project / "docs/a.md").chmod(0o755)
    r = run(plugin, project, "--update")
    assert r.returncode == 0
    assert "updated: docs/a.md" in lines(r)
    assert (project / "docs/a.md").read_bytes() == b"a2"
    assert (project / "docs/a.md").stat().st_mode & 0o777 == 0o755
    text = (project / LOCK).read_text()
    assert json.loads(text) == {"version": 1, "files": {"docs/a.md": sha(b"a2"), "docs/z.md": sha(b"z")}}
    assert text.endswith("}\n") and text.startswith('{\n  "version"')
    assert "unchanged: docs/a.md" in lines(run(plugin, project))


def test_update_leaves_every_other_state_alone(env):
    plugin, project = full_case(env)
    before = snapshot(project)
    r = run(plugin, project, "--update")
    assert r.returncode == 0
    assert "updated: docs/c.md" in lines(r)
    after = snapshot(project)
    lock = json.loads((project / LOCK).read_text())["files"]
    old = json.loads(before[LOCK][1])["files"]
    assert {k: v for k, v in lock.items() if k != "docs/c.md"} == {k: v for k, v in old.items() if k != "docs/c.md"}
    assert lock["docs/c.md"] == sha(b"c2")
    for rel in before:
        if rel not in (LOCK, "docs/c.md"):
            assert after[rel] == before[rel]


def test_update_lists_changed_in_both_untouched(env):
    plugin, project = full_case(env)
    r = run(plugin, project, "--update")
    assert "not touched (changed in both): docs/d.md" in lines(r)
    assert (project / "docs/d.md").read_bytes() == b"d2"
    assert json.loads((project / LOCK).read_text())["files"]["docs/d.md"] == sha(b"d")
    assert "changed in this project: docs/b.md" in lines(r)


def test_update_with_invalid_lock_writes_nothing(env):
    plugin, project = env
    (project / LOCK).write_text("not json")
    before = snapshot(project)
    r = run(plugin, project, "--update")
    assert r.returncode == 1
    assert lines(r)[0].startswith("not set up:")
    assert snapshot(project) == before
    (project / LOCK).unlink()
    r = run(plugin, project, "--update")
    assert r.returncode == 1 and lines(r)[0].startswith("not set up:")
    assert not (project / LOCK).exists()


def test_without_flag_writes_nothing_even_with_newer_file(env):
    plugin, project = full_case(env)
    before = snapshot(project)
    r = run(plugin, project)
    assert "newer in the plugin: docs/c.md" in lines(r)
    assert snapshot(project) == before


def accept_case(env):
    plugin, project = env
    files = {
        "docs/a.md": setup_file(plugin, project, "docs/a.md", b"a", b"a2", b"a3"),  # changed in both
        "docs/b.md": setup_file(plugin, project, "docs/b.md", b"b", b"b2", b"b2"),
        "docs/nt.md": setup_file(plugin, project, "docs/nt.md", b"n", b"n", None),
        "docs/np.md": setup_file(plugin, project, "docs/np.md", b"p", None, b"p"),
        "AGENTS.md": setup_file(plugin, project, "AGENTS.md", b"x", b"x", None),
        "CLAUDE.md": sha(b"c"),
    }
    (project / "CLAUDE.md").write_bytes(b"c-merged")
    (plugin / "templates" / "CLAUDE.md.tmpl").write_bytes(b"c2")
    write_lock(project, files)
    return plugin, project


def test_accept_sets_lock_to_template_and_writes_only_the_lock(env):
    plugin, project = accept_case(env)
    before = snapshot(project)
    r = run(plugin, project, "--accept", "docs/a.md", "CLAUDE.md")
    assert r.returncode == 0
    assert lines(r) == ["accepted: docs/a.md", "accepted: CLAUDE.md"]
    after = snapshot(project)
    for rel in before:
        if rel != LOCK:
            assert after[rel] == before[rel]
    new = json.loads((project / LOCK).read_text())["files"]
    old = json.loads(before[LOCK][1])["files"]
    assert new["docs/a.md"] == sha(b"a3") and new["CLAUDE.md"] == sha(b"c2")
    assert {k: v for k, v in new.items() if k not in ("docs/a.md", "CLAUDE.md")} == \
        {k: v for k, v in old.items() if k not in ("docs/a.md", "CLAUDE.md")}


def test_accept_then_drift_reports_changed_in_this_project_or_unchanged(env):
    plugin, project = accept_case(env)
    assert run(plugin, project, "--accept", "docs/a.md", "docs/b.md").returncode == 0
    out = lines(run(plugin, project))
    assert "changed in this project: docs/a.md" in out
    assert "unchanged: docs/b.md" in out


@pytest.mark.parametrize("path,msg", [
    ("docs/zzz.md", "cannot accept (not in the lock): docs/zzz.md"),
    ("./docs/a.md", "cannot accept (not in the lock): ./docs/a.md"),
    ("docs/nt.md", "cannot accept (no template in the plugin): docs/nt.md"),
    ("docs/np.md", "cannot accept (not in the project): docs/np.md"),
    ("AGENTS.md", "cannot accept (AGENTS.md has no template to compare): AGENTS.md"),
])
def test_accept_refusals_write_nothing_even_for_a_good_path(env, path, msg):
    plugin, project = accept_case(env)
    before = snapshot(project)
    r = run(plugin, project, "--accept", "docs/a.md", path)
    assert r.returncode == 1
    assert lines(r) == [msg]
    assert snapshot(project) == before


def test_accept_with_missing_or_invalid_lock(env):
    plugin, project = env
    r = run(plugin, project, "--accept", "docs/a.md")
    assert r.returncode == 1 and lines(r)[0].startswith("not set up:")
    assert not (project / LOCK).exists()
    (project / LOCK).write_text("not json")
    before = snapshot(project)
    r = run(plugin, project, "--accept", "docs/a.md")
    assert r.returncode == 1 and lines(r)[0].startswith("not set up:")
    assert snapshot(project) == before


def test_accept_with_update_is_an_argparse_error(env):
    plugin, project = accept_case(env)
    before = snapshot(project)
    r = run(plugin, project, "--accept", "docs/a.md", "--update")
    assert r.returncode == 2
    assert snapshot(project) == before


def dropped_case(env):
    plugin, project = env
    files = {
        "docs/a.md": setup_file(plugin, project, "docs/a.md", b"a", b"a", b"a"),
        "docs/gone.md": sha(b"gone"),
    }
    write_lock(project, files)
    return plugin, project


def test_update_removes_dropped_entry(env):
    plugin, project = dropped_case(env)
    r = run(plugin, project, "--update")
    assert r.returncode == 0
    assert "removed from the lock: docs/gone.md" in lines(r)
    assert "unchanged: docs/a.md" in lines(r)
    assert set(json.loads((project / LOCK).read_text())["files"]) == {"docs/a.md"}


def test_plain_drift_keeps_dropped_entry_and_writes_nothing(env):
    plugin, project = dropped_case(env)
    before = snapshot(project)
    r = run(plugin, project)
    assert "dropped (gone from both): docs/gone.md" in lines(r)
    assert snapshot(project) == before
