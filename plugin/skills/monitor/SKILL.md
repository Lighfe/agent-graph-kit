---
name: monitor
description: "Write the step rows of Claude Code launches and Codex QA attempts: one JSON line per assistant message or Codex command and turn (tools, tokens, time), kept outside the repo. Use when the owner asks what a launch did or cost step by step, also while a stage still runs, or wants to explore tokens and time in the monitor notebook."
---

# Monitor

This skill writes one row per step (assistant message) of each Claude Code launch, and one per command and per turn of each Codex QA attempt, so the owner can see what each launch did and what it cost. It reads the transcripts as they are, also while a launch still runs. It writes no prompt, thinking or tool output text: only sizes, tool names, file paths and the Bash command cut to 300 characters. The rows are for the owner to read; no hook, script or role uses them to decide anything.

## Steps

1. Run the script from this skill's folder in the project root:

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/steps.py" collect --project <owner/name> [--transcripts <transcript folder>] [--codex-runs <stream folder>] [--stage <stage issue number>]
   ```

2. The script prints how many rows it wrote. Running it again adds no second row for the same step.

- `--transcripts`: default `~/.claude/projects/<current dir with each character that is not a letter or digit replaced by ->`. Every `*.jsonl` under it is read, subagent transcripts included.
- Role and issue come from the first prompt `ROLE=<role> ISSUE=<n>`. A transcript without it has issue null and role `orchestrator` (`/goal`), `planner` (`/stage-start`, `/agk:stage-start`) or `main`: the first user line that starts with `<command-name>/goal</command-name>` or a stage-start command tag decides.
- Stage: `--stage`, else the stage of a run-record line of the issue, else the parent issue from `gh api repos/{owner}/{repo}/issues/<n>/parent` (read only, one call per issue), else null.
- A step of a launch that is still running can be written before it is complete (its last tool results or its `duration_s` missing); a later run does not change a row that is already written.

## Codex QA attempts

`qa-codex` saves the whole Codex event stream (`codex exec --json` stdout) of each QA attempt that started the Codex process, also a failed one and the partial stream of a timeout. `collect` reads these files too:

- `--codex-runs`: the stream folder. Default `$CODEX_RUNS_DIR`, else `$XDG_STATE_HOME/agent-graph-kit/codex-runs/`, else `~/.local/state/agent-graph-kit/codex-runs/`. Folder mode 0700, file mode 0600: a stream can hold command output and messages, so it stays private and local.
- File name: `<project with / as __>-<issue>-<attempt start, UTC %Y%m%dT%H%M%S>.jsonl` (`-2`, `-3`, … before `.jsonl` for a second attempt in the same second). Only the files of `--project <owner/name>` are read; `--project` must be the `owner/name` form for them to match.
- Retention: at each save, `qa-codex` deletes the `*.jsonl` files of the folder older than 90 days (modification time).
- Rows: role `qa-codex`, `launch` the file name without `.jsonl`, `issue` and `time` (the attempt start) from the file name, `duration_s` and `model` null, the stage as for transcripts. One row per `command_execution` item (`tool` `["command_execution"]`, `target` the command cut to 300 characters, `result_chars` the output length, `is_error` for a non-zero exit code, tokens 0) and one per `turn.completed` (`input_tokens` and `context_tokens` the Codex `input_tokens`, `cache_read_tokens` the cached tokens, `cache_creation_tokens` the cache-write tokens). No row holds the command output or message text.
- A missing stream folder gives no Codex rows and no error.

The step file is `$STEPS_FILE`, else `$XDG_STATE_HOME/agent-graph-kit/steps.jsonl`, else `~/.local/state/agent-graph-kit/steps.jsonl`, with mode 0600. The `write` command of the run-record skill also writes the step rows of a stage. Spec: `docs/specs/2026-11-04-kit-monitoring.md`, Part 1.

## Retry cases

`cases.py` writes one row per return round of an issue, so the owner can see what a retry cost, what caused it and what changed. It sorts and judges nothing; the owner sorts the cases.

```bash
uv run --script "${CLAUDE_SKILL_DIR}/cases.py" collect --project <name> (--issues <file> | --repo-slug <owner/repo> --stage <n>) [--repo <project repo path>]
```

- `--issues`: a saved issue JSON file in the form that `run_record.py write --issues` reads, with an optional `userContentEdits` list (`{"editedAt": ...}`) per issue. `--repo-slug`: reads the sub-issues of stage `<n>`, their comments and their body edit times (GraphQL `userContentEdits`, every page) with `gh`. All `gh` calls are reads; the script writes no comment and changes no label.
- A round marker is a comment whose first line is `## QA: FAIL`, `## QA: UNVERIFIABLE`, `## QA: INVALID`, `## QA: UNAVAILABLE`, `## Engineer: BLOCKED` or a `## ... NEEDS OWNER` line. It starts a round when a launch receipt (`## Launch: <role> ...`) comes after it before the next round marker. The round lasts until the next marker that starts a round, or the last comment. Comments by others than the owner are ignored.
- Fields: `id` (`<project>:<issue>:<round>`), `project`, `stage`, `issue`, `round`, `marker`, `comment_url`, `failed_lines` (the lines of a QA marker that start with `- [ ]`, not indented, and end with ` - FAIL`, ` - INVALID` or ` - UNVERIFIABLE`), `criteria` (the matching `- [ ]` lines of the current issue body), `next_markers` (the PM, Engineer and QA result markers after the round marker), `body_edited` (null without edit data), `commit` (the `Commits:` range of the first `## Engineer: DONE` of the round), `files_changed`, `lines_added`, `lines_removed` (from `git diff --numstat` with `--repo`, else null), `tokens` (per provider, from the run-record lines that start in the round), `seconds` (the `duration_s` sum of the step rows in the round). No matching data gives null.
- The case file is `$XDG_STATE_HOME/agent-graph-kit/retry-cases.jsonl`, else `~/.local/state/agent-graph-kit/retry-cases.jsonl`, mode 0600. A run replaces only its own rows: the rows of its project and its stage (with no `--stage`, the rows of its project with `stage` null) and every row with the same `id` as a new case. All other rows stay, so the file holds the cases of several projects and stages. Lines that are not a JSON object with an `id` are dropped. The file is written as a whole through a temp file and a rename. Spec: `docs/specs/2026-11-04-kit-monitoring.md`, Part 2.

## Notebook

`explore.py` is a marimo notebook to explore the run record, the step rows and the retry cases. Start it in the project root with one command:

```bash
uv run --with marimo --with polars marimo edit "${CLAUDE_SKILL_DIR}/explore.py"
```

marimo and polars are not part of the setup (`/agk:setup` does not install them); `uv run --with` fetches them for this one run. The notebook shows numbers and text only: no verdict, no recommendation, no automatic cause group.

- Data: the run record (`$RUN_RECORD_FILE`, else `$XDG_STATE_HOME/agent-graph-kit/run-record.jsonl`, else `~/.local/state/agent-graph-kit/run-record.jsonl`; the last line per `id` counts) and the step rows (`$STEPS_FILE`, else `steps.jsonl` in the same folder). A missing file gives empty tables; a line that is not JSON is skipped. The loaders and joins are in `data.py` (standard library only).
- Weights: `$RUN_WEIGHTS_FILE`, else `docs/run-weights.json` of the project when it exists, else `run-weights.json` of this skill (the same content as `docs/run-weights.json` of the kit repo). A Codex line's `input_tokens` includes its cached input (`cache_read_tokens`), so its weighted value counts `max(input - cached, 0)` as input and the cached part only once, at the cache read factor.
- Totals: the four token kinds and the time (`end` minus `start`) by project, stage, issue, role, model and retry, with a filter for each. Weighted totals per provider are an estimate from price ratios, not measured plan use; Claude and Codex are never added together, and lines with no provider have no weighted value. Lines with `estimate: true` are rows apart from the measured lines.
- Drill-down: select a total to see its launches, and a launch to see its steps (tool, target, tokens, duration, context size over the steps). Kit document reads (`kit_doc` not null) per launch and per role. A launch with no step rows shows an empty table. A Codex record line holds the time Codex reported the usage, not the attempt start that names the stream file, so it joins the `qa-codex` launch of the same project and issue with the newest attempt start at or before that time.
- Running stage: the launches of the chosen stage with role, issue, start (first step time), run time, tokens so far and the last step (highest `seq`). A launch is active when its newest step time is at most 5 minutes before now. A Codex QA attempt counts as active only in the 5 minutes after its start, since its rows carry the attempt start as `time`.
- Retry cases: a table with one row per case of `retry-cases.jsonl` (written by `cases.py`, in `$XDG_STATE_HOME/agent-graph-kit/`, else `~/.local/state/agent-graph-kit/`), with filters for project, stage, role, marker and tag. The role of a case is the word between `## ` and the first `:` of its marker (`## QA: FAIL` gives `QA`). Each row shows the criteria, failed lines, next markers, commit, changed files and lines, body edit, tokens per provider, seconds, and your current tag and note.
- Tags: pick a case, write a free-text tag and a note, and save. There are no preset tags or causes; the tag filter offers the tags in use and "no tag". Each save appends one line `{case_id, tag, note, time}` (UTC) to the tag file `retry-tags.jsonl` in the same state folder, with mode 0600; the last line per case wins, so an empty tag and note clears the tag. A collect rewrites only the case file: tags stay, and a tag of a case that is no longer in the case file stays in the tag file but is not shown.
- Refresh: the button runs `steps.py collect --project <chosen project>` in the current folder; with a chosen stage it then runs `cases.py collect --project <project> --repo-slug <project> --stage <stage>`, and the notebook reads the step rows, cases and tags again. With no stage chosen, no case collect runs. The stage list is read when the notebook opens or the project changes, so a refresh keeps the chosen stage. Opening or exporting the notebook runs no collect and writes no tag line.

## Export settings

Claude Code and Codex send their OTel data to the Collector of the monitoring stack (below) when you set these two blocks. They are your own user settings files, so you paste them by hand, once for all projects; no agent edits them. `/agk:setup` prints the same two blocks. Spec: `docs/specs/2026-11-13-otel-monitoring-boards.md`, Part A.

Claude Code: merge this block into your user settings `~/.claude/settings.json`, once. This is the one user step for all projects; there is no step per project. Do not put it into a project's `.claude/settings.json`: Claude Code ignores telemetry variables in a project's .claude/settings.json (project settings can only turn telemetry off); set them in your user settings. (Claude Code 2.1.303 says it so: "Claude Code ignores these telemetry variables in project settings. A project's settings files can only turn telemetry off.") `OTEL_LOG_USER_PROMPTS` is not set, so prompt text is not exported.

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
    "OTEL_LOG_TOOL_DETAILS": "1",
    "OTEL_METRIC_EXPORT_INTERVAL": "60000"
  },
  "otelHeadersHelper": "~/.local/state/agent-graph-kit/otel-headers.py"
}
```

- The block names no project. Claude Code runs the `otelHeadersHelper` in the folder of each session and sends the JSON object it prints as OTLP headers. The helper (`otel_headers.py` of this skill) looks up the session folder in the project list `monitor-projects.json` (see "Monitoring stack"): when the folder is the `repo` of an entry, or a folder below it, it prints `{"x-agk-project": "<owner/name>"}` of that entry (the deepest `repo` wins); else `{}`. The Collector moves the header into the resource attribute `agk.project` and drops data without a listed project, so a session outside every kit project (no git repo, or a repo not in the list) sends nothing that is kept, and data of one project never carries the tag of another.
- `board.py up` writes the helper to `<state dir>/otel-headers.py`, next to the project list, mode 0700, on every `up`. The path does not hold the plugin version, so a plugin update does not break the user step; the next `up` writes the new helper. Run `board.py up` once before the user step: without the file, Claude Code shows "otelHeadersHelper failed; telemetry is not being exported". With `XDG_STATE_HOME` set, the path is `$XDG_STATE_HOME/agent-graph-kit/otel-headers.py`; `/agk:setup` prints the path that fits.
- Claude Code sends OTLP over HTTP (port 4318), not gRPC: checked with Claude Code 2.1.303, only its HTTP exporters send the helper's headers; with `grpc` the header did not arrive and the Collector dropped the data. Codex stays on gRPC (4317).
- When a project's `.claude/settings.json` still holds an older export block (with `OTEL_RESOURCE_ATTRIBUTES` or `grpc`), remove it: the user block is the only place.
- The helper always exits 0 and prints a JSON object (Claude Code takes empty output as a failure). It reads one file, starts no process and makes no network call, so a session starts as before when the stack is down.
- Add a project by adding its entry to `monitor-projects.json` and running `board.py up` again (see "Monitoring stack"); the user settings do not change.

Codex: add to `~/.codex/config.toml` (Codex ignores `otel` in a project-level config). Logs and metrics only: the Collector has no traces pipeline.

```toml
[otel]
log_user_prompt = false
exporter = { otlp-grpc = { endpoint = "http://127.0.0.1:4317" } }
metrics_exporter = { otlp-grpc = { endpoint = "http://127.0.0.1:4317" } }
```

- Key names, checked against Codex 0.153.4: the `[otel]` table has the keys `exporter` (logs), `trace_exporter`, `metrics_exporter`, `log_user_prompt` and `environment`, read from the installed binary. A wrong exporter variant is refused by `codex exec -c 'otel.exporter={bogus={endpoint="x"}}'` with `unknown variant ... expected one of none, statsig, otlp-http, otlp-grpc`, and `otlp-grpc` is accepted. Codex has no key for agent responses, so there is nothing to switch off for them; `log_user_prompt = false` is the prompt switch. The Collector deletes the response attributes as a second guard (see "Monitoring stack"). Codex tool output is exported in clear text and has no switch (`docs/research/observability-in-agent-graphs.md`, 3.1).
- `scripts/qa-codex` runs `codex exec --ignore-user-config`, so your `[otel]` block is not read for QA runs. It passes the same exporters as `-c otel.exporter=...`, `-c otel.metrics_exporter=...` and `-c otel.log_user_prompt=false` on the `codex exec` command line, and sets `OTEL_RESOURCE_ATTRIBUTES=agk.project=<owner/name>` in the environment of the run (the `owner/name` of the issue URL; an `agk.project` entry already there is replaced, other entries stay). Checked with Codex 0.153.4: a run with that variable sent logs whose resource attributes held `agk.project`. When the project is unknown, it passes neither. The sandbox arguments do not change, and an exporter that cannot reach the Collector changes no QA result, retry count or comment.
- No trace exporter is set for either tool.

## Monitoring stack (optional)

`board.py` starts and stops an optional stack of four Docker containers: the OTel Collector, Prometheus, Loki and Grafana. Docker is needed for this part only; the rest of the skill runs without it. `/agk:setup` does not install Docker. Spec: `docs/specs/2026-11-13-otel-monitoring-boards.md`, Part B. Run it from the project root the first time (it reads the project from the current folder):

```bash
uv run --script "${CLAUDE_SKILL_DIR}/board.py" up     # check Docker, start the stack in the background, print the URLs
uv run --script "${CLAUDE_SKILL_DIR}/board.py" down   # stop the stack; exit 0 also when it is not running
```

- Ports, all on `127.0.0.1` only (never on another address). Each can be changed with an environment variable set when you run `up`:

  | Service | Port | Variable |
  |---|---|---|
  | Collector, OTLP gRPC | 4317 | `AGK_OTLP_GRPC_PORT` |
  | Collector, OTLP HTTP | 4318 | `AGK_OTLP_HTTP_PORT` |
  | Prometheus | 9090 | `AGK_PROMETHEUS_PORT` |
  | Loki | 3100 | `AGK_LOKI_PORT` |
  | Grafana | 3000 | `AGK_GRAFANA_PORT` |

  Prometheus also scrapes the host process `facts.py` at the gateway address of the compose network (for example `172.25.0.1:9464`, port `AGK_FACTS_PORT`, see "Facts" below). `AGK_FACTS_PORT` is a port variable of `up` like the others.
- Nothing starts on boot and nothing restarts by itself (`restart: "no"` on every service). `down` stops the stack; the data stays in the Docker volumes `agk-monitor_prometheus-data` and `agk-monitor_loki-data`.
- What the stack holds: metrics in Prometheus and logs in Loki, each kept for 365 days. Claude Code and Codex send OTLP to the Collector. The Collector keeps only data of the kit projects: it drops all data whose resource attribute `agk.project` is missing or is not in the project list. Before that filter, it sets `agk.project` from the request header `x-agk-project` when the header is there (Claude Code sends it through the `otelHeadersHelper`, see "Export settings"); data without the header (Codex sets `agk.project` itself) stays as it is. The list is `$XDG_STATE_HOME/agent-graph-kit/monitor-projects.json` (else under `~/.local/state`), mode 0600, a list of `{"project": "owner/name", "repo": "<path of the project repo>"}`. When the file is missing, `up` writes it once with the current project (`owner/name` from `gh repo view`, the current folder as repo); add other projects by hand and run `up` again. Each `up` also writes the `otelHeadersHelper` to `<state dir>/otel-headers.py`. As a second guard behind the export settings, the logs pipeline deletes the attributes `prompt`, `user_prompt`, `response`, `response_text`, `output_text`, `assistant_message` and `last_assistant_message`.
- Grafana: `http://127.0.0.1:3000`, user `admin`, password in `<state dir>/grafana-admin` (`$XDG_STATE_HOME/agent-graph-kit/grafana-admin`, else under `~/.local/state`), mode 0600. `up` writes a random value on the first start and reuses it after. `board.py` prints the path of the file, never the value. Anonymous access, sign-up, update checks, usage reports and the news feed are off. Two data sources are provisioned: `prometheus` (uid `agk-prometheus`) and `loki` (uid `agk-loki`). No community plugin is installed. The boards come from `grafana/boards/`: the live board "Now" (`live.json`, see "The live board" below) and the history board "Stages" (`history.json`, see "The history board" below).
- First start: Docker downloads the four images, each pinned to an exact version (tags and push dates are in `compose.yaml`).
- What the containers see: their own config files (read only) and the password file. No token or credential: no `gh`, Claude or Codex folder or variable.
- Failures: without `docker` on PATH, or when `docker info` fails (daemon not running, no access), `up` names Docker, exits 2 and starts nothing. Without a project list and without `gh`, `up` exits 2 and starts nothing. When `docker compose up` fails (for example a port is in use), `up` names the ports, stops what it started and exits 1.
- RAM: the four containers together use about 240 MiB right after `up` with no load, and about 420 MiB after a few minutes of Loki and Prometheus data (measured with `docker stats --no-stream`), well below the budget of 1 GB. Do not add `GOMEMLIMIT` or a memory cap to Grafana: a heap limit made its GC run all the time, and a cap would kill it.

## Facts (`facts.py`)

`facts.py` is a host process (Python standard library only) that `board.py up` starts after the containers and `board.py down` stops. Every 30 s it reads GitHub with `gh` (read only: `issue list`, `issue view` and `api` GET calls, run in the `repo` folder of each project) and the usage-limit files, and serves them as Prometheus text format at `http://<gateway>:<AGK_FACTS_PORT>/metrics` (default port 9464). Prometheus scrapes it. It writes no comment, no label and no repo file.

- Port: `AGK_FACTS_PORT` (default 9464). `up` checks that the port is free before it starts the containers. When it is in use, `up` prints a message that names `AGK_FACTS_PORT`, exits non-zero and starts nothing.
- Listen address and why: Prometheus runs in a container and reaches the host only through the Docker bridge, never through `127.0.0.1` of the host (the name `host.docker.internal` leads to the `docker0` gateway, which can differ from the gateway of the compose network). So `up` first starts the containers, reads the IPv4 gateway of the network `agk-monitor_default` with `docker network inspect`, recreates Prometheus with that address as scrape target (`AGK_FACTS_HOST` in `compose.yaml`; the Prometheus data is in a volume) and starts `facts.py --host <gateway>`. Listen and scrape address are the same. `facts.py` is never started on `0.0.0.0`, `::`, an empty host or a public address, and `facts.py` itself refuses them (without `--host` it listens on `127.0.0.1`). When no address is found (no IPv4 gateway, empty or invalid output), `up` prints one line that names the cause, starts no `facts.py` and goes on: the boards then miss the facts metrics. When the target stays `down` although `facts.py` runs, a firewall of the host that blocks the Docker bridge to port `AGK_FACTS_PORT` is a possible cause (the kit changes no firewall). Check it at `http://127.0.0.1:9090/targets` or `/api/v1/targets`.
- Files in `<state dir>` (`$XDG_STATE_HOME/agent-graph-kit`, else `~/.local/state/agent-graph-kit`): `facts.pid` (the process id, written by `up`, removed by `down`) and `facts.log` (stderr of `facts.py`, appended: every read error and every skipped bad line). `down` stops `facts.py` and exits 0 also when it is not running.
- Errors: any error in a read (a failing `gh` call, a bad line, a missing file) is logged and never stops the server or `board.py`. After a failing `gh` call the previous metrics stay and `agk_facts_last_success_seconds` does not move.
- Projects: the entries of `<state dir>/monitor-projects.json` (`project` = `owner/name`, `repo` = folder where `gh` runs).

The four metrics (all gauges):

| Metric | Labels | Value |
|---|---|---|
| `agk_issue_info` | `agk_project`, `stage`, `issue`, `title`, `order` | 1 for each sub-issue (open and closed) of each open stage issue (label `stage`). `stage` and `issue` are issue numbers as text; `order` is the position 1, 2, ... in the GitHub sub-issues list |
| `agk_marker` | `agk_project`, `stage`, `issue`, `role`, `launch` | 1 for the current marker of each project; no series when the project has no open stage issue |
| `agk_usage_limit_percent` | `provider`, `window` | `used_percent` from `usage-limits-claude.jsonl` and `usage-limits-codex.jsonl` in the state dir. A line counts only when `v` is 1, `used_percent` is a number and `provider` and `window` are non-empty text; the last valid line per provider and window wins; a missing file gives no series |
| `agk_facts_last_success_seconds` | none | Unix time of the last full read (no series before the first one) |

The marker (which issue and role is in work now) comes from the launch receipts: the comments `## Launch: <role> (attempt <n>)` or `(continued, round <n>)` on the sub-issues of the open stage issue, and `## Launch: planner (attempt <n>)` on the stage issue. Only comments of the owner count. A receipt followed by `## Launch not started: <same role and attempt>` is skipped. The newest remaining receipt by `createdAt` gives `stage`, `issue`, `role` and `launch` (`<receipt role>-<n>`, for example `engineer-2`). When its issue is closed and no newer receipt exists, or the stage has no receipt yet, the marker is `issue=""`, `role="orchestrator"`, `launch=""` (work of the stage). The planner receipt gives `issue=""`, `role="planner"`. With more than one open stage issue, the newest receipt of all of them wins, and a stage with no receipt at all uses the highest stage number. Roles: `pm`, `engineer`, `qa-claude` (receipt role `qa`, line `Agent: qa-engineer`), `qa-codex` (line `Agent: qa-codex`), `planner`, `orchestrator`. The boards join OTel data with this marker (issue #312).

## The live board

`grafana/boards/live.json` is the board "Now" (uid `agk-live`, refresh 30 s, built-in panels only). The filters `project` and `stage` choose the stage; the time range (default 7 days) must cover the stage, because the charts add up the time range. The panels, from top to bottom:

- "Now": the role and issue of the subagent in work, its return number, active time, tokens, the time since its last step (the last minute with token use), and its last tool with target. When only the orchestrator works the role is "orchestrator". A tile "facts age" shows only when `agk_facts_last_success_seconds` is more than 2 minutes old. The panel reads Prometheus and Loki, so its data source is "-- Mixed --".
- "Tokens per issue, by role" and "Active time per issue, by role": stacked bars, one bar per issue of the stage in execution order (order, issue number and short title), one segment per role in the role colour. Issues not started yet are empty slots: the issue is on the x axis with no bar, also when no issue of the stage has data yet. The hover shows each segment and the total: the total is one more series "total" with no fill, on a hidden scale of its own, so it is not stacked on the segments. The dashed grey line for the typical issue is not drawn (the built-in bar chart cannot take a threshold line from a query); the guarded median is the hidden query B of each panel.
- "Timeline": one row for the orchestrator, then one row per issue in execution order. A block per launch in the role colour; the text of a return starts with "↺". The hover shows the issue (the row name), the role, the return number, the active minutes and the tokens of the launch, for example `↺ engineer · return 1 · 7 min active · 1.20 M tokens` (the sums in the time range of the board). The state is a number that holds these values (role code, return number up to 9, minutes up to 9999, tokens in units of 10 000); it is made text and a regex value mapping per role turns it into the hover text. A block shows the text only as far as it is wide. An issue with no launch yet has an empty row.
- "Plan usage limit": one bar per provider and window from `agk_usage_limit_percent`, or "no source".
- "Launches of this stage": the only table, newest first, one row per launch of a subagent on an issue (the orchestrator has no row; its tokens are in the bar charts). A teal dot before the role marks a running launch. The marker columns "tokens above typical" and "active time above typical" show "▲" (rose) when the launch is above the 75th percentile of the same role in the other stages of the project; they stay empty until three other stages have data. The two marker columns have a fixed width of 60 px and a wrapped header; the other columns are sized by Grafana. (Grafana draws a column at least 50 px wide; a smaller set width pushes the last column out of the panel.) The p75 is taken over the launches of the other stages (one value per stage, issue and launch).
- "Telemetry" (collapsed row): eight time series: token rate by kind, active time per hour, API requests per minute, API latency p50 and p95, API errors, tool calls by tool with the p95 tool duration, lines of code added and removed, commits and pull requests. The panels for API requests, latency, errors and tool calls read the Loki events `claude_code.api_request`, `claude_code.api_error`, `claude_code.tool_result` and `codex.api_request`; the last three counters come from Claude Code (`claude_code_lines_of_code_count_total`, `claude_code_commit_count_total`, `claude_code_pull_request_count_total`).

## The history board

`grafana/boards/history.json` is the board "Stages" (uid `agk-history`, built-in panels only, no auto refresh). It compares the stages and issues of a project and drills down from a stage to an issue, a launch and its steps. Filters: `project` and `stage`; `issue` and `launch` are set by the drill-down (they are also lists you can pick from). The lists hold the stages, issues and launches of the last 365 days. The panels, from top to bottom:

1. "Tokens per stage, by role": stacked bars, one bar per stage in number order, tokens in millions, one segment per role in the role colour; the hover shows each segment and the total.
2. "Active time per stage, by role": the same with the active time.
3. "Token kinds per stage": the same per token kind (cache read, cache creation, output, input) in the kind colours.
4. "Selected stage: tokens per issue, by role": the chart "Tokens per issue, by role" of the live board for the stage in the filter, also for a closed stage.
5. "Most expensive issues of all stages": horizontal stacked bars, the ten issues with the most tokens of all stages, largest on top, labelled `stage · #issue`, one segment per role.
6. "Steps of the launch": one bar per tool call of the selected launch at its time, its height the duration (log scale), rose above 2 minutes; the hover gives the tool and its target (file path or command). A teal line on the right axis is the context size of each API request (input + cache read + cache creation tokens).
7. "Launches of the issue": a table, one row per launch of a subagent on the selected issue, in start order: issue, role, tokens, active time, return, model, start.
8. "Steps of the launch (table)": the tool calls and API requests of the selected launch in time order: step, tool (an API request shows "API request" and the model as target), target, duration (rose above 2 minutes), tokens of the API request, time.
9. "Kit document reads per role": one bar per role, the number of `Read` calls on a kit document (a file under `docs/`, `.agents/skills/` or `plugin/skills/`, or `AGENTS.md` or `CLAUDE.md`); the hover lists the documents and their read counts.

Drill-down: a click on a bar of panels 1 to 3 opens the menu with the link "Select this stage" (sets `stage`). A click on an issue bar of panel 4 or 5 opens "Launches of this issue" (sets `issue`; panel 5 also sets `stage`). A click on a row of panel 7 opens "Steps of this launch": it sets `launch`, and panels 6 and 8 then show the first to last minute of the launch in `agk:active_seconds:1m`. Each link keeps `project`.

- Time ranges: panels 1 to 5 and 7 always show the last 365 days, and panel 9 the last 30 days (Loki refuses a query longer than 721 hours), so they keep their range during a drill-down. Panels 6 and 8 have their own range, the window of the selected launch: from one minute before its first sample in `agk:active_seconds:1m` to its last sample. The hidden variables `launch_ago` and `launch_span` (seconds) compute it from the stored sample times each time the board loads, and the two panels use them as their relative time and time shift. So the window does not depend on the board range and stays the same after a reload at any later time. Without a launch the two panels show the last 24 hours and stay empty.
- Each step is its own data point: panels 6 and 8 run Loki log queries (no metric aggregation), so two calls of the same tool and target close together stay two bars and two rows, and each API request is one point of the context size line. Panel 6 splits the tool calls into one series per tool and target, and its hover names the one call under the mouse.
- Panels 6 and 8 read the Loki events `claude_code.tool_result` and `claude_code.api_request` and keep the events of the role of the launch: the launch name (`pm-1`, `engineer-2`, `qa-1`) gives the role, and the role of an event comes from its attributes `query_source` and `agent_name` as in the recording rules. Tool targets need `OTEL_LOG_TOOL_DETAILS=1` (see "Export settings"). For a `qa-codex` launch the two panels stay empty: Codex sends other events (Codex steps: issue #322).
- Typical stage: the dashed grey line is not drawn (the built-in bar chart cannot take a threshold line from a query). Panels 1 and 2 hold the median of the stage totals of the other stages of the project as the hidden query B, which gives no value until three such stages have data.
