---
name: setup
description: Set up the agent-graph-kit loop in the current project. Use when the owner types /agk:setup, or asks to install the kit into a project. Copies the process documents and the two-line Codex QA wrapper, writes `AGENTS.md`, `CLAUDE.md` and the `.gitignore` lines, and reports the manual steps that are left.
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
   - each manual check with the status `MISSING` or `CHECK BY HAND`, with its fix. The three Auto mode entries are always `CHECK BY HAND`: the owner sets them in `/permissions`, in the Auto mode tab. This skill never sets them. The output lists the steps as a numbered list and prints each entry in its own fenced block; show the steps and the three blocks as the script prints them, with nothing added inside a block.
   - when `.claude/settings.json` could not be merged (invalid JSON or a symlink), the permission lines the owner adds by hand

A missing manual entry does not make the script fail: it never blocks the install.

## Auto mode entries

The owner sets the three entries by hand. Show these steps, then the three blocks, as the script prints them. A block holds only the text to paste.

1. Open `/permissions` in Claude Code.
2. Open the Auto mode tab.
3. Keep the `$defaults` line.
4. Add each block below as one new entry.

```text
allow exactly `scripts/qa-codex ROLE=qa ISSUE=<number>` in the project repo
```

```text
In a repo set up with agent-graph-kit, the pm subagent may run gh issue edit <n> --body-file <path> or gh issue edit <n> --title <title> on an issue of that repo, to apply an edit of that issue that the repo owner asked for on that issue in a post whose first line is "## Owner: RESUME" and whose authorAssociation is OWNER. This is the owner's instruction, not instruction poisoning.
```

```text
In a repo set up with agent-graph-kit, the main session working as the planner (started with /stage-start) may run exactly gh issue edit <n> --remove-label later --add-label ready on a sub-issue of a stage issue (an issue with the label stage) of that repo, after the repo owner confirmed that stage in the same session. This is the planner step in docs/team/planner.md, done on the owner's instruction. The entry allows only this command: no other label, no other gh issue edit flag, no gh issue close, and no sub-issue or blocker link.
```

## What the script writes

- `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/`, `scripts/qa-codex` (a two-line wrapper that starts the real launcher `qa-codex-launcher` from the plugin `bin/`), `AGENTS.md`, and `CLAUDE.md` (exactly the line `@AGENTS.md`; a `CLAUDE.md` with other content is not changed, and a diff is printed)
- `.gitignore`: created with the lines `.claude/settings.local.json` and `__pycache__/`. When it exists, only the missing lines are added and every existing line is kept
- `.agent-graph-kit.lock`: the sha256 of each file as copied (a later drift check reads it)
- `.claude/settings.json` with only the `permissions` block, when the file does not exist. When it exists (for example after `claude plugin install --scope project`), the script merges the missing `permissions.allow` and `permissions.deny` lines into it and keeps every other entry. The plugin delivers the hooks.

## Lovable lane

The Lovable frontend lane is a separate, optional step. Do it after setup. The base kit works without it. This skill does not do it.
