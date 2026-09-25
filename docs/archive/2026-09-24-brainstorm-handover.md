# Brainstorm Handover: agent-graph-kit

- Source: brainstorming session in the Claude.ai project "AI Dev Tools Zoomcamp", 2026-09-24
- Purpose: transfer all decisions and open questions into the repo. The design work continues in Claude Code.
- Language: ASD-STE100 Simplified Technical English
- Status: the decisions below are accepted. Do not reopen them unless the owner asks. The open questions are not decided.

---

## 1. Purpose of agent-graph-kit

agent-graph-kit is a reusable set-up for AI-native development with several agents (Graph Engineering, as in Article 1 of AI Dev Tools Zoomcamp).

- The Claude Code main session is the orchestrator.
- Workers are Claude Code subagents, Codex CLI, and Lovable (MCP).
- Jev (TypeSafe AI) makes fast, typed decisions at the handoffs between workers.
- The kit must work for new projects with little set-up effort.
- Not every project needs the full graph. Small projects must be able to use less.

### Goals for the Jev integration (from the owner)

| # | Goal | Status after brainstorming |
|---|---|---|
| 1 | Speed | Indirect gain: fewer LLM steps and fewer human stops |
| 2 | Token usage / cost | Important. The owner hits Claude Code and Codex usage limits regularly. Review work uses the most tokens. Jev dollar cost is not a constraint (approx. $0.04 per project) |
| 3 | Decision quality | Gain on narrow, checkable decisions only |
| 4 | Fewer or better human feedback loops | Strong fit through confidence-gated escalation |

---

## 2. Decisions

### D1. Jev is an edge function, not a node

Jev does not write code, read files, or use tools. Code must send Jev a state and act on the answer. Thus, Jev is not a worker role. Jev is a router, gate, or check on the edges of the graph.

### D2. Jev works on the handoff edges

Candidate edge checks (version 1 still open, see O2):

| Edge | Check | Notes |
|---|---|---|
| PM → Engineer | Grooming quality gate | Code checks that the template sections exist. Jev checks narrow properties of each acceptance criterion (checkable, one behavior, no vague words). The human or PM judges completeness |
| Engineer → Reviewer / QA | "Done" claim gate | Stop hook. Code first checks facts: did a test run pass after the last file change? Only then Jev asks: "Does the final message claim completion?" |
| Engineer → Reviewer / QA | Review depth gate | Code rules first (for example auth, migrations, CI files → full review). Jev scores risk and file relevance. Light review only at high confidence. Never skip QA |
| QA → close | QA verdict cross-check | Jev checks if the evidence supports the QA verdict for each criterion. Disagreement → human. Jev enhances QA. Jev does not replace QA |
| Any edge → human | Escalation policy | Three confidence bands: act, ask, escalate. Stricter thresholds for risky actions |

Later candidates: commit message vs. diff; document relevance filter (outdated docs); tool-call risk gate (fewer permission prompts).

Not selected, with reasons:

| Use case | Reason |
|---|---|
| Lane routing with Jev | The lane concept stays. The PM writes the lane label into the groomed issue. Code routes on the label |
| Model / effort routing | Conflicts with "use the best model". Reframed as the review depth gate |
| Capability routing | Too few tools and agents. An LLM chooses well among 4 to 6 options |
| Supervisor with Jev | Supervision is mostly System 2. Loop limits are facts. Code counts them |
| Cheap draft, strong fallback | Conflicts with "use the best model" |
| Rule compliance | Deferred until the projects have real semantic rules |

### D3. Enforcement: hook-enforced edges (approach B)

A prose instruction ("call Jev at this step") is not reliable. The orchestrator LLM can skip it.

- Claude Code stays the orchestrator (Article 1 and Article 5 workflow).
- Each handoff is a tool call of the orchestrator (Task tool, Bash for Codex, MCP for Lovable). Claude Code hooks intercept these calls.
- Before a handoff: a hook checks that the issue passed the previous gate. If not, the hook denies the call.
- After a handoff: hooks run the edge check.
- State lives in GitHub issues (labels and comments), not in the LLM context.
- Format contract: each handoff call names the role and the issue (for example `ROLE=engineer ISSUE=12`). A call without this format is denied.
- Receipts: each gate writes a log line. Code can compare handoffs with gate records.

### D4. Prose guides, hooks guarantee

AGENTS.md, process.md and the role files stay the main description of the process. They also describe the gates. Hooks enforce only the few critical edges.

### D5. Packaging: Claude Code plugin + init command + project config

- The repo is a plugin marketplace. It holds hooks, gate code, and an init command.
- The init command writes the project parts into a new repo: AGENTS.md, `docs/`, `.agents/`, and a config file.
- The config file switches gates on, off, or to shadow mode. This also gives the "small project" option.
- Vendor-neutral parts (skills, role prose) go to `.agents/` and `docs/`, so Codex can read them too (Article 5 convention: `.claude/skills` is a symlink to `.agents/skills`).
- Gate scripts in Python: use `uv run --script` with inline dependencies (PEP 723).

### D6. Name and visibility

The repo name is `agent-graph-kit`. The repo is public. Jev is a module inside the kit (for example `gates/jev/`), not part of the name.

Consequences of a public repo:
- Never commit API keys. `TYPESAFE_API_KEY` stays in the user environment.
- Do not commit copies of third-party articles. Commit links and own notes only.

### D7. Superpowers: use with strict boundaries

| Use | Do not use |
|---|---|
| brainstorming, writing-plans (upstream: idea → spec → plan → issues) | subagent-driven-development |
| test-driven-development (technique for the engineer role) | executing-plans |
| verification-before-completion (prose version of the "done" gate) | |
| requesting / receiving-code-review (technique for the reviewer role) | |
| using-git-worktrees (parallel mode) | |

Reason: subagent-driven-development and executing-plans are a second orchestrator. They make their own rulings without asking the human. This conflicts with process.md and with the escalation policy.

If conflicts repeat, copy the used skills into the kit (fork later, only with evidence).

### D8. Folder convention

Use `docs/` everywhere (not `_docs/`). Specs go to `docs/specs/`. Plans go to `docs/plans/`. AGENTS.md overrides the superpowers default paths.

### D9. Rules for all Jev use

1. Facts (tests, exit codes, git state) can block. Jev can route, warn, or escalate. Jev alone never blocks.
2. Code builds the state for Jev. The orchestrator LLM does not.
3. Atomic questions. Many questions in one call. Combine answers in code.
4. Each Choice has an explicit "none / escalate" option.
5. All questions and thresholds are in one reviewed file.
6. Pin the model version (`jev-1.13.0`).
7. Each new gate starts in shadow mode (log only).
8. If Jev is not available: routing falls back to the default path; approvals go to the human.

### D10. Bootstrap order

1. Start the repo with a prose-only process (Article 1: PM → SWE → QA).
2. Build the kit with this process.
3. Switch on the first gates in the kit repo itself (dogfooding).

---

## 3. Open questions

| # | Question | Notes |
|---|---|---|
| O1 | Which roles exist, and which agent type takes each role? | Owner's main goal. Consider: Codex has separate usage limits, and review uses the most tokens. A different vendor for review/QA reduces "grading its own homework" |
| O2 | Which edge gates are in version 1, and in which order? | Candidates in D2 |
| O3 | Config format and levels for small vs. full projects | For example level 0 (single engineer loop), level 1 (PM/SWE/QA prose), level 2 (full graph with gates) |
| O4 | How does Lovable integrate? | Not researched. Which repo does Lovable write to? How does the orchestrator start and check Lovable work? |
| O5 | How does the orchestrator start Codex, and how does it read the Codex result? | For example `codex exec` through Bash. Not verified |
| O6 | Parallel mode (worktrees) in version 1? | Article 5 pattern |
| O7 | Process against outdated documents | Owner problem: documentation grows, outdated artifacts reappear. Jev can only help as a relevance filter. A process fix is necessary first |

### Spike candidates (verify before building)

1. Current Claude Code hook events and blocking behavior for Task, Bash, and MCP tool calls.
2. Hooks inside a Claude Code plugin: configuration and per-project options.
3. Jev accuracy on 10 to 20 real issues of the owner (grooming quality questions).
4. Size of a typical groomed issue and diff in tokens (Jev limit: 32k tokens for state + longest question).

---

## 4. References

- Jev research: `docs/research/jev_usage_documentation.md`
- Article 1: https://aishippingblog.com/p/ai-native-development-specifications
- Article 2: https://aishippingblog.com/p/build-and-ship-a-full-stack-app-with
- Article 3: https://aishippingblog.com/p/deploy-a-full-stack-app-with-ai-coding
- Article 4: https://aishippingblog.com/p/devops-and-observability-for-an-ai
- Article 5: https://aishippingblog.com/p/coding-agent-building-blocks-reusable
- TypeSafe documentation index: https://docs.typesafe.ai/llms.txt
- Superpowers: the installed Claude Code plugin

---

## 5. Requirements from the bootstrap review

Source: Codex review of the bootstrap, `docs/reviews/2026-09-24-codex-bootstrap-review.md`. The owner deferred these items to the kit. The prose process does not implement them.

| # | Requirement | Codex finding |
|---|---|---|
| R1 | Bind each result comment to one launch with an attempt ID. The orchestrator accepts only a result with the ID of the current launch | H1 |
| R2 | Reconstruct the return counter exactly from label events (for example the time when `ready` was added again), not only from comment markers | M1 |
