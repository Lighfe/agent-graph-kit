#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Release channels of the agk plugin (issue #326). Used by the workflows `release-dev` and
`release-stable`; it does not push, tag or call GitHub itself.

  scripts/release_channels.py [--root <repo>] check
  scripts/release_channels.py [--root <repo>] marketplace <dev|stable>

`check` prints `release v<version>` when the plugin version in
`plugin/.claude-plugin/plugin.json` has no git tag `v<version>` yet, else `no release`.
`marketplace` sets the marketplace name of the channel in `.claude-plugin/marketplace.json`,
in place: `agent-graph-kit-dev` for `dev`, `agent-graph-kit` for `stable`.
`--root` is the repo to work on; the default is the repo of this script.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("plugin") / ".claude-plugin" / "plugin.json"
MARKETPLACE = Path(".claude-plugin") / "marketplace.json"
NAMES = {"dev": "agent-graph-kit-dev", "stable": "agent-graph-kit"}
VERSION = re.compile(r"\d+\.\d+\.\d+")
NAME_LINE = re.compile(r'^([ \t]*"name"[ \t]*:[ \t]*)"(?:[^"\\]|\\.)*"', re.M)


def plugin_version(root: Path) -> str:
    """The plugin version of the repo `root`. Exits 1 unless it has the form X.Y.Z."""
    version = json.loads((Path(root) / MANIFEST).read_text(encoding="utf-8")).get("version")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        print(f"not a version: {version}", file=sys.stderr)
        raise SystemExit(1)
    return version


def needs_release(version: str, tags: list[str]) -> bool:
    """True when the tag `v<version>` does not exist yet."""
    return f"v{version}" not in tags


def channel_marketplace(text: str, channel: str) -> str:
    """The text of `marketplace.json` with the marketplace name of `channel`, all else unchanged."""
    if channel not in NAMES:
        raise ValueError(f"not a channel: {channel!r}, expected one of {sorted(NAMES)}")
    data = json.loads(text)
    wanted = dict(data, name=NAMES[channel])
    # Change only the name line, so the diff of the channel commit is one line. The first
    # `"name"` line can belong to a plugin entry; then write the whole file again.
    changed = NAME_LINE.sub(lambda m: m.group(1) + json.dumps(NAMES[channel]), text, count=1)
    if json.loads(changed) == wanted:
        return changed
    return json.dumps(wanted, indent=2, ensure_ascii=False) + "\n"


def git_tags(root: Path) -> list[str]:
    done = subprocess.run(["git", "tag", "--list"], cwd=root, capture_output=True, text=True)
    if done.returncode != 0:
        print(f"git tag failed: {done.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return done.stdout.split()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release channels of the agk plugin.")
    parser.add_argument("--root", type=Path, default=ROOT, help="the repo to work on (default: the repo of this script)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="print `release v<version>` or `no release`")
    market = commands.add_parser("marketplace", help="set the marketplace name of a channel, in place")
    market.add_argument("channel", choices=sorted(NAMES))
    args = parser.parse_args(argv)
    if args.command == "check":
        version = plugin_version(args.root)
        print(f"release v{version}" if needs_release(version, git_tags(args.root)) else "no release")
        return 0
    path = args.root / MARKETPLACE
    path.write_text(channel_marketplace(path.read_text(encoding="utf-8"), args.channel), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
