# Codex review: big-picture-lean-docs-research

- Date: 2026-10-01
- Target: docs/research/big-picture-and-lean-docs.md
- Verdict: needs-attention

## Summary

The report is useful, but three conclusions overstate the evidence or misdescribe workflow behavior. Reviewed the working-tree document and spot-checked primary sources; no commit range was supplied.

## Findings

### 1. [medium] Separate tracker authority from behavior-spec disposal

- File: docs/research/big-picture-and-lean-docs.md:284
- Confidence: 0.97

P6 presents 'no behavior spec after intake' as an observed practice, but using issues as the work backlog does not establish that behavior specs are discarded or never consulted. The report itself says the course does not describe the post-intake lifecycle. Symphony also publishes a substantial behavior SPEC.md. This unsupported inference feeds the proposed decision to archive this kit's spec and replace its code references.

Recommendation: Label P6 as a proposed option unless explicit lifecycle evidence is available. Separate disposable execution plans from durable behavior specifications, and correct the corresponding claims in sections 3.1 and 10.

Decision: taken - the report now separates execution plans (one-off in the sources) from behavior specs (kept living in every source that has one, Symphony's own SPEC.md included). P6 covers the plan part as observed and marks archiving the spec as an unobserved option. Sections 3.1, 7, 8, 9 (question 1) and 10 are corrected.

### 2. [medium] Correct Beads' parked-work promotion mechanism

- File: docs/research/big-picture-and-lean-docs.md:90
- Confidence: 0.99

Running `bd ready` does not promote deferred work: deferred issues are excluded from its default output even when they have no blockers. The cited [Beads defer documentation](https://github.com/gastownhall/beads/blob/main/docs/cli-reference/defer.md) explicitly distinguishes deferred work from blocked work. As written, the report suggests a scheduler can solve parked-backlog promotion merely by querying unblocked tasks, leaving the actual promotion step undefined.

Recommendation: Describe readiness queries separately from undefer or scheduling decisions, and state who makes those decisions—or mark that responsibility as unverified.

Decision: taken - section 2.2 now says that `bd ready` leaves out deferred issues, that they return by an explicit undefer or a `--until` time, and that who decides to undefer is not described.

### 3. [medium] Do not interpret unmerged PRs as incorrect proposals

- File: docs/research/big-picture-and-lean-docs.md:285
- Confidence: 0.99

P7 uses unmerged PR counts to support 'Not all proposals are right.' Merge status does not establish correctness. The [GitHub report](https://github.github.com/gh-aw/blog/2026-01-13-meet-the-workflows-documentation/) specifically attributes the noob tester's lower merge rate partly to improvements being too ambitious for immediate implementation. This misstates the available evidence about doc-agent false positives.

Recommendation: Report these as merge or adoption rates, with rejection reasons and correctness unknown. Only claim incorrect proposals when individual reviews establish that.

Decision: taken - P7 now reports merge rates only, names "too ambitious" as one reported reason for the noob tester, and says that correctness of unmerged PRs is not reported.

## Next steps

- Correct the three evidence-to-conclusion mismatches before using the report to choose spec lifecycle or backlog automation.
