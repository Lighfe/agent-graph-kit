# Stages, planner and living docs: plan

Each task below becomes one GitHub issue in `docs/task-template.md` format, as a sub-issue of its stage issue. The PM grooms each issue before work starts; the criteria here are the starting point. This plan is archived once the stages are set up.

**Goal:** The kit plans and runs work in stages on GitHub, a planner role plans and reviews the stages, and the agent-readable docs stay true by construction.

**Spec:** `docs/specs/2026-10-01-stages-and-planner.md`

## Global constraints

- Principles of the v1 spec hold: hooks check only guarded calls and only facts (labels, markers, SHAs, git status, GitHub links); prose guides; state lives on the issue and is read with `gh`; few agent-facing files.
- Python is stdlib only, run with `uv run --script`. Test command: `uv run --with pytest pytest`. No network in tests: `gh` is faked as in the existing hook tests.
- No guard or hook on reading docs (spec section 5).
- Every `gh issue list` call in code passes `--limit`; every REST list call pages (`--paginate`).
- Each issue changes the instruction files that its change makes false, in the same commit.

## Stage issues

| Stage issue | Purpose | Blocked by |
|---|---|---|
| Stage 1: Stages on GitHub | The loop reads order and blockers from GitHub, and QA can verify criteria about GitHub state | none |
| Stage 2: Planner | Stages are planned and reviewed by the planner; the owner only validates purposes and chooses | Stage 1 |
| Stage 3: Living docs | The agent-readable docs stay true by construction | Stage 2 |

Each stage issue has the label `stage` and the sections `## Purpose`, `## Background`, `## Exit check` (spec section 2).

---

## Stage 1: Stages on GitHub

Order: 1.1 and 1.2 first (independent), then 1.3 (blocked by 1.1), then 1.4 (blocked by 1.3), then 1.5 (blocked by 1.1).

### Task 1.1: Spike: sub-issue order and blocker paging with `gh`

Lane: default

**Goal:** There is evidence whether `gh` returns the sub-issues of an issue in the order shown on GitHub and can change that order, and how blocker lists behave with paging and with a repo the `gh` login cannot see.

**Acceptance criteria**
- [ ] A report `docs/research/spike-sub-issues-and-blockers.md` states the `gh` version and shows, for each case, the exact command and its output (shortened, no secrets)
- [ ] Sub-issue order: one `gh` call that lists the sub-issues of a test parent with their numbers and states, compared with the order on the GitHub page; and whether a `gh` or `gh api` call can move a sub-issue to a given position
- [ ] Paging: `gh api .../dependencies/blocked_by` on an issue with more blockers than one page holds (or the documented page size, quoted, if creating that many is not sensible), with and without `--paginate`
- [ ] A blocker in a repo the login cannot see: what the read returns (or the documented behavior, quoted, marked "not observed")
- [ ] The report ends with "Consequences": the read form and the order rule that task 1.3 and task 1.5 use
- [ ] Every issue, link and sub-issue created for the spike is closed or removed again; the report shows the final read

**Out of scope:** any change to hooks, docs or process.

**Constraints:** commit only the report. Test issues get the label `later` and a title starting with "Spike test:".

### Task 1.2: Codex QA can verify criteria about GitHub state (existing issue #89)

Lane: default

**Goal:** A criterion about GitHub state (labels, created issues, links, sub-issues, comments of the issue) no longer comes back `## QA: UNVERIFIABLE` only because the Codex sandbox has no network.

**Background:** Happened on #83 and #84 (2026-10-01). #51 already passes the issue comments to Codex.

**Acceptance criteria**
- [ ] The QA pre-step of `scripts/qa-codex` reads, before Codex starts and with the owner's `gh` login: the issue's labels, its timeline events in the commit range's time window, its native blockers and sub-issues, and the list of issues created in that window; it passes them to Codex as files, the same way as the comments of #51
- [ ] The QA prompt tells Codex where these files are and that they are the evidence for criteria about GitHub state
- [ ] A failing read in the pre-step posts `## QA: UNAVAILABLE` with the error (as other pre-step failures do)
- [ ] Tests with a faked `gh` cover: the files are written; a failing read; an empty window
- [ ] `docs/team/qa-engineer.md` and `docs/team/pm.md` say that criteria about GitHub state are checkable

**Out of scope:** network access for the Codex sandbox.

**Constraints:** `scripts/`, its tests, the two role files, the v1 spec section on `qa-codex` if it states the pre-step inputs.

### Task 1.3: Native "blocked by" links replace `Waiting on:` and `waiting` (existing issue #64, rewritten)

Lane: default

**Goal:** Blockers are native "blocked by" links. An issue may have several blockers, also in other repos. The `Waiting on: #<N>` line and the label `waiting` are gone.

**Acceptance criteria**
- [ ] The hook reads the blockers of an issue with the read form chosen in task 1.1 (repo, number, state, all pages)
- [ ] G1 denies a role launch on an issue that has an open blocker, and names the blockers in the deny message; this replaces the check on the label `waiting`
- [ ] The check that reads the `Waiting on:` line (G2) reads native blockers instead: a `## PM: WAITING` result is valid only if the issue has at least one open native blocker
- [ ] `docs/team/pm.md`: the PM adds the blocker with `gh issue edit <n> --add-blocked-by <number or URL>` and then posts `## PM: WAITING` (no `Waiting on:` line)
- [ ] `docs/team/orchestrator.md` and `docs/process.md`: "free the waiting issues" reads native blockers; when every blocker of an issue is closed, the issue goes back to the PM; the label `waiting` is no longer used
- [ ] Tests cover: no blocker; one open blocker; several blockers, one open; a closed blocker in another repo; a read error (deny, as for every hook error)
- [ ] README "Labels" no longer creates `waiting`

**Out of scope:** removing the label `waiting` from GitHub (owner).

**Constraints:** `.claude/hooks/` and their tests, `docs/process.md`, `docs/team/`, README, the v1 spec sections on G1 and G2.

### Task 1.4: Stage issues and parked follow-ups in the process

Lane: default

**Goal:** The process knows stage issues, the active stage, and parked follow-ups with their source.

**Acceptance criteria**
- [ ] `docs/task-template.md` has a second form, "Stage issue", with `## Purpose`, `## Background`, `## Exit check`, and says that a stage issue has the label `stage`, never `ready`
- [ ] `docs/task-template.md`: an optional line `Source: <URL>` for follow-ups
- [ ] `docs/process.md` describes: stage issues and their sub-issues; the active stage (its sub-issues have `ready`); the pick order (native blockers, then position in the stage's sub-issue list as found in task 1.1); follow-ups are filed with `later`, no parent and `Source:`; a parked issue that blocks an issue of the active stage is added to the stage (sub-issue and `ready`) by the orchestrator
- [ ] `docs/team/orchestrator.md`: the pick order; the promotion of a parked blocker; when every sub-issue of the active stage is closed, the loop stops and the final report says the stage is finished (the stage review comes in stage 2)
- [ ] `docs/team/pm.md`: the PM files out-of-scope follow-ups with `later` and `Source:`
- [ ] README "Labels" creates the label `stage`

**Out of scope:** the planner and the stage review (stage 2).

**Constraints:** docs only: the files named above.

### Task 1.5: The close check allows a finished stage issue

Lane: default

**Goal:** `gh issue close <n>` on a stage issue is allowed when all its sub-issues are closed, and denied otherwise.

**Acceptance criteria**
- [ ] The close check: for an issue with the label `stage`, allow when the issue has at least one sub-issue and every sub-issue is closed; deny with the open sub-issue numbers otherwise; the QA PASS check does not apply to stage issues
- [ ] Issues without the label `stage` are checked as today
- [ ] Tests cover: all closed; one open; no sub-issues; a read error
- [ ] The v1 spec section on the close check and `docs/team/orchestrator.md` ("Close an issue") say this

**Out of scope:** who closes a stage issue (stage 2: the planner in set-up).

**Constraints:** `.claude/hooks/` and their tests, the two doc places named.

---

## Stage 2: Planner

Order: 2.1 first; then 2.2 and 2.4 (both blocked by 2.1); 2.3 blocked by 2.2; 2.5 last (blocked by 2.3 and 2.4).

### Task 2.1: Planner role file and subagent

Lane: default

**Goal:** The planner role is defined: its three jobs, its inputs and its result.

**Acceptance criteria**
- [ ] `docs/team/planner.md` describes the three jobs of spec section 3 (intake, stage set-up, stage review), when each runs and as what (main session or subagent)
- [ ] Stage review: the comment format of spec section 4, first line exactly `## Planner: STAGE REVIEW`, posted with `gh issue comment <n> --body-file <path>`; the subagent creates, edits and closes no issue
- [ ] Intake: brainstorming → spec in `docs/specs/` → plan in `docs/plans/` → one stage issue with sub-issues (sub-issues as `later` until the owner confirms the stage)
- [ ] Set-up: present the options of the newest stage review, answer questions, the owner chooses and validates the purpose; write the stage issue, file or link sub-issues (`gh issue edit <stage> --add-sub-issue`), set blockers, add `ready` to the sub-issues, close the finished stage issue, archive the plan; end with the line "Stage #N is ready. Run `/goal …` here or in a new session."
- [ ] `.claude/agents/planner.md` points to the role file, like the other subagent files; tools: Read, Grep, Glob, Bash

**Out of scope:** the hook (2.2), the skill (2.4).

**Constraints:** the two new files only.

### Task 2.2: The hook accepts planner launches on stage issues

Lane: default

**Goal:** The orchestrator can launch the planner subagent on a stage issue, and only there.

**Acceptance criteria**
- [ ] The launch line `ROLE=planner ISSUE=<n>` is accepted for the agent `planner`
- [ ] Allowed only on an open issue with the label `stage`; `ready` is not required; denied otherwise with a message that names the missing condition
- [ ] The launch posts `## Launch: planner (attempt <n>)` like other launches; outage and not-started receipts work as for other roles
- [ ] `## Planner: STAGE REVIEW` is a valid result marker; a planner launch does not count as a return
- [ ] Tests cover the allowed launch, a launch on a non-stage issue, a closed stage issue, and the marker
- [ ] The v1 spec sections on the launch line, the checks and the result markers name the planner

**Out of scope:** the prose of the stage end (2.3).

**Constraints:** `.claude/hooks/` and their tests, the v1 spec sections named.

### Task 2.3: The orchestrator ends a stage with a stage review

Lane: default

**Goal:** When the active stage is finished, the orchestrator launches the planner with its run notes and stops.

**Acceptance criteria**
- [ ] `docs/team/orchestrator.md`: when every sub-issue of the active stage is closed, launch the planner on the stage issue; the prompt has the launch line, the role line, and a section "Run notes" (escalations, guard and classifier denies, outages, collisions, anything unusual, each with the issue number)
- [ ] It reads the result with the existing command (prefix `## Planner: `), and if the marker is missing, escalates the stage issue
- [ ] The final report names the stage review comment and says: "Start the next session with `/stage-start`."
- [ ] If a sub-issue is escalated, the stage has not ended: no planner launch, the loop stops as today
- [ ] `docs/process.md` lifecycle names this step

**Constraints:** docs only: the two files.

### Task 2.4: Skill `/stage-start`

Lane: default

**Goal:** A session started with `/stage-start` works as the planner, in dialogue with the owner.

**Acceptance criteria**
- [ ] `.agents/skills/stage-start/SKILL.md` makes the main session follow `docs/team/planner.md`
- [ ] It finds the newest `## Planner: STAGE REVIEW` on an open stage issue; with one, it runs set-up; without one, it runs intake
- [ ] It says that this session does not orchestrate until set-up has ended, and that the switch to the orchestrator happens at most once
- [ ] Its description names when to use it, so it is found by name

**Constraints:** the new skill file only.

### Task 2.5: Role separation in the instruction files

Lane: default

**Goal:** Every instruction file says the same about which role the main session has.

**Acceptance criteria**
- [ ] `docs/process.md` "Roles": orchestrator = main session while it runs `/goal`; planner = main session after `/stage-start`, and a subagent for the stage review; without a command, no role
- [ ] README line "The Claude Code main session is the orchestrator" says the same; the set-up section mentions `/stage-start` as the way to start
- [ ] `AGENTS.md`: the upstream line (brainstorming, writing-plans) points to the planner role and `/stage-start`; the documents list names `docs/team/planner.md`
- [ ] A search for "main session" in the instruction files finds no statement that contradicts this

**Constraints:** docs only: the three files.

---

## Stage 3: Living docs

Order: 3.1 first; then 3.2, 3.3 and 3.4 (all blocked by 3.1); 3.5 last (blocked by 3.3).

### Task 3.1: Living behavior spec; archive the v1 spec

Lane: default

**Goal:** One living behavior spec `docs/specs/agent-graph-kit.md` says how the kit behaves now; the v1 spec is archived.

**Acceptance criteria**
- [ ] `docs/specs/agent-graph-kit.md` holds: principles, roles (including the planner), the launch contract with G1 to G8, the result markers, the `qa-codex` contract, the stage model; each as stated by the current code and the spec `docs/specs/2026-10-01-stages-and-planner.md`
- [ ] Its headings are stable names (no numbers)
- [ ] `docs/specs/2026-09-25-agent-graph-kit-v1.md` is moved unchanged to `docs/archive/`; `docs/specs/2026-10-01-stages-and-planner.md` and the proposals of #83 and #84 too
- [ ] Every instruction file that pointed to the v1 spec points to the living spec

**Out of scope:** code references to section numbers (3.2).

### Task 3.2: Code cites spec anchors; fact test for anchors and guarantee IDs

Lane: default

**Goal:** Code and README cite the living spec by heading anchor or guarantee ID, and a test fails when a citation points to nothing.

**Acceptance criteria**
- [ ] No line in `.claude/hooks/`, `scripts/`, `tests/`, `.agents/skills/` or README cites a spec section number
- [ ] A test collects every cited anchor and guarantee ID and fails if the living spec has no such heading or ID
- [ ] A test fails if the guarantee IDs named in the docs and the checks in the hook differ

### Task 3.3: Fact test for paths in instruction files

Lane: default

**Goal:** A test fails when an instruction file names a repo path that does not exist.

**Acceptance criteria**
- [ ] The test reads the instruction files of spec section 5 and checks every repo-relative path in backticks or links
- [ ] Placeholder paths (with `<…>`) and paths in other repos are skipped by a rule the test states
- [ ] The test passes at the end of this issue (fix or remove the paths it finds)

### Task 3.4: Reading rules and doc lifecycles in prose (existing issue #87; #16 merged into it)

Lane: default

**Goal:** The reading rules and the lifecycles of spec section 5 are written down, and existing docs are where their lifecycle puts them.

**Acceptance criteria**
- [ ] `docs/process.md` "Work rules" states the reading rules of spec section 5 (prose; no hook), replacing "Do not read old reviews…"
- [ ] The living spec has a short lifecycle table (kind of doc, folder, lifecycle)
- [ ] Executed plans in `docs/plans/` are moved to `docs/archive/`
- [ ] Each file in `docs/reviews/` is listed in the issue comment with its decision (findings in issues: delete; open: keep); the deletions are made
- [ ] No hook or test is added for reading

### Task 3.5: Doc-drift check in the stage review

Lane: default

**Goal:** The stage review reports doc drift.

**Acceptance criteria**
- [ ] `docs/team/planner.md`, stage review: run the test command and list the failures of the fact tests; run `/doctor prompt-audit` if a subagent can run it, else say in the review that the owner's `/stage-start` session runs it at set-up
- [ ] The issue comment shows the evidence for which of the two holds (a run, or the error)
