# Codex model choice with a subscription login

Date: 2026-10-21. Issue: #228. Codex CLI 0.153.4, logged in with a ChatGPT subscription (no API key).
This note changes no setting. The QA launcher still uses `QA_MODEL = "gpt-6-astra"` and `QA_EFFORT = "medium"`.

## Models and effort levels

Source of every row: real runs on 2026-10-21 (no Codex docs were used). Command form, the same flags as `BASE_FLAGS` in `scripts/codex_exec.py`, run in an empty directory:

```
echo "Reply with exactly: ok" | codex exec --json --ephemeral --ignore-user-config --disable hooks --disable apps --disable unbounded_connection_retries -c project_doc_max_bytes=0 -c skills.include_instructions=false --skip-git-repo-check -s read-only -m <model> -c 'model_reasoning_effort="<effort>"' -
```

| Model | Effort | Result |
|---|---|---|
| gpt-6-astra | low | accepted, answer `ok` |
| gpt-6-astra | medium | accepted, answer `ok` |
| gpt-6-astra | high | accepted, answer `ok` |
| gpt-6-astra | xhigh | accepted, answer `ok` |
| gpt-6-astra | minimal | rejected: "Unsupported value: 'minimal' is not supported with the 'gpt-6-astra' model. Supported values are: 'low', 'medium', 'high', 'xhigh', and 'max'." |
| gpt-5.5 | medium | rejected: "The 'gpt-5.5' model is not supported when using Codex with a ChatGPT account." |
| gpt-5.5-mini | medium | rejected, same message with 'gpt-5.5-mini' |
| gpt-5.4-mini | medium | rejected, same message with 'gpt-5.4-mini' |
| gpt-5-codex | medium | rejected, same message with 'gpt-5-codex' |
| bogus-model-x | medium | rejected, same message (a made-up name gets the same text) |

What this shows (backed by the runs above):

- With a subscription login, `gpt-6-astra` is the one model that was accepted. It takes the levels low, medium, high and xhigh. The rejection text for `minimal` lists `max` as supported too; `max` was not tried.
- Every other model name tried was rejected. The rejection text is the same for a real older name and for a made-up name, so a rejection does not prove the model exists. It only shows the name is not usable with this login.
- Not tried: other model names that may exist. No list of models was available from the CLI in these runs. So "gpt-6-astra is the only usable model" is only shown for the names above.
- A "mini" or cheaper model is therefore not selectable with the names tried. The only cheaper choice that was accepted is a lower effort (low) of the same model.

## Cost of a cheaper model

Source: the local token record `codex-qa-usage.jsonl` (written by #224). Numbers are quoted here because the file is local. 13 runs, all of one pair: model `gpt-6-astra`, effort `medium` (issues 224, 223 x2, 227 x3, 231, 151, 235, 150 x2, 236, 230).

| Field | Min | Median | Max | Sum |
|---|---|---|---|---|
| input tokens | 85,377 | 623,946 | 1,397,908 | 8,956,410 |
| cached input tokens | 58,624 | 589,952 | 1,341,568 | 8,444,928 |
| output tokens | 976 | 2,356 | 4,507 | 31,824 |

So a QA run reads a lot (about 94 % of input is cached) and writes little. Input size varies by a factor of 16 between runs.

The record cannot say whether a cheaper model or a lower effort changes the usage-limit cost. It has one model/effort pair only, so no pair can be compared (2 or more runs of each of 2 pairs are missing). Also missing: how the subscription counts tokens against its usage limit; the record has token counts, not limit use. One more datum from the trivial-prompt runs above: low, medium, high and xhigh all showed 11,647 input and 5 output tokens, and 0 reasoning tokens. For a trivial prompt, effort changed nothing in the counts. That says nothing about a real QA run.

What would be needed for a claim: the same issue checked by the QA launcher with at least two efforts (for example low and medium), 2 or more runs each, and the limit use read from the subscription page before and after.

## Decision

later

Reason: no cheaper model can be selected with a subscription login (only `gpt-6-astra` was accepted), and the only cheaper option, `low` effort, has no cost data and no quality data. Applying a change now would be a guess.

What must exist first: QA runs at `low` and `medium` on the same issues (2 or more each) with their token records, and a check that `low` finds the same FAIL cases as `medium`.

The rule the orchestrator would use once that exists: choose by the number of acceptance criteria in the issue. An issue with 3 or fewer criteria and lane `default` is light: run `gpt-6-astra` with effort `low`. All others stay at `medium`. Until the data above exists, every issue stays at `medium`.

## Link to #66

#66 (model and effort per role or task) covers the general question of who gets which model and effort, for the Claude roles. This note covers only what a subscription login can use for the Codex QA run and leaves the Claude roles to #66.
