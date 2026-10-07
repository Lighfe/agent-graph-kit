---
name: setup
description: Set up the agent-graph-kit loop in the current project. Use when the owner types /agk:setup, or asks to install the kit into a project. Copies the process documents and the Codex QA launcher, writes `AGENTS.md`, `CLAUDE.md` and the `.gitignore` lines, and reports the manual steps that are left.
---

# Setup

This skill turns a mostly fresh project into a project in which the loop can run. It never overwrites a file and never writes outside the project root.

## Steps

1. Ask the owner for two values:
   - the project name (the first line of `AGENTS.md`)
   - the test command of the project (for example `uv run --with pytest pytest`)
2. Run the script from this skill's folder. The project root is the git root of the project (the current directory when it is that root):

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/setup.py" --root "<project root>" --name "<project name>" --test-command "<test command>"
   ```

3. Show the owner the output of the script, and name what is left:
   - each file that already existed with other content: the script did not touch it and printed a diff. The owner decides whether to merge by hand.
   - each manual check with the status `MISSING` or `CHECK BY HAND`, with its fix. The three Auto mode entries are always `CHECK BY HAND`: the owner sets them in `/permissions`, in the Auto mode tab. This skill never sets them.
   - when `.claude/settings.json` could not be merged (invalid JSON or a symlink), the permission lines the owner adds by hand

A missing manual entry does not make the script fail: it never blocks the install.

## What the script writes

- `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/`, `scripts/qa-codex`, `scripts/codex_exec.py`, `scripts/qa-result.schema.json`, `AGENTS.md`, and `CLAUDE.md` (exactly the line `@AGENTS.md`; a `CLAUDE.md` with other content is not changed, and a diff is printed)
- `.gitignore`: created with the lines `.claude/settings.local.json` and `__pycache__/`. When it exists, only the missing lines are added and every existing line is kept
- `.agent-graph-kit.lock`: the sha256 of each file as copied (a later drift check reads it)
- `.claude/settings.json` with only the `permissions` block, when the file does not exist. When it exists (for example after `claude plugin install --scope project`), the script merges the missing `permissions.allow` and `permissions.deny` lines into it and keeps every other entry. The plugin delivers the hooks.

## Lovable lane

The Lovable frontend lane is a separate, optional step. Do it after setup. The base kit works without it. This skill does not do it.
