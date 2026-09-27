# Codex review: issues #33–#36

Date: 2026-09-27
Reviewer: Codex (`codex exec`, read-only), one run
Target: `git diff 81d121d..b71de10`

- #33 `issue_state.py` value parsing and missing comments
- #34 `qa-codex` redaction before posting
- #35 `qa-codex` retries and interrupts
- #36 `qa-codex` re-check after `HEAD` moves

The orchestrator read the code for each finding before deciding. Codex did not run the test suite. It reproduced the findings with in-memory probes and synthetic values.

No findings for #33 and #36.

## 1 High: secrets that span several lines can reach a public comment

`render()` (`scripts/qa-codex:191`) indents each evidence line before the final redaction of the comment. `redact()` (`scripts/codex_exec.py:85`) replaces exact env values, so a value that spans several lines (for example a private key) no longer matches after the indent. `_run_step()` (`scripts/qa-codex:227`) picks one line of the step output before redaction, so a fragment of such a value does not match either.

Decision: taken. Follow-up issue #37: redact the raw evidence and the whole step output before splitting, indenting or picking a line. Keep the final redaction.

## 2 Medium: a first interrupt during cleanup stops the cleanup

When SIGINT, SIGTERM or SIGHUP first arrives during the worktree removal in the `finally` block of `_main` (`scripts/qa-codex:430`), `Interrupted` escapes. `main()` (`scripts/qa-codex:337`) kills the children but does not retry the removal, and `shutil.rmtree(tmp)` does not run. A stale worktree and a temporary directory stay.

Decision: taken. Follow-up issue #38: defer interrupts during cleanup, then return 128 + the signal number.

## Next steps

#37 and #38 run in the prose loop before #7, because `qa-codex` becomes the QA path for all issues after #7.
