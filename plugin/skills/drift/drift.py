#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Show the drift of the copied kit files in a project (issue #161).

  uv run --script drift.py --root <project root>

Reads `.agent-graph-kit.lock` and prints one line `<state>: <path>` per locked path. It compares the
sha256 of the lock (L), the project file (P) and the plugin template (T). It writes no file.
Exit code 1 only when the lock file is missing or unusable, otherwise 0.
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


def state(root: Path, rel: str, lock_sha: str) -> str:
    target = root / rel
    if not target.exists() and not target.is_symlink():
        return f"deleted from this project: {rel}"
    if rel == AGENTS:
        template_sha = lock_sha  # filled in at setup: no plugin value to compare
    else:
        template = TEMPLATES / rel
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root)
    lock = read_lock(root / LOCK)
    if lock is None:
        print(f"not set up: {LOCK} is missing or not a valid lock file in {root}")
        return 1
    for rel in sorted(lock):
        print(state(root, rel, lock[rel]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
