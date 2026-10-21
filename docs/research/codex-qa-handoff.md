Issue: #229

# Hand-off from a limit-stopped Codex QA run to the fallback QA

This note changes no code and spent no Codex quota. It made no `codex exec` call. It reads the code, the specs and the token record of #224.

It revisits decision 3 of `docs/research/codex-qa-delays.md` ("Hand-off to the fallback: do not apply"). That decision said: a failed run leaves no evidence; revisit the one named case (partial `--json` events of a run that the limit stopped in the middle) once the token record exists. The record exists now.

## Sources

- Code: `scripts/codex_exec.py`, `scripts/qa-codex`.
- `docs/research/codex-qa-delays.md` (decision 3, section "Hand-off to the fallback"). It cites `docs/research/quack-rl-pattern-review.md` for the timing numbers: Codex QA median 3.6 minutes (77 results), fallback median 9.2 minutes (15 results), the failed Codex run median 0.6 minutes, 14 of 15 `## QA: UNAVAILABLE` results were the usage limit.
- `docs/research/spike-codex-cli.md` (error events of `--json`, the usage limit is not retried).
- The token record `codex-qa-usage.jsonl` of #224. The file is local (state dir outside the git tree), so the numbers are quoted here.

## What a limit-stopped run leaves

### Kept today

| Item | Where | Kept after a stop? |
|---|---|---|
| Reset time of the limit | `parse_reset_time`, `write_limit`, `read_limit` in `scripts/codex_exec.py`; used in `_main` of `scripts/qa-codex` | Yes. One timestamp in a local file. The next launch skips Codex until then (#203) |
| The failure reason (the `turn.failed` message) | `_turn_failed`, `failure_reason` in `scripts/codex_exec.py`; `post(UNAVAILABLE, reason)` in `_main` | Yes. One redacted line in the `## QA: UNAVAILABLE` comment (cut to `REASON_MAX`, 500 characters) |
| The comment that says what was verified | `render` in `scripts/qa-codex` | No. With `output is None`, `render` writes only the marker, the reason and `Checker: codex`. No criteria, no tests line, no `Verified:` line |
| Token numbers | `usage_from_stdout`, `record_usage` in `scripts/codex_exec.py` | No. They come from the `turn.completed` event, which a stopped run never prints. `run_codex` returns `CodexRun("unavailable", None, reason)` with `usage=None`, and `_main` calls `record_usage` only for status `ok` |
| The `-o` result file | `run_codex` | No. `run_codex` returns on `p.returncode != 0` before it reads the file, and `shutil.rmtree(tmp)` removes it in `finally`. The spike (`docs/research/spike-codex-cli.md`, `-o` after a failed run) says a failed run does not write a new one |
| The stdout events | `p.communicate` in `run_codex` | No. The text sits in a local variable. `failure_text` and `_turn_failed` read only the last `turn.failed` message and the rest is dropped when the function returns |
| The inputs that `qa-codex` built before Codex started: GitHub state files, worktree, uv cache, prompt | `write_github_state`, `pre_step`, `build_prompt` in `scripts/qa-codex` | Built, then deleted: `finally` in `_main` removes the worktree and the run temp folder. The fallback does not need them (it has `gh` and builds its own checkout) |

So today a stopped run leaves exactly: a marker, one reason line and a stored reset time.

### What the partial `--json` events could add

With `--json`, Codex prints one JSON event per line on stdout while it works. The record of #224 (step 1 of its comment) shows the types `thread.started`, `turn.started`, `item.completed` and `turn.completed` for a trivial run; the spike shows `error` and `turn.failed` for a failure. So a stopped run has at least the events that came before `error` and `turn.failed`: one `item.completed` event for each finished item of the run (for example a message, and, as far as the event format goes, a command that Codex ran).

What these events could add for the fallback:

- the commands Codex had run and whether they succeeded (for example `git diff`, the test command and its exit code)
- the test result, if the test command had finished
- notes of the model in messages, such as "criterion 2 holds because ..."

What they cannot add, from what the code and the records show:

- A verdict for a criterion. The verdicts exist only in the final JSON that the output schema asks for (`scripts/qa-result.schema.json`, validated in `validate`), which is written at the end and goes to the `-o` file. A stopped run never reaches it. "Criteria already checked" would have to be guessed from commands and messages. No code or record shows that a message names a criterion by number.
- Whether the event format of a command item holds the command text, the exit code and the output. This was not checked: the only real `--json` run in the repo is the trivial "Reply with exactly: ok" run of #224, which ran no command. Checking it needs a Codex run.

### Does a stopped run leave a usable partial result?

The note cannot show it. Two reasons:

1. No stopped run was ever captured. `run_codex` drops the stdout of a failed run, and the record of #224 holds only runs that ended `ok`. Nobody has seen the events of a real mid-run stop.
2. The numbers point to a stop at the start, not in the middle. The failed Codex run has a median of 0.6 minutes (36 seconds), against 3.6 minutes for a whole QA run (both from `docs/research/quack-rl-pattern-review.md`, via the delays note). A run that had done work would be nearer to minutes. The spike's stub test hit the limit at the first request (0.9 seconds, no retry).

The token record shows that a mid-run stop is possible in principle, because the runs are large. All 14 lines of the record, input tokens (cached in brackets, output next to it):

```
#224  807,130 (763,264) out 3,094
#223   85,377 (58,624)  out 976
#223  106,289 (80,256)  out 1,010
#227  254,832 (215,040) out 2,353
#227 1,189,053 (1,153,152) out 4,507
#227  203,740 (165,120) out 1,568
#231  166,476 (138,880) out 1,019
#151 1,166,148 (1,125,888) out 2,356
#235  571,502 (533,632) out 2,864
#150 1,106,943 (1,046,912) out 3,114
#236 1,277,066 (1,232,640) out 3,066
#230  623,946 (589,952) out 2,337
#150 1,397,908 (1,341,568) out 3,560
#228  519,057 (483,968) out 1,925
```

The input tokens of a finished run range from 85,377 to 1,397,908, and the median is about 598,000 (the mean of 571,502 and 623,946). Output is 976 to 4,507 tokens, about 0.3 to 1.2 percent of the input. Using the delays note's figure of about 40,000 input tokens per tool call, the median run makes about 15 tool calls and the largest about 35. A run of that length could meet a limit in the middle. But the record cannot say how often a limit stops a run after some work, because it never sees stopped runs.

## Ways to hand over the checked criteria

Both ways have the same base: `qa-codex` keeps the stdout of a failed run (today dropped in `run_codex`) and redacts it. They differ in what goes to the fallback.

### Way A: an event digest as hints

`run_codex` returns the stdout with a failed `CodexRun` (a new field). On `unavailable` after the process had started, `_main` writes a short digest into the `## QA: UNAVAILABLE` comment: the commands that finished, their exit codes, and the last test result, if the event format has them. The orchestrator's fallback launch text and `docs/team/qa-engineer.md` say: the digest is a list of hints, not evidence.

- The fallback may trust: nothing as proof. It may use the digest to choose where to look first (which files, which test command).
- The fallback must check again: every criterion, and it must run the tests itself. A claim that "the test passed" was made by an earlier step that is not independent.
- Cost in time: saves about 0 to 1 minute of the fallback's 9.2 minutes (basis: the delays note estimated one to two minutes for the whole pre-built data and called it a guess; a digest of commands saves less than that, because the fallback still runs each command to see the result). It costs nothing at run time of Codex.
- Cost in maintenance: `scripts/codex_exec.py` (keep and parse the stdout of a failed run, new field on `CodexRun`, redaction of command text), `scripts/qa-codex` (`render` and `_main`), `docs/team/qa-engineer.md` and the fallback launch text in `docs/team/orchestrator.md`, the spec sections "QA launcher" and "Failure rules" in `docs/specs/agent-graph-kit.md`, and the tests `tests/test_qa_codex.py` (new cases: events before a limit, no events, a secret in a command) and the fake `codex` in `tests/fakes`. The event format of a command item must first be learned from a real run, and the format can change with a Codex CLI version.

### Way B: a checkpoint of verdicts that Codex writes as it goes

The Codex prompt asks Codex to append one line per criterion to a file in the run temp folder as soon as it has decided that criterion (id, verdict, evidence). If the limit stops the run, `qa-codex` reads the file and puts the criteria that were decided into the `## QA: UNAVAILABLE` comment. The fallback checks only the rest in full.

- The fallback may trust: a `fail` verdict as a pointer to look at first (it still confirms the failure, because a false FAIL sends the issue back to the engineer for nothing). It may trust the evidence text of a `pass` only as a lead.
- The fallback must check again: every `pass`. A false PASS is the costly error, and the QA step is the only check between the engineer and the close (delays note, section "Model by issue importance"). If it re-checks every pass, it saves little: the work that the Codex run did is exactly the work that has to be repeated, and the fallback has a cold start (delays note: "the fallback being a Claude agent with a cold start").
- Cost in time: saves about 0 to 3 minutes of the fallback's 9.2 minutes, and only on a mid-run stop. The upper figure assumes half the criteria were decided and the fallback confirms each in about half the time it needs for a fresh check. Basis: the 5.6-minute difference between the fallback (9.2) and Codex (3.6), halved for the half of the criteria, and halved again for the confirmation. It is a guess; there is no measurement. Because the failed-run median is 0.6 minutes, most stops would have no checkpoint lines at all.
- Cost in maintenance: the prompt in `build_prompt`, a writable path in the sandbox settings (`QA_SANDBOX`, `scripts/qa-codex`), the checkpoint reader and `render`, a new trust rule for the fallback in `docs/team/qa-engineer.md`, the specs ("QA launcher", "Failure rules"), and tests in `tests/test_qa_codex.py`. It also depends on the model following the prompt rule (write after each criterion), which is unmeasured. The prompt change might shift the behaviour of every Codex QA run, also the runs that finish, and its effect on the verdict quality is unmeasured.

## Decision: do not apply

Decision 3 of `docs/research/codex-qa-delays.md` said "do not apply" for three reasons. Here is what changed since then and what did not:

- Changed: the token record exists (#224), so the condition "revisit once the record exists" is met. The record shows the size of finished runs (median about 598,000 input tokens, up to about 1.4 million). That makes a mid-run stop plausible in principle.
- Not changed: the record has only runs that ended `ok`. It holds no stopped run, and `run_codex` still drops the stdout of a failed run. So there is still no evidence that a stopped run leaves a usable partial result. The note found no verdicts in the events, and not even a confirmed format for command events.
- Not changed: the only timing available (failed run median 0.6 minutes against 3.6) says the limit is usually met at the start. #203 already removes the cost of those runs: the reset time is stored and the next launch skips Codex.
- Not changed: the possible saving is small (about 0 to 1 minute for Way A, 0 to 3 minutes for Way B, both guesses) against a new trust problem in the check that should be independent and a maintenance cost on `qa-codex`, the fallback role and the specs.

### What new evidence would reopen it

Reopen when there is a captured `--json` stdout of a real Codex QA run that the limit stopped after it had run commands, with both of these shown:

1. The events hold the command, its exit code and its output, and a message or file that ties a result to a criterion.
2. Stopped runs with work done are a real share of the `## QA: UNAVAILABLE` results. For example: the failed run takes longer than about 2 minutes in more than 1 of 5 stopped runs, measured from the time between the launch receipt and the `## QA: UNAVAILABLE` comment on the issue.

A cheap way to get that evidence (a choice for the planner, not part of this decision): extend the token record of #224 with one line for a stopped run, with only the elapsed seconds and the number of `item.completed` events, never any text. That would show whether stops with work done happen at all, with no hand-off built.
