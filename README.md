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

### Project repo

The project is a git repo with a GitHub remote `origin` and a branch `main`. The loop keeps its tasks in the GitHub issues of that repo, and the `gh` commands below act on it. To start from a new, empty GitHub repo, create it on GitHub (or with `gh repo create`), then clone it and put the clone on `main`:

```bash
git clone https://github.com/<owner>/example-app.git
cd example-app
git checkout -B main   # an empty clone starts on the branch of init.defaultBranch, which may not be main
```

The clone has no commit yet. The first commit and push are in "Start".

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

If the new project already has its own `.claude/settings.json`: do not overwrite it. Skip the `cp` of the settings file and merge the two blocks into the existing file by hand: add the `allow` and `deny` rules to its `permissions` block, and add every entry of the kit's `hooks` block to its `hooks` block. Today these are `PreToolUse` (the guard hook) and `PermissionDenied` (runs `.claude/hooks/not_started.py`, which marks a launch that was denied before it ran). Check afterwards that each event name in the kit's `hooks` block is also in yours.

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

Nobody edits `frontend/` locally. All frontend changes go through Lovable.

### Labels

```bash
gh label create ready --description "Orchestrator may work on this issue" --color 1D76DB --force
gh label create needs-owner --description "Escalated: the orchestrator waits for the owner" --color FBCA04 --force
gh label create later --description "Out of scope for the current implementation" --color BFD4F2 --force
```

`--force` updates a label that already exists instead of failing.

### Start

1. Commit the copied and adjusted files (with `.gitignore` and, for the frontend lane, `.gitmodules` and `frontend`), and push them to `main` on GitHub (`git push -u origin main` for the first push).
2. Open the project folder in Claude Code and trust the folder. The project allow rules for `scripts/qa-codex` and for `gh issue close` apply only in a trusted folder (spec 5.9). The hooks apply from the next tool call after `.claude/settings.json` is in place.
3. Final step: run the acceptance test in [docs/checks/hook-activation.md](docs/checks/hook-activation.md) before the first issue gets the label `ready`. If a step fails, the loop does not start.

## Background

The kit builds on the workflow from the DataTalksClub [AI Dev Tools Zoomcamp](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp) by Alexey Grigorev.

## Design

- Accepted design: [docs/specs/](docs/specs/)
- Historical input: [docs/archive/](docs/archive/)
- Development process of this repo: [docs/process.md](docs/process.md)
