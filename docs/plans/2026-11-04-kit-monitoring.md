# Kit monitoring Implementation Plan

> **For agentic workers:** this plan is executed through GitHub issues, as `docs/process.md` defines (one issue per task, PM, engineer, QA). Do not use the skills subagent-driven-development or executing-plans (see `AGENTS.md`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** collect step-level data and retry cases for every plugin project, also while a stage runs, and give the owner a marimo notebook to explore where the kit spends tokens and time.

**Architecture:** a new hand-written plugin skill `monitor` (`plugin/skills/monitor/`) holds a step extractor, a retry case collector, a shared data module and a marimo notebook. The extractor reuses the transcript reading of `plugin/skills/run-record/run_record.py`; the run-record `write` command also writes step rows. `qa-codex` keeps the Codex event stream of each attempt, and the extractor turns it into step rows.

**Tech Stack:** Python 3.11 standard library for the extractor and the collector (uv inline scripts, as `run_record.py`); marimo (and polars or pandas, the builder's choice) only inside the notebook, never in `/agk:setup`; pytest.

**Spec:** `docs/specs/2026-11-04-kit-monitoring.md`

## Global Constraints

- No conclusions, verdicts, scores or automatic cause groups in any output (spec "Purpose", "Non-goals")
- No hook, script or role reads monitoring data to make a decision; a failing monitoring write never changes a QA result, retry count, comment or hook decision (O1, O2)
- Data files stay outside the repo in `<state dir>/agent-graph-kit/` with mode 0600; folders 0700 (O3)
- Never write thinking text, prompt text or tool output text; only sizes, names, paths, and `Bash` commands cut to 300 characters
- Role files do not change for monitoring (O4)
- The extractor and the collector call no network, except `gh` read-only calls named in the spec (parent issue, issue comments)
- Marimo is not installed by `/agk:setup` (#188)
- `plugin/skills/monitor/` is a hand-written skill: add `"monitor"` to `HAND_SKILLS` in `scripts/build_plugin.py`
- The engineer does not bump the plugin version

## Review Focus

- A transcript that is still being written (half line at the end): the extractor skips that line and reads the rest; running again later adds the remaining steps, no duplicates
- The same transcript read twice (refresh, then stage end): no duplicate step ids
- A `Bash` command that holds a secret-looking value beyond 300 characters is cut; output text never appears in `steps.jsonl`
- A retry case whose issue body was edited and no commit followed (rewording only): the case shows "no commit" and "body edited", not an error
- A `qa-codex` run where the stream write fails (read-only folder): the QA result is the same as without the write

---

### Task 1: Step extractor

**Files:**
- Create: `plugin/skills/monitor/SKILL.md`, `plugin/skills/monitor/steps.py`
- Modify: `plugin/skills/run-record/run_record.py` (`write` also writes the step rows of the stage), `plugin/skills/run-record/SKILL.md` (one line), `scripts/build_plugin.py` (`HAND_SKILLS`)
- Test: `tests/test_monitor_steps.py` with synthetic transcripts in `tests/fakes/monitor/`

**Interfaces:**
- Consumes: transcript reading of `run_record.py` (`read_launch`, `is_subagent_transcript`, `project_folder`), moved to a shared place or imported; the builder chooses, no copied code
- Produces: `steps_path() -> Path` (`$STEPS_FILE`, else `<state dir>/agent-graph-kit/steps.jsonl`); `read_steps(transcript: Path, project: str, stage: int | None) -> list[dict]`; `write_steps(rows: list[dict]) -> int` (appends rows whose `id` is new, returns the count); CLI `uv run --script steps.py collect --project <name> [--transcripts <folder>] [--stage <n>]`. Row fields exactly as the table of spec Part 1: `v`, `id`, `project`, `stage`, `issue`, `role`, `launch`, `seq`, `time`, `duration_s`, `model`, `input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens`, `context_tokens`, `tool` (list), `target` (list), `result_chars`, `is_error`, `kit_doc`

- [ ] **Step 1: Write failing tests** in `tests/test_monitor_steps.py`:
  - `test_one_row_per_assistant_message`: a fake engineer transcript (`ROLE=engineer ISSUE=7`) with 3 assistant messages gives 3 rows with `role == "engineer"`, `issue == 7`, `seq == [0, 1, 2]`
  - `test_tool_and_target`: a `Read` of `docs/process.md` gives `tool == ["Read"]`, `target == ["docs/process.md"]`, `kit_doc == "docs/process.md"`; a `Bash` call with a 400-character command gives a target of length 300
  - `test_no_text_written`: the fake transcript holds the marker strings `SECRET_PROMPT`, `SECRET_THINKING`, `SECRET_OUTPUT`; none appears in the written file
  - `test_half_line_skipped`: a transcript whose last line is cut gives the rows of the full lines, no exception
  - `test_no_duplicates`: `write_steps` twice on the same rows returns `n` then `0`; the file has `n` lines
  - `test_main_session_role`: a main-session transcript whose first user line is `/goal …` gets `role == "orchestrator"`, `/stage-start` gives `planner`, else `main`
  - `test_file_mode`: the created file has mode `0o600`
  - `test_run_record_write_writes_steps`: `run_record.py write` with the existing fixtures also creates step rows for the stage's launches
- [ ] **Step 2: Run** `uv run --with pytest pytest tests/test_monitor_steps.py -v`. Expected: FAIL (module missing)
- [ ] **Step 3: Implement** `steps.py` and the `run_record.py` call. The run-record call wraps the step write so that its failure prints a warning and the run-record result stays the same (O2). `context_tokens = input + cache_creation + cache_read`; `duration_s` is the time to the next assistant message, null for the last. `stage`: the `--stage` argument, else from the run record when it has the issue, else the parent issue (`gh api repos/<slug>/issues/<n>/parent`, read only, once per issue), else null
- [ ] **Step 4: Run** the test file, then `uv run --with pytest pytest`. Expected: all pass, tests shown as run; `uv run scripts/build_plugin.py` leaves no diff
- [ ] **Step 5: Commit**

### Task 2: Keep the Codex QA event stream (#30)

**Files:**
- Modify: `scripts/codex_exec.py`, `scripts/qa-codex` (built copies in `plugin/bin/` via `uv run scripts/build_plugin.py`), `plugin/skills/monitor/steps.py` (read the streams)
- Test: `tests/test_qa_codex.py`, `tests/test_monitor_steps.py`

**Interfaces:**
- Consumes: Task 1 `write_steps`, row fields
- Produces: `codex_runs_dir() -> Path` (`$CODEX_RUNS_DIR`, else `<state dir>/agent-graph-kit/codex-runs/`); `save_stream(project: str, issue: int, attempt_time: datetime, stdout: str) -> Path | None` (returns None on any write error, never raises); file name `<project with / as __>-<issue>-<UTC time %Y%m%dT%H%M%S>.jsonl`; `prune_streams(now: datetime, days: int = 90) -> int`; `read_codex_stream(path: Path) -> list[dict]` in `steps.py`, rows with `role == "qa-codex"`

- [ ] **Step 1: Write failing tests**: `test_stream_saved_on_ok_run`, `test_stream_saved_on_timeout` (partial stdout kept), `test_stream_write_failure_keeps_result` (a read-only folder: the posted QA result is identical to a run without saving), `test_prune_older_than_90_days`, `test_stream_mode_0600`, `test_codex_stream_to_steps` (a fake stream with two `command_execution` items and one `turn.completed` gives step rows with the commands as `target` and the usage tokens)
- [ ] **Step 2: Run** the two test files. Expected: FAIL
- [ ] **Step 3: Implement.** Do not change the sandbox arguments of `qa-codex` (spec Part 3)
- [ ] **Step 4: Run** `uv run --with pytest pytest`; build leaves no diff. Expected: all pass
- [ ] **Step 5: Commit**

### Task 3: Retry case collector

**Files:**
- Create: `plugin/skills/monitor/cases.py`
- Test: `tests/test_monitor_cases.py` with saved issue JSON fixtures (synthetic)

**Interfaces:**
- Consumes: issue JSON as `run_record.py load_issues` reads it (`number`, `comments`, `closedAt`, `labels`, plus `body` and `userContentEdits` or the issue's edit time when present); the run record and `steps.jsonl` for cost
- Produces: `collect_cases(issues: list[dict], project: str, stage: int | None, repo: Path | None) -> list[dict]`; case fields: `id` (`<project>:<issue>:<round>`), `project`, `stage`, `issue`, `round`, `marker`, `comment_url`, `failed_lines` (list of str), `criteria` (list of str, the matching issue-body lines), `next_markers` (list of str), `body_edited` (bool), `commit` (sha or null), `files_changed`, `lines_added`, `lines_removed`, `tokens` (sum of the round's launches, per provider), `seconds`; `cases_path()` (`<state dir>/agent-graph-kit/retry-cases.jsonl`, rewritten as a whole on each collect); CLI `uv run --script cases.py collect --project <name> (--issues <file> | --repo-slug <owner/repo> --stage <n>) [--repo <path>]`

- [ ] **Step 1: Write failing tests**: `test_qa_fail_starts_a_round` (launch qa, `## QA: FAIL` with one line `- [ ] … - FAIL`, launch engineer, DONE, launch qa, PASS gives one case with `marker == "## QA: FAIL"` and that line in `failed_lines`); `test_blocked_and_rewording` (BLOCKED, then a body edit, then a new qa launch gives `body_edited == True`, `commit is None`); `test_markers_counted`: each of `QA: FAIL`, `QA: UNVERIFIABLE`, `QA: INVALID`, `QA: UNAVAILABLE`, `Engineer: BLOCKED`, `PM: NEEDS OWNER` starts a round; `test_no_round_without_relaunch`; `test_no_verdict_fields` (no key named `cause`, `verdict`, `category` or `score`)
- [ ] **Step 2: Run.** Expected: FAIL
- [ ] **Step 3: Implement.** The commit is the SHA named in the next `## Engineer: DONE`; line counts from `git -C <repo> show --numstat` when `--repo` is given, else null
- [ ] **Step 4: Run** the full test command. Expected: all pass
- [ ] **Step 5: Commit**

### Task 4: Marimo notebook: totals, drill-down, running stage

**Files:**
- Create: `plugin/skills/monitor/data.py` (loaders and joins, standard library + the dataframe library), `plugin/skills/monitor/explore.py` (marimo notebook)
- Modify: `plugin/skills/monitor/SKILL.md` (how to start: `uv run --with marimo --with <df lib> marimo edit "${CLAUDE_SKILL_DIR}/explore.py"`, and that the notebook runs `steps.py collect` on refresh)
- Test: `tests/test_monitor_data.py`

**Interfaces:**
- Consumes: Task 1 rows, run record lines (`run-record.jsonl`, last line per `id`), `docs/run-weights.json` weights
- Produces: `load_steps()`, `load_record()`, `totals(record, by: list[str])`, `launch_steps(steps, launch: str)`, `kit_doc_reads(steps, by: list[str])`, `running(steps, now, active_minutes: int = 5)`; weighted totals labelled "estimate from price ratios, not measured plan use"

- [ ] **Step 1: Write failing tests**: `test_totals_by_role` on fixture rows; `test_weighted_totals_per_provider` (Claude and Codex never summed together); `test_record_last_line_per_id`; `test_running_marks_recent_launch_active` (a launch with a step 2 minutes ago is active, 20 minutes ago is not); `test_notebook_parses` (`explore.py` compiles with `python -m py_compile`)
- [ ] **Step 2: Run.** Expected: FAIL
- [ ] **Step 3: Implement** `data.py`, then the notebook views Totals, Drill-down (launch → steps, context size over the steps, kit document reads) and Running stage, with filters for project, stage, issue, role, model and retry. No verdict text
- [ ] **Step 4: Run** the full test command; then run the notebook headless on the fixtures (`uv run --with marimo … marimo export html explore.py -o /tmp/explore.html` with `STEPS_FILE` and `RUN_RECORD_FILE` set to fixtures). Expected: tests pass, export exits 0
- [ ] **Step 5: Commit**

### Task 5: Notebook: retry cases view with owner tags

**Files:**
- Modify: `plugin/skills/monitor/explore.py`, `plugin/skills/monitor/data.py`
- Test: `tests/test_monitor_data.py`

**Interfaces:**
- Consumes: Task 3 `retry-cases.jsonl` and `cases.py collect`; Task 4 `data.py`
- Produces: `load_cases()`, `load_tags()`, `save_tag(case_id: str, tag: str, note: str) -> None` (appends to `<state dir>/agent-graph-kit/retry-tags.jsonl`, mode 0600; the last line per `case_id` wins)

- [ ] **Step 1: Write failing tests**: `test_tag_roundtrip` (save two tags for one case, load gives the second); `test_tags_survive_recollect` (rewriting `retry-cases.jsonl` keeps the tags); `test_tags_file_mode`
- [ ] **Step 2: Run.** Expected: FAIL
- [ ] **Step 3: Implement** the view: a table with filters (project, stage, role, marker, tag), per case the criterion text, failed lines, next markers, change (commit, files, lines, body edited) and cost, and a tag and note field that calls `save_tag`. Tags are free text chosen by the owner; the notebook offers no preset causes
- [ ] **Step 4: Run** the full test command and the headless export as in Task 4. Expected: pass, exit 0
- [ ] **Step 5: Commit**

## Existing issues in the same stage (not tasks of this plan)

- #255 check the run record against its spec (read only)
- #258, #259, #260, #261, #262: upstream fixes from quack-rl to the role files. #262 point 1: a credit or spend-limit pause needs the owner, the engineer stops with `## Engineer: BLOCKED`
