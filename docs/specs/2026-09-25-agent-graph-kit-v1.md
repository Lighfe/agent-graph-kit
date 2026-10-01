# agent-graph-kit v1

- Date: 2026-09-25
- Status: v1 is implemented.
- Source: design session with the owner on 2026-09-25. Research inputs: `docs/research/`.
- Updated 2026-10-01: status set to implemented.

This spec is the accepted design of the kit for version 1. Earlier notes in `docs/archive/` are historical input only.

---

## 1. Purpose

v1 turns the prose loop PM → Engineer → QA into a graph where:

- hooks check every prescribed handoff call and deny it when the issue is not in the right state,
- a different vendor (Codex) is the default checker of every result (a Claude fallback is a marked exception),
- frontend work goes to Lovable.

The kit is dogfooded in this repo. The Lovable lane is proven in a demo repo, `paint-math` (a UI where you enter mathematical equations and see them drawn on a canvas; the name can change).

## 2. Principles

| # | Principle |
|---|---|
| P1 | **Prose guides, hooks check.** `docs/process.md` and the role files stay the main description of the process. Hooks check only the prescribed handoff calls. They are not a security boundary: a call outside the prescribed ones (for example `gh api`, or a comment written by hand) is not checked. |
| P2 | **Facts only.** v1 hooks check facts: labels, comment markers, SHAs, git status. No LLM or Jev judgment blocks anything. |
| P3 | **State lives on the issue.** Hooks and scripts read the state with `gh`. Nothing depends on what the orchestrator remembers. |
| P4 | **Few files.** The kit adds as few agent-facing files as possible. Adopting the kit means merging into existing files, never appending a second set. |
| P5 | **No secrets.** No keys in commits, issues, comments or reviews. Examples are synthetic. |

## 3. Scope

### In v1

1. Hook guarantees for role launches and for closing an issue (section 5)
2. Codex QA through a launcher script, with a Claude fallback (sections 6 and 7)
3. A Codex review skill that always writes a review file (section 8)
4. The Lovable lane and the paint-math demo (section 9)
5. The `later` label (section 10)
6. Tests, CI for this repo, and README set-up instructions (section 12)
7. Three spikes before the dependent work (section 13)

### Not in v1

Each item becomes a GitHub issue with the label `later` during intake. The note after the dash goes into the issue body.

| Item | Note |
|---|---|
| Jev at the handoffs | Before building: measure Jev accuracy on 10 to 20 real groomed issues; measure the token size of typical issues and diffs against Jev's limit (32k tokens for state + longest question) |
| Packaging: Claude Code plugin + init command | Before building: verify how hooks work inside a plugin and how a project can configure them |
| Adopting the kit in existing projects | First pilot: mini-kanban-board. Adoption merges the kit into existing docs (P4) |
| Doc decluttering ("librarian") | Process to find and remove outdated or redundant agent-facing docs |
| Separate Reviewer role | Add only if QA passes work with real quality problems |
| Parallel mode (worktrees) | Changes every guarantee that assumes one HEAD and one sequence |
| Role limits through Bash | PM and QA cannot write or commit through Bash |
| Required review before intake | A plan becomes issues only after a review with a status on each finding. Decide after using the review skill on a few specs |
| Codex as an engineer lane | Rule "the checker is always a different vendor from the implementer" |
| Config levels for small projects | For example: loop without some roles or gates |
| Independent test design by QA | QA designs tests before the engineer implements. Add if QA often finds missing tests |
| CI in the close gate | Close only with green CI on the verified SHA. Needs a push rule |
| CI/CD set-up and deploy skills | Skills, not roles (see `docs/research/qa-and-cicd-in-agent-graphs.md`) |
| On-call loop | A separate observe/respond graph for production alerts |

## 4. Roles and lanes

| Role | Runs on | Launched through | Posts the result |
|---|---|---|---|
| Orchestrator | Claude main session | – | – |
| PM | Claude subagent `pm` | subagent launch | the PM, with `gh` |
| Engineer, lane `default` | Claude subagent `software-engineer` | subagent launch | the engineer, with `gh` |
| Engineer, lane `frontend` | Claude subagent `frontend-engineer`, which drives Lovable through MCP | subagent launch | the subagent, with `gh` |
| QA (default checker) | Codex (`codex exec`) | the script `qa-codex`, through Bash | the script, with `gh` |
| QA fallback | Claude subagent `qa-engineer` | subagent launch, only after `## QA: UNAVAILABLE` | the subagent, with `gh` |

- The orchestrator only launches subagents and the `qa-codex` script. It never calls Lovable or Codex directly.
- The PM writes the lane into the issue: `Lane: default` or `Lane: frontend`. `frontend` is allowed only in a repo with a Lovable submodule.
- One role file per role in `docs/team/`. Both QA checkers use `docs/team/qa-engineer.md`. The frontend lane is a section in `docs/team/software-engineer.md`, not a separate role file (P4).

## 5. Launch contract and hook guarantees

### 5.1 Guarded calls

A hook runs before each tool call of the orchestrator and of its subagents. It guards only these calls:

| Call | Role |
|---|---|
| Subagent launch of `pm` | pm |
| Subagent launch of `software-engineer` or `frontend-engineer` | engineer |
| Subagent launch of `qa-engineer` | qa (fallback) |
| `SendMessage` that continues a role agent | the role in its launch line |
| Bash call of `qa-codex` | qa |
| Bash call of `gh issue close <number>` | close |
| Bash command that writes to `.claude/settings*.json` | – (always denied, G8) |
| Any other Bash command that contains the trigger (below) | – (always denied, G1) |

All other calls pass. Examples: other subagent types, the Codex review skill, Bash commands without the trigger.

**Bash trigger rule.** The hook does not parse Bash commands to find a guarded call. It uses a fail-closed rule instead:

- **Trigger.** A text is triggered if it contains both words `gh` and `close` (Python regexes `\bgh\b` and `\bclose\b` with the flag `re.ASCII`, case-sensitive), or the text `qa-codex`. A Bash command is triggered if its original text is triggered, or a copy of it with every backslash-newline (`\` followed by LF) removed is triggered. So `gh issue clo\` + LF + `se 5` is triggered.
- **Allowed forms.** A triggered command is a guarded call only if its original, unchanged text (never the copy) matches one of these patterns with Python `re.fullmatch`:
  - close: `gh issue close ([1-9][0-9]*)(?:(?: --reason | --reason=| -r )(?:completed|'not planned'|"not planned"))?[ \t]*\n?`
  - qa: `scripts/qa-codex ROLE=qa ISSUE=([1-9][0-9]*)[ \t]*\n?`

  A match is not an allow on its own. The call then goes through the checks (5.4), the lock and the deadline (5.6, 5.7) and the launch comment (5.3), as every guarded call does. `qa-codex` runs with the Bash tool's background option (`run_in_background`), not with `&`.
- **Deny.** Every other triggered command is denied with `G1:`, before any `gh` or `git` call. The deny reason names the two forms and the ways around: `git commit -F <file>` for a commit message, `gh … --body-file <file>` for a comment body, the Read or Grep tool instead of Bash, a path without the trigger word (`git add scripts/`), and `run_in_background` instead of `&`.
- **No trigger.** A Bash command that is not triggered is not a guarded call. G8 (5.9) still applies to it, and G8 runs first for every Bash command.

**Bash comment commands (no check).** The guard does not check comment commands. The check G9 ([#72](https://github.com/Lighfe/agent-graph-kit/issues/72), [#78](https://github.com/Lighfe/agent-graph-kit/issues/78)) that kept every comment call in one exact form was removed in [#90](https://github.com/Lighfe/agent-graph-kit/issues/90): after the content check was dropped in #78, the form protected nothing, and it denied many commands that only wrote a file. A comment command goes through G8 and the G1 trigger rule like any Bash command (a command or path with `close` or `qa-codex` in it is still denied by G1). The agents post with `gh issue comment <n> --body-file <literal absolute path>`, with the body in a file; this is a rule of `docs/process.md`, not a check.

- **Not started.** A comment command is not a launch, so the `PermissionDenied` hook (5.7) posts nothing for it.
- **Owner's marker.** The agents and hooks post with the owner's `gh` login (5.3), so `authorAssociation` cannot tell an agent from the owner. That agents never post the owner's marker is a rule of `docs/process.md`, not a check. The owner posts `## Owner: RESUME` on the GitHub web page, in a terminal, or from a Claude Code session.
- **Other routes.** Other posting routes stay unchecked ([#76](https://github.com/Lighfe/agent-graph-kit/issues/76)): `gh api`, Codex inside the QA launcher, and MCP tools with GitHub write access.

**Accepted false denies.** The rule denies some commands that run no guarded call. This is accepted, because the agent can always use one of the ways around. Examples:

- `cat scripts/qa-codex`
- a heredoc commit message that mentions `qa-codex` (`git commit -m "$(cat <<'EOF'` … `EOF` … `)"`)
- `git commit -m "Fix gh close handling"`
- `gh issue view 5 | grep close`
- `gh pr close 5`
- `/usr/bin/gh issue close 5`, `command gh issue close 5`, `gh  issue close 5` (not the exact form)

**Known limit (P1).** A text that does not literally contain the trigger is not recognized, for example variables (`$GH issue close 5`), `$'…'` escapes, brace expansion (`gh issue {close,} 5`), globs, quotes or backslashes inside a word (`gh issue cl''ose 5`, `gh issue c\lose 5`), and other letter case (`GH issue close 5`, which runs `gh` on a case-insensitive macOS file system). Calls outside the prescribed ones (`gh api`, `gh issue edit --state closed`) stay unchecked.

### 5.2 Launch line

A guarded launch of a role must contain the line `ROLE=<role> ISSUE=<number>` (in the subagent prompt, in the `SendMessage` message, or as arguments of `qa-codex`). A launch without this line is denied. A `SendMessage` without this line is denied too.

Close needs no launch line. The hook reads the issue number from the `gh issue close` command. If the command has no single, clear issue number, the hook denies it. Close posts no launch comment.

### 5.3 Launch comments and valid results

When the hook allows a launch, it posts a launch comment on the issue before the call runs:

```
## Launch: engineer (attempt 3)
Agent: software-engineer
Call: 3f2a9c01b7de
```

The `Call:` line is the **call hash**: the first 12 hex characters of the SHA-256 of the event's `tool_use_id`. The raw id is not posted. An event without a string `tool_use_id` gets a receipt without a `Call:` line.

**Only the owner's comments count** ([#70](https://github.com/Lighfe/agent-graph-kit/issues/70)). The issue state is read with `gh issue view <n> --json number,state,labels,body,comments`, which gives each comment its `authorAssociation`. Only comments whose `authorAssociation` is exactly `OWNER` count; other comments (`COLLABORATOR`, `MEMBER`, `CONTRIBUTOR`, `NONE`, …) are ignored, as if they were not on the issue. This holds for every comment this section and 5.4 read: launch comments, not-started and stop comments, result markers and `## Owner: RESUME`. So in a public repo a stranger's comment cannot resume, pass, block, void a receipt or close an issue. The agents and hooks post with the owner's `gh` login, so all legitimate comments are the owner's. Missing author data is an error: a comment without a string `authorAssociation` makes the issue parser (`issue_state.parse_issue`, the one parse point for the guard, both hooks of 5.7 and `qa-codex`) fail, like a comment without a string body; the guard then denies with `guard error`, and the hooks post nothing. Organization-owned repos are not supported yet: their owner's comments are not `OWNER` ([#75](https://github.com/Lighfe/agent-graph-kit/issues/75)).

**Not started.** The guard runs before the permission check, so it cannot see a later denial. When auto mode denies the call (also without a classifier verdict), Claude Code runs the `PermissionDenied` hook (5.7) with the same `tool_use_id`. If the newest receipt on the issue has the matching `Call:` line, no valid result and no `## Owner: RESUME` after it, and is not yet marked, the hook posts a **not-started comment**:

```
## Launch not started: engineer (attempt 3)
Call: 3f2a9c01b7de
Reason: Auto mode could not evaluate this action and is blocking it for safety
```

A receipt is **not started** when a later not-started comment has the same `<role> (…)` part and the same `Call:` value. Such a receipt counts for nothing (pending, validity, current result, G2, returns) except the attempt number: the next launch of that role gets the next number. A not-started comment is not a result, not a receipt and not `## Owner: RESUME`. A not-started comment that matches no receipt changes nothing.

**Stopped by an outage** ([#52](https://github.com/Lighfe/agent-graph-kit/issues/52)). A role agent can start and then be stopped by an auto mode outage: its calls are denied without a classifier verdict, so it cannot read the issue or post a result. Evidence: when the `PermissionDenied` hook sees a denial inside a subagent (the event has an `agent_id`, a name of 1 to 64 letters, digits, `_` or `-`) whose reason's first line starts with `Classifier unavailable`, `Auto mode could not evaluate this action and is blocking it for safety` or `Auto mode unavailable` (the no-verdict texts of Claude Code 2.1.284), it writes that first line as is (trailing whitespace kept), cut to 200 characters, to the evidence file `<git dir>/agent-graph-kit-outage/<agent_id>`. The file is in the git dir, not in the working tree, so the clean-tree check of G1 is not affected. Any other reason (a classifier judgment, `Permission denied`) is no evidence. When the agent ends, the `SubagentStop` hook (5.7) reads and deletes the evidence file (it deletes it at every stop, so evidence of one round never counts for a later round of the same agent). It reads the launch line (5.2) from the first user message of the agent's transcript and checks that `agent_type` has that role. If the newest receipt on that issue has that role, a `Call:` line, no valid result and no `## Owner: RESUME` after it, and is not yet voided, the hook posts a **stop comment**:

```
## Launch stopped by outage: pm (attempt 1)
Call: 3f2a9c01b7de
Reason: Classifier unavailable
```

A stop comment voids its receipt exactly like a not-started comment: same key (the `<role> (…)` part and the `Call:` value), same effects. So the orchestrator launches the same step again; it is not a return, and the owner posts no `## Owner: RESUME`. Its `Reason:` is the content of the evidence file, unchanged. The comment holds no agent id, no transcript text and no raw `tool_use_id`.

**Deny with a verdict** ([#71](https://github.com/Lighfe/agent-graph-kit/issues/71)). A role agent can also get a deny with a verdict: an auto mode classifier judgment (for example "Instruction Poisoning") or a permission rule (`Permission denied`). This is no outage evidence, and the agent can still act. So when it does not retry the denied call, it posts its result marker and quotes the deny message, with secrets redacted (rule "Denied action" in `## Rules` of `docs/process.md`): the PM `## PM: NEEDS OWNER` when only the owner can resolve the deny (settings or permissions), the engineer `## Engineer: BLOCKED`, the QA fallback `## QA: UNVERIFIABLE` with each affected criterion marked `- [ ] … - INVALID`. A guard deny that names a way around (for example `--body-file`) is retried that way first; it is no denied action. The three cases differ: a deny with a verdict leads to a result by the agent; an outage deny leads to a stop comment by the hook (the agent posts no result and ends); a denied comment call leaves the issue pending, because the agent cannot post a result.

**Continuation.** The orchestrator may continue a role agent with `SendMessage` instead of a new launch, for example to give the same engineer the QA feedback with its own context. The message carries the same launch line. The hook runs the same checks as for a launch of that role and posts a launch comment of the form `## Launch: <role> (continued, round <n>)`. For validity, pending and returns, a continued comment counts as a launch comment. The `SendMessage` input names the target agent, not its type, so the agent part of G3 applies only to a new launch.

A result comment is **valid** only if both are true:

1. Its first line is a result marker of the role (section 5.5).
2. It was posted after the newest launch comment of that role.

An old result from an earlier attempt is ignored automatically.

The issue is **pending** if the newest launch comment has no valid result after it and no `## Owner: RESUME` comment after it. While the issue is pending, every guarded call on it is denied. A late result cannot be mixed up with a newer attempt, because no newer attempt can start. If a launched role ends without a result, the orchestrator escalates. The owner continues with `## Owner: RESUME`. A role that started and then could not act stays pending only when the `SubagentStop` hook found no outage evidence for it; with evidence, its receipt is voided by a stop comment (see above). A role whose action got a deny with a verdict posts a result, so the issue is not pending; it stays pending only when the comment call is denied too (see above).

The **current result** of an issue is the newest valid result of any role, or an `## Owner: RESUME` comment, if that is newer.

### 5.4 Checks

| # | Launch | Allowed only if |
|---|---|---|
| G1 | any guarded call | the launch line exists (5.2; not for close) · the issue is not pending (5.3) · the working tree is clean · the issue is open · it has the label `ready` and not the labels `later`, `needs-owner` or `waiting` (`waiting` is checked first, so the message names it also when `ready` is missing) |
| G2 | PM | the issue has no launch comment yet, or the current result is `## Engineer: BLOCKED`, `## QA: UNVERIFIABLE`, `## Owner: RESUME`, or `## PM: WAITING` with exactly one `Waiting on: #<N>` line (outside fences), `<N>` not the issue itself, and issue `<N>` closed |
| G3 | engineer | the current result is `## PM: GROOMED` or `## QA: FAIL` · the agent matches the lane (`default` → `software-engineer`, `frontend` → `frontend-engineer`) |
| G4 | qa (`qa-codex`) | the current result is `## Engineer: DONE`, or `## QA: PASS` with a verified SHA not equal to `HEAD` (re-check) · a `## Engineer: DONE` comment with a `Commits:` line exists |
| G5 | qa fallback (`qa-engineer`) | the current result is `## QA: UNAVAILABLE` |
| G6 | close | the current result is `## QA: PASS` and its verified SHA is equal to `HEAD` |
| G7 | PM or engineer | fewer than 3 returns (`## QA: FAIL`, `## QA: UNVERIFIABLE` or `## Engineer: BLOCKED`) after the newest `## Owner: RESUME` comment |
| G8 | any Bash call | the command does not write to `.claude/settings*.json` (5.9). This check reads no issue state. When in doubt, it denies |

Notes:

- All checks read only the comments whose `authorAssociation` is `OWNER`; other comments are ignored, and missing author data is an error that denies with `guard error` (5.3). A stranger's `## Owner: RESUME` does not pass G2 or reset the G7 count, and a stranger's `## QA: PASS` does not pass G6.
- G1 "clean tree before every launch" is possible because no role may leave uncommitted work: the engineer commits before DONE, and PM and QA do not write files. If a blocked engineer leaves changes, the next launch is denied, and the orchestrator stops the loop and asks the owner.
- G1, voided twice: a guarded launch (not close) is denied when the two newest receipts on the issue are each not started or stopped by an outage (5.3, any mix) and no result marker and no `## Owner: RESUME` comes after the older of the two. The message starts with `G1: issue #<n>: the last 2 launches` and names `## Owner: RESUME` as the way on. Claude Code is denying calls, so a third try would most likely fail too; the orchestrator stops the loop and asks the owner.
- G2: after `## Owner: RESUME`, the issue goes back to the PM for grooming. The PM applies the edits of the issue title and body that the owner's RESUME asks for; this needs the user-level Auto mode allow entry from the README ([#73](https://github.com/Lighfe/agent-graph-kit/issues/73)). After `## QA: UNVERIFIABLE`, it goes back to the PM to make the blocked criteria checkable (7). After `## PM: WAITING`, it goes back to the PM once the blocker is closed (any reason); the deny for an open blocker names `#<N>` and says that it is open. `## PM: WAITING` is not a return and does not reset the G7 count.
- G5: the fallback is only possible after `qa-codex` reported that Codex cannot run.

### 5.5 Result markers

| Role | First line |
|---|---|
| PM | `## PM: GROOMED`, `## PM: NEEDS OWNER`, `## PM: WAITING` |
| Engineer | `## Engineer: DONE`, `## Engineer: BLOCKED` |
| QA | `## QA: PASS`, `## QA: FAIL`, `## QA: UNAVAILABLE`, `## QA: INVALID`, `## QA: UNVERIFIABLE` |
| Owner | `## Owner: RESUME` |
| Hook | `## Launch: <role> (attempt <n>)`, `## Launch: <role> (continued, round <n>)`, `## Launch not started: <role> (attempt <n>)`, `## Launch not started: <role> (continued, round <n>)`, `## Launch stopped by outage: <role> (attempt <n>)`, `## Launch stopped by outage: <role> (continued, round <n>)` (not results) |

`## PM: NEEDS OWNER` and `## QA: INVALID` allow no next launch. The orchestrator escalates. `## QA: UNVERIFIABLE` leads to a PM launch with the URL of that QA comment (G2, 7). `## PM: WAITING` is not escalated: the orchestrator parks the issue (removes `ready`, adds `waiting`) while its blocker is open, and before every pick it gives `ready` back to each waiting issue whose blocker is closed; then the PM is launched with the URL of the WAITING comment (G2).

### 5.6 Failure behavior

- If `gh` or `git` fails (network, auth), or the hook script has any other error, the hook denies the call with an explicit deny response. A crash must never let the call through, except when Claude Code kills the hook at its timeout. Unknown facts do not allow a launch.
- Timeout (S1): a hook that Claude Code kills at its settings `timeout` lets the call through, and a command wrapper cannot catch this. So the guard has one overall deadline (about 60 s) for all its work, including the wait for the lock (5.7). At the deadline, it denies. The settings `timeout` is higher (about 120 s). Only a hung machine can cause a fail-open.
- The guard never outputs "allow". An allowed call produces no output, so the normal permission check stays on.
- Each deny message names the check that failed (for example `G3: current result is ## QA: PASS, expected ## PM: GROOMED or ## QA: FAIL`), so the orchestrator knows what is missing.

### 5.7 Implementation

- Python scripts run with `uv run --script` (inline dependencies, PEP 723), in `.claude/hooks/`, registered in `.claude/settings.json`.
- One shared module reads the issue state (labels, comments with timestamps) with one `gh` call. Each check is a small function.
- Blocker read: only for a PM launch or continuation whose current result is `## PM: WAITING` with a usable `Waiting on: #<N>` line (and G1 passes), the guard reads the blocker with one extra `gh issue view <N> --json state` call and passes its state to the checks as a fact, so the check module stays free of I/O. The read runs inside the lock, before the launch comment, within the same deadline; a failing or slow read, or a state other than `OPEN` or `CLOSED`, denies with `guard error`.
- The launch comments are the receipts. There is no separate log.
- Hooks of two calls in one message can run at the same time (S1). The guard holds an exclusive file lock from reading the facts until the launch comment is posted, so the second call sees the first launch comment and is denied as pending.
- Matcher: `Agent|Bash|SendMessage`. The command wrapper is POSIX `sh` and turns a crash or a missing `uv` into a deny (`… || { echo '…' >&2; exit 2; }`).
- `PermissionDenied` hook (`.claude/hooks/not_started.py`, same matcher, no wrapper): Claude Code runs it when auto mode denies a call. It classifies the call with the guard's rules and, for a denied launch of `pm`, `engineer` or `qa` (also `qa-codex` and a continuation), posts the not-started comment (5.3). It holds the same lock as the guard from reading the issue until the comment is posted, within the same deadline, so a receipt and its not-started comment cannot interleave with another launch. It cannot block anything; it prints nothing to stdout and always exits 0. It also writes the outage evidence (5.3) for a no-verdict denial inside a subagent, for any matched call; a failure there never stops the not-started comment.
- `SubagentStop` hook (`.claude/hooks/outage_stop.py`, no matcher, so it runs for every subagent): without an evidence file for the event's `agent_id` it ends at once, with no transcript read and no `gh` call. Otherwise it posts the stop comment (5.3). It holds the same lock as the guard from reading the issue until the comment is posted, within the same deadline. It prints nothing to stdout and always exits 0. Its command ends with `|| true`, because a `SubagentStop` hook that exits with code 2 keeps the agent running; a missing `uv` or a crash must never do that.
- Known limit: only denials of `Agent`, `Bash` and `SendMessage` calls count as outage evidence (the `PermissionDenied` matcher). A subagent stopped only by denials of other tools stays pending, as before.

### 5.8 Prose changes

- `docs/team/orchestrator.md` and `AGENTS.md`: the launch line; the new markers; the pending state; the issue list command leaves out `later` and `needs-owner` (`gh issue list --state open --label ready --search "-label:later -label:needs-owner"`); the hook deny message replaces most hand-written result queries.
- Role files: the launch line is in the prompt; the result must be posted after launch.
- `docs/process.md`: the hooks enforce the lifecycle; after `## Owner: RESUME` the issue goes back to the PM.
- `docs/team/orchestrator.md`: continue a role with `SendMessage` only with the launch line in the message.

### 5.9 Activation, settings protection and acceptance test

Project hooks are not a session-start snapshot (S1). An edit of `.claude/settings.json` applies at the next tool call of every running session in the repo, also the session that wires the hooks.

**Activation.**

1. Before the hook wiring task starts, the owner puts `{"disableAllHooks": true}` into `.claude/settings.local.json` (not committed; the file is in `.gitignore`).
2. The hook wiring task runs and is closed under the old process.
3. The owner deletes the file. The hooks apply from the next tool call.

No warning shows when `disableAllHooks` is still present. If the owner forgets step 3, all guards stay off.

**Settings protection.** Any agent that can write files can put `disableAllHooks` into the local settings file, and the change applies at the next tool call. So:

- `permissions.deny` rules for `Edit` and `Write` on `.claude/settings*.json`.
- The guard denies `Bash` commands that write to `.claude/settings*.json`.

**Allow rules.** The guard posts the launch comment before the permission check. If a prompt or a missing allow rule then stops the call, the issue stays pending without a real problem. So the project settings allow `Bash(scripts/qa-codex ROLE=qa ISSUE=*)` and `Bash(gh issue close *)`. Claude Code then does not ask the owner before these two calls. An auto mode denial is handled by the `PermissionDenied` hook (5.3, 5.7): the receipt is marked not started. A denial that fires no `PermissionDenied` event (a manual "No", a `permissions.deny` rule, another `PreToolUse` hook, Esc) still leaves the issue pending ([#53](https://github.com/Lighfe/agent-graph-kit/issues/53)). The guard still runs first, and its deny still stops the call. Project allow rules apply only after the folder is trusted.

**Acceptance test.** After the owner has deleted `disableAllHooks`, and before the next real issue gets `ready`, the owner runs a checklist (`docs/checks/hook-activation.md`) in an interactive session in the VS Code extension (the surface of the loop), on a throwaway issue. The owner types the prompts and checks each result. An agent does not test its own gates. If a step fails, the loop does not start. The checklist covers: the guard is listed in `/hooks`; a launch without a launch line is denied; a `SendMessage` continuation with and without the line (and whether the extension has `SendMessage` at all); writes of `disableAllHooks` with `Edit` and with `Bash` are denied; a guarded `qa-codex` call shows no permission prompt; whether `disableAllHooks` in the local file also stops user-level hooks. If the extension blocks `SendMessage`, the owner runs the loop with `claude` in the VS Code integrated terminal.

## 6. Codex QA launcher (`qa-codex`)

### 6.1 Call and flow

Call: `qa-codex ROLE=qa ISSUE=<n>`. A Python script run with `uv run --script`.

1. Read the issue with one `gh issue view <n> --json number,state,labels,body,comments` call, outside the sandbox. This single read gives the acceptance criteria (from the body), the range and the comments, so they are one snapshot; there is no second `gh` read. Read the range from the `Commits: <base>..<head>` line of the newest valid `## Engineer: DONE` comment. Only comments whose `authorAssociation` is `OWNER` count (5.3): other comments are ignored for the newest valid DONE and the range, and are not passed to Codex at all; missing author data is an error (`## QA: UNAVAILABLE`, see below). The comment text passed to Codex is the first line of every counted issue comment, in issue order, and the full text of that newest valid DONE comment (the one that gives the range); no other comment body is passed. Codex cannot read GitHub from the sandbox, so this lets it check criteria about the comments (launch comments, evidence in the DONE comment). If the issue read fails, or its output is not JSON or is rejected by the issue parser (for example a missing `comments` list, or a comment without a string `authorAssociation`), post `## QA: UNAVAILABLE` without a Codex run (6.2). The DONE head (`<head>`) must be `HEAD` or an ancestor of `HEAD` (`git merge-base --is-ancestor`). QA then verifies `<base>..HEAD`. So a re-check after `HEAD` moved (G4, 5.4) needs no new DONE. If the DONE head is not an ancestor of `HEAD` (for example after a rebase), post `## QA: INVALID` without a Codex run. The engineer must post a new DONE.
2. Create a temporary `git worktree` at `HEAD`. Codex can write files in the working tree in every sandbox. In the main tree this would make G1 deny the next launch, and a PASS could apply to code that is not in `HEAD`. The worktree is deleted after the run.
3. Pre-step, outside the sandbox, with fixed commands and no LLM decision: in a repo with a frontend, fetch the submodule commits into the worktree, run the install command that follows the lockfile in the worktree's `frontend/`, then install the Playwright browser with the Playwright CLI of the frontend's own dependency, through the package manager of the lockfile: `npx --no playwright install chromium` (npm lockfile) or `bun x --no-install playwright install chromium` (bun lockfile). `--no` and `--no-install` refuse a registry fetch, so the browser version follows the frontend's lockfile and nothing is fetched from the registry for it; a bun frontend needs `bun` on `PATH` and no `npx`. The install command: with an npm lockfile (`package-lock.json` or `npm-shrinkwrap.json`) `npm ci`, else with a bun lockfile (`bun.lock` or `bun.lockb`) `bun install --frozen-lockfile`, else `## QA: UNAVAILABLE` (the reason names the four file names). If both kinds exist, `npm ci` runs. A bun frontend needs `bun` on `PATH`; without it, the result is `## QA: UNAVAILABLE`. The lockfile is checked after the submodule update, and neither missing case runs an install, the browser step, the uv cache fill below or Codex. The frontend needs a Playwright dependency: `playwright` or `@playwright/test` in `dependencies` or `devDependencies` of `frontend/package.json` (in practice `@playwright/test` as a dev dependency, added through Lovable, in `package.json` and its lockfile; other fields and `playwright-core` do not count). The check reads the worktree's `frontend/package.json` after the submodule update and the lockfile checks, and before the install. Without the dependency (or with a missing or invalid `package.json`) the result is `## QA: UNAVAILABLE` whose reason names `package.json`, and no install, browser step, uv cache fill or Codex run happens. The Lovable project gets the dependency by a chat prompt (for example "Add `@playwright/test` as a dev dependency, update the lockfile, do not add tests"); the project then bumps its `frontend` submodule, because the worktree checks out the recorded commit. If the pre-step fails, the result is `## QA: UNAVAILABLE`. (`codex exec` cannot pause for an install, and the sandbox cannot reach the npm registry or write `$HOME`.) Test command: in the sandbox `uv` cannot lock its cache `$HOME/.cache/uv` (read-only) and cannot reach PyPI, so when `uv` is on `PATH` the pre-step runs `uv run --no-project --no-config --with pytest pytest --version` with `UV_CACHE_DIR=<run temp folder>/uv-cache` (the run temp folder is the folder that holds the worktree, under `/tmp` or `$TMPDIR`, which the sandbox can already write; it is removed with the worktree). This cache fill runs with the run temp folder as its working directory, not the worktree, so it does not discover, read or build the reviewed project or its uv config (`pyproject.toml`, `uv.toml`, a `.venv`): that repository code runs only in the sandbox. The cache fill is skipped without `uv` on `PATH`. Step 4 passes one `-c shell_environment_policy.set={UV_CACHE_DIR="<that folder>",UV_OFFLINE="1",CI="1"}` to `codex exec`; without `uv` on `PATH` the table holds only `CI="1"`. It is one table because Codex keeps only the last `-c` for the same key. `CI="1"` holds for every command Codex runs, the test command included, and for no pre-step command. Why `CI`: dev tooling such as the TanStack devtools plugin of a Lovable frontend runs `bun outdated` on dev-server start and so contacts the npm registry, which the sandbox blocks, unless `CI` is set. `CI` can change how some tools behave (for example, a Playwright config may not reuse a running server, or may retry).

   **Accepted risk: frontend pre-step.** The frontend pre-step runs repository-controlled code outside the Codex sandbox, with the user's environment and access (home folder, credentials, network). Three paths do this:
   - Lifecycle scripts: the install runs the `preinstall`, `install`, `postinstall` and `prepare` scripts. `npm ci` runs those of `frontend/package.json` and of every dependency. `bun install --frozen-lockfile` runs those of `frontend/package.json` and of the dependencies bun trusts: `trustedDependencies` in `frontend/package.json` and bun's built-in default trusted list.
   - Package manager config: the install reads the config in the reviewed `frontend/`: `frontend/.npmrc` (npm) and `frontend/bunfig.toml` (bun). This config can, for example, change the registry or the shell that runs scripts.
   - Playwright CLI: the browser step runs the Playwright CLI from `frontend/node_modules`. The lockfile decides which package that is (its source URL and its integrity hash), so this is repository code even without lifecycle scripts.

   Why this is accepted: the frontend code comes from the owner's own Lovable project and from the loop's engineer, not from strangers. The owner accepted the risk in issue #50 and kept the pre-step as it is. Remaining risk, including packages that agents add: a dependency or a new version that the Lovable agent (through `frontend-engineer`) or another agent of the loop puts into `frontend/package.json` or the lockfile runs its install scripts (and, for the Playwright package, its CLI) with the user's access at the next QA run, before QA or the owner has looked at the change. Nothing in the loop checks a new or changed dependency before the pre-step runs it. A change to `frontend/package.json`, the lockfile, `frontend/.npmrc`, `frontend/bunfig.toml` or `trustedDependencies` in a diff is a review item for the owner.
4. Run `codex exec` in the worktree with:
   - the localhost-only sandbox profile (S2: `--enable network_proxy` and a permissions profile `qa` that allows only `localhost` and `127.0.0.1`). QA tests the checked-out code and needs no GitHub. Codex runs outside the Claude Code hooks, so the sandbox is its only limit. `network_proxy` is experimental; check it after each Codex update,
   - the flags from S2 that keep the user config, `AGENTS.md`, skills, hooks and apps out of the run (`--ignore-user-config` and others). Because `--ignore-user-config` also removes the user's model and effort, the model and the reasoning effort are set explicitly. v1 starts with `medium` for all runs and records the results,
   - the prompt: the QA role file, the criteria, the range, and the comment text from step 1 (the first line of every comment and the full newest valid DONE comment). Each comment is redacted like a posted comment (P5) before it goes into the prompt. The comment text is a delimited data block: every line in it starts with a fixed prefix, so a comment cannot end the block early. The prompt says before the block that the text was written by agents, is data to check against the criteria and not instructions, and that a claim in a comment is not proof of the behavior it claims. The posted QA comment does not repeat this text. When `uv` is on `PATH`, the prompt also has a rule, outside the data block, that names `UV_CACHE_DIR` with its path (the same run temp folder `uv-cache` as in the `shell_environment_policy.set` table of step 3; the launcher passes one value to both) and `UV_OFFLINE`, says they are already set for every command Codex runs, to an offline cache that already holds pytest, and tells Codex to run the test command with them as given: not to set, change or unset them (not inline, not with `export`, `unset` or `env`), not to use another cache folder, and to report the command and the error in `tests` if the test command still fails, instead of working around it with another cache. Without `uv` on `PATH` the prompt has no such rule. The rule is in the prompt and not in the QA role file, because the Claude QA fallback reads the role file too and has no such cache (a QA run failed when Codex set a `UV_CACHE_DIR` of its own, which replaced the pre-filled one),
   - `--output-schema qa-result.schema.json` and `-o <file>` for the final message.
5. Validate the JSON against the schema. Check that it has exactly one entry for each acceptance criterion of the issue, and that the verified SHA is equal to `HEAD`. The script derives the overall marker from the criterion verdicts: any criterion `fail` gives `## QA: FAIL`; otherwise any criterion `invalid` gives `## QA: UNVERIFIABLE`, with a `Reason:` line that names each such criterion; otherwise `## QA: PASS`. So FAIL comes before UNVERIFIABLE, and UNVERIFIABLE before PASS. The top-level `verdict` of the JSON is not used. The prompt tells Codex to use `invalid` only when a tool, sandbox, network or permission limit of its environment stops the check, and `fail` when the code or document does not meet the criterion.
6. Render the issue comment from the JSON and post it with `gh`. A `Done head: <SHA>` line directly before `Verified:` names the DONE head. The footer has `Checker: codex` and `Retries: <n> (<reasons>)` if there were retries.

The QA result schema contains: verdict (`pass` or `fail`), one entry per criterion (text, verdict, evidence), the tests (command and result, or "not run" with the reason), and the verified SHA. The rendered comment follows the format in `docs/team/qa-engineer.md`.

### 6.2 Failure handling

Claude does not skip Codex because of a small problem. Each failure type has its own rule:

| Failure | Action |
|---|---|
| Transient: network error, server error, short rate limit, crashed process | Retry up to 3 times. Wait 1, 3 and 10 minutes. If all retries fail, post `## QA: INVALID` with the reason → escalate |
| Timeout (default limit 30 minutes, because QA may start the app) | Retry once. If it times out again, post `## QA: INVALID` with the reason → escalate |
| Output does not match the schema, a criterion is missing or duplicated, or the verified SHA is not `HEAD` | Retry once. Then post `## QA: INVALID` with the reason → escalate |
| Unknown error | Post `## QA: INVALID` with the reason → escalate |
| Codex not installed, not logged in, or usage limit reached | Post `## QA: UNAVAILABLE` with the reason → the orchestrator launches the Claude `qa-engineer` fallback |
| The pre-step (6.1 step 3) fails | Post `## QA: UNAVAILABLE` with the reason → the fallback, as above |
| The issue read (6.1 step 1) fails, or its output is not JSON or cannot be parsed | Post `## QA: UNAVAILABLE` without a Codex run. The reason names the step (`reading issue #<n> with gh issue view failed: <first error line>`), redacted → the fallback, as above |

The overall marker of a run that returned valid JSON follows 6.1 step 5: any criterion `fail` gives `## QA: FAIL` → the engineer; otherwise any criterion `invalid` (a limit of Codex's environment) gives `## QA: UNVERIFIABLE` → the PM (7); otherwise `## QA: PASS`. `## QA: INVALID` stays for the launcher's own causes and still escalates: no acceptance criteria, no valid `## Engineer: DONE`, no `Commits:` line, a DONE head that does not resolve or is not an ancestor of `HEAD` (6.1 step 1), a worktree that cannot be created or reset, and the rows above that end in `## QA: INVALID` → escalate.

The retry limits apply to one launch. The fallback posts a normal QA comment with the footer `Checker: claude (fallback)`.

If the script cannot post its comment, it exits with an error. The issue stays pending (5.3), and the orchestrator escalates.

How Codex reports each error (exit codes, error text, usage limit vs. network error) is in the S2 error table (`docs/research/spike-codex-cli.md`).

**Trust entry.** Each Codex run with a writable sandbox writes `trust_level = "trusted"` for a repo without an entry into `$HOME/.codex/config.toml`. No flag stops this. The set-up adds the entry up front (12.4), so Codex writes nothing during the loop. QA runs are not affected, because `--ignore-user-config` ignores the trust list. Remaining risk: a manual `codex` session in a trusted repo loads the repo's `.codex/config.toml` and `.codex/hooks.json`. A new `.codex/` folder in a diff is a review item.

## 7. QA behavior

QA checks the result against the acceptance criteria. The main evidence is running the behavior, not re-running the engineer's tests (see `docs/research/qa-and-cicd-in-agent-graphs.md`).

For each criterion, QA:

1. Exercises the behavior: runs the command, calls the endpoint, opens the page, reads the document (for a prose task).
2. Judges if a test really covers the criterion, or only mirrors the implementation.
3. Gives a verdict with evidence.

QA also runs the test command from AGENTS.md as secondary evidence. The engineer writes the tests. QA does not change anything in the repo.

A criterion without enough evidence cannot pass.

**Unverifiable criteria.** `## QA: UNVERIFIABLE` means: the checker ran, no criterion failed, and at least one criterion could not be checked because of a limit of the checker's environment (a tool, sandbox, network or permission limit; for example a blocked `api.github.com`, or a crashing browser). In the Codex JSON this is the per-criterion verdict `invalid`; the schema does not change. The comment marks each such criterion `- [ ] … - INVALID`. A criterion that the code or document does not meet is `fail`, not `invalid`. FAIL comes before UNVERIFIABLE (6.1 step 5): the engineer must fix a failing criterion anyway.

`## QA: INVALID` is no longer the result for an unverifiable criterion. It stays for the launcher's own causes (6.2) and for the fallback when the commit range is missing or cannot be used, and it still escalates.

After `## QA: UNVERIFIABLE`, the orchestrator launches the PM with the URL of that QA comment (G2). For each criterion that QA marked `INVALID`, the PM does one of:

- a) It rewrites the criterion so it can be checked from the repo checkout and from the comment text that `qa-codex` passes to Codex (6.1 step 1), for example by writing the expected values into the criterion, with the same intent and scope. Then it posts `## PM: GROOMED`.
- b) It leaves the criterion unchanged when the limit is already gone (a fix has landed), and names the commit or issue of that fix. Then it posts `## PM: GROOMED`.
- c) It posts `## PM: NEEDS OWNER` when the only way to make the criterion checkable changes its intent or scope (dropping it, weakening it, moving it out of scope), needs an edit of the project settings files (the committed and the local Claude Code settings JSON files in `.claude/`, 5.9), of `.claude/hooks/`, or of the Codex sandbox arguments (`QA_SANDBOX`) in `qa-codex`. The orchestrator escalates. If the criterion only waits on an open issue of this repo, the PM posts `## PM: WAITING` with one line `Waiting on: #<N>` instead; the orchestrator parks the issue and the PM grooms it again when #N is closed (5.5).

The `## PM: GROOMED` comment lists each criterion the PM changed, with the old text, the new text, and one line on why the intent is the same. The PM changes no criterion that QA did not mark `INVALID`.

Then the engineer runs as after any `## PM: GROOMED` (G3). If the code already meets the regroomed criteria, the engineer makes no commit and posts a new `## Engineer: DONE` whose `Commits:` line starts at the base of the previous `## Engineer: DONE` and ends at `HEAD`, and says that no code change was needed. Then QA runs as usual (G4).

`## QA: UNVERIFIABLE` counts as a return (G7), like `## QA: FAIL` and `## Engineer: BLOCKED`. So a PM, engineer, QA cycle that keeps hitting a limit escalates after 3 returns.

Example (issue #10). Criterion 11 says that the label descriptions in the README match the labels of the repo. Codex cannot check it, because the sandbox blocks the GitHub label read (`gh label list`). No other criterion fails, so `qa-codex` posts `## QA: UNVERIFIABLE` with a `Reason:` line that names criterion 11. The orchestrator launches the PM with the URL of that QA comment. The PM reads the three label descriptions and writes them into criterion 11, so the check stays strict and works from the checkout. Its `## PM: GROOMED` comment lists the old text of criterion 11, the new text, and why the intent is the same: the README must still match the repo labels; only the expected values now stand in the criterion. The engineer finds that README.md already matches, makes no commit, and posts `## Engineer: DONE` with the base of the previous DONE and `HEAD` in the `Commits:` line. Codex QA compares README.md with the values in the criterion and posts `## QA: PASS`. The orchestrator closes the issue. If the only way had been to drop criterion 11, the PM would have posted `## PM: NEEDS OWNER`.

If QA needs a tool that is not in the lockfile or the set-up, the result is `## QA: FAIL` back to the engineer (undeclared dependency). QA does not install anything and does not escalate for an install.

`docs/team/qa-engineer.md` gets this behavior and one delivery rule: when run by `qa-codex`, return JSON only and do not post a comment. The Claude fallback posts its comment as before.

## 8. Codex review skill

- Skill: `.agents/skills/codex-review/SKILL.md`, named `codex-review`.
- Trigger: the owner, in natural language ("let Codex review the spec") or with `/codex-review`. Claude derives the target from the conversation: a file, a folder, or a commit range. The skill does not start by itself in the loop.
- AGENTS.md gets one line: "When the owner asks for a Codex review, use the `codex-review` skill."
- What it does:
  1. Runs `codex exec` read-only with a normal review prompt (not adversarial) and a findings schema. The model and the reasoning effort are set explicitly (start with `medium`, as for QA).
  2. Writes `docs/reviews/<date>-<topic>-codex-review.md`, always.
- Findings format: adapted from the Codex plugin's review schema (openai-codex plugin for Claude Code, with credit): verdict (`approve` or `needs-attention`), summary, findings (severity, title, body, file, lines, confidence, recommendation), next steps.
- The code that runs Codex and captures its output is shared with `qa-codex`.
- Every review ends the same way: each finding gets a decision (taken, partly taken, or rejected, with a short reason), written into the review file. Then the review file is committed. The decisions are made by whoever works on the review: the owner together with Claude, or Claude alone. When Claude works alone, it commits the review file together with the changes it made.
- `docs/process.md` gets one rule: "Do not read old reviews in `docs/reviews/` unless the owner points to one."
- For an adversarial review, the owner uses `/codex:adversarial-review` from the Codex plugin. The kit does not wrap it.

## 9. Lovable lane and paint-math

### 9.1 Repo layout

- `paint-math` is a new GitHub repo. The kit is copied in with the README set-up instructions.
- `frontend/` is a git submodule. It points to the repo that Lovable manages.
- The owner creates the Lovable project, connects it to GitHub and makes the Lovable repo public. No MCP tool can make the GitHub connection (S3). A public repo needs no read access for the loop machine, the engineer fetch or the QA pre-step.
- The submodule tracks the branch that Lovable syncs (the default branch, `main`).
- Nobody edits `frontend/` locally. All frontend changes go through Lovable.

### 9.2 `frontend-engineer`

- Agent file: `.claude/agents/frontend-engineer.md`, with the Lovable MCP tools, Bash, and read tools.
- Role text: a section "Lane `frontend`" in `docs/team/software-engineer.md`.

Flow:

1. Note the base SHA of the main repo: `git rev-parse HEAD`.
2. Send Lovable the goal and the acceptance criteria of the issue in plain words. Lovable does not know about issues or git.
3. Wait until Lovable has finished and its commit is on GitHub (detection: the method in the S3 findings). If Lovable pauses (`awaiting_input`) on its plan step or with a question, review the plan against the goal, the criteria and the constraints of the issue, and answer with a follow-up message: "implement this plan", the corrections, or the answer from the issue. A new message supersedes the pause. Only a credit or spend-limit check-in needs the owner: post `## Engineer: BLOCKED`.
4. Review the diff of Lovable's commit against the issue. If it does not fit, send Lovable a follow-up message. Repeat until all criteria are met, within the time budget (default 60 minutes per launch, follow-up messages after a pause included). When the budget runs out, post `## Engineer: BLOCKED` with what is missing.
5. Fetch the submodule and pin it to the exact commit of Lovable's change (the merge commit whose `X-Lovable-Edit-ID` trailer matches the edit id; the method is in the S3 findings). Do not take the newest commit of the branch without this check. Commit the pointer update.
6. Run the project test command, if one exists.
7. Post `## Engineer: DONE` with `Commits: <base>..<head>`.

Lovable cost is not a limit. Time is.

### 9.3 QA for frontend issues

Codex checks the range, including the submodule content (`git diff --submodule=diff <base>..<head>`, with the submodule commits fetched). Following section 7, QA exercises the UI in a headless browser (Playwright). The dependencies and the browser are installed by the `qa-codex` pre-step (6.1). Codex starts the app and runs the browser check in one command, because a background process does not survive into the next Codex command (S2).

Browser-based QA is a precondition of the frontend lane. S2 showed that `qa-codex` can run Playwright with headless Chromium in the localhost-only profile. Build, tests and code reading alone are not enough evidence for a UI criterion.

Open point: S3 found that `git diff --submodule=diff` needs no network only in the clone where the engineer fetched the `frontend/` commits. A new QA worktree may not have the submodule objects. The pre-step fetches them (outside the sandbox, no credentials needed for the public Lovable repo). The plan checks how the worktree gets them.

### 9.4 Demo scope

Two issues in paint-math, both through PM → engineer → Codex QA → close with the hooks active:

1. Lane `frontend`: the canvas shows the curve of an equation that the user enters (Lovable).
2. Lane `default`: a small non-UI part, for example an equation parser and validator with tests (Claude engineer).

The owner can replace these issue ideas. The issues live in the paint-math repo.

## 10. The `later` label

- `docs/process.md` (done in this session): "Issues with the label `later` are out of scope for the current implementation. Do not work on them."
- The orchestrator lists only issues with `ready` and without `later` or `needs-owner`. The PM grooms only the issue it gets.
- Guarantee G1 denies every launch on an issue with `later`, also if it has `ready` by mistake.
- The PM gives each follow-up issue (out-of-scope item) the label `later`.
- The owner removes `later` and adds `ready` to start work on an issue.

## 11. Files

| File | Change |
|---|---|
| `.claude/hooks/` | New: guard hook, issue-state module |
| `.claude/settings.json` | New: hook registration, allow and deny rules (5.9) |
| `docs/checks/hook-activation.md` | New: acceptance test checklist (5.9) |
| `.claude/agents/frontend-engineer.md` | New |
| `.claude/agents/qa-engineer.md` | Unchanged pointer; now the fallback |
| `scripts/qa-codex` (Python) + QA result schema | New |
| `.agents/skills/codex-review/` | New: skill, review schema, render script |
| `.github/workflows/ci.yml` | New |
| `tests/` | New |
| `docs/team/orchestrator.md`, `pm.md`, `software-engineer.md`, `qa-engineer.md` | Changed (sections 4, 5.8, 7, 9.2, 10) |
| `docs/process.md` | Changed (sections 5.8, 8, 10) |
| `docs/task-template.md` | Lane values `default`, `frontend` |
| `AGENTS.md` | Test command; issue list command; one line for Codex reviews |
| `README.md` | Set-up section |

The exact paths can change in the plan if a spike shows a reason.

## 12. Tests, CI, README

### 12.1 Tests

- pytest for the hook checks, with synthetic issue JSON and a synthetic git state.
- pytest for the hook entry point: a failing `gh`, a failing `git`, and an internal error each produce a deny response.
- pytest for `qa-codex`, with a fake `codex` command for each failure type (retry, timeout, invalid output, unavailable).
- pytest for the review renderer (JSON → review file).
- No network in the tests.
- AGENTS.md gets the real test command: `uv run --with pytest pytest`.

### 12.2 CI

`.github/workflows/ci.yml` runs the tests on each push and pull request. The graph does not read CI results in v1.

### 12.3 End-to-end proof

- Dogfooding: after the hook wiring task is closed, all later tasks of this repo run with the hooks on.
- paint-math: the two demo issues (section 9.4).

### 12.4 README set-up section

- Prerequisites: `gh` (logged in), `uv`, Codex CLI (logged in), the Claude Code plugin `lovable` (frontend lane only; the tool names in `frontend-engineer.md` depend on it).
- Codex trust entry: add `trust_level = "trusted"` for the project to `$HOME/.codex/config.toml` (6.2), so Codex writes nothing during the loop.
- Frontend lane only: create the Lovable project, connect it to GitHub by hand, and make the Lovable repo public (9.1).
- Frontend lane only: the accepted risk of the QA frontend pre-step: it runs repository-controlled code (lifecycle scripts, `.npmrc`/`bunfig.toml`, the Playwright CLI) outside the sandbox with the user's access, including packages that agents add; dependency and config changes are review items (6.1 step 3).
- Hook activation and the acceptance test (5.9).
- Files to copy: AGENTS.md, CLAUDE.md, `docs/process.md`, `docs/team/`, `docs/task-template.md`, `.claude/agents/`, `.claude/hooks/`, the hooks and permissions blocks of `.claude/settings.json`, `docs/checks/`, `scripts/qa-codex` and its schema, `.agents/skills/codex-review/`, the symlink `.claude/skills` → `.agents/skills`.
- Files to adjust: the project description and test command in AGENTS.md; the `frontend/` submodule and the `frontend` lane (Lovable only).
- Labels to create: `ready`, `needs-owner`, `later`, `waiting`.
- The paint-math task checks these instructions. Missing steps are fixed in the README.

## 13. Spikes

Each spike is a plan task. The output is a short findings file in `docs/research/`. If a finding changes this design, the owner decides before the dependent tasks start.

Status 2026-09-26: all three spikes are done (`spike-claude-code-hooks.md`, `spike-codex-cli.md`, `spike-lovable-mcp.md`). The owner decisions on their consequences are merged into sections 5, 6, 7, 8, 9 and 12. Nothing from S1–S3 is open, except the submodule objects in the QA worktree (9.3).

| # | Spike | Questions | Blocks |
|---|---|---|---|
| S1 | Claude Code hooks | Does a hook before a subagent launch see the agent type and the prompt? Can it deny with a reason? Does it work in auto mode? Can a Bash hook reliably match `qa-codex` and `gh issue close`? Do hooks fire for calls inside subagents? Can a hook post a comment (side effect) before the call runs? Which hook output reliably denies a call (exit code or deny response), and what happens when the hook script crashes or times out? | Section 5 |
| S2 | Codex CLI | `--output-schema` and `-o` behavior. What each sandbox mode allows: run tests, run the app, write temp files, run a headless browser. Can `qa-codex` run a headless browser (for example Playwright), and with which sandbox setting? How each error shows (network, rate limit, usage limit, auth, not installed): exit codes, error text. Timeout behavior | Sections 6, 8, 9.3 |
| S3 | Lovable MCP | How to detect that a Lovable message has finished. When Lovable's commit reaches GitHub, and how to identify the exact commit of one Lovable change. Can the GitHub connection be made through MCP? | Section 9 |
