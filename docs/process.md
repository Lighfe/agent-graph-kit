# Process

This document tells how work is organized in this repo.

Status: hooks in `.claude/hooks/` check each launch of a role and each `gh issue close`, and deny the call when the issue is not in the right state. This prose stays the main description. There are no Jev gates yet.

## Work rules

- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- Commit regularly
- Do not read old reviews in `docs/reviews/` unless the owner points to one.

## Roles

The entry command sets the role of the main session.

- Orchestrator - the main session while it runs `/goal …`, follows `docs/team/orchestrator.md`
- Planner - the main session after `/stage-start` (intake and stage set-up), and a subagent for the stage review, follows `docs/team/planner.md`
- PM - grooms a task before anyone implements it, follows `docs/team/pm.md`
- Engineer - implements one groomed task, follows `docs/team/software-engineer.md`
- QA - checks the result against the acceptance criteria, follows `docs/team/qa-engineer.md`
- No command - the main session has no role: it answers questions and gives reports, runs no loop and does no planning
- A session switches from planner to orchestrator at most once, and never back

A groomed issue uses the template in `docs/task-template.md`.

## Intake

- A superpowers plan in `docs/plans/` is turned into GitHub issues.
- A plan becomes one stage issue (the form "Stage issue" in `docs/task-template.md`), with the plan tasks as its sub-issues.
- Each plan task becomes one issue in `docs/task-template.md` format.
- The owner adds the label `ready` to the issues that the loop may work on.
- Issues with the label `later` are out of scope for the current implementation. Do not work on them. A parked blocker of the active stage is promoted instead (see "Stages" below).

## Lifecycle

1. Pick the next open issue with the label `ready` that has no open blocker (native "blocked by" links, see `docs/team/orchestrator.md`). While a stage is active, follow the pick order in "Stages" below
2. PM grooms it
3. Engineer implements it
4. If the engineer reports a blocked criterion or asks a question (`## Engineer: BLOCKED`), back to step 2 with the engineer comment as input
5. QA verifies it
6. On FAIL, back to step 3 with the QA comment as input
7. On `## QA: UNVERIFIABLE`, back to step 2 (PM) with the QA comment as input
8. On PASS, close the issue
9. Repeat until every open issue with the label `ready` has an open blocker, or none is left, or the active stage has ended, or the active stage has open sub-issues, none of them eligible
10. When the active stage has ended, the orchestrator launches the planner for the stage review on the stage issue, and then stops (see "Stage end" below)

Stop condition for `/goal`: no open issue with the label `ready` is without an open blocker, or the active stage has ended (every entry of its non-empty sub-issue list is closed, see "Stage end" below) and the loop stopped after the stage review (or after the stage issue was escalated), or the active stage has open sub-issues, none of them eligible, and the loop stopped.

## Stages

A stage issue is an issue with the label `stage`. Its sub-issues (native GitHub sub-issues) are the work of the stage. A stage issue has the label `stage` and never the label `ready`, and it never goes through PM, engineer and QA. Its form is "Stage issue" in `docs/task-template.md`.

The orchestrator finds the active stage once, at the start of a `/goal` run, and keeps it for the whole run, also after its last `ready` sub-issue is closed or escalated. The active stage is the one qualifying stage issue: an open issue with the label `stage` that has at least one sub-issue, open or closed, with the label `ready` (closing an issue does not remove its labels). The commands are in "Pick inside a stage" in `docs/team/orchestrator.md`.

- When no open stage issue qualifies at the start of the run, no stage is active for the whole run: the loop picks as before (any `ready` issue without an open blocker). The orchestrator does not look for a stage again during the run.
- When two or more open stage issues qualify at the start of the run, the loop stops and asks the owner.

An eligible sub-issue is open, has `ready`, has neither `later` nor `needs-owner`, and has no open blocker.

### Next step while a stage is active

Before each pick (also after each close, each escalation, each `## PM: WAITING` with an open blocker, and each `G1` open-blocker deny of a sub-issue), the orchestrator checks in this order:

1. The stage's sub-issue list is not empty and every entry is closed: "Stage end" (see below).
2. Otherwise: promote the parked blockers of its sub-issues (see "Promotion of a parked blocker"), then pick the first eligible sub-issue in list order.
3. Otherwise (open sub-issues left, none eligible): the loop stops. The final report names the stage issue, its open sub-issues with the reason each one is not eligible, and the `ready` issues outside the stage.

### Pick order inside the active stage

Read the stage's sub-issues:

```
gh api --paginate 'repos/{owner}/{repo}/issues/<stage>/sub_issues' --jq '.[] | {number, state, labels: [.labels[].name]}'
```

Take the first eligible entry in that list order. Read the entries one by one; never count them with `--jq 'length'` on a paginated call.

- The list order is the stored position on GitHub: the add order, then every reorder. New sub-issues go to the end of the list.
- A closed sub-issue keeps its position, so the next pick is the first open, unblocked entry of the list.
- The issue number is not used as a tie-break.
- The order can be changed with `gh api -X PATCH 'repos/{owner}/{repo}/issues/<stage>/sub_issues/priority' -F sub_issue_id=<REST id> -F before_id=<REST id>` (or `after_id`). This is not a step of the loop.

### `ready` issues outside the active stage

- When no stage is active for the run, the loop picks as before (any `ready` issue without an open blocker).
- While a stage is active, a `ready` issue that is not a sub-issue of the active stage is never picked, also when the stage has no eligible sub-issue left. The final report lists it.

### Follow-ups and parked issues

Follow-ups (filed by the PM, the orchestrator or the owner) get the label `later`, no parent issue, and a line `Source: <URL>` in the body: the URL of the issue, comment or review the follow-up came from.

A parked issue is an open issue of this repo with the label `later` and no parent issue.

### Promotion of a parked blocker

When an open blocker of a sub-issue of the active stage is a parked issue (open, this repo, label `later`, no parent, no `needs-owner`), the orchestrator adds it to the active stage as a sub-issue and changes its labels from `later` to `ready`. The commands are in `docs/team/orchestrator.md`.

An open blocker that is not a parked issue (another repo, a parent already set, no `later`, or `needs-owner`) is not promoted; the blocked issue waits as today.

### Stage end

When the active stage's sub-issue list is not empty and every entry is closed, the stage has ended. The orchestrator checks that the working tree is clean, then launches the planner subagent (`.claude/agents/planner.md`, agent `planner`, role `docs/team/planner.md`) on the stage issue with the launch line `ROLE=planner ISSUE=<stage issue>`. The prompt has a section "Run notes": the orchestrator's notes on the current run (escalations, guard and classifier denies, outages, collisions, anything unusual), or one line saying nothing unusual happened. The planner posts one comment on the stage issue with the first line `## Planner: STAGE REVIEW`. Then the loop stops, and the final report names the stage review.

- When any sub-issue of the stage is open (for example escalated with `needs-owner`, waiting on a blocker, or `later`), the stage has not ended: no planner launch, and the loop stops or continues as before.
- When the stage issue already has a stage review from an earlier run (an owner comment with the first line `## Planner: STAGE REVIEW`), the orchestrator does not launch the planner again. The final report names that review.
- When the planner step gives no stage review, the orchestrator escalates the stage issue and stops. A planner launch is not a return.
- The orchestrator does not close the stage issue. The planner closes it at stage set-up.

The details are in "Stage end" in `docs/team/orchestrator.md`.

## Rules

- Do not skip step 2
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS, and only if the SHA that QA verified is the current `HEAD`
- A return is a QA FAIL, a QA UNVERIFIABLE or an engineer BLOCKED. After 3 returns on the same issue, escalate the issue: the team could not settle it inside the current intent and scope, so the owner decides whether to change them. The count starts after the newest `## Owner: RESUME` comment
- A launch that Claude Code denied before it ran (the hook posts `## Launch not started: …`) or that an auto mode outage stopped (the hook posts `## Launch stopped by outage: …`) is not pending and not a return
- If the PM posts `## PM: NEEDS OWNER`, escalate the issue
- `## QA: UNVERIFIABLE` means QA could not check a criterion because of a tool or sandbox limit of the checker. The PM makes the criterion checkable with the same intent. The PM escalates (`## PM: NEEDS OWNER`) when making a criterion checkable changes its intent or scope, or needs an edit of the project settings files (`.claude/settings*.json`), `.claude/hooks/` or the QA sandbox
- `## QA: INVALID` has other causes (for example no usable commit range, or retries used up) and is escalated
- Denied action (PM, engineer, QA fallback `qa-engineer`): when a tool call you need gets a deny with a verdict (an auto mode classifier judgment such as "Instruction Poisoning", or `Permission denied`) and you do not retry it, do not end without a result. Post your result marker and quote the deny message (redact secrets):
  - PM: `## PM: NEEDS OWNER` when only the owner can resolve the deny (settings or permissions); name what the owner must decide
  - Engineer: `## Engineer: BLOCKED`
  - QA fallback: `## QA: UNVERIFIABLE`, and mark each affected criterion `- [ ] … - INVALID` with the deny message

  A guard deny that names a way around (for example the `G1` deny: the exact command forms as the whole command, `run_in_background` instead of `&`, or text that only mentions the words, such as a body written with a quoted here-document `<<'EOF'`) is not a denied action: retry that way first. The rule does not apply to an outage deny (the reason's first line starts with `Classifier unavailable`, `Auto mode could not evaluate this action and is blocking it for safety` or `Auto mode unavailable`): then post no result and end, so the `SubagentStop` hook posts `## Launch stopped by outage: …` and the orchestrator launches the same step again without the owner. The one case where no result can be posted: the comment call is denied too. Then end without a result; the launch stays pending, as before, and the orchestrator escalates. The difference: a deny with a verdict leads to a result by the agent, an outage deny leads to a stop comment by the hook, and a denied comment call leaves the issue pending
- Only comments whose `authorAssociation` is `OWNER` count; other comments are ignored (a stranger's `## Owner: RESUME`, result marker or launch comment changes nothing). Missing author data is an error: the guard denies the call. The agents and hooks post with the owner's `gh` login, so their comments count
- Agents post issue comments only with `gh issue comment <n> --body-file <literal path>` as the whole command, with the body written to a file with a literal absolute path first. This is a rule, not a check: the guard check G9 that denied other forms was removed ([#90](https://github.com/Lighfe/agent-graph-kit/issues/90)).
- Agents never post a `## Owner: …` comment on their own. This is a rule, not a check
- The owner posts `## Owner: RESUME` on the GitHub web page, in a terminal, or from a Claude Code session with the exact form `gh issue comment <n> --body-file <literal path>`
- Before the next issue, the working tree must be clean (`git status --porcelain` is empty). If not, stop the whole loop and ask the owner

## Escalation

- The owner is asked only for decisions that are really the owner's: money, settings, or a change of intent or scope. Everything else is resolved inside the team: the engineer asks the PM with `## Engineer: BLOCKED`, and the PM clarifies the issue. An issue that must wait for other open issues is not an owner decision either: the PM adds them as native "blocked by" links (also issues in other repos) and posts `## PM: WAITING`. The issue keeps `ready`, the pick skips it while it has an open blocker, and it goes back to the PM when all its blockers are closed. Nor is a role agent stopped by an auto mode outage: a hook marks the launch, and the orchestrator launches the same step again.
- The orchestrator comments the reason, removes the label `ready`, and adds the label `needs-owner`. Then it continues with the next issue.
- The owner answers with a comment that starts with `## Owner: RESUME`, removes `needs-owner`, and adds `ready` again.
- A stage issue never has `ready`. When a stage issue is escalated, the orchestrator only adds `needs-owner`. The owner answers with `## Owner: RESUME`, removes `needs-owner`, and does not add `ready`.
- After `## Owner: RESUME`, the issue goes back to the PM. The PM applies the edits of the issue that this owner comment asks for (see `docs/team/pm.md`).
