# agent-graph-kit

A reusable set-up for AI-native development with several agents (Graph Engineering).

Target architecture:

- The Claude Code main session is the orchestrator.
- Workers are Claude Code subagents, Codex CLI, and Lovable (MCP).
- Jev (TypeSafe AI) makes fast, typed decisions at the handoffs between workers.

Current bootstrap: Claude subagents only. Which agent type takes each role, and how the orchestrator starts Codex, are open design questions.

Later, this repo becomes a Claude Code plugin.

## Status

Bootstrap. Not usable yet.

## Background

The kit builds on the workflow from the DataTalksClub [AI Dev Tools Zoomcamp](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp) by Alexey Grigorev.

## Design

- Accepted design: [docs/specs/](docs/specs/)
- Historical input: [docs/archive/](docs/archive/)
- Development process of this repo: [docs/process.md](docs/process.md)
