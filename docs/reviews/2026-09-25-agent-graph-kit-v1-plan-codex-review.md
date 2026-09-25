# Codex review: agent-graph-kit v1 plan

- Date: 2026-09-25
- Target: `docs/plans/2026-09-25-agent-graph-kit-v1.md`, against `docs/specs/2026-09-25-agent-graph-kit-v1.md`
- Checker: Codex, read-only. The review prompt was normal, not adversarial. This run used the Codex plugin, because the kit's `codex-review` skill is not built yet (plan Task 8)
- Verdict: needs-attention

## Summary

The plan covers the spec and respects the owner and plan decisions. Its prose changes are focused. Five findings need a fix: three about guard parsing, one about the complete QA input, and one about hook activation. Codex edited no file and ran no project test suite. It checked the parser example in an isolated reproduction.

## Findings

### 1. [high] Ordinary whitespace bypasses the close guard

- File: plan, Task 5 (the `classify` description)
- Confidence: 1.0

The raw-text shortcut returns `None` unless the command contains the exact substring `gh issue close`. Both `gh  issue close 5` and a tab-separated version bypass classification, and with it G1 and G6.

Recommendation: Identify guarded commands from tokens, not from raw substrings. Add whitespace-variant tests.

Decision: taken. The prefilter is removed, and every Bash command is tokenized. A command that cannot be parsed is denied if it contains `gh` or `qa-codex`. New tests cover `gh  issue close 12` and a tab variant.

### 2. [high] Criterion extraction drops required continuation text

- File: plan, Task 6 (`parse_criteria`), Tasks 7 and 10 (nested criteria)
- Confidence: 0.99

`parse_criteria` extracts only checkbox lines, but several tasks put required detail in nested bullets. Codex would get an incomplete set of requirements, and the validator would accept full coverage of that incomplete set.

Recommendation: Extract each whole checkbox item, including its nested lists. Test extraction and prompt construction.

Decision: taken, with a change. Each top-level item is sent in full, including its indented continuation lines, and numbered from 1. Codex answers with the number as `id` instead of copying the text. The rendered comment uses the issue's own text. A new test uses a criterion with nested bullets.

### 3. [high] The hook-wiring task lacks an explicit bootstrap QA path

- File: plan, Task 7
- Confidence: 0.94

Task 7 closes before the hooks are active, but its new prose sends QA through `qa-codex`. `qa-codex` needs a valid `## Engineer: DONE`, and validity needs a launch receipt that Task 7's engineer did not get.

Recommendation: State that Task 7 is verified and closed under the bootstrap workflow, and add this to its acceptance criteria.

Decision: partly taken. A constraint in Task 7 says that the issue is verified and closed with the process in force when it started: the Claude `qa-engineer`, the manual SHA check and `gh issue close`. The new rules start with Task 8 in a new session. This is a constraint on how the issue is processed, not a property of the result, so it is not an acceptance criterion.

### 4. [medium] The parser loses compound-command structure

- File: plan, Task 5 (`simple_commands`, `classify`)
- Confidence: 1.0

`simple_commands` drops operators and empty segments. So `(gh issue close 5)` and `gh issue close 5 &` look like one plain close, which contradicts Task 5's own criterion. `echo "$(gh issue close 5)"` looks like a plain `echo`.

Recommendation: Keep the shell structure (subshells, background operators, command substitutions). Add tests, and keep the tests for harmless quoted mentions.

Decision: taken. `split_command` returns the operator count, and a guarded call with any operator is denied. The text inside `$(…)` and backticks is classified on its own, recursively. The new deny tests are `(gh …)`, `… &`, `$(…)` and backticks. A new pass test is a heredoc commit message that mentions `qa-codex`.

### 5. [low] Whitespace validation has contradictory expected outcomes

- File: plan, Review Focus item 4, Task 6
- Confidence: 1.0

Review Focus says that a difference in criterion whitespace leads to a retry and then INVALID. Task 6 normalizes whitespace and tests that such text matches.

Recommendation: Choose one policy and align all sections.

Decision: taken. Matching by id (finding 2) removes text matching. Review Focus item 4 now names missing or duplicated ids and a short SHA. The whitespace test is replaced by a nested-criterion test.

## Next steps

- All five findings are resolved in the plan. After owner approval, commit the plan together with this review file.
