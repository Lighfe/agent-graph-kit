---
name: update
description: Update the copied kit files of this project after a plugin update. Use when the owner types /agk:update, or asks whether the copied kit files are up to date after a plugin update. Runs the safe part of the update and names the files that still need a decision.
---

# Update

After `claude plugin update` and a restart, the copied kit files (`docs/process.md`, `docs/team/*`, and others) stay as copied. This skill takes the new plugin files that the project did not change, and names the files that need a decision. It uses `drift.py` from the `drift` skill, called with `${CLAUDE_SKILL_DIR}`, so the owner types no plugin cache path.

## Steps

The project root is the git root of the project (the current directory when it is that root).

1. Run `drift.py` read only, and show a short summary with the number of files per state (for example `2 newer in the plugin, 5 unchanged`):

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/../drift/drift.py" --root "<project root>"
   ```

   When the script prints `not set up:`, tell the owner to run `/agk:setup` first, and stop.

2. Run the safe update. It replaces each file that is `newer in the plugin`, and removes each `dropped (gone from both)` entry from the lock:

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/../drift/drift.py" --root "<project root>" --update
   ```

   Report each `updated: <path>` line and each `removed from the lock: <path>` line. "Nothing to update" is a normal answer: say it plainly.

3. Name each `not touched (changed in both): <path>` file. The plugin and the project both changed it, so it needs a merge. The merge step is not part of this skill yet: say that the file stays as it is and shows `changed in both` again next time.

4. When no file is `changed in both`, say that the update is complete. Name the files that changed (`updated:` lines, and `.agent-graph-kit.lock`) so the owner can commit them. Do not commit and do not push.

## In-session result

The engineer ran `drift.py --update` inside a Claude Code session on a synthetic project (a temporary folder with a lock file). The guard hooks and the Auto mode classifier did not deny it. The files are in `docs/` and `scripts/`, not in the `.claude` folder.

If a deny occurs anyway (a guard hook or the Auto mode classifier), do not try another way around it. Print the one command for a terminal outside Claude Code, with the real path of this skill's folder:

```bash
uv run --script "<skill folder>/../drift/drift.py" --root "<project root>" --update
```

Tell the owner to run `/agk:update` again afterwards.

## Not in this skill

- Merges of `changed in both` files, `--accept`, the final checks and the commit offer
- `claude plugin update`: the new version loads only after a restart
- `AGENTS.md` and the project settings file: this skill never touches them
