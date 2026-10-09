# Process

This document tells how work is organized in this repo.

Status: hooks in `.claude/hooks/` check the guarded calls and deny a call that is not allowed (the list is in "Guarded calls" of `docs/specs/agent-graph-kit.md`). This prose stays the main description.

## Work rules

- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- Commit regularly
- Reading rules for the doc folders (prose only, no hook checks them; the lifecycles are in "Doc lifecycles" of `docs/specs/agent-graph-kit.md`):
  - `docs/archive/`: read a file there only when the owner or the issue points to it
  - `docs/research/`: readable; you may build on earlier research and cite it
  - `docs/plans/`: reach a plan through the issue that came from it
  - `docs/reviews/`: a review matters in the session that asked for it; read an older review only when the owner or the issue points to one

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

The planner (the main session, started with `/stage-start`) does intake and stage set-up, in dialogue with the owner. The steps and commands are in "Intake" and "Stage set-up" in `docs/team/planner.md`.

- A superpowers plan in `docs/plans/` is turned into GitHub issues.
- A plan becomes one stage issue with the label `stage` (the form "Stage issue" in `docs/task-template.md`), with the plan tasks as its sub-issues.
- Each plan task becomes one issue in `docs/task-template.md` format. The sub-issues carry the label `later` until the owner confirms the stage.
- Only after the owner has confirmed the stage does the planner remove `later` and add `ready` on each sub-issue: at intake, when the owner confirms the stage in the session; at stage set-up, after the owner has chosen an option of the stage review, validated its purpose and, when permissions were named, confirmed the stage with them. A denied relabel follows the rule "Denied relabel" in `docs/team/planner.md`.
- A task that needs a permission beyond the defaults names it in its `Permissions:` line at planning or grooming, and the owner sets it before the engineer launch.
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

- When no open stage issue qualifies at the start of the run, no stage is active for the whole run: the loop picks any `ready` issue without an open blocker. The orchestrator does not look for a stage again during the run.
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

- When no stage is active for the run, the loop picks any `ready` issue without an open blocker.
- While a stage is active, a `ready` issue that is not a sub-issue of the active stage is never picked, also when the stage has no eligible sub-issue left. The final report lists it.

### Follow-ups and parked issues

Follow-ups (filed by the PM, the orchestrator or the owner) get the label `later`, no parent issue, and a line `Source: <URL>` in the body: the URL of the issue, comment or review the follow-up came from.

A parked issue is an open issue of this repo with the label `later`, no parent issue and no `needs-owner`. A fix issue that the PM filed with `later` and `needs-owner` (rule "A tool problem that an issue can fix" in `docs/team/pm.md`) is not parked: it waits for the owner.

When no stage is active, or the blocked issue is not a sub-issue of the active stage, a parked fix issue is not promoted and not picked (it has `later`). The blocked issue waits; the orchestrator's final report lists it with its open blockers. The planner's stage review places the parked fix issue like any other follow-up.

### Promotion of a parked blocker

When an open blocker of a sub-issue of the active stage is a parked issue (open, this repo, label `later`, no parent, no `needs-owner`), the orchestrator adds it to the active stage as a sub-issue and changes its labels from `later` to `ready`. The commands are in `docs/team/orchestrator.md`.

An open blocker that is not a parked issue (another repo, a parent already set, no `later`, or `needs-owner`) is not promoted; the orchestrator does not promote it or pick it, and the blocked issue waits.

### Stage end

When the active stage's sub-issue list is not empty and every entry is closed, the stage has ended. The orchestrator checks that the working tree is clean, then launches the planner subagent (`.claude/agents/planner.md`, agent `planner`, role `docs/team/planner.md`) on the stage issue with the launch line `ROLE=planner ISSUE=<stage issue>`. The prompt has a section "Run notes": the orchestrator's notes on the current run (escalations, guard and classifier denies, outages, collisions, anything unusual), or one line saying nothing unusual happened. The planner posts one comment on the stage issue with the first line `## Planner: STAGE REVIEW`. Then the loop stops, and the final report names the stage review.

- When any sub-issue of the stage is open (for example escalated with `needs-owner`, waiting on a blocker, or `later`), the stage has not ended: no planner launch, and the loop picks the next eligible sub-issue, or stops when none is eligible (see "Next step while a stage is active").
- When the stage issue already has a stage review from an earlier run (an owner comment with the first line `## Planner: STAGE REVIEW`), the orchestrator does not launch the planner again. The final report names that review.
- When the planner ended without a result (a miss), the orchestrator launches the planner once more. When the planner step gives no stage review after the second miss in a row, or gives a result in another form, the orchestrator escalates the stage issue and stops. A planner launch is not a return.
- The orchestrator does not close the stage issue. The planner closes it at stage set-up.

The details are in "Stage end" in `docs/team/orchestrator.md`.

## Rules

- Do not skip step 2
- The engineer does not close the issue
- QA does not fix the code. It only posts a result marker: `## QA: PASS`, `## QA: FAIL`, `## QA: UNVERIFIABLE` or `## QA: INVALID` (`qa-codex` or the fallback `qa-engineer`, see `docs/team/qa-engineer.md`), or `## QA: UNAVAILABLE` (only `qa-codex`, see `docs/team/orchestrator.md`)
- The orchestrator closes the issue only after QA outputs PASS, and only if the SHA that QA verified is the current `HEAD`
- A return is a QA FAIL, a QA UNVERIFIABLE or an engineer BLOCKED. After 3 returns on the same issue, escalate the issue: the team could not settle it inside the current intent and scope, so the owner decides whether to change them. The count starts after the newest `## Owner: RESUME` comment
- A launch that Claude Code denied before it ran (the hook posts `## Launch not started: …`) or that an auto mode outage stopped (the hook posts `## Launch stopped by outage: …`) is not pending and not a return
- A launch that ended without a result of its role (and with no `## Owner: RESUME` after it) is a miss, and the issue is pending. After one miss, the orchestrator continues that agent with `SendMessage` or launches the same role once more, without the owner (`qa-codex` and the planner only get a new launch); the hook denies a call of any other role. Only two misses in a row of the same role escalate the issue to the owner. A miss is not a return
- If the PM posts `## PM: NEEDS OWNER`, escalate the issue
- `## QA: UNVERIFIABLE` means QA could not check a criterion because of a tool or sandbox limit of the checker. The PM makes the criterion checkable with the same intent. When the only way needs a change that a filed issue can fix (also an edit of the project settings files (`.claude/settings*.json`), `.claude/hooks/` or the QA sandbox), the PM links that fix issue as a blocker and posts `## PM: WAITING`; a fix issue that edits hooks, settings or the QA sandbox gets `needs-owner`. The PM escalates (`## PM: NEEDS OWNER`) when making a criterion checkable changes its intent or scope, and in the other cases of the rule "A tool problem that an issue can fix" in `docs/team/pm.md`
- `## QA: INVALID` has other causes (for example no usable commit range, or retries used up) and is escalated
- Denied action (PM, engineer, QA fallback `qa-engineer`): when a tool call you need gets a deny with a verdict (an auto mode classifier judgment such as "Instruction Poisoning", or `Permission denied`) and you do not retry it, do not end without a result. Post your result marker and quote the deny message (redact secrets):
  - PM: when a filed issue can fix the cause (a change in this repo, or an open issue in any repo), link that fix issue as a native blocker and post `## PM: WAITING` (rule "A tool problem that an issue can fix" in `docs/team/pm.md`). The PM files the fix issue itself when none exists, as a follow-up with `later`; it also gets `needs-owner` when the fix edits `.claude/hooks/`, the project settings files in `.claude/` or `QA_SANDBOX` in `scripts/qa-codex`. `## PM: NEEDS OWNER` only when the owner alone can resolve the cause outside this repo (for example a missing user-level Auto mode allow entry), no filed issue can fix it, it needs a change of intent, scope or money, the call that files the fix issue or adds the blocker link is denied too, or the fix issue was closed without a fix; name what the owner must decide
  - Engineer: `## Engineer: BLOCKED`
  - QA fallback: `## QA: UNVERIFIABLE`, and mark each affected criterion `- [ ] … - INVALID` with the deny message

  A guard deny that names a way around (for example the `G1` deny: the exact command forms as the whole command, `run_in_background` instead of `&`, or text that only mentions the words, such as a body written with a quoted here-document `<<'EOF'`) is not a denied action: retry that way first. The rule does not apply to an outage deny (the reason's first line starts with `Classifier unavailable`, `Auto mode could not evaluate this action and is blocking it for safety` or `Auto mode unavailable`): then post no result and end, so the `SubagentStop` hook posts `## Launch stopped by outage: …` and the orchestrator launches the same step again without the owner. The one case where no result can be posted: the comment call is denied too. Then end without a result; the launch stays pending (a miss), and the orchestrator launches the same step once more, and escalates on the second miss in a row. The difference: a deny with a verdict leads to a result by the agent, an outage deny leads to a stop comment by the hook, and a denied comment call leaves the issue pending
- Only comments whose `authorAssociation` is `OWNER` count; other comments are ignored (a stranger's `## Owner: RESUME`, result marker or launch comment changes nothing). Missing author data is an error: the guard denies the call. The agents and hooks post with the owner's `gh` login, so their comments count
- Agents post issue comments only with `gh issue comment <n> --body-file <literal path>` as the whole command, with the body written to a file with a literal absolute path first. Each body gets its own path: `/tmp/<role>-<issue>-attempt<n>.md` for a launched role, where `<n>` is the number of its newest `## Launch: <role> (…)` receipt on the issue, and `/tmp/<role>-<issue>-<UTC time>.md` (time from `date -u +%Y%m%dT%H%M%S`) for the orchestrator and the planner in the main session, which have no receipt. The agent writes the file fresh, reads it back with `cat <path>` as its own call right before the post, and posts only when the first line is the intended one and no placeholder text is left. The same holds for bodies passed with `--body-file` to `gh issue create` and `gh issue edit`. The details are in "Body files" of each role file in `docs/team/`. This is a rule, not a check.
- Agents never post a `## Owner: …` comment on their own. This is a rule, not a check
- The owner posts `## Owner: RESUME` on the GitHub web page, in a terminal, or from a Claude Code session with the exact form `gh issue comment <n> --body-file <literal path>`
- The resume match: a comment's first line is the owner's resume marker when it is `## Owner: RESUME` after leading and trailing whitespace is removed, each run of whitespace inside (spaces, tabs, CR) counts as one space, and letter case is ignored. So `## OWNER: Resume` counts; `## Owner: RESUME later`, `# Owner: RESUME` and `##Owner: RESUME` do not. Every mention of `## Owner: RESUME` as a comment on the issue means a comment that passes the resume match. All other markers match exactly. The escalation comment names the exact line `## Owner: RESUME` to copy
- Before the next issue, the working tree must be clean (`git status --porcelain` is empty). If not, stop the whole loop and ask the owner

## Escalation

- The owner is asked only for decisions that are really the owner's: money, settings, or a change of intent or scope. Everything else is resolved inside the team: the engineer asks the PM with `## Engineer: BLOCKED`, and the PM clarifies the issue. An issue that must wait for other open issues is not an owner decision either: the PM adds them as native "blocked by" links (also issues in other repos) and posts `## PM: WAITING`. The issue keeps `ready`, the pick skips it while it has an open blocker, and it goes back to the PM when all its blockers are closed. Nor is a role agent stopped by an auto mode outage: a hook marks the launch, and the orchestrator launches the same step again.
- A tool problem with a fix issue is not an owner decision on the blocked issue either. When a deny with a verdict or a QA limit can be fixed by a filed issue, the PM links the fix issue as a blocker and posts `## PM: WAITING` (rule "A tool problem that an issue can fix" in `docs/team/pm.md`). The blocked issue keeps `ready` and goes back to the PM when the fix issue is closed, with no `## Owner: RESUME`. This applies only to a deny with a verdict and to QA limits; an outage deny is unchanged (the agent posts no result and ends, and the hook posts `## Launch stopped by outage: …`).
- A fix issue that edits `.claude/hooks/`, the project settings files in `.claude/` or `QA_SANDBOX` in `scripts/qa-codex` has the label `needs-owner`. The owner decides on the fix issue, not on the blocked issue, in one of three ways:
  - remove `needs-owner` to approve it: it is then a parked issue, and the orchestrator promotes it when it blocks a sub-issue of the active stage
  - make the change and close the fix issue
  - close the fix issue as not planned: the blocked issue then goes back to the PM, which posts `## PM: NEEDS OWNER` and names the closed fix issue
- The orchestrator comments the reason, removes the label `ready`, and adds the label `needs-owner`. Then it continues with the next issue.
- The owner answers with a comment whose first line passes the resume match (see Rules), removes `needs-owner`, and adds `ready` again.
- A stage issue never has `ready`. When a stage issue is escalated, the orchestrator only adds `needs-owner`. The owner answers with `## Owner: RESUME`, removes `needs-owner`, and does not add `ready`.
- After `## Owner: RESUME`, the issue goes back to the PM. The PM applies the edits of the issue that this owner comment asks for (see `docs/team/pm.md`).
