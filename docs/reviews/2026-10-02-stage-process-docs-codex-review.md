# Codex review: stage-process-docs

- Date: 2026-10-02
- Target: e86be75d4ef4057e92b8510835d46879aabd1f95..74fda6901cec200596a3963058b37e9612a219a2
- Verdict: needs-attention

## Summary

Reviewed the requested diff and related process instructions. Found one stage-lifecycle gap. Tests were not run because the changes are documentation-only.

## Findings

### 1. [medium] Retain the active stage when its last ready issue leaves the queue

- File: docs/team/orchestrator.md:28-32
- Confidence: 0.94

The fallback declares that no stage is active whenever no open ready issue has a stage parent. After closing the stage's last task, this condition becomes true, allowing the loop to pick unrelated ready issues instead of stopping and reporting the stage finished. The same problem occurs when the last ready task is escalated: ready is removed, so the stage loses its scope boundary even though it still has unfinished work. The instructions do not specify retaining the selected stage or checking its completion before applying this fallback.

Recommendation: Discover the active stage at loop entry and retain its identity for the run. After closing or escalating a task, check that stage's completion and remaining eligible work before any fallback to unrelated issues. Mirror this rule in docs/process.md.

Decision: taken - confirmed in the text; filed as #117 (Keep the active stage for the whole run), a sub-issue of Stage 2 (#93), so the fix goes through PM, engineer and QA

## Next steps

- Clarify stage retention and verify the last-task closure and last-task escalation scenarios with an unrelated ready issue present.
