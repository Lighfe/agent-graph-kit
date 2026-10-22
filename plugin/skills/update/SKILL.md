---
name: update
description: Update the copied kit files of this project after a plugin update. Use when the owner types /agk:update, or asks whether the copied kit files are up to date after a plugin update. Runs the safe part of the update, proposes a merge for each file that changed in both, and finishes with the checks and a commit offer.
---

# Update

After `claude plugin update` and a restart, the copied kit files (`docs/process.md`, `docs/team/*`, and others) stay as copied. This skill takes the new plugin files that the project did not change, proposes a merge for each file that both sides changed, and finishes the update. It uses `drift.py` from the `drift` skill, called with `${CLAUDE_SKILL_DIR}`, so the owner types no plugin cache path.

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

3. For each `not touched (changed in both): <path>` file, propose a merge (the section "Merge proposal" below). When no file is `changed in both`, go to step 5.

4. Write the merges the owner agreed to (see "Merge proposal"), then run the checks:

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/../drift/drift.py" --root "<project root>" --accept <path> [<path> ...]
   uv run --script "${CLAUDE_SKILL_DIR}/../drift/drift.py" --root "<project root>"
   uv run --script "${CLAUDE_SKILL_DIR}/../hook-activation-check/check.py" --root "<project root>"
   ```

   `--accept` gets the merged paths only, never a path with a "no". The second call is the `drift.py` read-only run: no `changed in both` may be left for an accepted file. The third call is the hook activation check (`/agk:hook-activation-check`). Show its output. Show each `FAILED` line to the owner and do not hide it. When no file was written, skip these three calls.

5. Say that the update is complete, or which files still show `changed in both` (the ones with a "no"). Name the files that changed (`updated:` lines, the merged files and `.agent-graph-kit.lock`).

6. Offer one commit that holds the changed files and `.agent-graph-kit.lock` together. Commit only when the owner says yes. Never push.

## Merge proposal

For each `changed in both` file, read three things: the project file, the plugin template (`${CLAUDE_SKILL_DIR}/../../templates/<path>`, and `CLAUDE.md.tmpl` for `CLAUDE.md`) and the diff between them. The lock holds only a sha256, so there is no common base: the diff shows two versions, not who changed what. Judge each part of the diff, and give one sentence of reason for each. Every part is one of three kinds:

- a kit change to carry into the project file (a new or reworded rule in the template)
- a project change made on purpose to keep (a project-specific rule or name)
- a template line that names a file or command the project does not have (for example `scripts/build_plugin.py`): leave it out or reword it

Start each proposal with a one-line recommendation: take the template, keep the project file, or merge. Then list the parts to carry, the parts to keep and the lines to leave out or reword, each with its reason.

The owner answers for each file: yes, no, or a change.

- Write a file only after a yes (or after the owner's change is applied and the owner agreed to the result). Never write a file before the answer
- On a no, the file and its lock entry stay as they are. Say that the file shows `changed in both` again at the next update
- Never merge or accept without the answer

## In-session result

The engineer ran `drift.py --update` inside a Claude Code session on a synthetic project (a temporary folder with a lock file). The guard hooks and the Auto mode classifier did not deny it. The files are in `docs/` and `scripts/`, not in the `.claude` folder.

If a deny occurs anyway (a guard hook or the Auto mode classifier), do not try another way around it. Print the one command for a terminal outside Claude Code, with the real path of this skill's folder:

```bash
uv run --script "<skill folder>/../drift/drift.py" --root "<project root>" --update
```

Tell the owner to run `/agk:update` again afterwards.

## Not in this skill

- `claude plugin update`: the new version loads only after a restart
- `AGENTS.md` and the project settings file (`.claude/settings.json`): this skill never touches them, also not when the owner asks in a merge. `drift.py` does not compare `AGENTS.md`, and the plugin delivers the hooks
- A push: the skill never pushes
