# OpenTelemetry monitoring: charts that show what happens

## Purpose

The owner opens the Grafana boards and sees in a few seconds which issue, which role and which step spends the tokens and the time. The boards are charts first. Tables are only for drill-down, and they highlight what matters.

The boards of Stage 20 (`docs/specs/2026-11-06-visual-monitoring.md`) are 13 tables and one text panel. They show the right data but no picture. Their time numbers are also wrong: the orchestrator time is clock time from the first to the last message (with idle hours) and is stored once per model, a subagent that stopped on the usage limit counts the wait, and Codex time is always 0. That spec left "the panel types and layout of the boards" to the builder, and no test checked them. This spec fixes the panel types, the colours and the layout.

The data source changes to OpenTelemetry (OTel). Claude Code and Codex export their token use and active time themselves. The kit stops computing them from transcripts for the boards.

## Goals

- OTel export of Claude Code and Codex into a standard local stack: OTel Collector, Prometheus, Loki, Grafana
- Every token count and every time on the boards is attributed to project, stage, issue and role
- A live board and a history board as described in "The boards", with the panel types given there
- A collapsed row "Telemetry" with the standard OTel time-series panels on the live board
- One fixed colour set for all panels (Paul Tol "muted")
- Tests that fail when a chart panel is a table, and a check on real data with screenshots

## Non-goals

- Old stages on the boards. The boards are forward only: they show data from the first stage that runs with OTel on. No back-fill, no fallback to the SQLite store
- Cost in dollars or weighted tokens on the boards. The boards show plain token counts
- Live CPU and memory per agent (parked as #302)
- Alerts, and any loop decision that reads monitoring data
- Changes to the run record (`run_record.py`), its report and the marimo notebook. They stay as they are
- Writers for the plan usage limit in percent (#300, #301). They stay owner decisions
- Hosting the stack in the cloud. Maybe a later stage. This stage keeps the way open: the Collector endpoint, and the Prometheus and Loki addresses Grafana uses, are settings, not fixed values

## Anti-goals

- A dashboard of tables. A panel that this spec names as a chart must not be a table
- A time that counts idle time or counts parallel work twice
- Monitoring data leaving the owner's machine
- A stack that starts on its own, runs at boot, or slows down agent work

## Principles

O1 to O4 of `docs/specs/2026-09-26-agent-graph-observability.md` hold: no hook, script or role reads monitoring data to decide anything (O1); a failing export, a stopped stack or a missing marker never changes a QA result, a retry count, a comment or a hook decision (O2); runtime data stays local (O3); the loop works the same without the stack, and the role files do not change for it (O4).

M1 and M3 of `docs/specs/2026-11-06-visual-monitoring.md` hold: every port listens on `127.0.0.1` only, Grafana needs a login, the admin password is not in the repo; no GitHub token, Claude or Codex credential goes into a container.

Changed and added:

- M2 (new value): the whole stack (Collector, Prometheus, Loki, Grafana) with both boards open uses less than 1 GB RAM in total during agent work, and close to no CPU while no board refreshes. A task measures it on the owner's machine (10 minutes during a running stage, peak RAM and CPU of each container) and records the numbers in `## Engineer: DONE`
- M4: prompt text and agent answers are not exported (`OTEL_LOG_USER_PROMPTS` off for Claude Code, `log_user_prompt` and agent responses off for Codex). Tool names and tool targets (file path, command) are exported, because the boards show the last tool and its target and the kit document reads
- M6: only kit work is stored. Data that does not carry the project tag of a kit project is dropped at the Collector, before it reaches Prometheus or Loki. Sessions and Codex runs of unrelated work leave no trace in the stack
- M7: built-in Grafana panels only. No community panel plugin
- M5: retention of at least one year in Prometheus and Loki, so the history board can compare stages. The task records the disk use of one stage

## Definitions

### Tokens

- Plain token counts, not weighted, shown in millions (`M`) with one decimal, or in thousands (`k`) where a value is below 0.1 M
- Four kinds: cache read, cache creation, output, input. For Codex, `input` is the non-cached input: Codex counts its cached input inside its input tokens, so the cached part is subtracted first and shown as cache read
- Claude and Codex count the same per token. They are added together, and each chart can still tell them apart by colour (QA on Codex has its own colour)

### Active time

- Active time is the time in which an agent works on the task: it thinks, calls a tool, or waits for its own tool, for example a test run, however long it takes
- Not active: the agent's turn ended and it waits for the owner; the session is paused or the machine is off; the agent stopped on a usage limit and waits for the reset. When work continues, the clock runs again
- Source: Claude Code `claude_code.active_time.total` with `type=cli` (tool execution and model answers; idle time is not in it). Codex: the durations of its turns (API requests and tool calls)
- Time per issue and per stage is the union of the active periods. When two agents work at the same time (the orchestrator waits while its subagent works), that stretch counts once. The orchestrator's time counts once, not once per model
- Precision: about one minute (the OTel export interval). This is enough to see which issue and role take long
- Shown in hours with one decimal, or minutes below one hour

### Roles

Orchestrator, PM, engineer, QA on Claude (the `qa-engineer` subagent), QA on Codex (`scripts/qa-codex`). Also: the planner's stage review (`ROLE=planner`) is its own role; the frontend engineer counts as engineer; every other subagent type is "other". The Claude Code attribute `agent.name` gives the subagent type, and `query_source=main` marks the orchestrator.

### Attribution to project, stage and issue

OTel knows the session, the agent id and the subagent type, but not the issue or stage. Only one subagent works at a time (no parallel mode exists), so the issue in work is known while it runs. The kit publishes this as a marker (project, stage, issue, role), and the boards join the OTel data on it. The marker holds the issue until the next issue starts. So the orchestrator's work while a subagent runs, and its follow-up on that issue (reading the result, closing the issue), count to that issue. Only the orchestrator's work before the first launch and after the last issue is closed goes to the stage, with no issue.

Rules for the marker:

- It is written by kit code that already runs at the launch of a subagent or of `scripts/qa-codex`, or derived from the launch receipts (`## Launch: <role> (attempt <n>)`) on GitHub. The builder picks one way and says why
- O2: a failing marker write never blocks or changes the launch. Data without a marker is shown as "no issue", never dropped
- O4: no role file changes for it

### Typical values (a hint, not a focus)

- "Typical issue" and "typical stage" are the median of the earlier issues or stages of the same project with OTel data. The charts show it as a thin dashed grey threshold line where the built-in panel can draw one; else it is left out (M7). Until three stages have data, no line is shown
- A table cell is highlighted (rose, see "Colours") when the value is above the 75th percentile of the same role in earlier stages of the project. Until three stages have data, no cell is highlighted

## Colours

Paul Tol "muted". Each panel uses exactly these values. A role or a token kind has the same colour on every panel.

| What | Colour |
|---|---|
| Orchestrator | indigo `#332288` |
| PM | sand `#DDCC77` |
| Engineer | green `#117733` |
| QA on Codex | cyan `#88CCEE` |
| QA on Claude | wine `#882255` |
| Cache read | teal `#44AA99` |
| Cache creation | olive `#999933` |
| Output | purple `#AA4499` |
| Input | pale grey `#DDDDDD` |
| Planner (stage review) | olive `#999933` |
| Other subagent | pale grey `#DDDDDD` |
| Above typical, long tool call, error | rose `#CC6677` |
| Running launch (dot in the table) | teal `#44AA99` |
| Provider lines in the Telemetry row | Claude indigo `#332288`, Codex cyan `#88CCEE` |
| Typical value | grey dashed line |

## The boards

Both boards have the filters project and stage. Refresh at most every 30 s. Every chart has a tooltip on hover with the values of the bar or block.

### Live board ("Now")

From top to bottom:

1. **Now** (a stat or text panel, one line): the role and issue of the subagent that works now, its return number, its active time, its tokens, the time since its last step, and its last tool with target. When only the orchestrator works: "orchestrator" and its last tool
2. **Tokens per issue, by role** (bar chart, stacked): x axis the issues of the stage in execution order (issue number and short title), y axis tokens. One stack segment per role, in the role colours. The hover shows each segment and the total; a total label on top of the bar only where the built-in bar chart can show it (M7). Issues not started yet show as empty slots. Typical issue as dashed line
3. **Active time per issue, by role** (bar chart, stacked): the same layout with active time
4. **Timeline** (state timeline): one row for the orchestrator on top, then one row per issue in execution order, x axis the clock time of the stage, with a "now" mark. A block per launch in the role colour. A return (the engineer again after a QA FAIL) keeps the role colour and shows the text "↺" in the block (built-in value mapping). Hover on a block: issue, role, return number, active time, tokens
5. **Plan usage limit** (bar gauges, small): one per account and window (Claude 5 h, Claude week, Codex 5 h, Codex week) where a source exists; else one line "no source". The source stays as decided in Stage 20 (`docs/research/usage-limit-source.md`)
6. **Launches of this stage** (table, newest first): columns in this order: issue, role, tokens, active time, return, model, start (time only). Each column only as wide as its content, no line wrap, no empty space between columns. A running launch has a teal dot before the role. Tokens and active time cells are highlighted as in "Typical values"
7. **Telemetry** (a row, collapsed by default), time-series panels over the chosen time range:
   - token rate by kind (stacked, kind colours)
   - active time per hour, Claude and Codex
   - API requests per minute, Claude and Codex
   - API latency p50 and p95
   - API errors
   - tool calls by tool, and p95 tool duration
   - lines of code added and removed
   - commits and pull requests

### History board ("Stages")

From top to bottom:

1. **Tokens per stage, by role** (bar chart, stacked): one bar per stage, typical stage as dashed line (rule in "Typical values")
2. **Active time per stage, by role** (bar chart, stacked): same layout
3. **Token kinds per stage** (bar chart, stacked, kind colours)
4. **Selected stage: tokens per issue, by role**: the same chart as on the live board, for the stage in the filter
5. **Most expensive issues of all stages** (horizontal bar chart, stacked by role): the top 10, labelled with stage and issue
6. **Drill-down**: a click on a stage bar sets the stage, a click on an issue bar opens its launches, a click on a launch opens its steps. The steps of a launch are a bar chart: one bar per tool call with its duration (rose above 2 minutes; hover gives the tool and target), and a line for the context size. Below it, a compact launches table and a compact steps table, with the column rules of the live board table
7. **Kit document reads per role** (bar chart; hover gives the documents)

## Parts

### Part A: Export

- Claude Code: the environment variables that turn on the OTel export of metrics and logs (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, the exporters, OTLP protocol and the local Collector endpoint), with `OTEL_LOG_TOOL_DETAILS` on and prompt logging off (M4)
- Codex: an `[otel]` block in `~/.codex/config.toml` with the local Collector endpoint (Codex ignores `otel` in a project-level config)
- The project tag (M6): the data of each kit project carries the OTel resource attribute `agk.project` with its `owner/name`. For Claude Code, the tag is not set per project: Claude Code ignores telemetry variables in a project's `.claude/settings.json` (project settings can only turn telemetry off), and a fixed tag in the user settings would tag the sessions of every project as one project. Instead, the user settings name the `otelHeadersHelper` `<state dir>/otel-headers.py` (issue #324). Claude Code runs it in the folder of each session; it prints the header `x-agk-project` with the `owner/name` of the entry of `monitor-projects.json` whose repo is that folder or a parent of it, else no header. The Collector moves the header into `agk.project`. Codex runs started by `scripts/qa-codex` carry the tag in `OTEL_RESOURCE_ATTRIBUTES` (the sandbox arguments do not change). The Collector keeps only data with a tag from the project list of the stack and drops the rest
- The user settings (`~/.claude/settings.json` and `~/.codex/config.toml`) are the owner's step, done once for all projects, with no step per project; no agent edits them. The Claude Code block names no project and no path with the plugin version (`board.py up` writes the helper to the fixed state path). The kit prints the exact text to paste (the monitor `SKILL.md`, and the output of `/agk:setup` for a plugin project). The task names this step to the owner in words
- A check after setup: one short Claude Code session and one Codex run show up in Prometheus and Loki

### Part B: The stack

- One `compose.yaml` in the monitor skill folder with the OTel Collector, Prometheus, Loki and Grafana, each image pinned to an exact version at least two weeks old. Grafana provisions the data sources and both boards from files in the skill
- One command starts the stack, one stops it (as `board.py up` and `board.py down` today). Nothing starts on boot
- M1, M2, M3, M5 hold. The Collector receives OTLP on `127.0.0.1` only
- A small host process provides the issue list, titles, execution order and usage-limit values (see "My calls"). It never writes to GitHub
- The SQLite store, the loader and the Stage 20 boards leave the stack. The run record, `steps.py`, `cases.py`, the notebook and their files stay

### Part C: Attribution marker

As in "Attribution to project, stage and issue". A test shows that usage with a marker gets the right issue and role, and usage without a marker shows as "no issue".

### Part D: The boards

As in "The boards" and "Colours". Board files are JSON in the skill folder.

Tests (run without starting Grafana):

- Panel types: each panel named in "The boards" has the type given there. A chart panel that is a table, or a table panel that is not in the list, fails the test
- Colours: each role and token kind uses its colour from "Colours", on every panel
- Table columns: the two launches tables have the columns in the given order
- Queries: every query of the board files is valid for its data source (PromQL or LogQL syntax check, and the label names exist in the Collector configuration)

Check on real data, recorded in `## Engineer: DONE`: one stage (or at least two issues) runs with the stack up; screenshots of both boards, and the M2 and M5 numbers. QA compares the screenshots with "The boards".

### Part E: Docs

- The monitor `SKILL.md`: the commands, the owner's export settings, the URL, what each board shows
- The living spec `docs/specs/agent-graph-kit.md`, section "Monitoring stack (optional)": the new stack in short

## Decided by the owner

- A monitoring dashboard is charts first. Tables only for drill-down or with highlighting
- The main questions: which issue spends the tokens and the time, and which role or step (for example review or engineer) takes long. Stage totals and stage duration alone are of little use
- Tokens: plain counts in millions, not weighted; Claude and Codex count the same per token and are shown together, with Codex QA in its own colour. Cache read and cache creation are the main kinds
- Active time: the time the agents need to finish the issue or stage. Waiting for an own tool or script counts. Idle time, pauses and shutdowns do not. Parallel work counts once
- "Typical" values are only a hint, not the focus. No "returns per issue" panel
- No parallel agents: one subagent at a time, the orchestrator runs next to it
- Timeline as drawn; hover shows the tokens of a block
- Tables compact, important columns left, no empty space; running launch as a coloured dot, not as a word
- The plan usage limit is a small panel
- OpenTelemetry in this stage, forward only, no fallback for old stages
- Built-in Grafana panels only, no community plugin (M7)
- Sessions outside the kit are dropped (M6)
- A standard stack: Prometheus and Loki (with the OTel Collector and Grafana), below 1 GB RAM
- Colours: Paul Tol muted; orchestrator indigo, PM sand, engineer green, QA Codex cyan, QA Claude wine; token kind colours as in "Colours"
- The standard OTel panels as a collapsed "Telemetry" row on the live board

## My calls (planner)

- The SQLite store, the loader and the Stage 20 boards leave the stack, because the boards are forward only and read OTel data. The run record and the notebook stay
- "Typical" is the median of earlier stages of the same project; highlighting starts at the 75th percentile of the same role; both need three stages of data
- Retention of one year (M5)
- Tool targets are exported (M4), because the boards need the last tool and target and the kit document reads; prompt text stays off
- A return keeps the role colour and shows "↺" (no border: built-in panels only)
- A small host process reads the stage's sub-issues, titles and order from GitHub (read only, every few minutes) and the usage-limit files, and gives them to Prometheus. It replaces the Stage 20 loader for these facts. M3 holds: the GitHub token stays on the host
- The planner's stage review has its own colour (olive); the frontend engineer counts as engineer; other subagents are "other" (pale grey)
- Orchestrator work belongs to the issue in work until the next issue starts
- Time precision of about one minute

## Left to the builder

- The marker mechanism, within the rules of "Attribution to project, stage and issue"
- How the Collector feeds Prometheus and Loki (for example OTLP into both, or a Prometheus exporter), and the exact versions
- Panel sizes and the exact Grafana panel options, as long as the panel types, order and colours above hold
- Metric and label names inside the kit (the OTel names of Claude Code and Codex are given)
