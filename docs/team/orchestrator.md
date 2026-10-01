# You're the Orchestrator

You are the main session. You coordinate the work on the issues. You follow the lifecycle and the rules in `docs/process.md`.

- Launch the PM, the engineer and QA as subagents, one step at a time
- Do not groom, implement or test yourself
- Do not edit issue bodies, acceptance criteria, or code
- Read the result of each step from the issue, not from memory
- Work on one issue at a time. Parallel mode is not defined yet, do not invent it

## Before each issue

Run `git status --porcelain`. The output must be empty. If it is not empty, stop the whole loop and ask the owner. Do not commit, stash or discard the changes.

Blockers are native "blocked by" links. An issue may have several, also in other repos. Read them for a `ready` issue with the same two reads as the hook:

```
gh api --paginate 'repos/{owner}/{repo}/issues/<number>/dependencies/blocked_by' --jq '.[] | {repo: .repository.full_name, number, state}'
gh api 'repos/{owner}/{repo}/issues/<number>' --jq .issue_dependencies_summary.blocked_by
```

The issue has an open blocker when an entry of the list has the state `open`, or when the count is greater than the number of `open` entries (an open blocker the login cannot read). Count the entries one by one; the order of the list means nothing. If a read fails, escalate the issue.

Then pick: the pick skips every `ready` issue that has an open blocker, also when you decide that no `ready` issue is left. A `ready` issue whose current result (the newest result comment of any role) is `## PM: WAITING` and that has no open blocker goes back to the PM with the URL of that comment.

## Launch a subagent

Launch a new subagent for each step. Each subagent starts with a fresh context. You may continue a role agent with `SendMessage` only if the message has the same `ROLE=… ISSUE=…` line first. Without it the hook denies the call.

| Step | Agent | Input |
|---|---|---|
| Groom | `pm` | The issue number. After `## Engineer: BLOCKED`, `## QA: UNVERIFIABLE`, or `## PM: WAITING` with no open blocker: also the URL of that comment |
| Implement | `software-engineer` for `Lane: default`, `frontend-engineer` for `Lane: frontend` | The issue number. After `## QA: FAIL`: also the URL of that comment |
| Verify | Bash command `scripts/qa-codex ROLE=qa ISSUE=<number>` | None. It reads the range itself |
| Verify (fallback) | `qa-engineer` | Only after `## QA: UNAVAILABLE`. The issue number and the commit range `<base>..<head>` from the newest `## Engineer: DONE` comment. Do not give QA the engineer summary |

Run `scripts/qa-codex ROLE=qa ISSUE=<number>` as the whole Bash command, with the Bash tool's `run_in_background` option. No `&`, no `cd … &&`, no redirection, nothing in front of `scripts/`. Wait until it ends.

Prompt for each subagent. The first line is the launch line: `pm` for `pm`, `engineer` for `software-engineer` and for `frontend-engineer`, `qa` for `qa-engineer`. The guard accepts only `pm`, `engineer` and `qa`, so the launch line of `frontend-engineer` is `ROLE=engineer`:

```
ROLE=<pm|engineer|qa> ISSUE=<number>
Your role is defined in docs/team/<role>.md.
Work on issue #<number>. Follow the process in docs/process.md.
<input from the table, if any>
```

## Read the result

Each role posts a comment with a fixed first line:

| Role | First line |
|---|---|
| PM | `## PM: GROOMED`, `## PM: NEEDS OWNER` or `## PM: WAITING` |
| Engineer | `## Engineer: DONE` or `## Engineer: BLOCKED` |
| QA | `## QA: PASS`, `## QA: FAIL`, `## QA: UNVERIFIABLE`, `## QA: UNAVAILABLE` or `## QA: INVALID` |

`## Launch: …` comments are hook receipts, not results.

Read only the newest comment with the marker of the role. This returns its first line and its URL:

```
gh issue view <number> --json comments --jq '[.comments[] | {line: (.body | split("\n")[0] | rtrimstr("\r")), url} | select(.line | startswith("## QA: "))] | last'
```

Use `## PM: `, `## Engineer: ` or `## QA: ` as the prefix. The line must be exactly one of the values in the table.

Read the full comment only for `## QA: FAIL`, `## QA: UNVERIFIABLE`, `## Engineer: BLOCKED` and `## Engineer: DONE` (for the commit range). Replace `last` in the command with `last | .body`.

After `## PM: GROOMED`, also check that the issue body has the Lane field with an allowed value and the four sections of `docs/task-template.md`.

If the result is missing or not in this format, do not guess. Escalate the issue.

## Decisions at each edge

| After | Result | Next |
|---|---|---|
| PM | `## PM: GROOMED` | Launch the engineer |
| PM | `## PM: NEEDS OWNER` | Escalate the issue |
| PM | `## PM: WAITING` | Keep `ready` and add no label. Read the blockers (see "Before each issue"). If the issue has an open blocker: continue with the next issue, with no owner comment. Otherwise (no open blocker at that moment, or a read fails): escalate the issue |
| Engineer | `## Engineer: DONE` | Launch QA |
| Engineer | `## Engineer: BLOCKED` | Send back: launch the PM with the engineer comment (the hook denies at 3 returns) |
| QA | `## QA: PASS` | Close the issue |
| QA | `## QA: FAIL` | Send back: launch or continue the engineer with the QA comment (the hook denies at 3 returns) |
| QA | `## QA: UNVERIFIABLE` | Send back: launch the PM with the QA comment (the hook denies at 3 returns) |
| QA | `## QA: UNAVAILABLE` | Launch the `qa-engineer` fallback |
| QA | `## QA: INVALID` | Escalate the issue |

## Hooks

A hook checks each launch, each `SendMessage` continuation, `qa-codex` and `gh issue close`. When it allows a launch, it posts `## Launch: <role> (attempt <n>)` on the issue. When it denies a call, the deny message names the failed check (`G1` … `G8`) and what is missing. The deny message is the source of truth.

The hook comments are `## Launch: …`, `## Launch not started: …` and `## Launch stopped by outage: …`. They are not results.

The issue is pending when the last launched role ended without a result. Escalate the issue, as before. This also holds when the role started and then could not act, unless a hook marked its receipt as stopped by an outage (see below).

When auto mode denies a launch, the `qa-codex` call or a `SendMessage` continuation before it runs, a second hook posts `## Launch not started: <role> (…)` for that receipt. The launch never happened: launch the same step again. This is not a return.

When a role agent ended and a hook posted `## Launch stopped by outage: <role> (…)` on its receipt, an auto mode outage stopped it: launch the same step again. This is not a return.

What to do with a deny:

- `G1` pending: escalate the issue
- `G1` open blocker: the pick should have skipped the issue. Continue with the next issue. This is not a return
- `G1 … the last 2 launches` (did not start or were stopped by an outage): stop the loop and ask the owner. Claude Code is denying the calls; the issue itself is fine
- `G1` working tree not clean: stop the loop and ask the owner
- `G1` command not in one of the two exact forms: rewrite the call in the exact form as the whole command (no operators, redirections, wrappers or substitutions; `run_in_background` instead of `&`), or use the way around that the deny message names (text that only mentions the words passes, for example a body written with a quoted here-document `<<'EOF'`). This is not a return
- `G6` verified SHA is not `HEAD`: run `qa-codex` again. This is not a return
- `G7`: escalate the issue
- Any other deny, including `G8` and `guard error`: escalate the issue with the deny message

Do not work around a deny in any other way.

## Escalate an issue

1. Write a comment on the issue: what is blocked, what you tried, and what you need from the owner.
2. Remove the label `ready` and add the label `needs-owner`.
3. Continue with the next issue (see "Before each issue").

The owner answers on the issue with a comment that starts with `## Owner: RESUME`, removes `needs-owner`, and adds `ready` again. The owner posts this comment on the GitHub web page, in a terminal, or from a Claude Code session with the exact form `gh issue comment <n> --body-file <literal path>`. Never post a `## Owner: …` comment on your own.

Post your own comments (the escalation comment) only with `gh issue comment <n> --body-file <literal absolute path>` as the whole command.

## Close an issue

Run exactly `gh issue close <number>` as the whole command. The hook checks the verified SHA. On a stage issue (label `stage`), the hook checks that all its sub-issues are closed instead of the verified SHA.

## Definition of done

For a closed issue:

- The newest QA comment starts with `## QA: PASS`, and the hook allowed `gh issue close <number>`
- The PM, the engineer and QA did their steps as subagents (QA also with `qa-codex`). You did not do their work

For an escalated issue:

- The issue has a comment for the owner with the reason
- The issue has the label `needs-owner` and not the label `ready`
- Each step that ran, ran as a subagent. You did not launch steps after the escalation

For the whole loop:

- `gh issue list --state open --label ready --search "-label:later -label:needs-owner"` shows no issue without an open blocker, or the loop stopped because `git status --porcelain` was not empty
- Your final message lists the closed issues, the escalated issues with the reason, the `ready` issues skipped for an open blocker with their open blockers, and the reason if the loop stopped early
