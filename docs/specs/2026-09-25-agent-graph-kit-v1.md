# agent-graph-kit v1

- Date: 2026-09-25
- Status: draft, for owner review
- Source: design session with the owner on 2026-09-25. Research inputs: `docs/research/`.

This spec is the accepted design of the kit for version 1. Earlier notes in `docs/archive/` are historical input only.

---

## 1. Purpose

v1 turns the prose loop PM → Engineer → QA into a graph where:

- hooks guarantee the handoffs (the orchestrator LLM cannot skip or reorder a step),
- a different vendor (Codex) verifies every result,
- frontend work goes to Lovable.

The kit is dogfooded in this repo. The Lovable lane is proven in a demo repo, `paint-math` (a UI where you enter mathematical equations and see them drawn on a canvas; the name can change).

## 2. Principles

| # | Principle |
|---|---|
| P1 | **Prose guides, hooks guarantee.** `docs/process.md` and the role files stay the main description of the process. Hooks enforce only the handoffs. |
| P2 | **Facts only.** v1 hooks check facts: labels, comment markers, SHAs, git status. No LLM or Jev judgment blocks anything. |
| P3 | **State lives on the issue.** Hooks and scripts read the state with `gh`. Nothing depends on what the orchestrator remembers. |
| P4 | **Few files.** The kit adds as few agent-facing files as possible. Adopting the kit means merging into existing files, never appending a second set. |
| P5 | **No secrets.** No keys in commits, issues, comments or reviews. Examples are synthetic. |

## 3. Scope

### In v1

1. Hook guarantees for role launches and for closing an issue (section 5)
2. Codex QA through a launcher script, with a Claude fallback (sections 6 and 7)
3. A Codex review skill that always writes a review file (section 8)
4. The Lovable lane and the paint-math demo (section 9)
5. The `later` label (section 10)
6. Tests, CI for this repo, and README set-up instructions (section 12)
7. Three spikes before the dependent work (section 13)

### Not in v1

Each item becomes a GitHub issue with the label `later` during intake. The note after the dash goes into the issue body.

| Item | Note |
|---|---|
| Jev at the handoffs | Before building: measure Jev accuracy on 10 to 20 real groomed issues; measure the token size of typical issues and diffs against Jev's limit (32k tokens for state + longest question) |
| Packaging: Claude Code plugin + init command | Before building: verify how hooks work inside a plugin and how a project can configure them |
| Adopting the kit in existing projects | First pilot: mini-kanban-board. Adoption merges the kit into existing docs (P4) |
| Doc decluttering ("librarian") | Process to find and remove outdated or redundant agent-facing docs |
| Separate Reviewer role | Add only if QA passes work with real quality problems |
| Parallel mode (worktrees) | Changes every guarantee that assumes one HEAD and one sequence |
| Role limits through Bash | PM and QA cannot write or commit through Bash |
| Required review before intake | A plan becomes issues only after a review with a status on each finding. Decide after using the review skill on a few specs |
| Codex as an engineer lane | Rule "the checker is always a different vendor from the implementer" |
| Config levels for small projects | For example: loop without some roles or gates |
| Independent test design by QA | QA designs tests before the engineer implements. Add if QA often finds missing tests |
| CI in the close gate | Close only with green CI on the verified SHA. Needs a push rule |
| CI/CD set-up and deploy skills | Skills, not roles (see `docs/research/qa-and-cicd-in-agent-graphs.md`) |
| On-call loop | A separate observe/respond graph for production alerts |

## 4. Roles and lanes

| Role | Runs on | Launched through | Posts the result |
|---|---|---|---|
| Orchestrator | Claude main session | – | – |
| PM | Claude subagent `pm` | subagent launch | the PM, with `gh` |
| Engineer, lane `default` | Claude subagent `software-engineer` | subagent launch | the engineer, with `gh` |
| Engineer, lane `frontend` | Claude subagent `frontend-engineer`, which drives Lovable through MCP | subagent launch | the subagent, with `gh` |
| QA | Codex (`codex exec`) | the script `qa-codex`, through Bash | the script, with `gh` |
| QA fallback | Claude subagent `qa-engineer` | subagent launch, only after `## QA: UNAVAILABLE` | the subagent, with `gh` |

- The orchestrator only launches subagents and the `qa-codex` script. It never calls Lovable or Codex directly.
- The PM writes the lane into the issue: `Lane: default` or `Lane: frontend`. `frontend` is allowed only in a repo with a Lovable submodule.
- One role file per role in `docs/team/`. Both QA checkers use `docs/team/qa-engineer.md`. The frontend lane is a section in `docs/team/software-engineer.md`, not a separate role file (P4).

## 5. Launch contract and hook guarantees

### 5.1 Guarded calls

A hook runs before each tool call of the orchestrator and of its subagents. It guards only these calls:

| Call | Role |
|---|---|
| Subagent launch of `pm` | pm |
| Subagent launch of `software-engineer` or `frontend-engineer` | engineer |
| Subagent launch of `qa-engineer` | qa (fallback) |
| Bash call of `qa-codex` | qa |
| Bash call of `gh issue close` | close |

All other calls pass. Examples: other subagent types, the Codex review skill, normal Bash commands.

### 5.2 Launch line

A guarded launch must contain the line `ROLE=<role> ISSUE=<number>` (in the subagent prompt, or as arguments of `qa-codex`). A guarded launch without this line is denied.

### 5.3 Launch comments and valid results

When the hook allows a launch, it posts a launch comment on the issue before the call runs:

```
## Launch: engineer (attempt 3)
Agent: software-engineer
```

A result comment is **valid** only if both are true:

1. Its first line is a result marker of the role (section 5.5).
2. It was posted after the newest launch comment of that role.

An old result from an earlier attempt is ignored automatically. If a launched role posts no result, no valid result exists, the next step is denied, and the orchestrator escalates.

The **current result** of an issue is the newest valid result of any role, or an `## Owner: RESUME` comment, if that is newer.

### 5.4 Checks

| # | Launch | Allowed only if |
|---|---|---|
| G1 | any guarded call | the launch line exists (5.2) · the working tree is clean · the issue has the label `ready` and not the label `later` |
| G2 | PM | the issue has no launch comment yet, or the current result is `## Engineer: BLOCKED` or `## Owner: RESUME` |
| G3 | engineer | the current result is `## PM: GROOMED` or `## QA: FAIL` · the agent matches the lane (`default` → `software-engineer`, `frontend` → `frontend-engineer`) |
| G4 | qa (`qa-codex`) | the current result is `## Engineer: DONE`, or `## QA: PASS` with a verified SHA not equal to `HEAD` (re-check) |
| G5 | qa fallback (`qa-engineer`) | the current result is `## QA: UNAVAILABLE` |
| G6 | close | the current result is `## QA: PASS` and its verified SHA is equal to `HEAD` |
| G7 | PM or engineer | fewer than 3 returns (`## QA: FAIL` or `## Engineer: BLOCKED`) after the newest `## Owner: RESUME` comment |

Notes:

- G1 "clean tree before every launch" is possible because no role may leave uncommitted work: the engineer commits before DONE, and PM and QA do not write files. If a blocked engineer leaves changes, the next launch is denied, and the orchestrator stops the loop and asks the owner.
- G2: after `## Owner: RESUME`, the issue goes back to the PM for grooming.
- G5: the fallback is only possible after `qa-codex` reported that Codex cannot run.

### 5.5 Result markers

| Role | First line |
|---|---|
| PM | `## PM: GROOMED`, `## PM: NEEDS OWNER` |
| Engineer | `## Engineer: DONE`, `## Engineer: BLOCKED` |
| QA | `## QA: PASS`, `## QA: FAIL`, `## QA: UNAVAILABLE`, `## QA: INVALID` |
| Owner | `## Owner: RESUME` |
| Hook | `## Launch: <role> (attempt <n>)` |

`## PM: NEEDS OWNER` and `## QA: INVALID` allow no next launch. The orchestrator escalates.

### 5.6 Failure behavior

- If `gh` or `git` fails (network, auth), the hook denies the call. Unknown facts do not allow a launch.
- Each deny message names the check that failed (for example `G3: current result is ## QA: PASS, expected ## PM: GROOMED or ## QA: FAIL`), so the orchestrator knows what is missing.

### 5.7 Implementation

- Python scripts run with `uv run --script` (inline dependencies, PEP 723), in `.claude/hooks/`, registered in `.claude/settings.json`.
- One shared module reads the issue state (labels, comments with timestamps) with one `gh` call. Each check is a small function.
- The launch comments are the receipts. There is no separate log.

### 5.8 Prose changes

- `docs/team/orchestrator.md`: the launch line; the new markers; the hook deny message replaces most hand-written result queries.
- Role files: the launch line is in the prompt; the result must be posted after launch.
- `docs/process.md`: the hooks enforce the lifecycle; after `## Owner: RESUME` the issue goes back to the PM.

## 6. Codex QA launcher (`qa-codex`)

### 6.1 Call and flow

Call: `qa-codex ROLE=qa ISSUE=<n> RANGE=<base>..<head>`. A Python script run with `uv run --script`.

1. Read the issue body (the acceptance criteria) with `gh`. Do not pass on the engineer's comment.
2. Run `codex exec` with:
   - the most restrictive sandbox that still lets QA exercise the behavior (the Codex spike decides which),
   - the prompt: the QA role file, the criteria, and the range,
   - `--output-schema qa-result.schema.json` and `-o <file>` for the final message.
3. Validate the JSON against the schema, and check that the verified SHA is equal to `HEAD`.
4. Render the issue comment from the JSON and post it with `gh`. The footer has `Checker: codex` and `Retries: <n> (<reasons>)` if there were retries.

The QA result schema contains: verdict (`pass` or `fail`), one entry per criterion (text, verdict, evidence), the tests (command and result, or "not run" with the reason), and the verified SHA. The rendered comment follows the format in `docs/team/qa-engineer.md`.

### 6.2 Failure handling

Claude does not skip Codex because of a small problem. Each failure type has its own rule:

| Failure | Action |
|---|---|
| Transient: network error, server error, short rate limit, crashed process | Retry up to 3 times. Wait 1, 3 and 10 minutes |
| Timeout (default limit 30 minutes, because QA may start the app) | Retry once. If it times out again, post `## QA: INVALID` with the reason → escalate |
| Output does not match the schema, or the verified SHA is not `HEAD` | Retry once. Then post `## QA: INVALID` with the reason → escalate |
| Codex not installed, not logged in, or usage limit reached | Post `## QA: UNAVAILABLE` with the reason → the orchestrator launches the Claude `qa-engineer` fallback |

The fallback posts a normal QA comment with the footer `Checker: claude (fallback)`.

How Codex reports each error (exit codes, error text, usage limit vs. network error) is not documented. The Codex spike finds this out before the script is written.

## 7. QA behavior

QA checks the result against the acceptance criteria. The main evidence is running the behavior, not re-running the engineer's tests (see `docs/research/qa-and-cicd-in-agent-graphs.md`).

For each criterion, QA:

1. Exercises the behavior: runs the command, calls the endpoint, opens the page, reads the document (for a prose task).
2. Judges if a test really covers the criterion, or only mirrors the implementation.
3. Gives a verdict with evidence.

QA also runs the test command from AGENTS.md as secondary evidence. The engineer writes the tests. QA does not change anything in the repo.

`docs/team/qa-engineer.md` gets this behavior and a note that code checks the result format.

## 8. Codex review skill

- Skill: `.agents/skills/codex-review/SKILL.md`, named `codex-review`.
- Trigger: the owner, in natural language ("let Codex review the spec") or with `/codex-review`. Claude derives the target from the conversation: a file, a folder, or a commit range. The skill does not start by itself in the loop.
- AGENTS.md gets one line: "When the owner asks for a Codex review, use the `codex-review` skill."
- What it does:
  1. Runs `codex exec` read-only with a normal review prompt (not adversarial) and a findings schema.
  2. Writes `docs/reviews/<date>-<topic>-codex-review.md`, always.
- Findings format: adapted from the Codex plugin's review schema (openai-codex plugin for Claude Code, with credit): verdict (`approve` or `needs-attention`), summary, findings (severity, title, body, file, lines, confidence, recommendation), next steps.
- The code that runs Codex and captures its output is shared with `qa-codex`.
- No modes. What happens with the findings is decided in the conversation.
- `docs/process.md` gets one rule: "Do not read old reviews in `docs/reviews/` unless the owner points to one."
- For an adversarial review, the owner uses `/codex:adversarial-review` from the Codex plugin. The kit does not wrap it.

## 9. Lovable lane and paint-math

### 9.1 Repo layout

- `paint-math` is a new GitHub repo. The kit is copied in with the README set-up instructions.
- `frontend/` is a git submodule. It points to the repo that Lovable manages.
- The owner creates the Lovable project and connects it to GitHub. This is a manual step unless the Lovable spike shows it works through MCP.
- Nobody edits `frontend/` locally. All frontend changes go through Lovable.

### 9.2 `frontend-engineer`

- Agent file: `.claude/agents/frontend-engineer.md`, with the Lovable MCP tools, Bash, and read tools.
- Role text: a section "Lane `frontend`" in `docs/team/software-engineer.md`.

Flow:

1. Note the base SHA of the main repo: `git rev-parse HEAD`.
2. Send Lovable the goal and the acceptance criteria of the issue in plain words. Lovable does not know about issues or git.
3. Wait until Lovable has finished (detection: see the Lovable spike).
4. If a criterion is not met, send Lovable a follow-up message. Repeat until all criteria are met, within the time budget (default 60 minutes per launch). When the budget runs out, post `## Engineer: BLOCKED` with what is missing.
5. Update the submodule (`git submodule update --remote frontend`). Check that the new submodule commit contains Lovable's change. Commit the pointer update.
6. Run the project test command, if one exists.
7. Post `## Engineer: DONE` with `Commits: <base>..<head>`.

Lovable cost is not a limit. Time is.

### 9.3 QA for frontend issues

Codex checks the range, including the submodule content (`git diff --submodule=diff`). Following section 7, QA exercises the UI in a headless browser if the Codex sandbox allows it (Codex spike). If it does not, QA uses build, tests, and code reading, and the QA comment says that the UI was not exercised.

### 9.4 Demo scope

Two issues in paint-math, both through PM → engineer → Codex QA → close with the hooks active:

1. Lane `frontend`: the canvas shows the curve of an equation that the user enters (Lovable).
2. Lane `default`: a small non-UI part, for example an equation parser and validator with tests (Claude engineer).

The owner can replace these issue ideas. The issues live in the paint-math repo.

## 10. The `later` label

- `docs/process.md` (done in this session): "Issues with the label `later` are out of scope for the current implementation. Do not work on them."
- The orchestrator lists only issues with `ready`. The PM grooms only the issue it gets.
- Guarantee G1 denies every launch on an issue with `later`, also if it has `ready` by mistake.
- The PM gives each follow-up issue (out-of-scope item) the label `later`.
- The owner removes `later` and adds `ready` to start work on an issue.

## 11. Files

| File | Change |
|---|---|
| `.claude/hooks/` | New: guard hook, issue-state module |
| `.claude/settings.json` | New: hook registration |
| `.claude/agents/frontend-engineer.md` | New |
| `.claude/agents/qa-engineer.md` | Unchanged pointer; now the fallback |
| `scripts/qa-codex` (Python) + QA result schema | New |
| `.agents/skills/codex-review/` | New: skill, review schema, render script |
| `.github/workflows/ci.yml` | New |
| `tests/` | New |
| `docs/team/orchestrator.md`, `pm.md`, `software-engineer.md`, `qa-engineer.md` | Changed (sections 4, 5.8, 7, 9.2, 10) |
| `docs/process.md` | Changed (sections 5.8, 8, 10) |
| `docs/task-template.md` | Lane values `default`, `frontend` |
| `AGENTS.md` | Test command; one line for Codex reviews |
| `README.md` | Set-up section |

The exact paths can change in the plan if a spike shows a reason.

## 12. Tests, CI, README

### 12.1 Tests

- pytest for the hook checks, with synthetic issue JSON and a synthetic git state.
- pytest for `qa-codex`, with a fake `codex` command for each failure type (retry, timeout, invalid output, unavailable).
- pytest for the review renderer (JSON → review file).
- No network in the tests.
- AGENTS.md gets the real test command: `uv run --with pytest pytest`.

### 12.2 CI

`.github/workflows/ci.yml` runs the tests on each push and pull request. The graph does not read CI results in v1.

### 12.3 End-to-end proof

- Dogfooding: after the hook wiring task is closed, all later tasks of this repo run with the hooks on.
- paint-math: the two demo issues (section 9.4).

### 12.4 README set-up section

- Prerequisites: `gh` (logged in), `uv`, Codex CLI (logged in), Lovable MCP plugin (frontend lane only).
- Files to copy: AGENTS.md, CLAUDE.md, `docs/process.md`, `docs/team/`, `docs/task-template.md`, `.claude/agents/`, `.claude/hooks/`, the hooks block of `.claude/settings.json`, `scripts/qa-codex` and its schema, `.agents/skills/codex-review/`, the symlink `.claude/skills` → `.agents/skills`.
- Files to adjust: the project description and test command in AGENTS.md; the `frontend/` submodule and the `frontend` lane (Lovable only).
- Labels to create: `ready`, `needs-owner`, `later`.
- The paint-math task checks these instructions. Missing steps are fixed in the README.

## 13. Spikes

Each spike is a plan task. The output is a short findings file in `docs/research/`. If a finding changes this design, the owner decides before the dependent tasks start.

| # | Spike | Questions | Blocks |
|---|---|---|---|
| S1 | Claude Code hooks | Does a hook before a subagent launch see the agent type and the prompt? Can it deny with a reason? Does it work in auto mode? Can a Bash hook reliably match `qa-codex` and `gh issue close`? Do hooks fire for calls inside subagents? Can a hook post a comment (side effect) before the call runs? | Section 5 |
| S2 | Codex CLI | `--output-schema` and `-o` behavior. What each sandbox mode allows: run tests, run the app, write temp files, run a headless browser. How each error shows (network, rate limit, usage limit, auth, not installed): exit codes, error text. Timeout behavior | Sections 6, 8, 9.3 |
| S3 | Lovable MCP | How to detect that a Lovable message has finished. When Lovable's commit reaches GitHub. Can the GitHub connection be made through MCP? | Section 9 |
