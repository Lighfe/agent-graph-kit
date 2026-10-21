# Run record Implementation Plan

**Goal:** Keep the cost of every launch (tokens, model, time, retries, escalations) in one local JSONL file that the plugin writes at the end of a stage, and let the report read it. In the same stage: the Codex QA limit work and three doc fixes from the stage review of #238.

**Architecture:** A stdlib-only writer script ships in the plugin as a hand-written skill (like `drift`). It reads the subagent transcripts, the Codex QA token record and the issue JSON, and appends flat JSON lines to `<state dir>/agent-graph-kit/run-record.jsonl`. `scripts/run_report.py` gets `--record` and a weights table. The orchestrator runs the writer once per stage, before the planner is launched.

**Tech Stack:** Python 3 standard library, pytest, `uv run --script`, `gh` JSON.

**Spec:** `docs/specs/2026-10-21-run-record.md`

## Global Constraints

- Record path: `<state dir>/agent-graph-kit/run-record.jsonl`; env `RUN_RECORD_FILE` is the whole path, else `$XDG_STATE_HOME`, else `~/.local/state`
- Limit path: `run-record-limits.jsonl`, same folder
- The writer calls no network and writes no prompt, comment or output text
- Weights are never stored in the record
- Format version `v` is 1
- Orchestrator lines are always appended; every other line is skipped when its `id` exists
- Tests never touch the real state dir: they set `RUN_RECORD_FILE`
- Plugin copies are built: `uv run scripts/build_plugin.py` leaves no diff, and `uv run --with pytest pytest` passes

## Review Focus

- A transcript with no assistant usage: writes no token line, no crash
- A launch with two models: two lines, same `retry`
- The writer runs twice on the same input: the second run adds no non-orchestrator line
- An open issue (no close time): the Codex window runs to now
- A Codex line of another issue or outside the window: skipped and counted
- An empty or missing Codex file: no Codex lines, no crash
- A record line that is not valid JSON: the report skips it and says how many

---

## Order

1. Existing issues #228, #229, #239 (Codex limit work, role-file examples)
2. Task 1 and 2 (doc fixes)
3. Task 3 to 6 in a chain
4. Task 7 last (blocked by Task 6 and Task 1, which edits the same file)

### Task 1: Orchestrator doc reference

Fix `docs/team/orchestrator.md:80`: replace `and the line below (see "Definition of done")` with `and ends with the sentence required in "Definition of done"`. Rebuild plugin copies; update any test that pins the old text.

### Task 2: Planner prompt audit file list

Fix `docs/team/planner.md:213`: the sentence says the `docs/` run reads `docs/process.md`, `docs/team/` and `docs/task-template.md`; add `docs/checks/`. Rebuild plugin copies; update any test that pins the old text.

### Task 3: Writer for Claude subagent launches

**Files:** Create `plugin/skills/run-record/SKILL.md`, `plugin/skills/run-record/run_record.py`, `tests/test_run_record.py`. Modify `scripts/build_plugin.py` (add `run-record` to `HAND_SKILLS`) and the plugin test that lists skills.

**Interfaces:**
- Produces: command `run_record.py write --project <name> --stage <n> --issues <issues.json> --transcripts <folder>` (later tasks add options); function `record_path() -> Path`; function `claude_lines(issues, transcripts, project, stage) -> list[dict]`; function `append_lines(lines)` that skips an existing `id`, except lines with `role == "orchestrator"`

### Task 4: Codex lines and issue lines

**Files:** Modify `plugin/skills/run-record/run_record.py`, `tests/test_run_record.py`.

**Interfaces:**
- Consumes: Task 3 `append_lines`, `record_path`
- Produces: option `--codex-usage <file>`; function `codex_lines(usage_file, issues, project, stage) -> (list[dict], int)` (lines and the number skipped); function `issue_lines(issues, project, stage) -> list[dict]`

### Task 5: Orchestrator lines

**Files:** Modify `plugin/skills/run-record/run_record.py`, `tests/test_run_record.py`.

**Interfaces:**
- Consumes: Task 3
- Produces: option `--orchestrator-transcript <path>` (else the newest main-session transcript of the project folder, with the file named on stdout); function `orchestrator_lines(path, project, stage) -> list[dict]` with a measured line and an estimate line

### Task 6: Weights, limits and the report

**Files:** Create `docs/run-weights.json` (name is the builder's choice, one file); modify `scripts/run_report.py`, `plugin/skills/run-record/run_record.py` (subcommand `limit`), `tests/test_run_report.py`, `tests/test_run_record.py`.

**Interfaces:**
- Consumes: Tasks 3 to 5 (record lines)
- Produces: `run_report.py --record <file> [--limits <file>]`; subcommand `run_record.py limit --project <name> --stage <n> --point start|end --percent <number> --plan <text>`; function `weighted(line, weights) -> float`

### Task 7: Orchestrator step, README and living spec

**Files:** Modify `docs/team/orchestrator.md`, `README.md`, `docs/specs/agent-graph-kit.md`, `plugin/skills/run-record/SKILL.md`; rebuild plugin copies.

**Interfaces:**
- Consumes: Tasks 3 to 6 (command forms)
- Produces: a numbered step in the "stage ended" part of `docs/team/orchestrator.md`, after the plugin release step and before the planner launch

Permissions: Task 7 needs an Auto mode allow entry so the orchestrator may run the writer, which appends to a file outside the repo.
