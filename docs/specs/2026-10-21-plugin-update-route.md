# Plugin update route: spec

## Problem

A project that uses the kit as a plugin updates in two steps: the plugin (`claude plugin update`), then the copied kit files (`/agk:drift`, `drift.py --update`). The second step is not complete (found in Lighfe/quack-rl issue 150, update from plugin 0.1.0 to 0.1.5):

1. `.agent-graph-kit.lock` holds the sha256 of the templates as copied at setup. `--update` writes the lock only for files that are `newer in the plugin`. When the owner merges a `changed in both` file by hand, nothing sets the lock entry to the new template. Drift reports `changed in both` again, on every run.
2. An entry `dropped (gone from both)` stays in the lock until the owner deletes it by hand. The README route does not say so.
3. `--update` can change nothing (no file is `newer in the plugin`). The README does not say that this is a normal answer.
4. The README does not say where the plugin templates are (versioned folder under the plugin cache).
5. A merged template line can name a file only the kit repo has (for example `scripts/build_plugin.py`). The route has no step to reword or remove such a line.

## Behavior

### `drift.py --accept <path>...`

For each path, the script sets the lock entry to the sha256 of the current plugin template. It does not change the project file.

- Allowed only for a path that is in the lock, has a plugin template, and exists in the project. `AGENTS.md` is refused: it has no template to compare (`CLAUDE.md` compares with `CLAUDE.md.tmpl` and is allowed)
- A refused path prints `cannot accept (<reason>): <path>`. If any path is refused, the script writes nothing and exits with 1
- Each accepted path prints `accepted: <path>`
- After the accept, drift reports the file as `changed in this project`, or as `unchanged` when the project file equals the template
- `--accept` cannot be combined with `--update`

### `drift.py --update` and `dropped` entries

`--update` also deletes every lock entry whose state is `dropped (gone from both)`, and prints `removed from the lock: <path>` for each. Plain drift (no flag) still writes nothing.

### Text

The README section "Update a plugin project" is one section. Its route is:

1. The two `claude plugin` commands, each in its own block, then a restart of Claude Code in the project
2. `/agk:update`: the owner reads each merge proposal, answers yes or no, and accepts or declines the commit (the skill runs the drift check, `drift.py --update`, the merge and `drift.py --accept`; see the update-skill spec)
3. One sentence on why the two commands are not enough: the plugin update does not touch the files that `/agk:setup` copied
4. The "already at the latest version" hint
5. A pointer to the drift skill: `drift.py --update` and `--accept` are the low-level commands that the skill uses. A terminal outside Claude Code is needed only when `/agk:update` reports a deny

The drift skill keeps the low-level route: the template folder (`<plugin cache>/agk/<version>/templates/`), "nothing to update" as a normal answer, `--update` clearing `dropped` entries, a hand merge of each `changed in both` file (reword or remove a template line that names a file the project does not have), `--accept` for each merged file, and a last `/agk:drift` with no `changed in both` and no `dropped`.

## Not in this spec

- A three-way merge or a diff in the script
- Automatic accept of a file
