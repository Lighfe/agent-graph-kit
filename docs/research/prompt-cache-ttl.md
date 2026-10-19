# Prompt cache TTL for subagents

Issue: #190. Question: should a role get a 1h prompt cache (`experimental: cacheTtl: 1h` in the agent frontmatter) instead of the default 5m for subagents? Result: no role gets `1h` now. No agent file changes.

## Measurement

Source: the subagent transcripts of Claude Code for this project (folder pattern `~/.claude/projects/<project-folder>/<session-id>/subagents/agent-*.jsonl`), read with `python3 scripts/run_report.py --comments <json> --issues 193,189,219,220 --transcripts ~/.claude/projects/<project-folder>`. Issues used: #193, #189, #219, #220, the four finished tasks of stage #222. Only counts are in this note, no transcript text. The folder is not committed.

Tokens per role and issue (input and output tokens are small and left out). The role name is the `ROLE=` value of the launch prompt; `qa` is the QA fallback `qa-engineer` plus other QA launches that wrote a transcript.

| Role | Issue | Cache creation | Cache read |
|---|---|---|---|
| `pm` | #193 | 41,843 | 527,517 |
| `pm` | #189 | 37,079 | 341,762 |
| `pm` | #219 | 30,256 | 274,320 |
| `pm` | #220 | 28,913 | 112,749 |
| `software-engineer` (`engineer`) | #193 | 62,831 | 630,726 |
| `software-engineer` (`engineer`) | #189 | 91,298 | 1,566,890 |
| `software-engineer` (`engineer`) | #219 | 30,576 | 315,939 |
| `software-engineer` (`engineer`) | #220 | 31,462 | 412,368 |
| `qa-engineer` (`qa`) | #193 | 104,999 | 5,483,472 |
| `qa-engineer` (`qa`) | #189 | 28,584 | 231,076 |
| `qa-engineer` (`qa`) | #219, #220 | no transcript | no transcript |
| `frontend-engineer` | all four | no transcript | no transcript |
| `planner` | all four | no transcript | no transcript |

Gaps between two API requests of one transcript (timestamps of the distinct assistant messages; a gap includes the tool time, so it is the time the cache has to survive):

| Role | Transcripts | Gaps | Longest gap | Gaps over 5 min |
|---|---|---|---|---|
| `pm` | 4 | 42 | 16 s | 0 |
| `software-engineer` | 4 | 50 | 280 s | 0 |
| `qa` | 3 | 86 | 376 s | 4 |
| `frontend-engineer`, `planner` | 0 | no transcript | no transcript | no transcript |

Limits: this stage had no QA FAIL, so no engineer continuation after a QA round was measured. No frontend task ran, so the Lovable wait (up to 10 min) was not measured. The quota effect on a subscription is not shown by these numbers (transcripts hold tokens, not quota).

## Decision

| Role | Decision | Reason |
|---|---|---|
| `pm` | `5m` | Longest gap 16 s, 0 gaps over 5 min. A cache never expires inside a launch |
| `software-engineer` | `5m` | Longest gap 280 s, 0 gaps over 5 min in 4 launches. A 1h write costs 2x base input, a 5m write 1.25x: on 30,000 to 91,000 cache creation tokens per launch, 1h adds about 0.75x of that to every launch to protect against a gap that did not happen. The longest gap is close to 5 min (280 s), so a long foreground test run can still miss; this is accepted, and re-measure when a gap over 5 min shows up |
| `qa-engineer` (fallback) | `5m` | 4 gaps over 5 min (longest 376 s) in 86 gaps, and the fallback is rare (Codex QA is the first choice). A miss costs one cache write of about 30,000 to 105,000 tokens; a 1h cache would cost more on every launch than 4 misses cost |
| `frontend-engineer` | `5m` | No transcript, so no number supports the 2x write cost. The Lovable `send_message` wait of up to 10 min is a known risk; re-measure after the first frontend stage |
| `planner` | `5m` | No transcript. Short launches in the stage review; no number for `1h` |

Is 1h worth it on a subscription? Not by these numbers: the engineer, the role with the most to gain, had no gap over 5 min, and the 1h write costs more on every launch. The quota effect on a subscription is unknown, the measurement does not show it. `1h` is ignored while the account uses usage credits, so there it would give nothing.

The global options (the project-wide TTL setting and the variables for all subagents or everything) are not favored by the numbers either, so no follow-up issue is filed.

## Other questions

- VS Code extension and `experimental.cacheTtl`: not checked. No role gets `1h`, so the question has no effect now, and this session has no VS Code extension to test.
- Two agent locations: `.claude/agents/` is the source; `python3 scripts/build_plugin.py` copies it to `plugin/agents/`, and `python3 scripts/build_plugin.py --check` lists any copy that differs.

## Default for the engineer after a QA FAIL

Launch a fresh engineer (with the QA comment in the prompt). Reason: a QA round takes minutes (QA gaps reach 376 s, and a QA launch lasts longer than the 5m cache), so a continued engineer meets a cold cache and writes its whole old context again at 1.25x, while a fresh engineer writes only a small new context (30,000 to 91,000 tokens cache creation per launch in this stage). The continuation with `SendMessage` stays for a miss (a launch that ended without a result), where the old context holds work not yet posted.
