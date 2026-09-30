# agent-graph-kit

A reusable set-up for AI-native development with several agents (Graph Engineering).

Target architecture:

- The Claude Code main session is the orchestrator.
- Workers are Claude Code subagents, Codex CLI, and Lovable (MCP).
- Jev (TypeSafe AI) makes fast, typed decisions at the handoffs between workers.

Current bootstrap (v1): the orchestrator runs the loop in [docs/process.md](docs/process.md). The PM and the engineer are Claude subagents. Hooks in `.claude/hooks/` check each role launch and each `gh issue close`, and deny the call when the issue is not in the right state. QA runs through the Codex QA launcher `scripts/qa-codex` (`codex exec` in a sandbox). When Codex is not available, the Claude subagent `qa-engineer` is the fallback. Issues with `Lane: frontend` go to the Lovable frontend lane: the subagent `frontend-engineer` drives Lovable through MCP, and the code lives in the `frontend/` submodule. Jev is not part of v1.

Later, this repo becomes a Claude Code plugin.

## Status

v1: guard hooks, Codex QA with the Claude fallback, and the Lovable frontend lane. You set up the kit in a project by hand with the steps below. The first project that uses these steps is the paint-math demo.

## Set up the kit in a project

Run these steps in the root of the new project (the git root; see "Project repo" for a new, empty repo), in a terminal outside Claude Code. Do not run them from a Claude Code session: the kit's guard hooks deny the `cp` of `.claude/settings.json` (`G8:`) and every command that names `scripts/qa-codex` (`G1:`), and the Auto mode classifier denies the copy into `.claude/` and the `git submodule add`. The examples use a synthetic project `example-app` at `/home/you/projects/example-app` and a clone of this repo next to it at `../agent-graph-kit`.

### Prerequisites

- `gh`, logged in (`gh auth status`)
- `uv` (the guard hook runs with `uv run --script`, and so does the Codex QA launcher)
- Codex CLI, logged in (`codex login`)
- Frontend lane only: the Claude Code plugin `lovable`. The tool names in `.claude/agents/frontend-engineer.md` depend on it.
- Frontend lane only: the tools for the install command of `frontend/`. The QA pre-step picks it from the lockfile in `frontend/`: with an npm lockfile (`package-lock.json` or `npm-shrinkwrap.json`) it runs `npm ci`, else with a bun lockfile (`bun.lock` or `bun.lockb`) it runs `bun install --frozen-lockfile`, else it posts `## QA: UNAVAILABLE`. So an npm frontend needs `npm` and `npx`, and a bun frontend needs `bun` on `PATH` (it no longer needs `npx`: its browser step runs through `bun`)
- Frontend lane only: a Playwright dependency in the frontend: `@playwright/test` as a dev dependency in `frontend/package.json` and its lockfile (see "Frontend lane" below). Without it, the QA pre-step posts `## QA: UNAVAILABLE`

### Project repo

The project is a git repo with a GitHub remote `origin` and a branch `main`. The loop keeps its tasks in the GitHub issues of that repo, and the `gh` commands below act on it. To start from a new, empty GitHub repo, create it on GitHub (or with `gh repo create`), then clone it and put the clone on `main`:

```bash
git clone https://github.com/<owner>/example-app.git
cd example-app
git checkout -B main   # an empty clone starts on the branch of init.defaultBranch, which may not be main
```

The clone has no commit yet. The first commit and push are in "Start".

The repo must be owned by your GitHub user account, and `gh` must be logged in as that user. The hooks and `scripts/qa-codex` count only issue comments whose `authorAssociation` is `OWNER`; other comments are ignored, so in a public repo a stranger's comment cannot resume, pass, block or close an issue. A comment without author data is an error: the guard denies the call. The agents and hooks post with your `gh` login, so their comments count. Organization-owned repos are not supported yet: there, the owner's comments are not `OWNER` ([#75](https://github.com/Lighfe/agent-graph-kit/issues/75)).

### Copy

Copy these files and folders from this repo into the new project, with the same paths:

- `AGENTS.md`, `CLAUDE.md`
- `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/`
- `.claude/agents/`, `.claude/hooks/`, and from `.claude/settings.json` the `hooks` block and the `permissions` block (the `allow` and the `deny` rules)
- `scripts/qa-codex` (the Codex QA launcher; it must stay executable), `scripts/codex_exec.py`, `scripts/qa-result.schema.json`
- `.agents/skills/codex-review/`
- the symlink `.claude/skills` -> `.agents/skills`

Copy example, run in the root of the new project:

```bash
KIT=../agent-graph-kit
mkdir -p docs .claude .agents/skills scripts
cp "$KIT/AGENTS.md" "$KIT/CLAUDE.md" .
cp -r "$KIT/docs/process.md" "$KIT/docs/task-template.md" "$KIT/docs/team" "$KIT/docs/checks" docs/
cp -r "$KIT/.claude/agents" "$KIT/.claude/hooks" .claude/
cp -r "$KIT/.agents/skills/codex-review" .agents/skills/
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

- `AGENTS.md`: the first line (`# <project name>`), the project description (replace the two kit sentences at the top: "This repo will become a Claude Code plugin ..." and "Now, it is in bootstrap."), and the test command (the line `Test command: ...`)
- `AGENTS.md`: remove or reword the lines that are only true for this kit repo: `docs/specs/` - the design of the kit (under "Documents"), the key name `TYPESAFE_API_KEY` (under "Public repo"), and the line about `docs/references/local/` (under "Public repo")
- Frontend lane only: the `frontend/` submodule (see "Frontend lane" below) and the `frontend` lane. Add the line `Lovable project: <id>` to `AGENTS.md`; the `frontend-engineer` reads the Lovable project id from it. Without a Lovable project, the PM must not use `Lane: frontend`.

### Codex trust entry

Add the trust entry for the project to `$HOME/.codex/config.toml` (spec 6.2). Otherwise Codex writes it there during the loop. The path is the git root of the project (`git rev-parse --show-toplevel`), as an absolute path:

```toml
[projects."/home/you/projects/example-app"]
trust_level = "trusted"
```

### Frontend lane (optional)

Frontend lane only. No MCP tool can make the GitHub connection of a Lovable project, so you do these steps by hand (spec 9.1):

1. Create the Lovable project.
2. Connect the Lovable workspace to GitHub (one time per workspace).
3. Connect the project: Project settings -> Git -> GitHub -> Connect.
4. Make the new GitHub repo of the Lovable project public.
5. Add it as the `frontend/` submodule, tracking `main`:

   ```bash
   git submodule add -b main <Lovable repo URL> frontend
   ```

6. Add Playwright as a dev dependency through Lovable (QA needs it for the headless browser). Send the Lovable project a chat prompt, for example:

   > Add `@playwright/test` as a dev dependency, update the lockfile, do not add tests.

   Then check in the Lovable GitHub repo that the new commit changed `package.json` (`@playwright/test` under `devDependencies`) and the lockfile (`bun.lock` or `package-lock.json`).
7. Bump the `frontend` submodule in the project to that commit, and commit the new pointer. The QA worktree checks out the commit that the submodule records, not the newest commit of the Lovable repo:

   ```bash
   git submodule update --remote frontend
   git add frontend
   git commit -m "Bump frontend to the commit with the Playwright dependency"
   ```

Nobody edits `frontend/` locally. All frontend changes go through Lovable.

Lovable can pause a message and wait for input. The `frontend-engineer` answers a plan or a question itself: it checks Lovable's plan against the issue and approves or corrects it. A credit or spend-limit check-in can only be answered by a person in the Lovable editor. Then the engineer posts `## Engineer: BLOCKED`, and the issue is escalated to you. Check that the Lovable workspace has enough credits before a frontend issue gets the label `ready`.

The QA pre-step installs the frontend dependencies with the install command that follows the lockfile in `frontend/`: an npm lockfile (`package-lock.json` or `npm-shrinkwrap.json`) gives `npm ci`, else a bun lockfile (`bun.lock` or `bun.lockb`) gives `bun install --frozen-lockfile`, else the result is `## QA: UNAVAILABLE`. If both kinds exist, `npm ci` runs. A bun frontend (Lovable projects often use bun) needs `bun` on `PATH`; without it, the result is `## QA: UNAVAILABLE`.

The frontend needs a Playwright dependency: `playwright` or `@playwright/test` (as a dev dependency: step 6 above) in `dependencies` or `devDependencies` of `frontend/package.json`, and in its lockfile. Without it, the result is `## QA: UNAVAILABLE`, and nothing is installed. After the install, the pre-step installs the browser with the Playwright CLI of that dependency, through the package manager of the lockfile: `npx --no playwright install chromium` (npm lockfile) or `bun x --no-install playwright install chromium` (bun lockfile). `--no` and `--no-install` stop a registry fetch, so the browser version follows the frontend's lockfile and nothing is fetched from the registry for it. A bun frontend does not need `npx`.

### Labels

```bash
gh label create ready --description "Orchestrator may work on this issue" --color 1D76DB --force
gh label create needs-owner --description "Escalated: the orchestrator waits for the owner" --color FBCA04 --force
gh label create later --description "Out of scope for the current implementation" --color BFD4F2 --force
gh label create waiting --description "Parked: waits until its blocker issue is closed" --color C5DEF5 --force
```

`--force` updates a label that already exists instead of failing.

### Start

1. Commit the copied and adjusted files (with `.gitignore` and, for the frontend lane, `.gitmodules` and `frontend`), and push them to `main` on GitHub (`git push -u origin main` for the first push).
2. Open the project folder in Claude Code and trust the folder. The project allow rules for `scripts/qa-codex` and for `gh issue close` apply only in a trusted folder (spec 5.9). The hooks apply from the next tool call after `.claude/settings.json` is in place.
3. Final step: run the acceptance test in [docs/checks/hook-activation.md](docs/checks/hook-activation.md) before the first issue gets the label `ready`. If a step fails, the loop does not start.

## Update the kit in a project

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

## Background

The kit builds on the workflow from the DataTalksClub [AI Dev Tools Zoomcamp](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp) by Alexey Grigorev.

## Design

- Accepted design: [docs/specs/](docs/specs/)
- Historical input: [docs/archive/](docs/archive/)
- Development process of this repo: [docs/process.md](docs/process.md)
