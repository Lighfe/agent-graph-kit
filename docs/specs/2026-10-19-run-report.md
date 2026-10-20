# Run report: time and tokens of a stage

## Purpose

The owner sees where a stage spends time and tokens: per role, per issue (outliers) and per failure type. The report is a script for the kit owner. It is not shipped in `plugin/`. #189 and #190 use its numbers.

## Design

`scripts/run_report.py` (Python standard library only) is read-only. It calls no network and writes only Markdown to stdout.

Call:

```
python3 scripts/run_report.py --comments <issues.json> (--issues 1,2,3 | --stage N) [--transcripts <folder>] [--codex-usage <file>]
```

- `<issues.json>` holds, for each issue, the output of `gh issue view <n> --json number,comments,closedAt,labels` (one object, a list of objects, or an object keyed by issue number). For `--stage N`, the object of the stage issue carries a list `subIssues` of issue numbers (added by the owner from the sub-issue list); the script does not call GitHub.
- `<file>` is the Codex QA token record `codex-qa-usage.jsonl` that `qa-codex` keeps (see "Token record" in `docs/specs/agent-graph-kit.md`). For each issue the report prints one line `Codex QA tokens: <sum of input, cached input and output>`, or `Codex QA tokens: no record` without the flag, with a missing or empty file, or when the issue has no line.
- `<folder>` is searched recursively for `.jsonl` files. These are the Claude Code subagent transcripts, normally under `<projects folder>/<project>/<session>/subagents/`.

## Numbers and sources

| Number | Source | Where the data lives |
|---|---|---|
| Time from the first `## Launch:` receipt to close (else to the last result marker) | `createdAt` of the receipt, `closedAt` of the issue | issue comments |
| Launches per role (a continuation receipt counts) | first line `## Launch: <role> (...)` | issue comments |
| Launches without a result, per role | no marker of the same role group (`PM`, `Engineer`, `QA`, `Planner`) between this receipt and the next receipt of that group | issue comments |
| Failure type share | first lines `## Engineer: BLOCKED`, `## QA: FAIL`, `## QA: UNAVAILABLE`, `## QA: UNVERIFIABLE`; escalation is label `needs-owner` or a `## ... NEEDS OWNER` marker. Share is issues with the type divided by all issues of the report; an issue without a marker counts with zero | issue comments and labels |
| Tokens per role and issue: input, output, cache creation, cache read | `usage.input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` of each assistant message, summed over the transcripts whose first prompt has `ROLE=<role> ISSUE=<n>`. A message id seen twice counts once | subagent transcripts (`.jsonl`) |

The fields were checked on a real transcript: each assistant line has `message.usage` with the four counts and `message.model`; `.meta.json` next to it has `agentType`; the first user line starts with `ROLE=<role> ISSUE=<n>`. The report takes the role from the first prompt. The model is not printed yet.

The last section "Most expensive" names the top 3 issues by launch-to-close time, the top 3 by total tokens (the four counts added), the role with the most tokens and the failure type with the largest share. With fewer than 3 issues it lists those it has. Without tokens it says "no transcript data" and prints the rest.

## Not measured

- Tokens of the main session (orchestrator, planner in `/stage-start`): the report reads subagent transcripts only, not the transcript of the main session.
- Tokens of Codex QA runs are read from the record only when `--codex-usage` is given; runs from before the record existed, and failed runs, have no number.
- Memory and CPU (see #223).
- Transcripts deleted by Claude Code retention: the report says "no transcript" for such an issue and does not guess.
- The link from one launch comment to one transcript: the report joins on role and issue number only (see #31). A launch that was retried is therefore summed with the first one.

## Relation to open ideas

- #28 (process report over issue comments): this report covers its comment-based part, and the token part from transcripts.
- #30 (Codex run record), #31 (launch-to-transcript link) and #32 (OTel export) stay open. They are the ways to add Codex data and an exact launch-to-transcript link.
