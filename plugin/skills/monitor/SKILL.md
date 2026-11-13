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

  Prometheus also scrapes the host process `facts.py` at `host.docker.internal:9464` (`AGK_FACTS_PORT`, built in issue #310).
- Nothing starts on boot and nothing restarts by itself (`restart: "no"` on every service). `down` stops the stack; the data stays in the Docker volumes `agk-monitor_prometheus-data` and `agk-monitor_loki-data`.
- What the stack holds: metrics in Prometheus and logs in Loki, each kept for 365 days. Claude Code and Codex send OTLP to the Collector. The Collector keeps only data of the kit projects: it drops all data whose resource attribute `agk.project` is missing or is not in the project list. The list is `$XDG_STATE_HOME/agent-graph-kit/monitor-projects.json` (else under `~/.local/state`), mode 0600, a list of `{"project": "owner/name", "repo": "<path of the project repo>"}`. When the file is missing, `up` writes it once with the current project (`owner/name` from `gh repo view`, the current folder as repo); add other projects by hand and run `up` again. As a second guard behind the export settings, the logs pipeline deletes the attributes `prompt`, `user_prompt`, `response`, `response_text`, `output_text`, `assistant_message` and `last_assistant_message`.
- Grafana: `http://127.0.0.1:3000`, user `admin`, password in `<state dir>/grafana-admin` (`$XDG_STATE_HOME/agent-graph-kit/grafana-admin`, else under `~/.local/state`), mode 0600. `up` writes a random value on the first start and reuses it after. `board.py` prints the path of the file, never the value. Anonymous access, sign-up, update checks, usage reports and the news feed are off. Two data sources are provisioned: `prometheus` (uid `agk-prometheus`) and `loki` (uid `agk-loki`). No community plugin is installed. The boards come from `grafana/boards/` (none yet; see issues #313 and #314).
- First start: Docker downloads the four images, each pinned to an exact version (tags and push dates are in `compose.yaml`).
- What the containers see: their own config files (read only) and the password file. No token or credential: no `gh`, Claude or Codex folder or variable.
- Failures: without `docker` on PATH, or when `docker info` fails (daemon not running, no access), `up` names Docker, exits 2 and starts nothing. Without a project list and without `gh`, `up` exits 2 and starts nothing. When `docker compose up` fails (for example a port is in use), `up` names the ports, stops what it started and exits 1.
- RAM: the four containers together use about 240 MiB right after `up` with no load, and about 420 MiB after a few minutes of Loki and Prometheus data (measured with `docker stats --no-stream`), well below the budget of 1 GB. Do not add `GOMEMLIMIT` or a memory cap to Grafana: a heap limit made its GC run all the time, and a cap would kill it.
