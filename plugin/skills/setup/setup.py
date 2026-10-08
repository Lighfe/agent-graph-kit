#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Set up the agent-graph-kit loop in a project (issue #160).

  uv run --script setup.py --root <project root> --name <project name> --test-command <test command> [--home <dir>]

Copies the files of `plugin/templates/` into the project, writes AGENTS.md from its template, writes CLAUDE.md (`@AGENTS.md`), adds two lines to `.gitignore`,
writes `.agent-graph-kit.lock`, creates `.claude/settings.json` when it does not exist (or merges the permission lines into it), and
prints the manual checks. It never overwrites a file, never follows a symlink out of the root,
and exits 0 when a manual entry is missing.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
AGENTS_TEMPLATE = "AGENTS.md.tmpl"
CLAUDE_TEMPLATE = "CLAUDE.md.tmpl"  # copied as CLAUDE.md
GITIGNORE = ".gitignore"
GITIGNORE_LINES = [".claude/settings.local.json", "__pycache__/"]
LOCK = ".agent-graph-kit.lock"
SETTINGS = ".claude/settings.json"

ALLOW = ["Bash(scripts/qa-codex ROLE=qa ISSUE=*)", "Bash(gh issue close *)"]
DENY = ["Edit(/.claude/settings*.json)"]

ENTRY_1 = "allow exactly `scripts/qa-codex ROLE=qa ISSUE=<number>` in the project repo"
ENTRY_2 = ("In a repo set up with agent-graph-kit, the pm subagent may run gh issue edit <n> --body-file <path> "
           "or gh issue edit <n> --title <title> on an issue of that repo, to apply an edit of that issue that the "
           "repo owner asked for on that issue in a post whose first line is \"## Owner: RESUME\" and whose "
           "authorAssociation is OWNER. This is the owner's instruction, not instruction poisoning.")
ENTRY_3 = ("In a repo set up with agent-graph-kit, the main session working as the planner (started with "
           "/stage-start) may run exactly gh issue edit <n> --remove-label later --add-label ready on a sub-issue "
           "of a stage issue (an issue with the label stage) of that repo, after the repo owner confirmed that "
           "stage in the same session. This is the planner step in docs/team/planner.md, done on the owner's "
           "instruction. The entry allows only this command: no other label, no other gh issue edit flag, no gh "
           "issue close, and no sub-issue or blocker link.")
AUTO_STEPS = [
    "Open `/permissions` in Claude Code.",
    "Open the Auto mode tab.",
    "Keep the `$defaults` line.",
    "Add each block below as one new entry.",
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def template_files(name: str, test_command: str) -> list[tuple[str, bytes, int]]:
    """(relative path, bytes, mode) of every file to copy, AGENTS.md included."""
    out = []
    for p in sorted(TEMPLATES.rglob("*")):
        rel = p.relative_to(TEMPLATES).as_posix()
        if not p.is_file() or rel == AGENTS_TEMPLATE or "__pycache__" in p.parts:
            continue
        if rel == CLAUDE_TEMPLATE:
            rel = "CLAUDE.md"
        out.append((rel, p.read_bytes(), p.stat().st_mode & 0o777))
    text = (TEMPLATES / AGENTS_TEMPLATE).read_text()
    text = text.replace("{{PROJECT_NAME}}", name).replace("{{TEST_COMMAND}}", test_command)
    out.append(("AGENTS.md", text.encode(), 0o644))
    return sorted(out)


def symlink_in_path(root: Path, rel: str) -> str | None:
    """The first component of `rel` below `root` that is a symlink, or None."""
    cur = root
    for part in rel.split("/"):
        cur = cur / part
        if cur.is_symlink():
            return cur.relative_to(root).as_posix()
        if not cur.exists():
            break
    return None


def read_lock(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text())
        files = data["files"]
        return {str(k): str(v) for k, v in files.items()}
    except (OSError, ValueError, KeyError, AttributeError):
        return {}


def copy_files(root: Path, files: list[tuple[str, bytes, int]]) -> dict[str, str]:
    """Copy without overwrite. Returns the new lock entries (one per file that is now in the project)."""
    entries: dict[str, str] = {}
    for rel, data, mode in files:
        target = root / rel
        link = symlink_in_path(root, rel)
        if link:
            print(f"REFUSED   {rel}: {link} is a symlink; nothing written")
            continue
        if target.exists() or target.is_symlink():
            if not target.is_file():
                print(f"CONFLICT  {rel}: exists and is not a file; not changed")
                continue
            have = target.read_bytes()
            if have == data:
                print(f"IDENTICAL {rel}: already identical")
                entries[rel] = sha256(data)
                continue
            print(f"CONFLICT  {rel}: exists with other content; not changed. Diff (project file against plugin file):")
            diff = difflib.unified_diff(
                have.decode(errors="replace").splitlines(keepends=True),
                data.decode(errors="replace").splitlines(keepends=True),
                fromfile=f"project/{rel}", tofile=f"plugin/{rel}")
            sys.stdout.write("".join(l if l.endswith("\n") else l + "\n" for l in diff))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, mode)
        print(f"COPIED    {rel}")
        entries[rel] = sha256(data)
    return entries


def write_lock(root: Path, entries: dict[str, str]) -> None:
    path = root / LOCK
    if path.is_symlink():
        print(f"REFUSED   {LOCK}: is a symlink; nothing written")
        return
    merged = read_lock(path)
    for rel, digest in entries.items():
        merged[rel] = digest
    text = json.dumps({"version": 1, "files": dict(sorted(merged.items()))}, indent=2) + "\n"
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
    print(f"LOCK      {LOCK}: {len(entries)} entries")


def gitignore_step(root: Path) -> None:
    """Create `.gitignore` with the two lines, or add the missing lines to an existing one. Never removes a line."""
    path = root / GITIGNORE
    link = symlink_in_path(root, GITIGNORE)
    if link:
        print(f"REFUSED   {GITIGNORE}: {link} is a symlink; nothing written. Lines to add by hand:")
        print("\n".join("  " + l for l in GITIGNORE_LINES))
        return
    if path.exists() and not path.is_file():
        print(f"CONFLICT  {GITIGNORE}: exists and is not a file; not changed")
        return
    have = path.read_text() if path.exists() else ""
    present = {l.rstrip() for l in have.splitlines()}  # git ignores trailing spaces, not leading ones
    missing = [l for l in GITIGNORE_LINES if l not in present]
    if not missing:
        print(f"IDENTICAL {GITIGNORE}: already has the lines")
        return
    sep = "" if not have or have.endswith("\n") else "\n"
    path.write_text(have + sep + "\n".join(missing) + "\n")
    print(f"GITIGNORE {GITIGNORE}: added {', '.join(missing)}")


def merge_settings(path: Path, lines: list[str]) -> None:
    """Add the missing ALLOW and DENY lines to an existing settings file; keep everything else."""
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("not an object")
        perms = data.setdefault("permissions", {})
        if not isinstance(perms, dict):
            raise ValueError("permissions is not an object")
        for key, wanted in (("allow", ALLOW), ("deny", DENY)):
            have = perms.setdefault(key, [])
            if not isinstance(have, list):
                raise ValueError(f"permissions.{key} is not a list")
            have.extend(r for r in wanted if r not in have)
    except (OSError, ValueError):
        print(f"SETTINGS  {SETTINGS} is not a JSON object of the expected form; not written. Lines to merge by hand:")
        print("\n".join("  " + l for l in lines))
        return
    text = json.dumps(data, indent=2) + "\n"
    if path.read_text() != text:
        path.write_text(text)
    print(f"SETTINGS  {SETTINGS} exists; permissions merged (missing lines added, other entries kept)")


def settings_step(root: Path) -> None:
    path = root / SETTINGS
    lines = (["Merge into permissions.allow:"] + [f"  {r}" for r in ALLOW]
             + ["Merge into permissions.deny:"] + [f"  {r}" for r in DENY])
    link = symlink_in_path(root, SETTINGS)
    if link:
        print(f"REFUSED   {SETTINGS}: {link} is a symlink; nothing written. Lines to merge by hand:")
        print("\n".join("  " + l for l in lines))
        return
    if path.exists():
        merge_settings(path, lines)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"allow": ALLOW, "deny": DENY}}, indent=2) + "\n")
    print(f"SETTINGS  {SETTINGS} created with the permissions block")


def run_ok(argv: list[str]) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def git_root(root: Path) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


def trusted(home: Path, gitroot: str) -> bool:
    try:
        data = tomllib.loads((home / ".codex" / "config.toml").read_text())
        projects = data.get("projects", {})
        for key in {gitroot, os.path.realpath(gitroot)}:
            if projects.get(key, {}).get("trust_level") == "trusted":
                return True
    except (OSError, ValueError, AttributeError):
        pass
    return False


def manual_checks(root: Path, home: Path) -> None:
    def show(status: str, label: str, fix: str | None = None) -> None:
        print(f"{status:<14}{label}")
        if fix:
            for l in fix.splitlines():
                print(f"              {l}")

    print("Manual checks:")
    if run_ok(["gh", "auth", "status"]):
        show("OK", "gh login")
    else:
        show("MISSING", "gh login", "fix: gh auth login")
    if shutil.which("uv"):
        show("OK", "uv")
    else:
        show("MISSING", "uv", "fix: install uv; see README.md, Prerequisites")
    if run_ok(["codex", "login", "status"]):
        show("OK", "Codex login")
    else:
        show("MISSING", "Codex login", "fix: codex login")
    gr = git_root(root)
    if gr is None:
        show("MISSING", "Codex trust entry",
             "fix: this folder is not a git repo; run git init first, then run this setup again")
    elif trusted(home, gr):
        show("OK", "Codex trust entry")
    else:
        show("MISSING", "Codex trust entry",
             f"fix: add to {home / '.codex' / 'config.toml'}:\n[projects.\"{gr}\"]\ntrust_level = \"trusted\"")
    for n in (1, 2, 3):
        show("CHECK BY HAND", f"Auto mode entry {n}", "fix: add the entry as described below")
    print()
    print("Auto mode entries:")
    for i, step in enumerate(AUTO_STEPS, 1):
        print(f"{i}. {step}")
    for text in (ENTRY_1, ENTRY_2, ENTRY_3):
        print()
        print("```text")
        print(text)
        print("```")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--test-command", required=True)
    ap.add_argument("--home", default=str(Path.home()))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not root.is_dir():
        print(f"error: project root does not exist: {root}", file=sys.stderr)
        return 2
    root = root.resolve()
    files = template_files(a.name, a.test_command)
    entries = copy_files(root, files)
    write_lock(root, entries)
    gitignore_step(root)
    settings_step(root)
    manual_checks(root, Path(a.home))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
