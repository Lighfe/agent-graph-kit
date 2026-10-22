# agent-graph-kit

This repo is the agent-graph-kit, a Claude Code plugin for multi-agent Graph Engineering. It ships the plugin `agk` in `plugin/`.
Hooks in `.claude/hooks/` check the handoff calls (see `docs/process.md`).

## Documents

- `docs/process.md` - how work is organized. Read it before you start a task.
- `docs/task-template.md` - the template for a groomed issue
- `docs/team/` - the role definitions (orchestrator, planner, PM, software engineer, QA engineer)
- `docs/team/planner.md` - the planner: intake and stage set-up in the main session started with `/stage-start`, and the stage review as a subagent
- `docs/specs/agent-graph-kit.md` - the living behavior spec: how the kit behaves now

## Commands

- `gh issue list --state open --label ready --search "-label:later -label:needs-owner -label:stage" --limit 500` - list the issues the loop may work on
- `gh issue view <number> --comments` - read an issue and its comments
- `gh issue comment <number> --body-file <file>` - add a comment to an issue
- `gh issue edit <number> --add-label <label>` / `--remove-label <label>` - change labels
- `gh issue close <number>` - close an issue: the orchestrator closes a task issue after `## QA: PASS` (see `docs/team/orchestrator.md`), and the planner closes a finished stage issue (all its sub-issues closed) at stage set-up (see `docs/team/planner.md`)

Test command: uv run --with pytest pytest. Never report tests as passed if no test ran.

## Skills and subagents

- Project skills go to `.agents/skills/<name>/SKILL.md`. `.claude/skills` is a symlink to `.agents/skills`.
- Subagent definitions go to `.claude/agents/`. They point to the role files in `docs/team/`.
- When the owner asks for a Codex review, use the `codex-review` skill.

## Rules

### Folders

- Specs go to `docs/specs/`. Plans go to `docs/plans/`.
- These paths override the default paths of the superpowers skills.

### Superpowers

Use these skills:

- brainstorming, writing-plans (upstream: idea → spec → plan → issues). The planner role (`docs/team/planner.md`) uses them, in the main session started with `/stage-start`. Plan tasks become issues in `docs/task-template.md` format (see Intake in `docs/process.md`).
- test-driven-development (technique for the engineer role)
- verification-before-completion (prose version of the "done" gate)
- requesting-code-review, receiving-code-review (technique for the reviewer role; the reviewer role is not defined yet, do not invent it)
- using-git-worktrees (parallel mode; parallel mode is not defined yet, do not invent it)

Do not use these skills: subagent-driven-development, executing-plans.

Reason: these two skills are a second orchestrator. They make their own rulings without asking the human. This conflicts with `docs/process.md`, which defines when to escalate to the owner.

If a skill offers one of these two skills as the next step, do not accept. Turn the plan into issues and follow `docs/process.md`.

### Public repo

- Never put secrets in commits, issue bodies, issue comments or reports. `TYPESAFE_API_KEY` and other keys stay in the user environment. Redact sensitive output. Use synthetic examples.
- Do not commit full third-party articles. `docs/references/local/` is local only.

## Kit-repo release steps

These steps exist only in this repo. A plugin project has neither script. The role files in `docs/team/` send each role here when this heading exists. The skill `bump-plugin-version` describes the bump.

- Orchestrator, in "Stage end", before the planner is launched: run `uv run scripts/bump_plugin_version.py`. When it prints that no bump is needed, there is nothing to commit. Otherwise run the test command above and commit the bump (`plugin/.claude-plugin/plugin.json`, `scripts/plugin-release.json` and the rebuilt copies in `plugin/`). When the script or the tests fail, do not commit: reset the files, name the failure in the run notes and go on
- Planner, before the stage review is written: run `scripts/build_plugin.py --release-status`. The answer `unreleased changes` is a doc drift finding: the stage changed the plugin and the end-of-stage bump of the orchestrator did not run
- Engineer: do not bump the plugin version in a task. The orchestrator does at the end of the stage
