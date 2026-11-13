# Visual monitoring Implementation Plan

> For agentic workers: each task below becomes one GitHub issue in `docs/task-template.md` format and runs through the loop of `docs/process.md`. Do not use subagent-driven-development or executing-plans (`AGENTS.md`).

**Goal:** correct the monitoring data, then show it in an optional, light Grafana stack with a live board and a history board.

**Architecture:** the existing files (run record, step rows, retry cases, tags, Codex streams) stay the source. A host-side loader copies them into one SQLite file every 30 s. One pinned Grafana container with a SQLite data source reads that file read-only and shows two provisioned boards.

**Tech stack:** Python 3.11 standard library (`sqlite3`), `uv run --script`, Docker Compose, Grafana with a SQLite data source plugin (pinned versions), pytest.

**Spec:** `docs/specs/2026-11-06-visual-monitoring.md`

## Global constraints

- Principles O1 to O4 and M1 to M3 of the spec hold for every task. In short: nothing in the loop reads the store; a monitoring failure never changes a result; data stays local, files mode 0600; Grafana on `127.0.0.1` with a login; no credential in a container; at most 400 MB RAM for the stack
- Hand-written plugin skill: all monitor files live in `plugin/skills/monitor/` (in `HAND_SKILLS` of `scripts/build_plugin.py`). `uv run scripts/build_plugin.py` must leave no diff
- Synthetic test data only (`tests/fakes/monitor/`); no network in tests
- Test command: `uv run --with pytest pytest`. Engineers run the full suite under a memory cap as `docs/team/software-engineer.md` says
- No plugin version bump in a task (`AGENTS.md`, "Kit-repo release steps")
- Images and plugins pinned to exact versions at least two weeks old

## Review focus

1. A half-written last line in any input file while a launch writes: the loader skips it and loads it on the next run, no duplicate row (Task 11)
2. The loader on a state with a missing file, an empty file or a deleted `monitor.sqlite`: it rebuilds without error (Task 11)
3. A schema change that breaks a board query: caught by the query test, not found in Grafana (Tasks 13, 14)
4. The stack started without Docker or with the port taken: a clear message and exit, nothing else touched (Task 12)
5. A Codex QA attempt that is still running: shown as active by the stream file time, not by its start (Task 11)

---

## Part A: correct the data

### Task 1: Codex token meaning

**Files:** `docs/specs/2026-10-21-run-record.md`, `plugin/skills/monitor/data.py` (`weighted`), `scripts/run_report.py`, `tests/test_monitor_data.py`, `tests/test_run_report.py`

- Find out, with a source (Codex docs, Codex source code, or a measured `codex exec --json` stream; name the version), whether `input_tokens` includes `cached_input_tokens`. Write the answer and the source into the run-record spec
- If it includes it: the weighted Codex value is `(input - cached) * w.input + cached * w.cache_read + output * w.output`. Test `test_codex_weighted_excludes_cached_from_input`: line input 100, cached 80, output 0 with the weights of `docs/run-weights.json` gives 28. If not: a test pins the current formula and the spec says why
- **Produces:** `weighted(line, weights) -> float | None` in `data.py` with the rule above; Task 11 uses it

### Task 2: Writer: `retry` on Codex QA lines

**Files:** `plugin/skills/run-record/run_record.py` (`codex_lines`), `tests/test_run_record.py`

- Test `test_codex_lines_count_retry`: three Codex usage lines and three `## Launch: qa` receipts on one issue give three `qa-codex` lines with `retry` 0, 1, 2

### Task 3: Writer: real `start` on Codex QA lines

**Files:** `run_record.py` (`codex_lines`), `tests/test_run_record.py`. Blocked by Task 2 (same function)

- Test `test_codex_line_start_is_receipt_time`: a QA launch receipt at T0 and a Codex usage line at T1 > T0 give one `qa-codex` line with `start` T0 and `end` T1

### Task 4: Writer: no stage issue line; defined `provider` and `source` for issue lines

**Files:** `run_record.py` (`issue_lines`), `docs/specs/2026-10-21-run-record.md`, `tests/test_run_record.py`

- Test `test_issue_lines_skip_stage_issue`: an issue file with the stage issue (label `stage`) and two sub-issues gives issue lines for the two sub-issues only
- The spec field table names the `provider` and `source` values of an issue line; test `test_issue_line_provider_and_source` checks them

### Task 5: Report: clear estimate labels and one weighted total per stage

**Files:** `scripts/run_report.py`, `tests/test_run_report.py`. Blocked by Task 1

- In a report of a one-stage record, the estimate row of each table names the orchestrator and the model; the issue table has no bare "none" row; the weighted totals table says the estimate column is the orchestrator estimate line
- Test `test_report_weighted_total_per_stage`: a record with two stages gives two weighted totals

### Task 6: Spec: `project` row in the run-record field table

**Files:** `docs/specs/2026-10-21-run-record.md`

- The field table has a row whose first cell is `` `project` ``; the `id` row no longer holds the project text

### Task 7: Stage-end write also writes the Codex QA step rows (#272)

Existing issue #272; its body holds the criteria. Blocked by Task 3 (same Codex part of `run_record.py`)

### Task 8: Retry case collector keeps other projects and stages (#273)

Existing issue #273; its body holds the criteria

### Task 9: Bump skill line matches the release steps

**Files:** `.agents/skills/bump-plugin-version/SKILL.md`

- The commit step names both exceptions of `AGENTS.md` "Kit-repo release steps": no commit when the script prints that no bump is needed; no commit (reset the files) when the script or the tests fail

## Part E: usage limit source

### Task 10: Find a local source for the plan usage limit in percent

**Files:** `docs/research/usage-limit-source.md`

- For Claude Code and for Codex: is the usage limit in percent available locally (status-line input, the `--json` stream, a local file)? Exact field, the version checked, and how a value could reach `monitor.sqlite`
- Ends with one proposed way per tool, or "no source". A way that changes the owner's user settings is named as the owner's decision, in words
- No code change; no settings change

## Parts B to D: the store, the stack and the boards

### Task 11: Loader: files to `monitor.sqlite`

**Files:** create `plugin/skills/monitor/store.py`, `tests/test_monitor_store.py`, fixtures in `tests/fakes/monitor/`; modify `plugin/skills/monitor/SKILL.md`. Blocked by Task 1

**Interfaces (produces):**
- `store_path() -> Path`: `$MONITOR_DB_FILE`, else `<state dir>/agent-graph-kit/monitor.sqlite`
- `load(db: Path, *, now: datetime) -> dict` loads new lines of the run record, step rows, retry cases, tags and `run-record-limits.jsonl`, and the stream file times; returns counts per table
- CLI: `store.py load [--once]` (default: loop every 30 s until stopped), `store.py rebuild`
- Tables (names fixed, columns left to the builder, documented in `SKILL.md`): `launches`, `steps`, `issues`, `cases`, `limits`, `loads`. View `active_launches` uses the liveness rule of the spec (newest step, or stream file mtime for Codex, at most 5 minutes old). Weighted columns use `data.weighted` and carry an `estimate` flag
- Project config: `<state dir>/agent-graph-kit/monitor-projects.json`, list of `{"project": "owner/name", "repo": "<path>"}`; created with the current project when missing

**Behavior and tests:**
- `test_load_is_incremental`: a second `load` on unchanged files adds no rows
- `test_half_written_line_loaded_next_run`: a last line without newline is skipped, then loaded once complete
- `test_rebuild_matches_incremental`: `rebuild` after a deleted db gives the same row counts
- `test_missing_and_empty_inputs`: missing or empty files give empty tables, no error
- `test_codex_attempt_active_by_mtime`: a stream file with a recent mtime and an old start is active
- `test_db_mode_0600`
- `test_load_failure_recorded`: a load error is a row in `loads` with time and message; the exit code of `--once` is not 0
- Each loop runs `steps.py collect` per configured project; every 5 minutes it runs `cases.py collect` for the open stage issue of each project and reads sub-issue titles with `gh` (read only). Tests stub the commands; no network
- `SKILL.md`: the loader commands, the tables, the config file

### Task 12: Grafana stack: one command up, one down

**Files:** create `plugin/skills/monitor/compose.yaml`, `plugin/skills/monitor/grafana/provisioning/` (data source, board provider), `plugin/skills/monitor/board.py`, `tests/test_monitor_board.py`; modify `SKILL.md`, `README.md` (optional monitoring section). Blocked by Task 11

**Interfaces (produces):** `board.py up` (checks Docker, creates the admin password file with mode 0600 if missing, `docker compose up -d`, then runs the loader loop in the foreground; Ctrl-C stops the loader and the stack), `board.py down`. Board JSON files go to `plugin/skills/monitor/grafana/boards/`

**Behavior and tests:**
- `compose.yaml`: one Grafana service, pinned image, pinned SQLite data source plugin, port `127.0.0.1:<port>`, `restart: "no"`, the db mounted read-only, no credential env from the host except the admin password file. Test `test_compose_binds_localhost_only` and `test_compose_pins_versions` parse the file
- `test_up_without_docker_exits_with_message`: no `docker` on PATH gives a message and a non-zero exit, nothing started
- `test_password_file_created_0600`
- Check on the owner's machine, recorded in `## Engineer: DONE`: start the stack, open both board stubs, run 10 minutes during agent work; peak RAM and CPU of the container and the loader (for example from `docker stats` and `/usr/bin/time -v`). Budget: at most 400 MB together
- `SKILL.md` and `README.md`: requirements (Docker), the two commands, the URL, the password file, what downloads on first start

### Task 13: Live board

**Files:** `plugin/skills/monitor/grafana/boards/live.json`, `tests/test_monitor_boards.py`. Blocked by Task 12

- Panels as in the spec, Part D "Live board": active launches (role, model, issue and title, stage, start, run time, tokens raw and weighted estimate, last tool and target, last step time), the current stage timeline with retries, Codex QA attempts, the hand-entered limits from `limits` (labelled "entered by hand"), a "no source" usage-limit panel, last load time and last failed load. Filters: project, stage. Refresh 30 s
- `test_board_queries_run_on_fixture`: every SQL query in the board files runs without error on a db built by `store.rebuild` from the fixtures, and each live panel query returns at least one row
- Engineer DONE: a screenshot path (local only, not committed) or the Grafana API answer showing the board loaded

### Task 14: History board

**Files:** `plugin/skills/monitor/grafana/boards/history.json`, `tests/test_monitor_boards.py`. Blocked by Task 12 and Task 5

- Panels as in the spec, Part D "History board": per stage weighted tokens per provider (estimate), raw kinds, time, launches, retries, escalations; breakdowns by issue, role, model; drill-down by data links stage → issue → launch → steps; kit document reads per role. Filters: project, stage
- The same query test as Task 13 covers this file

### Task 15: Usage limit on the live board

**Files:** `store.py`, `grafana/boards/live.json`, `tests/test_monitor_store.py`, `tests/test_monitor_boards.py`. Blocked by Task 10 and Task 13

- When `docs/research/usage-limit-source.md` names a local source that needs no change to the owner's user settings: the loader reads it into `limits` with `source` `live`, and the live board shows the newest percent per plan and its time. Test on a synthetic source file
- When the note names only a way that changes the owner's settings: the engineer stops with `## Engineer: BLOCKED` and names the owner's decision in words; nothing changes in the settings
- When the note found no source: the "no source" panel of Task 13 stays; the task changes only `SKILL.md` to say so

### Task 16: Living spec

**Files:** `docs/specs/agent-graph-kit.md`. Blocked by Tasks 12 to 14

- A short section on the optional monitoring stack (what it reads, the two commands, O1/O2/M1 to M3), next to "Run record"

## Order

1 to 9 (Part A), 10, then 11, 12, 13, 14, 15, 16. Blockers: 5 after 1; 3 after 2; 7 after 3; 11 after 1; 12 after 11; 13 after 12; 14 after 12 and 5; 15 after 10 and 13; 16 after 13 and 14.
