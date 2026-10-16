---
name: drift
description: Show which copied kit files changed in this project or in the plugin. Use when the owner types /agk:drift, or asks whether the kit files in the project are up to date. Read-only.
---

# Drift

This skill compares each file that `/agk:setup` copied with the file in the project and with the plugin template. It writes nothing and overwrites nothing.

## Steps

1. Run the script from this skill's folder. The project root is the git root of the project (the current directory when it is that root):

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/drift.py" --root "<project root>"
   ```

2. Show the owner the output. Each line is `<state>: <path>`:
   - `unchanged`: the project file and the plugin template are as copied
   - `changed in this project`: the owner edited the file; the plugin did not change
   - `newer in the plugin`: the plugin has a new version; the project file is as copied
   - `changed in both`: both changed; the owner merges by hand
   - `deleted from this project`: the file is gone from the project, and the plugin still has a template for it
   - `dropped (gone from both)`: the file is gone from the project and the plugin has no template for it. The owner can delete such an entry from `.agent-graph-kit.lock` by hand
   - `no longer in the plugin`: the plugin has no template for this path any more
3. When the script prints `not set up:` (exit code 1), tell the owner to run `/agk:setup` first.

`AGENTS.md` is filled in with project facts at setup, so it is the only file compared with the lock only: `unchanged` or `changed in this project`. `CLAUDE.md` is compared with its template `CLAUDE.md.tmpl` like the other files.

The skill does not merge, update or print a diff. The owner decides what to do with each answer.
