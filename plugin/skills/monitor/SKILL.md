---
name: monitor
description: "Write the step rows of Claude Code launches and Codex QA attempts: one JSON line per assistant message or Codex command and turn (tools, tokens, time), kept outside the repo. Use when the owner asks what a launch did or cost step by step, also while a stage still runs."
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
