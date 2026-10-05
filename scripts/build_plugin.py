#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Build the plugin folder `plugin/` from the v1 files of this repo (issue #159).

The v1 files stay the only source of the hook scripts, the agents and the skills.
`plugin/hooks/*.py`, `plugin/agents/` and `plugin/skills/` are generated copies:
do not edit them. `plugin/templates/` (docs, role files, QA launcher) is built the same way.
The hand-written files are `plugin/.claude-plugin/plugin.json`, `plugin/hooks/hooks.json`,
`plugin/skills/setup/` and `plugin/templates/AGENTS.md.tmpl`.

  scripts/build_plugin.py          write the copies
  scripts/build_plugin.py --check  list copies that differ from the source, exit 1 when any
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"

HOOK_SCRIPTS = ["guard.py", "issue_state.py", "not_started.py", "outage_stop.py"]
AGENTS = ["pm", "software-engineer", "frontend-engineer", "qa-engineer", "planner"]
SKILLS = ["stage-start", "codex-review"]
HAND_SKILLS = ["setup", "drift"]  # written by hand in plugin/skills/, not built (issues #160, #161)
# plugin/templates/: the files that /agk:setup copies into a project (issue #160)
TEMPLATE_FILES = ["docs/process.md", "docs/task-template.md", "scripts/qa-codex", "scripts/codex_exec.py",
                  "scripts/qa-result.schema.json"]
TEMPLATE_DIRS = ["docs/team", "docs/checks"]
HAND_TEMPLATES = {"AGENTS.md.tmpl"}  # written by hand in plugin/templates/
IGNORED = {"__pycache__", ".pytest_cache"}


def _tree(base: Path) -> dict[str, bytes]:
    """All files under `base` (a file or a folder) as {relative posix path: bytes}."""
    if base.is_file():
        return {"": base.read_bytes()}
    return {
        p.relative_to(base).as_posix(): p.read_bytes()
        for p in sorted(base.rglob("*"))
        if p.is_file() and not (set(p.relative_to(base).parts) & IGNORED) and p.suffix != ".pyc"
    }


def mapping() -> list[tuple[Path, Path]]:
    """(source, plugin copy) pairs: a file pair or a folder pair."""
    pairs = [(ROOT / ".claude" / "hooks" / n, PLUGIN / "hooks" / n) for n in HOOK_SCRIPTS]
    pairs += [(ROOT / ".claude" / "agents" / f"{n}.md", PLUGIN / "agents" / f"{n}.md") for n in AGENTS]
    pairs += [(ROOT / ".agents" / "skills" / n, PLUGIN / "skills" / n) for n in SKILLS]
    for rel in TEMPLATE_FILES + TEMPLATE_DIRS:
        pairs.append((ROOT / rel, PLUGIN / "templates" / rel))
    return pairs


def differences() -> list[str]:
    """One line per copy that is missing, extra or different."""
    out = []
    for src, dst in mapping():
        if not src.exists():
            out.append(f"source missing: {src.relative_to(ROOT)}")
            continue
        want = _tree(src)
        have = _tree(dst) if dst.exists() else {}
        for rel in sorted(set(want) | set(have)):
            name = (dst / rel if rel else dst).relative_to(PLUGIN.parent).as_posix()
            if rel not in have:
                out.append(f"missing: {name}")
            elif rel not in want:
                out.append(f"extra: {name}")
            elif want[rel] != have[rel]:
                out.append(f"differs: {name}")
    # an agent or skill file in the plugin that no source names
    for folder, known in (("agents", {f"{n}.md" for n in AGENTS}), ("skills", set(SKILLS) | set(HAND_SKILLS))):
        d = PLUGIN / folder
        for p in sorted(d.iterdir()) if d.exists() else []:
            if p.name not in known:
                out.append(f"extra: {p.relative_to(PLUGIN.parent).as_posix()}")
    # a file in plugin/templates/ that no source names
    tdir = PLUGIN / "templates"
    wanted = set(TEMPLATE_FILES) | HAND_TEMPLATES
    for rel in sorted(_tree(tdir)) if tdir.exists() else []:
        if rel not in wanted and not any(rel.startswith(d + "/") for d in TEMPLATE_DIRS):
            out.append(f"extra: plugin/templates/{rel}")
    return out


def build() -> None:
    for src, dst in mapping():
        if dst.is_dir():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORED, "*.pyc"))
        else:
            shutil.copy2(src, dst)


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        diffs = differences()
        print("\n".join(diffs) if diffs else "plugin copies match the v1 sources")
        return 1 if diffs else 0
    if argv:
        print(__doc__)
        return 2
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
