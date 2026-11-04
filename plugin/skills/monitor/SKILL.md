---
name: monitor
description: "Write the step rows of Claude Code launches: one JSON line per assistant message (tools, tokens, time), kept outside the repo. Use when the owner asks what a launch did or cost step by step, also while a stage still runs."
---

# Monitor

This skill writes one row per step (assistant message) of each Claude Code launch, so the owner can see what each launch did and what it cost. It reads the transcripts as they are, also while a launch still runs. It writes no prompt, thinking or tool output text: only sizes, tool names, file paths and the Bash command cut to 300 characters. The rows are for the owner to read; no hook, script or role uses them to decide anything.

## Steps

1. Run the script from this skill's folder in the project root:

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/steps.py" collect --project <name> [--transcripts <transcript folder>] [--stage <stage issue number>]
   ```

2. The script prints how many rows it wrote. Running it again adds no second row for the same step.

- `--transcripts`: default `~/.claude/projects/<current dir with each character that is not a letter or digit replaced by ->`. Every `*.jsonl` under it is read, subagent transcripts included.
- Role and issue come from the first prompt `ROLE=<role> ISSUE=<n>`. A transcript without it has issue null and role `orchestrator` (`/goal`), `planner` (`/stage-start`, `/agk:stage-start`) or `main`: the first user line that starts with `<command-name>/goal</command-name>` or a stage-start command tag decides.
- Stage: `--stage`, else the stage of a run-record line of the issue, else the parent issue from `gh api repos/{owner}/{repo}/issues/<n>/parent` (read only, one call per issue), else null.
- A step of a launch that is still running can be written before it is complete (its last tool results or its `duration_s` missing); a later run does not change a row that is already written.

The step file is `$STEPS_FILE`, else `$XDG_STATE_HOME/agent-graph-kit/steps.jsonl`, else `~/.local/state/agent-graph-kit/steps.jsonl`, with mode 0600. The `write` command of the run-record skill also writes the step rows of a stage. Spec: `docs/specs/2026-11-04-kit-monitoring.md`, Part 1.
