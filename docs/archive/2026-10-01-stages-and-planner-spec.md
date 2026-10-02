# Stages, the planner role and living docs

Date: 2026-10-01.
Status: owner decisions of 2026-10-01, for owner review of this text
Replaces as the source of truth: the proposals `docs/specs/2026-10-01-big-picture.md` (#83) and `docs/specs/2026-10-01-doc-lifecycle.md` (#84), and the stage part of `docs/research/backlog-triage-proposal.md` (#85). Where this file and a proposal differ, this file holds.

## 1. Goal

The kit sees beyond one issue. Work is grouped in stages with a purpose. A team role plans the stages; the owner validates the purpose and confirms or chooses the next stage, but does not plan. Each stage ends with a systematic review. The agent-readable docs stay true without double bookkeeping and without guardrails on reading.

## 2. Stages on GitHub

- **One place: GitHub issues.** Order, dependencies, stages and follow-ups live in issue fields. No roadmap file, no dependency table in a plan, no second copy.
- **A stage is a stage issue.** Label `stage`. It never gets `ready`, so no role launch runs on it (the hook already denies launches without `ready`); it never goes through PM, engineer and QA. Its body holds meta information:
  - `## Purpose`: what the stage achieves, in one or two sentences; the owner validates it
  - `## Background`: the overarching goal, how the issues depend on each other, constraints that hold for all of them
  - `## Exit check`: by default "every sub-issue is closed and the purpose is met"
- **The work of a stage is its sub-issues.** Normal task issues in `docs/task-template.md` format. The PM reads the stage issue as context when it grooms a sub-issue.
- **Order.** Stages are ordered by native "blocked by" links between stage issues. Inside a stage: native "blocked by" links first, then the position in the sub-issue list (fallback: issue number, if `gh` cannot read the list order).
- **Native "blocked by" links replace** the `Waiting on: #<N>` line of `## PM: WAITING` and the label `waiting`. The hooks read blockers with the REST form that gives repo, number and state (`gh api .../dependencies/blocked_by`), with paging. The PM adds a link instead of writing the line.
- **The active stage** is found once, at the start of a `/goal` run, and kept for the whole run: the one open stage issue with at least one sub-issue (open or closed) with `ready`. It stays active after its last `ready` sub-issue is closed or escalated; the loop then goes to the stage end or stops, and does not pick `ready` issues outside the stage. With no such stage, no stage is active for the run, and the loop works on `ready` issues as today.
- **Follow-ups are parked.** Whoever files one (PM, orchestrator, owner after a review) gives it the label `later`, no parent, and a line `Source: <URL>` (the comment, review or issue it came from). Two ways out of parked:
  - during a stage: if a parked issue blocks an issue of the active stage, the orchestrator adds it to the stage (sub-issue, `ready`)
  - all others: at the stage review (section 4)

## 3. Roles: planner and orchestrator

The entry command sets the role of the main session:

| Start | Role of the main session | Follows |
|---|---|---|
| `/stage-start` (kit skill) | **Planner**: intake or stage set-up, in dialogue with the owner | `docs/team/planner.md` |
| `/goal …` | **Orchestrator**: runs the loop on the `ready` issues | `docs/team/orchestrator.md` |
| no command | assistant (questions, reports); no loop, no planning duties | - |

- A session switches from planner to orchestrator at most once, never back. The planner ends set-up with: "Stage #N is ready. Run `/goal …` here or in a new session."
- The planner also runs as a **subagent** (`.claude/agents/planner.md`, launch line `ROLE=planner ISSUE=<stage issue>`) for the stage review only. The hook allows this launch only on an open issue with the label `stage`.
- The planner's three jobs:
  1. **Intake** (main session): a new idea → brainstorming → spec in `docs/specs/` → plan in `docs/plans/` → one stage issue with its sub-issues. Uses the superpowers skills brainstorming and writing-plans.
  2. **Stage set-up** (main session): reads the newest stage review, presents its options, answers the owner's questions; the owner chooses and validates the purpose; the planner writes the stage issue, files or links its sub-issues, sets order and blockers, adds `ready` to the sub-issues, and closes the finished stage issue.
  3. **Stage review** (subagent, launched by the orchestrator): see section 4. It reads and posts one comment; it creates, edits or closes no issue.
- The owner validates purposes and confirms or chooses. The owner does not order the work.

## 4. Stage end

When every sub-issue of the active stage is closed, the orchestrator launches the planner subagent on the stage issue. The prompt carries the orchestrator's **run notes**: escalations, guard and classifier denies, outages, collisions, anything unusual in the run. Then the orchestrator stops; the final report names the stage review.

If a sub-issue is escalated (`needs-owner`), the stage has not ended; the loop stops as today.

The planner posts one comment on the stage issue, first line `## Planner: STAGE REVIEW`, with:

1. **Purpose check**: was the purpose met, with evidence (closed issues, commits, reports)
2. **Run notes**: the orchestrator's notes, and what the planner concludes from them
3. **Doc drift**: the result of the fact tests and of the instruction audit (`/doctor prompt-audit`, where it can run), as findings
4. **Follow-ups**: every parked issue whose `Source:` points into this stage, and every older parked issue the planner sees as relevant, each with a proposed placement: next stage, a later stage, stay parked, or close
5. **Next-stage options**: one to three, each with purpose, sub-issues (existing or to be filed), order and blockers, and a recommendation
6. Last line: the start command for the next session, `/stage-start`

The owner reads it and starts a new session with `/stage-start` when it suits them.

## 5. Docs

- **Living behavior spec**: `docs/specs/agent-graph-kit.md`, no date in its name. It holds what the code implements and no other file states: principles, roles, the launch contract and the guarantees G1 to G8, the `qa-codex` contract, the stage model. The v1 spec moves unchanged to `docs/archive/`.
- **Kept up to date, in the same commit as the change that makes them false**: the instruction files (`AGENTS.md`, `CLAUDE.md`, `docs/process.md`, `docs/team/*.md`, `docs/task-template.md`, `.claude/agents/*.md`, `.agents/skills/`, the README set-up section) and the living spec.
- **Code cites names, not numbers**: a heading anchor of the living spec or a guarantee ID, instead of "spec 5.3".
- **Fact tests**: tests in the normal test command that check facts in the docs, never meaning: every repo path named in an instruction file exists; every cited spec anchor exists; the guarantee IDs in the docs match the checks in the hook.
- **Lifecycles**: plans and proposals are archived to `docs/archive/` once their stage is set up; research and spike reports are written once and stay; reviews are deleted once each finding is an issue or decided.
- **Reading rules are prose, never hooks**:
  - `docs/archive/`: read only when pointed to
  - `docs/research/`: readable; agents may build on earlier research and cite it
  - `docs/plans/`: reached through the issue that came from it
  - `docs/reviews/`: matter in the session that asked for the review
- **Not now**: a scheduled doc agent; hard size limits.

## 6. Rollout in three stages

The first stage issues are written by hand in the session that wrote this file (the planner role does not exist yet). Stage 1 ends with a stage review by hand; from stage 2 on, the planner does it.

| Stage | Purpose | Sub-issues (one line each; the plan details them) |
|---|---|---|
| 1. Stages on GitHub | The loop reads order and blockers from GitHub and can verify criteria about GitHub state | spike: sub-issue order and blocker paging with `gh`; Codex QA gets GitHub state (#89); native blockers replace `Waiting on:` and `waiting` in hooks, tests and docs (#64 rewritten); label `stage`, stage issue form, `Source:` line for follow-ups, the close check allows a `stage` issue whose sub-issues are all closed |
| 2. Planner | Stages are planned and reviewed by the planner; the owner only validates and chooses | role file and subagent; hook accepts `ROLE=planner` on `stage` issues; skill `/stage-start`; orchestrator stage-end step with run notes; role separation in `docs/process.md`, `README.md`, `AGENTS.md` |
| 3. Living docs | The docs stay true by construction | living spec and archive of the v1 spec; anchors instead of section numbers; fact tests; reading rules as prose; lifecycle moves of existing docs (#87, #16); drift check in the stage review |

Stage 2 is blocked by stage 1; stage 3 by stage 2. The open `later` issues stay parked; the stage reviews place them (this replaces #91).
