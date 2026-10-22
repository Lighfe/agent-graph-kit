Archived on 2026-10-22: the manual route of the README (a project that copied the kit from a clone of this repo). The README now describes only the plugin route (issue #249).

The text below is word for word what was removed. Each part starts with its source section.

<!-- from: Set up the kit in a project (heading, intro, Prerequisites) -->
## Set up the kit in a project

This is the manual route (v1). For v2 use the section "Start a new project" above.

Run these steps in the root of the new project (the git root; see "Project repo" for a new, empty repo), in a terminal outside Claude Code. Do not run them from a Claude Code session: the kit's guard hooks deny the `cp` of `.claude/settings.json` (`G8:`), and the Auto mode classifier denies the copy into `.claude/` and the `git submodule add`. The examples use a synthetic project `example-app` at `/home/you/projects/example-app` and a clone of this repo next to it at `../agent-graph-kit`.

### Prerequisites

The prerequisites are in "Prerequisites" of [Start a new project](#start-a-new-project), including the optional block for the frontend lane. The frontend lane also needs a Playwright dependency in the frontend: `@playwright/test` as a dev dependency in `frontend/package.json` and its lockfile (see "Frontend lane" below). Without it, the QA pre-step posts `## QA: UNAVAILABLE`.

<!-- from: Set up the kit in a project, subsections Copy and Adjust -->
### Copy

Copy these files and folders from this repo into the new project, with the same paths:

- `AGENTS.md`, `CLAUDE.md`
- `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/`
- `.claude/agents/`, `.claude/hooks/`, and from `.claude/settings.json` the `hooks` block and the `permissions` block (the `allow` and the `deny` rules)
- `scripts/qa-codex` (the Codex QA launcher; it must stay executable), `scripts/codex_exec.py`, `scripts/qa-result.schema.json`
- `.agents/skills/codex-review/`, `.agents/skills/stage-start/`
- the symlink `.claude/skills` -> `.agents/skills`

Copy example, run in the root of the new project:

```bash
KIT=../agent-graph-kit
mkdir -p docs .claude .agents/skills scripts
cp "$KIT/AGENTS.md" "$KIT/CLAUDE.md" .
cp -r "$KIT/docs/process.md" "$KIT/docs/task-template.md" "$KIT/docs/team" "$KIT/docs/checks" docs/
cp -r "$KIT/.claude/agents" "$KIT/.claude/hooks" .claude/
cp -r "$KIT/.agents/skills/codex-review" "$KIT/.agents/skills/stage-start" .agents/skills/
cp -p "$KIT/scripts/qa-codex" "$KIT/scripts/codex_exec.py" "$KIT/scripts/qa-result.schema.json" scripts/
cp "$KIT/.claude/settings.json" .claude/settings.json   # only if the project has no .claude/settings.json yet
ln -s ../.agents/skills .claude/skills
test -x scripts/qa-codex && echo "launcher is executable"
```

The file `.claude/settings.json` of this repo holds only the two blocks, so the `cp` above copies exactly them.

If the new project already has its own `.claude/settings.json`: do not overwrite it. Skip the `cp` of the settings file and merge the two blocks into the existing file by hand: add the `allow` and `deny` rules to its `permissions` block, and add every entry of the kit's `hooks` block to its `hooks` block. Today these are `PreToolUse` (the guard hook), `PermissionDenied` (runs `.claude/hooks/not_started.py`, which marks a launch that was denied before it ran) and `SubagentStop` (runs `.claude/hooks/outage_stop.py`, which marks a launch that was stopped by an auto mode outage). Check afterwards that each event name in the kit's `hooks` block is also in yours.

If the new project already has a `.claude/skills` folder: move its skills into `.agents/skills/` first, then delete the empty `.claude/skills` folder, then run `ln -s`. If the folder still exists, `ln -s` creates the link inside that folder instead of replacing it.

Also add these lines to the `.gitignore` of the project:

```gitignore
.claude/settings.local.json
__pycache__/
```

`.claude/settings.local.json` is local only. `cp -r` also copies the kit's local `__pycache__/` folders (in `.claude/hooks/` and `.agents/skills/codex-review/`); do not commit them.

### Adjust

- `AGENTS.md`: the first line (`# <project name>`), the project description (replace the kit sentence at the top: "This repo is the agent-graph-kit, a Claude Code plugin ..."), and the test command (the line `Test command: ...`)
- `AGENTS.md`: remove or reword the lines that are only true for this kit repo: `docs/specs/agent-graph-kit.md` - the living behavior spec: how the kit behaves now (under "Documents"), the key name `TYPESAFE_API_KEY` (under "Public repo"), and the line about `docs/references/local/` (under "Public repo")
- Frontend lane only: the `frontend/` submodule (see "Frontend lane" below) and the `frontend` lane. Add the line `Lovable project: <id>` to `AGENTS.md`; the `frontend-engineer` reads the Lovable project id from it. Without a Lovable project, the PM must not use `Lane: frontend`.

<!-- from: Set up the kit in a project, subsections Labels and Start -->
### Labels

Create the four labels with the labels step of [Start a new project](#start-a-new-project).

### Start

1. Commit the copied and adjusted files (with `.gitignore` and, for the frontend lane, `.gitmodules` and `frontend`), and push them to `main` on GitHub (`git push -u origin main` for the first push).
2. Open the project folder in Claude Code and trust the folder. The project allow rules for `scripts/qa-codex` and for `gh issue close` apply only in a trusted folder ([G8](docs/specs/agent-graph-kit.md#g8-settings-protection)). The hooks apply from the next tool call after `.claude/settings.json` is in place.
3. Run `/agk:hook-activation-check` before the first issue gets the label `ready`. If a line says `FAILED`, the loop does not start.
4. Final step: plan the first stage with `/stage-start`, as in the last step of [Start a new project](#start-a-new-project).

<!-- from: Update the kit in a project -->
## Update the kit in a project

This is the route for a project that copied the kit from a clone of this repo. A project that has the kit as a plugin uses the section "Update a plugin project" below.

The kit still changes (new hooks, role rules, QA launcher fixes). A project does not get these changes by itself: you copy them in by hand. In the paint-math demo this was needed several times during the run, for example for the QA launcher fix of [#67](https://github.com/Lighfe/agent-graph-kit/issues/67) and [#68](https://github.com/Lighfe/agent-graph-kit/issues/68).

1. Update only while no role agent runs, for example while the issue waits for you with the label `needs-owner`. Run the steps in the root of the project, in a terminal outside Claude Code, for the same reason as in "Copy": the guard hooks and the Auto mode classifier deny writes into `.claude/` and commands that name `scripts/qa-codex`.
2. Pull the kit clone (`git -C ../agent-graph-kit pull`), then copy the kit files again. Leave out `AGENTS.md`, `CLAUDE.md` and `.claude/settings.json`: you adjusted them, so they get step 3.

   ```bash
   KIT=../agent-graph-kit
   cp -r "$KIT/docs/process.md" "$KIT/docs/task-template.md" "$KIT/docs/team" "$KIT/docs/checks" docs/
   cp -r "$KIT/.claude/agents" "$KIT/.claude/hooks" .claude/
   cp -r "$KIT/.agents/skills/codex-review" .agents/skills/
   cp -p "$KIT/scripts/qa-codex" "$KIT/scripts/codex_exec.py" "$KIT/scripts/qa-result.schema.json" scripts/
   test -x scripts/qa-codex && echo "launcher is executable"
   ```

   `cp` does not delete a file that the kit removed. Compare the folders (for example `diff -r "$KIT/.claude/hooks" .claude/hooks`) and delete such files by hand.
3. Compare the adjusted files with the kit and carry each kit change over by hand, keeping your adjustments: `diff "$KIT/AGENTS.md" AGENTS.md`, and `diff "$KIT/.claude/settings.json" .claude/settings.json` for the `hooks` and `permissions` blocks. A new hook event in the kit (for example `SubagentStop` from [#52](https://github.com/Lighfe/agent-graph-kit/issues/52)) does nothing until it is in the project's settings file.
4. Read the kit issues named in the new kit commits (`git -C ../agent-graph-kit log --oneline`) for new prerequisites, and check "Prerequisites" again.
5. Commit and push to `main`. Name the kit issues in the message, for example `git commit -m "Update QA launcher (agent-graph-kit #67, #68)"`.

The orchestrator closes an issue only if the SHA that QA verified is the current `HEAD`. Your update commit moves `HEAD`, so an issue that is in progress needs a new `## Engineer: DONE` and a new QA run that end at the new `HEAD`. In paint-math #1, the update commit moved `HEAD`, and the issue went through PM, engineer and QA again before it was closed.
