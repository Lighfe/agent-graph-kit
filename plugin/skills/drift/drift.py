#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Show the drift of the copied kit files in a project (issue #161).

  uv run --script drift.py --root <project root>

Reads `.agent-graph-kit.lock` and prints one line `<state>: <path>` per locked path. It compares the
sha256 of the lock (L), the project file (P) and the plugin template (T). It writes no file.

  uv run --script drift.py --root <project root> --update

With `--update` it replaces only the files that are `newer in the plugin` with the plugin template and
sets their lock entries to the new sha256 (issue #201). Every other file and lock entry stays as it was.
`--update` also deletes each lock entry whose state is `dropped (gone from both)` and prints
`removed from the lock: <path>`. Plain drift writes nothing.
Exit code 1 only when the lock file is missing or unusable, otherwise 0.

  uv run --script drift.py --root <project root> --accept <path> [<path> ...]

After the owner has merged a kit file by hand, `--accept` sets the lock entry of each path to the sha256
of the current plugin template (`CLAUDE.md.tmpl` for `CLAUDE.md`) and prints `accepted: <path>`. It
changes no project file and no other lock entry. A path is refused, in this order, when it is `AGENTS.md`
(no template to compare), not in the lock, has no plugin template, or is not in the project; paths are
used as written. When any path is refused, nothing is written and the exit code is 1. A missing or
unusable lock file prints the `not set up` line and exits with 1. `--accept` and `--update` exclude
each other (argparse error, exit code 2).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
LOCK = ".agent-graph-kit.lock"
AGENTS = "AGENTS.md"
CLAUDE = "CLAUDE.md"


def sha256_of(path: Path) -> str | None:
    """sha256 of a file, or None when it is not a readable file."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_lock(path: Path) -> dict[str, str] | None:
    try:
        files = json.loads(path.read_text())["files"]
        if not isinstance(files, dict):
            return None
        return {str(k): str(v) for k, v in files.items()}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def template_path(rel: str) -> Path:
    """The plugin template of a locked path. AGENTS.md and CLAUDE.md are copied from a `.tmpl` file."""
    if rel in (AGENTS, CLAUDE):
        return TEMPLATES / f"{rel}.tmpl"
    return TEMPLATES / rel


def state(root: Path, rel: str, lock_sha: str) -> str:
    target = root / rel
    template = template_path(rel)
    if not target.exists() and not target.is_symlink():
        if not template.is_file():
            return f"dropped (gone from both): {rel}"
        return f"deleted from this project: {rel}"
    if rel == AGENTS:
        template_sha = lock_sha  # filled in at setup: no plugin value to compare
    else:
        if not template.is_file():
            return f"no longer in the plugin: {rel}"
        template_sha = sha256_of(template)
    project_sha = sha256_of(target)
    project_same = project_sha == lock_sha
    plugin_same = template_sha == lock_sha
    if project_same and plugin_same:
        label = "unchanged"
    elif project_same:
        label = "newer in the plugin"
    elif plugin_same:
        label = "changed in this project"
    else:
        label = "changed in both"
    return f"{label}: {rel}"


def accept(root: Path, lock: dict[str, str], paths: list[str]) -> int:
    """Set the lock entry of each path to the sha256 of its plugin template. All or nothing."""
    new_lock = dict(lock)
    refused = False
    for rel in paths:
        if rel == AGENTS:
            reason = f"cannot accept (AGENTS.md has no template to compare): {rel}"
        elif rel not in lock:
            reason = f"cannot accept (not in the lock): {rel}"
        elif sha256_of(template_path(rel)) is None:
            reason = f"cannot accept (no template in the plugin): {rel}"
        elif not (root / rel).exists() and not (root / rel).is_symlink():
            reason = f"cannot accept (not in the project): {rel}"
        else:
            new_lock[rel] = sha256_of(template_path(rel))
            continue
        print(reason)
        refused = True
    if refused:
        return 1
    text = json.dumps({"version": 1, "files": dict(sorted(new_lock.items()))}, indent=2) + "\n"
    (root / LOCK).write_text(text)
    for rel in paths:
        print(f"accepted: {rel}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--update", action="store_true",
                    help="replace the files that are newer in the plugin; touch nothing else")
    ap.add_argument("--accept", nargs="+", metavar="PATH",
                    help="record the current plugin template as the lock entry of hand-merged files")
    a = ap.parse_args(argv)
    if a.accept and a.update:
        ap.error("--accept and --update cannot be used together")
    root = Path(a.root)
    lock = read_lock(root / LOCK)
    if lock is None:
        print(f"not set up: {LOCK} is missing or not a valid lock file in {root}")
        return 1
    if a.accept:
        return accept(root, lock, a.accept)
    new_lock = dict(lock)
    for rel in sorted(lock):
        line = state(root, rel, lock[rel])
        if a.update and line.startswith("newer in the plugin: "):
            data = template_path(rel).read_bytes()
            (root / rel).write_bytes(data)  # keeps the file mode of the project file
            new_lock[rel] = hashlib.sha256(data).hexdigest()
            print(f"updated: {rel}")
        elif a.update and line.startswith("dropped (gone from both): "):
            del new_lock[rel]
            print(f"removed from the lock: {rel}")
        elif a.update and line.startswith("changed in both: "):
            print(f"not touched (changed in both): {rel}")
        else:
            print(line)
    if a.update and new_lock != lock:
        text = json.dumps({"version": 1, "files": dict(sorted(new_lock.items()))}, indent=2) + "\n"
        (root / LOCK).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
