# The big picture and lean docs in agentic development

Research on how other people experience two problems and how they solve them:

- **A. The big picture.** Nobody keeps the project goals, the order of tasks, their dependencies, what can run in parallel and how important each task is. New work that comes up mid-stream (reviews, QA, demo runs, follow-ups) is not sorted into it.
- **B. Lean and true agent-readable docs.** Docs that agents read become outdated, redundant or contradict the code. "Lean and true" also covers lifecycle: when a doc is created, kept, archived or deleted.

Research questions (section 0 has the agreed plan):

1. Who reports these problems, and what do they cost?
2. How do people keep docs lean and true? Who detects drift, who decides, and when? Which lifecycles do docs have?
3. Where do goals, order, dependencies and priority live, and how many copies exist?
4. How is mid-stream work sorted (review findings, QA follow-ups, scope creep)?
5. How are long autonomous runs split into stages, how does a run move from one stage to the next, and where does a human come in?
6. Who does these jobs (orchestrator, separate agent, tool or skill, CI, human), and at what cost?
7. What do current Claude Code, Codex and GitHub features offer?
8. What did people try that did not work, and why?

- Research date: 2026-10-01
- Sources: 2026 or later, read in the primary source (article, repo, docs, issue threads, paper). Each source in the list at the end has its date and one line on why it is credible. Vendor sources are marked. Pre-2026 sources are named only as background. Where only an abstract was read, the source list says so.
- Experiments: two read-only experiments on this repo (section 6). Nothing in the repo or on GitHub was changed.
- Review: Codex, `docs/reviews/2026-10-01-big-picture-lean-docs-research-codex-review.md`. All three findings are worked into this version.
- Status: research input. Nothing here changes the process, the role files, the hooks or the specs. Adapting the findings to the kit is a later step (section 9).

---

## 0. Research plan

Agreed with the owner in chat on 2026-10-01.

- **Report:** this file.
- **Problem A, the big picture,** comes first. Open question: what is a "stage" in a `/goal` loop, and how does the loop move from one stage to the next without the owner?
- **Problem B, agent-readable docs stay lean and true.** Not only drift: also the size of the docs and how long they live. A spec that is thrown away after use has maximum drift but cannot mislead an agent. The cost of throwing it away (how the next spec or plan is written) is part of the question.
- **Equal weight.** The two problems are reported separately. Where a source treats them as one, the report says so.
- **Research questions:** the eight above.
- **Sources:** 2026 or later, dated, credibility line, vendor marked. About 10 to 20 strong sources plus the course material. Say what was looked for and not found.
- **In depth:** 3 to 5 tools or workflows that handle one or both problems.
- **Experiments (read-only):** a sampled doc audit of this repo, and the dependency graph of the open backlog built from the issue text alone.
- **Existing issues:** all may be outdated, #16 included. They are checked against the findings, not built on.
- **Review:** a Codex review of the draft if worth the time.
- **Output:** this report, ending with suggested next-step issues. Committed only after the owner approves.

---

## 1. Who reports the problems, and what they cost (Q1)

| Who | Problem | What they report |
|---|---|---|
| OpenAI harness team (Lopopolo, Feb 2026) [1] | B, then A | A single big `AGENTS.md` "rots instantly", "becomes a graveyard of stale rules", and "agents can't tell what's still true". Code drift: the team spent "every Friday (20% of the week)" cleaning up "AI slop" until they automated it |
| OpenAI Symphony team (Apr 2026) [2] | A | With interactive agents, an engineer can manage "three to five sessions" before context switching hurts. "We'd forget which session was doing what". The bottleneck was human attention, not the agents |
| Spec Kit users (GitHub issues, 2025-11 to 2026-08) [10] | B | Specs cannot be updated in place. Each change opens a new feature folder, or the agent rewrites `spec.md` and regenerates `tasks.md`: "History disappears". "This makes it almost impossible to code with speckit" (#1191). Grep-based alignment misses a reworded requirement, so a second "live line" for the same behavior appears, and `/speckit.analyze` "only reports what the model loaded" (#4164) |
| OpenSpec users (2026-03) [11] | B | After `archive`, the living spec was sometimes not updated. Users had to tell the agent to copy the spec by hand. One user blames older models (#799) |
| Anthropic Labs (Rajasekaran, Mar 2026) [5] | A | Long runs need a planner, a spec and a contract per sprint. With newer models, the sprint structure became overhead and was removed |
| GSD Core maintainers (docs and ADRs, 2026) [13] | A and B together | "Context rot" in long sessions: the model contradicts earlier decisions, and plans ignore stated requirements. A file-based log of drift acknowledgments needed a sweeper, a CI lane and manual merges and left `main` red for 24 pushes (ADR-3942) |
| Gloaguen et al. (ETH, arXiv, Feb–Sep 2026) [14] | B | Context files do not generally raise task success and raise inference cost by over 20%. Repository overviews do not help. Instructions in the files are followed |
| Gao et al. (arXiv, Jul 2026) [17] | B | Of reused agent skills, 53% are never changed after adoption; later changes are "overwhelmingly additive" |
| Course material (Grigorev, Jul 2026) [19] | both, implicitly | Spec → plan → tasks → GitHub issues as the canonical backlog, plus "living documents" (`process.md` and others) where corrections are fed back. The course does not say what happens to the spec and plan after intake |

Two things recur. First, the cost is human attention: someone has to tell the agents what is still true and what comes next. Second, the failure is silent: nothing fails when a doc is stale or a follow-up is not sorted in; the agent just reads the wrong thing or works on the wrong thing.

## 2. Problem A: the big picture

### 2.1 Where goals, order, dependencies and priority live (Q3)

| Source | Goals | Order and dependencies | Priority | Copies |
|---|---|---|---|---|
| OpenAI Symphony [2][3] | Issues in Linear; a plan task produces "a tree of tasks, breaking the work into stages and defining dependencies" | Linear `blockedBy`. "Agents only start working on tasks that aren't blocked" | Linear priority; dispatch sorts by priority, then oldest | One: the tracker. The repo holds only `WORKFLOW.md` (how to work, not what) |
| OpenAI harness repo [1] | `docs/product-specs/`, `docs/exec-plans/active/` | Inside each exec plan (milestones) | Not described | Plans in the repo; a tech-debt tracker file |
| Beads [12] | Epics (hierarchical ids) | `bd dep` graph with types (`blocks`, `parent-child`, `discovered-from`, `supersedes`, …); cross-project deps as `external:<project>:<capability>` | `-p 0..4` | One: the Beads database. Its README says "Do not use markdown TODO lists" and "Do not use external issue trackers" |
| GSD Core [13] | `ROADMAP.md` (milestones, phases, goals), `REQUIREMENTS.md` (numbered) | Phase order in `ROADMAP.md`; plans in "dependency waves" inside a phase | Phase order | `ROADMAP.md` is "the single source of truth for what the project is building and in what order". `STATE.md` says where the run is |
| Spec Kit [10] | One feature folder per spec | `tasks.md` order; `taskstoissues` creates "dependency-ordered GitHub issues" | Not first-class | Two after `taskstoissues`: `tasks.md` and the issues |
| Claude Code agent teams [6] | Lead's prompt | Task list with dependencies; a blocked task cannot be claimed; done tasks unblock others automatically | None | One per session, stored locally; not shared across sessions |
| This repo today | Spec section 1 and 3 | The plan's dependency table (frozen since intake); one reactive `Waiting on:` line | None | Spec, plan and issues, partly overlapping (section 6) |

What the sources agree on: the order and the dependencies live in **one place that a program can query**: a tracker field (Symphony, Beads, GitHub) or one roadmap file (GSD). None of the sources keeps a dependency table in a prose plan after work starts.

What they disagree on: whether that one place is the issue tracker (Symphony, Beads), or a file in the repo (GSD, OpenAI exec plans). GSD supports both. Its "issue-driven orchestration" guide maps a tracker issue onto a `ROADMAP.md` phase and copies the issue URL into the phase's `CONTEXT.md` [13], which makes two copies.

### 2.2 Mid-stream work (Q4)

| Source | What happens when new work comes up | What keeps it from derailing the current work |
|---|---|---|
| Symphony [2][3] | The agent files a new issue in `Backlog`, links the current issue as related, and sets `blockedBy` if the follow-up depends on it | `Backlog` is outside the workflow: "do not modify". A human moves it to `Todo`. "Many of these follow-up tasks also get picked up by agents" once a human schedules them |
| Beads [12] | `bd create … --deps discovered-from:<parent>`. At the end of a session ("landing the plane"): "File issues for remaining work" | `bd ready` shows only unblocked work. `bd defer` parks an issue ("not blocked by anything specific, just postponed"). `bd supersede`, `bd duplicate`, `bd find-duplicates`, `bd stale`, `bd orphans` clean up. `bd human` flags issues that need a human decision |
| GSD Core [13] | `/gsd-capture` (and `--seed`) to note it; `/gsd-phase --insert N` for urgent work between phases (decimal phase numbers); `BACKLOG.md` for deferred work; `/gsd-new-milestone` for a new set | Phases are inserted into one roadmap; the run continues in roadmap order |
| Spec Kit [10] | `/speckit.converge` compares code with spec and appends missing work as tasks to `tasks.md` | Only for the same feature. Requirement changes have no command; users ask for `/speckit.revise` with `SUPERSEDED` and `RETIRED` markers (#4156, open) |
| OpenAI harness [1] | Background Codex tasks scan for deviations and open small refactoring PRs, most "reviewed in under a minute and automerged"; a tech-debt tracker in the repo | Paid down "continuously in small increments" instead of in bursts |
| This repo | The PM files a follow-up issue with `later`; the Codex review becomes follow-up issues (for example the Task 4–6 review) | `later` keeps them out of the loop. Nothing places them relative to other work (section 6.2) |

Pattern: new work gets **a link to where it came from** (`discovered-from`, "related"), **a parked state** that the loop does not touch (Backlog, deferred, `later`), and **someone who promotes it** into the active set. In Symphony that someone is a human (`Backlog` → `Todo`). In Beads, `bd ready` lists unblocked work but leaves out deferred issues even when nothing blocks them; a deferred issue comes back by an explicit undefer or a `--until` time. Who decides to undefer is not described. GSD inserts new work into the roadmap during planning.

### 2.3 Stages in long autonomous runs (Q5)

| Source | Unit of a stage | How the run moves on | Where a human comes in |
|---|---|---|---|
| GSD Core [13] | **Milestone** ("a meaningful, releasable increment") made of **phases** (one discuss → plan → execute → verify → ship loop each) | `/gsd-autonomous` runs every incomplete phase in roadmap order, then "audit → complete → cleanup" for the milestone. `--from/--to/--only` bound the run | Before the run (decisions in `PROJECT.md` or discuss), and at the PR (ship). `--interactive` surfaces open questions |
| Anthropic harness [5] | V1: sprints with a "sprint contract" negotiated by generator and evaluator before coding. V2: no sprints | V1: the next sprint starts after the evaluator passes the contract. V2: the generator builds continuously; one QA pass at the end | Grading criteria and evaluator calibration, set by a human ahead of time |
| OpenAI ExecPlans [4] | Milestones inside one plan, each "independently verifiable" | "Move directly to the next milestone without asking for next steps" | The plan is the hand-off; living sections (Progress, Decision Log, Surprises) allow resuming |
| Symphony [2] | One ticket; a big ticket can produce a task tree "in stages" with dependencies | The daemon dispatches every unblocked active ticket; the DAG decides the order | Moving `Backlog` → `Todo`; `Human Review` before merge |
| Claude Code `/goal` [6] | One condition per session ("one goal can be active per session") | A small model checks the condition after each turn | Setting the condition; errors that need a fix clear the goal |
| Course material [19] | The backlog | `/goal work through the backlog` until no `ready` issue is left | The owner adds `ready` (this repo's `docs/process.md`) |

None of the sources defines a stage the same way. Two shapes recur:

- **A named set with a goal and an exit check.** GSD milestone (requirements covered, audit), Anthropic sprint contract, ExecPlan milestone. The run moves on when the check passes.
- **No stages, just a dependency graph.** Symphony and Beads: whatever is unblocked runs. A "stage" exists only as a parent issue or epic.

Anthropic's report is the only one that measured the cost of stages: removing sprints with a stronger model kept the result and saved time [5]. Its numbers are for one app generator, not for an issue loop.

### 2.4 Who does the job (Q6), Problem A

| Placement | Who uses it | Reported trade-off |
|---|---|---|
| In the issue tracker, read by a scheduler | Symphony [2][3]; Beads (`bd ready`) [12] | The orchestrator stays small: Symphony's spec says the orchestrator "MUST NOT … branch on provider-specific blocker, board, transition, or comment semantics"; an adapter derives one `dispatchable` flag. Cost: the tracker must hold real dependency data; Symphony's spec calls `blocked_by` "best-effort" |
| In one roadmap file, read by an orchestrator command | GSD Core [13] | One file to read. Cost: the orchestrating session itself fills up; GSD added hooks to warn about context headroom and moved heavy work to fresh subagents |
| In a planner agent | Anthropic [5]; Symphony's "produce an implementation plan" tickets [2] | The planner writes the order once. Anthropic's spec "remained largely static" during the build |
| With a human | Symphony (`Backlog` → `Todo`) [2]; Spec Kit (user runs each command) [10]; this repo (owner adds `ready`) | Symphony keeps human judgment at the promotion step and at review. This repo's owner reports that they do not want to order the work |

## 3. Problem B: lean and true agent-readable docs

### 3.1 Doc lifecycles in use (Q2)

| Lifecycle | Who uses it | What the agent reads later |
|---|---|---|
| **One-off execution plan, then the tracker holds the work** | Course material [19] (plan → issues); Symphony (a plan ticket produces a task tree) [2]; Beads ("replaces messy markdown plans") [12] | The issues for the work. These sources say nothing about discarding a *behavior* spec: Symphony itself keeps a long living `SPEC.md` [3], and the OpenAI harness repo keeps `product-specs/` [1] |
| **Change folder, then archive and merge into a living spec** | OpenSpec [11]: `changes/<name>/` holds proposal, design, tasks and *delta* specs; `archive` moves the folder to `changes/archive/<date>-<name>/` and merges the deltas into `specs/`, "the source of truth" | The living `specs/` plus the open change folders. Archived changes stay in the repo |
| **Active / completed folders** | OpenAI harness [1]: `docs/exec-plans/active/` and `completed/`, plus a tech-debt tracker | Active plans; completed ones are kept but out of the main path |
| **Living plan with a log** | OpenAI ExecPlans [4]: Progress, Surprises & Discoveries, Decision Log, Outcomes must "stay up to date as work proceeds" | The one plan, which grows during the work |
| **Living spec, iterated** | Spec Kit [10] (`converge` appends tasks; users ask for in-place revisions with `SUPERSEDED`/`RETIRED` markers) | The feature folder, with all past lines |
| **Phase artifacts archived per phase** | GSD Core [13]: "Ship … archives the phase artefacts"; `MILESTONES.md` keeps history; `DECISIONS-INDEX.md` is a "bounded rolling summary" when old decisions get too many | `STATE.md`, `ROADMAP.md`, the current phase |
| **PR-lifetime data stays out of the tree** | GSD Core ADR-3942 [13]: drift acknowledgments moved from files into commit trailers, read only from the PR's own commits, so "nothing is left behind in the tree once your PR merges" | Nothing after merge |

Two kinds of document need to be kept apart. **Execution plans** (task lists, order, dependencies) are one-off or move to "completed" in every source that has them; the work then lives in the tracker or a roadmap. **Behavior specs** (how the system should behave) are kept living in every source that has one: OpenSpec and Spec Kit make the spec the truth and pay with a merge step (OpenSpec) or with rewrite and duplicate problems (Spec Kit); the OpenAI harness repo keeps product specs and design docs and keeps them true by automation (3.2); Symphony keeps its own `SPEC.md`. Beads does not address behavior specs. No source was found that discards the behavior spec after intake; that option (P6) is untested in the sources.

### 3.2 How drift is detected and fixed (Q2, Q6)

| Mechanism | Who | Cadence | Reported result |
|---|---|---|---|
| Map, not manual: `AGENTS.md` of about 100 lines as a table of contents into `docs/` | OpenAI harness [1] | Always | Replaced a single big file that failed |
| Linters and CI jobs that check the knowledge base is "up to date, cross-linked, and structured correctly" | OpenAI harness [1] | Every change | No numbers given |
| A recurring "doc-gardening" agent that finds docs that do not match code behavior and opens fix-up PRs | OpenAI harness [1] | Recurring | No numbers given |
| Scheduled doc agents in GitHub Actions (updater, glossary, "unbloat", "noob tester") | GitHub Next, gh-aw [9] | Daily | Merge rates: updater 57/59, unbloat 88/103, glossary 10/10, noob tester 9 merged out of 21 PRs. The updater runs with `auto-merge: true` but excludes `README.md` and the docs index |
| Size and growth guard on agent-facing files in CI; a new file over the cap cannot be acknowledged; an `@`-import that hides size "games the guard" | GSD Core [13] | Every PR | In use; the acknowledgment storage was redesigned twice (3.4) |
| `/doctor prompt-audit`: reports instructions for older models, references to files or commands that do not exist, and files that contradict each other, with proposed edits; changes nothing until asked | Claude Code ≥ 2.1.283 [6] | On demand | Vendor feature; no field reports found |
| `/doctor` trim check: proposes cutting content Claude "can derive from the codebase" (layouts, dependency lists, architecture overviews) | Claude Code ≥ 2.1.206 [6] | On demand | Matches the Gloaguen finding that overviews do not help [14] |
| Startup warning when an instruction file is over the recommended length, or when files add up past a combined limit | Claude Code [6] | Each session | Vendor feature |
| `bd stale`, `bd orphans` (work committed but issue still open), `bd lint` (missing sections), `bd find-duplicates` | Beads [12] | On demand | For issues, not prose docs |
| `/speckit.analyze` for duplicates and conflicts | Spec Kit [10] | On demand | Users report it misses lines that were not loaded (#4164) |

Cadence: the strongest reports use **two layers**: a mechanical check on every change (links, structure, size), and a **scheduled agent** that opens small PRs a human or an agent reviews quickly. Nobody reported a one-time clean-up that stayed clean.

Who decides "update, archive or delete": in OpenAI's and GitHub Next's reports, the agent proposes and a review accepts or rejects the PR. In OpenSpec, the archive step decides by construction (a finished change is archived). Nobody reported an agent that deletes docs on its own.

### 3.3 How lean the docs should be (Q2)

- Claude Code docs: "target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence." Imports organise but "don't reduce its context cost". Put multi-step procedures into skills and part-of-codebase rules into path-scoped rules [6].
- Codex docs: combined `AGENTS.md` files stop being added at 32 KiB (`project_doc_max_bytes`); split guidance into nested directories [7].
- OpenAI harness: "too much guidance becomes non-guidance" [1].
- Gloaguen et al.: context files cost over 20% more inference and do not generally raise success; overviews do not help; non-standard practices do [14].
- McMillan (1,650 Claude Code sessions, one trivial instruction): file size from 25 to 500 lines and a contradicting instruction in another file had **no detectable effect** on adherence; adherence fell with each function generated within a session [15]. Single author, one instruction type. This contradicts the "shorter is better for adherence" advice for that narrow case, and supports "length costs tokens, not obedience".
- Gao and Chen: in 557 agent sessions, 60.5% of doc reads were agent-facing files (instruction files and working notes), 10.6% classic docs [16] (abstract only). Agents read what is put in front of them.

Reading together: the evidence for "lean" is mostly about **cost and relevance**, not about agents ignoring long files. Stale content matters because it is followed: Gloaguen found instructions in context files are well followed [14].

### 3.4 What did not work (Q8)

| What | Who | Why it failed |
|---|---|---|
| One big `AGENTS.md` | OpenAI harness [1] | Crowds out the task; "everything important" means nothing is; rots; cannot be checked mechanically |
| Manual weekly clean-up of agent slop (20% of the week) | OpenAI harness [1] | Did not scale; replaced by encoded rules plus scheduled agents |
| Regenerating the spec and tasks on each change | Spec Kit users [10] | History lost; no "remove the old code" tasks; duplicate live requirements |
| Grep-based lookup of the existing requirement | Spec Kit users [10] | A reworded requirement is missed; an analysis only checks what was loaded |
| Agent-run archive-and-merge step | OpenSpec users [11] | Sometimes silently skipped; the living spec stays stale |
| A permanent file for PR-lifetime data (a log of acknowledgments), then fragments, then a sweeper | GSD Core ADR-3942 [13] | The data's lifetime (one PR) did not match its storage (shared, permanent). Each fix created the next defect: collisions, stale fragments blocking PRs, a sweeper that needed its own CI lane and still left `main` red for 24 pushes |
| Sprint decomposition with stronger models | Anthropic [5] | Became overhead with Opus 4.6; removed |
| Treating agents as "rigid nodes in a state machine" | Symphony team [2] | "Models get smarter and can solve bigger problems than the box we try to fit them in"; they gave agents more tools instead |
| `context: fork` on orchestrator skills | GSD Core [13] | Removed because those skills spawn subagents themselves |
| Interactive supervision of many sessions | Symphony team [2] | Above 3–5 sessions, humans lose track; moved to the tracker as control plane |

## 4. Current Claude Code, Codex and GitHub features (Q7)

Checked in the current docs on 2026-10-01. The docs pages show no dates; versions are from the docs text.

| Product | Feature | Relevant to | Note |
|---|---|---|---|
| Claude Code | `/doctor prompt-audit` (≥ 2.1.283) | B | Finds outdated or conflicting instructions, missing files, contradictions across CLAUDE.md, AGENTS.md, rules, skills, agents. Report only |
| Claude Code | `/doctor` trim check (≥ 2.1.206); size warnings at startup | B | Proposes cutting derivable content |
| Claude Code | `.claude/rules/` with `paths:` frontmatter; skills load only descriptions first | B | Load docs only when relevant |
| Claude Code | `InstructionsLoaded` hook | B | Logs which instruction files loaded and why. Does not fire for an `AGENTS.md` read directly (only via a `CLAUDE.md` import) |
| Claude Code | `/goal` | A | One condition per session, checked after every turn by a small model that sees only the transcript. Survives resume. Can bound runs ("or stop after 20 turns"). No built-in notion of stages or a chain of goals |
| Claude Code | Agent teams task list (experimental) | A | Task dependencies with automatic unblocking; stored under `~/.claude/tasks/`; one team per session; "task status can lag" and block dependent tasks |
| Claude Code | Routines (`/schedule`, research preview), `/loop` | A, B | Scheduled or event-triggered runs, for example a recurring doc or backlog check |
| Codex | `AGENTS.md` merge with a 32 KiB default cap; `AGENTS.override.md` | B | Silent cut-off past the cap |
| Codex | Scheduled tasks (local app or web) with a review inbox | A, B | Example uses include updating skills from recent issues |
| Codex | ExecPlans (`PLANS.md`) | A, B | A convention, not a feature: living plan with progress and decision log |
| GitHub | Issue dependencies (blocked by / blocking), sub-issues | A | `gh` 2.98.0 (2026-08-20) has `gh issue create --blocked-by/--blocking/--parent` and `gh issue edit --add-blocked-by …`, accepting "issue number or URL". `gh issue view --json blockedBy` and the search qualifier `is:blocked` work (tested read-only on this repo) |
| GitHub | Agentic Workflows (gh-aw) | B | Markdown-defined agent workflows in Actions with "safe outputs" (PRs, issues). Ready-made doc updater and unbloat workflows [9] |
| GitHub | Projects, milestones | A | Not examined in depth; no 2026 experience report of an agent loop using them as its roadmap was found |

## 5. In-depth comparison

Five workflows that handle one or both problems.

| | OpenAI harness + Symphony | Beads | GSD Core | OpenSpec | Spec Kit |
|---|---|---|---|---|---|
| Problem | A and B | A | A and B | B | B (and A for one feature) |
| Adoption | Vendor first-party; Symphony repo 27.5k stars | 27.6k stars, v1.3.1 (2026-09-30) | 10k stars; predecessor 64k | 70.8k stars, v1.14.0 (2026-09-30) | 139.6k stars, v1.0.13 (2026-09-29) |
| Goals | Product specs in repo; tickets | Epics | `PROJECT.md`, `ROADMAP.md`, `REQUIREMENTS.md` | Living `specs/` (behavior), change proposals | Constitution; one spec per feature |
| Order, deps | Tracker `blockedBy`; scheduler dispatches unblocked | `bd dep` graph, `bd ready` | Roadmap order; waves inside a phase | Not a focus | `tasks.md` order; `[P]` for parallel |
| Copies of order | 1 (tracker) | 1 (Beads DB) | 1 (`ROADMAP.md`), 2 with a tracker | – | 1–2 (`tasks.md`, issues) |
| Docs lifecycle | Map `AGENTS.md`; living docs kept true by CI and a gardening agent; exec plans active → completed | No prose plans ("Do not create markdown TODO lists"); `bd remember` for durable facts | Phase artifacts archived per phase; rolling decisions index; PR-lifetime data in commit trailers | Change folder → archive + merge deltas into living spec | Feature folder stays; edited or regenerated |
| New work mid-stream | Agent files a `Backlog` issue with related/blockedBy; human promotes | `discovered-from`, `defer`, `supersede`, `find-duplicates`, `human` | `capture`, `phase --insert`, `BACKLOG.md` | New change folder | `converge` appends tasks; no revise command |
| Stages | Ticket trees; none beyond the DAG | Epics; molecules (workflow templates, not examined) | Milestone → phases; `/gsd-autonomous` with audit at milestone end | Change = unit | Feature = unit |
| Human role | Promote from Backlog; review at `Human Review` | Decides priority; answers `human` beads | Discuss phase; ship (PR) | Proposes and archives | Runs every command |
| Reported problems | Lost mid-flight steering; failures fixed by adding skills and guardrails, not patches | 70+ commands ("bd has 70+ commands"); a database next to git | Ceremony for small tasks ("overkill"); orchestrator context fills; ack-log redesign | Archive merge skipped by some models | Iteration on existing specs; duplicates; history loss |

Notes:

- **OpenAI harness + Symphony.** The same team reports both problems in sequence: first they made the repo the system of record for knowledge (B), then the tracker the control plane for work (A). Knowledge and work live in different places on purpose. Vendor report; the product and repo are internal, so the claims cannot be checked beyond the public Symphony spec.
- **Beads.** The clearest "one copy of the graph" design. Its answer to stale plans is to not have prose plans. It replaces the tracker rather than using GitHub, but can sync with GitHub (`bd github sync`).
- **GSD Core.** The only workflow with an explicit stage model (milestone, phase) and an autonomous runner over it. It also guards the size of its own agent-facing files in CI. It is heavy: about 97 files in `docs/adr/` and many artifact types.
- **OpenSpec.** The clearest doc lifecycle: a change is a temporary folder, its deltas update the living spec, then it is archived. The step that keeps the living spec true is itself an agent step and has been reported to fail.
- **Spec Kit.** The most adopted. Its issue tracker is the richest record of spec drift in practice. The maintainers' current direction (#4164) is to keep Markdown for humans and add a script-owned inventory, as an opt-in extension rather than core.

## 6. Experiments (read-only, this repo)

### 6.1 Doc audit, sampled

Method: `git log`, `grep` and `wc` on the repo at `f5e9375`; reading the heads of the spec and plan. A sample, not a full audit.

1. **The spec was edited during execution, and each edit was a second copy.** The v1 spec had 337 lines at intake (2026-09-25 14:39 UTC, when issues #1–#13 were created) and has 490 now. It has 23 commits in total and 21 after intake; 19 commit messages name an issue. Of the 19 commits after `7ad234c` (the Task 5 trigger rule), 18 changed at least one other file in the same commit (process, role files, code or tests). The behavior change was written in the issue, the spec and the other docs.
2. **The plan says the spec wins, but the plan is not maintained.** `docs/plans/…-v1.md` (1,337 lines) was last changed on 2026-09-27. It still says "Execution is deferred. In a later session, convert these tasks to issues", and "Where a task below and the spec differ, the spec wins". Both are no longer true or no longer useful: 42 issues are closed, and the spec changed 19 times after the plan's last edit.
3. **The spec's status is wrong.** Its head says "Status: draft, for owner review" and "Updated 2026-09-26"; it was edited until 2026-09-30.
4. **Code is tied to spec section numbers.** 44 lines in `.claude/`, `scripts/`, `.agents/` and `tests/` reference "spec 5.x", "spec 6.x", "spec 7" or "spec 8" (107 lines repo-wide, 38 of them in the plan). The sampled references still point at existing sections. They would break if the spec were archived or renumbered.
5. **The `later` items have two copies.** 19 open issues are one-liners with "Source: docs/specs/…, section 3" (or the observability spec). The spec's "Not in v1" table holds the same text.
6. **Archived docs are still pointed to.** Open issue #66 points to `docs/archive/2026-09-24-brainstorm-handover.md`.
7. **The process text and the practice differ.** `docs/process.md` and spec section 10 say the owner adds `ready`. The owner reports that in practice they ask the orchestrator session what to do next. The repo cannot show who added a label, because agents use the owner's login.
8. **Size of what agents can read.** `docs/research/` 1,944 lines in 7 files; `docs/plans/` 1,337; `docs/reviews/` 659 in 11 files (one per review); `docs/specs/` 615; `docs/archive/` 295; `docs/team/` 294. `docs/process.md` says not to read old reviews unless the owner points to one; no other folder has such a rule.
9. **Side finding.** The kit's own guard denied three commands of this research session that changed no issue and no settings: G8 twice (read-only commands that combined `.claude/` paths with `;` or `&&`), and G9 once (a local text edit whose content contained the words "gh" and "comment"). Each deny message named the way around. This is a cost of the guard, not a doc problem.

Conclusion: the symptoms in the task description hold, with slightly different numbers (the task said 16 commits and 409 → 463 lines; the current count is 19 commits after Task 5 and 409 → 490 lines). The biggest single source of double bookkeeping is spec edits that repeat what an issue and the process docs already say.

### 6.2 The backlog as a graph, from the issue text alone

Method: `gh issue list --state open --json number,title,body,labels,comments,blockedBy,parent,subIssues`; references `#N` in body and comments; a keyword scan for dependency words.

| Measure | Value |
|---|---|
| Open issues | 37 (the task said about 34) |
| With label `later` | 37 |
| With label `ready` | 0 |
| Milestones in the repo | 0 |
| Native GitHub dependencies (`blockedBy`), parents, sub-issues | 0, 0, 0 |
| In task-template format | 11 |
| One-line items from a spec | 19 |
| Opened after intake (#44–#79) | 17 |
| Issues with a `#N` link to another **open** issue | 4 (#26, #29, #66, #79) |
| Edges between open issues | 7: #26→#28, #26→#32 (related), #29→#17, #29→#23, #29→#66 (evidence for), #66→#29 (needs evidence), #79→#76 (moved from) |
| Stated as a dependency | 1 (#66 depends on #29) |
| Gated on evidence, not on an issue | 7 ("before building", "add only if", "decide after", "only with evidence") |
| Issues ever sent to `## PM: WAITING` in this repo | 0 |
| Issues with an `## Owner: RESUME` comment | 13 of 79 |

What the issues alone cannot tell:

- which goal or group an issue belongs to (the grouping exists only as the spec's "Not in v1" table and the observability spec's "Order" section);
- the order and the priority (no field, no label, no milestone);
- which issues are still valid. Many follow-ups name a closed parent (#44 → #40, #41; #73–#75 → #70), but nothing says whether they are still needed;
- what can run in parallel.

By title only, the open issues fall into about eight clusters (owner trust and markers; guard robustness; observability; packaging and adoption; QA; roles and lanes; process; Jev). This is the author's reading, not recorded anywhere, and not a proposal.

Conclusion: the backlog is flat as described. The only dependency data is in prose, mostly as "evidence for" links. The `WAITING` mechanism has not been used in this repo yet.

## 7. Patterns

| # | Pattern | Who | Solves | Costs | Reported failure modes |
|---|---|---|---|---|---|
| P1 | **The tracker is the one copy of work and order.** Dependencies as tracker fields; a scheduler starts only unblocked work | Symphony, Beads, Claude Code agent teams, course material | A: order, dependencies, parallel work, crash recovery | Real dependency data must be entered; a tracker-specific adapter; blocker data is "best-effort" | Blocked tasks stay blocked when status lags (agent teams); humans still promote from backlog |
| P2 | **One roadmap file with stages.** Milestones → phases; a state file says where the run is; an autonomous runner walks the roadmap | GSD Core; OpenAI ExecPlans (milestones inside a plan) | A: stages, the move from one stage to the next, resumption | A second copy if a tracker is also used; ceremony for small work; orchestrator context | Overkill for small tasks; scope that is too large or too small per phase |
| P3 | **Parked state plus provenance for new work.** New work is filed with a link to its source and a state the loop ignores until promoted | Symphony (`Backlog` + related/blockedBy), Beads (`discovered-from`, `defer`), GSD (`capture`, `BACKLOG.md`), this repo (`later`) | A: mid-stream work without derailing | Someone must promote; the parked pile grows | Without promotion rules the pile is a flat list (this repo, 6.2) |
| P4 | **Map, not manual.** A short entry file points into structured docs; docs load on demand | OpenAI harness, Claude Code rules and skills, Codex nested `AGENTS.md` | B: size, relevance | Structure must be kept; links can rot | One big file failed (OpenAI) |
| P5 | **Change folder, then archive and merge.** Work artifacts are temporary; only the living behavior spec stays in the main path | OpenSpec; OpenAI exec plans `active/` → `completed/`; GSD phase archive | B: no stale plans in the agent's path; history kept | A merge step on every change; a living spec to keep | The merge step is skipped (OpenSpec #799) |
| P6 | **One-off execution plan; the tracker holds the work.** The plan is input for intake and is not read again. *Not observed, only an option:* also archiving the behavior spec after intake | Plan part: course material, Symphony, Beads. Spec part: no source | B: no stale plan in the agent's path; for the spec part, maximum lean | Spec part: no single place that says how the system behaves now; the next spec starts from code and closed issues | Plan part: not reported as failing. Spec part: no reports at all |
| P7 | **Continuous doc gardening.** Mechanical checks on every change, plus a scheduled agent that opens small doc PRs | OpenAI harness, GitHub Next gh-aw, Claude Code `/doctor prompt-audit` (on demand) | B: drift detection and repair | Agent runs on a schedule; review time; for gh-aw an AI-credit budget | Merge rates below 100%: 2 of 59 updater PRs and 15 of 103 unbloat PRs were not merged; the "noob tester" chain merged 9 of 21, partly because changes were too ambitious to do at once. Why each PR was not merged, and whether it was wrong, is not reported |
| P8 | **Size and growth guards on agent-facing files.** CI fails when an agent-facing file grows or a new one exceeds a cap; escape hatch needs a written reason | GSD Core; Claude Code size warnings; Codex 32 KiB cap | B: lean over time | False alarms; an escape hatch | An escape hatch stored as a file became its own drift problem (ADR-3942) |
| P9 | **Storage lifetime matches data lifetime.** PR-lifetime data lives in the PR (commit trailers, PR comments); permanent data lives in the tree | GSD Core ADR-3942 | B: no ever-growing logs of spent decisions | Data is only in git history after merge | The file-based version collided, blocked PRs and needed a sweeper |
| P10 | **Living plan with logs.** One plan per long task with Progress, Decision Log, Surprises | OpenAI ExecPlans | A (resume a long run), B (decisions in one place) | The plan grows; it is one more doc to keep | Not reported; the log grows with the task, not across tasks |
| P11 | **Fewer stages as models improve.** Remove harness structure that a newer model does not need; re-test which parts are load-bearing | Anthropic; Symphony ("rigid nodes" did not work) | A: less overhead | Needs measurement per model change | Removing too much was not reported |

Where a source treats A and B as one problem: GSD Core (`.planning/` holds both the roadmap and the decisions; context rot is the shared cause) and OpenAI ExecPlans (one living plan holds progress and decisions). Symphony and the OpenAI harness post keep them apart on purpose (knowledge in the repo, work in the tracker).

## 8. Relevance to the symptoms

Which patterns address which symptom from the task description. This does not say how the kit would use them.

| Symptom (task section 3) | Patterns that address it |
|---|---|
| The v1 spec was edited during execution; each behavior change written twice | P5 (temporary change folder, one living spec), P6 (plan one-off; the spec part is unobserved), P9 |
| About 44 code references into spec sections | P5 or P6 decide whether the referenced document stays; P4 (references to a stable map) |
| The frozen plan still says "the spec wins" | P5 (plans move out of the main path when done), P7 (an audit flags stale claims) |
| `docs/reviews/` grows by one file per review | P9 (review data with PR or issue lifetime), P5 (archive) |
| No double bookkeeping, no ever-growing decision log | P1 or P2 (one copy of order), P6, P9 |
| The dependency table was not kept current; follow-ups not in it | P1 (dependencies as tracker fields), P2 (one roadmap), P3 (provenance on follow-ups) |
| 37 open issues, all `later`, no order or grouping | P1, P2, P3 |
| The owner should not be the one who orders work | P1 (a scheduler orders by priority and blockers); P2 (the roadmap orders); Symphony still keeps a human at "promote from backlog" |
| A `/goal` loop that moves from one set of work to the next | P2 (milestone → phase runner), P1 (a DAG with no stages), P11 |
| `## PM: WAITING`: reactive, same-repo, one blocker | P1 (native multi-blocker dependencies; `gh` accepts issue URLs), Beads `external:` dependencies |
| The orchestrator role is already large | P1 (Symphony keeps the orchestrator free of tracker semantics), P2 (state in a file, heavy work in fresh subagents) |
| Kit principles: facts only, state on the issue, few files, no secrets | P1 and P3 keep state on the issue; P4, P8 keep files few; P7's scheduled agents are LLM judgment, not facts, and sit outside the hooks |
| The kit becomes a plugin used in other repos | P4, P8 apply to any repo; P1 depends on the tracker each repo uses |

## 9. Open questions for the adaptation step

1. Is the kit's spec an execution plan (one-off, P6) or a behavior spec (living, P5), or does it mix both and need to be split? If a behavior spec is kept living, what keeps it true, given that the archive-merge step is itself fragile? Archiving a behavior spec after intake has no support in the sources.
2. If the spec is archived, what replaces the 44 code references to spec sections?
3. Where does the order of work live: in GitHub fields (P1) or in one roadmap file (P2)? One copy either way: which?
4. What is a "stage" for this loop: a milestone with an exit check (P2), a parent issue, or no stage at all (P1)? What is the exit check, and who checks it?
5. Who promotes parked work into the active set, if not the owner? With which rule, and when does it escalate?
6. Do GitHub's native dependencies fit "facts only, state on the issue"? Can one `gh` call give the guard everything it needs, including blockers in another repo (#64)?
7. Which docs are agent-facing, and which are for humans only? Should agents be kept out of `docs/research/`, `docs/archive/` and `docs/plans/` the way they are kept out of old reviews?
8. Where does review output live once its findings are issues: in `docs/reviews/`, in the issues, or in the PR (P9)?
9. Is a scheduled doc or backlog agent (P7) acceptable under "facts only", if it only opens issues or PRs and never blocks a call?
10. How much of this must work in other repos (#14, #15), where the tracker or docs layout may differ?
11. Does the evidence on file size (McMillan [15]) change how strict "few files, short files" should be, or is cost (Gloaguen [14]) the real reason?

## 10. What was looked for and not found

- A neutral study that compares ways to keep a backlog or roadmap for agent loops (tracker vs file vs DAG). None found; all reports are from tool makers or users of one tool.
- Any report of archiving a behavior spec after intake and working from issues and code alone (the spec part of P6). The sources treat only execution plans as one-off. Nobody reports on how the *next* spec is written from closed issues.
- Numbers on doc-gardening agents beyond GitHub Next's merge rates: false positives, cost per run, missed drift.
- A 2026 experience report of an agent loop that uses GitHub Projects or milestones as its roadmap.
- Kiro steering files, Gas Town (Yegge's multi-agent orchestrator built on Beads) and Beads "molecules" were not examined.
- Field reports on Claude Code `/doctor prompt-audit`.

## 11. Next-step issues

The owner reviewed the suggested issues on 2026-10-01. They were rewritten to read on their own and created in execution order. The issue bodies on GitHub are the only copy; this list only names them.

| Order | Issue | Label | Waits for |
|---|---|---|---|
| 1 | #80 Experiment: GitHub native issue dependencies for the loop | `ready` | – |
| 2 | #81 Experiment: Claude Code /doctor prompt-audit on this repo | `ready` | – |
| 3 | #82 Fix status lines in the v1 plan and spec that are false today | `ready` | #81 |
| 4 | #83 Proposal: where the big picture of the work lives | `ready` | #80 |
| 5 | #84 Proposal: how long each kind of agent-readable doc lives | `ready` | #81 |
| 6 | #85 Proposal: sort the open backlog | `ready` | #83, #84 |
| – | #73 Let the PM apply issue edits asked for in an Owner RESUME comment | `ready` (moved from `later` by the owner) | – |
| – | #86 Guard: false denies by G8 and G9 (side finding of section 6.1) | `later` | – |

The waits are recorded as native GitHub "blocked by" links and as a line in each issue body for the PM. The three proposals (#83, #84, #85) produce files marked "proposal, owner decides", because the loop runs without the owner.

Relation to existing issues, also posted as a note on each:

| Issue | Relation |
|---|---|
| #14 Packaging, #15 Adoption | #83 and #84 must say how their choice works in another repo |
| #16 Librarian | #84 is now where this is decided; #16 may become obsolete. No source solved drift with one role |
| #18 Parallel mode | #83's choice of where dependencies live is an input; #83 does not define parallel mode |
| #20 Review before intake | #84 proposes where review output lives; #20 stays separate |
| #28 Process report | Unaffected |
| #61 Tasks in another repo | #80 tests a cross-repo "blocked by" link; input only |
| #64 Several or cross-repo blockers | #80 tests exactly its open questions; #83 may make it obsolete |
| #73 PM applies RESUME edits | Unaffected by the research; added to this batch by the owner |
| #77 Final loop report | #83 proposes what a stage is; a report may later report per stage |

---

## Sources

Vendor sources are marked **[vendor]**. Dates are publication dates or, for repos and docs, the date read and the latest release.

1. **[vendor]** Ryan Lopopolo (OpenAI), "Harness engineering: leveraging Codex in an agent-first world", 2026-02-11. https://openai.com/index/harness-engineering/ — First-party experience report of a five-month, roughly one-million-line agent-written product; concrete mechanisms and failures.
2. **[vendor]** Alex Kotliarskyi, Victor Zhu, Zach Brock (OpenAI), "An open-source spec for Codex orchestration: Symphony", 2026-04-27. https://openai.com/index/open-source-codex-orchestration-symphony/ — First-party report by the same team, with reported outcomes and trade-offs.
3. **[vendor]** openai/symphony, `SPEC.md` and `elixir/WORKFLOW.md`, repo created 2026-02-26, read 2026-10-01 (27.5k stars). https://github.com/openai/symphony — The primary spec behind source 2; checked for dispatch, blocker and backlog rules.
4. **[vendor]** OpenAI, `PLANS.md` (ExecPlans) in openai/openai-agents-python, added 2026-01-12. https://github.com/openai/openai-agents-python/blob/main/PLANS.md — The template OpenAI uses in its own repo.
5. **[vendor]** Prithvi Rajasekaran (Anthropic Labs), "Harness design for long-running application development", 2026-03-24. https://www.anthropic.com/engineering/harness-design-long-running-apps — First-party experiment with costs, durations and what was removed as models improved.
6. **[vendor]** Claude Code docs: "How Claude remembers your project", "Keep Claude working toward a goal", "Orchestrate teams of Claude Code sessions", read 2026-10-01 (no page dates; versions as stated in the text). https://code.claude.com/docs/en/memory , https://code.claude.com/docs/en/goal , https://code.claude.com/docs/en/agent-teams — Current first-party feature docs.
7. **[vendor]** Codex docs: "AGENTS.md" and "Scheduled tasks", read 2026-10-01. https://learn.chatgpt.com/docs/agent-configuration/agents-md , https://learn.chatgpt.com/docs/automations — Current first-party feature docs.
8. **[vendor]** GitHub, "Creating issue dependencies" docs, read 2026-10-01, and `gh` 2.98.0 (2026-08-20) help output. https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies — First-party docs, plus the CLI tested read-only.
9. **[vendor]** Don Syme, Peli de Halleux, Mara Kiefer (GitHub Next), "Meet the Workflows: Continuous Documentation", 2026-01-13, and `github/gh-aw` `.github/workflows/daily-doc-updater.md`, read 2026-10-01. https://github.github.com/gh-aw/blog/2026-01-13-meet-the-workflows-documentation/ — Maintainers' report with merge counts; workflow file checked for settings.
10. **[vendor-maintained]** github/spec-kit, v1.0.13 (2026-09-29), 139.6k stars; issues #1191 (opened 2025-11-15, comments into 2026-02), #4156 (2026-08-16), #4164 (2026-08-17); `templates/commands/converge.md`, `taskstoissues.md`. https://github.com/github/spec-kit — Most adopted SDD toolkit; issue threads are user experience reports.
11. Fission-AI/OpenSpec, v1.14.0 (2026-09-30), 70.8k stars; `docs/concepts.md`; issues #557 (2026-01-22), #799 (2026-03-04). https://github.com/Fission-AI/OpenSpec — Widely adopted; the lifecycle is documented and its failure reported by users.
12. Steve Yegge and contributors, Beads (gastownhall/beads, formerly steveyegge/beads), v1.3.1 (2026-09-30), 27.6k stars; `README.md`, `AGENTS.md`, `docs/cli-reference/` (`dep`, `ready`, `defer`, `stale`, `orphans`, `find-duplicates`, `human`, `prime`). https://github.com/gastownhall/beads — Widely adopted, by a practitioner with a long track record; commands checked in the generated CLI docs.
13. GSD Core (open-gsd/gsd-core), read 2026-10-01, 10k stars (predecessor gsd-build/get-shit-done 64k stars, archived); `docs/explanation/the-phase-loop.md`, `context-engineering.md`, `docs/reference/planning-artifacts.md`, `docs/how-to/run-phases-autonomously.md`, `drive-gsd-from-a-tracker-issue.md`, `docs/issue-driven-orchestration.md`, ADR-3942 (2026-08-27). https://github.com/open-gsd/gsd-core — Widely adopted; ADRs document what failed with evidence.
14. Thibaud Gloaguen, Niels Mündler-Sasahara, Mark Niklas Müller, Veselin Raychev, Martin Vechev (ETH Zurich SRI), "Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?", arXiv 2602.11988, v1 2026-02-12, v3 2026-09-29. https://arxiv.org/abs/2602.11988 — Controlled evaluation on SWE-bench and real repos with committed context files (abstract read).
15. Damon McMillan, "Instruction Adherence in Coding Agent Configuration Files: A Factorial Study of Four File-Structure Variables", arXiv 2605.10039, 2026-05-11. https://arxiv.org/abs/2605.10039 — Factorial design with mixed-effects models, 1,650 Claude Code sessions; single author and one trivial instruction type, so limited scope (abstract and results summary read).
16. Zhijun Gao, Jing Chen, "From Agent Behaviour to Agent-Friendly Documentation", arXiv 2608.20195, 2026-08-20. https://arxiv.org/abs/2608.20195 — Empirical study of 557 sessions and 33k PRs (abstract read only).
17. Haoyu Gao, Jai Lal Lulla, Hong Yi Lin, Sebastian Baltes, Christoph Treude, Mansooreh Zahedi, "From Registry to Repository: How AI Agent Skills Are Written, Adapted, and Maintained", arXiv 2607.00911, 2026-07-01. https://arxiv.org/abs/2607.00911 — Mining study of 41k skills by established SE researchers (abstract read only).
18. Birgitta Böckeler (Thoughtworks), "Context Engineering for Coding Agents", martinfowler.com, 2026-02-05. https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html — Recognized practitioner series; advice, no experience numbers.
19. Course material: Alexey Grigorev, "AI-Native Development: Specifications, Loop and Graph Engineering", 2026-07-22, and Article 5 "Coding Agent Building Blocks", summaries in `docs/references/summaries/01-…` and `05-…`. — The method this kit follows.

Background (pre-2026, not used as evidence): Anthropic, "Effective harnesses for long-running agents" (2025-11-26), the progress-file and feature-list pattern; Birgitta Böckeler, "Understanding Spec-Driven Development: Kiro, spec-kit, and Tessl" (2025-10); Steve Yegge, "Introducing Beads" (2025-11).
