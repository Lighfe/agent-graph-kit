# Sorting the open backlog

Issue: #85. Date: 2026-10-01.
Status: proposal, owner decides
Inputs: the big-picture proposal `docs/specs/2026-10-01-big-picture.md` (#83) and the doc-lifecycle proposal `docs/specs/2026-10-01-doc-lifecycle.md` (#84), used as they are, as a form to write in and not as accepted rules.

This file gives every open issue with the label `later` one outcome: close, merge into another open issue, keep in a proposed stage, or keep parked. Nothing here changes an issue. Applying the outcomes the owner accepts is #91.

How to read an outcome line:

- `#<n> -> close, ...`: close the issue, with the reason.
- `#<n> -> merge into #<m>, ...`: move what is still open into issue `#<m>`, then close `#<n>`.
- `#<n> -> stage "<stage name>", position <k>, blocked by <...>`: the form of the big-picture proposal (section "Form of one issue's group, order and blockers"). No stage issue exists yet, so a stage has a short name in place of `#<stage>`.
- `#<n> -> parked, source <URL>`: stays `later`, with no parent. `source unknown` when the issue text gives no source.

Every reason uses only the issue text, its comments, the repo files and git history. Where that evidence is not enough to choose, the outcome is "keep parked", and the reason says what is missing.

## The list

Command, run on 2026-10-01 (UTC) at base commit `d5f9a09`:

```
gh issue list --state open --label later --limit 200
```

Full output (number, state, title, labels, last update):

```
91	OPEN	Apply the accepted outcomes of the backlog sorting proposal	later	2026-10-01T13:25:57Z
89	OPEN	Codex QA cannot check criteria about GitHub state	later	2026-10-01T11:08:14Z
88	OPEN	Live check: the PM applies an issue edit from an Owner RESUME in Auto mode	later	2026-10-01T11:01:00Z
87	OPEN	Carry out the chosen doc lifecycle (moving, archiving, deleting docs)	later	2026-10-01T10:47:53Z
86	OPEN	Guard: false denies by G8 and G9	later	2026-10-01T09:55:42Z
79	OPEN	Guard: recognize the owner's typed prompt for Owner marker comments	later	2026-09-30T20:36:42Z
77	OPEN	Make the final loop report actionable for the owner (v2)	later	2026-10-01T09:57:07Z
76	OPEN	Check Owner markers on comment routes outside gh issue comment	later	2026-09-30T17:36:21Z
75	OPEN	Owner-only marker rule for organization-owned repos	later	2026-09-30T14:43:12Z
74	OPEN	Trust the issue body only when the owner's account wrote it	later	2026-09-30T14:43:10Z
66	OPEN	Choose the model and effort per role or task	later	2026-09-30T09:51:26Z
65	OPEN	Guard: go on after the G1 two-launch outage stop without an owner RESUME	later	2026-09-30T09:22:53Z
64	OPEN	Waiting on a blocker in another repo, or on several blockers	later	2026-10-01T09:56:58Z
63	OPEN	README: Lovable project knowledge entry as a frontend lane set-up step	later	2026-09-30T08:49:28Z
61	OPEN	Process: tasks whose change is in another repo	later	2026-10-01T09:57:00Z
54	OPEN	Make the hook activation checklist usable in a new project	later	2026-09-28T09:31:00Z
53	OPEN	Guard: launches stopped before start without a PermissionDenied event still leave the issue pending	later	2026-09-28T09:26:16Z
47	OPEN	Codex QA: prepare the test command of a target repo	later	2026-09-28T08:33:32Z
46	OPEN	README: Lovable project id line in AGENTS.md	later	2026-09-28T08:24:22Z
45	OPEN	Check that frontend-engineer reaches the Lovable tools	later	2026-09-28T08:24:21Z
44	OPEN	Guard may read stale issue comments	later	2026-09-28T08:05:07Z
32	OPEN	Optional local telemetry	later	2026-09-26T16:19:02Z
31	OPEN	Link launch comments to runtime ids	later	2026-09-26T16:19:01Z
30	OPEN	QA run record in qa-codex	later	2026-09-26T16:18:59Z
29	OPEN	Record escaped defects	later	2026-09-30T09:51:35Z
28	OPEN	Process report over issue comments	later	2026-09-26T16:18:57Z
27	OPEN	Codex sandbox and headless browser on macOS	later	2026-09-26T12:48:13Z
26	OPEN	On-call loop	later	2026-09-26T16:19:09Z
25	OPEN	CI/CD set-up and deploy skills	later	2026-09-25T14:39:46Z
24	OPEN	CI in the close gate	later	2026-09-25T14:39:44Z
23	OPEN	Independent test design by QA	later	2026-09-25T14:39:43Z
22	OPEN	Config levels for small projects	later	2026-09-25T14:39:42Z
21	OPEN	Codex as an engineer lane	later	2026-09-25T14:39:40Z
20	OPEN	Required review before intake	later	2026-10-01T09:57:03Z
19	OPEN	Role limits through Bash	later	2026-09-25T14:39:36Z
18	OPEN	Parallel mode (worktrees)	later	2026-10-01T09:57:02Z
17	OPEN	Separate Reviewer role	later	2026-09-25T14:39:33Z
16	OPEN	Doc decluttering ("librarian")	later	2026-10-01T09:56:56Z
15	OPEN	Adopting the kit in existing projects	later	2026-10-01T09:57:06Z
14	OPEN	Packaging: Claude Code plugin + init command	later	2026-10-01T09:57:04Z
13	OPEN	Jev at the handoffs	later	2026-09-25T14:39:28Z
```

Count: 41 issues. The output is below the limit of 200, so the list is complete. #85 itself has the label `ready`, not `later`, so it is not in the list.

## Proposed stages

In this order. A stage starts only when the stage before it has ended.

| Order | Stage name | Goal | Must end before it starts |
|---|---|---|---|
| 1 | "Planning model" | The outcomes the owner accepts from this file and from the big-picture proposal are on the issues, the loop reads blockers from native "blocked by" links, and Codex QA can check criteria about GitHub state. | none |
| 2 | "Doc lifecycle" | The doc lifecycle the owner accepts from the doc-lifecycle proposal is carried out: docs are split, moved, archived or deleted, and the fact checks and the stage-end audit are in place. | "Planning model" |

Why this order: the doc-lifecycle proposal ties its stage-end audit to the stage model ("depends on the stage model of #83", follow-up item for `docs/team/orchestrator.md`), so the stage model comes first.

Both stages exist only if the owner accepts the matching proposal. If the owner rejects a proposal, the issues of its stage go back to parked.

Every other issue stays parked. The proposals do not make them part of the next work, and most of them state their own condition ("before building", "add only if", "only with evidence", "to be groomed when the owner picks this up"), which no fact in the repo or on the issues meets yet.

## Outcomes

One line per issue, in the order of the list.

### #91 Apply the accepted outcomes of the backlog sorting proposal

```
#91 -> stage "Planning model", position 2, blocked by #89
```

Reason: #91 applies the outcomes of this file once the owner has decided, which is the first step of the big-picture proposal's follow-up ("#85 sorts the backlog in the form above"). Every criterion of #91 is about GitHub state (closed issues, labels, parents, blocker links), and Codex QA cannot read GitHub state (#89, which cost one return each on #83 and #84). So #89 comes first.

### #89 Codex QA cannot check criteria about GitHub state

```
#89 -> stage "Planning model", position 1, blocked by none
```

Reason: the issue records a return on #83 and on #84 for the same cause on 2026-10-01, and #91 and the hook change in #64 will have criteria about GitHub state (issue edits, labels, blocker links). Without #89 each of them is likely to come back `## QA: UNVERIFIABLE`.

### #88 Live check: the PM applies an issue edit from an Owner RESUME in Auto mode

```
#88 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/73
```

Reason: a live check in the owner's environment of what #73 documented. No issue of the proposed stages needs it first. Missing for a promotion: an issue whose work depends on the PM applying such an edit in Auto mode.

### #87 Carry out the chosen doc lifecycle (moving, archiving, deleting docs)

```
#87 -> stage "Doc lifecycle", position 1, blocked by none
```

Reason: the doc-lifecycle proposal names #87 as the issue that carries it out ("most of them belong to issue #87"). This agrees with the proposal. #87 says it will be split into smaller issues from the proposal's follow-up list once the owner decides; those issues would join this stage after #87's grooming.

### #86 Guard: false denies by G8 and G9

```
#86 -> parked, source unknown
```

Reason: the G9 half is done elsewhere: G9 was removed by #90 (hook commit `9e56e83`, docs commit `d5f9a09`). The G8 half stays, and the issue itself says it needs evidence: a count of false G8 denies of role agents in real loop runs ("Three denies in one owner session are not enough on their own"). That count does not exist yet. The issue names a research session on 2026-10-01 but gives no URL, so the source is unknown. When it is groomed, the title and goal should drop G9.

### #79 Guard: recognize the owner's typed prompt for Owner marker comments

```
#79 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/78
```

Reason: since #78 (no content check) and #90 (no G9), no hook checks `## Owner:` markers at all; the rule is prose only. #79 is the only issue that could bring a marker check back. Its criteria say "To be groomed when the owner picks this up", and nothing shows the prose rule failing. Missing: evidence that an agent posted an `## Owner: …` comment on its own.

### #77 Make the final loop report actionable for the owner (v2)

```
#77 -> parked, source unknown
```

Reason: the issue requires a brainstorming session with the owner "not inside the loop" and is "Planned for v2", so the loop cannot run it as stage work. The big-picture proposal links it to its follow-up ("the final report per stage (#77)"), which is an input when the owner plans it. The background names the loop on #72, #69 and #50 but no URL, so the source is unknown.

### #76 Check Owner markers on comment routes outside gh issue comment

```
#76 -> merge into #79, the checks it asks about only matter if a marker check exists again
```

Reason: #76 asks which routes besides `gh issue comment` need an `## Owner:` marker check like the one of #72. That check was dropped on `gh issue comment` itself (#78), and G9 is gone (#90). A check on the other routes (`gh api`, Codex, MCP tools) would be stricter than the main route, which has none. Both issues are about one question: whether a hook checks Owner markers again. #79 already names #76 as its out-of-scope neighbour, and #90 left the other routes "in #76", so its list of routes should move into #79 as a section, not be lost.

### #75 Owner-only marker rule for organization-owned repos

```
#75 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/70
```

Reason: it matters only for an organization-owned repo. This repo and `Lighfe/paint-math` are user-owned. Missing: an adopting repo that is owned by an organization (it would come up in #15).

### #74 Trust the issue body only when the owner's account wrote it

```
#74 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/70
```

Reason: an open design question ("Question for grooming") with no reported case of a stranger's issue reaching the loop. Missing: an owner decision on whether the guard and `scripts/qa-codex` should refuse such issues, which is a change of intent, not a fact.

### #66 Choose the model and effort per role or task

```
#66 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/archive/2026-09-24-brainstorm-handover.md
```

Reason: the issue states that it needs the record of escaped defects (#29) as evidence, and #29 is parked. The source is the brainstorm handover that the issue says it reopens. The doc-lifecycle proposal notes that #66 points into `docs/archive/` and must be checked against the reading rule when it is groomed; that note stands.

### #65 Guard: go on after the G1 two-launch outage stop without an owner RESUME

```
#65 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/52
```

Reason: the stop it changes still exists (`.claude/hooks/issue_state.py`, "the last 2 launches did not start or were stopped by an auto mode outage"), and the issue names owner feedback against click work on #39 and #43. No issue of the proposed stages needs it first, and the order against other parked work is a planning choice of the owner. Of all parked guard issues, it is the one with recorded owner feedback, so it is a candidate for the next stage the owner plans.

### #64 Waiting on a blocker in another repo, or on several blockers

```
#64 -> stage "Planning model", position 3, blocked by none
```

Reason: the big-picture proposal says #64 "becomes obsolete or is rewritten as the hook change above" (G1 denies on an open native blocker, read with form B; G2 reads native blockers instead of the `Waiting on:` line). This file picks "rewritten": the proposal answers #64's open questions (several blockers, other repos, all closed), but no other open issue holds the hook change, and #91 keeps hooks out of scope. When #64 is groomed, its goal becomes that hook change. It has no blocker: the hook change can be built and tested without the edits of #91.

### #63 README: Lovable project knowledge entry as a frontend lane set-up step

```
#63 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/62
```

Reason: not done (`README.md` has no project knowledge step). No issue needs it first, and #62 reached its goal without it. Missing: evidence that repeating the standing constraints in each Lovable message causes a problem.

### #61 Process: tasks whose change is in another repo

```
#61 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/60
```

Reason: its own constraint says "Only with evidence from more such tasks; until then, the rule per task in Constraints is enough". Two such tasks exist (#11, #60); no third. The comment on it says neither #80 nor #83 decides the `Commits:` rule.

### #54 Make the hook activation checklist usable in a new project

```
#54 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/10
```

Reason: still not done (`docs/checks/hook-activation.md` names #7 on lines 3, 7 and 241). But the doc-lifecycle proposal classes this file as a one-time runbook to archive (follow-up "Archive after use", part of #87), while `README.md` step 3 of the set-up still tells a new project to run it. The two cannot both hold. Missing: the owner's choice between archiving the checklist (then #54 is obsolete and the README step needs another set-up check, see #14 and #15) and keeping it as an adopter check (then #54 applies). See "Where the two proposals disagree".

### #53 Guard: launches stopped before start without a PermissionDenied event still leave the issue pending

```
#53 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/48
```

Reason: the issue says these stops are rare in Auto mode, and it lists only options, no reported case in a loop run. Missing: a loop run where such a stop left an issue pending.

### #47 Codex QA: prepare the test command of a target repo

```
#47 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/43
```

Reason: the only target repo so far, `Lighfe/paint-math`, uses the same test command as this repo (#11 sets `Test command: uv run --with pytest pytest`), and the frontend pre-steps came with #49, #58 and #59. Missing: a target repo with another test command; it would come up in #15.

### #46 README: Lovable project id line in AGENTS.md

```
#46 -> close, done elsewhere: README step in commit 6fad996 (#10), paint-math line in #11
```

Reason: criterion 1 is met by `README.md` (the step "Add the line `Lovable project: <id>` to `AGENTS.md`", added in commit `6fad996`, "Add README set-up section (#10)"). Criterion 2 is met by #11 (closed): its PM grooming says its criterion "also covers criterion 2 of #46", and the paint-math `AGENTS.md` has the line. The issue itself said it "can be folded into #10 and #11".

### #45 Check that frontend-engineer reaches the Lovable tools

```
#45 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/9
```

Reason: half answered elsewhere: the demo run #12 (closed) launched `frontend-engineer` five times on `Lighfe/paint-math#1` with `ToolSearch` in `tools:`, so the agent reaches the Lovable tools with it. Still open: whether it reaches them without `ToolSearch` (criterion 2). Missing: a reason to remove `ToolSearch`; no run reported a problem with it.

### #44 Guard may read stale issue comments

```
#44 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/40
```

Reason: the issue says "Not proven. This issue is parked until the owner decides to look into it." No later case is recorded on the issue.

### #32 Optional local telemetry

```
#32 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-26-agent-graph-observability.md#4-items
```

Reason: the observability spec (status "deferred") puts item 4.5 last, "after its checks". Nothing calls for it yet.

### #31 Link launch comments to runtime ids

```
#31 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-26-agent-graph-observability.md#4-items
```

Reason: the issue needs the owner's choice of variant (public ids in the comment or a private local map) before grooming. That choice is missing.

### #30 QA run record in qa-codex

```
#30 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-26-agent-graph-observability.md#4-items
```

Reason: the observability spec says it "needs nothing else" but sets no time for it. No issue needs it first.

### #29 Record escaped defects

```
#29 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-26-agent-graph-observability.md#4-items
```

Reason: the observability spec puts it first (with 4.1), and #17, #23 and #66 name it as their evidence. But none of those is in a proposed stage, so no stage needs it first. If the owner plans a stage with #17, #23 or #66, #29 belongs before them.

### #28 Process report over issue comments

```
#28 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-26-agent-graph-observability.md#4-items
```

Reason: the observability spec puts it first (with 4.3), and it would give the count of false denies that #86 asks for. No issue of the proposed stages needs it.

### #27 Codex sandbox and headless browser on macOS

```
#27 -> parked, source https://github.com/Lighfe/agent-graph-kit/issues/2
```

Reason: it applies "before the kit is recommended for macOS". Nothing records such a plan. Missing: an adopting setup on macOS.

### #26 On-call loop

```
#26 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: a separate graph for the product, out of v1 scope. No issue or doc names it as needed now.

### #25 CI/CD set-up and deploy skills

```
#25 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: one-line item of the v1 "Not in v1" table with no condition and no issue that needs it. Missing: a project that needs deploy skills.

### #24 CI in the close gate

```
#24 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: CI for this repo exists (`.github/workflows/ci.yml`), but the item "Needs a push rule", and no push rule exists. Missing: the owner's decision on a push rule.

### #23 Independent test design by QA

```
#23 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: "Add if QA often finds missing tests". The evidence for that would come from #28 or #29, which are parked.

### #22 Config levels for small projects

```
#22 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: one-line item with no condition. Missing: a small project that adopts the kit (#15).

### #21 Codex as an engineer lane

```
#21 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: one-line item with no condition and no issue that needs it.

### #20 Required review before intake

```
#20 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: "Decide after using the review skill on a few specs". `docs/reviews/` has 12 reviews, so the condition may be met, but the decision is the owner's. The comment on it keeps it separate from #84 (review output vs. whether a review is required).

### #19 Role limits through Bash

```
#19 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: one-line item with no condition. When it is groomed, note that the PM has no Write tool and writes its comment body files with Bash (see #90, which kept the Write tool out of scope), so "cannot write through Bash" must leave that path open. Missing: a reported case of a PM or QA writing or committing in the repo through Bash.

### #18 Parallel mode (worktrees)

```
#18 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: it changes every guarantee that assumes one HEAD. This agrees with the big-picture proposal, which says #18 "may later allow several active stages"; that is input for its grooming, not a reason to start it now.

### #17 Separate Reviewer role

```
#17 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: "Add only if QA passes work with real quality problems". The evidence would come from #29, which is parked.

### #16 Doc decluttering ("librarian")

```
#16 -> merge into #87, the doc-lifecycle proposal replaced it and #87 holds the work
```

Reason: this agrees with the doc-lifecycle proposal, which "replaces issue #16 as the place where this is decided" and rejects a single librarian role. What is left of #16 (finding and removing outdated docs) is the follow-up work of that proposal, which #87 carries out. Nothing new needs to move into #87 beyond a link to #16.

### #15 Adopting the kit in existing projects

```
#15 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: it agrees with the big-picture proposal: when it is groomed, #15 takes the set-up checks of its question 6 (labels `ready`, `later`, `needs-owner`, `stage`; `gh` at least 2.98.0; one blocker read). It stays parked because it needs #14 (packaging) or a decision to adopt without it, and no stage is planned for either.

### #14 Packaging: Claude Code plugin + init command

```
#14 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: it agrees with the big-picture proposal: when it is groomed, #14 takes the set-up checks of its question 6. `AGENTS.md` says the repo "will become a Claude Code plugin", but the order against the two proposed stages is the owner's choice: the stage model and the doc lifecycle both change what the plugin would ship. Missing: the owner's plan for a packaging stage.

### #13 Jev at the handoffs

```
#13 -> parked, source https://github.com/Lighfe/agent-graph-kit/blob/d5f9a098dd190ceff2b003c260548b41c77c7a42/docs/specs/2026-09-25-agent-graph-kit-v1.md#3-scope
```

Reason: "Before building: measure Jev accuracy on 10 to 20 real groomed issues". No such measurement is recorded.

## Summary of the outcomes

| Outcome | Issues | Count |
|---|---|---|
| Stage "Planning model" | #89 (1), #91 (2), #64 (3) | 3 |
| Stage "Doc lifecycle" | #87 (1) | 1 |
| Merge | #76 into #79, #16 into #87 | 2 |
| Close | #46 | 1 |
| Parked | #88, #86, #79, #77, #75, #74, #66, #65, #63, #61, #54, #53, #47, #45, #44, #32, #31, #30, #29, #28, #27, #26, #25, #24, #23, #22, #21, #20, #19, #18, #17, #15, #14, #13 | 34 |
| Total | | 41 |

## Outcomes the proposals already name

| Issue | What the proposal says | This file |
|---|---|---|
| #16 | Replaced by the doc-lifecycle proposal as the place where the doc lifecycle is decided | Merge into #87: agrees |
| #64 | Obsolete, or rewritten as the hook change for native blockers | Stage "Planning model", rewritten as the hook change: agrees |
| #87 | Carries out the doc lifecycle | Stage "Doc lifecycle", position 1: agrees |
| #14 | Takes the set-up checks of the big-picture proposal | Parked; takes the checks when groomed: agrees |
| #15 | Takes the set-up checks of the big-picture proposal | Parked; takes the checks when groomed: agrees |
| #18 | May later allow several active stages | Parked; the note is input for its grooming: agrees |

## Where the two proposals disagree

None found between the two proposals on a point that matters for this sorting. Their follow-up lists fit together: the doc-lifecycle proposal's stage-end audit uses the stage model of the big-picture proposal, and both use `Source:` lines and the parked state for follow-ups.

Conflicts that matter for this sorting, but between a proposal and another file, not between the two proposals:

- `docs/checks/hook-activation.md`: the doc-lifecycle proposal archives it as a one-time runbook, while `README.md` (set-up step 3) tells every new project to run it, and #54 wants it usable in a new project. This is why #54 stays parked.
- The doc-lifecycle proposal puts proposals under `docs/specs/<date>-<topic>.md`. This file is at `docs/research/backlog-triage-proposal.md` because #85 names that path, and research reports are "written once" there, while a proposal is "archived after use". Under the doc-lifecycle proposal, this file would move to `docs/archive/` once #91 is done.
- The doc-lifecycle proposal cites guarantee IDs "G1 to G9". G9 was removed by #90 after it was written, so #87 should use G1 to G8.

## Gaps found

Work that the proposals list as follow-up and that no open issue holds. This file creates no issue; the owner decides whether to file them.

- The process and role changes for stages of the big-picture proposal (`docs/process.md`, `docs/team/orchestrator.md`, `docs/team/pm.md`, `docs/task-template.md`, the label `stage`). #91 keeps them out of scope, and #64 covers only the hook part. Without them, stage "Planning model" does not reach its goal.
- The two spikes of the big-picture proposal (the sub-issue order as read by `gh`, and limit 7 of #80 with paging of form B).

## Sources

- Big-picture proposal, `docs/specs/2026-10-01-big-picture.md`, read at commit `d5f9a09` on 2026-10-01.
- Doc-lifecycle proposal, `docs/specs/2026-10-01-doc-lifecycle.md`, read at commit `d5f9a09` on 2026-10-01.
- Research report `docs/research/big-picture-and-lean-docs.md`, section "6.2 The backlog as a graph, from the issue text alone", read at commit `d5f9a09`.
- Observability spec `docs/specs/2026-09-26-agent-graph-observability.md` and v1 spec `docs/specs/2026-09-25-agent-graph-kit-v1.md` section 3, read at commit `d5f9a09`.
- The 41 issues in the list above, with their comments, and the closed issues #9, #10, #11, #12, #43, #48, #52, #60, #62, #70, #73, #78 and #90 (titles, and the bodies and comments of #11, #12, #60, #62 and #90), read with `gh issue view` on 2026-10-01.
- `README.md`, `docs/checks/hook-activation.md`, `.claude/agents/frontend-engineer.md`, `.claude/hooks/issue_state.py` and `.github/workflows/` at commit `d5f9a09`; `git log -S` for the README step of #46.
