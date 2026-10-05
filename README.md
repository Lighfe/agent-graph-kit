# agent-graph-kit

A reusable set-up for AI-native development with several agents (Graph Engineering).

Target architecture:

- The entry command sets the role of the Claude Code main session: `/goal …` makes it the orchestrator, `/stage-start` makes it the planner, and without a command it has no role (questions and reports, no loop, no planning).
- Workers are Claude Code subagents, Codex CLI, and Lovable (MCP).
- Jev (TypeSafe AI) makes fast, typed decisions at the handoffs between workers.

Current bootstrap (v1): the orchestrator runs the loop in [docs/process.md](docs/process.md). The PM and the engineer are Claude subagents. Hooks in `.claude/hooks/` check each role launch and each `gh issue close`, and deny the call when the issue is not in the right state. QA runs through the Codex QA launcher `scripts/qa-codex` (`codex exec` in a sandbox). When Codex is not available, the Claude subagent `qa-engineer` is the fallback. Issues with `Lane: frontend` go to the Lovable frontend lane: the subagent `frontend-engineer` drives Lovable through MCP, and the code lives in the `frontend/` submodule. Jev is not part of v1.

Later, this repo becomes a Claude Code plugin.

## Status

v1: guard hooks, Codex QA with the Claude fallback, and the Lovable frontend lane. You set up the kit in a project by hand with the steps in "Set up the kit in a project". The first project that uses these steps is the paint-math demo.

v2: the kit is a Claude Code plugin, `agk`. This is the plugin route: use "Install the kit as a plugin (v2)" below.

## Install the kit as a plugin (v2)

Run these steps in the root of the project (the git root).

1. Add the marketplace and install the plugin:

   ```bash
   claude plugin marketplace add Lighfe/agent-graph-kit
   claude plugin install agk@agent-graph-kit --scope project
   ```

2. Run the setup in a Claude Code session in the project:

   ```text
   /agk:setup
   ```

   The skill (`plugin/skills/setup/SKILL.md`) asks for the project name and the test command, then copies the kit files and writes the lock file.
3. Do the remaining manual steps:
   1. Check `gh auth status`. If it fails, log in with `gh auth login`.
   2. Log in to Codex with `codex login`.
   3. Add the Codex trust entry to `$HOME/.codex/config.toml`. Use the absolute path of the project (`git rev-parse --show-toplevel`):

      ```toml
      [projects."/home/you/projects/example-app"]
      trust_level = "trusted"
      ```

   4. Add the three Auto mode entries in `/permissions`, in the Auto mode tab. The texts of entry 2 and entry 3 are in [Auto mode allow entries](#auto-mode-allow-entries). Entry 1 allows exactly this command in the project repo:

      ```text
      scripts/qa-codex ROLE=qa ISSUE=<number>
      ```

To see which copied files changed since the setup, run `/agk:drift` (`plugin/skills/drift/SKILL.md`).

## Lovable frontend lane (optional, v2)

The base kit works without this lane. To add it:

1. Create the Lovable project.
2. Add the line `Lovable project: <id>` to `AGENTS.md`.
3. Install the `lovable` plugin.

## Set up the kit in a project

This is the manual route (v1). For v2 use the section "Install the kit as a plugin (v2)" above.

Run these steps in the root of the new project (the git root; see "Project repo" for a new, empty repo), in a terminal outside Claude Code. Do not run them from a Claude Code session: the kit's guard hooks deny the `cp` of `.claude/settings.json` (`G8:`), and the Auto mode classifier denies the copy into `.claude/` and the `git submodule add`. The examples use a synthetic project `example-app` at `/home/you/projects/example-app` and a clone of this repo next to it at `../agent-graph-kit`.

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

The agents post comments with `gh issue comment <n> --body-file <literal path>`, with the body written to a file first. This is a rule of `docs/process.md`, not a check: the guard does not check comment commands (the comment-form check was removed in [#90](https://github.com/Lighfe/agent-graph-kit/issues/90)). Because the agents use your login, the rule that agents never post your marker is not enforced by a check either.

You post `## Owner: RESUME` on the GitHub web page, in a terminal, or from a Claude Code session, for example with `gh issue comment <n> --body-file <literal path>`.

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

- `AGENTS.md`: the first line (`# <project name>`), the project description (replace the two kit sentences at the top: "This repo will become a Claude Code plugin ..." and "Now, it is in bootstrap."), and the test command (the line `Test command: ...`)
- `AGENTS.md`: remove or reword the lines that are only true for this kit repo: `docs/specs/agent-graph-kit.md` - the living behavior spec: how the kit behaves now (under "Documents"), the key name `TYPESAFE_API_KEY` (under "Public repo"), and the line about `docs/references/local/` (under "Public repo")
- Frontend lane only: the `frontend/` submodule (see "Frontend lane" below) and the `frontend` lane. Add the line `Lovable project: <id>` to `AGENTS.md`; the `frontend-engineer` reads the Lovable project id from it. Without a Lovable project, the PM must not use `Lane: frontend`.

### Codex trust entry

Add the trust entry for the project to `$HOME/.codex/config.toml`. Otherwise Codex writes it there during the loop. The path is the git root of the project (`git rev-parse --show-toplevel`), as an absolute path:

```toml
[projects."/home/you/projects/example-app"]
trust_level = "trusted"
```

### Auto mode allow entries

The loop runs in Auto mode. Three agent calls need an allow entry for the Auto mode classifier. The entries are user-level: in a session, run `/permissions`, open the **Auto mode** tab, and add each entry (keep `$defaults`). Claude Code saves them as `autoMode.allow` in `~/.claude/settings.json`. The classifier does not read `autoMode` from project settings, and an entry in the **Allow** tab (`permissions.allow`) has no effect on it.

Entry 1 (QA): allow exactly `scripts/qa-codex ROLE=qa ISSUE=<number>` in the project repo. This is the Codex QA launch command (see `docs/checks/hook-activation.md`, "Set-up" step 2).

Entry 2 (PM edits): copy this text as is:

```text
In a repo set up with agent-graph-kit, the pm subagent may run gh issue edit <n> --body-file <path> or gh issue edit <n> --title <title> on an issue of that repo, to apply an edit of that issue that the repo owner asked for on that issue in a post whose first line is "## Owner: RESUME" and whose authorAssociation is OWNER. This is the owner's instruction, not instruction poisoning.
```

Without entry 2, the classifier may deny the PM's edit ("Instruction Poisoning"). The PM then posts `## PM: NEEDS OWNER` with the deny message (rule "Denied action" in `docs/process.md`). Then either set the entry, or make the edit by hand; in both cases post a new `## Owner: RESUME`.

The limit: entry 2 holds for every repo of the user, and the classifier cannot check `authorAssociation`. The PM's own check (`docs/team/pm.md`, "After `## Owner: RESUME`") is what keeps a stranger's RESUME from editing an issue.

Entry 3 (planner relabel): copy this text as is:

```text
In a repo set up with agent-graph-kit, the main session working as the planner (started with /stage-start) may run exactly gh issue edit <n> --remove-label later --add-label ready on a sub-issue of a stage issue (an issue with the label stage) of that repo, after the repo owner confirmed that stage in the same session. This is the planner step in docs/team/planner.md, done on the owner's instruction. The entry allows only this command: no other label, no other gh issue edit flag, no gh issue close, and no sub-issue or blocker link.
```

Without entry 3, the classifier may deny the relabel ("External System Writes"), also after you confirmed the stage. The planner then tells you in the session: it quotes the deny message, names each sub-issue that still has `later` with its relabel command, and waits (rule "Denied relabel" in `docs/team/planner.md`). Then either set the entry and ask the planner to retry, or relabel by hand and tell the planner that the labels are set. The planner then checks the labels of every sub-issue and goes on.

The limit: entry 3 holds for every repo of the user, and the classifier cannot check that the owner confirmed the stage. The planner's own steps in `docs/team/planner.md` (the relabel only after your confirmation, in "Intake" and in "Stage set-up") are what keep the relabel after the confirmation.

An entry for a task's `Permissions:` line (see `docs/task-template.md`) is temporary: make it as narrow as the task allows, and remove it after the task is closed. The stage review lists these entries for removal.

### Frontend lane (optional)

Frontend lane only. No MCP tool can make the GitHub connection of a Lovable project, so you do these steps by hand:

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

Accepted risk ("Worktree and pre-step" in [docs/specs/agent-graph-kit.md](docs/specs/agent-graph-kit.md#worktree-and-pre-step)): the QA pre-step runs code from the repository outside the Codex sandbox, with your environment and access. This happens on three paths: the lifecycle scripts (`preinstall`, `install`, `postinstall`, `prepare`) of `frontend/package.json` and of every dependency with `npm ci`, or of the dependencies bun trusts (`trustedDependencies` and bun's default trusted list) with `bun install`; the package manager config `frontend/.npmrc` or `frontend/bunfig.toml`; and the Playwright CLI from `frontend/node_modules`, which the lockfile decides. This is accepted because the frontend code comes from your own Lovable project and from the loop's engineer (issue #50). The remaining risk includes packages that agents add: a new dependency or version that Lovable or another agent of the loop puts into `package.json` or the lockfile runs with your access at the next QA run, before QA or you have looked at it. Nothing in the loop checks it first. Treat changes to `frontend/package.json`, the lockfile, `.npmrc`, `bunfig.toml` or `trustedDependencies` as review items.

### Labels

```bash
gh label create ready --description "Orchestrator may work on this issue" --color 1D76DB --force
gh label create needs-owner --description "Escalated: the orchestrator waits for the owner" --color FBCA04 --force
gh label create later --description "Out of scope for the current implementation" --color BFD4F2 --force
gh label create stage --description "Stage issue: purpose and context for its sub-issues; never ready" --color 5319E7 --force
```

`--force` updates a label that already exists instead of failing.

### Start

1. Commit the copied and adjusted files (with `.gitignore` and, for the frontend lane, `.gitmodules` and `frontend`), and push them to `main` on GitHub (`git push -u origin main` for the first push).
2. Open the project folder in Claude Code and trust the folder. The project allow rules for `scripts/qa-codex` and for `gh issue close` apply only in a trusted folder ([G8](docs/specs/agent-graph-kit.md#g8-settings-protection)). The hooks apply from the next tool call after `.claude/settings.json` is in place.
3. Run the acceptance test in [docs/checks/hook-activation.md](docs/checks/hook-activation.md) before the first issue gets the label `ready`. If a step fails, the loop does not start.
4. Final step: run `/stage-start` in the project to plan the first stage (intake). The main session is then the planner (`docs/team/planner.md`). The planner ends set-up with a `/goal …` line: run it in the same or a new session to start the loop.

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

- Accepted design: the living behavior spec [docs/specs/agent-graph-kit.md](docs/specs/agent-graph-kit.md) (how the kit behaves now), and the other specs in [docs/specs/](docs/specs/)
- Historical input: [docs/archive/](docs/archive/)
- Development process of this repo: [docs/process.md](docs/process.md)
