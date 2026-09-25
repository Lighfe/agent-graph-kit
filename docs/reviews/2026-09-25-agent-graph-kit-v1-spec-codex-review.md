# Codex review: agent-graph-kit v1 spec

- Date: 2026-09-25
- Reviewer: Codex (codex exec, read-only)
- Target: docs/specs/2026-09-25-agent-graph-kit-v1.md

## Verdict

**needs-attention**

The integrations are broadly feasible, but G1–G7 do not yet guarantee the lifecycle described. Pending launches can expose earlier results, the close contract is incomplete, and the Codex launcher conflicts with the shared QA instructions. Most fixes can stay within the existing checks and role files; narrowing the guarantee is preferable to building a general shell enforcement system.

## Findings

### 1. A pending launch leaves earlier transitions available — severity high, confidence 1.0

- Location: §5.3–5.4, lines 108–127.
- Problem: Validity is calculated against the newest launch **of each role**, while the current result can come from any role. A launch without a result therefore does not necessarily block subsequent launches, contrary to line 113.
- Failure scenario: PM posts GROOMED, then engineer launches and produces no result. PM’s GROOMED remains current, so G3 permits another engineer launch indefinitely. During QA fallback, its launch invalidates UNAVAILABLE but exposes the earlier Engineer DONE, allowing another Codex launch.
- Recommendation: Treat the newest launch as pending until its matching result arrives. While pending, deny further role launches and close; use the existing escalation path if execution ends without a result. Require results to identify the launch attempt so delayed output cannot complete a newer attempt.

### 2. The claimed guarantee exceeds the guarded interfaces — severity high, confidence 1.0

- Location: §1, line 15; §5.1, lines 83–93.
- Problem: Other agent types, normal Bash, and issue-comment writes are explicitly unguarded. G1–G7 also do not check that the caller is the orchestrator.
- Failure scenario: The orchestrator uses a general-purpose agent for implementation or closes an issue through `gh api`. Alternatively, it posts a QA PASS after a QA launch without the checker completing; the marker and timestamp satisfy §5.3.
- Recommendation: State that v1 validates the prescribed calls under cooperative role behavior, rather than guaranteeing that the LLM cannot skip steps. Check caller identity for guarded launches and close. Do not expand v1 into a general Bash parser or security boundary.

### 3. Close has no usable launch-line contract — severity high, confidence 1.0

- Location: §5.1–5.4, lines 91–126; `docs/team/orchestrator.md`, line 90.
- Problem: G1 requires a launch line for every guarded call, including close, but §5.2 defines its placement only for subagent prompts and `qa-codex`. The existing close command has neither field. `gh issue close` accepts an issue number or URL, not the launcher’s custom arguments. [GitHub CLI documentation](https://cli.github.com/manual/gh_issue_close).
- Failure scenario: An otherwise valid `gh issue close 42` is denied for lacking `ROLE=close ISSUE=42`. A different implementation accepts unrelated metadata without verifying that it identifies the issue actually being closed.
- Recommendation: Exempt close from the launch-line requirement and derive its issue and repository directly from the command. Reject ambiguous or mismatched targets. Close should not create a role-launch receipt.

### 4. Ordinary hook failures do not automatically deny execution — severity high, confidence 0.98

- Location: §5.6–5.7, lines 149–155; §13, S1.
- Problem: “If `gh` or `git` fails, deny” needs an explicit hook-output contract. Claude Code does not generally block on an ordinary nonzero exit without a blocking decision. An uncaught Python exception can therefore defeat the intended behavior. [Claude Code hooks reference](https://code.claude.com/docs/en/hooks).
- Failure scenario: `gh` fails authentication; the Python subprocess exception exits with code 1; the guarded action proceeds without a successful state check.
- Recommendation: Require exit 2 or a valid deny response for handled failures, including receipt-publication failure. Test actual hook exit behavior, not only check functions. Have S1 document the remaining startup and timeout limitations instead of claiming unconditional failure denial.

### 5. Codex receives conflicting publication and output instructions — severity high, confidence 1.0

- Location: §4, lines 72–77; §6.1, lines 170–178; §7, line 207; `docs/team/qa-engineer.md`, lines 10–14 and 40.
- Problem: The shared QA role instructs the checker to post a GitHub comment and finish with its marker and URL. The launcher instead requires JSON and reserves publication for itself. The specified role changes do not explicitly remove this conflict.
- Failure scenario: Codex posts a FAIL directly, then the launcher posts the same FAIL again, counting two returns. Or Codex returns the prescribed marker and URL and triggers schema retries.
- Recommendation: Keep one role file, but explicitly distinguish delivery: Codex returns JSON only and never publishes; Claude fallback publishes the rendered comment. Keep verification behavior shared.

### 6. Schema validation does not establish criterion coverage or verdict consistency — severity high, confidence 0.98

- Location: §6.1, lines 175–178; G6, line 126.
- Problem: A static result schema can validate field structure without proving that every issue criterion appears exactly once or that the overall verdict agrees with individual verdicts.
- Failure scenario: Codex returns `pass`, the current SHA, and one passing criterion while omitting two others. The JSON is structurally valid, and G6 permits closure.
- Recommendation: In the existing launcher, compare returned criteria with the supplied criteria and derive the overall verdict from their results. Reject missing, duplicate, or contradictory entries before publication.

### 7. QA is not bound to a stable revision of the work and criteria — severity high, confidence 0.96

- Location: §5.4, G4/G6; §6.1, lines 168–175.
- Problem: The launcher accepts an orchestrator-supplied range and compares a model-supplied SHA only with the final HEAD. Neither the range’s relationship to Engineer DONE nor changes to the issue’s criteria are checked.
- Failure scenario: The issue gains a new acceptance criterion after QA reads it. HEAD stays unchanged, so the old PASS still authorizes closure against the revised issue.
- Recommendation: Resolve the range from the issue’s Engineer DONE receipt, capture HEAD and the acceptance criteria before QA, and reject publication or closure if either changed. Put this binding in the existing QA receipt, without adding another state store.

### 8. Retry exhaustion and launcher failures lack a terminal outcome — severity medium, confidence 1.0

- Location: §6.2, lines 184–193.
- Problem: Transient retries have a limit but no specified outcome after exhaustion. Unknown errors and failure to publish the final comment are also unspecified.
- Failure scenario: Four Codex attempts fail with server errors. One implementation silently exits, another reports UNAVAILABLE and invokes fallback, and another continues retrying.
- Recommendation: Specify one terminal rule: exhausted or unclassified execution failures produce INVALID and escalation. If publication fails, report that failure to the orchestrator and use the existing missing-result escalation behavior. Clarify that retry budgets apply to one launch and are finite across mixed failure types.

### 9. G1 omits open-state and escalation-state checks — severity medium, confidence 0.99

- Location: §5.4, line 121; §10, lines 264–268; `docs/process.md`, lines 31 and 54–55.
- Problem: G1 requires `ready` and excludes `later`, but does not require an open issue or exclude `needs-owner`. The ready-only selection rule also repeatedly selects an issue carrying both `ready` and `later`.
- Failure scenario: An escalated issue accidentally retains `ready` alongside `needs-owner`; a permitted transition starts without owner resolution. An issue carrying `ready,later` can instead remain permanently selectable but unlaunchable.
- Recommendation: Require open state and absence of `needs-owner` in G1. Specify that contradictory labels stop selection with an owner-facing explanation, rather than retrying the same denied issue.

### 10. The frontend flow does not bind verification to the committed submodule revision — severity high, confidence 0.95

- Location: §9.2–9.3, lines 239–251.
- Problem: Criteria are checked before fetching the submodule, and `update --remote` selects a tracking-branch tip rather than a specific Lovable result. The shown QA diff also omits the commit range; on a clean committed tree, bare `git diff --submodule=diff` shows no task changes. [Git submodule documentation](https://git-scm.com/docs/git-submodule).
- Failure scenario: The Lovable preview satisfies the criteria, but GitHub synchronization is delayed. The engineer fetches an older tip, or a later unrelated tip, while QA examines an empty working-tree diff.
- Recommendation: Make S3 establish how to identify the completed change’s GitHub revision. Fetch and pin that revision before checking the result, and specify `git diff --submodule=diff <base>..<head>` with the required submodule objects available.

### 11. “UI not exercised” has no defined effect on PASS — severity medium, confidence 0.98

- Location: §7, lines 199–205; §9.3, line 251.
- Problem: The frontend exception permits build, tests, and code reading when browser execution is unavailable, but does not define whether unverified visual or interaction criteria may pass.
- Failure scenario: The canvas builds successfully but renders nothing. QA cannot run a browser, records the limitation, and still posts PASS for the curve-display criterion.
- Recommendation: State that a criterion without sufficient evidence cannot receive PASS. Use the existing INVALID/escalation path for an environmental inability to verify, unless another available check actually proves that criterion.

### 12. Mandatory review files create avoidable lifecycle friction — severity medium, confidence 0.98

- Location: §8, lines 215–220; §5.4, G1.
- Problem: Every review must create a repository file, although review is an optional conversational operation and all subsequent guarded calls require a clean tree. The design then adds a separate rule to prevent reading accumulated reviews.
- Failure scenario: The owner requests a review during a paused loop. The new untracked review file blocks the next launch, forcing an unrelated commit or owner intervention.
- Recommendation: Return reviews in the conversation by default and save them only when requested. This removes mandatory artifacts and the need for the “do not read old reviews” process rule.

### 13. Cross-vendor verification is a preference, not an invariant — severity low, confidence 1.0

- Location: §1, line 16; §4, line 73; §6.2, line 189.
- Problem: The purpose promises a different vendor for every result, while automatic Claude fallback can verify Claude implementation.
- Failure scenario: Codex reaches its usage limit; Claude implements and Claude verifies, while the documented invariant still claims cross-vendor checking.
- Recommendation: Describe Codex as the default checker with an explicit same-vendor fallback exception. Retain the existing checker footer.

## Checked and OK

- Claude Code exposes the Agent prompt and subagent type to hooks and supports blocking decisions. [Hooks reference](https://code.claude.com/docs/en/hooks).
- `codex exec --output-schema ... -o ...` is a supported structured-output pattern. [Official OpenAI documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
- Lovable provides an MCP server for agent-driven project work; the synchronization spike remains appropriate. [Lovable MCP](https://lovable.dev/mcp).
- A frontend section in the existing engineer role avoids an unnecessary separate role document.
- Deferring Jev, parallel execution, and CI-based closure keeps the initial enforcement scope smaller.
- No files changed. No implementation tests ran; this was a design review.
## Decisions

Decided by the owner together with Claude on 2026-09-25.

| # | Decision | Reason / what changed |
|---|---|---|
| 1 | Partly taken | Pending state added: while the newest launch has no result, every guarded call is denied. Attempt IDs in results rejected: with the pending rule, no newer attempt can start, so a late result cannot be mixed up |
| 2 | Partly taken | Purpose and principle reworded: hooks check the prescribed calls and are not a security boundary. Caller-identity check rejected: extra mechanism, and a close by a subagent is already checked |
| 3 | Taken | Close needs no launch line; the hook reads the issue number from the command; no launch comment for close |
| 4 | Taken | Any hook error gives an explicit deny; entry-point tests added; spike S1 checks deny and crash behavior |
| 5 | Taken | One delivery rule in the QA role file: under `qa-codex`, return JSON only |
| 6 | Taken | `qa-codex` checks one entry per criterion and derives the overall verdict in code |
| 7 | Partly taken | `qa-codex` reads the range from the newest Engineer DONE comment (no range argument). Criteria binding rejected: changed criteria go through Owner RESUME and PM grooming |
| 8 | Taken | Exhausted retries and unknown errors give QA INVALID; a failed post leaves the issue pending |
| 9 | Taken | G1 also requires an open issue without `needs-owner`; the issue list command leaves out `later` and `needs-owner` |
| 10 | Taken | The engineer pins the exact Lovable commit (spike S3 finds out how); QA diff command gets the range |
| 11 | Taken, changed | A criterion without enough evidence cannot pass. Browser-based QA is a precondition of the frontend lane (spike S2); if it is not possible, the owner decides before frontend work starts |
| 12 | Rejected | Reviews always produce a file (owner decision). The clean-tree friction is solved differently: each finding gets a decision in the review file, and the review file is committed |
| 13 | Taken | Reworded: Codex is the default checker; the Claude fallback is a marked exception |
