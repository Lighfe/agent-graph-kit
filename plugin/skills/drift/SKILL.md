---
name: drift
description: Show which copied kit files changed in this project or in the plugin. Use when the owner types /agk:drift, or asks whether the kit files in the project are up to date. Read-only unless the owner adds --update or --accept.
---

# Drift

This skill compares each file that `/agk:setup` copied with the file in the project and with the plugin template. Plain `/agk:drift` is read-only: it writes nothing and overwrites nothing.

## Steps

1. Run the script from this skill's folder. The project root is the git root of the project (the current directory when it is that root):

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/drift.py" --root "<project root>"
   ```

2. Show the owner the output. Each line is `<state>: <path>`:
   - `unchanged`: the project file and the plugin template are as copied
   - `changed in this project`: the owner edited the file; the plugin did not change
   - `newer in the plugin`: the plugin has a new version; the project file is as copied
   - `changed in both`: both changed; `/agk:update` proposes a merge and the owner answers
   - `deleted from this project`: the file is gone from the project, and the plugin still has a template for it
   - `dropped (gone from both)`: the file is gone from the project and the plugin has no template for it. `--update` removes such an entry from the lock
   - `no longer in the plugin`: the plugin has no template for this path any more
3. When the script prints `not set up:` (exit code 1), tell the owner to run `/agk:setup` first.

`AGENTS.md` is filled in with project facts at setup, so it is the only file compared with the lock only: `unchanged` or `changed in this project`. `CLAUDE.md` is compared with its template `CLAUDE.md.tmpl` like the other files.

## Update with `--update`

Add `--update` to take the new plugin files:

```bash
uv run --script "${CLAUDE_SKILL_DIR}/drift.py" --root "<project root>" --update
```

Rule: only files that are `newer in the plugin` are replaced by the new template, and their lock entries get the new sha256. A file the project changed is never overwritten. The output is `updated: <path>` per replaced file and `not touched (changed in both): <path>` per `changed in both` file; every other line is as without the flag. Each lock entry in the state `dropped (gone from both)` is deleted, and the script prints `removed from the lock: <path>` for it. "Nothing updated" is a normal answer when no file is `newer in the plugin`. Nothing else changes: no other file and no other lock entry, and `AGENTS.md` is never written. `/agk:update` is the route for the whole update (it calls `--update`, proposes the merges, calls `--accept`); `--update` and `--accept` are the low-level commands. On a missing or invalid lock the script prints `not set up:`, exits with 1 and writes nothing.

Writes into `.claude/` are denied inside a Claude Code session, so tell the owner to run the `--update` command in a terminal outside Claude Code.

## Accept with `--accept`

After a `changed in both` file is merged (`/agk:update` does this after the owner's yes), record it in the lock:

```bash
uv run --script "${CLAUDE_SKILL_DIR}/drift.py" --root "<project root>" --accept <path> [<path> ...]
```

Arguments: one or more paths as written in the lock. Each lock entry gets the sha256 of the current plugin template (`CLAUDE.md.tmpl` for `CLAUDE.md`). The output is `accepted: <path>` per path. No project file and no other lock entry changes. A path is refused, in this order, when it is `AGENTS.md`, not in the lock, without a plugin template, or not in the project. When any path is refused, nothing is written and the exit code is 1. `--accept` and `--update` cannot be used together (exit code 2). The same rule holds: tell the owner to run it in a terminal outside Claude Code.

This skill does not merge or print a diff. The merge proposal is in the skill `update` (`/agk:update`).
