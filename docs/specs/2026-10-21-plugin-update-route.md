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

The README section "Update a plugin project", the drift skill and the living spec describe one complete route:

1. Update the plugin, and name the template folder (`<plugin cache>/agk/<version>/templates/`)
2. `/agk:drift`
3. In a terminal: `drift.py --update` (says that "nothing to update" is a normal answer; it also clears `dropped` entries)
4. Merge each `changed in both` file by hand; reword or remove a template line that names a file the project does not have
5. `drift.py --accept` for each merged file
6. `/agk:drift` again: no `changed in both`, no `dropped`
7. Commit the files and the lock together

## Not in this spec

- A three-way merge or a diff in the script
- Automatic accept of a file
