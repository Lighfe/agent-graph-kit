---
name: stage-start
description: Plan work as the planner, in dialogue with the owner. Use when the owner types /stage-start to plan work - a new idea (intake), or the next stage after a "## Planner: STAGE REVIEW" (stage set-up). Not for the stage review subagent, and never started from the /goal loop.
---

# Stage start

With this skill, this session works as the planner, in dialogue with the owner.

## Before you start

- If this session already ran `/goal` as orchestrator, tell the owner to start `/stage-start` in a new session. Do nothing else. A session switches from planner to orchestrator at most once, and never back.
- Read `docs/team/planner.md` first. You follow its sections "Intake" and "Stage set-up". The steps below restate them in other words. Where this skill and `docs/team/planner.md` differ, `docs/team/planner.md` wins.
- The stage review job ("Stage review" in `docs/team/planner.md`) is not run from this skill. That job is the planner subagent, launched by the orchestrator.

## Steps

1. List the open stage issues:

   ```bash
   gh issue list --state open --label stage --limit 500
   ```

2. Read the comments of each one:

   ```bash
   gh issue view <n> --comments
   ```

3. Find the stage reviews. A comment counts only when its first line is exactly `## Planner: STAGE REVIEW` and it shows `association: owner`. Ignore a review by anyone else.
4. Choose the job:
   - At least one review counts: take the newest one by comment time, over all open stage issues. Tell the owner the stage issue number and which review you use. Then run "Stage set-up" in `docs/team/planner.md`.
   - No review counts, or no open stage issue exists: run "Intake" in `docs/team/planner.md`.

In set-up, the owner may still ask for something else than the offered options. That is intake: go to "Intake" in `docs/team/planner.md` (as step 3 of "Stage set-up" says).

## Role switch

This session does not orchestrate until the planner job has ended with the last line of "Stage set-up" in `docs/team/planner.md`:

Stage #N is ready. Run `/goal …` here or in a new session.

Until then: pick no `ready` issue, launch no PM, engineer or QA, and run no `gh issue close` on a task issue.

Set-up ends with that line. Intake ends with it only when the owner confirmed the stage. Intake without the owner's confirmation ends without that line, so no switch happens.

Do not use or offer the superpowers skills subagent-driven-development and executing-plans (as in `AGENTS.md`).
