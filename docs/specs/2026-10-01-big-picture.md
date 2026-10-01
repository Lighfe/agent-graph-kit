# Where the big picture of the work lives

Issue: #83. Date: 2026-10-01.
Status: proposal, owner decides
Inputs: the research report `docs/research/big-picture-and-lean-docs.md` (sections 2, 7 and 9) and the spike report `docs/research/spike-github-issue-dependencies.md` (#80).

This proposal says where the goals, the order of work, the dependencies, the priority and the stages of this kit's work are kept, how new work that comes up mid-stream is placed, and how a `/goal` loop moves from one set of work to the next without the owner. Nothing here changes the process, the role files, the hooks or any issue. The owner decides; the follow-up work is listed at the end.

## Summary of the recommendation

- **One place: GitHub issue fields.** No roadmap file, no dependency table in a plan, no second copy.
- **A stage is a stage issue:** an open issue with the label `stage`, whose body states the stage goal. Its sub-issues are the work of the stage. Stages are ordered by native "blocked by" links between stage issues.
- **Order inside a stage:** native "blocked by" links first, then the position in the stage issue's sub-issue list.
- **A stage ends** when every sub-issue is closed. The orchestrator then closes the stage issue, and the next stage issue has no open blocker any more: it is the new active stage, and the orchestrator adds `ready` to its sub-issues.
- **Follow-ups are parked:** label `later`, no parent, and a `Source:` line with the URL of the comment or file they came from. Only one rule promotes a parked issue without the owner: it is a native blocker of an issue in the active stage.
- **Native "blocked by" links replace the `Waiting on: #<N>` line** and the `waiting` label, read with the REST form that gives repo, number and state in one call.

The six questions below give the options and reasons.

## 1. Where the order of work and the dependencies are kept

Recommended: **GitHub issue fields**, owner decides.

- Dependencies: native "blocked by" links (`gh issue edit <n> --add-blocked-by <number or URL>`).
- Group (stage): the parent issue (sub-issue link, `gh issue edit <n> --parent <stage>`).
- Order of stages: native "blocked by" links between stage issues.
- Order inside a stage: blockers first, then the position in the parent's sub-issue list.
- Priority: not a separate field. Priority is the order. An urgent issue is moved to an earlier position or into the active stage.

No second copy is kept. A plan in `docs/plans/` is input for intake only: once its tasks are issues with these fields, the plan's dependency table is not read again and not updated. A proposal file such as the backlog sorting of #85 is input for one set of edits, not a copy that is kept current.

Rejected options:

- One roadmap file in the repo (GSD Core's `ROADMAP.md`): the loop already reads its state from the issues, so a file would be a second copy of the order; research section 2.1 shows GSD itself ends up with two copies when it is driven from a tracker.
- Milestones as stages: `gh` 2.98.0 has no `milestone` command (create needs `gh api`), milestones have no order field and no comments, and a repo that adopts the kit may already use milestones for releases; research section 4 found no 2026 report of a loop using them.
- Labels such as `stage:<name>` or `p1`/`p2` for group and priority: a label has no order and no state of its own, so the loop could not tell when a stage is done or which comes next.
- No stages, only the dependency graph (Symphony, Beads): there would be no unit that the owner approves as a whole, so every issue would again need its own `ready` from the owner.

Reason: P3 says state lives on the issue and is read with `gh`. Native links and sub-issues are fields that `gh` reads in one call per issue (spike, cases 1 to 3; `gh issue view --json parent,subIssues,subIssuesSummary`), and research section 2.1 found that every source keeps order and dependencies in one place a program can query, never in a prose plan after work starts.

## 2. What a stage is, what ends it, and how the next one starts

Recommended: **a stage is a stage issue with sub-issues; it ends when all sub-issues are closed**, owner decides.

A stage is a set of work with one goal. It is recorded as one issue:

- label `stage`, never `ready`, so G1 never launches a role on it;
- body: the goal of the stage in one or two sentences, and the stage's exit check (by default the one below);
- sub-issues: the issues that belong to the stage;
- blocked by: the stage issue that must end first (none for the first stage).

The **active stage** is the open stage issue with no open blocker. If several open stage issues have no open blocker, the active stage is the one with the lowest number; running them in parallel is a later question for parallel mode (#18).

**Exit check** (facts only, read with `gh`): every sub-issue of the stage issue is closed. Escalated issues are open, so a stage with an escalated issue does not end.

**How the next stage starts**, all done by the orchestrator before each pick:

1. If the active stage passes the exit check, the orchestrator posts a stage result comment on the stage issue (which issues were closed, which commit was `HEAD`) and closes the stage issue.
2. The next stage issue now has no open blocker, so it is the active stage.
3. The orchestrator adds `ready` to each open sub-issue of the active stage that has neither `later` nor `needs-owner`.
4. The pick takes the first sub-issue of the active stage, in sub-issue order, that has `ready` and no open blocker.

Rejected options:

- A milestone with an exit check (GSD Core): rejected for the reasons in question 1.
- An exit check that also runs QA against stage-level criteria (Anthropic's sprint contract): `qa-codex` reads its commit range from an `## Engineer: DONE` comment, which a stage issue does not have; it can be added later if the fact check proves too weak.
- No stages (only the dependency graph): rejected in question 1.

Reason: the stage issue keeps the goal, the members, the order and the result on GitHub, where the hooks already read state (P3). The exit check is a count of closed issues (P2). The owner approves a whole stage once, by its sub-issues, instead of one `ready` per issue, and the loop can then move from stage to stage on its own.

## 3. When the loop asks the owner, and what it decides on its own

Recommended: **the owner plans stages; the loop runs them**, owner decides.

The loop decides on its own:

- the pick order inside the active stage (question 2);
- closing a stage that passed the exit check, and starting the next one;
- adding `ready` to the sub-issues of the active stage;
- parking new follow-ups (question 4);
- promoting a parked issue that is a native blocker of an issue in the active stage (question 4);
- waiting on an open blocker, without escalation (question 5).

The loop asks the owner (escalation as today: comment, `needs-owner`):

- every case that `docs/process.md` already escalates: money, settings, a change of intent or scope, 3 returns, `## PM: NEEDS OWNER`, `## QA: INVALID`, a pending launch;
- a blocker that cannot be read (for example a link to a repo the `gh` login cannot see, spike limit 7).

The loop stops and reports to the owner, without escalating an issue, when:

- the active stage cannot end because only escalated or blocked sub-issues are left; the next stage does not start, because its stage goal may depend on the unfinished one;
- no open stage issue is left, or the active stage has no sub-issues: there is no planned work.

Only the owner creates a stage issue, changes its goal, reorders stages, and moves a parked issue into a stage for any reason other than the blocker rule.

Rejected options:

- The owner adds `ready` to each issue (today's `docs/process.md`): the owner reports that they do not want to order the work issue by issue (research section 6.1, finding 7).
- The loop also plans the next stage from the parked issues when no stage is left: choosing what to build next is a change of scope; the loop may at most write a proposal file for the owner (a later option, listed in the follow-up work).
- The loop goes on to the next stage while the active stage has an escalated issue: the next stage may build on the unfinished goal, and skipping it would hide the escalation.

Reason: the owner's decisions stay the ones `docs/process.md` already names (money, settings, intent or scope). Planning a stage is a scope decision, so it stays with the owner; running a planned stage is not.

## 4. How follow-up issues are placed

Recommended: **parked by default, promoted only by the blocker rule or by the owner**, owner decides.

Who files follow-ups: the PM (out-of-scope items while grooming), the owner after a review (for example a Codex review), and the orchestrator for a side finding. Each follow-up gets:

- **a link to its source:** one line `Source: <URL>` in the body, where the URL is the comment, the review file or the issue it came from. GitHub has no "discovered from" link type, so the body line is the link; a mention of the source issue also shows on that issue's timeline.
- **the parked state:** label `later`, no parent (no stage). G1 already denies every launch on `later`.
- **no blocker links of its own**, unless the filer knows them.

Promotion into the active work:

- **Blocker rule (no owner):** when the PM finds that an issue of the active stage needs a parked issue first, it adds a native "blocked by" link from the active issue to the parked one and posts `## PM: WAITING`. Before the next pick, the orchestrator promotes every open parked issue that blocks an open sub-issue of the active stage: it sets the stage issue as parent, places the issue directly before the issue it blocks, removes `later` and adds `ready`. The issue is then groomed like any other. The scope does not grow beyond what the active stage needs, because the PM decided the issue is required for an issue already in the stage.
- **Owner:** every other promotion. The owner moves a parked issue into a stage (or a sorting proposal like #85 suggests it and the owner applies it).

A parked issue in another repo is never promoted; it stays a blocker that is waited on (question 5).

Rejected options:

- The owner promotes every follow-up (Symphony's `Backlog` → `Todo`): it keeps the owner as the one who orders work, which the owner does not want; it also stops the loop whenever a needed blocker is parked.
- The PM promotes any follow-up it judges important: that is a scope decision by judgment, not by a fact, and it is the owner's (`docs/process.md`, Escalation).
- Follow-ups go straight into the active stage: the stage would grow without a check, and research section 2.2 found that every source keeps a parked state for new work.

Reason: research pattern P3 (parked state plus provenance) with a promotion rule that is a fact (a native blocker link from an active issue), so the orchestrator can apply it without judgment (P2).

## 5. Native "blocked by" links instead of `Waiting on: #<N>`

Recommended: **yes, native links replace the `Waiting on: #<N>` line and the `waiting` label**, owner decides.

How it works:

- The PM adds the blocker as a native link (`gh issue edit <n> --add-blocked-by <number or URL>`) and posts `## PM: WAITING`. It names the blockers in the comment for the reader, but the links are the only copy that is read.
- An issue may have several blockers and blockers in other repos. It is unblocked when **every** blocker is closed. This answers the open questions of #64.
- The orchestrator does not park the issue with a label. Its pick skips every issue with an open blocker, and G1 denies a launch on an issue with an open blocker instead of checking the `waiting` label.
- After `## PM: WAITING`, the issue goes back to the PM when all its blockers are closed (G2 reads the blockers instead of the line).

The limits from the spike's "Limits found" section and how this proposal handles them:

- **Limit 1, no repo field in `gh issue view --json blockedBy`.** The guard and the orchestrator read blockers with form B, `gh api repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by --paginate --jq '.[] | {repo: .repository.full_name, number, state}'`, which gives repo, number and state in one call. Form A is not used for decisions.
- **Limit 2, upper and lower case of `state`.** Only form B is used, so the state is always lower case (`open`, `closed`). Any other value denies with `guard error`, as today.
- **Limit 3, the 30-row default of `gh issue list`.** Every list the loop uses passes `--limit 200`, and the orchestrator escalates when a list returns exactly the limit.
- **Limit 4, search index lag, and limit 5, `is:blocked` seen in three tries only.** The loop never uses the search qualifiers `is:blocked` or `-is:blocked` for a decision. It reads the blockers of each candidate issue with form B, which showed new links at once.
- **Limit 6, paging.** Form B is always called with `--paginate`.
- **Limit 7, no test of a repo the login cannot see.** A failing blocker read is not "no blocker": the guard denies with `guard error` and the orchestrator escalates the issue.

Rejected options:

- Keep the one-line `Waiting on: #<N>` (today): it holds one same-repo blocker only (#64), and it would be a second copy next to the native links that intake and sorting will add.
- Keep both, the line and the links: two copies that can disagree.
- Keep the `waiting` label as a cache of "has an open blocker": a second copy that the orchestrator must keep in step; one form B read per candidate issue is cheap.

Reason: the spike showed that one `gh` call returns every blocker with repo, number and state, including closed and cross-repo blockers. Reading those facts directly fits P2 and P3 and removes a line format and a label.

## 6. How the choice works in another repo that adopts the kit

Recommended: **the same GitHub fields in every repo; the kit checks them at set-up**, owner decides.

- The kit's set-up (#14 packaging, #15 adoption) creates the labels `ready`, `later`, `needs-owner` and `stage` and checks two facts with read-only calls: `gh --version` is at least 2.98.0 (the version the spike used for `--add-blocked-by`), and `gh api repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by` answers for one existing issue. If a check fails, set-up stops with the message; there is no fallback to a file.
- Stage issues are ordinary issues, so a repo that already uses milestones for releases keeps them; the kit does not touch milestones.
- Cross-repo blockers work as in the spike (case 2): an issue in the adopting repo can wait on an issue in the kit's repo or in a third repo, as long as the `gh` login can read it (limit 7).
- A repo that keeps its work in another tracker (Linear, Jira) is out of scope: P3 says the state is read with `gh`.
- A repo with no stage issue yet starts with one stage issue that the owner creates for the first set of work.

Rejected options:

- A per-repo choice between issue fields and a roadmap file: two code paths in hooks and role files, against P4.
- Milestones in adopting repos: they may already mean releases there (question 1).

Reason: the kit is a Claude Code plugin for GitHub repos, and every field it uses is part of GitHub issues and `gh`, with no extra file in the adopting repo (P4).

## Form of one issue's group, order and blockers

The form has three fields on the issue, plus the parked state for follow-ups:

| What | Where it is recorded | Write with | Read with |
|---|---|---|---|
| Group (stage) | Parent issue with label `stage` | `gh issue edit <n> --parent <stage>` | `gh issue view <n> --json parent` |
| Place in the order | Position in the parent's sub-issue list; blockers come first | `gh issue edit <stage> --add-sub-issue <n>` (appends; reordering is in the follow-up work) | `gh issue view <stage> --json subIssues` |
| Blockers | Native "blocked by" links | `gh issue edit <n> --add-blocked-by <number or URL>` | form B (question 5) |
| Parked | Label `later`, no parent, `Source: <URL>` line | `gh issue edit <n> --add-label later` | `gh issue view <n> --json labels,parent,body` |

In a proposal file (such as the backlog sorting of #85), one issue is written as one line in this form, so it can be applied with the commands above:

```
#<n> -> stage #<stage>, position <k>, blocked by <none | #<a>, owner/repo#<b>>
#<n> -> parked, source <URL>
```

Synthetic example, in repo `example-org/example-app` (all numbers made up):

- Stage issue #200 "Stage: sign-up works end to end", label `stage`, blocked by #150 (the previous stage).
- Issue #212 "Send the confirmation e-mail", second of the three sub-issues of #200, blocked by #211 (same repo) and `example-org/mail-lib#7` (another repo).

As one line:

```
#212 -> stage #200, position 2, blocked by #211, example-org/mail-lib#7
```

As the loop reads it:

```
$ gh issue view 212 --json parent --jq .parent.number
200
$ gh issue view 200 --json subIssues --jq '[.subIssues.nodes[].number]'
[211,212,213]
$ gh api repos/example-org/example-app/issues/212/dependencies/blocked_by --paginate --jq '.[] | {repo: .repository.full_name, number, state}'
{"number":211,"repo":"example-org/example-app","state":"closed"}
{"number":7,"repo":"example-org/mail-lib","state":"open"}
```

#212 belongs to stage #200, comes after #211, and is still blocked because `example-org/mail-lib#7` is open. The pick skips it and takes #213 if that has no open blocker.

A parked follow-up of #212:

```
#230 -> parked, source https://github.com/example-org/example-app/issues/212#issuecomment-1000001
```

## Fit with the kit principles

From `docs/specs/2026-09-25-agent-graph-kit-v1.md`, section "2. Principles":

- **P1, prose guides, hooks check.** The rules for stages, the pick order, parking and the blocker promotion are written in `docs/process.md` and the role files. The hooks check only facts at the guarded calls: a launch is denied on an issue with an open blocker or with the label `stage`, and closing a stage issue is allowed only when all its sub-issues are closed.
- **P2, facts only.** Every decision of the loop reads a fact: a label, a parent link, a sub-issue position, a blocker's state, a count of closed sub-issues. The only judgments, which issue blocks which and what belongs in a stage, are made by the PM while grooming or by the owner while planning, never by a hook.
- **P3, state lives on the issue.** The goal, members, order and result of a stage live on the stage issue; the blockers live as native links; the source of a follow-up lives in its body. Everything is read with `gh`. Nothing depends on what the orchestrator remembers, and no roadmap file exists.
- **P4, few files.** The proposal adds no agent-facing file. The changes go into the existing `docs/process.md`, role files and hooks. An adopting repo gets one more label (`stage`) and no file.

## Follow-up work

If the owner accepts the proposal, it needs this work. These are items in this file, not issues.

- **Spike:** check that `gh issue view <stage> --json subIssues` returns the sub-issues in the order shown on GitHub, and find a `gh` form that moves a sub-issue to a given position (gh 2.98.0 `--add-sub-issue` appends). If the order is not readable, use blockers plus issue number as the order instead.
- **Spike:** limit 7 of #80, a blocker in a repo the `gh` login cannot see, and paging of form B with more than one page.
- **`docs/process.md`:** stages, the active stage, the exit check, the pick order, the parked state with `Source:`, the blocker promotion rule, the new stop conditions; change "the owner adds `ready`" to "the owner plans stages; the loop adds `ready` in the active stage"; replace the `waiting` text in Escalation.
- **`docs/team/orchestrator.md`:** "Before each issue" (stage exit check, stage close, next stage, `ready` for the active stage, blocker promotion) replaces "free the waiting issues"; the pick order; the `## PM: WAITING` row in "Decisions at each edge"; the final report per stage (#77).
- **`docs/team/pm.md`:** add native blocker links instead of the `Waiting on:` line; file follow-ups with `later` and `Source:`.
- **`docs/task-template.md`:** an optional `Source:` line.
- **Hooks (`.claude/hooks/`) and their tests:** G1 denies on an open native blocker (form B) and on the label `stage` instead of checking `waiting`; G2 reads native blockers instead of the `Waiting on:` line; the close check allows `gh issue close` on a `stage` issue when all its sub-issues are closed; every list call uses `--limit`.
- **Spec `docs/specs/2026-09-25-agent-graph-kit-v1.md`:** sections 5 and 10 (the `waiting` and `later` text), or the spec that replaces them, depending on the doc-lifecycle proposal (#84).
- **Labels:** create `stage`; retire `waiting` after the hook change.
- **Issues:** #64 (several or cross-repo blockers) becomes obsolete or is rewritten as the hook change above; #85 sorts the backlog in the form above; #14 and #15 take the set-up checks of question 6; #18 (parallel mode) may later allow several active stages.
- **Later option:** when no stage is left, the loop launches the PM to write a proposal for the next stage from the parked issues, which the owner accepts or not.

## Sources

Besides the research report and the spike report:

- Kit spec v1, `docs/specs/2026-09-25-agent-graph-kit-v1.md`, dated 2026-09-25, read at commit `0f5e8f4` on 2026-10-01: [link](2026-09-25-agent-graph-kit-v1.md)
- Process, `docs/process.md`, read at commit `0f5e8f4` on 2026-10-01: [link](../process.md)
- Orchestrator role, `docs/team/orchestrator.md`, read at commit `0f5e8f4` on 2026-10-01: [link](../team/orchestrator.md)
- PM role, `docs/team/pm.md`, read at commit `0f5e8f4` on 2026-10-01: [link](../team/pm.md)
- Issue #64 "Waiting on a blocker in another repo, or on several blockers", read 2026-10-01: https://github.com/Lighfe/agent-graph-kit/issues/64
- Issue #85 "Proposal: sort the open backlog", read 2026-10-01: https://github.com/Lighfe/agent-graph-kit/issues/85
- `gh` 2.98.0 (2026-08-20) help output of `gh issue create`, `gh issue edit` and `gh issue view` (flags `--parent`, `--add-sub-issue`, `--add-blocked-by`, `--milestone`; JSON fields `parent`, `subIssues`, `subIssuesSummary`), read 2026-10-01: https://github.com/cli/cli/releases/tag/v2.98.0
