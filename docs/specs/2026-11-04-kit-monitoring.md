# Kit monitoring: where the kit spends tokens and time

## Purpose

The owner finds out where the agent-graph-kit itself spends tokens and time, and why retries happen. Then the owner judges what is useful and what is waste. The kit means all of it: the roles, the loop, the hooks, and the documents every launch reads (`AGENTS.md`, `docs/process.md`, `docs/team/`). No part is treated as "real work" apart from "process".

The owner asks three questions:

1. What do we spend the most tokens on?
2. What do we spend the most time on?
3. What does a retry cost, what causes it, and did it help?

Then the owner drills down: what the agents actually do there (files read, tool calls, commands, tests), and whether it is useful.

The owner does the analysis. The tools collect and show data. They draw no conclusions, give no verdicts and sort no cases.

quack-rl is the main data source today (8 stages in the run record, about 650 subagent transcripts). The tools are general: they work for every project that uses the plugin.

## Goals

- Collect step-level data from now on, for every project that uses the plugin: one row per step of each launch
- Collect it at any time, also while a stage runs, not only at the stage end
- Collect the retry cases from the issue record, with what the owner needs to sort them
- Keep the Codex QA event stream, so Codex runs have step detail too
- A marimo notebook in which the owner explores the data: from totals down to single steps, with filters, a view of the running stage, and the retry cases
- Check the existing run record against its spec, so the owner knows whether its numbers can be trusted
- The upstream fixes that quack-rl filed against the kit role files

## Non-goals

- Conclusions, scores or labels made by the tools ("wasteful", "real defect")
- OpenTelemetry, a collector or a docker-compose backend (#32). The step rows are shaped so that a later OTel source can feed the same analysis
- Alerts, and any loop decision that reads monitoring data
- Keeping old transcripts before Claude Code deletes them. The old ones are analysed while they exist
- A rule change for literal QA reading (#257). This stage collects the cases. A review of the PM and QA role files as a whole is a later stage (parked issue)
- Planner (`/stage-start`) session tokens

## Principles

The principles O1 to O5 of `docs/specs/2026-09-26-agent-graph-observability.md` hold. In short:

- O1: no hook, script or role reads monitoring data to make a decision. The issue stays the state
- O2: a failing monitoring write never changes a QA result, a retry count, a comment or a hook decision
- O3: runtime data stays on the owner's machine, with owner-only file permissions. Nothing from it goes into commits, issues or comments without a check for private data
- O4: optional and owner-side. Agents need no knowledge of it. Role files do not change for it
- O5 does not block this stage: the issue record cannot answer "what did the agent do in this launch", so step data is needed

## Part 1: Step rows

A step extractor reads Claude Code transcripts (subagents and the main session) and writes step rows.

Source: the transcript folders of Claude Code (`~/.claude/projects/<project folder>/`, subagent transcripts under `<session>/subagents/`). The extractor reads the transcripts as they are, also while a launch still writes to them. A half-written last line is skipped, not an error.

Output: `<state dir>/agent-graph-kit/steps.jsonl`, the same state dir as `run-record.jsonl` (env var `STEPS_FILE` for the whole path). JSONL, append-only, one flat object per line, a version field `v`. The file has owner-only permissions (0600).

One row per assistant message of a launch (a "step"). Fields, at least:

| Field | Meaning |
|---|---|
| `v`, `id` | Version; stable id (project, transcript id, message id), so a second run adds no duplicate |
| `project`, `stage`, `issue`, `role`, `launch` | As in the run record. `launch` is the id of the launch, the same launch part as the run-record `id`, so steps join to run-record lines. Role and issue come from the first prompt `ROLE=<role> ISSUE=<n>`; the main session has role `orchestrator` |
| `seq`, `time`, `duration_s` | Order in the launch, time of the message, time until the next step (the wait for tool results is part of it) |
| `model` | From `message.model` |
| `input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens` | The usage of this message. A message id seen twice counts once |
| `context_tokens` | Input + cache creation + cache read of this message: the size of the context at this step |
| `tool`, `target` | Tool name of each tool call in the message (for example `Read`, `Bash`, `Edit`), and its target: the file path for file tools, the command for `Bash` (cut to 300 characters), the subagent type for `Agent`. Several tool calls in one message give several values |
| `result_chars`, `is_error` | Size of the tool result in characters, and whether the tool reported an error |
| `kit_doc` | The kit document a `Read` call read (`AGENTS.md`, `docs/process.md`, a file under `docs/team/`, `docs/task-template.md`), else null |

Cost of the kit documents: the first step of a launch shows the context that the launch starts with (system prompt, agent definition, first prompt). The `kit_doc` steps show later reads. Both are visible per launch and per role. The exact token count of one file inside the context is not available from the transcript. The notebook shows the measured numbers and says what they include.

Thinking text, prompt text and tool output text are never written. Only sizes, names, paths and the cut command are.

When it runs:

- From the notebook, on each refresh (the live view)
- At the stage end, from the run-record step that the orchestrator already runs. The `write` command of the run-record script also writes the step rows of the stage. No role file changes for this (O4)
- By hand, with one command that the skill documents

The extractor reads local files only and calls no network.

## Part 2: Retry cases

A case collector builds one row per return round of an issue from the issue comments. A return round is a new launch of a role after one of these markers: `## QA: FAIL`, `## QA: UNVERIFIABLE`, `## QA: INVALID`, `## QA: UNAVAILABLE`, `## Engineer: BLOCKED`, a `## ... NEEDS OWNER` marker, or a PM rewording after one of them.

Fields, at least:

- project, stage, issue, round number, the marker that started the round, the comment URL
- the failed or invalid criterion lines from the QA comment (the lines marked FAIL, INVALID or UNVERIFIABLE), and the matching criterion text from the issue body
- what came next: the next markers up to the next result, whether the issue body was edited in between (a PM rewording), and the commit of the next engineer DONE with its changed files and line counts (from git in the project repo, when the repo is on the machine)
- the cost of the extra round: tokens and time of its launches, joined from the run record and the step rows

The collector does not sort a case. The owner sorts in the notebook (Part 4). The owner's tags are kept in a local file next to the record (`retry-tags.jsonl`), keyed by the case id, so they survive a refresh.

The collector reads issue comments with `gh` (read only), or from a saved issue JSON file as the run-record script does. It writes no comment and changes no label.

## Part 3: Codex QA event stream

This is item 4.2 of the observability spec (#30). `qa-codex` already reads the Codex event stream (`--json`) and keeps only the totals today. It now keeps the whole stream of each attempt in a private folder outside the repo and outside the QA worktree (`<state dir>/agent-graph-kit/codex-runs/`). There is one file per attempt, named for the project, the issue and the time, and the file is also kept on timeout. Files have owner-only permissions. Retention is bounded: files older than 90 days are deleted at the next write.

The step extractor turns these files into step rows with role `qa-codex` (command, tool, tokens where the stream has them).

O2: a failing write never changes the QA result. The sandbox arguments of `qa-codex` do not change.

## Part 4: The notebook

A marimo notebook in the plugin. Marimo is not installed by `/agk:setup` (#188). The notebook starts with one `uv` command, which its skill documents (for example `uv run --with marimo marimo edit <path>`). It reads the run record, the step rows, the retry cases and the tags. It can call the extractor and the collector on refresh.

Views, at least:

- **Totals**: tokens (raw kinds and weighted per provider, with the weights of `docs/run-weights.json`, labelled as an estimate) and time, by project, stage, issue, role, model and retry, with filters for each
- **Drill-down**: from a total to its launches, from a launch to its steps (tool, target, tokens, duration, context size over the steps), and the kit document reads per launch and per role
- **Running stage**: the launches of the current stage with role, issue, start, run time, tokens so far and their last step, plus which launches are still active (a transcript written to in the last minutes)
- **Retry cases**: the table of Part 2 with filters (project, stage, role, marker), each case with its criterion text, QA text, next-round change and cost, and a field where the owner sets a tag and a note

The notebook shows numbers and text. It shows no verdict, no recommendation and no automatic grouping of causes.

## Part 5: Check of the run record

Issue #255: check the run-record lines that exist (quack-rl stages and Stage 18 of the kit) against `docs/specs/2026-10-21-run-record.md`, line kind by line kind, and file findings as follow-ups. Read only.

## Part 6: Upstream fixes from quack-rl

Five issues filed from the quack-rl stage reviews, each a change to kit role files and their built plugin copies:

- #258 orchestrator run-record step and cache rule true in a plugin project
- #259 research notes folder named; reason for the engineer memory cap
- #260 one QA test-run rule, `qa-codex` pre-step evidence, headless browser check
- #261 PM reads `scripts/qa-codex` before NEEDS OWNER on a QA tool problem
- #262 project-waived spend and the Lovable `awaiting_input` pause. Owner decision for its point 1: a credit or spend-limit pause needs the owner, so the engineer stops with `## Engineer: BLOCKED`. It is not expected to happen

#257 (QA fails on literal wording) is not a rule change in this stage. Its case is one row of Part 2. The parked issue for the later review of the PM and QA role files as a whole carries its content.

## Decided by the owner

- Monitoring is about the kit as a whole, including its documents. No split into "real work" and "process"
- The questions are tokens, time, and retries (cost, cause, benefit), then the drill-down
- Live collection while a stage runs, without OpenTelemetry. OTel stays the later plan (#32)
- Focus on collecting from now on; old transcripts are analysed while they exist, not kept
- The tools draw no conclusions; the owner explores in a marimo notebook
- The upstream fixes are in the same stage
- #257: collect the cases now (way A); the review of the role files as a whole is later (way B, parked)
- A Lovable credit or spend-limit pause needs the owner

## Left to the builder

- Names of the skill, scripts and modules; the module split with `run_record.py` (share the transcript reading, do not copy it)
- The exact rule for "still active" in the running-stage view
- How the notebook lays out its views, and its charts
- Whether the case collector is part of the extractor script or its own script

## My calls (planner)

- All monitoring parts live in the plugin, so every plugin project collects data. The notebook and the extractor go into one plugin skill
- Commands are cut to 300 characters; Codex streams are kept for 90 days. The owner can change both
- The step rows are written on notebook refresh and at the stage end, so data is kept even if the owner never opens the notebook
- A main-session transcript gets role `orchestrator` when it ran `/goal`, `planner` when it ran `/stage-start`, else `main`. Planner rows are collected but not analysed in this stage
- The stage of a step comes from the run record when it has the issue, else from the parent issue of the task issue (`gh`, read only), else null
