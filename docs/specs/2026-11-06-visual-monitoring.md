# Visual monitoring: Grafana boards, live and after the stage

## Purpose

The owner watches the agent-graph-kit work in Grafana: live, while a stage runs, and afterwards, for a finished stage. The numbers on the boards are correct.

The aim is the same as in `docs/specs/2026-11-04-kit-monitoring.md`: find where the kit itself spends tokens and time, and where it creates overhead. That stage collected the data and gave a marimo notebook to explore it. The notebook is for data exploration (and for tagging retry cases), not for monitoring. Grafana takes over the monitoring.

The owner's laptop is not strong (8 cores, 15 GB RAM, about 5 to 6 GB free while agents run). The stack must not slow down agent work.

## Goals

- Correct data first: the six findings of the run-record check (`docs/reviews/2026-11-04-run-record-check.md`, section "Proposed follow-ups"), the Codex step rows at the stage end (#272), and retry cases of more than one stage (#273)
- An optional, light Grafana stack in the plugin, started and stopped by the owner with one command each
- A live board: what runs now and what ran in the current stage
- A history board: cost per project, stage, issue, role and model, with drill-down
- The plan usage limit in percent on the live board, when a local source for it exists

## Non-goals

- OpenTelemetry, Prometheus, Loki, Tempo or any other store than one SQLite file. They are a later stage. The table layout stays close to the step rows, so a later OpenTelemetry source can feed the same boards
- Live CPU and memory per agent. Wanted, not a blocker: a later stage (it needs an extra collector)
- Alerts, outlier detection, and any loop decision that reads monitoring data
- Replacing the marimo notebook. It stays, unchanged except where Part A changes the data it reads
- Planner (`/stage-start`) session tokens on the boards (collected, not shown)
- The PM's standard form of a test-suite criterion (a finding of the Stage 19 review). It is not monitoring work

## Anti-goals

- A stack that runs on its own, starts at boot, or keeps using CPU when the owner does not look at it
- A board that shows wrong numbers without saying so. An estimate is labelled as an estimate
- Any monitoring data leaving the owner's machine

## Principles

O1 to O5 of `docs/specs/2026-09-26-agent-graph-observability.md` hold. In short: no hook, script or role reads monitoring data to decide anything (O1); a failing monitoring write or a stopped stack never changes a QA result, a retry count, a comment or a hook decision (O2); runtime data stays local with owner-only file modes (O3); the loop works the same without the stack, and role files do not change for it (O4).

Added for this stage:

- M1: Grafana listens on `127.0.0.1` only. It needs a login (no anonymous access). The admin password is not in the repo: it comes from the owner's environment or a local file with mode 0600, created on first start
- M2: resource budget. The stack with both boards open uses at most 400 MB RAM in total (target about 300 MB), and close to no CPU while no board refreshes. Board refresh is 30 s at most often. A task measures this on the owner's machine and records the numbers
- M3: no GitHub token, Claude or Codex credential goes into a container

## Part A: Correct the data

Each item is one task. Sources: `docs/reviews/2026-11-04-run-record-check.md` for A1 to A6, the parked issues for A7 and A8, the Stage 19 review prompt audit for A9.

- A1 Codex token meaning: the run-record spec (`docs/specs/2026-10-21-run-record.md`) states, with its source (Codex docs or source code, or a measured stream), whether Codex `input_tokens` includes `cached_input_tokens`. If it does, the weighted total counts the non-cached input plus the weighted cached part, not both in full (report test: input 100, cached 80, output 0 gives 20 + 8 = 28 with the weights of `docs/run-weights.json`). The notebook and the boards use the same rule
- A2 Writer: `retry` counts on `qa-codex` lines (three Codex runs and three QA launch receipts on one issue give `retry` 0, 1, 2)
- A3 Writer: a real `start` on `qa-codex` lines (the launch receipt time, not the end time)
- A4 Writer: no issue line for the stage issue itself; the spec field table names the `provider` and `source` value of an issue line
- A5 Report: clear labels for the orchestrator estimate rows, and one weighted total per stage
- A6 Spec: a `project` row in the run-record field table
- A7 #272: the stage-end `write` also writes the Codex QA step rows of the stage
- A8 #273: `cases.py collect` keeps the cases of other projects and stages
- A9 `.agents/skills/bump-plugin-version/SKILL.md` repeats the two exceptions of the release steps in `AGENTS.md` (nothing to commit when no bump is needed; no commit when the script or the tests fail)

Order: A1 before A5 (both change weighted totals); A3 before A7 (both change the Codex part of `run_record.py`).

## Part B: The store and the loader

The loader turns the existing files into one SQLite file that Grafana reads.

- Input: the run record, the step rows, the retry cases and the retry tags, at the paths the monitor skill already uses (`$RUN_RECORD_FILE`, `$STEPS_FILE`, `$XDG_STATE_HOME/agent-graph-kit/…`, else `~/.local/state/agent-graph-kit/…`), and the Codex stream folder
- Output: `<state dir>/agent-graph-kit/monitor.sqlite`, mode 0600. It is a derived copy: deleting it and running the loader again gives the same content
- Each run first runs the step collector (`steps.py collect`) for every configured project, then loads only the new lines (by file offset or by id). A half-written last line is skipped, as in the step collector. A run on an unchanged state does no work beyond reading file sizes
- Projects: the owner's projects that use the kit, from a small local config file (for example `<state dir>/agent-graph-kit/monitor-projects.json`: `owner/name` and repo path per project). The loader writes a starter file with the current project when none exists
- Liveness: for each launch, the time of its newest step. For a Codex QA attempt, the modification time of its stream file (its rows carry only the attempt start). A launch is active when that time is at most 5 minutes old. The rule lives in one place and the live board uses it
- Weighted tokens: the loader computes them with the weights file (the same lookup as the notebook: `$RUN_WEIGHTS_FILE`, else `docs/run-weights.json` of the project, else the skill copy) and the rule of A1. Claude and Codex are never added together. Weighted values are marked as estimates in the tables
- Escalations: the retry cases whose marker is a `## ... NEEDS OWNER` line
- Retry cases and issue titles: at most every 5 minutes, the loader runs `cases.py collect` for the open stage issue of each project (label `stage`), and reads the titles of its sub-issues, with `gh` (read only). Between those runs it uses the last result
- The loader runs on the host, not in a container, because the step collector reads the stage of a running issue with `gh` (read only) and M3 keeps the token out of containers. It loops every 30 s while the stack runs and stops with it
- Read only toward GitHub and toward the transcript and state files it reads. It writes only `monitor.sqlite` and its log
- O2: a loader error is written to its log and shown on the live board as "last load: failed at <time>". It never touches the loop

## Part C: The stack

- One `compose.yaml` in the monitor skill folder: one Grafana container (pinned image version) with the SQLite data source plugin (pinned version), the data source and both boards provisioned from files in the skill. The SQLite file is mounted read-only
- One command starts the stack and the loader, one command stops both (or one foreground command that stops both on Ctrl-C). The monitor `SKILL.md` documents them and the URL. Nothing starts on boot (`restart: no`)
- Docker and Docker Compose are a requirement of this optional part only. `/agk:setup` does not install them. Without Docker the command says so and exits; nothing else in the kit changes
- The first start downloads the image and the plugin. After that the stack works without network
- M2 check: with both boards open and refreshing for 10 minutes during a running stage, record the peak RAM of the container and the loader, and their CPU use, in `## Engineer: DONE`

## Part D: The boards

Both boards have filters for project and stage. They show numbers and text: no verdict, no recommendation.

Live board ("Now"):

- Active launches: role, model, issue (with its title when known), stage, start, run time, tokens so far (raw and weighted estimate), the last tool and target, the time of the last step
- Current stage: every launch of the stage so far, in time order (a timeline or a table), with retries visible
- Codex QA attempts of the stage, active or done
- Usage limit in percent per plan, when Part E finds a source; else a panel that says "no source; weighted tokens are an estimate". The values the owner already enters by hand with `run_record.py limit` (`run-record-limits.jsonl`, start and end of a stage) are shown in both cases, labelled as entered by hand
- The time of the last load, and a failed load

History board ("Stages"):

- Per stage: weighted tokens per provider (estimate), raw token kinds, time, launches, retries, escalations
- Breakdowns by issue, role and model, with the same filters as the notebook totals
- Drill-down: stage, then issue, then launch, then steps (tool, target, tokens, duration, context size over the steps). Grafana data links between panels are enough
- Kit document reads per role (`kit_doc`)

Board files are JSON in the skill folder, provisioned on start. A test runs every SQL query of the board files against a synthetic SQLite fixture, so a schema change that breaks a panel fails a test without starting Grafana.

## Part E: Source of the usage limit in percent

A short check, written to `docs/research/` as a note:

- Does Claude Code expose the plan usage limit in percent locally (for example in the status-line input or in another local file), and how can it be kept over time?
- Does Codex expose it (for example in the `codex exec --json` stream or a local file)?
- For each: the exact field, the Claude Code or Codex version checked, and how a value would reach the store

The note proposes the way. A way that changes the owner's user settings (for example a status-line command) is the owner's step: the task says so in words and the owner decides. The live-board task for the usage limit shows the values only from a source the note found and the owner accepted.

## Decided by the owner

- Grafana takes over the monitoring; the marimo notebook stays for data exploration
- Fix the data in the same stage
- Start light: Grafana with SQLite, about 200 to 300 MB RAM is fine
- OpenTelemetry and heavier stores later (expected about 400 to 700 MB for a lean OpenTelemetry setup, 1 to 2 GB for the full bundle)
- Live CPU and memory per agent: wanted, not a blocker for this stage
- Monitoring is about the kit as a whole (from the earlier stage)

## My calls (planner)

- SQLite in a file, no database server
- 30 s refresh and a 5 minute liveness window (the same window as the notebook)
- The loader runs on the host, not as a container (Part B gives the reason: `gh` and M3). This replaces the container loader I named in the session
- Grafana needs a login (M1)
- The PM test-criterion form stays out of this stage

## Left to the builder

- Names of the scripts, tables and board panels; the table layout
- Which Grafana SQLite data source plugin, and the exact versions (pinned, at least two weeks old)
- How the loader tracks what it has loaded
- The panel types and layout of the boards
