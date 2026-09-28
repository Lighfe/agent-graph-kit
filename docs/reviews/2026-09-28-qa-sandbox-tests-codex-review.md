# Codex review: qa-sandbox-tests

- Date: 2026-09-28
- Target: 2042a98b25fbf583fb0f6d00fcc503e98d1bb71d..72fe02a048d04fc02ad6bdf79c5f2a6c77a967dd
- Verdict: needs-attention

## Summary

The cache wiring and cleanup are covered by fake-tool tests, but the new pre-step introduces an execution risk outside the sandbox. Tests could not run because the read-only filesystem prevents uv from acquiring its cache lock.

## Findings

### 1. [high] Project discovery can execute reviewed code outside the sandbox

- File: scripts/qa-codex:262-263
- Confidence: 0.96

The cache-fill command runs `uv run` in the reviewed worktree with the full inherited environment. If that revision contains a Python project with a build backend, uv can build and install it before invoking `pytest --version`. Consequently, repository-controlled build code executes outside the QA sandbox with access to the user's environment and filesystem. Using a fixed command and requesting only the pytest version does not prevent this.

Recommendation: Warm pytest in a neutral directory with project discovery disabled. Keep repository-controlled builds inside the sandbox, and add coverage using a synthetic project build backend to verify that the pre-step does not execute it.

Decision: taken - confirmed at scripts/qa-codex:263 (cwd is the reviewed worktree, full environment, outside the sandbox); fixed in #49, since findings do not go back to the engineer of a closed issue

## Next steps

- Isolate the cache-fill operation from repository-controlled project configuration.
- Verify a real warmed-cache test run under the QA sandbox; the fake uv does not establish this behavior.
