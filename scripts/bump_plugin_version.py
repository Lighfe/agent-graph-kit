#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Bump the patch number of the agk plugin version (issue #227). Run once at the end of a stage.

  scripts/bump_plugin_version.py

Steps: build the plugin copies, raise the patch number of `version` in
`plugin/.claude-plugin/plugin.json`, write the new version and the plugin hash to
`scripts/plugin-release.json`, check that `build_plugin.py --release-status` answers `released`.
When it answers `released` already, nothing changes and the script exits 0.
When a step fails, the script exits 1 and restores the two files. The minor and
major number are a human decision.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_plugin  # noqa: E402

MANIFEST = build_plugin.PLUGIN / ".claude-plugin" / "plugin.json"
RELEASE = build_plugin.RELEASE_FILE
VERSION = re.compile(r'^([ \t]*"version"[ \t]*:[ \t]*")(\d+)\.(\d+)\.(\d+)(")', re.M)


def bump() -> tuple[str, str] | None:
    """Return (old, new) version, or None when no bump is needed. Raises when a step fails."""
    if build_plugin.release_status() == "released":
        return None
    missing = [d for d in build_plugin.differences() if d.startswith("source missing")]
    if missing:
        raise RuntimeError("; ".join(missing))
    build_plugin.build()
    text = MANIFEST.read_text()
    m = VERSION.search(text)
    if not m:
        raise RuntimeError(f"no x.y.z version line in {MANIFEST.name}")
    old = ".".join(m.group(2, 3, 4))
    new = f"{m.group(2)}.{m.group(3)}.{int(m.group(4)) + 1}"
    MANIFEST.write_text(VERSION.sub(lambda _: f"{m.group(1)}{new}{m.group(5)}", text, count=1))
    RELEASE.write_text(json.dumps({"version": new, "sha256": build_plugin.plugin_hash()}, indent=2) + "\n")
    status = build_plugin.release_status()
    if status != "released":
        raise RuntimeError(f"release status after the bump is '{status}'")
    return old, new


def main() -> int:
    saved = {p: (p.read_bytes() if p.exists() else None) for p in (MANIFEST, RELEASE)}
    try:
        result = bump()
    except Exception as e:  # any failed step: restore both files
        for p, data in saved.items():
            if data is not None:
                p.write_bytes(data)
        print(f"bump failed: {e}", file=sys.stderr)
        return 1
    if result is None:
        print("no bump needed: plugin is released")
    else:
        print(f"plugin version {result[0]} -> {result[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
