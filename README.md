# agent-graph-kit

A reusable set-up for AI-native development with several agents (Graph Engineering).

Target architecture:

- The Claude Code main session is the orchestrator.
- Workers are Claude Code subagents, Codex CLI, and Lovable (MCP).
- Jev (TypeSafe AI) makes fast, typed decisions at the handoffs between workers.

Current bootstrap: Claude subagents only. The role-to-agent mapping (O1) and the Codex start mechanism (O5) are open questions.

Later, this repo becomes a Claude Code plugin.

## Status

Bootstrap. Not usable yet.

## Background

The kit builds on the workflow from the DataTalksClub [AI Dev Tools Zoomcamp](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp) by Alexey Grigorev.

## Design

- Decisions and open questions: [docs/design/brainstorm-handover.md](docs/design/brainstorm-handover.md)
- Development process of this repo: [docs/process.md](docs/process.md)
