# Codex review: stage-close-check

- Date: 2026-10-02
- Target: 336767533093a60e28d95eb9c24dd95abf33212f..e86be75d4ef4057e92b8510835d46879aabd1f95
- Verdict: needs-attention

## Summary

Found an API compatibility gap that can block completed stage closes. Tests could not run: pytest is unavailable, and uv is blocked by the read-only filesystem.

## Findings

### 1. [high] Support sub-issue responses without an embedded repository

- File: .claude/hooks/guard.py:74
- Confidence: 0.87

The new query requires repository.full_name, but GitHub's documented sub-issue response provides repository_url without an embedded repository object. Such a valid response produces repo: null, which parse_sub_issues rejects, preventing a completed stage from closing. The tests reuse blocker fixtures containing repository.full_name and miss this case. See the [GitHub response example](https://docs.github.com/en/rest/issues/sub-issues#list-sub-issues).

Recommendation: Derive the repository identity from repository_url when repository.full_name is absent, and add a regression test using the documented response shape.

Decision: rejected - the live read of the sub-issues of #92 on 2026-10-02 returns `repository.full_name` for every entry (the documentation example is abridged); if the field were ever missing, the guard denies with `guard error`, so it fails closed and never allows a wrong close

## Next steps

- Correct the sub-issue projection and its fixtures.
- Run the guard and issue-state tests in an environment with pytest and writable temporary storage.
