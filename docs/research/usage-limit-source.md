# A local source for the plan usage limit in percent

Issue #281, spec `docs/specs/2026-11-06-visual-monitoring.md`, Part E.

Question: is the plan usage limit in percent (for example "62 % of the 5-hour limit used") available locally from Claude Code and from Codex, and how can a value reach the monitoring store?

"State dir" in this note means `$XDG_STATE_HOME`, else `~/.local/state` (the rule in `plugin/skills/run-record/run_record.py`).

Short answer:

- Claude Code: yes. The status-line input has `rate_limits.five_hour.used_percentage` and `rate_limits.seven_day.used_percentage`. The `claude -p --output-format stream-json --verbose` stream has a `rate_limit_event`.
- Codex: yes, but not in the `codex exec --json` stream that `qa-codex` saves. The value is in the `token_count` events of the session files in `~/.codex/sessions/` (not written for `--ephemeral` runs), and in the app-server request `account/rateLimits/read`.

All values in this note are synthetic examples, marked `(synthetic)`. No real usage value, account id, email, token or session id is written here.

## Claude Code

Version checked: Claude Code `2.1.303` (`claude --version`).

### Fields found

1. Status-line input (JSON on stdin of the `statusLine` command):
   - `rate_limits.five_hour.used_percentage`: percent of the 5-hour window used, 0 to 100
   - `rate_limits.five_hour.resets_at`: Unix epoch seconds when the window resets
   - `rate_limits.seven_day.used_percentage` and `rate_limits.seven_day.resets_at`: the same for the weekly window
   - `rate_limits.spend_limit.*`: only behind a Claude apps gateway with a spend limit; not used here
   - The object is present only for claude.ai Pro, Max and Ultra subscribers, only after the first API response of the session, and each window can be absent on its own
2. Print-mode stream (`claude -p --output-format stream-json --verbose`): an event with `"type": "rate_limit_event"` and the object `rate_limit_info`. Keys seen in the local run: `status`, `resetsAt`, `rateLimitType`, `utilization`, `overageStatus`, `overageDisabledReason`, `isUsingOverage`, `surpassedThreshold`, `overageEnabled`, and `unifiedWindows.five_hour.{utilization, resetsAt}` and `unifiedWindows.seven_day.{utilization, resetsAt}`. Here `utilization` is a fraction (usually 0 to 1), not a percent. The schema text in the binary marks `unifiedWindows` as `@internal`, so it can change without notice.

Not a source: the Claude Code transcripts (checked at intake, no such field), and the hook inputs (the `rate_limits` schema text in the binary is only in the status-line help text).

### How it was checked

- Official docs: https://code.claude.com/docs/en/statusline (section "Available data" and "Rate limit usage"). The page also says that the status line updates on events with a 300 ms debounce, and that the optional `refreshInterval` setting re-runs the command every N seconds.
- The schema text built into the installed binary: `strings` on `@anthropic-ai/claude-code/bin/claude.exe`, then a search for `rate_limits` and `rate_limit_event`. The status-line schema and the `rate_limit_event` schema (`rate_limit_info`) are both in the binary.
- One local run, from a scratch folder, keys and value types only (the values were not printed or saved):

  ```
  claude -p "Reply with the word ok." --model haiku --no-session-persistence \
    --output-format stream-json --verbose --settings '{"disableAllHooks":true}' < /dev/null \
    | jq -c 'select(.type=="rate_limit_event") | ...keys and types only...'
  ```

  Result: one `rate_limit_event` with the keys above.
- No status-line test was run. The status line runs only in an interactive session, so a test needs an interactive `claude --settings <file>` session in a terminal.
- Side effect of the local run: Claude Code itself refreshed its own cache files under `~/.claude/` during the run (credentials refresh, model catalog cache, plugin sync cache). `--no-session-persistence` keeps the transcript off disk, but no flag stops these cache writes. No settings file was changed. A parallel session was running at the same time, so not every write can be put down to this run.

### How a value can reach `<state dir>/agent-graph-kit/`

- File: `<state dir>/agent-graph-kit/usage-limits-claude.jsonl`
- Format: one JSON line per reading, appended. Example (synthetic):

  ```
  {"v":1,"time":"2026-01-01T10:00:00Z","provider":"claude","window":"five_hour","used_percent":62.0,"resets_at":"2026-01-01T14:00:00Z","source":"statusline"}
  ```

  One line per window (`five_hour`, `seven_day`). No session id, no transcript path, no account data in the line.
- What writes it, and when: a small script that the `statusLine` command calls. It reads the JSON from stdin, takes only `rate_limits.five_hour` and `rate_limits.seven_day`, and appends a line only when the rounded percent or the reset time changed since its last line (the status line runs often, so without this check the file grows on each update). It then prints the status line text as before. It writes nothing when `rate_limits` is absent.
- The loader (#282) reads the file like `run-record-limits.jsonl`, and the board (#286) shows the newest line per window, labelled as read from Claude Code.

### Proposed way

The status-line command above. It changes the owner's user settings: the `statusLine` entry in `~/.claude/settings.json` must call the script (or an existing status-line script must call it too). This is the owner's decision. This task did not make the change. The status line runs in the owner's interactive main session (for example the orchestrator session), so it gives readings while the loop runs; it gives no readings when no interactive session is open.

A way without a settings change, for comparison: a short `claude -p ... --output-format stream-json --verbose --no-session-persistence` probe that reads `rate_limit_event`. It costs a small model request each time, writes Claude Code cache files under `~/.claude/`, and reads `@internal` fields, so it is not the proposed way.

## Codex

Version checked: `codex-cli 0.153.4` (`codex --version`).

### Fields found

1. Session files (rollout files), `~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl`: lines with `"type": "event_msg"` and `payload.type == "token_count"` have `payload.rate_limits`:
   - `payload.rate_limits.primary.used_percent`: percent used, with `primary.window_minutes` (300, the 5-hour window) and `primary.resets_at` (Unix epoch seconds)
   - `payload.rate_limits.secondary.used_percent`: the same for `secondary.window_minutes` 10080 (the weekly window)
   - also `limit_id`, `plan_type`, `credits`, `rate_limit_reached_type`
2. App server (`codex app-server`, JSON-RPC over stdio): request `account/rateLimits/read`. The response has `rateLimits.primary.usedPercent`, `rateLimits.primary.windowDurationMins`, `rateLimits.primary.resetsAt`, the same under `secondary`, and `rateLimitsByLimitId`. The app server also sends the notification `account/rateLimits/updated`.

Not a source: the `codex exec --json` stream. Its event types are `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.started`, `item.updated`, `item.completed` and `error`; none has a rate limit field. The 36 streams that `qa-codex` saved in `<state dir>/agent-graph-kit/codex-runs/` have no `rate_limit`, `used_percent` or `usedPercent` text. `qa-codex` runs `codex exec` with `--ephemeral` (`scripts/codex_exec.py`), so its runs write no session file either.

### How it was checked

- Public source code of Codex:
  - https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs (`TokenCountEvent.rate_limits`, `RateLimitSnapshot`, `RateLimitWindow { used_percent, window_minutes, resets_at }`)
  - https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs (`ThreadEvent`, the `--json` event types)
  - https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/GetAccountRateLimitsResponse.ts and `RateLimitWindow.ts` in the same folder (the app-server response)
  - The source is the `main` branch at the time of the check, not the `0.153.4` tag.
- The installed binary: `strings` on the `codex` binary of `@openai/codex-linux-x64`. It holds `account/rateLimits/read`, `account/rateLimits/updated`, `usedPercent`, `windowDurationMins`, `rateLimitsByLimitId`, `used_percent` and `window_minutes`, so `0.153.4` has these names.
- Read only: the newest session file in `~/.codex/sessions/` (its `session_meta` says `cli_version` `0.153.4`). Only the key names, the value types and the window lengths were read, with `jq`; no usage value was printed or saved.
- No local Codex run: a Codex run writes its own state files under `~/.codex/` (log and state databases), which this task does not allow. So `account/rateLimits/read` was not called; its shape comes from the source and the binary.

### How a value can reach `<state dir>/agent-graph-kit/`

- File: `<state dir>/agent-graph-kit/usage-limits-codex.jsonl`
- Format: one JSON line per reading, appended, the same form as for Claude Code. Example (synthetic):

  ```
  {"v":1,"time":"2026-01-01T10:00:00Z","provider":"codex","window":"five_hour","used_percent":41.0,"resets_at":"2026-01-01T13:00:00Z","source":"app-server"}
  ```

  `window` is `five_hour` for `windowDurationMins` 300 and `seven_day` for 10080; another length is written as `<n>_minutes`. No account data, no plan id, no thread id in the line.
- What writes it, and when: `qa-codex`, after each Codex attempt (next to `record_usage` and `keep_stream`), starts `codex app-server`, sends `initialize`, then `account/rateLimits/read`, writes one line per window, and stops the app server. A failure writes nothing and changes no QA result. Second choice for the same file: the loader reads the newest `token_count` event of the newest session file in `~/.codex/sessions/`; this gives values only when the owner uses Codex in a non-ephemeral session, not from the loop.
- The app-server call writes Codex state files under `~/.codex/` on each call, like any Codex run. That is a change in the user's Codex home, but not a settings change.

### Proposed way

The `account/rateLimits/read` call from `qa-codex` after each Codex attempt, written to `usage-limits-codex.jsonl`. It needs no change of the owner's user settings. A follow-up task must first check the call with one local run (the app-server handshake and the response shape in `0.153.4`), because this note did not run it.
