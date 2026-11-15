# OpenTelemetry monitoring boards Implementation Plan

> For agentic workers: each task below becomes one GitHub issue in `docs/task-template.md` format and runs through the loop of `docs/process.md`. Do not use subagent-driven-development or executing-plans (`AGENTS.md`).

**Goal:** Claude Code and Codex export OTel data into a local stack (OTel Collector, Prometheus, Loki, Grafana). Two Grafana boards show charts per issue and role, with tables only for drill-down.

**Architecture:** Claude Code and Codex send OTLP to the Collector. The Collector keeps only data with a kit project tag, sends metrics to Prometheus and logs (events) to Loki. A host process (`facts.py`) reads GitHub (read only) and the usage-limit files. It serves the stage's issues, the attribution marker and the usage limits as Prometheus metrics on `127.0.0.1`. Prometheus recording rules join the OTel counters with the marker once per minute, so every token and second gets project, stage, issue and role. Grafana reads Prometheus and Loki with built-in panels only.

**Tech stack:** Docker Compose; pinned images of the OTel Collector (contrib), Prometheus, Loki, Grafana; Python 3.11 standard library for `facts.py` and `board.py`; pytest.

**Spec:** `docs/specs/2026-11-13-otel-monitoring-boards.md`

## Global constraints

- O1 to O4 and M1 to M7 of the spec hold for every task. In short: nothing in the loop reads monitoring data; a monitoring failure never changes a result; data stays local; all ports on `127.0.0.1`; Grafana needs a login; no credential in a container; less than 1 GB RAM for the stack; no prompt text exported; only data with a kit project tag is stored; built-in Grafana panels only; retention at least one year
- Forward only: no back-fill of old stages, no fallback to the SQLite store
- All monitor files live in `plugin/skills/monitor/` (in `HAND_SKILLS` of `scripts/build_plugin.py`). `uv run scripts/build_plugin.py` must leave no diff
- Images pinned to exact versions at least two weeks old
- Synthetic test data only (`tests/fakes/monitor/`); no network and no Docker in pytest tests
- Test command: `uv run --with pytest pytest`. Engineers run the full suite as `docs/team/software-engineer.md` says
- No plugin version bump in a task (`AGENTS.md`, "Kit-repo release steps")
- The run record (`run_record.py`), `steps.py`, `cases.py`, `data.py` and the notebook stay unchanged

## Shared names

These names are fixed for all tasks:

- Project tag: OTel resource attribute `agk.project` with the value `owner/name`. In Prometheus the label `agk_project`, in Loki the stream label `agk_project`
- Roles (label `role`): `orchestrator`, `pm`, `engineer`, `qa-claude`, `qa-codex`, `planner`, `other`. Mapping: Claude Code `query_source="main"` → `orchestrator`; `agent.name` `pm` → `pm`; `software-engineer` and `frontend-engineer` → `engineer`; `qa-engineer` → `qa-claude`; `planner` → `planner`; any other subagent → `other`; Codex data → `qa-codex`
- Token kinds (label `kind`): `cache_read`, `cache_creation`, `output`, `input`. Codex: `input` = input minus cached input; cached input → `cache_read`
- Metrics served by `facts.py` (Task 2):
  - `agk_issue_info{agk_project, stage, issue, title, order}` = 1 for each sub-issue of each open stage issue; `order` is the sub-issue position (1, 2, …)
  - `agk_marker{agk_project, stage, issue, role, launch}` = 1 for the current marker of each project, no series when there is none. `issue=""` for stage-level work. `launch` is `<role>-<attempt>` from the newest receipt, for example `engineer-2`
  - `agk_usage_limit_percent{provider, window}` from the usage-limit files
  - `agk_facts_last_success_seconds` = Unix time of the last full read
- Recording rules (Task 4), evaluated every 60 s:
  - `agk:tokens:1m{agk_project, stage, issue, role, launch, kind, model}`: tokens of the last minute
  - `agk:active_seconds:1m{agk_project, stage, issue, role, launch}`: active seconds of the last minute, after the priority rule
- Colours: the table "Colours" of the spec, exact hex values

## Review focus

1. GitHub not reachable or `gh` not logged in while the stack runs: `facts.py` keeps the last marker and issue list, logs the error, sets no new `agk_facts_last_success_seconds`; the live board shows the age of the facts (Task 2, Task 5)
2. A session of a project without the tag, or of a non-kit project: nothing of it reaches Prometheus or Loki (Task 1 config test, Task 3 live check)
3. The orchestrator and a subagent active in the same minute: the minute counts once, to the subagent (Task 4)
4. Usage before the first launch of a stage and after its last issue is closed: shown as stage-level work with `issue=""`, never dropped (Task 2, Task 4)
5. The stack started without Docker, with a port in use, or with the facts port in use: a clear message and exit, nothing else touched (Task 1)

---

### Task 1: The stack: Collector, Prometheus, Loki, Grafana in one compose file

**Files:**
- Modify: `plugin/skills/monitor/compose.yaml`, `plugin/skills/monitor/board.py`, `plugin/skills/monitor/SKILL.md`
- Create: `plugin/skills/monitor/otel/collector.yaml`, `plugin/skills/monitor/otel/prometheus.yaml`, `plugin/skills/monitor/otel/loki.yaml`, `plugin/skills/monitor/grafana/provisioning/datasources/monitor.yaml` (rewrite: Prometheus and Loki)
- Delete: `plugin/skills/monitor/store.py`, `plugin/skills/monitor/grafana/boards/live.json`, `history.json`, `monitor-stub.json`, `tests/test_monitor_store.py`, `tests/test_monitor_boards.py`
- Test: `tests/test_monitor_stack.py`, `tests/test_monitor_board.py` (update)

**Interfaces:**
- Produces: `board.py up` starts the four containers and then `facts.py` (Task 2; until Task 2 lands, `up` starts only the containers); `board.py down` stops both. The Collector receives OTLP gRPC on `127.0.0.1:4317` and OTLP HTTP on `127.0.0.1:4318`. Prometheus on `127.0.0.1:9090`, Loki on `127.0.0.1:3100`, Grafana on `127.0.0.1:3000` (each port overridable by an `AGK_*_PORT` variable). Prometheus scrapes `facts.py` at `host.docker.internal:<AGK_FACTS_PORT, default 9464>`. Prometheus loads rule files from `plugin/skills/monitor/otel/rules/` (empty until Task 4)
- The project list for the filter: `<state dir>/agent-graph-kit/monitor-projects.json` (the existing file), read by `board.py up` and passed to the Collector

Steps:

- [ ] Write the failing tests in `tests/test_monitor_stack.py`:
  - `test_all_ports_on_localhost`: every `ports` entry in `compose.yaml` starts with `127.0.0.1:`
  - `test_images_pinned`: every `image` has an exact version tag (no `latest`, no bare major)
  - `test_restart_no`: every service has `restart: "no"`
  - `test_collector_drops_untagged`: `collector.yaml` has a filter processor in both the metrics and the logs pipeline that drops data whose `agk.project` is missing or not in the project list
  - `test_collector_no_prompt_attributes`: the logs pipeline deletes the attributes `prompt` and the Codex prompt and response fields (M4), as a second guard behind the export settings
  - `test_retention_one_year`: Prometheus `--storage.tsdb.retention.time` and Loki `retention_period` are at least `365d`
  - `test_no_credentials_in_compose`: no `GH_TOKEN`, `GITHUB_TOKEN`, `ANTHROPIC_*` or `OPENAI_*` in `compose.yaml`
- [ ] Run them: `uv run --with pytest --with pyyaml pytest tests/test_monitor_stack.py -v`. Expected: FAIL
- [ ] Write the compose file and the three configs. Grafana keeps the M1 settings of today (login, password file, analytics off) and loads no community plugin (M7). Remove the SQLite data source plugin. Keep `GF_PLUGINS_DISABLE_PLUGINS` but keep `prometheus` and `loki` on
- [ ] Update `board.py`: same commands and messages as today for Docker missing and port in use; no loader thread; the store code goes
- [ ] Delete the SQLite store, the Stage 20 boards and their tests. Update `SKILL.md`: commands, ports, what the stack holds
- [ ] Run the full suite. Expected: PASS
- [ ] Check on the owner's machine: `board.py up`, then `docker stats --no-stream` with no load. Record the RAM of each container in `## Engineer: DONE`. Expected: below 1 GB together
- [ ] Commit

### Task 2: `facts.py`: issues, marker and usage limits as metrics

**Files:**
- Create: `plugin/skills/monitor/facts.py`, `tests/test_monitor_facts.py`, `tests/fakes/monitor/facts/` (fake `gh` JSON answers and usage-limit files)
- Modify: `plugin/skills/monitor/board.py` (start and stop `facts.py`), `plugin/skills/monitor/SKILL.md`

**Interfaces:**
- Consumes: `monitor-projects.json` (project and repo path), `gh` (read only), `<state dir>/agent-graph-kit/usage-limits-<claude|codex>.jsonl` (format as read by `store.py` today: `v` 1, `provider`, `window`, `used_percent`, `time`)
- Produces: the metrics of "Shared names" on `127.0.0.1:<AGK_FACTS_PORT>/metrics`, Prometheus text format
- `read_facts(projects, gh, now) -> Facts` (pure apart from `gh`), `render(facts) -> str` (Prometheus text), `marker_of(receipts, issues) -> Marker | None`

Marker rule: the receipts are the `## Launch: <role> (attempt <n>)` and `## Launch: <role> (continued, round <n>)` comments on the sub-issues of the open stage issue (the pattern of `.claude/hooks/issue_state.py`), plus `## Launch: planner` on the stage issue. The newest receipt by time gives issue, role and launch. When the newest receipt's issue is closed and no newer receipt exists, the marker is stage-level (`issue=""`, `role="orchestrator"`). Reads every 30 s.

Steps:

- [ ] Write the failing tests:
  - `test_marker_is_newest_receipt`: receipts PM #10 at T1, engineer #10 at T2 give `issue="10", role="engineer", launch="engineer-1"`
  - `test_marker_return_attempt`: a second engineer receipt (attempt 2) on #10 gives `launch="engineer-2"`
  - `test_marker_stage_level_after_close`: newest receipt on #10, #10 closed, no newer receipt → `issue=""`, `role="orchestrator"`
  - `test_marker_planner_on_stage_issue`: a `## Launch: planner` receipt on the stage issue gives `issue=""`, `role="planner"`
  - `test_issue_info_order`: three sub-issues give `order` 1, 2, 3 in sub-issue order, with titles
  - `test_gh_failure_keeps_last_facts`: a failing `gh` call keeps the previous facts and does not move `agk_facts_last_success_seconds`
  - `test_usage_limits_bad_lines_skipped`: lines with `v` ≠ 1 or a non-number percent are skipped
  - `test_render_escapes_labels`: a title with `"` and `\` gives valid Prometheus text
  - `test_listens_on_localhost_only`: the server binds `127.0.0.1`
- [ ] Run them. Expected: FAIL
- [ ] Implement `facts.py` (standard library `http.server`, a 30 s read loop in a thread). `gh` runs on the host with the owner's login; nothing goes into a container (M3). Errors go to its log and never stop `board.py`
- [ ] `board.py up` starts it, `down` stops it; a port in use gives a clear message
- [ ] Run the full suite. Expected: PASS
- [ ] Commit

### Task 3: Export settings and the project tag

**Files:**
- Modify: `plugin/skills/monitor/SKILL.md` (section "Export settings"), the setup script of `plugin/skills/setup/` (prints the blocks), `scripts/qa-codex` (Codex runs carry `agk.project`), `tests/test_qa_codex.py`, the setup tests
- Owner step (not an agent edit): the `env` block in each kit project's `.claude/settings.json` and the `[otel]` block in `~/.codex/config.toml`

**Interfaces:**
- Consumes: the Collector endpoints of Task 1
- Produces: Claude Code and Codex data with `agk.project` set, so the filter of Task 1 keeps it

Content of the printed blocks:

- Claude Code (`env` of the project's `.claude/settings.json`): `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317`, `OTEL_LOG_TOOL_DETAILS=1`, `OTEL_RESOURCE_ATTRIBUTES=agk.project=<owner/name>`, `OTEL_METRIC_EXPORT_INTERVAL=60000`. `OTEL_LOG_USER_PROMPTS` is not set (M4)
- Codex (`~/.codex/config.toml`): `[otel]` with `exporter` OTLP to the same Collector, `log_user_prompt = false`, agent responses off

Steps:

- [ ] Find and record (in `SKILL.md`, with the Codex version) how a Codex run gets the resource attribute `agk.project`: a `-c` config override on `codex exec`, or `OTEL_RESOURCE_ATTRIBUTES` in its environment. The sandbox arguments of `scripts/qa-codex` do not change. If no way exists, post `## Engineer: BLOCKED` with what was tried
- [ ] Write the failing tests: `test_qa_codex_passes_project_tag` (the `codex exec` command line or environment carries `agk.project=<owner/name>` of the repo); `test_setup_prints_otel_blocks` (the setup output holds both blocks, with the project's `owner/name`, and no `OTEL_LOG_USER_PROMPTS`)
- [ ] Run them. Expected: FAIL
- [ ] Implement. Run the full suite. Expected: PASS
- [ ] Ask the owner in `## Engineer: DONE` to set both blocks (they are the owner's settings; `docs/process.md`, "Escalation"). Then the live check, recorded in the same comment: one short Claude Code session in this repo and one `scripts/qa-codex` run appear in Prometheus (`claude_code_token_usage…` with `agk_project`) and Loki; one Claude Code session in a folder without the tag leaves no trace
- [ ] Commit

### Task 4: Recording rules: attribution per minute

**Files:**
- Create: `plugin/skills/monitor/otel/rules/agk.yaml`, `plugin/skills/monitor/otel/rules/agk_test.yaml` (a `promtool test rules` file), `tests/test_monitor_rules.py`

**Interfaces:**
- Consumes: the Claude Code metrics `claude_code.token.usage` (attribute `type`: `input`, `output`, `cacheRead`, `cacheCreation`) and `claude_code.active_time.total` (`type="cli"` only), attributes `query_source`, `agent.name`, `model`; the Codex metric `codex.turn.token_usage` (`token_type`) and the `duration_ms` histograms of `codex.api_request` and `codex.tool.call`; `agk_marker` of Task 2. The exact Prometheus names after the Collector's conversion are taken from the live data of Task 3
- Produces: `agk:tokens:1m` and `agk:active_seconds:1m` of "Shared names"

Rules:

- Tokens: the increase of each counter over the last minute, mapped to `role` and `kind` as in "Shared names", joined with `agk_marker` on `agk_project` for `stage`, `issue`, `launch`
- Active time, priority rule: within one minute, the active seconds of the subagent or Codex count to their role; the orchestrator's seconds count only for the part not covered: `max(0, orchestrator − sum of the others)`. So a minute is never counted twice, and the sum of all roles in a minute is at most 60

Steps:

- [ ] Write the `promtool` test file with these cases:
  - `tokens_go_to_marker_issue`: marker issue 10, role engineer; 1000 `cacheRead` tokens of `agent.name=software-engineer` → `agk:tokens:1m{issue="10", role="engineer", kind="cache_read"}` = 1000
  - `orchestrator_time_not_twice`: orchestrator 60 s and engineer 50 s in one minute → engineer 50, orchestrator 10
  - `codex_cached_input_split`: Codex input 100 with cached 80 → `input` 20, `cache_read` 80
  - `stage_level_without_issue`: marker `issue=""` → the tokens keep `issue=""`
- [ ] Write `tests/test_monitor_rules.py`: `test_rules_have_promtool_tests` (each rule in `agk.yaml` appears in at least one case of `agk_test.yaml`) and `test_rule_names` (the two names of "Shared names")
- [ ] Run `docker run --rm -v "$PWD/plugin/skills/monitor/otel/rules:/r" --entrypoint promtool <pinned Prometheus image> test rules /r/agk_test.yaml`. Expected: FAIL before the rules exist
- [ ] Write the rules. Run the same command. Expected: `SUCCESS`. Put the output in `## Engineer: DONE` (QA may not have Docker; the output is the evidence)
- [ ] Run the full suite. Expected: PASS
- [ ] Commit

### Task 5: Live board

**Files:**
- Create: `plugin/skills/monitor/grafana/boards/live.json`, `tests/test_monitor_board_layout.py`
- Modify: `plugin/skills/monitor/SKILL.md` (what the board shows)

**Interfaces:**
- Consumes: `agk:tokens:1m`, `agk:active_seconds:1m`, `agk_issue_info`, `agk_marker`, `agk_usage_limit_percent`, `agk_facts_last_success_seconds`; Loki events `claude_code.tool_result` and `claude_code.api_request` and the Codex events for the "Now" line and the last tool
- Produces: a shared test helper `panels(board) -> list[dict]` and the layout tests that Task 6 extends

Panels, in this order, as in spec "The boards" → "Live board": Now (stat or text), Tokens per issue by role (barchart, stacked), Active time per issue by role (barchart, stacked), Timeline (state-timeline), Plan usage limit (bargauge), Launches of this stage (table), Telemetry (row, collapsed) with the eight time-series panels of the spec. Filters: project, stage. Refresh 30 s. A small text in the Now panel shows the age of the facts when it is more than 2 minutes old.

Typical values (spec "Typical values"): the dashed line is the median per issue over the earlier stages of the project; the table highlight compares tokens and active time of a launch with the 75th percentile of launches of the same role in earlier stages. Both come from queries over `agk:tokens:1m` and `agk:active_seconds:1m`. With fewer than three earlier stages, the line and the highlight are absent.

Steps:

- [ ] Write the failing tests in `tests/test_monitor_board_layout.py`:
  - `test_live_panel_types`: the panel titles and types match the list above, in order; the only `table` panel is "Launches of this stage"
  - `test_role_colours`: every field override for a role or a token kind uses its hex from the spec table "Colours"
  - `test_launch_table_columns`: columns in the order issue, role, tokens, active time, return, model, start; no fixed column width; cell wrap off
  - `test_builtin_panels_only`: every panel type is one of Grafana's built-in types (`stat`, `text`, `barchart`, `state-timeline`, `bargauge`, `table`, `timeseries`, `row`)
  - `test_queries_use_known_names`: every PromQL query uses only metric names of "Shared names" or of the OTel metrics of Task 4, and only the labels listed there
  - `test_telemetry_row_collapsed`: the row "Telemetry" is collapsed and holds the eight panels
  - `test_highlight_needs_three_stages`: the typical-value and highlight queries return nothing when fewer than three earlier stages exist (the query holds a `count(...) >= 3` guard)
- [ ] Run them. Expected: FAIL
- [ ] Build the board in Grafana against the running stack, export the JSON, and clean it (no instance ids). The return mark "↺" comes from a value mapping; the running dot is a teal value mapping in the role column; "typical issue" is a dashed threshold line where the bar chart allows it
- [ ] Run the full suite. Expected: PASS
- [ ] Screenshot of the board with live data of this stage, attached to `## Engineer: DONE`
- [ ] Commit

### Task 6: History board with drill-down

**Files:**
- Create: `plugin/skills/monitor/grafana/boards/history.json`
- Modify: `tests/test_monitor_board_layout.py`, `plugin/skills/monitor/SKILL.md`

**Interfaces:**
- Consumes: the same metrics as Task 5; Loki `claude_code.tool_result` (tool, target, duration) and `claude_code.api_request` (tokens per request for the context size) for the steps of a launch. A launch's time range comes from the first and last minute of its `launch` value in `agk:active_seconds:1m`; the steps query reads Loki in that range for that role
- Consumes: `panels(board)` of Task 5

Panels, in order, as in spec "The boards" → "History board": Tokens per stage by role (barchart, stacked), Active time per stage by role (barchart, stacked), Token kinds per stage (barchart, stacked), Selected stage: tokens per issue by role (barchart, stacked), Most expensive issues of all stages (barchart, horizontal, stacked, top 10), Steps of a launch (barchart for tool call durations with a context size line, or a timeseries panel with bars and a line), Launches of the issue (table), Steps of the launch (table), Kit document reads per role (barchart). Drill-down with data links: stage bar → stage filter; issue bar → issue filter; launch row → launch filter.

Kit documents: a `Read` whose target is under `docs/`, `.agents/skills/`, `plugin/skills/`, or is `AGENTS.md`, `CLAUDE.md`.

Steps:

- [ ] Add the failing tests: `test_history_panel_types` (titles, types and order; the only tables are the two drill-down tables), `test_history_drilldown_links` (the three data links set the variables `stage`, `issue`, `launch`), `test_history_table_columns` (launches table as in Task 5; steps table: step, tool, target, duration, tokens, time), and the colour and built-in tests of Task 5 for this board
- [ ] Run them. Expected: FAIL
- [ ] Build, export and clean the board as in Task 5
- [ ] Run the full suite. Expected: PASS
- [ ] Screenshot with data of this stage, attached to `## Engineer: DONE`
- [ ] Commit

### Task 7: Check on real data, and the living spec

**Files:**
- Modify: `docs/specs/agent-graph-kit.md` (section "Monitoring stack (optional)"), `plugin/skills/monitor/SKILL.md` (only if the check finds a gap)

Steps:

- [ ] With the stack up during at least two issues of this stage: screenshots of both boards, the drill-down down to the steps of one launch, and the Telemetry row open
- [ ] M2: peak RAM and CPU of each container over 10 minutes of agent work with both boards open (`docker stats`). Expected: below 1 GB together
- [ ] M5: disk use of the Prometheus and Loki volumes after the issues, and the estimate for one year
- [ ] Compare the per-issue tokens on the live board with the sum of the `claude_code.api_request` events in Loki for one issue. Expected: equal within 1 %
- [ ] Rewrite the living spec section in short: the four containers, `facts.py`, the owner's export settings, forward only, the two boards
- [ ] Run the full suite. Expected: PASS
- [ ] Commit. Record all numbers and screenshots in `## Engineer: DONE`

## Order and blockers

1 → 2 → 4; 1 → 3 → 4; 4 → 5 → 6 → 7. Task 3 needs the owner to set the export settings before its live check.
