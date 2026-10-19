# Codex QA delays: tokens, model, hand-off

Issue: #189. This note answers three questions about the delays of the Codex QA (`scripts/qa-codex`). It changes no code. The changes are in #224. No new Codex call was made for this note, so no quota was spent.

## Sources and limits

- A. `docs/research/quack-rl-pattern-review.md` (14 of 15 `## QA: UNAVAILABLE` results were the usage limit; Codex QA median 3.6 minutes over 77 results; fallback median 9.2 minutes over 15 results; the failed Codex run itself median 0.6 minutes; 13 of 62 QA'd issues ended with a fallback verdict).
- B. `docs/research/spike-codex-cli.md` (one trivial run printed `tokens used 13,883`; the usage-limit error is not retried).
- C. `codex debug models` of the installed CLI (`codex-cli 0.153.4`). It makes no model call.
- D. Local Codex session files in `$HOME/.codex/sessions/`: 27 sessions with 2 or more tool calls, all with `gpt-6-astra`. Each file has `token_count` events with input, cached input and output tokens. These are Codex review and rescue runs the owner started (code review of a commit or a plan), not QA runs. `qa-codex` runs with `--ephemeral`, so a QA run stores no session. D is the best real number for a Codex run that reads a repo with tools. It is a proxy, not QA data.
- E. The prompt of `scripts/qa-codex`, built offline with its own `build_prompt` for five real closed issues (#220, #219, #217, #203, #193). Sizes in characters; tokens are about characters divided by 4 (an estimate).

What nobody measured: tokens of a real QA run, the quality of a QA verdict by model or effort, and the usage-limit weight of each model.

## Token use

Where a Codex QA run spends tokens:

| Part | Size | Source |
|---|---|---|
| Fixed Codex start (system prompt, tools), no repo work | 15,000 to 16,000 tokens in, 80 percent cached (15,265 and 16,126 for "Reply with exactly: ok"; 13,883 in B) | D, B |
| QA prompt built by `qa-codex` (role file, criteria, GitHub state text, comment block) | 11,300 to 14,600 characters, about 2,800 to 3,700 tokens | E |
| of that: role file `docs/team/qa-engineer.md` | 5,748 characters | E |
| of that: GitHub state text | 1,724 characters (the five JSON files are read by Codex with tools, on top) | E |
| of that: the newest `## Engineer: DONE`, full | 800 to 2,300 characters | E |
| of that: first line of every other comment | small, 6 to 16 comments | E |
| The diff of the commit range | 700 to 20,000 characters on the five issues. It is not in the prompt. Codex reads it with tools (`git diff`) | E |
| Files Codex reads and tests it runs | not measured for QA | none |
| Tool turns | Each tool call is one more request that sends the whole context again. Input tokens of a run grow with the number of tool calls: median 120,000 for 2 to 4 calls, 280,000 for 5 to 7, 450,000 for 8 to 10 | D |
| Output (the verdict JSON and reasoning) | median 2,300 tokens, at most 5,000 | D |

Answer to "why so many tokens": the prompt is small (about 3,000 tokens). The cost comes from the tool turns. Over the 27 runs of D, the median run sent 200,000 input tokens, 79 percent of them cached, so about 37,000 not cached; output was about 1 percent. About 40,000 input tokens per tool call. QA spends tokens because it looks into the repo with many small steps, not because the prompt is big. What counts against the usage limit (cached or not, input or output) is not documented in the repo; do not assume cached tokens are free.

Data about Codex tokens:

- Exists: normal mode prints `tokens used <n>` on stderr (B). The session files have `token_count` events with input, cached input, output and reasoning tokens, and the rate-limit percent (D). Whether `codex exec --json` prints a usage event on stdout was not checked here: that needs a run.
- Does not exist for QA: `qa-codex` runs `--json`, reads stdout only on failure (`codex_exec.failure_text`) and drops it after a success, and the run is `--ephemeral`. The run report spec says: "Tokens of Codex QA runs: no record is kept" (`docs/specs/2026-10-19-run-report.md`). So the kit has no token number for any QA run.
- Follow-up proposed: `qa-codex` keeps the usage numbers of each run (from the `--json` stdout, after one check of which event carries them) in a small record per run, and the run report reads it. This is the open idea #30 (Codex run record).

Splitting QA into sub-agents with smaller contexts:

- What would be split: one `codex exec` per criterion or per group of criteria, each with the shared prompt part and only its criteria.
- Estimate from D: input grows with tool calls. A run with 9 tool calls costs about 450,000 input tokens. Three runs of 3 tool calls cost about 3 x 120,000 = 360,000, a saving of at most 20 percent. But each split run pays the fixed start (about 15,000) again, repeats the same checkout reads and the same test run, and the verdicts must be merged. The real saving is lower, and it was not measured.
- Another cost: more Codex calls give more chances to hit the usage limit mid-run.
- Conclusion: do not split now. It does not fix the main delay (the limit hit and the cold fallback). Measure real QA tokens first; split only if QA runs show runs with many tool turns.

## Model by issue importance

What the installed CLI offers (`codex debug models`, `codex-cli 0.153.4`):

| Model | Listed | Efforts | Default effort | Description in the catalog |
|---|---|---|---|---|
| `gpt-6-astra` | yes | low, medium, high, xhigh, max, ultra | low | "Frontier intelligence for the most demanding work." |
| `gpt-5.6-sol` | yes | low to ultra | low | "Older generation workhorse model." |
| `gpt-5.6-terra` | yes | low to ultra | medium | "Older balanced model for straightforward work." |
| `gpt-5.6-luna` | yes | low to max | medium | "Older fast and efficient model." |
| `gpt-reserve` | hidden | low to max | medium | "Fast and affordable agentic coding model." |
| `codex-auto-review` | hidden | low to max | medium | "Automatic approval review model for Codex." |

Today `qa-codex` uses `QA_MODEL = "gpt-6-astra"` and `QA_EFFORT = "medium"` for every issue (`scripts/qa-codex`, spec "QA launcher").

Signals that could pick a model, all known to `qa-codex` before Codex starts:

- the lane (`Lane: default` or `frontend`; frontend QA uses a browser and is harder)
- the size of the diff (`git diff --shortstat`: the five issues above range from 2 to 426 changed lines)
- whether only files under `docs/` changed
- the number of criteria (5 to 9 above)
- a label on the issue (for example a new label for a light issue)

Recommendation:

- Keep `gpt-6-astra` for every issue for now. A cheaper model may fit a light issue (docs only, a small diff, few criteria), for example `gpt-5.6-terra` (described as for straightforward work). The quality risk: a weaker model may pass a criterion it should fail, and QA is the only check that sits between the engineer and the close. A false PASS costs more than the saved tokens, and nobody has measured the difference. This note does not claim any result about quality.
- Reasoning effort is a smaller lever than it looks: output is about 1 percent of the tokens (D), and the many tool turns dominate. Lowering the effort saves little on tokens unless it also makes the model use fewer tool calls, which is unmeasured.
- Also, the older models are marked "older generation" in the catalog; the catalog can change between CLI versions, so the list must be read again when the choice is made.
- Before any switch: record tokens per QA run (see "Token use"), then run the cheaper model on a few closed issues whose verdict is known, and compare verdicts. That needs Codex runs and quota, so it is a later task for the owner to approve.

## Hand-off to the fallback

What a failed Codex run leaves:

- The usage-limit message with the reset time ("You've hit your usage limit. Try again at ..."). `qa-codex` already stores the reset time (#203) and skips the Codex call until then, so the `UNAVAILABLE` run costs almost nothing.
- Before Codex starts, `qa-codex` has built: the GitHub state files (labels, timeline, blockers, sub-issues, created issues), the checkout at `HEAD`, the pre-step result (uv cache, frontend install) and the prompt. These are made outside Codex. The fallback `qa-engineer` can read the same GitHub state itself with `gh` (it has the network) and builds its own checkout.
- Nothing else. The limit is hit at the first request (the stub test of B: 0.9 seconds, no retry), so Codex has gathered no evidence and written no `-o` file. For a limit hit in the middle of a run, B shows the `-o` file is not written either, and `qa-codex` drops the stdout events. So no partial evidence reaches the fallback today.

Cost against saving:

- The fallback takes a median of 9.2 minutes against 3.6 for Codex, about 5.6 minutes more (A). Most of this is the fallback running the tests and reading the diff itself; the Codex run does the same with its own tool calls. A hand-off of the things in the list above (state files, comment block) would save only the reading of the issue and the comments: a few tool calls of the fallback, probably one or two minutes. That is a guess, not measured.
- Building the hand-off costs work in `qa-codex`, the hook for the fallback (the fallback is allowed only after `## QA: UNAVAILABLE`, guard G5) and the fallback launch text. The fallback must trust data that an earlier step wrote. That is a new place for wrong evidence, in the check that should be independent.
- The failed-run part is already solved by #203. The rest of the gap is the fallback being a Claude agent with a cold start, which a hand-off of the Codex leftovers does not remove.

Recommendation: do not build a hand-off of the failed run's leftovers. Only in one named case: if a later change keeps the `--json` events of a Codex run that stopped in the middle (limit hit after some work), the commands it ran and the results could go to the fallback as hints that it must verify. Today no such events are kept. A cheaper step with a similar effect: the orchestrator's fallback launch text names the issue's range and the labels so the fallback skips its first reads. That is a text change in a role file, not a hand-off.

## Decisions

The changes are in #224.

1. Token use: **apply** (record tokens), **do not apply** (split QA into sub-agents). Record: the usage numbers of each Codex QA run have no source today, and every other decision needs them. Files the record would touch: `scripts/codex_exec.py`, `scripts/qa-codex`, `scripts/run_report.py`, `docs/specs/agent-graph-kit.md`, `docs/specs/2026-10-19-run-report.md`, and the tests of these. Before it is built, one `codex exec --json` run must show which event carries the usage numbers (needs a small quota use, owner approval). Splitting: estimated saving of at most 20 percent, not proven, and it adds fixed cost and merge work.
2. Model by issue importance: **later**. A cheaper model for light issues may fit, but the quality risk is unmeasured, and the token numbers (decision 1) and a comparison on closed issues are needed first. The wider model rule for all roles is #66.
3. Hand-off to the fallback: **do not apply**. A failed run leaves no evidence, the reset-time skip (#203) already removes its cost, and a hand-off of the pre-built data saves about a minute against a new trust and maintenance cost. The one named case (partial `--json` events from a mid-run limit) depends on decision 1; revisit it after the record exists.
