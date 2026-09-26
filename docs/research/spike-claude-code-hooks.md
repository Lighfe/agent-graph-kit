# Spike S1: Claude Code hooks

Can Claude Code `PreToolUse` hooks carry the guarantees of spec section 5 (`docs/specs/2026-09-25-agent-graph-kit-v1.md`)? This file answers Q1–Q10 of issue #1 with evidence.

- Claude Code version: `2.1.266 (Claude Code)` (output of `claude --version`)
- Date of the experiments: 2026-09-26
- Documentation read on 2026-09-26: https://code.claude.com/docs/en/hooks (HOOKS), https://code.claude.com/docs/en/permissions (PERM), https://code.claude.com/docs/en/permission-modes (MODES), https://code.claude.com/docs/en/tools-reference (TOOLS)
- Where: a scratch git repo outside this repo (`$SCRATCH` below). No GitHub issue was touched. `gh` was a local stub on `PATH`.
- Redaction: `session_id`, `prompt_id`, `tool_use_id`, `agent_id` are replaced by placeholders. Absolute paths are replaced by `$SCRATCH` and `$HOME`.

## How the experiments ran

All experiments are headless sessions: `claude -p "<prompt>" --model <haiku|sonnet> --output-format stream-json --verbose [--permission-mode <mode>] [--allowedTools …]`, started with a clean environment in `$SCRATCH`. Multi-turn sessions (Q8) used `--input-format stream-json`, with the settings file changed between two user messages.

The scratch repo has:

- `.claude/settings.json` with one `PreToolUse` hook, matcher `Agent|Task|Bash`, command `python3 "$CLAUDE_PROJECT_DIR/hook.py"`, `timeout` 10 (changed per experiment, see each question).
- `hook.py`: appends `{"t": <epoch seconds>, "pid", "mode", "phase": "start"|"end", "event": <stdin JSON>}` to `hook.log`, then acts by the mode in the file `.hookmode`: `log` (exit 0, no output), `deny-json`, `deny-exit2`, `exit1`, `sleep5-marker`, `sleep3`, `sleep-long` (30 s), `marker` (write `marker.txt`, exit 0, no output), `allow-json`.
- Stubs that append `<epoch seconds> <name> ran with: <args>` to `calls.log`: `scripts/stub`, `scripts/qa-codex`, and `stubbin/gh` (first on `PATH`).
- Test subagents `.claude/agents/pm.md` and `.claude/agents/software-engineer.md` (tools: Bash; model: haiku). Each runs one command, `scripts/stub from-<name>`.

"The call ran" means that the stub wrote its line to `calls.log`.

Interactive sessions: I tried to drive an interactive session in `tmux`. The trust dialog appeared (see Q8). The next step, accepting the dialog by sending keys, was refused by the permission classifier of my own session, which does not allow a session to drive another interactive Claude session. So no answer below was confirmed interactively. Where the interactive behavior matters, the answer says so and relies on the documentation.

## Questions and answers

| # | Answer | Confirmed by |
|---|---|---|
| Q1 | Yes. Tool name `Agent`. Fields `tool_input.subagent_type` and `tool_input.prompt` (also `description`, `run_in_background`). If the caller omits `subagent_type` (a `general-purpose` launch), the field is missing | Headless experiment |
| Q2 | Yes. Both deny reliably. The JSON `permissionDecision: "deny"` with exit 0 gives Claude exactly the reason text. Exit 2 gives Claude the stderr text with a prefix: `PreToolUse:<tool> hook error: [<hook command>]: <stderr>` | Headless experiment |
| Q3 | Yes. Both deny forms work in `default`, `auto` and `bypassPermissions` mode, for `Agent` and `Bash` | Headless experiment (auto mode needs a Sonnet model; see evidence) |
| Q4 | Yes. `tool_input.command` is the exact command string. The hook fires for a `run_in_background: true` call too, and `tool_input.run_in_background` is `true`. A deny also stops the background call | Headless experiment |
| Q5 | Yes. The hook fires for tool calls inside subagents. The input then has `agent_type` (the subagent name, for example `pm`) and `agent_id`. A deny inside a subagent works | Headless experiment |
| Q6 | Yes. The call waits for the hook. A file written by the hook after `sleep 5` exists before the call starts, for `Bash` and for `Agent` | Headless experiment |
| Q7 | Exit 1: the call runs. `uv` cannot start (exit 127): the call runs. Timeout: the call runs, and the hook process is killed. The wrapper `… \|\| { echo "…" >&2; exit 2; }` turns exit 1 and a missing `uv` into a deny. It does not help on a timeout: the call still runs | Headless experiment |
| Q8 | Not a snapshot. An edit of `.claude/settings.json` applies at the next tool call of the running session, also when the session started with no hooks. Headless: no trust step (hooks run in a folder that was never trusted). Interactive: the documentation says hooks are held back until the workspace trust dialog is accepted; the dialog appeared, but accepting it could not be tested | Headless experiment; interactive part from the documentation only |
| Q9 | At the same time for `Agent` calls. Two `Agent` calls in one message: their hooks overlapped (in two runs, the second hook started 2.3 s and 0.5 s before the first one ended). Two `Bash` calls in one message: their hooks ran one after another, each after the previous command had run | Headless experiment (2 runs) |
| Q10 | Yes, the side effect has already happened. The hook runs before the permission rules. A `permissions.deny` rule, and the `-p` rule "no allow rule → not run", stop the call after the hook wrote its marker. `permissionDecision: "allow"` does not skip a deny rule, but it does skip the normal permission check: a command without an allow rule ran. The user's "No" at an interactive prompt could not be tested; the documentation says the hook runs before the prompt | Headless experiment; the interactive prompt from the documentation only |

## Evidence

### Q1: subagent launch input

Session: `claude -p` in `default` mode, main model haiku. Prompt: call the Agent tool in the foreground with `subagent_type "pm"` and the prompt `ROLE=pm ISSUE=1`. The hook logged (redacted):

```json
{
  "session_id": "<session-id>",
  "transcript_path": "$HOME/.claude/projects/<project>/<session-id>.jsonl",
  "cwd": "$SCRATCH",
  "prompt_id": "<prompt-id>",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Agent",
  "tool_input": {
    "description": "PM spike test with issue 1",
    "prompt": "ROLE=pm ISSUE=1",
    "subagent_type": "pm",
    "run_in_background": false
  },
  "tool_use_id": "<tool-use-id>"
}
```

- The main session's own calls have no `agent_type` and no `agent_id` field.
- In an earlier run the main session launched a subagent without `subagent_type`. The hook input then had only `description`, `prompt` and `run_in_background`. The session's `task_started` event named the type `general-purpose`.
- The session's final `result` event lists denied Agent calls under the old name `"tool_name": "Task"` (field `permission_denials`). The hook always saw `"tool_name": "Agent"`. The TOOLS page lists no tool named `Task`; the matcher `Agent|Task|Bash` is an exact-match list (HOOKS, "Matcher patterns"), so `Task` matches nothing and is harmless.

### Q2 and Q3: deny

Prompt: (1) call Agent with `subagent_type "pm"` and prompt `ROLE=pm ISSUE=1`, (2) run Bash `scripts/stub q2`, then quote each tool result. `--allowedTools 'Bash(scripts/stub:*)'`.

Hook output for `deny-json` (exit 0):

```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"G1: test"}}
```

Hook for `deny-exit2`: `print("G1: test via exit 2", file=sys.stderr); sys.exit(2)`.

| Hook | Mode (`permission_mode` in the hook input) | Tool result that Claude saw (both calls) | `calls.log` |
|---|---|---|---|
| `deny-json` | `default` | `G1: test` (is_error) | empty |
| `deny-json` | `auto` | `G1: test` (is_error) | empty |
| `deny-json` | `bypassPermissions` | `G1: test` (is_error) | empty |
| `deny-exit2` | `default` | `PreToolUse:Agent hook error: [python3 "$CLAUDE_PROJECT_DIR/hook.py"]: G1: test via exit 2` and the same with `PreToolUse:Bash` | empty |
| `deny-exit2` | `auto` | same as above | empty |
| `deny-exit2` | `bypassPermissions` | same as above | empty |

- Auto mode: with `--permission-mode auto --model haiku` the session silently started in `default` mode (the `init` event said `permissionMode: default`, and the hook input said `"permission_mode": "default"`). MODES says auto mode needs Sonnet 4.6+ or Opus 4.6+ and falls back to Manual otherwise. The auto rows above are from a rerun with `--model sonnet`, where the `init` event and the hook input both said `auto`.
- HOOKS confirms: exit 2 blocks even if the JSON says `allow`; for `deny`, `permissionDecisionReason` is shown to Claude.

### Q4: Bash command matching

Prompt: run three Bash calls exactly as written. `--allowedTools 'Bash(scripts/qa-codex:*)' 'Bash(gh issue close:*)'`, mode `default`, model sonnet. Hook log (`tool_input` only):

```text
{"command": "scripts/qa-codex ROLE=qa ISSUE=1", "description": "Run qa-codex script for issue 1"}
{"command": "gh issue close 1 --reason completed", "description": "Close GitHub issue 1"}
{"command": "scripts/qa-codex ROLE=qa ISSUE=1", "description": "Run qa-codex script for issue 1 in background", "run_in_background": true}
```

`calls.log` shows all three ran, each after its hook ended (`qa-codex` at +0.08 s, `gh` at +0.02 s, background `qa-codex` at +0.02 s after the hook's end entry).

Deny of a background call: with a hook that denies a `Bash` call when `run_in_background` is `true`, the call `scripts/qa-codex ROLE=qa ISSUE=1` with `run_in_background: true` got the tool result `G1: test deny (agent_type=None, bg=True)` and did not run.

The command string is what Claude wrote. It is not normalized, so the guard must parse it (as Task 5 plans).

### Q5: calls inside subagents

In the Q1 session, the `pm` subagent ran `scripts/stub from-pm`. The hook logged (redacted):

```json
{
  "session_id": "<session-id>",
  "transcript_path": "$HOME/.claude/projects/<project>/<session-id>.jsonl",
  "cwd": "$SCRATCH",
  "prompt_id": "<prompt-id>",
  "permission_mode": "default",
  "agent_id": "<agent-id>",
  "agent_type": "pm",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "scripts/stub from-pm", "description": "Run the stub script with from-pm argument"},
  "tool_use_id": "<tool-use-id>"
}
```

Deny inside a subagent: with a hook that denies `Bash` calls that have `agent_type`, the `pm` subagent's `scripts/stub from-pm` got the tool result `G1: test deny (agent_type=pm, bg=None)` and did not run.

### Q6: side effect before the call

Hook mode `sleep5-marker`: sleep 5 s, append a line to `marker.txt`, exit 0. Prompt: run Bash `scripts/stub q6`, then launch the `pm` subagent.

```text
hook.log   1790425929.705 start Bash scripts/stub q6
marker.txt 1790425934.706 hook side effect for Bash
calls.log  1790425934.817 stub ran with: q6
hook.log   1790425937.024 start Agent (pm)
marker.txt 1790425942.025 hook side effect for Agent
hook.log   1790425945.142 start Bash (agent_type=pm) scripts/stub from-pm   <- first tool call of the subagent
marker.txt 1790425950.142 hook side effect for Bash
calls.log  1790425950.181 stub ran with: from-pm
```

The Bash call started 0.11 s after the side effect. The subagent's first tool call came 3.1 s after the Agent hook's side effect.

### Q7: crash, missing `uv`, timeout, and the wrapper

Prompt: run Bash `scripts/stub q7-<case>` once and quote the result. The hook command was set per case. `W` is ` || { echo "guard hook failed: call denied" >&2; exit 2; }`.

| Case | Hook command (`timeout`) | Tool result | Call ran? |
|---|---|---|---|
| exit 1 | `python3 "$CLAUDE_PROJECT_DIR/hook.py"` with mode `exit1` (10 s) | `stub: q7-exit1` | yes |
| exit 1 + wrapper | same + `W` (10 s) | `PreToolUse:Bash hook error: [python3 "$CLAUDE_PROJECT_DIR/hook.py" \|\| { echo "guard hook failed: call denied" >&2; exit 2; }]: hook crashed on purpose` / `guard hook failed: call denied` | no |
| no `uv` | `PATH=/usr/bin:/bin; uv run --script "$CLAUDE_PROJECT_DIR/hook.py"` (10 s) | `stub: q7-nouv` | yes |
| no `uv` + wrapper | same + `W` (10 s) | `PreToolUse:Bash hook error: [PATH=/usr/bin:/bin; uv run --script … \|\| { … }]: /bin/sh: 1: uv: not found` / `guard hook failed: call denied` | no |
| timeout | `python3 …/hook.py` with mode `sleep-long` (30 s sleep, `timeout` 3) | `stub: q7-timeout` (ran 3.1 s after the hook started) | yes |
| timeout + wrapper | same + `W` (`timeout` 3) | `stub: q7-timeout-wrapped` (ran 3.1 s after the hook started) | yes |

- In both timeout cases the hook never wrote its `end` line, also 30 s later: Claude Code killed the process. The wrapper never ran.
- The hook command runs with `/bin/sh` (the error text says `/bin/sh: 1: uv: not found`; `/bin/sh` is `dash` on this machine). The wrapper must be POSIX `sh`.
- HOOKS says the same: exit codes other than 0 and 2 are non-blocking errors, a hook that cannot start (exit 127) is non-blocking, and "A timed-out command … hook doesn't block the tool call". The default `timeout` is 600 s.
- `uv run --script` on a PEP 723 script with `dependencies = []` started in 0.02–0.28 s here (`uv 0.10.5`).

### Q8: settings edits mid-session and trust

Multi-turn headless sessions (`--input-format stream-json`). Turn 1 runs `scripts/stub …-turn1`. Between the turns the driver replaces `.claude/settings.json`. Turn 2 runs `scripts/stub …-turn2`. Hook B is `echo "B: denied by the edited settings" >&2; exit 2`.

| Case | Before turn 1 | Change before turn 2 | Turn 2 result |
|---|---|---|---|
| 8a | logging hook A | settings replaced by hook B, 5 s wait | `PreToolUse:Bash hook error: [echo "B: denied by the edited settings" >&2; exit 2]: B: denied by the edited settings` (not run) |
| 8b | `{}` (no hooks) | settings replaced by hook A, 5 s wait | ran, and hook A logged the call (so a hook added mid-session runs) |
| 8c | logging hook A | settings replaced by hook B, 0 s wait | denied by hook B, as in 8a |
| 8d | hook B in `.claude/settings.json` and `{"disableAllHooks": true}` in `.claude/settings.local.json` | `settings.local.json` deleted, 3 s wait | turn 1 ran (hooks off); turn 2 denied by hook B |

Trust:

- Headless: the scratch folder was never trusted (`hasTrustDialogAccepted: false` in `~/.claude.json`), and all project hooks above ran. HOOKS, "Workspace trust": a `-p` session "treats the folder as trusted, so hooks committed in a repository's `.claude/settings.json` run".
- Interactive: HOOKS says Claude Code "holds back hooks from every settings file … until you accept the workspace trust dialog". Starting `claude` interactively in the scratch folder showed the dialog `Accessing workspace: … Quick safety check: Is this a project you created or one you trust? … ❯ No, exit / Yes, I trust this folder`. Accepting it and checking the hooks afterwards was not possible (see "How the experiments ran").
- HOOKS: "Direct edits to hooks in settings files are normally picked up automatically by the file watcher." `/hooks` shows the hooks read-only; there is no separate review step for changed hooks in the documentation.

### Q9: several guarded calls in one message

Hook mode `sleep3`: log start, sleep 3 s, log end. Model sonnet.

Run 1: one message with two Agent calls (`pm` with `ROLE=pm ISSUE=1`, `software-engineer` with `ROLE=engineer ISSUE=2`), a later message with two Bash calls.

```text
247.444 start Agent pm            (same assistant message)
248.169 start Agent software-engineer
250.444 end   Agent pm            <- overlap 2.3 s
251.169 end   Agent software-engineer
262.917 start Bash par-a          (same assistant message)
265.917 end   Bash par-a
265.936 calls.log: par-a ran
265.974 start Bash par-b          <- starts after par-a ran
268.975 end   Bash par-b
```

Run 2: one message with two Agent calls and one Bash call (`scripts/qa-codex ROLE=qa ISSUE=3`).

```text
308.490 start Agent pm
311.029 start Agent software-engineer
311.490 end   Agent pm            <- overlap 0.5 s
314.029 end   Agent software-engineer
320.991 start Bash qa-codex       <- after both subagents had finished
```

(Times are the last digits of epoch seconds.) The two subagents' own Bash hooks also overlapped (run 1: 252.811–255.812 and 253.246–256.247). HOOKS says "All matching hooks run in parallel" for the hooks of one event; it says nothing about the calls of one message.

So two guarded `Agent` launches in one message can both read the issue before either posts its launch comment. A `Bash` call in the same message ran only after the `Agent` calls.

### Q10: side effect without a call, and `allow`

Settings: `"permissions": {"deny": ["Bash(scripts/stub denied:*)"]}` and the hook in mode `marker` (write `marker.txt`, exit 0, no output). Model haiku, mode `default`.

| Case | Setup | Tool result | `marker.txt` | Call ran? |
|---|---|---|---|---|
| deny rule in project settings | `--allowedTools 'Bash(scripts/stub:*)'`, command `scripts/stub denied one` | `Permission to use Bash with command scripts/stub denied one has been denied.` | written | no |
| deny rule on the CLI | also `--disallowedTools 'Bash(scripts/stub denied:*)'`, command `scripts/stub denied two` | `Permission to use Bash with command scripts/stub denied two has been denied.` | written | no |
| no allow rule (`-p` cannot prompt) | no `--allowedTools`, command `scripts/stub no-allow-rule` | `This command requires approval` | written | no |
| hook `allow` vs deny rule | hook mode `allow-json`, `--disallowedTools 'Bash(scripts/stub denied:*)'`, command `scripts/stub denied three` | `Permission to use Bash with command scripts/stub denied three has been denied.` | – | no |
| hook `allow`, no allow rule | hook mode `allow-json`, no `--allowedTools`, command `scripts/stub no-allow-rule-but-hook-allows` | `stub: no-allow-rule-but-hook-allows` | – | **yes** |

- The deny rule in the project `.claude/settings.json` applied although the folder was not trusted. (PERM: in an untrusted `-p` folder, project `permissions.allow` rules are not used.)
- HOOKS, "PreToolUse decision control": `"allow"` "skips the permission prompt"; "Deny and ask rules are still evaluated regardless of what the hook returns". The experiment matches both parts.
- Interactive prompt: in an interactive session the "no allow rule" case shows a permission prompt instead. By the order above (hook first, then rules, then prompt), the side effect exists before the user answers. Not confirmed by experiment.

## Other observations

- The Agent tool result ends with `use SendMessage with to: '<agent-id>' … to continue this agent`. A `SendMessage` to a finished subagent continues that role without an `Agent` call, so no `Agent` hook runs and no launch comment is posted. Not tested further.
- The user's own plugins and skills load in the scratch sessions (one session first called the `Skill` tool). A hook with matcher `Agent|Bash` does not see `Skill` calls.

## Consequences for the plan

### Task 4 (#4): issue state and checks G1–G7

Holds. The module is pure and has no hook I/O. Nothing in S1 changes the checks.

Owner decision needed: no

### Task 5 (#5): guard hook entry point

Holds for the tool name, the fields and the deny format:

- `SUBAGENT_TOOLS = {"Agent", "Task"}` holds (`Task` is harmless). Read `tool_input.subagent_type` and `tool_input.prompt`. A missing `subagent_type` means `general-purpose`, which passes.
- The deny JSON with exit 0 works in all modes. "An allowed call produces no output" is right and must stay: `"allow"` would skip the user's permission check (Q10).
- A guard inside a subagent's call works the same way (`agent_type` is set).

Changes needed:

1. **Deadline inside the guard (Q7).** A hook killed at its timeout lets the call through, and the `|| exit 2` wrapper cannot catch it. The guard needs one overall deadline for all its work (the `gh` and `git` calls and the comment post) that ends clearly before the settings `timeout` (Task 7), and denies when it is reached. With 20 s per call and four calls (`gh issue view`, `git rev-parse`, `git status`, `gh issue comment`), the worst case is 80 s, close to the planned `timeout` of 90 s. Suggestion: an overall budget of about 60 s, and a settings `timeout` of 120 s. A hook that is still killed (for example a hung machine) fails open. Command hooks cannot prevent this.
2. **Lock around read-check-post (Q9).** Two `Agent` launches in one message run their hooks at the same time, so both can see "not pending" and both post a launch comment. The guard should hold an exclusive file lock (for example `fcntl.flock` on a file in the git dir) from reading the facts until the launch comment is posted. The second hook then reads the first launch comment and G1 denies it as pending. The wait counts against the deadline of change 1.

Owner decision needed: yes, only to accept that a guard killed at its timeout fails open (spec 5.6 says "A crash must never let the call through"; a timeout is not preventable with command hooks). The two changes themselves stay within spec section 5.

### Task 7 (#7): hook wiring and prose switch

Holds for the wiring:

- The matcher `Agent|Task|Bash` works (`Agent|Bash` is enough).
- The wrapper `… || { echo '…' >&2; exit 2; }` turns a crash and a missing `uv` into a deny. It must be POSIX `sh` (the command runs with `/bin/sh`). The planned smoke check (exit 2 without `uv`) matches this finding.
- Set `timeout` above the guard's own deadline (see Task 5, change 1).

Changes needed:

1. **Activation (Q8).** Hooks are not a session-start snapshot: when `.claude/settings.json` gets the hooks block, every running session in this repo uses it at its next tool call. This includes the orchestrator session that is running Task 7. Its next launch, the `qa-engineer` fallback without a launch line and without receipts, would then be denied, and Task 7 could not be closed under the old process. The plan's branch "if they apply at once, the owner activates them after the close" needs a mechanism. Tested option: before Task 7 starts, the owner puts `{"disableAllHooks": true}` into `.claude/settings.local.json` (local, not committed). After Task 7 is closed, the owner deletes it; the hooks apply from the next tool call (case 8d). `.claude/settings.local.json` is already in this repo's `.gitignore`, so the clean-tree check G1 does not see it.
2. **Launch comment without a launch (Q10).** The launch comment is posted before the permission rules and before any prompt. If the call is then stopped (a deny rule, the user says "No" at the prompt, or a `-p` run without an allow rule), the issue stays pending and the orchestrator escalates (spec 5.3 already covers this path). To avoid false escalations, Task 7 could add allow rules for the guarded calls, for example `Bash(scripts/qa-codex ROLE=qa ISSUE=*)` and `Bash(gh issue close *)`. Project allow rules only apply after the folder is trusted.
3. **Interactive check.** Trust and mid-session reload in an interactive session are confirmed from the documentation only. The owner's first interactive session after activation should confirm that a guarded call without a launch line is denied (the Task 7 smoke check done inside a session, not only on the command line).
4. **`SendMessage` (other observations).** Continuing a subagent with `SendMessage` bypasses the `Agent` hook and posts no launch comment. The orchestrator prose should say: start each role with a new launch, never continue it with `SendMessage`.

Owner decision needed: yes: the activation procedure (change 1), whether to add allow rules for the guarded calls (change 2), and the `SendMessage` rule (change 4).
