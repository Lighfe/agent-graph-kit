# Plugin update skill: spec

## Problem

A project that uses the kit as a plugin must update twice: the plugin, then the kit files that `/agk:setup` copied into the project (`docs/process.md`, `docs/team/*`, `scripts/qa-codex`, and others). The owner reports that this is too much work (found again in Lighfe/quack-rl, update from plugin 0.1.0 to 0.1.5). The effort sits in these places:

1. Seven README steps in two sections. The first section shows only the two `claude plugin` commands, so a reader can stop too early.
2. The owner must find the plugin cache folder with its version number to call `drift.py`.
3. The README says to run `drift.py --update` in a terminal outside Claude Code.
4. The owner compares each `changed in both` file by hand with `diff`, decides what to keep, and edits the file.
5. The owner must then run `drift.py --accept`, `/agk:drift` again and `/agk:hook-activation-check`, and commit.
6. Many of the hand merges are not caused by the owner's edits. The role files that go to the project name commands that exist only in the kit repo (`scripts/build_plugin.py`, `scripts/bump_plugin_version.py`). The owner must remove these lines by hand each time.
7. The README still holds a second route (copy from a clone of the kit) with its own update steps. It adds noise and "compare the folders" text.

The goal: the owner updates the plugin, restarts Claude Code, types one command, and answers yes or no. The owner does not compare files and does not edit files.

## Behavior

### `/agk:update`

A new skill in `plugin/skills/update/SKILL.md`. The owner types it in the project, in a Claude Code session, after the plugin update and a restart. The skill works through these steps and stops with a clear message when a step cannot run:

1. Run `drift.py` (read only) and show the result in a short summary: how many files per state.
2. Run `drift.py --update` from the skill folder (`${CLAUDE_SKILL_DIR}`), so the owner never types a plugin cache path. This replaces the files that are `newer in the plugin` and removes `dropped` lock entries. "Nothing to update" is a normal answer.
3. For each `changed in both` file, propose a merge (see "Merge proposal"). The owner answers per file.
4. After the owner accepted the merges: write the merged files, run `drift.py --accept` for them, run `drift.py` again, and run the hook activation check.
5. Offer a commit that holds the changed files and `.agent-graph-kit.lock` together. The skill commits only when the owner says yes. It never pushes.

In-session writes: the README says `--update` needs a terminal outside Claude Code because the guard hooks and the Auto mode classifier deny writes into `.claude/`. The copied files are in `docs/` and `scripts/`, not in `.claude/`, and the command line of `drift.py` names none of the guarded words. So the update may work inside a session. The engineer finds out what is really denied. If the command is denied, the skill prints the one command for the owner to run in a terminal outside Claude Code and says to run `/agk:update` again afterwards. The skill never works around a deny.

### Merge proposal

For a `changed in both` file, the skill reads three things: the project file, the plugin template (`${CLAUDE_SKILL_DIR}/../../templates/<path>`), and the diff between them. The lock holds only a sha256, so there is no common base. The skill therefore reads the diff as two kinds of change and says which kind each hunk is, with a reason:

- a change the kit made (new or reworded rule): carry it into the project file
- a change the project made on purpose (a project-specific rule or name): keep it
- a template line that names a file or command the project does not have (for example `scripts/build_plugin.py`): leave it out, or reword it

The proposal for each file has: a one-line recommendation (take the template, keep the project file, or merge), the hunks it would apply, and the hunks it would keep, each with one sentence of reason. The owner answers yes, no, or gives a change. On "no" the file stays as it is and the lock entry stays: it shows `changed in both` again next time, and the skill says so. A file is written only after the owner agreed to its proposal.

`AGENTS.md` and `.claude/settings.json` are not part of this: `drift.py` never compares or writes `AGENTS.md`, and the plugin delivers the hooks. The skill does not touch them.

### Role files for plugin projects

The role files in `docs/team/` are copied into plugin projects. They must not tell a plugin project to run something that only the kit repo has. Today `planner.md` names `scripts/build_plugin.py --release-status` (stage review) and `orchestrator.md` names `scripts/bump_plugin_version.py` ("Stage end", step 3). The kit repo keeps both steps. A test fails when a role file in `plugin/templates/docs/team/` names a script path that `/agk:setup` does not copy. This is the content of issue #251; the way (move the steps to one kit-only place, or cut them while building the template) is the PM's choice.

### README

- The README describes only the plugin route. The copy-from-a-clone route (setup and update) moves word for word to `docs/archive/` (issue #249)
- One section "Update a plugin project" holds the whole update: the two `claude plugin` commands, the restart, `/agk:update`, and the "already at the latest version" hint (remove the cached copy, then install again). It says why the two commands are not enough: they change the hooks, agents, skills and `bin/`, but the copied files stay as copied until the update skill runs
- The old seven-step text with `diff` and `--accept` by hand goes. `drift.py --update` and `--accept` stay in the drift skill as the low-level commands

## Not in this spec

- Running `claude plugin update` from inside the skill. The new version loads only after a restart, so the owner runs the two commands and restarts
- A three-way merge in `drift.py`, or a stored copy of the old template as a merge base
- Automatic merge or accept without the owner's answer
- Merging `AGENTS.md` or `.claude/settings.json`
- A release step for plugin projects
- The release of the plugin: the orchestrator bumps the version at the end of the stage as usual

## Coverage by issue

| Part | Issue |
|---|---|
| `/agk:update`: summary, safe update, in-session run and the fallback | skill issue 1 |
| Merge proposal, per-file owner answer, accept, final checks, commit offer | skill issue 2 |
| Role files without kit-only commands, test | #251 |
| README: only the plugin route | #249 |
| README: one update section | #250 |
