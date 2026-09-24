# agent-graph-kit

This repo will become a Claude Code plugin for multi-agent Graph Engineering.
Now, it is in bootstrap. We build the kit with a prose-only process.

## Documents

- `docs/process.md` - how work is organized. Read it before you start a task.
- `docs/task-template.md` - the template for a groomed issue
- `docs/team/` - the role definitions (orchestrator, PM, software engineer, QA engineer)
- `docs/design/brainstorm-handover.md` - accepted decisions (D1 to D10) and open questions (O1 to O7)

## Commands

- `gh issue list --state open --label ready` - list the issues the loop may work on
- `gh issue view <number> --comments` - read an issue and its comments
- `gh issue comment <number> --body-file <file>` - add a comment to an issue
- `gh issue edit <number> --add-label <label>` / `--remove-label <label>` - change labels
- `gh issue close <number>` - close an issue (orchestrator only, see `docs/team/orchestrator.md`)

Test command: none yet. If no test suite exists, say so in the issue comment. Never report tests as passed if no test ran.

## Skills and subagents

- Project skills go to `.agents/skills/<name>/SKILL.md`. `.claude/skills` is a symlink to `.agents/skills`.
- Subagent definitions go to `.claude/agents/`. They point to the role files in `docs/team/`.

## Rules

### Folders

- Specs go to `docs/specs/`. Plans go to `docs/plans/`.
- These paths override the default paths of the superpowers skills.

### Superpowers (decision D7)

Use these skills:

- brainstorming, writing-plans (upstream: idea → spec → plan → issues). Plan tasks become issues in `docs/task-template.md` format (see Intake in `docs/process.md`).
- test-driven-development (technique for the engineer role)
- verification-before-completion (prose version of the "done" gate)
- requesting-code-review, receiving-code-review (technique for the reviewer role; the reviewer role is not defined yet, do not invent it)
- using-git-worktrees (parallel mode; parallel mode is not defined yet, do not invent it)

Do not use these skills: subagent-driven-development, executing-plans.

Reason: these two skills are a second orchestrator. They make their own rulings without asking the human. This conflicts with `docs/process.md`, which defines when to escalate to the owner. The Jev escalation policy (D2) is not defined yet, do not invent it.

If a skill offers one of these two skills as the next step, do not accept. Turn the plan into issues and follow `docs/process.md`. If conflicts repeat, copy the used skills into the kit (fork later, only with evidence).

### Public repo

- Never put secrets in commits, issue bodies, issue comments or reports. `TYPESAFE_API_KEY` and other keys stay in the user environment. Redact sensitive output. Use synthetic examples.
- Do not commit full third-party articles. `docs/references/local/` is local only.

### Decisions

- The decisions in `docs/design/brainstorm-handover.md` are accepted. Do not change them unless the owner asks.
- Do not decide the open questions O1 to O7 without the owner.
