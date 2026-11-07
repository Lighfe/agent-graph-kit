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

## Store

`store.py` copies the monitoring files into one SQLite file, `monitor.sqlite`, that Grafana reads. Run it on the host (not in a container), from the project root:

```bash
uv run --script "${CLAUDE_SKILL_DIR}/store.py" load          # load now, then every 30 s; Ctrl-C or SIGTERM ends it (exit 0)
uv run --script "${CLAUDE_SKILL_DIR}/store.py" load --once   # load once; exit 1 when the load failed
uv run --script "${CLAUDE_SKILL_DIR}/store.py" rebuild       # delete the db file and load everything again
```

- Db file: `$MONITOR_DB_FILE`, else `$XDG_STATE_HOME/agent-graph-kit/monitor.sqlite`, else `~/.local/state/agent-graph-kit/monitor.sqlite`, mode 0600, default rollback journal (not WAL). The db is a derived copy: `rebuild` gives the same rows as the loads before it (the `loads` table excepted).
- Log: `monitor-load.log` next to the db file, mode 0600: one line per load (`ok` or `failed` and the message), and the traceback of a load error.
- Projects: `$XDG_STATE_HOME/agent-graph-kit/monitor-projects.json` (else under `~/.local/state`), mode 0600, a list of `{"project": "owner/name", "repo": "<path of the project repo>"}`. When the file is missing, the loader writes it once with the current project (`owner/name` from `gh repo view`, the current folder as repo). Add other projects by hand.
- Each load: first `steps.py collect --project <project>` in the repo folder of each project. At most every 5 minutes, the stage read: for each project, the open issues with the label `stage` and their sub-issues (number, title, state), with `gh` reads only, and `cases.py collect --project <p> --repo-slug <p> --stage <n>` in the repo folder for each open stage. Between stage reads the `issues` rows of the last read stay. Then, in one transaction, the new full lines of the input files: the run record, the step rows, the hand-entered limits (`run-record-limits.jsonl`), the retry cases and tags, and the modification times of the Codex stream files (`$CODEX_RUNS_DIR`, else `codex-runs/` in the state folder). A load on unchanged files reads only file sizes and times.
- Incremental: the run record, the step file and the limits file are read from the byte offset of the last load; a later line with an id already loaded replaces that row (the last line per `id` counts). A last line without a newline is skipped and loaded once it is complete. A file that got shorter or was replaced is read again from the start; a missing file empties its table. The case file is rewritten as a whole by `cases.py`, so it and the tag file are read again as a whole when either changes. Only their full lines are read, with the readers of `data.py`: a last line without a newline is skipped until it is complete, also when it is valid JSON.
- Errors: a failing collector or stage read of one project is named in the load's message and does not stop the other projects; the load is then `failed`. A load error (for example an input file that cannot be read) rolls the load back, writes a `failed` row and the log line, and changes no input file. Nothing stops the loop (O2).
- Writes: the loader writes only the db file, its log and (once) `monitor-projects.json`; the collectors write their own files as before. Nothing is written to GitHub.

Tables (times as ISO text, and as Unix seconds in the `_s` columns):

- `launches`: one row per run-record line (last line per `id`): `id`, `project`, `stage`, `issue`, `role`, `provider`, `model`, `effort`, the four token kinds, `start_time`, `end_time`, `start_s`, `end_s`, `seconds`, `retry`, `estimate` (1 for the orchestrator estimate lines), `source`, `escalations` (issue lines), `launch` (the step rows' launch, from `launch_of` of `data.py`), `weighted`, `weighted_is_estimate`
- `steps`: one row per step row: `id`, `project`, `stage`, `issue`, `role`, `provider` (`codex` for the Codex QA role, else `claude`), `launch`, `seq`, `time`, `time_s`, `duration_s`, `model`, the four token kinds, `context_tokens`, `tool` and `target` (JSON text when a list), `result_chars`, `is_error`, `kit_doc`, `weighted`, `weighted_is_estimate`
- `issues`: the sub-issues of the open stage issues: `project`, `stage`, `issue`, `title`, `state`
- `cases`: one row per retry case: `id`, `project`, `stage`, `issue`, `round`, `marker`, `role`, `escalation` (1 when the marker ends with `NEEDS OWNER`), `tag` and `note` (the last line per `case_id` of `retry-tags.jsonl`), `criteria`, `failed_lines`, `next_markers` (JSON text), `commit_range`, `files_changed`, `lines_added`, `lines_removed`, `body_edited`, `tokens` (text), `tokens_claude`, `tokens_codex`, `seconds`, `comment_url`
- `limits`: the hand-entered plan limits of `run_record.py limit`: `line` (byte offset in the file), `project`, `stage`, `time`, `time_s`, `point`, `percent`, `plan`, `entered_by_hand` (always 1)
- `loads`: one row per load: `id`, `time`, `time_s`, `status` (`ok` or `failed`), `message`, `stage_read` (1 when the load ran the stage read)
- `files`: what the loader has read of each input file (`kind`, `path`, `inode`, `size`, `mtime_ns`, `mtime_s`, `offset`); a `codex-stream:<launch>` row holds the modification time of a Codex stream file
- View `active_launches`: the active launches, one row per project, launch and provider: `role`, `model`, `issue`, `stage`, `start_time`, `live_time`, `run_time_s`, `idle_s`, `steps`, the four token kinds so far, `weighted`, `weighted_is_estimate`, and the last step (`last_seq`, `last_tool`, `last_target`)

Active rule (only in the view, computed at the time of the query, not of the load): a Claude launch is active while its newest step time is at most 5 minutes old; a Codex QA attempt is active while the modification time of its stream file (stored at load) is at most 5 minutes old, since its rows carry only the attempt start.

Weighted tokens: `weighted` of `data.py` with the weights of each project (`$RUN_WEIGHTS_FILE`, else `docs/run-weights.json` of the project repo, else the skill copy) and the Codex rule of the notebook. They are estimates from price ratios, not measured plan use (`weighted_is_estimate` 1); a line with no provider has none. No column adds Claude and Codex values together.

## Grafana board (optional)

`board.py` starts an optional Grafana stack that shows `monitor.sqlite` as boards. Docker is needed for this part only; the rest of the skill runs without it. `/agk:setup` does not install Docker. Run it from any folder:

```bash
uv run --script "${CLAUDE_SKILL_DIR}/board.py" up     # check Docker, start Grafana, then run the loader (store.py load) in the foreground; Ctrl-C stops the loader and the stack
uv run --script "${CLAUDE_SKILL_DIR}/board.py" down   # stop the stack; exit 0 also when it is not running
```

- URL: `http://127.0.0.1:3000` (bound to localhost only; `AGK_GRAFANA_PORT` sets another port). The stub board is "agk monitor (stub)" in the folder `agent-graph-kit`: the time of the last load and the last ten loads.
- Login: user `admin`, password in `<state dir>/grafana-admin` (`$XDG_STATE_HOME/agent-graph-kit/grafana-admin`, else under `~/.local/state`), mode 0600. `up` writes a random value on the first start and reuses it after. `board.py` prints the path of the file, never the value. Anonymous access and sign-up are off.
- First start: Docker downloads the image `grafana/grafana:13.2.4` (about 200 MB compressed), and Grafana downloads the SQLite data source plugin `frser-sqlite-datasource` 4.0.6 into the Docker volume `agk-monitor_grafana-plugins`. After that the stack uses no network: update checks, usage reports and the news feed are off. Grafana's own settings db starts fresh on each `up`; the data source and the boards come from the files in `grafana/`.
- What the container sees: the folder of the db file (read only, so `store.py rebuild` and the journal file work while Grafana runs), `grafana/provisioning/` and `grafana/boards/` (read only) and the password file. No token or credential: no `gh`, Claude or Codex folder or variable. `up` refuses a db folder that is the home folder or holds `~/.claude`, `~/.codex`, `~/.config/gh` or `~/.ssh`; set `MONITOR_DB_FILE` to a file in a folder of its own. Grafana runs with your uid and gid, so it can read the 0600 db file.
- Failures: without `docker` on PATH, or when `docker info` fails (daemon not running, no access), `up` names Docker, exits 2 and starts nothing. When `docker compose up` fails (for example the port is in use), `up` exits 1 and does not start the loader.
- RAM: Grafana uses about 250 MB, the loader about 30 MB.
- Boards: each JSON file in `grafana/boards/` is a board (data source uid `agk-monitor`). Grafana reads changes of the folder every 30 s.
