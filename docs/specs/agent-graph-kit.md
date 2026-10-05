# agent-graph-kit behavior spec

- Status: living. This file says how the kit behaves now.
- It holds what the code implements and no other file states: the principles, the roles and lanes, the launch contract with the guarantees G1 to G8, the result markers, the `qa-codex` contract, the stage model and the doc lifecycles.
- The code wins. Where this file and the code differ, the code holds, and this file is fixed in the same commit as the change that made it false.
- The process prose stays in [docs/process.md](../process.md), the role files in [docs/team/](../team/), the agent files in [.claude/agents/](../../.claude/agents/) and the skills in [.agents/skills/](../../.agents/skills/). This file links them and does not repeat them.
- History: the v1 spec ([docs/archive/2026-09-25-agent-graph-kit-v1-spec.md](../archive/2026-09-25-agent-graph-kit-v1-spec.md)) and the stages spec ([docs/archive/2026-10-01-stages-and-planner-spec.md](../archive/2026-10-01-stages-and-planner-spec.md)) are archived unchanged. Scope, spikes, the file list and the demo of v1 stay there.

The code: [.claude/hooks/guard.py](../../.claude/hooks/guard.py), [.claude/hooks/issue_state.py](../../.claude/hooks/issue_state.py), [.claude/hooks/not_started.py](../../.claude/hooks/not_started.py), [.claude/hooks/outage_stop.py](../../.claude/hooks/outage_stop.py), [.claude/settings.json](../../.claude/settings.json), [scripts/qa-codex](../../scripts/qa-codex), [scripts/codex_exec.py](../../scripts/codex_exec.py) and [scripts/qa-result.schema.json](../../scripts/qa-result.schema.json).

## Principles

| ID | Principle |
|---|---|
| P1 | **Prose guides, hooks check.** `docs/process.md` and the role files stay the main description of the process. Hooks check only the prescribed handoff calls. They are not a security boundary: a call outside the prescribed ones (for example `gh api`, or a comment written by hand) is not checked. |
| P2 | **Facts only.** Hooks check facts: labels, comment markers, SHAs, git status, blocker and sub-issue links. No LLM or Jev judgment blocks anything. |
| P3 | **State lives on the issue.** Hooks and scripts read the state with `gh`. Nothing depends on what the orchestrator remembers. |
| P4 | **Few files.** The kit adds as few agent-facing files as possible. Adopting the kit means merging into existing files, never appending a second set. |
| P5 | **No secrets.** No keys in commits, issues, comments or reviews. Examples are synthetic. |

## Roles and lanes

The entry command sets the role of the main session; the rules are in "Roles" of [docs/process.md](../process.md#roles).

| Role | Runs on | Launched through | Role file | Agent file |
|---|---|---|---|---|
| Orchestrator | the main session, started with `/goal …` | – | [docs/team/orchestrator.md](../team/orchestrator.md) | – |
| Planner | the main session, started with `/stage-start` (intake, stage set-up); the subagent `planner` (stage review) | the subagent: a subagent launch on a stage issue | [docs/team/planner.md](../team/planner.md) | [.claude/agents/planner.md](../../.claude/agents/planner.md) |
| PM | the subagent `pm` | a subagent launch | [docs/team/pm.md](../team/pm.md) | [.claude/agents/pm.md](../../.claude/agents/pm.md) |
| Engineer, lane `default` | the subagent `software-engineer` | a subagent launch | [docs/team/software-engineer.md](../team/software-engineer.md) | [.claude/agents/software-engineer.md](../../.claude/agents/software-engineer.md) |
| Engineer, lane `frontend` | the subagent `frontend-engineer`, which drives Lovable through MCP | a subagent launch | [docs/team/software-engineer.md](../team/software-engineer.md), "Lane `frontend`" | [.claude/agents/frontend-engineer.md](../../.claude/agents/frontend-engineer.md) |
| QA (default checker) | Codex (`codex exec`) | `scripts/qa-codex`, through Bash | [docs/team/qa-engineer.md](../team/qa-engineer.md) | – |
| QA fallback | the subagent `qa-engineer` | a subagent launch, only after `## QA: UNAVAILABLE` (G5) | [docs/team/qa-engineer.md](../team/qa-engineer.md) | [.claude/agents/qa-engineer.md](../../.claude/agents/qa-engineer.md) |

Every role that runs as a subagent posts its own result with `gh`. `qa-codex` posts the Codex result itself.

The guard maps each guarded agent to a role (`AGENT_ROLE` in `guard.py`): `pm` to `pm`, `software-engineer` and `frontend-engineer` to `engineer`, `qa-engineer` to `qa`, `planner` to `planner`. Other subagent types are not guarded.

**Lanes.** An issue body names its lane in one line `Lane: default` or `Lane: frontend`. The guard reads the value from the lines outside fenced code blocks; when lines disagree, the value is unknown. Each lane has one engineer agent (`AGENT_LANE` in `issue_state.py`):

| Lane | Engineer agent |
|---|---|
| `default` | `software-engineer` |
| `frontend` | `frontend-engineer` |

G3 checks the pair. The lane `frontend` needs a repo with a Lovable submodule `frontend/` (see "Lane `frontend`" in `docs/team/software-engineer.md` and "Frontend lane (optional)" in the README).

## Launch contract

Three hooks in `.claude/hooks/`, registered in `.claude/settings.json`, guard the handoffs:

| Hook | Event and matcher | Command | Job |
|---|---|---|---|
| `guard.py` | `PreToolUse`, `Agent\|Bash\|SendMessage` | `uv run --script …/guard.py \|\| { echo 'guard hook failed: call denied' >&2; exit 2; }`, timeout 120 s | checks each guarded call and posts the launch comment |
| `not_started.py` | `PermissionDenied`, `Agent\|Bash\|SendMessage` | `uv run --script …/not_started.py`, timeout 120 s | posts the not-started comment and writes outage evidence |
| `outage_stop.py` | `SubagentStop`, no matcher | `uv run --script …/outage_stop.py \|\| true`, timeout 120 s | posts the stop comment |

The scripts use only the Python standard library and run with `uv run --script`. The checks in `issue_state.py` are pure functions; the guard reads the facts with `gh` and `git` and passes them in.

### Guarded calls

The guard runs before each tool call of the orchestrator and of its subagents. It guards only these calls:

| Call | Role |
|---|---|
| Subagent launch (tool `Agent`, or its old name `Task`) of `pm` | `pm` |
| Subagent launch of `software-engineer` or `frontend-engineer` | `engineer` |
| Subagent launch of `qa-engineer` | `qa` (fallback) |
| Subagent launch of `planner` | `planner` |
| `SendMessage` (a continuation of a role agent) | the role in its launch line; never `planner` |
| Bash command `scripts/qa-codex ROLE=qa ISSUE=<n>` | `qa` |
| Bash command `gh issue close <n>` | close |
| A Bash command that may write to `.claude/settings*.json` | – (denied, G8) |
| Any other Bash command that runs `gh issue close` or `qa-codex`, or may run it | – (denied, G1) |

All other calls pass. Examples: a subagent launch without `subagent_type` or of another type, the Codex review skill, and Bash commands that run neither, also when their text mentions the words.

Comment commands are not checked. The check G9 that kept every comment call in one exact form was removed in [#90](https://github.com/Lighfe/agent-graph-kit/issues/90). A comment command goes through G8 and the Bash rule of G1 like any Bash command. That agents post with `gh issue comment <n> --body-file <literal path>`, and that agents never post a `## Owner: …` comment, are rules of `docs/process.md`, not checks. Other posting routes stay unchecked ([#76](https://github.com/Lighfe/agent-graph-kit/issues/76)): `gh api`, Codex inside the QA launcher, and MCP tools with GitHub write access.

### Bash rule of G1

G8 runs first for every Bash command. Then the guard reads the command with its shell tokenizer (`_lex` in `guard.py`, [#107](https://github.com/Lighfe/agent-graph-kit/issues/107)) and decides by the commands that really run:

- **Simple commands.** The guard looks at every simple command: the top-level ones and, recursively, the ones inside `$(…)`, backticks, `<(…)`, `>(…)` and the substitutions inside an unquoted here-document body. The body text of a here-document is not a command. An array assignment `NAME=(…)` is one word, as bash reads it (so the `#` in `x=(a)#` starts no comment); the substitutions in its elements count, and an operator other than a newline inside it makes the command unreadable. The command is read twice: once with `case` as a reserved word anywhere, and once only where bash reads one (at the start of a command, also after `time`, `time -p`, `time --`, `coproc`, `coproc NAME`, `function NAME`). A simple command found in either reading counts.
- **Command word.** The first word after the assignment words (`NAME=value`), the redirections with their target word (`>/dev/null`, `{fd}>file`, `2>&1`) and the reserved words `{`, `}`, `!`, `if`, `then`, `else`, `elif`, `do`, `while`, `until`. Words are compared after quote removal, so `cl''ose`, `c\lose` and `$'close'` are `close`.
- **Close run.** The command word is `gh` or a path whose last part is `gh`, and the later words hold a word `issue` and, after it, a word `close`.
- **Launcher run.** The command word is `qa-codex` or a path whose last part is `qa-codex`.
- **Old word rule.** A text triggers it if it holds both words `gh` and `close` (Python regexes `\bgh\b` and `\bclose\b` with `re.ASCII`, case-sensitive), or the text `qa-codex`. A command triggers it if its text, or a copy with every backslash-newline removed, does.
- **Runner rule (fail-closed).** `RUNNER_COMMANDS` in `guard.py` lists commands that can run another command from their arguments, stdin or a here-document (for example `command`, `env`, `xargs`, `find`, `eval`, `source`, `bash`, `sh`, `python3`, `uv`, `make`, `ssh`). A simple command whose command word (or its last path part) is in this list counts as a run when the whole command triggers the old word rule. Nothing else counts as a run: a comment, an array assignment or an argument that mentions the words decides nothing.
- **Allowed forms.** A command with a run is a guarded call only if its original text matches one of these patterns with Python `re.fullmatch` (`CLOSE_FORM` and `QA_FORM`):
  - close: `gh issue close ([1-9][0-9]*)(?:(?: --reason | --reason=| -r )(?:completed|'not planned'|"not planned"))?[ \t]*\n?`
  - qa: `scripts/qa-codex ROLE=qa ISSUE=([1-9][0-9]*)[ \t]*\n?`

  A match is not an allow on its own: the call then goes through the checks, the lock, the deadline and the launch comment like every guarded call.
- **Deny.** Every other command with a run is denied with `G1:` before any `gh` or `git` call. The message names the two forms, says that the run must be the whole command (no operators, redirections, wrappers or substitutions), names the Bash tool's `run_in_background` option instead of `&`, and says that text which only mentions the words passes, for example a body written with a quoted here-document `<<'EOF'`.
- **Unreadable command.** When the tokenizer cannot read the command (also when it is nested too deeply), the command is denied with `G1:` if it triggers the old word rule, and passes otherwise.

Examples that pass: `cat scripts/qa-codex`, `git commit -m "Fix gh close handling"`, `echo gh issue close 5`, `gh issue view 5 | grep close`, `gh pr close 5`, `ls # gh close later`, and an issue body written with `cat > /tmp/x/body.md <<'EOF'` whose lines name the close command.

Accepted false denies: `bash -c 'echo gh issue close 5'`, `echo gh close | xargs echo`, a Python here-document that mentions both words, and real runs not in the exact form (`/usr/bin/gh issue close 5`, `command gh issue close 5`, `gh  issue close 5`). Such text can be written without a runner, for example with the Write tool.

Known limits (P1): variables and other expansions in the command word (`$GH issue close 5`, `"$x"gh issue close 5`), brace expansion, globs, other letter case, runners not in the list, a script file that holds a close run, and calls outside the prescribed ones (`gh api`, `gh issue edit --state closed`).

### Launch line

A guarded launch carries exactly one line `ROLE=<role> ISSUE=<n>`: in the subagent prompt, in the `SendMessage` message, or as the arguments of `qa-codex`. `<role>` is `pm`, `engineer`, `qa` or `planner`. The line must be a whole line (trailing spaces and a carriage return are ignored). A launch or a `SendMessage` with no such line or with two is denied; the message names the line as `ROLE=<pm|engineer|qa|planner> ISSUE=<number>`. The role must match the agent (`AGENT_ROLE`); any other pair is denied with `G1: launch line role is <role>, expected <role> for agent <agent>`.

Close needs no launch line: the guard reads the issue number from the close form. Close posts no launch comment.

### Launch comments

When the guard allows a launch, it posts a launch comment (the receipt) on the issue before the call runs. The three comment forms the hooks post:

```
## Launch: engineer (attempt 3)
Agent: software-engineer
Call: 3f2a9c01b7de
```

```
## Launch not started: engineer (attempt 3)
Call: 3f2a9c01b7de
Reason: Auto mode could not evaluate this action and is blocking it for safety
```

```
## Launch stopped by outage: pm (attempt 1)
Call: 3f2a9c01b7de
Reason: Classifier unavailable
```

- `## Launch:` is posted by `guard.py`. A continuation posts `## Launch: <role> (continued, round <n>)`. The number is the count of all earlier receipts of that role (voided ones included) plus one, for attempts and rounds alike. `Agent:` is the subagent type, `qa-codex`, or the `SendMessage` target. The planner only has the `(attempt <n>)` form.
- The `Call:` line is the call hash: the first 12 hex characters of the SHA-256 of the event's `tool_use_id`. The raw id is never posted. An event without a string `tool_use_id` gets a receipt without a `Call:` line, and such a receipt is never voided.
- `## Launch not started:` is posted by `not_started.py` (see "Not started and stopped by an outage").
- `## Launch stopped by outage:` is posted by `outage_stop.py` (same section).

The receipts are the log; there is no other.

### Only the owner's comments count

The issue state is read with `gh issue view <n> --json number,state,labels,body,comments`. Only comments whose `authorAssociation` is exactly `OWNER` count ([#70](https://github.com/Lighfe/agent-graph-kit/issues/70)); all others are ignored, as if they were not on the issue. This holds for every comment the hooks and `qa-codex` read: receipts, not-started and stop comments, result markers and `## Owner: RESUME`. So a stranger's comment cannot resume, pass, block, void a receipt or close an issue. The agents and hooks post with the owner's `gh` login, so their comments count.

Missing author data is an error: a comment without a string `body` or a string `authorAssociation`, or a missing `comments` list, makes `issue_state.parse_issue` fail (the one parse point for the guard, the two other hooks and `qa-codex`). The guard then denies with `guard error`, and the other hooks post nothing. Organization-owned repos are not supported yet: their owner's comments are not `OWNER` ([#75](https://github.com/Lighfe/agent-graph-kit/issues/75)).

### Not started and stopped by an outage

**Not started.** The guard runs before the permission check, so it cannot see a later denial. When auto mode denies a call, Claude Code runs `not_started.py` with the same `tool_use_id`. The hook classifies the call with the guard's rules. For a guarded launch of `pm`, `engineer`, `qa` or `planner` (also `qa-codex` and a continuation; not close, and not a call the guard denies itself) it posts the not-started comment when the newest receipt has that role, the matching `Call:` line, no result of its role and no `## Owner: RESUME` after it, and is not yet voided. `Reason:` is the first line of the deny reason, cut to 200 characters, or `(no reason given)`.

**Stopped by an outage** ([#52](https://github.com/Lighfe/agent-graph-kit/issues/52)). When `not_started.py` sees a denial inside a subagent (the event has an `agent_id` of 1 to 64 letters, digits, `_` or `-`) whose reason's first line starts with `Classifier unavailable`, `Auto mode could not evaluate this action and is blocking it for safety` or `Auto mode unavailable` (`NO_VERDICT_REASONS`), it writes that first line as is (trailing whitespace kept), cut to 200 characters, to `<git dir>/agent-graph-kit-outage/<agent_id>`. This is done for any matched call; a failure there never stops the not-started comment. The file is in the git dir, so the clean-tree check of G1 is not affected. A denial with a verdict (a classifier judgment, `Permission denied`) is no evidence.

When a subagent ends, `outage_stop.py` runs. Without an evidence file for its `agent_id` it ends at once, with no transcript read and no `gh` call. Otherwise it reads and deletes the file (at every stop, so evidence counts for one round only), reads the launch line from the first user message of the agent's transcript, and checks that `agent_type` has that role. It posts the stop comment when the newest receipt on that issue has that role, a `Call:` line, no result of its role and no `## Owner: RESUME` after it, and is not yet voided. `Reason:` is the evidence content, unchanged. The comment holds no agent id, no transcript text and no raw `tool_use_id`.

**Voided receipts.** A receipt is voided when a later not-started or stop comment has the same `<role> (…)` part and the same `Call:` value. A voided receipt counts for nothing (pending, misses, validity, current result, G2, returns) except the attempt number. A not-started or stop comment is not a result, not a receipt and not `## Owner: RESUME`; one that matches no receipt changes nothing. So after a voided receipt the orchestrator launches the same step again; it is not a return.

Both hooks hold the guard's lock from reading the issue until the comment is posted, within the guard's deadline. They print nothing to stdout and always exit 0. Known limit: only denials of `Agent`, `Bash` and `SendMessage` calls count as outage evidence; a subagent stopped only by denials of other tools stays pending. A denial that fires no `PermissionDenied` event (a manual "No", a `permissions.deny` rule, another `PreToolUse` hook, Esc) leaves the issue pending ([#53](https://github.com/Lighfe/agent-graph-kit/issues/53)).

What an agent does after a deny with a verdict is the rule "Denied action" in [docs/process.md](../process.md#rules) and "A tool problem that an issue can fix" in [docs/team/pm.md](../team/pm.md#a-tool-problem-that-an-issue-can-fix).

### Continuation

The orchestrator may continue a role agent with `SendMessage` instead of a new launch. The message carries the launch line. The guard runs the same checks as for a new launch of that role, with two differences: the agent part of the PM check and of G3 does not apply (the target is a name, not a type), and a continuation with `ROLE=qa` is checked as the fallback (G5), since only `qa-engineer` can be continued. A continuation counts as a launch for validity, pending and returns. After one miss (see "Valid result, pending and current result"), the orchestrator may continue the agent of the miss once, or launch the same role once more, without the owner; the continuation gets the receipt `(continued, round <n>)`, and when it also ends without a result, that is two misses in a row ([#132](https://github.com/Lighfe/agent-graph-kit/issues/132)). A planner cannot be continued: a `SendMessage` with `ROLE=planner` is denied with a message that starts with `G1:` and expects a new launch of the agent `planner` ([#99](https://github.com/Lighfe/agent-graph-kit/issues/99)).

### Valid result, pending and current result

Comment order is the order of the `gh` comments array. Only first lines count, and voided receipts are left out.

- A result comment is **valid** when its first line is a result marker of a role (see "Result markers") and it comes after the newest receipt of that role. An old result from an earlier attempt is ignored.
- A **miss** ([#132](https://github.com/Lighfe/agent-graph-kit/issues/132)) is a receipt that has no result marker of its role and no `## Owner: RESUME` between it and the next receipt (or the end of the comments).
- **Two misses in a row**: the two newest receipts are of the same role and both are misses (so no `## Owner: RESUME` comes after the older one). A `## Owner: RESUME` resets the count: receipts before the newest `## Owner: RESUME` never count toward two misses in a row.
- The issue is **pending** when the newest receipt is a miss. While an issue is pending, G1 allows only the role of the miss to go on, once: one continuation or one new launch of that role, without the owner (the planner only with a new launch). Every other guarded call is denied (G1), also `gh issue close` on an issue without the label `stage`. After two misses in a row every guarded call is denied; the orchestrator escalates, and the owner continues with `## Owner: RESUME`. A miss is not a return. For the role checks after G1, the guard leaves the receipt of the miss out (`without_miss` in `issue_state.py`), so a miss does not change the current result (a receipt makes the earlier results of its role invalid) and a first PM launch that missed counts as no receipt yet (G2).
- The **current result** is the newest comment that is a valid result or `## Owner: RESUME`. For a variant line that passes the resume match, the current result is the canonical `## Owner: RESUME`.
- The **resume match** ([#131](https://github.com/Lighfe/agent-graph-kit/issues/131), `is_resume` in `issue_state.py`): a comment's first line is the owner's resume marker when `" ".join(line.split()).casefold() == "## owner: resume"`. So leading and trailing whitespace is removed, each run of whitespace inside (spaces, tabs, CR) counts as one space, and letter case is ignored: `## OWNER: Resume` counts, `## Owner: RESUME later`, `# Owner: RESUME`, `##Owner: RESUME` and `## Owner:RESUME` do not. Only the owner's comments count, as for every marker. Everywhere in this spec, `## Owner: RESUME` as a comment on the issue means a comment that passes the resume match. All other markers (result markers, receipts, not-started and stop comments) match exactly. The constant `RESUME` and every deny message name exactly `## Owner: RESUME`.
- The newest valid `## Engineer: DONE` gives the commit range (G4, `qa-codex`). Its `Commits: <base>..<head>` value, and the `Verified: <SHA>` value of a QA result, are read from the lines outside fenced code blocks; lines that disagree make the value unknown.

### Checks

The guard allows a guarded call only when every check of its role passes. It checks G1 first, then the role checks in order, and denies with the first failing one.

| Call | Checks |
|---|---|
| `pm` (new launch: agent `pm`) | G1, G2, G7 |
| `engineer` | G1, G3, G7 |
| `qa` with `qa-codex` | G1, G4 |
| `qa` with `qa-engineer`, or a `qa` continuation | G1, G5 |
| `planner` (new launch of the agent `planner` only) | G1 on the planner path |
| close of an issue without the label `stage` | G1, G6 |
| close of an issue with the label `stage` | G1 and G6 on the stage path |
| any Bash command | G8, before everything else |

A `pm` call whose agent is not `pm`, or a `qa` call whose agent is neither `qa-codex` nor `qa-engineer`, is denied with `G1:`. Every check reads only the owner's comments.

### G1 Launch preconditions

For a launch or continuation of `pm`, `engineer` or `qa`, and for the close of an issue without the label `stage`, in this order:

1. The facts are for the issue of the call, and the issue is open (`G1: issue #<n> is closed, expected an open issue`).
2. It has no open blocker (not for close; see below).
3. It has the label `ready`.
4. It has neither `later` nor `needs-owner`.
5. The working tree is clean (`git status --porcelain` is empty). This works because no role may leave uncommitted work, except a role that ended without a result: a role that ended early may leave uncommitted work, and the go-on finishes or resets it ([#142](https://github.com/Lighfe/agent-graph-kit/issues/142)). So a dirty tree does not deny a launch or continuation of `pm`, `engineer` or `qa` while the issue is pending after one miss of that same role (the role match of step 7, where `qa` covers `qa-codex` and `qa-engineer`); G1 goes on with steps 6 and 7, and the role checks run as usual. The guard matches the dirty tree to the miss by issue state only, never by file content, and the facts are per issue, so a call on another issue never matches. With a dirty tree and two misses in a row, the deny is the two-misses message of step 7, as with a clean tree. Every other call with a dirty tree is denied with `G1: working tree is not clean, expected a clean tree (git status --porcelain empty)`: also a call of another role on the pending issue, the close, and the planner (the planner path below has no such exception).
6. Not voided twice (not for close): the two newest receipts are not both voided while no result marker and no `## Owner: RESUME` comes after the older one. The message starts with `G1: issue #<n>: the last 2 launches` and names `## Owner: RESUME`.
7. The pending rule ([#132](https://github.com/Lighfe/agent-graph-kit/issues/132), see "Valid result, pending and current result"). When the newest receipt is a miss:
   - two misses in a row deny with a message that starts with `G1: issue #<n> is pending: the last 2 launches of <role> ended without a result`, names both receipts and `## Owner: RESUME`. It never contains `the last 2 launches did not start`, which stays the voided-twice text of step 6;
   - a call of another role deny with `G1: issue #<n> is pending: <receipt> has no result, so only <role> may go on, expected one continuation or new launch of <role>, a result of <role> or ## Owner: RESUME`;
   - otherwise (one miss, a call of its role) G1 passes, the role checks run as usual, and the call gets a new receipt, numbered as always (`(attempt <n>)` or `(continued, round <n>)`).

**Blockers** ([#64](https://github.com/Lighfe/agent-graph-kit/issues/64)). Blockers are native "blocked by" links, also to other repos. For every role launch and continuation except the planner, and never for close, the guard runs two reads inside the lock (read form from the #95 report, `docs/research/spike-sub-issues-and-blockers.md`):

- the blocker list: `gh api --paginate repos/{owner}/{repo}/issues/<n>/dependencies/blocked_by --jq '.[] | {repo: .repository.full_name, number, state}'` (all pages, counted per item, no order rule),
- the open-blocker count: `gh api repos/{owner}/{repo}/issues/<n> --jq .issue_dependencies_summary.blocked_by`.

The issue has an open blocker when an entry is `open`, or when the count is greater than the number of `open` entries (a blocker the login cannot read). The deny names the open blockers as `<owner>/<repo>#<number>`, and for an unreadable one says that the count shows an open blocker the list does not hold. An item without a string `<owner>/<name>` repo, a positive integer `number` or a `state` of `open` or `closed`, or a count that is not one non-negative integer, denies with `guard error`.

**Planner path** ([#99](https://github.com/Lighfe/agent-graph-kit/issues/99)). A new launch of the agent `planner` with `ROLE=planner ISSUE=<n>` is allowed exactly when the issue is open, has the label `stage` (`ready` is neither required nor denied), the stage has ended (the stage issue has at least one sub-issue and every sub-issue is closed, [#119](https://github.com/Lighfe/agent-graph-kit/issues/119)), has neither `later` nor `needs-owner`, the working tree is clean, it is not voided twice, and the pending rule of step 7 lets it pass: after one planner miss, one new launch of the agent `planner` is allowed; after two planner misses in a row it is denied with the two-misses message ([#132](https://github.com/Lighfe/agent-graph-kit/issues/132)). A `SendMessage` with `ROLE=planner` stays denied. The guard runs no blocker read on this path: the "blocked by" links between stage issues order the start of stages, and a stage review reviews a stage that has run. G2 to G7 do not apply. The receipt is `## Launch: planner (attempt <n>)`, and the not-started and stop comments work for it as for the other roles. An issue without the label `stage` is denied with `G1: issue #<n> has no label stage, expected the label stage for a planner launch`. To check that the stage has ended, the guard runs, inside the lock, the same two reads as the stage path of close (`read_sub_issues`): `gh api --paginate repos/{owner}/{repo}/issues/<n>/sub_issues` and `gh api repos/{owner}/{repo}/issues/<n> --jq .sub_issues_summary.total`. It runs them only for a new launch of the agent `planner` on an open issue with the label `stage`, so a failing read does not change the message of an issue without `stage`. The launch is denied with a message that starts with `G1:` when a sub-issue is open (the message names every open sub-issue as `<owner>/<repo>#<number>`, also one in another repo), when the sub-issue list is empty (the message says the stage issue has no sub-issue), or when `sub_issues_summary.total` is greater than the number of listed entries (the message names both numbers, also when every listed entry is closed). A read that fails, or prints output the guard cannot read, denies with a message that starts with `guard error`. A denied launch posts no receipt.

**Stage path of close** ([#97](https://github.com/Lighfe/agent-graph-kit/issues/97)). For `gh issue close <n>` on an issue with the label `stage`, G1 checks only step 1 (the issue is open). The label `ready`, the labels `later` and `needs-owner`, the clean tree and the pending check do not apply. The rest of the check is G6 on the stage path.

### G2 PM launch

The PM may run when the issue has no receipt yet (voided ones do not count, and neither does the receipt of one PM miss, [#132](https://github.com/Lighfe/agent-graph-kit/issues/132): after a first PM launch that ended without a result, a PM relaunch or continuation passes G2), or when the current result is `## Engineer: BLOCKED`, `## QA: UNVERIFIABLE`, `## Owner: RESUME`, or `## PM: WAITING` with a blocker list that is not empty and has no open blocker (both blocker reads of G1). A `## PM: WAITING` without a blocker link is denied, and an open blocker is denied by its name. G2 reads no line of the WAITING comment. `## PM: WAITING` is not a return and does not reset the G7 count.

### G3 Engineer launch

The current result is `## PM: GROOMED` or `## QA: FAIL`. For a new launch, the issue body also has a known lane, and the agent is the engineer agent of that lane (`AGENT_LANE`, see "Roles and lanes"). A body without a `Lane:` line, an unknown lane, or another agent is denied. A continuation skips the agent part.

### G4 Codex QA launch

The current result is `## Engineer: DONE`, or `## QA: PASS` whose verified SHA is not `HEAD` (a re-check after `HEAD` moved). The newest valid `## Engineer: DONE` exists and has a `Commits: <base>..<head>` line.

### G5 QA fallback launch

The current result is `## QA: UNAVAILABLE`: the fallback runs only after `qa-codex` reported that Codex cannot run.

### G6 Close

The current result is `## QA: PASS`, and its `Verified:` SHA is equal to `HEAD`.

**Stage path** ([#97](https://github.com/Lighfe/agent-graph-kit/issues/97)). For the close of an issue with the label `stage`, instead: every sub-issue is closed. Only on this path and on the planner path of [G1](#g1-launch-preconditions) ([#119](https://github.com/Lighfe/agent-graph-kit/issues/119)), inside the lock and within the deadline, the guard runs two sub-issue reads (read form from the #95 report, "Consequences"):

- the sub-issue list: `gh api --paginate repos/{owner}/{repo}/issues/<n>/sub_issues --jq '.[] | {repo: .repository.full_name, number, state}'` (all pages, counted per item, no order rule),
- the count: `gh api repos/{owner}/{repo}/issues/<n> --jq .sub_issues_summary.total`.

The close is allowed exactly when the list has at least one entry, every entry has the state `closed` (any state reason, so "not planned" counts), and the count is not greater than the number of listed entries. Deny cases, with a message that starts with `G6:`: an open sub-issue, named as `<owner>/<repo>#<number>` (every open one); no sub-issue; a count greater than the listed entries. A failing or timed-out read, an item that cannot be read, or a count that is not one non-negative integer denies with `guard error`. An issue without the label `stage` gets no sub-issue read.

### G7 Return limit

For a PM or engineer launch or continuation: fewer than 3 returns (`MAX_RETURNS`) after the newest `## Owner: RESUME`. A return is `## QA: FAIL`, `## QA: UNVERIFIABLE` or `## Engineer: BLOCKED` (`RETURNS`), counted when a receipt of its role comes before it.

### G8 Settings protection

Any agent that can write files could put `disableAllHooks` into the local settings file, and the change applies at the next tool call. So:

- `.claude/settings.json` has a `permissions.deny` rule for `Edit` on `/.claude/settings*.json`. Claude Code applies it to the Edit and Write tools; it does not match `Write(…)` rules in file permission checks, so the settings have none ([#136](https://github.com/Lighfe/agent-graph-kit/issues/136)).
- The guard checks every Bash command first, before any `gh` call and without reading issue state. It reads the command with its shell tokenizer (`_lex`). A mention is a word after quote removal (also with braces removed, so `settings.{json,bak}` counts), a redirection target or the text of a substitution that names `settings*.json` (case-insensitive) or a `.claude/` path with a glob character. A command without a mention passes G8 ([#86](https://github.com/Lighfe/agent-graph-kit/issues/86)).
- Here-document body: the text of a here-document body is not a mention, unless the whole command has a pipe (`|` or `|&`) or a runner (see below). The substitutions inside an unquoted body still count as a mention when their text names a protected file; they count for the command that reads the body, so that command is not read-only.
- Read-only parts: a command with a mention passes G8 only when all of these hold:
  - every simple command whose own words, redirection targets or substitution texts mention a protected file is one `cat`, `grep`, `head`, `jq`, `ls`, `tail` or `wc` command (the command word exactly) without redirections or substitutions. The reserved words `{`, `!`, `if`, `then`, `else`, `elif`, `do`, `while` and `until` before a command are not part of it, so `then cat SETFILE` is the read-only command `cat SETFILE`. A word is a reserved word only where bash reads one: unquoted, at the start of a command (also after another such word or `time`), and not inside a case pattern. A redirection before the command word belongs to that simple command only, so `cat SETFILE; > /tmp/x echo x` passes. The list `READ_ONLY` stays at these seven commands: `sed`, `git` and `gh` can write files with some options, so they pass only in parts that do not mention a protected file
  - every part of the command between the separators `;`, `&&`, `||`, `&` and newline that holds both a mention and a pipe has only such read-only commands. Only separators outside a group or a compound command split parts: a subshell `( … )`, a group `{ …; }`, and `if … fi`, `while`/`until`/`for`/`select … done` and `case … esac` are read as one piece with the part they stand in, because a group can pass data across a separator into a pipe. So `{ ls SETFILE; } | tee /tmp/x` is denied, and `(true); cat SETFILE | head` passes, because the subshell is in another part. The words of a case pattern, and its `(`, `|` and `)`, are neither reserved words nor pipes. A function definition (`name ( )` or `function`) or a `coproc` makes the whole command one part. A part without a pipe is not checked this way, so `if true; then cat SETFILE; fi` passes
  - no redirection follows the end of a group or a compound command that holds a mention (`} > x`, `fi > x`, `done > x`, `) > x`, also `2>` or `<`), because it takes the output of the whole group. A redirection after a group without a mention is fine, so `cat SETFILE; (echo x) > /tmp/y` passes
  - no simple command, also inside a substitution, is a runner from `RUNNER_COMMANDS` (`bash`, `sh`, `xargs`, `eval`, `python3`, `find` …)
  - bash expands no parameter `$_` (also `${_}` and `${_…}`), which holds the last argument of the command before. It counts where bash expands it: unquoted, in double quotes, in a substitution or backticks, and in an unquoted here-document body. It does not count in single quotes, in `$'…'`, after a backslash or in a quoted here-document body, so `ls SETFILE; cat '$_'` passes. `${_…}` means the parameter `_` with an operator or an index (`${_:-x}`, `${_%.json}`, `${_[0]}`), its length `${#_}` or `${!_}`; a parameter whose name only starts with an underscore (`$_OTHER`, `${_OTHER}`, `${_x:-y}`) is another parameter and does not count
- A command that the tokenizer cannot read is denied with `G8:` when its text names a protected file.
- The deny message names the way around: split the command so the parts that name the protected files are read-only commands, or use the Read or Grep tool.
- Committing the owner's edit of a protected settings file: a `git` command that names the file (for example `git add .claude/settings.local.json && git commit -m x`) is denied, because `git` is not in `READ_ONLY`; commit the edit with a form that names no protected file, for example `git add -u` or `git commit -a`.
- Passing examples (`SETFILE` is `.claude/settings.local.json`, `HOOKSGLOB` is `.claude/hooks/*.py`): `gh issue view 86 --jq .title; grep -n G8 HOOKSGLOB`, `grep -n g8 HOOKSGLOB | head; sed -n 1,5p docs/specs/agent-graph-kit.md`, `grep -n x HOOKSGLOB && wc -l docs/process.md`, `ls HOOKSGLOB | wc -l`, `cat SETFILE | jq .`, a body file write `cat > /tmp/pm-86-attempt1.md <<'EOF'` (or `<<EOF`) whose body names `SETFILE` and `HOOKSGLOB`, `if true; then cat SETFILE; fi`, `{ cat SETFILE; } | wc -l`, `ls SETFILE; cat '$_'`, `ls SETFILE; cat \$_`, `cat SETFILE; > /tmp/x echo x`, `(true); cat SETFILE | head`, `cat SETFILE; (echo x) > /tmp/y`, `case x in a|b) cat SETFILE;; esac` and `cat SETFILE; echo "${_OTHER}"`.
- Denied examples: `ls SETFILE; cp x "$_"`, `ls SETFILE | while read f; do cp x "$f"; done`, `ls SETFILE | xargs cp x`, `ls SETFILE | tee /tmp/x`, `ls SETFILE > /tmp/x`, `cat SETFILE; cp x SETFILE`, `cd .claude && cp x settings.local.json`, `cat <<'EOF' | sh` or `bash <<'EOF'` with a body that names `SETFILE`, `cat > SETFILE <<'EOF'`, `cat <<EOF > /tmp/x` with a body line `$(cp x SETFILE)`, `ls HOOKSGLOB; cat $(echo SETFILE)`, `if true; then cat SETFILE; fi > /tmp/x`, `while read f; do cat x; done < SETFILE`, `ls SETFILE; echo $(echo $_)`, `(ls SETFILE; (true)) | tee /tmp/x`, `case x in a) ls SETFILE;; esac | tee /tmp/x`, `{ (cat SETFILE); } > /tmp/x`, `f() { ls SETFILE; }; f | tee /tmp/x`, `ls SETFILE; cp x ${#_}`.
- Known limits (P1, hooks are not a security boundary): data passed to a later command through a file or a variable set without naming the file (for example a file name read back from a list file that an earlier command wrote); file names built from pieces (for example with `printf`, string joins or variables) that the text search cannot see; case pattern alternatives read as a runner (for example `case x in a|sh) …`), an accepted false deny; and runners not in `RUNNER_COMMANDS`.

**Activation.** Project hooks apply from the next tool call after `.claude/settings.json` is in place, in every running session of the repo. `{"disableAllHooks": true}` in `.claude/settings.local.json` turns them off, with no warning. The owner's check of the hooks after activation is [docs/checks/hook-activation.md](../checks/hook-activation.md).

**Allow rules.** The guard posts the receipt before the permission check. So that a prompt does not leave the issue pending, the project settings allow `Bash(scripts/qa-codex ROLE=qa ISSUE=*)` and `Bash(gh issue close *)`. They apply only in a trusted folder. The user-level Auto mode allow entries are in "Auto mode allow entries" of the README.

### Failure behavior

- The guard never outputs "allow". An allowed call prints nothing, so the normal permission check stays on. A deny is the `PreToolUse` deny JSON (`permissionDecision: deny`) with exit code 0.
- Every deny names the failing check (`G1:` … `G8:`), for example `G3: current result is ## QA: PASS, expected ## PM: GROOMED or ## QA: FAIL`.
- Any error denies with a message that starts with `guard error`: a failing, missing or timed-out `gh` or `git` call (each call at most 20 s), output that cannot be parsed, broken hook input, a bad `GUARD_DEADLINE` value, and any other crash. Unknown facts never allow a call.
- **Deadline.** The guard has one overall deadline for all its work, the wait for the lock included: `GUARD_DEADLINE` seconds, default 60, with a `SIGALRM` backstop. At the deadline it denies with `guard error: deadline of <s> s reached before the checks finished, call denied`. The settings timeout of 120 s is higher, because a hook that Claude Code kills at its timeout lets the call through; only a hung machine can cause that fail-open. The command wrapper turns a crash or a missing `uv` into a deny with exit code 2.
- **Lock.** Hooks of two calls in one message can run at the same time. The guard holds an exclusive file lock (`<git dir>/agent-graph-kit-guard.lock`) from reading the facts until the receipt is posted, so the second call sees the first receipt. A call of another role is then denied as pending. Known limit since [#132](https://github.com/Lighfe/agent-graph-kit/issues/132): a running launch and a miss look the same in the comments, so a second call of the same role is allowed when the first receipt is the only miss, and denied (two misses in a row) when a miss came before it. `not_started.py` and `outage_stop.py` hold the same lock.

## Result markers

A result is a comment whose first line is one of these markers (`MARKERS` and `RESUME` in `issue_state.py`):

| Marker | Posted by |
|---|---|
| `## PM: GROOMED` | PM |
| `## PM: NEEDS OWNER` | PM |
| `## PM: WAITING` | PM |
| `## Engineer: DONE` | engineer (`software-engineer` or `frontend-engineer`) |
| `## Engineer: BLOCKED` | engineer |
| `## QA: PASS` | `qa-codex` or the fallback `qa-engineer` |
| `## QA: FAIL` | `qa-codex` or the fallback |
| `## QA: UNAVAILABLE` | `qa-codex` |
| `## QA: INVALID` | `qa-codex` or the fallback |
| `## QA: UNVERIFIABLE` | `qa-codex` or the fallback |
| `## Planner: STAGE REVIEW` | the planner subagent |
| `## Owner: RESUME` (the resume match, see "Valid result, pending and current result") | the owner (never an agent) |

The comments of the hooks (`## Launch:`, `## Launch not started:`, `## Launch stopped by outage:`) are not results.

- **Returns** (`RETURNS`): `## QA: FAIL`, `## QA: UNVERIFIABLE`, `## Engineer: BLOCKED`. A return sends the issue back (FAIL to the engineer, UNVERIFIABLE and BLOCKED to the PM). After `MAX_RETURNS` = 3 returns since the newest `## Owner: RESUME`, G7 denies the next PM or engineer launch.
- **Stop results** (`STOP_RESULTS`): `## PM: NEEDS OWNER`, `## QA: INVALID`. No check allows a next launch after them; the orchestrator escalates.
- `## PM: WAITING` is not a return. While the issue has an open blocker, G1 denies every launch on it; when all blockers are closed, G2 lets the PM run again.
- `## QA: UNAVAILABLE` allows only the fallback (G5).
- `## Planner: STAGE REVIEW` is valid only after a planner receipt; then it ends the pending state. It is not a return and does not reset the G7 count.
- `## Owner: RESUME` ends a pending state, resets the G7 count, and lets the PM run (G2).

The comment formats are in the role files; what the orchestrator does after each result is "Decisions at each edge" in [docs/team/orchestrator.md](../team/orchestrator.md#decisions-at-each-edge).

## qa-codex contract

### Call

`scripts/qa-codex ROLE=qa ISSUE=<n>` is the whole Bash command (the qa form of the Bash rule of G1), run with the Bash tool's `run_in_background` option. The script runs with `uv run --script`. Other arguments print the usage and exit 2; outside a git repo with a `HEAD` it exits 1. Both post nothing. Otherwise the script exits 0 when it posted its comment and non-zero when it could not; then the issue stays pending.

### Issue read and commit range

1. One read, outside the sandbox: `gh issue view <n> --json number,state,labels,body,comments`. It gives the criteria, the range, the labels and the comments as one snapshot. Only the owner's comments count. If the read fails, or its output is not JSON or is rejected by `issue_state.parse_issue`, the result is `## QA: UNAVAILABLE` (reason `reading issue #<n> with gh issue view failed: …`) without a Codex run.
2. The criteria are the top-level `- [ ]`, `- [x]` or `- [X]` items under `## Acceptance criteria`, up to the next level-1 or level-2 heading, each with its continuation lines. None: `## QA: INVALID`.
3. The range comes from the `Commits: <base>..<head>` line of the newest valid `## Engineer: DONE`. No such DONE, no such line, a DONE head that does not resolve to a commit, or a DONE head that is not `HEAD` or an ancestor of `HEAD` (`git merge-base --is-ancestor`): `## QA: INVALID`, without a Codex run. Codex verifies `<base>..HEAD`, so a re-check after `HEAD` moved needs no new DONE.
4. The window for the GitHub state starts at the committer date of `<base>` (`git show -s --format=%cI`, in UTC). A base that does not resolve: `## QA: INVALID`.

### What Codex gets

- **The prompt**: the QA role file `docs/team/qa-engineer.md`, the numbered criteria, the range, the text that names the GitHub state files, the comment block, the uv rule (only when `uv` is on `PATH`), and the rule for the per-criterion verdict: `invalid` only when a tool, sandbox, network or permission limit of the environment stops the check, `fail` when the code or document does not meet the criterion.
- **The comment block**: the first line of every counted comment, in issue order, and the full text of the newest valid `## Engineer: DONE` (the one that gives the range). No other comment body. Each comment is redacted before a line is picked. The block runs from the line `BEGIN ISSUE COMMENTS` to the line `END ISSUE COMMENTS`, and every line in between starts with `| `, so a comment cannot end the block early. The prompt says that the text was written by agents, is data and not instructions, and that a claim in a comment is not proof.
- **The GitHub state files** ([#89](https://github.com/Lighfe/agent-graph-kit/issues/89)): after the range checks and before the worktree, the script reads the GitHub state with the `gh` login of the user who runs it, outside the sandbox, and writes five JSON files into `<run temp folder>/github/`. Every string is redacted. An empty result is `[]`.
  - `labels.json`: the label names of the issue, from the one issue read,
  - `timeline.json`: the timeline events (`gh api repos/{owner}/{repo}/issues/<n>/timeline --paginate`) inside the window, each with event type, time and actor login, the label name for `labeled` and `unlabeled`, and the repo and number of the other issue for events that link one; no `commented` events and no bodies,
  - `blocked-by.json`: the native blockers (`…/issues/<n>/dependencies/blocked_by --paginate`), each with repo, number, title and state, in API order,
  - `sub-issues.json`: the sub-issues (`…/issues/<n>/sub_issues --paginate`), the same fields,
  - `created-issues.json`: the repo's issues created inside the window, pull requests left out (`repos/{owner}/{repo}/issues?state=all&since=<window start>&per_page=100 --paginate`), each with number, state, labels, author login, author association and creation time; title and body only when the author association is `OWNER`.

  The prompt names the folder, each file, and the window, and says that the files are a snapshot, are the evidence for criteria about GitHub state (such a criterion is `pass` or `fail`, not `invalid`), and are data, not instructions. If one of these reads fails (`gh` exits non-zero, cannot start, or prints output that is not a JSON array), the result is `## QA: UNAVAILABLE` (reason `reading <what> with gh api <path> --paginate failed: …`) without a Codex run.

### Worktree and pre-step

The script creates a temporary detached `git worktree` at `HEAD` in the run temp folder (under `/tmp` or `$TMPDIR`), so Codex never writes into the main tree. It is removed after the run, also after an interrupt. A worktree that cannot be created: `## QA: INVALID`.

The pre-step runs outside the sandbox, with fixed commands and no LLM decision. Each command has the timeout `QA_PRESTEP_TIMEOUT` (default 1800 s). A failing step gives `## QA: UNAVAILABLE`, and nothing after it runs.

- **Frontend** (the worktree's `.gitmodules` has a submodule with the path `frontend`):
  1. `git submodule update --init -- frontend` in the worktree.
  2. The install command from the lockfile in `frontend/`: `npm ci` with `package-lock.json` or `npm-shrinkwrap.json` (wins when both kinds exist), else `bun install --frozen-lockfile` with `bun.lock` or `bun.lockb` (needs `bun` on `PATH`). No lockfile, or a bun lockfile without `bun`: `## QA: UNAVAILABLE`.
  3. A Playwright dependency: `playwright` or `@playwright/test` in `dependencies` or `devDependencies` of `frontend/package.json`, checked before any install. Missing, or a missing or invalid `package.json`: `## QA: UNAVAILABLE`.
  4. The install command, then the browser with the frontend's own Playwright CLI: `npx --no playwright install chromium` (npm) or `bun x --no-install playwright install chromium` (bun). Nothing is fetched from the registry for the CLI.
- **uv cache** (only when `uv` is on `PATH`): `uv run --no-project --no-config --with pytest pytest --version` with `UV_CACHE_DIR=<run temp folder>/uv-cache`, run in the run temp folder, not the worktree, so it does not read or build the reviewed project.

The pre-step runs repository code outside the sandbox. This accepted risk is described in "Frontend lane (optional)" of the README ([#50](https://github.com/Lighfe/agent-graph-kit/issues/50)).

### Codex run

`codex exec` runs in the worktree with:

- the flags that keep the user config, `AGENTS.md`, skills, hooks and apps out of the run (`BASE_FLAGS` in `codex_exec.py`: `--json`, `--ephemeral`, `--ignore-user-config`, `--disable hooks`, `--disable apps`, `--disable unbounded_connection_retries`, `-c project_doc_max_bytes=0`, `-c skills.include_instructions=false`),
- the model `QA_MODEL` and the reasoning effort `QA_EFFORT` (`medium`), set explicitly because `--ignore-user-config` drops the user's,
- the sandbox `QA_SANDBOX`: `--enable network_proxy` and a permissions profile `qa` (extends `:workspace`, network on, local binding allowed, only the domains `localhost` and `127.0.0.1`), set as the default. Codex runs outside the Claude Code hooks, so the sandbox is its only limit,
- one `-c shell_environment_policy.set={…}` table for every command Codex runs: `CI="1"` always, and with `uv` on `PATH` also `UV_CACHE_DIR=<run temp folder>/uv-cache` and `UV_OFFLINE="1"`. The uv rule in the prompt names the same path and tells Codex not to change these variables,
- `--output-schema scripts/qa-result.schema.json`, `-o <file>` for the final message, and the prompt on stdin.

The result JSON has `verdict`, one entry per criterion (`id`, `verdict` of `pass`, `fail` or `invalid`, `evidence`), `tests` (`command`, `result`) and `verified_sha`. The script checks it against the schema, checks that the ids are exactly 1 to the number of criteria, once each, and that `verified_sha` is `HEAD`.

### Overall marker

From a valid result, the script derives the marker from the criterion verdicts; the top-level `verdict` is not used:

1. any criterion `fail`: `## QA: FAIL`,
2. else any criterion `invalid`: `## QA: UNVERIFIABLE`, with a `Reason:` line that names each such criterion and its evidence,
3. else `## QA: PASS`.

### Failure rules

| Failure | Result |
|---|---|
| Codex not installed, not logged in, usage limit or spend cap | `## QA: UNAVAILABLE`, no retry |
| Transient: network error, rate limit, high demand, server error, crashed process (signal or panic) | up to 3 retries, waiting 1, 3 and 10 minutes; then `## QA: INVALID` |
| Timeout (`QA_CODEX_TIMEOUT`, default 1800 s) | 1 retry; then `## QA: INVALID` |
| Output not JSON, not an object, against the schema, a criterion missing or duplicated, or `verified_sha` not `HEAD` | 1 retry; then `## QA: INVALID` |
| Unknown error | `## QA: INVALID` |
| The issue read, a GitHub state read or the pre-step fails | `## QA: UNAVAILABLE`, no Codex run |
| No criteria, no valid DONE, no `Commits:` line, a DONE head or base that does not resolve, a DONE head that is not an ancestor of `HEAD`, a worktree that cannot be created or reset for a retry | `## QA: INVALID` |

The errors are classified by the S2 error table in `codex_exec.py` (`FAILURE_PATTERNS`; source: `docs/research/spike-codex-cli.md`). Before each retry, the worktree and every initialized submodule are reset to `HEAD` and cleaned of untracked files; ignored files stay. The retry limits hold for one launch.

`## QA: UNAVAILABLE` leads to the fallback (G5); `## QA: INVALID` is a stop result; `## QA: UNVERIFIABLE` is a return to the PM.

### Comment

The script renders one comment and posts it with `gh issue comment <n> --body-file -`. The whole comment is redacted right before it is posted. The lines:

- the marker, then `Reason: …` when there is one,
- for a run with a valid result: one line per criterion, `- [x] <text> - PASS` or `- [ ] <text> - FAIL` / `- INVALID`, with the evidence indented below; then `Tests: …`, `Done head: <DONE head>`, `Verified: <HEAD>`,
- `Checker: codex`, and `Retries: <n> (<reasons>)` after retries.

The fallback `qa-engineer` posts its own comment with `Checker: claude (fallback)` (see [docs/team/qa-engineer.md](../team/qa-engineer.md)).

**Redaction (P5).** The values of environment variables whose names hold `KEY`, `TOKEN`, `SECRET` or `PASSWORD` (8 characters or more, also in joined, JSON-escaped and per-line forms) and common credential patterns (authorization headers, bearer tokens, GitHub tokens, `sk-` keys, `token=`, `key=`, `password=`) are replaced with `[redacted]`. Every reason is redacted before it is cut to 500 characters.

**Interrupts.** On `SIGINT`, `SIGTERM` or `SIGHUP` the script kills the process group of the running child, removes the worktree and the run temp folder, posts nothing and exits with 128 plus the signal number; the issue stays pending. A signal during the clean-up lets the clean-up finish first.

**Trust entry.** A Codex run with a writable sandbox writes a trust entry for the repo into `$HOME/.codex/config.toml` when none exists. The set-up adds it up front ("Codex trust entry" in the README); QA runs ignore the trust list.

## Stage model

The loop steps for stages (pick order, promotion, stage end) are in "Stages" of [docs/process.md](../process.md#stages) and in [docs/team/orchestrator.md](../team/orchestrator.md); stage set-up and the stage review are in [docs/team/planner.md](../team/planner.md). The form of a stage issue is "Stage issue" in `docs/task-template.md`. In short:

- A stage issue has the label `stage` and never the label `ready`. It never goes through PM, engineer and QA.
- Its native sub-issues are its work, in the order of the sub-issue list.
- **Active stage**: found once at the start of a `/goal` run and kept for the run: the one open stage issue with at least one sub-issue, open or closed, with the label `ready`. None: no stage is active for the run. Two or more: the loop stops and asks the owner.
- **Eligible sub-issue**: open, has `ready`, has neither `later` nor `needs-owner`, and has no open blocker.
- **Promotion of a parked blocker**: when an open blocker of a sub-issue of the active stage is a parked issue (open, this repo, label `later`, no parent, no `needs-owner`), the orchestrator adds it to the stage as a sub-issue and changes `later` to `ready`.
- **Stage end**: when the sub-issue list is not empty and every entry is closed, the orchestrator launches the planner subagent on the stage issue (`ROLE=planner ISSUE=<stage issue>`). The planner posts one comment, `## Planner: STAGE REVIEW`, and the loop stops.
- **Closing**: the planner closes the stage issue at stage set-up, in the main session, with `gh issue close <n>`. Before the close, set-up files the to-be-filed sub-issues of the options not chosen as follow-ups with `later`, and with `needs-owner` too when they need the owner's approval (see "Stage set-up" in `docs/team/planner.md`). Before the close, set-up also files as follow-ups the review findings that propose a change and belong to no option. When set-up went to intake because the owner chose no option, the finished stage issue is closed only after the owner confirms the new stage, with every option treated as not chosen (see "Intake" in `docs/team/planner.md`).

What the hooks do for a stage issue:

- A planner launch is allowed only on an open issue with the label `stage`: the planner path of [G1](#g1-launch-preconditions). It is checked that the stage issue has at least one sub-issue and that every sub-issue is closed ([#119](https://github.com/Lighfe/agent-graph-kit/issues/119)).
- A PM, engineer or QA launch on a stage issue is denied by G1 while it has no `ready`, which a stage issue never gets.
- The close of a stage issue is allowed only when it is open and every sub-issue is closed: the stage path of [G1](#g1-launch-preconditions) and [G6](#g6-close).
- `qa-codex` gives Codex the sub-issues of the checked issue in `sub-issues.json` (see "What Codex gets").

## Doc lifecycles

Each kind of doc has a folder and a lifecycle. The reading rules for these folders are prose in "Work rules" of [docs/process.md](../process.md#work-rules); no hook checks them.

| Kind of doc | Folder | Lifecycle |
|---|---|---|
| Living spec | `docs/specs/` (this file) | Kept up to date: fixed in the same commit as the change that makes it false. |
| Dated design specs and proposals | `docs/specs/`, `docs/research/` | Archived to `docs/archive/` once their stage is set up. Until then they stay where they are (for example a deferred spec in `docs/specs/`). |
| Plans | `docs/plans/` | Written at intake; archived to `docs/archive/` once every stage issue made from the plan is set up. |
| Research and spike reports | `docs/research/` | Written once and kept. Later research may build on them and cite them. |
| Reviews | `docs/reviews/` | Kept as a record once each finding is an issue or decided. Deleted only on clear evidence that agents read old reviews. |
| Archive | `docs/archive/` | Kept unchanged. |
| Owner checklists | `docs/checks/` | Kept up to date with the hooks and settings they check. |
| Instruction files | `AGENTS.md`, `CLAUDE.md`, `docs/process.md`, `docs/task-template.md`, `docs/team/`, `.claude/agents/`, `.agents/skills/` | Kept up to date: fixed in the same commit as the change that makes them false. |
