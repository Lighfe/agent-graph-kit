# Spike: Claude Code `/doctor prompt-audit` on this repo

Issue: #81. Report only; no proposed edit was applied.

## Setup

- Claude Code version (`claude --version`): `2.1.283 (Claude Code)`
- Commit the audit ran on: `c2510fea12141e1ff42b8949b779a96980a11fe1` (clean working tree, branch `main`)
- Issue #82 (fix of the plan and spec status lines) was still open. The checkout still contains the text of problems 1 to 3:
  - `docs/plans/2026-09-25-agent-graph-kit-v1.md:3` "Execution is deferred. In a later session, convert these tasks to issues ..."
  - `docs/plans/2026-09-25-agent-graph-kit-v1.md:51` "Where a task below and the spec differ, the spec wins."
  - `docs/specs/2026-09-25-agent-graph-kit-v1.md:4` "Status: draft, for owner review" and `:6` "Updated 2026-09-26 ..."

  So the "fixed before the run, not tested" case does not apply.
- Where it ran: from inside the loop (engineer subagent, auto mode), as a nested non-interactive run from the repo root. The nested run was not denied, and the slash command worked with `-p`. Both runs exited with code 0.
- After each run, `git status --porcelain` was empty: the audit left no stray or untracked files.

Both runs printed this warning as the first line of output. It is a Claude Code startup warning about this repo's settings, not an audit finding:

> Permission deny rule (.claude/settings.json): Write(/.claude/settings*.json) is not matched by file permission checks — only Edit(path) rules are. Use Edit(/.claude/settings*.json) instead (Edit rules cover all file-editing tools).

This is worth a separate look by the owner (settings are an owner decision). It is out of scope here.

## Run 1: default scope

Command (from the repo root):

```
claude -p "/doctor prompt-audit"
```

What the audit says it read: `CLAUDE.md` (which only imports `AGENTS.md`), `AGENTS.md`, `.agents/skills/codex-review/SKILL.md` (through the `.claude/skills` symlink), and the four subagent files `.claude/agents/{pm,software-engineer,qa-engineer,frontend-engineer}.md`. To check facts, it also looked up the paths these files name, `docs/team/orchestrator.md:134` and `README.md:11`. Reading outside the project (`~/.claude/`, parent folders, `/etc/claude-code/CLAUDE.md`, plugin files) was denied, and it said so.

Findings: **no findings.** It reports no dated prompt text, no stale facts, no conflicts, no tool descriptions and no API request code.

It added one note that it did not count as a finding:

| # | File | Note |
|---|---|---|
| N1 | `README.md:93` | `README.md:93` quotes two sentences of `AGENTS.md` ("This repo will become a Claude Code plugin ..." and "Now, it is in bootstrap."). If they are reworded, update the README in the same commit |

## Run 2: pointed at `docs/`

Command (from the repo root):

```
claude -p "/doctor prompt-audit docs/"
```

What the audit says it read: the files it counts as instructions: `docs/process.md`, `docs/task-template.md`, `docs/team/{orchestrator,pm,software-engineer,qa-engineer}.md` and `docs/checks/hook-activation.md`. It skipped on purpose `docs/specs`, `docs/plans`, `docs/research`, `docs/reviews`, `docs/archive`, `docs/references` and `docs/owner-notes`, because they are "design and reference documents, not instructions". `gh issue view` and `git blame` needed approval in the nested session, so it read no GitHub issue and no history. To check facts, it also looked at `.claude/hooks/`, `scripts/qa-codex` and the spec section numbers.

Findings (the audit's own table, shortened):

| # | File | What the audit says | Confidence | Proposed action |
|---|---|---|---|---|
| F1 | `docs/process.md:48` | "QA does not fix the code, only outputs PASS or FAIL" contradicts the four QA verdicts in `docs/team/qa-engineer.md:16`, the results in `docs/team/orchestrator.md` and lines 38 and 53-54 of `process.md` itself | High | rewrite |
| F2 | `docs/process.md:5` | The status line says the hooks check "each launch of a role and each `gh issue close`". They also check `SendMessage` continuations, `qa-codex`, comment commands (G9) and writes to the settings files (G8) | Medium | rewrite |
| F3 | `docs/process.md:60` | "the launch stays pending, as before": "as before" refers to an older version of the rules | Medium | remove |
| F4 | `docs/team/orchestrator.md:86` | "Escalate the issue, as before.": same as F3 | Medium | remove |
| F5 | `docs/process.md:55-60` | The "Denied action" bullet holds three cases in one bullet; could be split into sub-bullets | Low | flag |
| F6 | `docs/checks/hook-activation.md:3,7` | A one-time runbook tied to issue #7 and to "before the next real issue gets the label `ready`"; could move to `docs/archive/` once run | Low | flag |

It also proposed diffs for F1 to F4 and listed things it kept on purpose (the numbered steps of the frontend lane, the QA comment example, the three copies of the `## Owner: RESUME` rule, "Do not work around a deny").

## False positives

I checked each finding and note against the files at the audit commit.

- F1: correct. `docs/team/qa-engineer.md:16` says "PASS, FAIL, UNVERIFIABLE or INVALID", and `process.md` itself uses UNVERIFIABLE and INVALID.
- F2: correct. `docs/team/orchestrator.md:82` lists `SendMessage` continuations and `qa-codex`, and lines 98 and 101 name G9 and G8. During this spike, G8 and G1 denied two of my own read-only Bash commands, so the hooks check more than launches and `gh issue close`.
- F3, F4: correct, the text is there. Whether "as before" is harmful is a judgment, not a false fact.
- F5: not a false fact; a style judgment.
- F6: correct. Issue #7 ("Task 7: Hook wiring and prose switch") is closed, so the runbook's precondition is history. The audit could not check that itself.
- N1: partly wrong. `README.md:93` does not quote the two sentences as a duplicate. It is an install step that tells a user to replace those two sentences in `AGENTS.md`. The advice (keep the two in sync) still holds, but the reason it gives is wrong.

No finding is a false positive. Note N1 is partly wrong, as described above.

## The 8 problems from the manual audit

| # | Problem (from `docs/research/big-picture-and-lean-docs.md`) | Result | Why |
|---|---|---|---|
| 1 | Plan says "Execution is deferred ... convert these tasks to issues" | not found | `docs/plans/` is outside the default scope, and run 2 skipped `docs/plans` on purpose as "not instructions" |
| 2 | Plan says "the spec wins" but is not kept current | not found | Same: `docs/plans/` was read in neither run. The problem also needs history (plan versus spec over time), and run 2 had no `git blame` |
| 3 | Spec head says "Status: draft" and "Updated 2026-09-26" | not found | `docs/specs/` is outside the default scope, and run 2 skipped it on purpose |
| 4 | About 44 lines in code, hooks, scripts, skills and tests point to spec section numbers | not found (0 of about 44 named) | The references are in `.py` files, `scripts/qa-codex` and tests, which the audit does not treat as instruction files. A grep at the audit commit finds 42 matching lines: `.claude/hooks/` 26, `scripts/` 9, `tests/` 6, `.agents/skills/codex-review/review.py` 1. The in-scope Markdown files (`SKILL.md`, `.claude/agents/*.md`) hold none. Run 2 saw the spec references in `docs/team/pm.md`, checked only that sections 5.9, 6.1 and 6.2 exist, and did not flag them as a coupling |
| 5 | Spec "Not in v1" table and 19 open issues hold the same text | not found | One half lives in GitHub issues, which neither run read (run 2: `gh issue view` needed approval). The other half lives in `docs/specs/`, which neither run read |
| 6 | Open issue #66 points to a file in `docs/archive/` | not found | It lives in a GitHub issue; neither run read issues |
| 7 | `docs/process.md` says the owner adds `ready`; in practice the owner asks the orchestrator | not found | Run 2 read `docs/process.md`, but the gap is between the text and practice (how sessions really go), not between two files. The audit checks files against files and against the repo, so it cannot see this |
| 8 | Agents can read large folders that are not kept current (`docs/research/`, `docs/plans/`, `docs/reviews/`) | not found | Neither run reports on what agents may read. Run 2 skipped these folders itself and mentioned that `docs/process.md:12` tells agents to skip old reviews, but it did not raise the other folders as a risk |

Summary: 0 of 8 found. 7 of 8 are out of reach by design (outside the scope, in GitHub issues, or about practice rather than text). Problem 4 is in the repo but in code, which the audit does not cover. In exchange, run 2 found six things that the manual audit did not list (F1 to F6). At least F1 and F2 are real, and F1 is a real conflict between instruction files.

## What the audit did not look at

Top-level folders and files of the repo (`.git/` excluded):

| Path | Run 1 (default) | Run 2 (`docs/`) |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md` | audited | not audited |
| `.claude/agents/` | audited | not audited (looked up only to check that subagents set no model) |
| `.claude/skills` → `.agents/skills/` | `codex-review/SKILL.md` audited; `review.py`, `review.schema.json` not audited | not audited |
| `.claude/hooks/` | not audited (path only checked to exist) | not audited (read only to check facts: check IDs, G1 messages) |
| `.claude/settings.json` | skipped on purpose | skipped on purpose |
| `.github/` | not looked at | not looked at |
| `.pytest_cache/`, `.vscode/` | not looked at | not looked at |
| `docs/` | not audited (paths only checked to exist) | see below |
| `scripts/` | not looked at | not audited (`scripts/qa-codex` read only to check facts) |
| `tests/` | not audited (path only checked to exist) | not looked at |
| `README.md` | not audited (read only to check facts: lines 11 and 93) | not looked at |
| `LICENSE`, `.gitignore` | not looked at | not looked at |

`docs/` subfolders:

| Path | Run 1 (default) | Run 2 (`docs/`) |
|---|---|---|
| `docs/process.md`, `docs/task-template.md` | not audited (paths only checked to exist) | audited |
| `docs/team/` | not audited (`orchestrator.md:134` and the frontend lane section of `software-engineer.md` read only to check facts) | audited |
| `docs/checks/` | not looked at | audited |
| `docs/specs/` | not audited | skipped on purpose |
| `docs/plans/` | not audited | skipped on purpose |
| `docs/research/` | not looked at | skipped on purpose |
| `docs/reviews/` | not audited | skipped on purpose |
| `docs/archive/` | not looked at | skipped on purpose |
| `docs/references/` (`local/`, `summaries/`) | not audited (`local/` path only checked to exist) | skipped on purpose |
| `docs/owner-notes/` | not looked at | skipped on purpose |

Outside the repo: run 1 tried `~/.claude/`, parent `CLAUDE.md`/`AGENTS.md`, `/etc/claude-code/CLAUDE.md` and plugin files (superpowers, codex, lovable), and reading them was denied. Neither run read GitHub issues.

## Takeaways for #84

- `/doctor prompt-audit` checks instruction files against each other and against the repo. It does not find stale design docs (plans, specs, research), duplicates with GitHub issues, code that points at doc sections, or gaps between text and practice. Those were the 8 manual problems, so the two audits barely overlap.
- It is cheap to run (one non-interactive command, no file changes) and found a real conflict (F1) in `docs/process.md`. That file is outside its default scope, so the run pointed at `docs/` was the useful one.
- It runs fine from inside the loop with `claude -p`. Reading GitHub issues and git history needs approval in the nested session, so a run from the loop sees less than an interactive run would.
