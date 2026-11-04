# Run record check (issue #255)

Date: 2026-11-04. Spec: `docs/specs/2026-10-21-run-record.md`, with the living spec section "Run record" in `docs/specs/agent-graph-kit.md`.

This file holds record field values and report output only (counts, ids, model names, times, issue numbers). It holds no transcript text.

## The record that was read

- Path: `~/.local/state/agent-graph-kit/run-record.jsonl`
- Line count: 462 (the same count as at grooming time). Every line has `v` 1
- `run-record-limits.jsonl`: does not exist, so the limit part of the report was not checked
- Repeated `id`: none in the whole file, for every line kind
- Line kinds: Claude subagent 259, `qa-codex` 83, `issue` 98, orchestrator measured 11, orchestrator estimate 11

Lines per project, stage and role:

| project | stage | pm | engineer | qa | qa-codex | orchestrator | issue | total |
|---|---|---|---|---|---|---|---|---|
| Lighfe/agent-graph-kit | 254 | 5 | 8 | 0 | 8 | 2 | 6 | 29 |
| Lighfe/quack-rl | 162 | 9 | 9 | 5 | 4 | 2 | 10 | 39 |
| Lighfe/quack-rl | 166 | 9 | 15 | 7 | 7 | 2 | 9 | 49 |
| Lighfe/quack-rl | 198 | 28 | 37 | 9 | 26 | 4 | 22 | 126 |
| Lighfe/quack-rl | 208 | 12 | 10 | 0 | 10 | 2 | 9 | 43 |
| Lighfe/quack-rl | 223 | 9 | 9 | 3 | 6 | 2 | 9 | 38 |
| Lighfe/quack-rl | 239 | 9 | 9 | 3 | 6 | 2 | 10 | 39 |
| Lighfe/quack-rl | 252 | 10 | 11 | 5 | 6 | 2 | 11 | 45 |
| Lighfe/quack-rl | 257 | 7 | 8 | 1 | 6 | 2 | 7 | 31 |
| Lighfe/quack-rl | 267 | 5 | 6 | 1 | 4 | 2 | 5 | 23 |
| total | | 103 | 122 | 34 | 83 | 22 | 98 | 462 |

Models: Claude subagent lines use `claude-sonnet-5-5` (141) and `claude-opus-5-5` (118). All `qa-codex` lines use `gpt-6-astra`. Orchestrator lines use `claude-opus-5-5` (6), `claude-sonnet-5-5` (4) and `claude-haiku-5-5` (2; stage 198 only). Every launch line has `effort` `medium`; orchestrator and issue lines have `effort` null.

### Why Stage 17 (#247) has no lines

The record has no line with `stage` 247 and no line for any of its sub-issues (#228, #229, #239 to #246). The writer step itself was built in Stage 17: the orchestrator step "Write the run record" came with #246 (commit d9ffc3d, 2026-10-21 18:27 UTC), when the Stage 17 run was nearly over (its last sub-issue #246 closed 18:30 UTC). The Stage 17 run started hours before that commit (its first sub-issue #228 closed 16:39 UTC), so its orchestrator most likely worked from the role file as it read it at the start, without the writer step. The run notes of the Stage 17 review (comment 6326242109) name the plugin bump, but no writer run and no writer failure. So, as far as the record and the review show, the writer was not run for Stage 17. The first stage with lines is Stage 18 (#254), the next kit stage.

## Line kind: Claude subagent (`pm`, `engineer`, `qa`)

Verdict: complete for the kit Stage 18. For quack-rl, one gap that the record alone cannot explain (see "Missing lines").

- 259 lines. All 18 spec fields are present. No field is empty that the spec requires: `model`, `start`, `end`, `stage`, `issue` are set on every line. `provider` is `claude`, `source` is `transcript`, `estimate` is false on every line
- No line has `start` after `end`. No line has a negative or non-integer token field
- `retry` values: 0 (175), 1 (60), 2 (16), 3 (7), 4 (1). The `qa` lines count the receipts of the QA role group, so a Claude `qa` line after Codex runs has `retry` above 0 (for example quack-rl #182: two `qa-codex` lines, then a `qa` line with `retry` 3). This is as the spec says
- Observation, not a field fault: 11 launch lines end after the close time of their issue (the `end` of the `issue` line). Two end more than 100 minutes after the close:

| id (transcript part) | project | stage | issue | role | minutes after close |
|---|---|---|---|---|---|
| agent-a323df5afa344c498 | Lighfe/quack-rl | 162 | 159 | qa | 2.1 |
| agent-a323e815795469ccd | Lighfe/quack-rl | 162 | 158 | qa | 0.7 |
| agent-a1694d43677ef95b8 | Lighfe/quack-rl | 198 | 188 | engineer | 90.3 |
| agent-a1c47444604a6aa1f | Lighfe/quack-rl | 198 | 178 | engineer | 26.2 |
| agent-a2dcc996365ead340 | Lighfe/quack-rl | 198 | 195 | qa | 122.0 |
| agent-a446e83388feb4aac | Lighfe/quack-rl | 198 | 188 | engineer | 22.2 |
| agent-a6056abdbe90896d0 | Lighfe/quack-rl | 198 | 183 | qa | 30.1 |
| agent-ae01118ed71e55ea6 | Lighfe/quack-rl | 198 | 189 | qa | 0.4 |
| agent-ae6b2ac2456e167bd | Lighfe/quack-rl | 198 | 193 | qa | 110.7 |
| agent-aeb6b8a4f854ee3dd | Lighfe/quack-rl | 198 | 184 | qa | 39.5 |
| agent-a856722e958b15394 | Lighfe/quack-rl | 267 | 209 | qa | 0.5 |

  The spec defines `end` as the last message of the transcript, so the values follow the spec. The record cannot show why a transcript goes on after the close (for example work that went on in the background after the hand-back). It means that the launch time from `start` to `end` is not always time spent on the issue.

## Line kind: `qa-codex`

Verdict: not complete. One wrong value on every line.

- 83 lines. All 18 spec fields are present and set. `provider` is `codex`, `source` is `codex-record`, `cache_creation_tokens` is 0 on every line, as the spec says
- Wrong value: `retry` is 0 on all 83 lines. The spec says `retry` counts the earlier launch receipts of the role group on the issue. 16 issues have two or more `qa-codex` lines, and all of these lines still have `retry` 0. Examples: kit #249 (three runs, three QA receipts, all `retry` 0), kit #250 (two runs), quack-rl #196 (four runs). The writer sets `retry` to a fixed 0 for Codex lines
- `start` equals `end` on every line. The Codex record has one time per run (written when the run ends), so the writer puts that time in both fields. The spec says `start` is the first message of the launch. So `start` is not the launch start, and the line gives no launch time
- Token meaning: on all 83 lines `cache_read_tokens` (the Codex `cached_input_tokens`) is not larger than `input_tokens`. This agrees with the OpenAI usage format, where the input count includes the cached input. If that is so, the new input is `input_tokens` minus `cache_read_tokens`, and the weights count the cached part twice (see "Report" below). The record alone cannot prove it; it needs a check against the Codex usage format

## Line kind: `issue`

Verdict: not complete. Ten lines have empty `start` and `end`, and two fields have values the spec does not define.

- 98 lines. All spec fields and `escalations` are present. All four token fields are 0 on every line. `escalations` is 0 on 94 lines and 1 on 4 lines
- Empty fields: the line of the stage issue itself, one per stage, has `start` null and `end` null and no launch line. Ids: `Lighfe/agent-graph-kit:issue:254`, `Lighfe/quack-rl:issue:162`, `Lighfe/quack-rl:issue:166`, `Lighfe/quack-rl:issue:198`, `Lighfe/quack-rl:issue:208`, `Lighfe/quack-rl:issue:223`, `Lighfe/quack-rl:issue:239`, `Lighfe/quack-rl:issue:252`, `Lighfe/quack-rl:issue:257`, `Lighfe/quack-rl:issue:267`. The cause: the orchestrator step saves the JSON of the stage issue together with the sub-issues, and the writer writes an issue line for every issue in that file. A stage issue has no launch receipt, and it is still open when the writer runs, so both times are null. The spec describes issue lines for task issues only
- Values the spec does not define: `provider` is null on all 98 lines (the spec table allows `claude` or `codex`), and `source` is `transcript` on all 98 lines, although an issue line comes from the issue JSON, not from a transcript
- No line has `start` after `end`

## Line kind: orchestrator measured

Verdict: complete.

- 11 lines, one per stage and model (stage 198 has two models: `claude-haiku-5-5` and `claude-sonnet-5-5`). All fields are present. `issue` is null, `estimate` is false, `retry` is 0, `effort` is null
- `source`: `transcript` on 9 lines, `session-total` on the 2 lines of stage 198. Both are allowed by the spec
- No line has `start` after `end`. No `id` is repeated, so the writer ran once per stage

## Line kind: orchestrator estimate

Verdict: complete. The ratio is 1.1, up to the rounding to whole tokens.

- 11 lines, one for each measured line, with the same session and model and the suffix `estimate`. `estimate` is true, `source` is the same as on the measured line
- No stage has more than one measured or estimate line with the same `id`. If one had, a reader takes the last line of that `id` (spec, and `read_record` in `scripts/run_report.py` does so)

## Missing lines

### Kit Stage 18 (#249 to #253): launch receipts against the record

| issue | pm receipts / lines | engineer receipts / lines | qa receipts (agent `qa-codex`) / lines | issue line |
|---|---|---|---|---|
| #249 | 1 / 1 | 3 / 3 (retry 0, 1, 2) | 3 / 3 | yes |
| #250 | 1 / 1 | 2 / 2 (retry 0, 1) | 2 / 2 | yes |
| #251 | 1 / 1 | 1 / 1 | 1 / 1 | yes |
| #252 | 1 / 1 | 1 / 1 | 1 / 1 | yes |
| #253 | 1 / 1 | 1 / 1 | 1 / 1 | yes |

Every launch receipt has a record line. The eight `qa-codex` lines also match the eight lines of `codex-qa-usage.jsonl` for these issues one to one (same issue and `time`). No gap. The planner launch on #254 has no line; planner tokens are a non-goal of the spec.

### quack-rl stages (inside the record only)

- Each `issue` line of a task issue has at least one `pm`, one `engineer` and one QA line, except:
  - quack-rl #200 (stage 198): one `pm` line, no `engineer` line, no QA line. Its issue line has `escalations` 1, so the issue was most likely escalated after grooming. This is a gap in the work, not in the writer
  - the ten stage issue lines named under "Line kind: `issue`" have no launch line at all
- Each launch line has an `issue` line for the same project and issue. No gap
- One `retry` sequence skips a value: quack-rl #206 (stage 208) has `engineer` lines with `retry` 0, 2 and 3, and none with 1. So there was an engineer launch receipt with no record line. The record cannot tell whether that launch had no transcript (for example a launch that did not start) or whether the line is missing

## Estimate and weighted totals per stage

Ratio of the estimate line to the measured line per token kind (input, output, cache creation, cache read), and the weighted Claude total that `uv run scripts/run_report.py --record ~/.local/state/agent-graph-kit/run-record.jsonl --project <project> --stage <stage>` prints (column "measured"; the column "estimate" is the orchestrator estimate line alone):

| project | stage | model | input | output | cache creation | cache read | 1.1? | weighted Claude measured | weighted Claude estimate column |
|---|---|---|---|---|---|---|---|---|---|
| Lighfe/agent-graph-kit | 254 | claude-sonnet-5-5 | 1.1019 | 1.1 | 1.1 | 1.1 | yes | 2,271,766.8 | 1,001,019.9 |
| Lighfe/quack-rl | 162 | claude-sonnet-5-5 | 1.1 | 1.1 | 1.1 | 1.1 | yes | 5,200,625.8 | 1,505,515.8 |
| Lighfe/quack-rl | 166 | claude-sonnet-5-5 | 1.1 | 1.1 | 1.1 | 1.1 | yes | 10,242,661.4 | 2,465,809.6 |
| Lighfe/quack-rl | 198 | claude-haiku-5-5 | 1.0998 | 1.1 | 1.1 | 1.1 | yes | 38,111,241.5 (both models) | 15,738,195.9 (both models) |
| Lighfe/quack-rl | 198 | claude-sonnet-5-5 | 1.1 | 1.1 | 1.1 | 1.1 | yes | (above) | (above) |
| Lighfe/quack-rl | 208 | claude-opus-5-5 | 1.0994 | 1.1 | 1.1 | 1.1 | yes | 9,890,976.5 | 2,151,493 |
| Lighfe/quack-rl | 223 | claude-opus-5-5 | 1.1012 | 1.1 | 1.1 | 1.1 | yes | 5,602,114.5 | 1,674,982.7 |
| Lighfe/quack-rl | 239 | claude-opus-5-5 | 1.0994 | 1.1 | 1.1 | 1.1 | yes | 6,929,022.7 | 1,448,090.5 |
| Lighfe/quack-rl | 252 | claude-opus-5-5 | 1.0995 | 1.1 | 1.1 | 1.1 | yes | 12,277,210.8 | 2,192,808.4 |
| Lighfe/quack-rl | 257 | claude-opus-5-5 | 1.0984 | 1.1 | 1.1 | 1.1 | yes | 4,306,879.8 | 1,274,483.9 |
| Lighfe/quack-rl | 267 | claude-opus-5-5 | 1.102 | 1.1 | 1.1 | 1.1 | yes | 3,050,571.8 | 861,471.9 |

The input ratios differ from 1.1 only because the input counts are small (196 to 2,564) and the estimate is rounded to whole tokens (for example 216 × 1.1 = 237.6, stored as 238). The other three kinds are 1.1 to four places.

The orchestrator share is large: in kit Stage 18 the measured orchestrator line alone weighs about 0.91 million of the 2.27 million weighted Claude total. The factor 1.1 is a guess (living spec); the record holds no data to test it, because no `run-record-limits.jsonl` exists and the Claude Code usage view was not available to this check. The owner can compare the "weighted Claude measured" column with the usage view.

## Report output

Output of `uv run scripts/run_report.py --record ~/.local/state/agent-graph-kit/run-record.jsonl --project Lighfe/agent-graph-kit` (exit code 0; the tables "Tokens per role", "Tokens per model", "Weighted totals per provider" and "Time and escalations per issue" are complete; "Tokens per issue", "Tokens per project" and "Retries" are shortened):

```
# Run report (from the run record)

## Tokens per role

| role | input | output | cache creation | cache read |
|---|---|---|---|---|
| engineer | 216 | 1,804 | 358,192 | 5,455,238 |
| orchestrator (measured up to the report; not complete) | 216 | 12,483 | 86,428 | 7,393,528 |
| pm | 98 | 637 | 181,501 | 1,290,889 |
| qa-codex | 1,998,521 | 13,645 | 0 | 1,694,976 |
| estimate | 238 | 13,731 | 95,071 | 8,132,881 |

## Tokens per issue

| issue | input | output | cache creation | cache read |
|---|---|---|---|---|
| #249 | 925,349 | 7,188 | 180,455 | 2,721,397 |
| #250 | 251,134 | 2,785 | 109,867 | 1,509,390 |
| ... (#251 to #253) |
| none | 216 | 12,483 | 86,428 | 7,393,528 |
| estimate | 238 | 13,731 | 95,071 | 8,132,881 |

## Tokens per model

| model | input | output | cache creation | cache read |
|---|---|---|---|---|
| claude-sonnet-5-5 | 530 | 14,924 | 626,121 | 14,139,655 |
| gpt-6-astra | 1,998,521 | 13,645 | 0 | 1,694,976 |
| estimate | 238 | 13,731 | 95,071 | 8,132,881 |

## Tokens per project

| project | input | output | cache creation | cache read |
|---|---|---|---|---|
| Lighfe/agent-graph-kit | 1,999,051 | 28,569 | 626,121 | 15,834,631 |
| estimate | 238 | 13,731 | 95,071 | 8,132,881 |

## Weighted totals per provider

Label: estimate from price ratios, not measured plan use. Claude and Codex are never added together.

| provider | measured | estimate |
|---|---|---|
| claude | 2,271,766.8 | 1,001,019.9 |
| codex | 2,236,243.6 | 0 |

## Time and escalations per issue

| issue | time | escalations |
|---|---|---|
| #249 | 0h 16m | 0 |
| #250 | 0h 09m | 0 |
| #251 | 0h 10m | 0 |
| #252 | 0h 05m | 0 |
| #253 | 0h 06m | 0 |
| #254 | n/a | 0 |

## Retries

Highest retry value per role and issue (0 means no repeat).

| role | issue | retry |
|---|---|---|
| engineer | #249 | 2 |
| engineer | #250 | 1 |
| ... (engineer #251 to #253: 0; pm #249 to #253: 0) |
| qa-codex | #249 | 0 |
| qa-codex | #250 | 0 |
| ... (qa-codex #251 to #253: 0) |
```

### Places where the report reads badly or is wrong

1. Retries table, `qa-codex` #249 and #250: shows 0, but the issues had three and two QA runs. Wrong, because the writer stores `retry` 0 on every Codex line
2. Time table, row #254: the stage issue shows as an issue with time "n/a". It comes from the issue line of the stage issue and is not a task
3. "estimate" as a row in the role, issue, model and project tables: it is the orchestrator estimate line, but the tables do not say so, and in the model table it hides which model it is
4. Tokens per issue, row "none": it is the measured orchestrator line, but the label does not say so
5. Tokens per issue and per project add Claude and Codex counts in one row (for example #249 input 925,349 is almost all Codex). The two providers count input in different ways, so the sum has no clear meaning
6. Weighted totals, column "estimate": it is the orchestrator estimate line alone (1,001,019.9), not an estimate for the stage. The "measured" column already holds the measured orchestrator line, so the two columns cannot be added, and the header does not say this
7. Weighted Codex total: if the Codex `input_tokens` includes the cached input (see "Line kind: `qa-codex`"), the cached part is weighted twice, at 1 and at 0.1. For kit Stage 18 the total would then be 541,267.6 and not 2,236,243.6. To be checked
8. Role label "measured up to the report": the line is measured up to the writer run, not up to the report
9. No stage split: with `--project Lighfe/quack-rl` the nine quack-rl stages are added together in every table. The spec asks for the numbers "for a stage and for the record as a whole"; today each stage needs its own run with `--stage`. The `--stage` help text also only describes the comments mode ("its subIssues list is read from the JSON")

Also found in the spec, not in the report: in the field table of `docs/specs/2026-10-21-run-record.md` the rows `id` and `project` are joined into one row: the `id` cell ends with "Issue line: project, issue", then come two pipe signs and the text of the `project` row, so the table shows no `project` row.

## Proposed follow-ups

1. **Writer: count `retry` on Codex QA lines**
   - Reason: every `qa-codex` line has `retry` 0, also on the second and later QA runs of an issue, so the retries in the report are wrong for QA
   - Criterion: a writer test with three Codex runs and three QA launch receipts on one issue writes three `qa-codex` lines with `retry` 0, 1 and 2

2. **Writer: no issue line for the stage issue, and defined `provider` and `source` for issue lines**
   - Reason: each stage gets an issue line for the stage issue itself, with empty `start` and `end`, which shows as a task with time "n/a" in the report. Issue lines also have `provider` null and `source` `transcript`, which the spec does not define
   - Criteria: a writer test whose issue file holds the stage issue and two sub-issues writes issue lines for the two sub-issues only; the spec field table names the `provider` and `source` value of an issue line, and a test checks that value

3. **Codex token meaning: check whether `input_tokens` includes the cached input**
   - Reason: on all 83 Codex lines the cached count is not larger than the input count. If the input includes the cached part, the weighted Codex total counts it twice and is about four times too high for kit Stage 18
   - Criteria: the run-record spec states, with its source, whether Codex `input_tokens` includes `cached_input_tokens`; if it does, a report test with one Codex line (input 100, cached 80, output 0) gives the weighted total 20 + 8 = 28

4. **Report: clear labels for the orchestrator and estimate rows, and a stage split**
   - Reason: the "estimate" rows and column, the "none" row and the joined Claude and Codex counts read badly (places 3 to 6, 8 and 9 above)
   - Criteria: in the report from a test record with one stage, the estimate row of each table names the orchestrator and the model; the issue table has no "none" row without the word orchestrator; the weighted totals table says that the estimate column is the orchestrator estimate line; a record with two stages gives one weighted total per stage

5. **Spec: split the joined `id` and `project` rows of the run-record field table**
   - Reason: the field table of `docs/specs/2026-10-21-run-record.md` has no `project` row; its text is inside the `id` row
   - Criterion: the field table has a row whose first cell is `` `project` ``
