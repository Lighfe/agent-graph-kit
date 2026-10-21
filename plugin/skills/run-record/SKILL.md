---
name: run-record
description: "Write the run record of a stage: one JSON line per Claude subagent launch and model, kept outside the repo. Use when the orchestrator ends a stage, or when the owner asks to record the cost of a stage's launches."
---

# Run record

This skill keeps the cost of every subagent launch after Claude Code deletes its transcripts. It reads local files only, calls no network, and writes no prompt, comment or output text.

## Steps

1. For each issue of the stage, save `gh issue view <n> --json number,comments,closedAt,labels` to one JSON file (one object, a list, or an object keyed by number).
2. Run the script from this skill's folder:

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/run_record.py" write --project <name> --stage <stage issue number> --issues <issues.json> --transcripts <transcript folder> [--codex-usage <codex-qa-usage.jsonl>]
   ```

3. The script writes the Claude lines, the Codex QA lines (with `--codex-usage`) and one line per issue (time and escalations). It prints how many lines it wrote. Running it again adds no second line.

The record file is `$RUN_RECORD_FILE`, else `$XDG_STATE_HOME/agent-graph-kit/run-record.jsonl`, else `~/.local/state/agent-graph-kit/run-record.jsonl`. Spec: `docs/specs/2026-10-21-run-record.md`.

To enter the percent of the session limit used at the start or end of a stage by hand: `uv run --script "${CLAUDE_SKILL_DIR}/run_record.py" limit --project <name> --stage <n> --point start|end --percent <0-100> --plan <text>`. It appends to `run-record-limits.jsonl` next to the record (`$RUN_RECORD_LIMITS_FILE` sets the whole path). `scripts/run_report.py --record <file> --limits <file>` prints the percent next to the weighted total; the weights are in `docs/run-weights.json`.
