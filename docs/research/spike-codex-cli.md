# Spike S2: Codex CLI

How does `codex exec` behave for `qa-codex` (#6) and `codex-review` (#8), and can it run a headless browser for the frontend lane (#9)? This file answers Q1–Q9 of issue #2 with evidence. Spec: `docs/specs/2026-09-25-agent-graph-kit-v1.md`, sections 6, 7, 8, 9.3 and 13.

- Codex CLI version: `codex-cli 0.153.4` (output of `codex --version`), installed with npm (native binary `x86_64-unknown-linux-musl`)
- OS and kernel: Ubuntu 24.04.5 LTS, `Linux 7.0.0-34-generic #34~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC x86_64` (`uname -srvmo`). `kernel.apparmor_restrict_unprivileged_userns = 0`, `/usr/bin/bwrap` present
- Date of the experiments: 2026-09-26
- Codex source read: tag `rust-v0.153.4` of `openai/codex` (commit `3d2ee51`), files named below as `SRC:<path>` under `codex-rs/`
- Docs read on 2026-09-26: https://learn.chatgpt.com/docs/config-file/config-reference (CONFIG), https://developers.openai.com/codex/guides/agents-md (AGENTSMD)
- Other tools: Node v22.17.0, Playwright 1.63.0 with `chromium_headless_shell-1243`, Python 3.12
- Redaction: session, thread and request IDs, `cf-ray` values and the GitHub account name are removed. `$HOME` is the home directory, `$SCRATCH` is the scratch directory of the experiments (outside this repo)

## How the experiments ran

- All work ran in `$SCRATCH`. Scratch git repos: `q1git` (empty commit), `proj` (a test project, see below), `q8` (marker files for Q8), `trustrepo`. `q1nogit` is not a git repo.
- `proj` has `app.py` (a tiny HTTP server on `127.0.0.1:<port>`, page title `S2 Demo Page`, one line of JavaScript changes the `h1` text), `test_app.py` (one `unittest` test), `title.mjs` (Playwright: open a URL headless, print `TITLE=<title> H1=<h1 text>`), `hold.mjs` and `hold.sh` (start the app and a browser and wait 600 s, for Q6). Playwright was installed with `npm i -D playwright` before any Codex run; the browsers were already in `$HOME/.cache/ms-playwright`.
- Auth: the owner's `$HOME/.codex` (ChatGPT login). No `auth.json` was copied. Every run against the real model used `--ephemeral` and `--ignore-user-config`. About 20 small model runs in total.
- Without the model (no quota):
  - `codex sandbox -P <profile> -C $SCRATCH/proj -- bash probe.sh <port>` runs a probe script in the same Linux sandbox that `codex exec` uses. Built-in profiles: `:read-only`, `:workspace`, `:danger-full-access`.
  - A stub Responses API server (`stub_server.py`, Python stdlib) on `127.0.0.1`, used through `-c model_provider=stub -c 'model_providers.stub={name="stub",base_url="http://127.0.0.1:<port>/v1",wire_api="responses"}' -m stub-model`. It returns 500, 502, 503, 429, a usage-limit 429, an in-stream rate limit, an in-stream quota error, or a given final message, and it saves the last request body. Answers based on it are marked "simulated with a stub server".
  - `codex debug prompt-input` renders the model-visible prompt (Q8).
  - Offline runs: `unshare -rn` (a new network namespace with only a down loopback).
- Side effects on `$HOME/.codex`: every Codex run writes its own state and log databases there. The runs also added one entry to `$HOME/.codex/config.toml` (see Q8, "trust entry"): `[projects."$SCRATCH/proj"] trust_level = "trusted"`. I removed that entry after the experiments; the rest of the file is unchanged. Processes that the experiments left running (Q6, `danger-full-access`) were killed.

## Questions and answers

| # | Answer | Confirmed by |
|---|---|---|
| Q1 | The `-o` file holds only the final message, exactly as the model sent it (`{"ok":true}`, 11 bytes, no newline). The API enforces the schema in strict mode: every object needs `additionalProperties: false` and every property in `required`; otherwise the run fails at once with exit 1 and `invalid_json_schema`. A mismatch could not be provoked with the real model (it returned valid JSON when asked for plain text and an extra field). Codex does **not** validate the output itself: with a stub that returns `this is not json`, exit was 0 and the `-o` file held `this is not json`. After a failed run (exit 1) or a killed run (SIGTERM, SIGKILL), the `-o` file is not touched: an old file stays in place, and without an old file there is no file. A turn that completes without a final message gives exit 0 and an **empty** `-o` file (an old file is overwritten) | Experiment (real API and stub server) |
| Q2 | Yes, `codex exec … -` reads the prompt from stdin. `-C <DIR>` (`--cd`) sets the working directory. In a git repo `--skip-git-repo-check` is not needed. Outside a git repo it is: without it the run stops at once with exit 1 and `Not inside a trusted directory and --skip-git-repo-check was not specified.` | Experiment; the check is only "is there a git root" (`SRC:exec/src/lib.rs`) |
| Q3 | See the table in the evidence. `read-only`: tests run; no file writes; no sockets (so no app, no `localhost`). `workspace-write`: writes in the working tree, `/tmp` and `$TMPDIR`, not in `.git` and not in `$HOME`; still no sockets (`socket()` fails with `EPERM`). `workspace-write` with `-c sandbox_workspace_write.network_access=true`: plus app, `localhost`, internet and a headless browser. `danger-full-access`: everything. A process started in the background by one Codex command did not survive into the next command, in every mode. A non-interactive run uses approval `never` (header line `approval: never`); a blocked command fails at once with its exit code, nothing waits | Experiment (`codex exec` and `codex sandbox`); approval default also from the source |
| Q4 | Yes. Playwright with Chromium (headless shell) ran in `codex exec` in two settings. Most restrictive: a permission profile that allows only `localhost`, which needs the **experimental** feature `network_proxy`: `--enable network_proxy -c 'permissions.qa={extends=":workspace",network={enabled=true,allow_local_binding=true,domains={"localhost"="allow","127.0.0.1"="allow"}}}' -c 'default_permissions="qa"'`. With stable features only: `-s workspace-write -c sandbox_workspace_write.network_access=true` (full internet). Not possible in `read-only` or plain `workspace-write` (Chromium aborts: `sandbox_host_linux.cc:41 Check failed: . shutdown: Operation not permitted`). No extra browser flag was needed: Playwright already starts `chrome-headless-shell` with `--no-sandbox`. The app and the browser must start in the same Codex command | Experiment |
| Q5 | Every error ends with exit 1, except "not installed" (exit 127 from a shell, `FileNotFoundError` from `subprocess.Popen`). The text is the last `ERROR: …` line on stderr (printed twice) in normal mode; with `--json` it is only on stdout, as `{"type":"turn.failed","error":{"message":…}}`, and stderr has only log lines. Codex retries by itself first: 500, other 5xx and 401 answers (up to 5 stream retries, each with up to 4 request retries), in-stream rate limits (5 retries) and connection errors; an overloaded 503 gets only the 4 request retries; a plain HTTP 429, the usage limit and the quota error are not retried. A network outage never ends by default ("Reconnecting... waiting for network", feature `unbounded_connection_retries`, on by default); with `--disable unbounded_connection_retries` it ends after about 4 minutes. Details in the Q5 evidence table | Experiment; server error, rate limit and usage limit simulated with a stub server; retry rules also from the source |
| Q6 | Yes in the sandboxed modes. After `killpg(<codex pgid>, SIGKILL)`, all children were gone after 3 s: the sandbox helper, `bwrap`, the shell, the dev server, `node` and all Chromium processes. Several children run in their own session and process group (the sandbox helper, `bwrap --new-session`, the command inside, Chromium), but `bwrap --die-with-parent` and the PID namespace take them down. In `danger-full-access` (no sandbox) the dev server, `node` and Chromium **survived** the kill (Chromium runs in its own session; the others were reparented to `systemd --user`) | Experiment (`ps -eo pid,ppid,pgid,sid,cmd` before and after) |
| Q7 | Yes, both. `codex exec --output-schema` accepted the exact `scripts/qa-result.schema.json` from #6 (including `enum` fields without `type`) and a draft `review.schema.json` built as in #8 step 3. Both returned valid JSON. No change needed | Experiment (real API) |
| Q8 | Loaded from the working directory: `AGENTS.md` (and `AGENTS.override.md`) from the git root down to the working directory; project skills in `.agents/skills/`; and, only if the project is trusted in the user config, `.codex/config.toml` and `.codex/hooks.json`. Loaded from `$CODEX_HOME`: `config.toml` (plugins, MCP servers, model, trust list), `AGENTS.md`/`AGENTS.override.md`, `skills/`, `hooks.json` (hooks run only with persisted hook trust or `--dangerously-bypass-hook-trust`), `.rules` files, and the ChatGPT apps connector. Switches: `--ignore-user-config` (user `config.toml`, and with it the trust list: the project counts as not in the trust list, so its `.codex/config.toml` and `.codex/hooks.json` are not loaded either; there is no separate flag for the project config), `-c project_doc_max_bytes=0` (project `AGENTS.md`), `-c skills.include_instructions=false` (all skills), `--disable hooks` (all hooks), `--disable apps` (apps connector tools), `--ignore-rules` (rules). No switch removes `$CODEX_HOME/AGENTS.md`; the owner's `$HOME/.codex` has none today. A run whose sandbox can write the working directory writes `trust_level = "trusted"` for the repo into `$CODEX_HOME/config.toml`, also with `--ignore-user-config` | Experiment (prompt rendering, stub request bodies, two real runs); `--ignore-rules` from the help text only (reason in the evidence); that `--ignore-user-config` drops the project config also from the source (`SRC:config/src/loader/mod.rs`); that no switch removes `$CODEX_HOME/AGENTS.md` was seen in every experiment and matches the source (`SRC:codex-home/src/instructions/mod.rs`) and AGENTSMD |
| Q9 | (a) Yes: in both Q4 settings Codex can create and change files in the working tree. It cannot write `.git`, so it cannot commit or move `HEAD` (`fatal: Unable to create '…/.git/index.lock': Read-only file system`). (b) With the localhost-only profile: no, the proxy blocks `api.github.com`. With `workspace-write` + network: yes, `gh auth status` succeeded with the owner's login from the keyring. Nothing in the sandbox limits it. Hiding the login through `-c 'shell_environment_policy.set={GH_CONFIG_DIR="/nonexistent-s2-gh", DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-s2-bus"}'` made `gh auth status` fail, but the model can undo environment variables, so this is not a boundary | Experiment |

## Evidence

### Q1: `--output-schema` and `-o`

Schema `s.json`: `{"type":"object","additionalProperties":false,"required":["ok"],"properties":{"ok":{"type":"boolean"}}}`.

Normal run (in `q1git`):

```text
$ echo 'Reply with ok=true. Do not run any command.' | codex exec --ignore-user-config --ephemeral --output-schema s.json -o out.json -
exit=0 (7.6 s)
stdout: {"ok":true}
stderr: OpenAI Codex v0.153.4 / workdir: $SCRATCH/q1git / model: gpt-6-astra / provider: openai / approval: never / sandbox: read-only / reasoning effort: none / … / user / Reply with ok=true. … / codex / {"ok":true} / tokens used / 13,883
out.json (od -c): {   "   o   k   "   :   t   r   u   e   }     (11 bytes, no newline)
```

The request carries the schema as `"text":{"format":{"type":"json_schema","strict":true,…,"name":"codex_output_schema"}}` (stub request log; `SRC:core/src/session/turn.rs` sets `output_schema_strict` for normal sessions).

Schema rules (real API):

| Schema | Exit | Error (stderr, after `ERROR: `) | `-o` |
|---|---|---|---|
| property `note` not in `required` | 1 (2.6 s) | `"code": "invalid_json_schema", "message": "Invalid schema for response_format 'codex_output_schema': In context=(), 'required' is required to be supplied and to be an array including every key in properties. Missing 'note'."` | old file unchanged |
| no `additionalProperties` | 1 (2.0 s) | `"code": "invalid_json_schema", "message": "… In context=(), 'additionalProperties' is required to be supplied and to be false."` | old file unchanged |

The error is a pretty-printed JSON block; its first line on stderr is `ERROR: {`. With `--json` it is the `turn.failed` message (a JSON string with `\n`).

Mismatch:

- Real model, prompt `Ignore any output format. Answer with the plain word hello and nothing else, not JSON. Also add a field "extra": 1.` → exit 0, `-o` = `{"ok":true}`. Strict mode did not let the model leave the schema.
- Stub server (simulated), final message `this is not json` → exit 0, `-o` = `this is not json`. Final message `{"ok":"yes","extra":1}` → exit 0, `-o` = `{"ok":"yes","extra":1}`. So `codex exec` does not check the output against the schema; only the API does.

`-o` after a failed or killed run:

| Run | Exit | `-o` before | `-o` after |
|---|---|---|---|
| offline (`unshare -rn`), killed by `timeout 600` (SIGTERM) | 124 | `{"old":"stale"}` | `{"old":"stale"}` (same mtime) |
| offline with `--disable unbounded_connection_retries` | 1 | `{"old":"stale"}` | `{"old":"stale"}` |
| every stub error run of Q5 | 1 | `stale` | `stale` |
| not logged in | 1 | no file | no file |
| Q6 runs, killed with SIGKILL | -9 | no file | no file |

Completed turn without a final message (stub: `response.created`, then `response.completed`, no message item; simulated with a stub server): exit 0, stdout empty, `-o` had `stale` before and **0 bytes** after, stderr `Warning: no last agent message; wrote empty content to $SCRATCH/out-nomsg.json`.

Source: `SRC:exec/src/event_processor_with_jsonl_output_tests.rs` has the test `failed_turn_does_not_overwrite_output_last_message_file`; `SRC:exec/src/event_processor.rs` writes the empty file.

### Q2: stdin, working directory, git check

- Every run above passed the prompt on stdin with `-`. The help says: "If not provided as an argument (or if `-` is used), instructions are read from stdin. If stdin is piped and a prompt is also provided, stdin is appended as a `<stdin>` block".
- `-C`: started in `q1nogit` with `-C $SCRATCH/q1git` → header `workdir: $SCRATCH/q1git`, exit 0, `{"ok":true}`.
- Outside a git repo, without the flag:

  ```text
  $ cd $SCRATCH/q1nogit && echo '…' | codex exec --ignore-user-config --ephemeral --output-schema s.json -o out.json -
  Not inside a trusted directory and --skip-git-repo-check was not specified.
  exit=1   (no model call, no -o file)
  ```

  With `--skip-git-repo-check` the run started (the offline runs of Q1/Q5 ran in `q1nogit`).

### Q3: what each sandbox allows

Prompt (for port `P`): run the tests `python3 -m unittest -q test_app`; start the app in the background `python3 app.py P > /tmp/s2-app-P.log 2>&1 &`; `echo hi > /tmp/s2-x-P`; `curl -sS -m 5 http://localhost:P/`; `node title.mjs http://localhost:P`; stop the app; one line per step. Runs: `codex exec --json --ignore-user-config --ephemeral -C $SCRATCH/proj <sandbox flags> -o … -`. The table lists the exit codes from the `command_execution` events of the JSON stream.

| Step | `-s read-only` | `-s workspace-write` | `-s workspace-write -c sandbox_workspace_write.network_access=true` | localhost-only profile (Q4) | `-s danger-full-access` |
|---|---|---|---|---|---|
| tests | exit 0 `OK` | exit 0 | exit 0 | exit 0 | exit 0 |
| start app (background) | redirect fails: `/tmp/s2-app-18301.log: Read-only file system` | exit 1; log: `PermissionError: [Errno 1] Operation not permitted` | exit 0 | exit 0 | exit 0 |
| write `/tmp/s2-x-P` | not run by Codex (see note) | exit 0, file exists | exit 0 | exit 0 | exit 0 |
| `curl localhost` | exit 7 | exit 7 | exit 7 | exit 7 | exit 7 |
| headless browser | exit 1 | exit 1 (`browserType.launch: Target page, context or browser has been closed`) | exit 1 | exit 1 | exit 1 |
| total time | 24.4 s | 26.8 s | 31.3 s | 31.2 s | 24.8 s |

`curl` failed in every mode (`curl: (7) Failed to connect to localhost port … after 0 ms`) because the app from the previous command was no longer running. The app log stayed empty, and no process was left after the runs. In the probe below the same app runs fine in `danger-full-access` inside one command. So **a background process does not survive the end of the Codex command that started it**; the app and the check must run in one command (Q4 does this).

Note on the `read-only` run: the final message said `3 failed: /bin/bash: line 1: /tmp/s2-x-18301: Read-only file system`, but the JSON stream has no command for step 3. The model reported an error line for a step it did not run.

Probe script in one command (`codex sandbox`, no model). `probe.sh` prints `<name> rc=<exit> :: <last output line>`:

| Capability | `-P :read-only` | `-P :workspace` | `:workspace` + `network={enabled=true}` | `-P :danger-full-access` |
|---|---|---|---|---|
| tests | rc=0 `OK` | rc=0 | rc=0 | rc=0 |
| write in repo | rc=2 `Read-only file system` | rc=0 | rc=0 | rc=0 |
| write `/tmp` | rc=2 | rc=0 | rc=0 | rc=0 |
| write `$HOME` | rc=2 | rc=2 `Read-only file system` | rc=2 | rc=0 |
| write `.git/` | – | rc=2 | rc=2 | rc=0 |
| bind a socket on `127.0.0.1` | `PermissionError: [Errno 1] Operation not permitted` | same | ok | ok |
| `curl localhost` (app in the same command) | rc=7 | rc=7 | rc=0 `200` | rc=0 `200` |
| `curl https://example.com` | rc=6 | rc=6 | rc=0 `200` | rc=0 `200` |
| `node title.mjs` | rc=1 | rc=1 | rc=0 `TITLE=S2 Demo Page H1=rendered by js` | rc=0 same |

- Writable roots of `workspace-write` are the working directory, `/tmp` and `$TMPDIR` (CONFIG: `sandbox_workspace_write.exclude_slash_tmp`, `exclude_tmpdir_env_var`). `.git` inside the working directory stays read-only (`bwrap … --tmpfs /tmp/.git --remount-ro …` in the Q6 process list).
- The profile `:workspace` + `network={enabled=true}` was given as `-c 'permissions.qa={extends=":workspace",network={enabled=true}}' -P qa`, because `codex sandbox -P` ignores `sandbox_workspace_write`. In `codex exec` the same effect comes from `-s workspace-write -c sandbox_workspace_write.network_access=true` (Q4 runs).
- Unit tests that write caches (for example `__pycache__`) still pass in `read-only`; a test runner that must write files would fail there.

Approval: the header of every non-interactive run said `approval: never`. `SRC:exec/src/lib.rs`: "Default to never ask for approvals in headless mode" (`approval_policy: Some(AskForApproval::Never)`), unless the approvals reviewer is `auto_review` (`--approve-for-me`). All blocked commands above returned an error at once; no run waited. The longest `read-only` run took 24.4 s for 5 commands.

### Q4: headless browser

Prompt: run exactly `python3 app.py P & APP=$!; sleep 1; node title.mjs http://localhost:P; RC=$?; kill $APP; exit $RC` once, answer with the `TITLE=` line.

| Sandbox flags | Command exit | Output | Run time |
|---|---|---|---|
| `-s workspace-write` | 1 | `[pid=16][err] [0926/151848.002906:FATAL:content/browser/sandbox_host_linux.cc:41] Check failed: . shutdown: Operation not permitted (1)`, then `kill: (3) - No such process` | 11.1 s |
| `--enable network_proxy -c 'permissions.qa={extends=":workspace",network={enabled=true,allow_local_binding=true,domains={"localhost"="allow","127.0.0.1"="allow"}}}' -c 'default_permissions="qa"'` | 0 | `127.0.0.1 - - [26/Sep/2026 15:18:59] "GET / HTTP/1.1" 200 -` / `TITLE=S2 Demo Page H1=rendered by js` | 10.7 s |
| `-s workspace-write -c sandbox_workspace_write.network_access=true` | 0 | `TITLE=S2 Demo Page H1=rendered by js` | 10.4 s |

(In the table the profile is named `qa`; in the experiments it was named `qalocal`.)

The localhost-only profile, checked with `codex sandbox` and in `codex exec` (Q9):

| Probe | with `--enable network_proxy` | same profile without `--enable network_proxy` |
|---|---|---|
| `curl https://example.com` (proxy from env) | `curl: (56) CONNECT tunnel failed, response 403`; Codex adds `Network access to "example.com" was blocked: domain is not on the allowlist for the current sandbox mode.` | `200` |
| `curl --noproxy '*' https://example.com` | `000` (failed) | `200` |
| Python `socket.create_connection((<example.com IP>, 443))` | `OSError: [Errno 101] Network is unreachable` | connected |
| app + `curl localhost` + browser | ok | ok |

So the `domains` list only limits traffic when the feature `network_proxy` is on. `codex features list` shows `network_proxy  experimental  false`. Without it, the profile is plain full network.

Chromium flags: the Playwright launch log shows that it already starts `chrome-headless-shell … --no-sandbox …`. No extra flag was added.

Before the run: Playwright and its browsers must already be installed. `$HOME` is read-only in every sandbox except `danger-full-access`, so `npx playwright install` cannot write `$HOME/.cache/ms-playwright`, and the localhost-only profile cannot reach the npm registry or the browser download server.

### Q5: errors

Stub runs (simulated with a stub server): `codex exec --ignore-user-config --ephemeral -C $SCRATCH/q1git -c model_provider=stub -c 'model_providers.stub={…}' -m stub-model --output-schema s.json -o out.json -`, default retry settings. "Requests" counts the POSTs to `/v1/responses` in the stub log. The last `ERROR:` line is printed twice on stderr.

| Error | How produced | Exit | Last line on stderr | Time | Codex retried |
|---|---|---|---|---|---|
| network error (default) | `unshare -rn` (offline), real provider | none, killed by `timeout 600` → 124 | `ERROR: Reconnecting... waiting for network` (repeating) | ≥ 600 s | without end: 5 s delay, doubled up to 60 s (`SRC:core/src/responses_retry.rs`) |
| network error, bounded | offline + `--disable unbounded_connection_retries` | 1 | `ERROR: Connection failed: error sending request` | 251.7 s | yes: `Reconnecting... 1/5` to `5/5` over WebSocket, then the same over HTTPS |
| server error 500 | stub `500` | 1 | `ERROR: We're currently experiencing high demand, which may cause temporary errors.` | 25.2 s | yes, 30 requests |
| other 5xx (502) | stub `502`, with `--json` | 1 | (`--json`) `unexpected status 502 Bad Gateway: synthetic bad gateway, url: http://127.0.0.1:<port>/v1/responses` | 25.6 s | yes, 30 requests |
| server overloaded 503 (`server_is_overloaded`) | stub `503` | 1 | `ERROR: Selected model is at capacity. Please try a different model.` | 4.5 s | 5 requests (request level only) |
| rate limit, HTTP 429 | stub `429` (`type: rate_limit_exceeded`) | 1 | `ERROR: exceeded retry limit, last status: 429 Too Many Requests` | 1.0 s | no, 1 request |
| rate limit in the stream | stub: `response.failed` with `code: rate_limit_exceeded`, "Please try again in 1s." | 1 | `ERROR: rate limit exceeded: Rate limit reached (synthetic). Please try again in 1s.` | 6.3 s | yes, 6 requests |
| usage limit | stub `429` with `type: usage_limit_reached`, `resets_at` | 1 | `ERROR: You've hit your usage limit. Try again at Sep 27th, 2026 11:06 AM.` | 0.9 s | no, 1 request |
| quota | stub: `response.failed` with `code: insufficient_quota` | 1 | `ERROR: Quota exceeded. Check your plan and billing details.` | 1.1 s | no, 1 request |
| not logged in | `CODEX_HOME=$SCRATCH/empty-codex-home` (empty), real provider | 1 | `ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses, cf-ray: <redacted>, request id: <redacted>` | 16.0 s | yes, 5 WebSocket + 5 HTTPS attempts |
| not installed | `PATH=/usr/bin:/bin` | 127 | `sh: 1: codex: not found` (shell), `env: 'codex': No such file or directory` (`env`) | at once | – |

- Not installed, from Python: `subprocess.Popen(['codex','exec','-'], env={'PATH':'/usr/bin:/bin'})` raises `FileNotFoundError [Errno 2] No such file or directory: 'codex'` (the plan's `run_codex` already catches it).
- Not logged in, cheaper check: `codex login status` prints `Not logged in` and exits 1 with the empty `CODEX_HOME` (0 s, no network). With the owner's home it prints `Logged in using ChatGPT` and exits 0.
- Usage limit, real texts from the source (`SRC:protocol/src/error.rs`). Not observed with the real backend: the owner's account had not reached a limit, and reaching one on purpose would use up the owner's quota. The stub run shows the path through the same code: `You've hit your usage limit. …` (several plan-specific endings), `You've hit your usage limit for <limit>. Switch to another model now, …`, `Your workspace is out of credits. …`, `You hit your spend cap …`, `Quota exceeded. Check your plan and billing details.`, `To use Codex with your ChatGPT plan, upgrade to Plus: …`. The mapping is in `SRC:codex-api/src/api_bridge.rs`: 429 + `usage_limit_reached` → usage limit, 429 + `usage_not_included` → upgrade text, any other 429 → `exceeded retry limit, last status: 429 …`, 500 → "high demand" text, 503 + `server_is_overloaded` → "at capacity", other statuses → `unexpected status <code> …`.
- Where the text is: normal mode, stderr only (stdout empty). Stderr also has the banner (`OpenAI Codex v0.153.4`, first line), **the prompt** (after the line `user`), `ERROR: Reconnecting... n/5` lines, and log lines like `2026-09-26T13:12:14.490070Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, …`. With `--json`, the error is on stdout: `{"type":"error","message":"Reconnecting... 1/5 (…)"}` for each retry, then `{"type":"error","message":"<text>"}` and `{"type":"turn.failed","error":{"message":"<text>"}}`; stderr has only the log lines; the prompt is not echoed. Example (usage limit, `--json`):

  ```text
  {"type":"thread.started","thread_id":"<thread-id>"}
  {"type":"turn.started"}
  {"type":"error","message":"You've hit your usage limit. Try again at Sep 27th, 2026 11:06 AM."}
  {"type":"turn.failed","error":{"message":"You've hit your usage limit. Try again at Sep 27th, 2026 11:06 AM."}}
  exit=1
  ```

- Retry settings (CONFIG, and the stub run): `model_providers.<id>.request_max_retries` (default 4) and `model_providers.<id>.stream_max_retries` (default 5). With both set to 0, the stub 500 run ended after 1.2 s with 1 request. They cannot be set for the built-in provider: `-c model_providers.openai.stream_max_retries=0` → exit 1, ``Error loading config.toml: model_providers contains reserved built-in provider IDs: `openai`. Built-in providers cannot be overridden.`` The unbounded network wait is switched off with `--disable unbounded_connection_retries` (`codex features list`: `unbounded_connection_retries  stable  true`).
- Which errors Codex itself treats as retryable: `SRC:protocol/src/error.rs` `is_retryable()` — yes for stream errors, in-stream rate limits, timeouts, unexpected statuses, connection failures, 500; no for usage limit, quota, usage not included, overload, the 429 "retry limit" error, invalid requests.

### Q6: killing the process group

Driver `q6_driver.py`: starts `codex exec --ignore-user-config --ephemeral -C $SCRATCH/proj <sandbox flags> -o … -` with `subprocess.Popen(..., start_new_session=True)` (as the plan's `run_codex`), prompt "Run exactly this one shell command once and wait for it to finish: bash hold.sh P". It waits until the browser runs, prints the process list, calls `os.killpg(<codex pid>, SIGKILL)`, waits 3 s and prints the list again. Columns `PID PPID PGID SID CMD`, commands shortened.

Localhost-only profile (Q4):

```text
codex pid=116943 pgid=116943 sid=116943
--- BEFORE kill
 116943  116941  116943  116943 node $HOME/.nvm/…/bin/codex exec --ignore-user-config --ephemeral -C $SCRATCH/proj --enable network_proxy …
 116955  116943  116943  116943 …/x86_64-unknown-linux-musl/bin/codex …
 117676  116955  117676  116943 …/x86_64-unknown-linux-musl/bin/codex …            <- own process group
 117702  116955  117702  117702 $HOME/.codex/tmp/arg0/codex-arg0…/codex-linux-sandbox --sandbox-policy-cwd $SCRATCH/proj …   <- own session
 117703  117702  117702  117702 codex-linux-sandbox …
 117704  117702  117702  117702 codex-linux-sandbox …
 117710  117702  117710  117702 bwrap --as-pid-1 --new-session --die-with-parent --ro-bind / / --dev /dev --bind /tmp /tmp --perms 555 --tmpfs /tmp/.git --remount-ro /tmp …
 117711  117710  117711  117711 codex-linux-sandbox … (inside bwrap)                <- own session
 117712  117711  117711  117711 bash hold.sh 18602
 117713  117712  117711  117711 python3 app.py 18602
 117766  117712  117711  117711 node hold.mjs http://localhost:18602
 117811  117766  117811  117811 $HOME/.cache/ms-playwright/chromium_headless_shell-1243/…/chrome-headless-shell --disable-field-trial-config …   <- own session
 117813  117811  117811  117811 chrome-headless-shell --type=zygote …
 117814  117811  117811  117811 chrome-headless-shell --type=zygote --no-sandbox …
 117829  117813  117811  117811 chrome-headless-shell --type=gpu-process …
 117834  117811  117811  117811 chrome-headless-shell --type=utility …
 117854  117814  117811  117811 chrome-headless-shell --type=renderer …
--- killpg(116943, SIGKILL); codex returncode=-9
--- AFTER kill (+3 s)
    PID    PPID    PGID     SID CMD
(none)
```

`-s workspace-write -c sandbox_workspace_write.network_access=true`: the same shape (sandbox helper in session 123182, `bwrap` in its own group, the command in session 123203, Chromium in session 123290). After the kill: no process left.

`-s danger-full-access` (no `bwrap`):

```text
--- BEFORE kill
 119886  119884  119886  119886 node …/codex exec … -s danger-full-access …
 119898  119886  119886  119886 …/bin/codex …
 120443  119898  120443  120443 bash hold.sh 18603                 <- own session
 120444  120443  120443  120443 python3 app.py 18603
 120513  120443  120443  120443 node hold.mjs http://localhost:18603
 120558  120513  120558  120558 chrome-headless-shell …           <- own session
 (5 more chrome-headless-shell processes in session 120558)
--- killpg(119886, SIGKILL); codex returncode=-9
--- AFTER kill (+3 s)
 120444    5904  120443  120443 python3 app.py 18603               <- reparented to systemd --user (PID 5904)
 120513    5904  120443  120443 node hold.mjs http://localhost:18603
 120558  120513  120558  120558 chrome-headless-shell …
 (the 5 other chrome-headless-shell processes, still running)
```

I killed these leftovers by hand. In the sandboxed modes the source explains the result: `SRC:linux-sandbox/src/bwrap.rs` passes `--die-with-parent` and `--unshare-pid`, and `SRC:linux-sandbox/src/linux_run_main.rs` sets `PR_SET_PDEATHSIG`.

### Q7: the schemas of #6 and #8

- `qa-result.schema.json`: copied exactly from the Interfaces section of #6. Prompt: two criteria about `app.py` and `test_app.py`, read the files, `tests.command` = `not run`, `verified_sha` = `git rev-parse HEAD`. Sandbox `read-only`. Exit 0. Output:

  ```json
  {"verdict":"pass","criteria":[{"id":1,"verdict":"pass","evidence":"app.py defines greet(name) returning f\"hello {name}\"."},{"id":2,"verdict":"pass","evidence":"test_app.py asserts greet(\"qa\") equals \"hello qa\"."}],"tests":{"command":"not run","result":"not run (spike)"},"verified_sha":"1d1e4d8062893bdfdaa6858645dbca7d60045049"}
  ```

  The SHA was the full `HEAD` of the scratch repo.
- Draft `review.schema.json` (#8 step 3: the fields of `DATA`, all required, `additionalProperties: false` on each object, `severity` enum `critical | high | medium | low`, top-level `description` "Adapted from the review schema of the openai-codex plugin for Claude Code."; `line_start`/`line_end` integer, `confidence` number, `next_steps` array of strings). It stays in `$SCRATCH` (#8 writes the real one). Prompt: review `app.py`, at most one finding. Exit 0. Output: `{"verdict":"approve","summary":"No concrete correctness risks found in app.py for its documented usage: python3 app.py PORT.","findings":[],"next_steps":[]}`.

### Q8: instruction and config files

Set-up in the scratch repo `q8`: `AGENTS.md` "Always start your answer with MARKER-A."; `.codex/config.toml` with `developer_instructions = "MARKER-PC: …"`; project skill `.agents/skills/marker-skill/SKILL.md` (description `MARKER-S …`); `.codex/hooks.json` with a `SessionStart` hook that touches a file. Scratch Codex home `q8home`: `AGENTS.md` "Always end your answer with MARKER-U."; `config.toml` with `developer_instructions = "MARKER-UC: …"`; skill `skills/home-skill` (`MARKER-HS`); `hooks.json` with a `SessionStart` hook.

Prompt rendering (`CODEX_HOME=$SCRATCH/q8home codex debug prompt-input hi`, markers found in the output):

| Settings | Markers in the prompt |
|---|---|
| default (project not in the trust list) | A, HS, S, U, UC |
| project trusted in `q8home/config.toml` | A, HS, **PC**, S, U (project config replaces UC) |
| project `untrusted` in `q8home/config.toml` | HS, S, U, UC (no `AGENTS.md`, no project config; the project skill stays) |
| `-c project_doc_max_bytes=0` | HS, S, U, UC |
| `-c skills.include_instructions=false` | A, U, UC |
| `-c 'developer_instructions=""'` | A, HS, S, U |
| `-c projects."<q8>".trust_level=…` on the command line | no effect (same as default) |

`codex exec` through the stub server (markers in the saved request body; `CODEX_HOME=$SCRATCH/q8home`):

| Flags | Markers |
|---|---|
| none | A, HS, S, U, UC |
| `--ignore-user-config` | A, HS, S, U |
| `--ignore-user-config -c project_doc_max_bytes=0` | HS, S, U |
| `--ignore-user-config -c project_doc_max_bytes=0 -c skills.include_instructions=false` | U |

`AGENTS.md` goes into a `user` message, skills and developer instructions into a `developer` message. The user `AGENTS.md` (U) stays in every case: `SRC:codex-home/src/instructions/mod.rs` always reads `AGENTS.override.md`, then `AGENTS.md` from `$CODEX_HOME`, with no switch. AGENTSMD says the same ("The global file lives at ~/.codex/AGENTS.md (or $CODEX_HOME/AGENTS.md …)"). The owner's `$HOME/.codex` has no `AGENTS.md`, no `AGENTS.override.md`, no `hooks.json` and no `rules` today.

Real model (`codex exec --ignore-user-config --ephemeral -C $SCRATCH/q8`, owner's home, prompt "What is 2+2? Answer in one short line."):

- no extra flags → `MARKER-A 2+2=4.`
- with `-c project_doc_max_bytes=0 -c skills.include_instructions=false --disable hooks --disable apps` → `2 + 2 = 4.`

Hooks (stub server, `SessionStart` hooks in `q8home/hooks.json` and `q8/.codex/hooks.json`):

| Flags | Hooks that ran |
|---|---|
| none | none (no persisted hook trust) |
| `--dangerously-bypass-hook-trust` | user hook |
| `--dangerously-bypass-hook-trust --ignore-user-config` | user hook |
| project trusted + `--dangerously-bypass-hook-trust` | user hook and project hook |
| project trusted + `--dangerously-bypass-hook-trust --disable hooks` | none |
| project trusted, no bypass | none |

Project config of a trusted project (added after the QA review of issue #2; stub server, no model run). `CODEX_HOME=$SCRATCH/q8home`, whose `config.toml` holds the `MARKER-UC` line and `[projects."$SCRATCH/q8"] trust_level = "trusted"`; user and project `SessionStart` hooks as above. Script `q8pc.sh`: `echo hi | codex exec -s read-only --ephemeral -C $SCRATCH/q8 -c model_provider=stub -c 'model_providers.stub={…}' -m stub-model <flags> -`, markers from the saved request body, hooks from the files they touch:

| Flags | Exit | Markers | Hooks that ran |
|---|---|---|---|
| none | 0 | A, HS, **PC**, S, U | none |
| `--ignore-user-config` | 0 | A, HS, S, U | none |
| `--dangerously-bypass-hook-trust` | 0 | A, HS, **PC**, S, U | user and project hook |
| `--dangerously-bypass-hook-trust --ignore-user-config` | 0 | A, HS, S, U | user hook |
| `--ignore-user-config --disable hooks --disable apps -c project_doc_max_bytes=0 -c skills.include_instructions=false` (the #6 flags) | 0 | U | none |

So `--ignore-user-config` switches off the project `.codex/config.toml` and `.codex/hooks.json` of a trusted project: the trust list lives in the user `config.toml`, and without it the project counts as not in the trust list. `AGENTS.md` (A) still loads, as in the default row of the first table; only an explicit `untrusted` entry drops it. Source: `load_user_config_layer` returns an empty layer when `ignore_user_config` is set, and the project layers are added only when `project_trust_context` finds the project trusted in the merged config (`SRC:config/src/loader/mod.rs`). There is no separate flag: the loader has an `ignore_project_config` override (`SRC:config/src/state.rs`), but `codex exec` does not expose it. A trust entry in the system config `/etc/codex/config.toml` would still count, because `--ignore-user-config` drops only the user layer (source only; this machine has no `/etc/codex`).

What the owner's home adds (stub server, `-C $SCRATCH/proj`, names from the request body):

| Flags | Skills listed | Tools |
|---|---|---|
| none | 13 (for example `documents:documents`, `pdf:pdf`, `find-skills`, `imagegen`) | `exec_command`, `write_stdin`, MCP resource tools, `request_user_input`, `request_plugin_install`, `view_image`, `multi_agent_v1`, `mcp__cua_repl`, `mcp__node_repl`, five `mcp__codex_apps__*` tools, `web_search` |
| `--ignore-user-config` | 6 (`find-skills`, `imagegen`, `openai-docs`, `plugin-creator`, `skill-creator`, `skill-installer`) | the same without `mcp__cua_repl` and `mcp__node_repl` |
| `--ignore-user-config -c skills.include_instructions=false -c project_doc_max_bytes=0 --disable apps` | 0 | `exec_command`, `write_stdin`, `request_user_input`, `view_image`, `multi_agent_v1`, `web_search` |

The `mcp__codex_apps__*` tools come from the ChatGPT apps connector (feature `apps`, on by default); the offline run tried to reach `https://chatgpt.com/backend-api/ps/mcp` even with `--ignore-user-config`. `web_search` is a tool of the model provider; it is not a command in the sandbox, so the sandbox network setting does not apply to it (not tested further).

Rules: `--ignore-rules` "Do not load user or project execpolicy `.rules` files" (help text only). Not tested: a rule only acts on a command that the model runs, so a test needs an extra model run with a rule fixture, and the owner's home has no rules today.

For this repo: `AGENTS.md` (orchestrator commands such as `gh issue close`) is loaded by default, and so are the project skills in `.agents/skills/`. `-c project_doc_max_bytes=0` and `-c skills.include_instructions=false` remove both.

Trust entry: `SRC:app-server/src/request_processors/thread_processor.rs` persists `trust_level = "trusted"` for the git root when a thread starts with a working directory, the project has no trust level yet, and the sandbox can write the working directory. Stub runs in the fresh repo `trustrepo` with `CODEX_HOME=$SCRATCH/q8home`:

| Flags | Entry added to `$CODEX_HOME/config.toml` |
|---|---|
| `-s read-only` | none |
| `-s workspace-write` | `[projects."$SCRATCH/trustrepo"] trust_level = "trusted"` |
| `-s workspace-write --ignore-user-config` | the same |
| localhost-only profile | the same |
| `-s workspace-write -c projects."…".trust_level="untrusted"` | the same |

This is how `$SCRATCH/proj` got into the owner's `config.toml` (see "How the experiments ran").

### Q9: repo changes and GitHub

Prompt in `proj`: `echo q9 > q9.txt`; `gh auth status`; `curl -sS -m 8 https://example.com …`; `git add q9.txt && git … commit -m q9`. Output lines are redacted (account name).

| Step | localhost-only profile | `-s workspace-write -c sandbox_workspace_write.network_access=true` |
|---|---|---|
| `echo q9 > q9.txt` | exit 0; `git status` after the run: `?? q9.txt` | exit 0; `?? q9.txt` |
| `gh auth status` | exit -1: `X Failed to log in to github.com account <redacted> (default)`; Codex: `Network access to "api.github.com" was blocked: domain is not on the allowlist for the current sandbox mode.` | exit 0: `✓ Logged in to github.com account <redacted> (keyring)` |
| `curl https://example.com` | exit -1, `curl: (56) CONNECT tunnel failed, response 403` | exit 0, `200` |
| `git commit` | `fatal: Unable to create '$SCRATCH/proj/.git/index.lock': Read-only file system` | same |
| `git log` after the run | `1d1e4d8 scratch project` (unchanged) | unchanged |

With `codex sandbox` the same: in `:workspace` + network, `gh api -X GET /rate_limit --jq .resources.core.limit` printed `5000` (an authenticated rate limit); in the localhost-only profile it failed with `Forbidden`.

Hiding the login (`-s workspace-write -c sandbox_workspace_write.network_access=true -c 'shell_environment_policy.set={GH_CONFIG_DIR="/nonexistent-s2-gh", DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-s2-bus"}'`): `gh auth status` exit 1, `You are not logged into any GitHub hosts. To log in, run: gh auth login`. The files in `$HOME/.config/gh` and the real D-Bus socket are still readable in the sandbox, so a command that sets the variables back would reach the login again (not tested, because the only `gh` call allowed in this spike is the read-only probe).

## Error table

For `classify_failure` in `scripts/codex_exec.py` (#6). Apply the rows in this order; the first match wins; no match is `unknown`. Each regex is applied with `re.MULTILINE`. It matches the message with or without the `ERROR: ` prefix, so it works on the `turn.failed` message of `--json` (recommended, see Consequences) and on stderr lines. The anchor `^` keeps it off `Reconnecting...` lines and log lines. The example lines are real output with IDs redacted, or stub output; the fake `codex` of #6 can print them.

| Row | Error | Status (#6) | Exit code | Example error line | Regex |
|---|---|---|---|---|---|
| E1 | not installed | `unavailable` | 127 | `sh: 1: codex: not found` | `codex'?: (?:(?:command )?not found\|No such file or directory)\|No such file or directory: 'codex'` |
| E2 | not logged in | `unavailable` | 1 | `ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses, cf-ray: <redacted>, request id: <redacted>` | `^(?:ERROR: )?(?:unexpected status 401 Unauthorized\|Not logged in$)` |
| E3 | usage limit (also quota, spend cap, credits, plan) | `unavailable` | 1 | `ERROR: You've hit your usage limit. Try again at Sep 27th, 2026 11:06 AM.` | `^(?:ERROR: )?(?:You've hit your usage limit\|You hit your spend cap\|Your workspace is out of credits\|Quota exceeded\. Check your plan\|To use Codex with your ChatGPT plan)` |
| E4 | rate limit (HTTP 429) | `transient` | 1 | `ERROR: exceeded retry limit, last status: 429 Too Many Requests` | `^(?:ERROR: )?exceeded retry limit, last status: 429` |
| E5 | rate limit (in the stream) | `transient` | 1 | `ERROR: rate limit exceeded: Rate limit reached (synthetic). Please try again in 1s.` | `^(?:ERROR: )?rate limit exceeded: ` |
| E6 | server error (500) | `transient` | 1 | `ERROR: We're currently experiencing high demand, which may cause temporary errors.` | `^(?:ERROR: )?We're currently experiencing high demand` |
| E7 | server overloaded (503) | `transient` | 1 | `ERROR: Selected model is at capacity. Please try a different model.` | `^(?:ERROR: )?Selected model is at capacity` |
| E8 | other 5xx | `transient` | 1 | `ERROR: unexpected status 502 Bad Gateway: synthetic bad gateway, url: http://127.0.0.1:<port>/v1/responses` | `^(?:ERROR: )?(?:unexpected status 5\d\d\|exceeded retry limit, last status: 5\d\d)` |
| E9 | network error (only with `--disable unbounded_connection_retries`; without it, a network outage is a timeout) | `transient` | 1 | `ERROR: Connection failed: error sending request` | `^(?:ERROR: )?(?:Connection failed: \|stream disconnected before completion: )` |
| E10 | anything else, for example an invalid schema | `unknown` | 1 | `ERROR: {"type": "error", "error": {"type": "invalid_request_error", "code": "invalid_json_schema"}}` | – (no row matches) |

(`\|` is a `|` in the regex; it is escaped only for the Markdown table.)

### Regex check

`regex_check.py` (in `$SCRATCH`) holds the table above as a Python list and classifies each example line, first match wins. It also checks other "not installed" forms (the `env` and Python forms from Q5, and the `bash` form), which must match E1, and four real noise lines that must match no row.

```python
import re
TABLE = [  # (row, status, exit code, example line, regex) in table order
    ("E1 not installed", "unavailable", 127, "sh: 1: codex: not found",
     r"codex'?: (?:(?:command )?not found|No such file or directory)|No such file or directory: 'codex'"),
    ("E2 not logged in", "unavailable", 1, "ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses, cf-ray: <redacted>, request id: <redacted>",
     r"^(?:ERROR: )?(?:unexpected status 401 Unauthorized|Not logged in$)"),
    ("E3 usage limit", "unavailable", 1, "ERROR: You've hit your usage limit. Try again at Sep 27th, 2026 11:06 AM.",
     r"^(?:ERROR: )?(?:You've hit your usage limit|You hit your spend cap|Your workspace is out of credits|Quota exceeded\. Check your plan|To use Codex with your ChatGPT plan)"),
    ("E4 rate limit (HTTP 429)", "transient", 1, "ERROR: exceeded retry limit, last status: 429 Too Many Requests",
     r"^(?:ERROR: )?exceeded retry limit, last status: 429"),
    ("E5 rate limit (in stream)", "transient", 1, "ERROR: rate limit exceeded: Rate limit reached (synthetic). Please try again in 1s.",
     r"^(?:ERROR: )?rate limit exceeded: "),
    ("E6 server error (500)", "transient", 1, "ERROR: We're currently experiencing high demand, which may cause temporary errors.",
     r"^(?:ERROR: )?We're currently experiencing high demand"),
    ("E7 server overloaded (503)", "transient", 1, "ERROR: Selected model is at capacity. Please try a different model.",
     r"^(?:ERROR: )?Selected model is at capacity"),
    ("E8 other 5xx", "transient", 1, "ERROR: unexpected status 502 Bad Gateway: synthetic bad gateway, url: http://127.0.0.1:<port>/v1/responses",
     r"^(?:ERROR: )?(?:unexpected status 5\d\d|exceeded retry limit, last status: 5\d\d)"),
    ("E9 network error", "transient", 1, "ERROR: Connection failed: error sending request",
     r"^(?:ERROR: )?(?:Connection failed: |stream disconnected before completion: )"),
    ("E10 anything else", "unknown", 1, 'ERROR: {"type": "error", "error": {"type": "invalid_request_error", "code": "invalid_json_schema"}}',
     None),
]
E1_FORMS = [  # other "not installed" forms (env and Python from Q5, plus bash), must match E1
    "env: 'codex': No such file or directory",
    "bash: codex: command not found",
    "[Errno 2] No such file or directory: 'codex'",
]
NOISE = [  # lines from real output that must match no row
    "ERROR: Reconnecting... 2/5",
    "Reconnecting... 1/5 (unexpected status 502 Bad Gateway: synthetic bad gateway, url: http://127.0.0.1:<port>/v1/responses)",
    "2026-09-26T13:12:14.490070Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://api.openai.com/v1/responses",
    "warning: Falling back from WebSockets to HTTPS transport. unexpected status 401 Unauthorized: Missing bearer or basic authentication in header",
]
PATTERNS = [(row, status, re.compile(rx, re.MULTILINE)) for row, status, _, _, rx in TABLE if rx]

def classify(text):
    for row, status, rx in PATTERNS:
        if rx.search(text):
            return row, status
    return "E10 anything else", "unknown"

ok = True
for row, status, code, line, _ in TABLE:
    got_row, got_status = classify(line)
    good = (got_row, got_status) == (row, status)
    ok &= good
    print(f"{'OK  ' if good else 'FAIL'} {row:28} -> {got_row:28} {got_status}")
for line in E1_FORMS:
    got_row, got_status = classify(line)
    good = got_row == "E1 not installed"
    ok &= good
    print(f"{'OK  ' if good else 'FAIL'} E1 form: {line[:58]:58} -> {got_row}")
for line in NOISE:
    got_row, got_status = classify(line)
    good = got_status == "unknown"
    ok &= good
    print(f"{'OK  ' if good else 'FAIL'} noise: {line[:60]:60} -> {got_status}")
print("ALL OK" if ok else "MISMATCH")
```

```text
$ python3 regex_check.py; echo "exit=$?"
OK   E1 not installed             -> E1 not installed             unavailable
OK   E2 not logged in             -> E2 not logged in             unavailable
OK   E3 usage limit               -> E3 usage limit               unavailable
OK   E4 rate limit (HTTP 429)     -> E4 rate limit (HTTP 429)     transient
OK   E5 rate limit (in stream)    -> E5 rate limit (in stream)    transient
OK   E6 server error (500)        -> E6 server error (500)        transient
OK   E7 server overloaded (503)   -> E7 server overloaded (503)   transient
OK   E8 other 5xx                 -> E8 other 5xx                 transient
OK   E9 network error             -> E9 network error             transient
OK   E10 anything else            -> E10 anything else            unknown
OK   E1 form: env: 'codex': No such file or directory                    -> E1 not installed
OK   E1 form: bash: codex: command not found                             -> E1 not installed
OK   E1 form: [Errno 2] No such file or directory: 'codex'               -> E1 not installed
OK   noise: ERROR: Reconnecting... 2/5                                   -> unknown
OK   noise: Reconnecting... 1/5 (unexpected status 502 Bad Gateway: synt -> unknown
OK   noise: 2026-09-26T13:12:14.490070Z ERROR codex_api::endpoint::respo -> unknown
OK   noise: warning: Falling back from WebSockets to HTTPS transport. un -> unknown
ALL OK
exit=0
```

The same `classify` on the full captured stderr of the Q5 runs:

```text
nologin.stderr         -> ('E2 not logged in', 'unavailable')
err-usage.stderr       -> ('E3 usage limit', 'unavailable')
err-quota.stderr       -> ('E3 usage limit', 'unavailable')
err-429.stderr         -> ('E4 rate limit (HTTP 429)', 'transient')
err-streamrl.stderr    -> ('E5 rate limit (in stream)', 'transient')
err-500.stderr         -> ('E6 server error (500)', 'transient')
err-503.stderr         -> ('E7 server overloaded (503)', 'transient')
q5-net2.stderr         -> ('E9 network error', 'transient')
q1-s-noadd.stderr      -> ('E10 anything else', 'unknown')
```

Limit: in normal mode stderr also contains the prompt. A QA prompt with a criterion line that starts with one of these texts (for example this issue's own text) could match a row. With `--json` the prompt is not in the output.

## Other observations

- Default model and effort: the header said `model: gpt-6-astra` and `reasoning effort: none`, with and without `--ignore-user-config` (the owner's config sets neither). `-c model_reasoning_effort="high"` changed the header to `reasoning effort: high`.
- The final message can report a step that was not run (Q3, `read-only`). The `--json` event stream shows the commands and their exit codes; it is better evidence than the final message.
- `--json` and `-o` work together: the `-o` file is written as without `--json`.
- Offline, the header and the run start even without network. Log lines from the model catalog refresh (`failed to refresh available models: timeout waiting for child process to exit`) appear on stderr in normal runs too.

## Consequences for the plan

### #6 (qa-codex)

Holds:

- `--output-schema` + `-o` + prompt on stdin (`-`), `-C <repo>`, no `--skip-git-repo-check` in a git repo (Q1, Q2).
- `scripts/qa-result.schema.json` as written in the Interfaces section (Q7).
- A fresh temporary `-o` path per run, read only after exit 0 (Q1: old files survive failed and killed runs).
- The Python checks stay necessary: `codex exec` does not validate the output, and an exit 0 can come with an empty file (Q1, stub).
- `start_new_session=True` + `os.killpg(..., SIGKILL)` on timeout stops all children in the sandboxed modes (Q6).
- `FileNotFoundError` → `unavailable` (Q5).

Changes needed:

1. **`QA_SANDBOX` is a list of flags, not a mode name.** `run_codex(prompt, *, schema, sandbox_args: list[str], timeout_s, cwd)`; #8 passes `["-s", "read-only"]`. Two choices for QA (owner decision, see below):
   - most restrictive, with the experimental feature `network_proxy`: `QA_SANDBOX = ["--enable", "network_proxy", "-c", 'permissions.qa={extends=":workspace",network={enabled=true,allow_local_binding=true,domains={"localhost"="allow","127.0.0.1"="allow"}}}', "-c", 'default_permissions="qa"']`
   - stable features only, full internet and the owner's `gh` login reachable: `QA_SANDBOX = ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]`

   Never `danger-full-access`: the timeout kill leaves the app and the browser running (Q6), and it can write `.git` and `$HOME`.
2. **Command line** (with the first choice):

   ```text
   codex exec --json --ephemeral --ignore-user-config \
     --disable hooks --disable apps --disable unbounded_connection_retries \
     -c project_doc_max_bytes=0 -c skills.include_instructions=false \
     -c model_reasoning_effort="<owner's choice>" \
     --enable network_proxy \
     -c 'permissions.qa={extends=":workspace",network={enabled=true,allow_local_binding=true,domains={"localhost"="allow","127.0.0.1"="allow"}}}' \
     -c 'default_permissions="qa"' \
     -C <repo> --output-schema scripts/qa-result.schema.json -o <tmp>/last.json -
   ```

   `--ignore-user-config`, `-c project_doc_max_bytes=0`, `-c skills.include_instructions=false`, `--disable hooks` and `--disable apps` keep this repo's `AGENTS.md` (orchestrator commands), the project and user skills, hooks, plugins, MCP servers and the apps connector out of the QA run (Q8). `--ignore-user-config` also keeps out a repo's `.codex/config.toml` and `.codex/hooks.json` when the repo is trusted in `$HOME/.codex/config.toml` (this repo is trusted there but has no `.codex/` today): the flag drops the trust list (Q8, "Project config of a trusted project"). `$CODEX_HOME/AGENTS.md` cannot be switched off; the owner's home has none. The QA role file goes into the prompt, as planned.
3. **A network outage never ends by default** (Q5). Without `--disable unbounded_connection_retries` it shows up only as the 30-minute timeout. With the flag, it ends after about 4 minutes as E9 (`transient`).
4. **Classify from `--json`, not from stderr.** Take the message of the last `turn.failed` event on stdout; if there is none, use stderr. Reasons: in normal mode stderr starts with the banner, so the planned `_first_line(err)` gives `OpenAI Codex v0.153.4` as the reason; and stderr echoes the prompt, which contains the issue text. The regexes of the error table work on both forms. The fake `codex` of #6 prints these events on stdout for `--json`, and the E1 line with exit 127 for "not installed".
5. **Optional pre-check:** `codex login status` (exit 1, `Not logged in`) finds "not logged in" at once. Without it, the 401 path takes about 16 s (E2).
6. **Working tree.** In both QA sandboxes Codex can create and change files in the repo (not in `.git`, so `HEAD` cannot move; Q9). A QA run can leave the tree dirty, and G1 then denies the next launch. `qa-codex` should compare `git status --porcelain` before and after the run and treat a change as an error, or run Codex in a separate checkout.
7. **QA role text (#6 step 6):** start the app and run the browser check in one command (a background process does not survive into the next Codex command, Q3); do not rely on a background server.
8. **Side effect:** a run with a writable sandbox writes `trust_level = "trusted"` for the repo into `$HOME/.codex/config.toml` (Q8). This repo is already trusted there. Other repos (paint-math) get the entry on the first QA run.
9. **Model effort:** the default is `reasoning effort: none`. `qa-codex` should set it (and the model, if wanted) explicitly.

Owner decision needed: yes. (a) Which `QA_SANDBOX`: the localhost-only profile, which depends on the experimental `network_proxy` feature, or `workspace-write` with full network, where Codex can reach GitHub with the owner's `gh` login (Q9; hiding the login through environment variables is not a boundary). (b) What `qa-codex` does when a QA run changed the working tree. (c) The reasoning effort for QA. (d) Accept the trust entry in `$HOME/.codex/config.toml`.

### #8 (codex-review)

Holds:

- `read-only` works for a review: Codex reads files and runs read-only commands; it cannot write or use the network (Q3).
- The draft `review.schema.json` built as in step 3 is accepted as is (Q7).
- "On a Codex failure, write no file": failed runs leave no new output (Q1).

Changes needed: only the shared runner changes of #6: `sandbox_args=["-s", "read-only"]` instead of `sandbox="read-only"`, `--json` for the error text, `--disable unbounded_connection_retries`, and the same flags that keep `AGENTS.md`, project config, skills, hooks and apps out of the prompt. A read-only run does not write the trust entry (Q8).

Owner decision needed: no

### #9 (frontend lane)

Q4 is yes: `qa-codex` can run Playwright with headless Chromium, with either `QA_SANDBOX` of #6 (the localhost-only profile is the most restrictive that works). No extra Chromium flag is needed. So the precondition of spec 9.3 holds.

Changes needed:

1. Dependencies and browsers must be installed before the Codex run: `$HOME` is read-only in the sandbox (`npx playwright install` cannot write `$HOME/.cache/ms-playwright`), and the localhost-only profile cannot reach the npm registry. For paint-math this means `npm ci` and the Playwright browser install happen outside Codex, for example in `qa-codex` before the run or as a set-up step in the README (#10).
2. The QA role text asks Codex to start the dev server and the browser check in one command (see #6, change 7).

Owner decision needed: yes, only where the frontend dependencies are installed before QA (change 1). It follows the `QA_SANDBOX` decision of #6: with `workspace-write` + network, Codex could run `npm ci` itself, but still not the browser download into `$HOME`.
