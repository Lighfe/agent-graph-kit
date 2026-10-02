# Agent graph observability

- Date: 2026-09-26
- Status: deferred. Not in v1. Each item in section 4 is a GitHub issue with the label `later`. Grooming happens when the owner picks an item up.
- Research input: `docs/research/observability-in-agent-graphs.md` (with its Codex review). Tool facts, versions and variable names are there, not here, because they change often.

---

## 1. Purpose

Make the agent graph easier to understand and to improve:

- see where the loop spends time, how often it returns or escalates, and what it costs,
- debug a single run (for example a QA run that hits its timeout),
- collect the evidence that some `later` items require before they are built ("add only if …").

This spec covers the agent graph itself: the runtime (agents, tool calls, tokens) and the process (launches, results, returns). It does not cover the product that the graph builds. Production observability of the product is the on-call loop (section 6).

## 2. Principles

The kit principles (P1–P5 under the heading "Principles" in `docs/specs/agent-graph-kit.md`) apply unchanged. In addition:

| # | Principle |
|---|---|
| O1 | **The issue stays the state.** No hook, script or role reads observability data to make a decision. Launch and result comments stay the receipts |
| O2 | **Diagnostics never change results.** A failing log write, a missing backend or an exporter error never changes a QA verdict, a retry count, a comment or a hook decision |
| O3 | **Private by default.** Runtime data (transcripts, saved streams, telemetry) contains private data: account ids, email, tool arguments and tool output. It stays on the owner's machine. Nothing from it goes into issues, comments, reviews or commits unless it is checked for private data first (P5) |
| O4 | **Owner-side and optional.** The loop works the same without any of this. Agents need no knowledge of it. Role files do not change for it (P4) |
| O5 | **Process data before telemetry.** Answer a question with the issue record first. Add runtime telemetry only for what the issue record cannot answer |

## 3. Kinds of evidence

| Kind | Example questions | Source |
|---|---|---|
| Process | Time per role, returns, escalations, fallback rate | Issue comments (4.1) |
| Run record | What did Codex do in this QA run? | Saved Codex output (4.2), Claude Code transcripts |
| Quality | Did QA pass work with real defects? Is the QA effort level good enough? Is a review before intake needed? | Defects found after close (4.3), review decisions (v1 spec, section 8) |
| Runtime telemetry | Token use and cost per role, where a run spent its time | OTel export from Claude Code and Codex (4.5) |

Telemetry gives operational data only. It cannot show quality. Quality needs its own record (4.3).

## 4. Items

### 4.1 Process report (#28)

A read-only report over the issue comments of a repo.

- Measures: launch-to-result time per role, returns per issue, escalations, QA fallback rate (from the `Checker:` footer), QA FAIL reasons.
- Each measure is defined against the lifecycle rules of v1 (sections 5.3–5.5, 6.2):
  - a launch comment is posted before the call runs, and can exist without a run;
  - an attempt without a valid result is reported separately, not as a duration;
  - a continuation counts as a launch;
  - returns count after the newest `## Owner: RESUME`, and differ from launcher retries within one launch;
  - the report shows both the full history and the current cycle.
- Reuses the issue-state module of the guard. No network in the tests (fixtures).
- Output: text or Markdown on stdout. It writes nothing to GitHub.

### 4.2 QA run record (#30)

`qa-codex` keeps the Codex event stream (`--json`) of each attempt.

- Location: a private folder outside the repo and outside the temporary QA worktree (the worktree is deleted after the run).
- Owner-only file permissions. Bounded retention (by age or count).
- One file per attempt and retry, named so that it maps to the issue and the launch.
- Also kept on timeout (partial stream).
- O2 applies: a failing write never changes the QA outcome. Tests cover a write failure and a timeout.

### 4.3 Escaped defect record (#29)

A simple, public-safe record of defects found after an issue was closed with `## QA: PASS`.

- When someone finds a defect in closed work, they record it with a link to the closed issue (for example a label on the new bug issue and a reference to the closed one).
- Purpose: the evidence for "Separate Reviewer role" (#17), the QA effort level (v1 spec 6.1), and "Independent test design by QA" (#23).
- The exact form (label, marker, field) is decided in grooming. It must be readable by the process report (4.1).

### 4.4 Launch-to-runtime link (#31)

Link each launch comment to the runtime ids of that launch (Claude Code `session_id` and `tool_use_id`, from the hook input), so the owner can find the transcript or trace of a launch.

Two variants. The owner chooses one before grooming:

- (a) the guard writes the ids into the launch comment (public, opaque ids);
- (b) the guard keeps a private local map from the launch comment to the ids.

Must work for new launches and for `SendMessage` continuations. The guard must stay within its deadline (v1 spec 5.6) and never send telemetry itself.

### 4.5 Optional local telemetry (#32)

Runtime telemetry from Claude Code and Codex, sent to a local backend on the owner's machine.

- Claude Code: the owner enables it in the shell or the user settings. A repo cannot enable it (research 2.2). The kit adds nothing to `.claude/settings*.json` for it.
- Codex in `qa-codex`: `qa-codex` passes the OTel settings on the command line only when the owner opts in, because `qa-codex` ignores the user config. Signals are chosen explicitly; the destination is local unless the owner changes it on purpose. With Claude tracing on, the Codex run nests under the orchestrator's tool span.
- README: an optional set-up section with one tested local backend and the tool versions it was tested with.
- Content logging (prompts, tool input, tool output) stays off.

Before building:

1. Check the Claude Code side on the real loop surface (interactive session in VS Code): one launch, one `SendMessage` continuation, one QA retry, with synthetic data. The research could not check it (research 3.2).
2. Test one local backend with real Claude Code and Codex data.
3. Check that the tool and span names in the research are still current.

## 5. Order

1. 4.1 and 4.3 first. They need no new tool and give the evidence that other `later` items need.
2. 4.2 next. It needs nothing else.
3. 4.4 after the owner's choice of variant.
4. 4.5 last, after its checks.

Each item can be picked up alone.

## 6. Relation to the on-call loop

The on-call loop (#26) is about the product: an alert from the product in production starts an agent that finds the cause and proposes a fix. It needs product telemetry (for example OTel in the app, a backend with alerts), not agent graph telemetry.

Shared points:

- The same backend could hold both, if the owner wants one stack.
- The on-call agent's own runs can be observed with 4.4 and 4.5, like any other role.
- O1 and O3 apply there too: the alert starts work, but the state of that work lives on an issue.

## 7. Not in scope

- A hosted observability service as a default.
- A durable workflow engine as the state store (it would replace the issue as the state, against P3).
- Dashboards and alerts for the agent graph. Revisit with parallel mode (#18) or several projects.
