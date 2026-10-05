# Spike: a Claude Code plugin delivers the kit's hooks, agents and bin (issue #158)

Result in one line: the guard hook, the SubagentStop hook, `${CLAUDE_PLUGIN_ROOT}`, the plugin `bin/`, the plugin agents and the thin wrapper all work. The PermissionDenied hook is registered but its firing was not observed. Two facts change the plugin work: the v1 guard does not recognize a plugin agent that is launched by its namespaced name, and the v1 launcher cannot move to `bin/` without a path change.

Claude Code version: `2.1.289 (Claude Code)` (`claude --version`).

## Set-up of the probe

All names and data are synthetic. The probe ran in a scratch private repo (`Lighfe/agk-probe-158`, a clone in the session scratch directory, deleted at the end) with a scratch plugin in a scratch local marketplace.

- Plugin `agk-probe` 0.0.1: `.claude-plugin/plugin.json`, `hooks/hooks.json`, the v1 hook scripts copied unchanged (`guard.py`, `issue_state.py`, `not_started.py`, `outage_stop.py`) into `hooks/`, the five v1 agents in `agents/` plus three probe agents (`probe-agent`, `probe-tools`, `probe-disallow`), and `bin/probe-bin` and `bin/qa-codex-launcher`.
- Each hook command in `hooks.json` writes `<EVENT> root=${CLAUDE_PLUGIN_ROOT}` to a log in the project, saves the event JSON with `tee`, and then runs `uv run --script "${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py"`. The `PreToolUse` command keeps the v1 form `|| { echo 'guard hook failed: call denied' >&2; exit 2; }`.
- Install from a local path: `claude plugin marketplace add ../mkt` (output: `Successfully added marketplace: agk-probe-mkt`), then `claude plugin install agk-probe@agk-probe-mkt --scope project` (output: `Successfully installed plugin: agk-probe@agk-probe-mkt (scope: project)`). `claude plugin list` shows `Read from:` the local directory, `Scope: project`, `Status: enabled`.
- Every session ran as `claude -p "<prompt>" --model haiku|sonnet --permission-mode <mode>` in the scratch project.
- `claude plugin details agk-probe` lists: `Agents (8)`, `Hooks (3)  PreToolUse, SubagentStop, PermissionDenied`, `Skills (0)`, `MCP servers (0)`.

`claude plugin validate`:

- `claude plugin validate <plugin dir>`: `Validation passed with warnings` (one warning: `author: No author information provided`)
- `claude plugin validate <plugin dir> --strict`: `Validation failed (--strict treats warnings as errors)` for that same warning. A real plugin needs an `author` field to pass `--strict`
- `claude plugin validate <marketplace dir>`: `Validation passed with warnings` (marketplace description and plugin author missing)
- `claude plugin validate <plugin dir>/agents`: `Validation passed`
- Limit: `validate` on the plugin directory only reads the manifest (its first output line is `Validating plugin manifest: …`). It does not check `hooks/hooks.json`. A hooks error shows only at load time

## 1. The PreToolUse guard hook fires from a plugin and denies

Works.

Session: `claude -p "Run exactly this Bash command and report the raw tool result or error text verbatim: gh issue close 1" --model haiku --permission-mode bypassPermissions`.

Reply of the session (shortened): the command failed with the hook error `G1: issue #1 has no label ready, expected the label ready`. The issue stayed `OPEN` (`gh issue view 1 --json state --jq .state`). The hook log has one line: `PreToolUse root=<scratch marketplace>/plugins/agk-probe`.

This is the v1 `guard.py`, byte for byte, so it denies the same call as v1 does for the same issue state. The probe did not run the v1 guard in the kit repo on the scratch issue.

Later sessions showed more of the same guard, from the plugin:

- A `Bash` call with the exact form `scripts/qa-codex ROLE=qa ISSUE=1` was denied one rule at a time by the issue state, from `G1: issue #1 has no label ready` over the missing launch comment to `G4: current result is none, expected ## Engineer: DONE …`. After the label, a launch comment and an `## Engineer: DONE` comment were added to the scratch issue, the guard allowed the call. So the guard reads the issue state with `gh` from the plugin copy, as in v1
- The hook also fires inside a subagent: the saved event of a `Bash` call of `probe-agent` has `agent_id` and `agent_type: agk-probe:probe-agent`

Finding that matters for D3. The guard decides on `subagent_type` and has the bare names `pm`, `software-engineer`, `frontend-engineer`, `qa-engineer`, `planner` in `AGENT_ROLE`. A plugin agent has the namespaced name `agk-probe:pm`:

- `Agent` with `subagent_type` `agk-probe:pm` and a prompt without a launch line: not denied, the agent ran and answered `OK`. The guard treated it as an unguarded launch
- `Agent` with `subagent_type` `pm` and the same prompt: denied with `G1: launch of pm has no launch line, expected exactly one line ROLE=<pm|engineer|qa|planner> ISSUE=<number>`
- `Agent` with `subagent_type` `probe-agent` (bare name of a plugin agent): resolved and ran. So both names reach the same plugin agent, and a launch by the namespaced name skips the v1 guard

So the guard must also accept `<plugin name>:<agent name>`.

## 2. PermissionDenied and SubagentStop hooks

SubagentStop: works. After each subagent run the hook log has `SubagentStop root=<scratch marketplace>/plugins/agk-probe`, and `stop.json` holds the event (`session_id`, `transcript_path`, `cwd`, …). The v1 `outage_stop.py` ran from the plugin.

PermissionDenied: registered, firing not observed. `claude plugin details` shows the hook as registered. The firing needs a call that the auto mode classifier denies. The probe tried to cause one, and could not, for two reasons. A launch of such a call from this session was denied by the session's own classifier, and the engineer must not work around a classifier verdict. A milder call (`sudo rm -rf` of a path that does not exist) was refused by the model itself and never reached the classifier. So there is no log line either way. The trial task of the plan can cover this: in the trial project, an auto mode deny of a launch shows the `## Launch not started: …` comment, or does not show it.

## 3. `${CLAUDE_PLUGIN_ROOT}` resolves in the hook command

Works. The hook log shows the resolved value: `PreToolUse root=<scratch marketplace>/plugins/agk-probe`, the directory that `claude plugin list` shows under `Read from:`. The command `uv run --script "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"` found the script and started it. The guard found its inputs: it read the labels and comments of the scratch issue with `gh` (see question 1) and its sibling modules (`issue_state`) from the plugin directory.

Note: the plugin was installed from a local directory marketplace, which Claude Code read in place. A plugin from a remote marketplace is copied to a cache directory and `${CLAUDE_PLUGIN_ROOT}` points there. The probe did not test a remote install.

## 4. The plugin `bin/` is on the PATH of the Bash tool, also in a subagent

Works, in both.

- Main session: `claude -p "Run the Bash command: command -v probe-bin; probe-bin   and report the raw output."` printed `<scratch marketplace>/plugins/agk-probe/bin/probe-bin` and `probe-bin ran: the plugin bin is on PATH`
- Subagent: `Agent` with `subagent_type` `agk-probe:probe-agent` (a plugin agent) ran `probe-bin` with its `Bash` tool. The saved `PreToolUse` event of that call has `agent_type: agk-probe:probe-agent` and the command `probe-bin`. The agent's reply: `probe-bin ran: the plugin bin is on PATH`

## 5. A plugin agent reads the role files from the project's `docs/` at the same paths

Works. The scratch project has `docs/team/probe-role.md` (first line `PROBE-ROLE-LINE one`). `probe-agent` (a plugin agent) read `docs/team/probe-role.md` with a relative path and replied `PROBE-ROLE-LINE one`. The working directory of the subagent is the project, so the v1 prompt lines `Read your role definition from docs/team/<role>.md` resolve in the project.

## 6. Front matter keys of a plugin agent

Tested with `probe-agent`, `probe-tools` and `probe-disallow`:

| Key | Result for a plugin agent | Evidence |
|---|---|---|
| `name`, `description` | used | the agent is listed as `agk-probe:<name>` |
| `model` | honored | main session `--model sonnet`; `modelUsage` of the run lists `claude-haiku-4-5` for the subagent (`model: haiku`) and `claude-sonnet-5-5` for the main session |
| `tools` | honored | `probe-tools` (`tools: Read`) replied that it has only `Read` and no `Bash` |
| `disallowedTools` | honored | `probe-disallow` (`disallowedTools: Bash`) replied `NO BASH TOOL`, and the hook log has no `Bash` event for it. (A first run with another prompt made the agent say that Bash was available. That reply was wrong: the model had listed tools from memory. The second run made the agent try the tool.) |
| `permissionMode` | ignored | `probe-agent` has `permissionMode: bypassPermissions`. With the main session in default mode, its `Bash` call `probe-bin` was not run: the agent said it needed approval, and the run's `permission_denials` lists the `Bash` calls. The hook event of the subagent call has `permission_mode: default` |
| `hooks` (in the agent) | ignored | `probe-agent` has a `PreToolUse` hook that writes `agent-hook.log`. Its `Bash` call ran, and the file was never made |
| `mcpServers` (in the agent) | ignored | `probe-agent` has an MCP server whose command writes `mcp.log` when it starts. The file was never made |

Not tested: `skills`, `memory`, `maxTurns`, `color`, `effort`, `isolation`, `background`. The v1 agents in this repo use `name`, `description` and `disallowedTools` (checked with `.claude/agents/software-engineer.md`), so the untested keys do not matter for D3 now.

## The thin wrapper of D6

Works for the delivery path, with one limit.

Test: the scratch project had `scripts/qa-codex`:

```
#!/bin/sh
exec qa-codex-launcher "$@"
```

and the plugin `bin/qa-codex-launcher` was a stub that prints its arguments (the real v1 launcher posts comments and starts Codex, so the probe did not run it). After the scratch issue had the label, the launch comment and an `## Engineer: DONE` comment, this session ran: `claude -p "Run exactly this Bash command and report the raw output or error verbatim: scripts/qa-codex ROLE=qa ISSUE=1"`. Reply: `STUB LAUNCHER from plugin bin got: ROLE=qa ISSUE=1`. So the exact guard form passes the guard, the project file starts the launcher from the plugin `bin/`, and the arguments arrive unchanged. The guard reads only the command text, so the wrapper does not change what it sees.

Limit: the real launcher `scripts/qa-codex` (v1) sets `ROOT = Path(__file__).resolve().parents[1]`, imports from `ROOT / ".claude" / "hooks"` and its own folder (`codex_exec`), and reads `ROOT / "scripts" / "qa-result.schema.json"`. Moved to a plugin `bin/`, `ROOT` is the plugin directory, so the project root is wrong for the `git` and `gh` calls and the hook import path. The launcher needs one change: take the project root from the working directory (`git rev-parse --show-toplevel`) and the helper files from its own folder. The plugin task must do that before the switch.

## Consequences

| Question | Answer | What it means |
|---|---|---|
| 1 PreToolUse guard from a plugin | works | D3 holds for the guard. The guard must also recognize the namespaced agent name `<plugin>:<agent>` (found above), else a launch by that name is unguarded. The plugin task adds this and a test |
| 2 PermissionDenied and SubagentStop | SubagentStop works; PermissionDenied not observed (registered, no classifier deny could be provoked, see above) | D3 holds for SubagentStop. For PermissionDenied the trial in a fresh project must show the `## Launch not started: …` comment after an auto mode deny of a launch. Until then it is unproven |
| 3 `${CLAUDE_PLUGIN_ROOT}` | works (local directory install; remote install not tested) | D3: hook commands use `${CLAUDE_PLUGIN_ROOT}`, and no copy of the hooks is needed in the project. The trial covers a remote-style install |
| 4 plugin `bin/` on PATH, also in a subagent | works | D6: a project wrapper can start a launcher from `bin/` |
| 5 plugin agents read the project's role files | works | D3 and D4: agents in the plugin, role files copied into the project at the same paths |
| 6 front matter keys | `permissionMode`, `hooks`, `mcpServers` ignored; `model`, `tools`, `disallowedTools` honored | D3: the v1 agents need no change. A later agent must not rely on `permissionMode`, `hooks` or `mcpServers` in its front matter |

Decisions:

- D3: holds, with the guard change for the namespaced agent name
- D4: holds. The role files can stay in the project (question 5)
- D6: the wrapper works (see above). The switch needs the launcher change for `ROOT`. Keep the project copy of the launcher until that change is made and tested with the real launcher on a scratch issue

Extra notes for the plugin task:

- `claude plugin validate` needs an `author` field to pass `--strict`, and it does not check `hooks/hooks.json`
- With the owner's Auto mode entry for the scratch repo, `gh repo create <name> --private --clone` and `gh repo delete <name> --yes` both ran

## Final state

After the probe (all commands run by the probe):

- `claude plugin uninstall agk-probe@agk-probe-mkt --scope project`: `Successfully uninstalled plugin: agk-probe (scope: project)`
- `claude plugin marketplace remove agk-probe-mkt`: `Successfully removed marketplace: agk-probe-mkt`
- `claude plugin list | grep -c agk-probe`: `0`
- `gh repo delete Lighfe/agk-probe-158 --yes`, then `gh repo view Lighfe/agk-probe-158`: `GraphQL: Could not resolve to a Repository with the name 'Lighfe/agk-probe-158'. (repository)`
- `gh repo list Lighfe --limit 50 | grep -c probe`: `0`
- The scratch clone, the scratch marketplace and the scratch plugin folders were removed from the session scratch directory
- This repo has one new file, this note, and no other change
