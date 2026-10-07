"""Tests for the setup skill `plugin/skills/setup/setup.py` (issue #160). All data is synthetic."""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import build_plugin

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "plugin" / "skills" / "setup" / "setup.py"
TEMPLATES = ROOT / "plugin" / "templates"
README = (ROOT / "README.md").read_text()

COPIED = (["docs/process.md", "docs/task-template.md", "scripts/qa-codex", "scripts/codex_exec.py",
           "scripts/qa-result.schema.json"]
          + [p.relative_to(TEMPLATES).as_posix() for d in ("docs/team", "docs/checks")
             for p in sorted((TEMPLATES / d).rglob("*")) if p.is_file()])


def fake_bin(tmp_path, gh=True, uv=True, codex=True, git=True):
    """A folder with fake gh, uv and codex (exit 0), and the real git. gh and codex: flags choose exit 0 or 1."""
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    for name, ok in (("gh", gh), ("uv", uv), ("codex", codex)):
        if name == "uv" and not ok:
            continue
        if name != "uv" and ok is None:
            continue
        f = b / name
        f.write_text(f"#!/bin/sh\nexit {0 if ok else 1}\n")
        f.chmod(0o755)
    if git and not (b / "git").exists():
        (b / "git").symlink_to(shutil.which("git"))
    return b


def run(root, tmp_path, bin_dir=None, home=None, name="example-app", cmd="make test", root_arg=None):
    bin_dir = bin_dir or fake_bin(tmp_path)
    home = home or (tmp_path / "home")
    home.mkdir(exist_ok=True)
    env = {"PATH": str(bin_dir), "HOME": str(home)}
    return subprocess.run(
        [sys.executable, str(SETUP), "--root", str(root_arg or root), "--name", name, "--test-command", cmd,
         "--home", str(home)], capture_output=True, text=True, env=env, timeout=120)


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    return p


def test_fresh_directory_copies_every_file(project, tmp_path):
    r = run(project, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "docs/team/orchestrator.md" in COPIED and "docs/checks/hook-activation.md" in COPIED
    for rel in COPIED:
        assert (project / rel).read_bytes() == (TEMPLATES / rel).read_bytes(), rel
    assert (project / "scripts/qa-codex").stat().st_mode & stat.S_IXUSR
    agents = (project / "AGENTS.md").read_text()
    assert agents.startswith("# example-app\n")
    assert "Test command: make test." in agents
    assert "{{" not in agents and "}}" not in agents
    # a plain copy, not the thin wrapper
    assert (project / "scripts/qa-codex").read_bytes() == (ROOT / "scripts/qa-codex").read_bytes()


def test_no_overwrite_reports_a_diff_and_keeps_the_entry_out(project, tmp_path):
    (project / "docs").mkdir()
    (project / "docs/process.md").write_bytes(b"my own process\n")
    (project / "docs/task-template.md").write_bytes((TEMPLATES / "docs/task-template.md").read_bytes())
    r = run(project, tmp_path)
    assert (project / "docs/process.md").read_bytes() == b"my own process\n"
    assert "docs/process.md" in r.stdout and "--- project/docs/process.md" in r.stdout
    assert "+++ plugin/docs/process.md" in r.stdout and "-my own process" in r.stdout
    files = json.loads((project / ".agent-graph-kit.lock").read_text())["files"]
    assert "docs/process.md" not in files
    assert "docs/task-template.md" in files
    assert "already identical" in r.stdout
    # the other files are still copied
    assert (project / "docs/team/pm.md").is_file() and (project / "AGENTS.md").is_file()


def test_existing_lock_entry_stays_when_the_file_differs(project, tmp_path):
    run(project, tmp_path)
    (project / "docs/process.md").write_bytes(b"changed\n")
    before = json.loads((project / ".agent-graph-kit.lock").read_text())["files"]["docs/process.md"]
    run(project, tmp_path)
    after = json.loads((project / ".agent-graph-kit.lock").read_text())["files"]["docs/process.md"]
    assert before == after
    assert (project / "docs/process.md").read_bytes() == b"changed\n"


def test_symlink_out_of_the_root_is_refused(project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "docs").symlink_to(outside)
    r = run(project, tmp_path)
    assert r.returncode == 0
    assert list(outside.iterdir()) == []
    assert "REFUSED" in r.stdout and "docs/process.md" in r.stdout
    files = json.loads((project / ".agent-graph-kit.lock").read_text())["files"]
    assert not any(k.startswith("docs/") for k in files)
    assert "scripts/qa-codex" in files


def test_missing_root_is_an_error_and_writes_nothing(tmp_path):
    missing = tmp_path / "nope"
    r = run(missing, tmp_path)
    assert r.returncode != 0
    assert not missing.exists()


def test_lock_file_matches_the_files_and_a_second_run_changes_nothing(project, tmp_path):
    import hashlib
    run(project, tmp_path)
    lock_text = (project / ".agent-graph-kit.lock").read_text()
    lock = json.loads(lock_text)
    assert lock["version"] == 1
    assert set(lock["files"]) == set(COPIED) | {"AGENTS.md", "CLAUDE.md"}
    for rel, digest in lock["files"].items():
        assert digest == hashlib.sha256((project / rel).read_bytes()).hexdigest(), rel
    snap = {p: p.read_bytes() for p in project.rglob("*") if p.is_file() and ".git" not in p.parts}
    r = run(project, tmp_path)
    assert r.returncode == 0
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file() and ".git" not in p.parts} == snap
    assert (project / ".agent-graph-kit.lock").read_text() == lock_text


def test_settings_file_is_created_with_the_permission_block(project, tmp_path):
    run(project, tmp_path)
    data = json.loads((project / ".claude/settings.json").read_text())
    assert data == {"permissions": {
        "allow": ["Bash(scripts/qa-codex ROLE=qa ISSUE=*)", "Bash(gh issue close *)"],
        "deny": ["Edit(/.claude/settings*.json)"]}}


ALLOW = ["Bash(scripts/qa-codex ROLE=qa ISSUE=*)", "Bash(gh issue close *)"]
DENY = ["Edit(/.claude/settings*.json)"]


def write_settings(project, text):
    (project / ".claude").mkdir(exist_ok=True)
    f = project / ".claude/settings.json"
    f.write_text(text)
    return f


def test_existing_settings_with_only_enabled_plugins_gets_the_permissions(project, tmp_path):
    f = write_settings(project, json.dumps({"enabledPlugins": {"agk@x": True}, "model": "m"}))
    r = run(project, tmp_path)
    assert r.returncode == 0
    assert json.loads(f.read_text()) == {"enabledPlugins": {"agk@x": True}, "model": "m",
                                         "permissions": {"allow": ALLOW, "deny": DENY}}
    assert "permissions merged" in r.stdout
    assert "exists; not changed" not in r.stdout


def test_existing_permissions_are_kept_in_order_without_duplicates(project, tmp_path):
    f = write_settings(project, json.dumps({"permissions": {
        "allow": ["Bash(ls)", ALLOW[1]], "ask": ["Bash(rm *)"], "defaultMode": "plan"}}))
    run(project, tmp_path)
    perms = json.loads(f.read_text())["permissions"]
    assert perms["allow"] == ["Bash(ls)", ALLOW[1], ALLOW[0]]
    assert perms["deny"] == DENY
    assert perms["ask"] == ["Bash(rm *)"] and perms["defaultMode"] == "plan"


def test_second_run_on_merged_settings_changes_nothing(project, tmp_path):
    f = write_settings(project, json.dumps({"enabledPlugins": {"a": True}}))
    run(project, tmp_path)
    first = f.read_bytes()
    run(project, tmp_path)
    assert f.read_bytes() == first


def test_invalid_json_settings_is_not_written_and_rules_are_printed(project, tmp_path):
    f = write_settings(project, "{not json")
    r = run(project, tmp_path)
    assert r.returncode == 0
    assert f.read_text() == "{not json"
    for rule in ALLOW + DENY:
        assert rule in r.stdout


def test_symlinked_settings_is_not_written_and_rules_are_printed(project, tmp_path):
    (project / ".claude").mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    (project / ".claude/settings.json").symlink_to(target)
    r = run(project, tmp_path)
    assert target.read_text() == "{}"
    for rule in ALLOW + DENY:
        assert rule in r.stdout


def test_skill_and_readme_no_longer_tell_the_owner_to_merge_by_hand_for_an_existing_file():
    skill = (SETUP.parent / "SKILL.md").read_text()
    assert "already existed, the permission lines" not in skill
    assert "merges the missing" in skill and "merges the permission lines" in README


def status_line(out, label):
    return next(l for l in out.splitlines() if l.rstrip().endswith(label) and not l.startswith(" "))


def test_manual_checks_all_ok(project, tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    root = os.path.realpath(project)
    (home / ".codex/config.toml").write_text(f'[projects."{root}"]\ntrust_level = "trusted"\n')
    r = run(project, tmp_path, home=home)
    assert r.returncode == 0
    for label in ("gh login", "uv", "Codex login", "Codex trust entry"):
        assert status_line(r.stdout, label).startswith("OK"), label


def test_manual_checks_missing(project, tmp_path):
    b = fake_bin(tmp_path, gh=False, uv=False, codex=False)
    r = run(project, tmp_path, bin_dir=b)
    assert r.returncode == 0
    for label in ("gh login", "uv", "Codex login", "Codex trust entry"):
        assert status_line(r.stdout, label).startswith("MISSING"), label
    assert "gh auth login" in r.stdout
    assert "README.md, Prerequisites" in r.stdout
    assert "codex login" in r.stdout
    assert f'[projects."{os.path.realpath(project)}"]\n' in r.stdout.replace("              ", "")
    assert 'trust_level = "trusted"' in r.stdout


def test_codex_missing_program_is_missing(project, tmp_path):
    b = fake_bin(tmp_path)
    (b / "codex").unlink()
    r = run(project, tmp_path, bin_dir=b)
    assert status_line(r.stdout, "Codex login").startswith("MISSING")


def test_trust_entry_for_other_path_or_level_is_missing(project, tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex/config.toml").write_text('[projects."/somewhere/else"]\ntrust_level = "trusted"\n'
                                             f'[projects."{os.path.realpath(project)}"]\ntrust_level = "untrusted"\n')
    r = run(project, tmp_path, home=home)
    assert status_line(r.stdout, "Codex trust entry").startswith("MISSING")


def test_trust_entry_without_a_git_repo_says_git_init(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    r = run(plain, tmp_path)
    assert r.returncode == 0
    assert status_line(r.stdout, "Codex trust entry").startswith("MISSING")
    assert "git init" in r.stdout


def test_auto_mode_entries_are_always_check_by_hand(project, tmp_path):
    home = tmp_path / "home"
    r = run(project, tmp_path, home=home)
    for n in (1, 2, 3):
        assert status_line(r.stdout, f"Auto mode entry {n}").startswith("CHECK BY HAND")
        assert "OK" not in status_line(r.stdout, f"Auto mode entry {n}")
    assert "scripts/qa-codex ROLE=qa ISSUE=<number>" in r.stdout
    flat = " ".join(r.stdout.split())
    for entry in (setup_entry(2), setup_entry(3)):
        assert entry in flat


def setup_entry(n):
    """The entry text of README.md, "Auto mode allow entries", as one line."""
    section = README.split("### Auto mode allow entries")[1]
    block = section.split(f"Entry {n} ")[1].split("```text\n")[1].split("```")[0]
    return " ".join(block.split())


def test_entries_in_the_script_equal_the_readme():
    sys.path.insert(0, str(SETUP.parent))
    try:
        import setup as s
    finally:
        sys.path.pop(0)
    assert " ".join(s.ENTRY_2.split()) == setup_entry(2)
    assert " ".join(s.ENTRY_3.split()) == setup_entry(3)
    assert "allow exactly `scripts/qa-codex ROLE=qa ISSUE=<number>` in the project repo" in README


def test_skill_names_the_lovable_lane_as_optional():
    text = (ROOT / "plugin/skills/setup/SKILL.md").read_text()
    assert text.startswith("---\nname: setup\n")
    section = text.split("## Lovable lane")[1]
    assert "separate" in section and "optional" in section and "after setup" in section
    assert "works without it" in section


def test_templates_are_checked_by_the_build(monkeypatch, tmp_path):
    copy = tmp_path / "plugin"
    shutil.copytree(ROOT / "plugin", copy)
    monkeypatch.setattr(build_plugin, "PLUGIN", copy)
    assert build_plugin.differences() == []
    (copy / "templates/docs/process.md").write_text("changed\n")
    (copy / "templates/docs/team/stray.md").write_text("x\n")
    (copy / "templates/scripts/other.py").write_text("x\n")
    (copy / "templates/docs/checks/hook-activation.md").unlink()
    got = build_plugin.differences()
    assert "differs: plugin/templates/docs/process.md" in got
    assert "extra: plugin/templates/docs/team/stray.md" in got
    assert "extra: plugin/templates/scripts/other.py" in got
    assert "missing: plugin/templates/docs/checks/hook-activation.md" in got


GI_LINES = [".claude/settings.local.json", "__pycache__/"]


def test_claude_md_is_written_and_listed_in_the_lock(project, tmp_path):
    run(project, tmp_path)
    assert (project / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert (project / "CLAUDE.md").read_bytes() == (ROOT / "CLAUDE.md").read_bytes()
    assert "CLAUDE.md" in json.loads((project / ".agent-graph-kit.lock").read_text())["files"]


def test_gitignore_is_created_with_the_two_lines(project, tmp_path):
    run(project, tmp_path)
    assert (project / ".gitignore").read_text().splitlines() == GI_LINES


def test_second_run_changes_neither_claude_md_nor_gitignore(project, tmp_path):
    run(project, tmp_path)
    snap = ((project / "CLAUDE.md").read_bytes(), (project / ".gitignore").read_bytes())
    assert run(project, tmp_path).returncode == 0
    assert ((project / "CLAUDE.md").read_bytes(), (project / ".gitignore").read_bytes()) == snap


def test_existing_claude_md_is_kept_and_a_diff_is_printed(project, tmp_path):
    (project / "CLAUDE.md").write_text("my own notes\n")
    r = run(project, tmp_path)
    assert (project / "CLAUDE.md").read_text() == "my own notes\n"
    assert "CONFLICT  CLAUDE.md" in r.stdout and "+@AGENTS.md" in r.stdout
    assert "CLAUDE.md" not in json.loads((project / ".agent-graph-kit.lock").read_text())["files"]


def test_existing_gitignore_gets_only_the_missing_lines(project, tmp_path):
    (project / ".gitignore").write_text("node_modules/\n__pycache__/")
    run(project, tmp_path)
    assert (project / ".gitignore").read_text() == "node_modules/\n__pycache__/\n.claude/settings.local.json\n"
    (project / ".gitignore").write_text("a\n.claude/settings.local.json\n__pycache__/\n")
    run(project, tmp_path)
    assert (project / ".gitignore").read_text() == "a\n.claude/settings.local.json\n__pycache__/\n"


def test_gitignore_line_with_leading_space_is_not_the_required_line(project, tmp_path):
    (project / ".gitignore").write_text(" __pycache__/\n" + GI_LINES[0] + "\n")
    run(project, tmp_path)
    assert (project / ".gitignore").read_text() == " __pycache__/\n" + GI_LINES[0] + "\n__pycache__/\n"


def test_v2_readme_names_labels_and_closing_steps_and_skill_lists_the_files():
    v2 = README.split("## Install the kit as a plugin (v2)")[1].split("## Lovable frontend lane")[0]
    for label in ("ready", "needs-owner", "later", "stage"):
        assert f"gh label create {label} " in v2
    assert v2.index("gh label create ready") < v2.index("git push") < v2.index("trust dialog") < v2.index("hook-activation.md")
    assert "ignored" in v2 and "permissions.allow" in v2
    skill = (ROOT / "plugin/skills/setup/SKILL.md").read_text().split("## What the script writes")[1]
    assert "`CLAUDE.md`" in skill and "`.gitignore`" in skill
