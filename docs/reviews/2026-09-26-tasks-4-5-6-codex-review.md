# Codex review: Task 4, Task 5 resume, Task 6

Date: 2026-09-26
Reviewer: Codex (`codex exec`, read-only, offline), three runs
Targets:

- Task 4 result (issue #4): `git diff 0f76fb6..4cb8d5f`
- The owner's proposed `## Owner: RESUME` for Task 5 (issue #5, escalated after 3 QA FAILs)
- Task 6 result (issue #6): `git diff 03df9cd..cba9bda`

The orchestrator read the code for each finding before deciding. Codex did not run the test suite (pytest is only available through `uv`). It reproduced the findings with small probes.

## Task 4: `issue_state.py`

### 4.1 High: an embedded `Verified:` line can allow a close

`_value()` (`.claude/hooks/issue_state.py:78`) returns the first matching line anywhere in the comment, fenced examples included. A QA PASS that quotes an example with a real 40-character SHA before its own footer makes G6 compare the example SHA with `HEAD`. The same applies to `Commits:` and `Lane:`.

Decision: taken. Follow-up issue: read these values only outside fenced code blocks, and deny when two lines give different values.

### 4.2 Medium: the re-check after `HEAD` moves cannot finish in the Codex lane

Flow: DONE `A..B`, QA PASS at B, a new commit C. G4 allows another `qa-codex` run (spec 5.4 "re-check"). `qa-codex` takes the range from the newest DONE and posts `## QA: INVALID` when its head is not `HEAD`. The re-check in `docs/team/orchestrator.md` ("Close an issue", step 2) then ends in an escalation.

Decision: open, owner decides. This is a conflict between the spec for G4 and the spec for `qa-codex`. It must be settled before Task 7. Follow-up issue without `ready`.

### 4.3 Medium: missing `comments` counts as "no history"

`parse_issue()` (`.claude/hooks/issue_state.py:70`) turns a missing or `null` `comments` field into an empty tuple. A launch is then allowed. Spec 5.6: unknown facts do not allow a launch.

Decision: taken. Same follow-up issue as 4.1: `comments` must be a list, and each body a string, else parsing fails and the guard denies. `comments: []` stays valid.

## Task 5: the owner's resume proposal

Codex verdict: adopt with changes.

### 5.1 High: trimming whitespace can post a launch comment for a call that cannot run

`scripts/qa-codex ROLE=qa ISSUE=5\r` matches after `rstrip()`, but bash passes `ISSUE=5\r` and the launcher rejects it. The guard has already posted the launch comment, so the issue stays pending. `<digits>` also accepts `0` and `05`, but the launcher needs `[1-9][0-9]*`.

Decision: taken. Match the original text. Only trailing spaces, tabs and one final newline are allowed. Number grammar `[1-9][0-9]*`.

### 5.2 High: the rule contradicts the spec and the plan

Spec 5.1 ("normal Bash commands" pass) and plan Review Focus 1 (`cat scripts/qa-codex` and a commit message with `qa-codex` must pass) require the opposite of the new rule.

Decision: taken. The new rule supersedes them. Task 5 updates spec 5.1 and plan Review Focus 1 and Task 5.

### 5.3 Medium: more false denies than the proposal names

Denied: `git commit -m "Fix gh close handling"`, `gh issue view 5 | grep close`, `cat scripts/qa-codex`, `git diff scripts/qa-codex`, `git add scripts/qa-codex`, `gh pr close 5`.

Decision: accepted as a cost. Agents read files with the Read and Grep tools, not with Bash. The deny message names the ways around: `git commit -F <file>`, `--body-file`, the Read or Grep tool, a path without the trigger word (`git add scripts/`). No exemptions for "read-only" commands, because they would bring shell parsing back.

### 5.4 Medium: "word", backslash-newline and the launch form are not defined

- "Word" is defined as the ASCII regex `\bgh\b` and `\bclose\b`, case-sensitive. Then `/usr/bin/gh issue close 5` and `command gh issue close 5` are triggered and denied, because they are not an exact form.
- `gh issue clo\` + newline + `se 5` runs a close in bash, but does not contain the word `close`. Detection also checks a copy of the text with every backslash-newline removed. Acceptance never uses a changed text.
- The only `qa-codex` form is `scripts/qa-codex ROLE=qa ISSUE=<n>` (plan Task 7, spec 5.9 allow rule). It runs through the background option of the Bash tool, not with `&`.

Decision: taken.

### Not a finding

`gh api -X PATCH …/issues/5 -f state=closed` and `gh issue edit 5 --state closed` pass. They are outside the prescribed calls (spec P1).

## Task 6: `qa-codex`

### 6.1 High: nothing removes secrets before posting

`_post()` (`scripts/qa-codex:259`) posts Codex evidence, test output, error lines and pre-step output as they are. A token in a test log would reach a public issue. Spec P5.

Decision: taken. Follow-up issue: redact the whole comment before posting.

### 6.2 Medium: a retry can test frontend code that the last attempt changed

`_reset_worktree()` (`scripts/qa-codex:251`) resets only the main worktree, not the `frontend/` submodule, and ignores return codes.

Decision: taken. Follow-up issue, together with 6.3.

### 6.3 Medium: Ctrl-C or SIGTERM leaves Codex running

`scripts/codex_exec.py:161` kills the process group only on a timeout. On an interrupt, the worktree is removed while Codex keeps running in its own session.

Decision: taken. Same follow-up issue as 6.2.
