# Run record: keep the cost of every launch

## Purpose

The owner looks back at what a stage, an issue, a role and a model cost: tokens (weighted to a rough plan-limit estimate), time and owner escalations. The numbers live in one local file that grows over time and that a database or Grafana can load later. The plugin writes it, so a plugin project (for example quack-rl) collects data on its own.

Today `scripts/run_report.py` (see `docs/specs/2026-10-19-run-report.md`) prints a report from the subagent transcripts and loses the numbers when Claude Code deletes the transcripts. This spec keeps the numbers.

## Goals

- One record per launch and model, kept outside the repo, for every project on the machine
- Codex QA and the Claude QA fallback both show, so QA cost is complete
- The orchestrator (main session) shows, with a stated limit
- The model of each launch is always recorded
- The format is ready for a later live writer (OpenTelemetry, issue #32) and a later database. No OpenTelemetry code now

## Non-goals

- Planner tokens (the `/stage-start` session). Not in this version
- A live view, outlier detection, memory and compute numbers
- Any OpenTelemetry code, collector or docker-compose file
- A claim that the weighted total is the real plan use. It is an estimate

## The record file

Path: `<state dir>/agent-graph-kit/run-record.jsonl`. The state dir is built like the one of `codex-qa-usage.jsonl` (see "Token record" in `docs/specs/agent-graph-kit.md`): the env var `RUN_RECORD_FILE` (the whole path), else `$XDG_STATE_HOME`, else `~/.local/state`. The file lies outside the git tree and is never committed or posted. One file serves all projects on the machine.

Format: JSONL, append-only, one flat JSON object per line. Fields:

| Field | Meaning |
|---|---|
| `v` | Format version, an integer. Starts at 1 |
| `id` | Launch id, stable text, so writing the same launch twice adds no second line. Claude subagent line: project, the subagent transcript file id, model. Codex line: project, issue, the `time` of the Codex record line. Orchestrator line: project, session id, model, `measured` or `estimate`. Issue line: project, issue || `project` | The repo name (`owner/repo` from the git remote, else the folder name). Issue numbers repeat across projects |
| `stage` | The stage issue number, or null when unknown |
| `issue` | The task issue number, or null (orchestrator lines have null) |
| `role` | `pm`, `engineer`, `qa`, `qa-codex`, `orchestrator` (the role names `run_report.py` uses, plus the two new) |
| `provider` | `claude` or `codex` |
| `model` | The model name as the transcript or the Codex record gives it (for example `claude-sonnet-5-5`) |
| `effort` | The effort value if the source gives one, else null |
| `input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens` | Raw counts. For Codex: `input_tokens`, `cached_input_tokens` (stored in `cache_read_tokens`), `output_tokens`; `cache_creation_tokens` is 0 |
| `start`, `end` | UTC ISO 8601 time of the first and last message of the launch |
| `retry` | 0 for the first launch of a role on an issue, 1 for the next, and so on (count of launch receipts of that role group before this one) |
| `estimate` | `false` for measured lines. `true` for an estimated line (see "Orchestrator") |
| `source` | `transcript`, `codex-record`, `session-total` |

One line per launch and model: a launch that used two models writes two lines with the same launch part of `id`. Weights are not stored. Per-issue facts that are not a launch (escalations, time from first receipt to close) are lines with role `issue`: `issue`, `stage`, `escalations` (count of `needs-owner` labels or `## ... NEEDS OWNER` markers, as in `run_report.py`), `start` (first receipt), `end` (close time), all token fields 0.

## Writer

A script in `plugin/bin/` (name is the builder's choice) with a command line like `run_report.py`: it reads local files only, calls no network, writes only the record. It takes the stage issue number, the issue JSON as `run_report.py` does (the orchestrator produces it with `gh issue view --json number,comments,closedAt,labels` for each issue), the transcript folder, and optionally the Codex usage file.

- It reads subagent transcripts as `run_report.py` does and adds `model` (from `message.model` of the assistant messages), `start` and `end`
- It reads `codex-qa-usage.jsonl` and writes one `qa-codex` line per Codex run. The Codex line has no project field in its source, so the writer fills in the project of the call. A Codex line is matched to the stage only by issue number and by time (between the first receipt and the close of that issue)
- It skips a line whose `id` is in the file already, except orchestrator lines (see "Orchestrator"). A reader that sees one `id` twice takes the last line
- Which transcripts count: only those whose first prompt has `ROLE=<role> ISSUE=<n>` with `<n>` in the issue list the writer got (as `run_report.py` does). All other transcripts in the folder are ignored, so other stages and sessions are no problem. The orchestrator session is the one exception: it is passed explicitly
- Codex lines that match no issue of the list, or whose `time` is outside the window of that issue, are not written. The writer prints how many it skipped. The window runs from the first launch receipt of the issue to its close time, or to now when the issue is still open. Each Codex run is one line with its own `id`, so two runs of one issue never merge. My call: `qa-codex` is not changed, the Codex record keeps its fields
- It never writes prompt text, comment text or output text

The share of `run_report.py` that the writer needs (transcript reading, receipt counting, escalation reading) moves to a module that both use, so the plugin script does not copy the code. `run_report.py` itself stays in `scripts/` and reads the record when given `--record <file>`.

## Orchestrator

The orchestrator runs the writer once, at the end of the stage, in the same step as the end-of-stage plugin bump (see `docs/team/orchestrator.md`), and when no plugin changed too.

The main-session transcript has no `ROLE=` prompt. The writer takes the path or session id of the orchestrator session as an argument. If the orchestrator cannot learn it, the writer may use the newest main-session transcript of the project folder, and it must print the file it used. This is a heuristic and is accepted. Orchestrator lines are always appended; the number grows if the writer runs again, and a reader takes the last line per `id`. If `cost-state` is missing or cannot be trusted, the writer sums the assistant messages of the transcript instead (`source: transcript`). The main-session transcript also has a record of type `cost-state` with `modelUsage` per model (input, output, cache read, cache creation, thinking) and `totalCostUSD` for the session so far. It is not checked whether the session totals include subagent tokens. The builder checks this before using it: if they do, the writer must subtract the subagent lines to avoid counting twice.

The orchestrator number is measured up to the moment the writer runs. The orchestrator spends more after that (the report and the final answer). So:

- The measured line has `estimate: false` and `source: session-total` or `transcript`, and the spec of the report says the number is not complete
- A second line, role `orchestrator`, `estimate: true`, carries an educated guess of the total. The method and the first factor are the builder's call and are written in the spec of the report. The first version may use a fixed factor and says so

## Plan-limit weights

A small table in one file in the kit (the builder chooses the name), edited by the owner. Factors per token kind: new input, output, cache write, cache read. The first values are the public API price ratios: 1, 5, 1.25, 0.1. This is an assumption, not measured against the plans.

- Claude and Codex lines are weighted and totaled separately. They belong to different plans. No combined number
- The report prints the weighted total next to the raw counts, and labels it "estimate from price ratios, not measured plan use"
- Weights are applied when reading, never stored. Changing the table re-reads old lines with the new weights

The owner can hand-enter the percent of the session limit used at the start and at the end of a stage. The report has a place for the two numbers per stage (a second file next to the record, `run-record-limits.jsonl`, so the run record keeps one kind of line; fields: `v`, `project`, `stage`, `time`, `point` = `start` or `end`, `percent`, `plan`). The report prints them next to the weighted total of that stage so the weights can be checked over time. Nothing reads the percent automatically in this version.

## Retries

`retry` counts launches per role group on an issue. Both lines of a launch with two models carry the same value. It does not say why a launch was repeated (a QA FAIL, a miss, a limit stop). The report shows the count and claims nothing more.

## What the report shows (the minimum)

For a stage and for the record as a whole, from the file: tokens per role, per issue, per model, per project; weighted totals per provider; time per issue; escalations; retries. Read-only, Markdown to stdout, as `run_report.py` does.

## Left to the builder

- Names of scripts and files, the module split, test layout
- How the factor for the orchestrator estimate is chosen
- How the orchestrator learns its own session id or transcript path
- Whether `cost-state` is used for the orchestrator line or the assistant messages are summed

## Not in this spec

- Planner tokens, live writing, OpenTelemetry export (#32), the launch-to-transcript link (#31)
- A database or Grafana. The file shape is chosen so a later load is simple: flat lines, a stable `id`, a version field
- Measuring cache gaps between requests
