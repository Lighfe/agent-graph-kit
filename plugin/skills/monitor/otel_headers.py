#!/usr/bin/env python3
"""The `otelHeadersHelper` of Claude Code for the monitor stack (issue #324).

Claude Code runs this script in the folder of the session when the user settings
(`~/.claude/settings.json`) name it as `otelHeadersHelper`, and sends the JSON object it prints as
OTLP headers. The script prints `{"x-agk-project": "<owner/name>"}` when the session folder is the
repo folder of a project in `monitor-projects.json`, or a folder below it; else it prints `{}`.
The Collector moves the header into the resource attribute `agk.project`, and drops data without it.

`board.py up` copies this script to `<state dir>/otel-headers.py`, next to `monitor-projects.json`,
so the path in the user settings does not change with a plugin update. The script reads the project
list next to itself.

It always exits 0 and prints a JSON object (empty output counts as a failure in Claude Code, which
then shows a warning). It reads one file, starts no process and makes no network call.
Standard library only.
"""

import json
import os
import re
import sys
from pathlib import Path

HEADER = "x-agk-project"
LIST_NAME = "monitor-projects.json"
SLUG = re.compile(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+")


def project_for(folder, entries):
    """The `owner/name` of the entry whose repo is `folder` or a parent of it (the deepest one
    wins), or None. Paths are compared after symlinks are resolved."""
    here = os.path.realpath(folder)
    best, best_len = None, -1
    for e in entries:
        if not isinstance(e, dict):
            continue
        slug, repo = e.get("project"), e.get("repo")
        if not (isinstance(slug, str) and SLUG.fullmatch(slug) and isinstance(repo, str) and repo):
            continue
        root = os.path.realpath(os.path.expanduser(repo))
        inside = here == root or here.startswith(root.rstrip(os.sep) + os.sep)
        if inside and len(root) > best_len:
            best, best_len = slug, len(root)
    return best


def headers(folder, list_path):
    """The header object for a session in `folder`. Any problem gives `{}`."""
    try:
        entries = json.loads(Path(list_path).read_text(encoding="utf-8"))
        slug = project_for(folder, entries if isinstance(entries, list) else [])
    except Exception:
        slug = None
    return {HEADER: slug} if slug else {}


def main():
    try:
        out = headers(os.getcwd(), Path(os.path.abspath(__file__)).parent / LIST_NAME)
    except Exception:
        out = {}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
