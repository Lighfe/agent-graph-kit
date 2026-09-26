# Observability in agent graphs

Research on four questions from the owner:

1. Could OpenTelemetry (OTel) or another observability tool be an optional part of the kit?
2. What value would it add?
3. Where does it conflict with the v1 design?
4. Could it replace or improve existing parts, for example the comment-based handoffs?

- Research date: 2026-09-26
- Sources: web search, vendor docs, one local experiment (section 3). Vendor comparisons are marked. Most of them come from tool vendors and are not neutral.
- Review: Codex, `docs/reviews/2026-09-26-observability-research-codex-review.md`. The findings are worked into this version.
- Status: research input. Nothing here changes the v1 spec. The owner deferred the topic; the resulting spec is `docs/specs/2026-09-26-agent-graph-observability.md`.

---

## 1. Three kinds of observability

The word covers three different things. They need different answers.

| Level | Question | Where the data is |
|---|---|---|
| Runtime | What did each agent do: LLM calls, tool calls, tokens, time, errors? | Local transcripts (section 2.5). The owner has not configured an OTel export. Vendor telemetry to Anthropic or OpenAI is a separate topic, not checked here |
| Process | How does an issue move through the graph: launches, results, returns, escalations, time per role? | The issue comments. Today (bootstrap, prose only) the role results. With v1 hooks also a launch comment per launch (spec 5.3) |
| Product | Does the built app work in production: errors, latency, alerts? | Nowhere yet. This is the on-call loop, issue #26 (`later`) |

This document is about runtime and process. The product level is a separate graph (issue #26 and `qa-and-cicd-in-agent-graphs.md`, section 2).

## 2. Findings: the standard and the tools

### 2.1 OTel GenAI semantic conventions

- OTel describes an agent run as a span tree: `invoke_agent` (one agent run), `chat` (one model call), `execute_tool` (one tool call), `create_agent`.
- Status mid-2026: the GenAI conventions, including the agent spans, are "Development" (formerly "experimental"). None of them is stable.
- Several LLM observability tools (Langfuse, Arize Phoenix, OpenLLMetry, Laminar) read these conventions or the similar OpenInference conventions. Claude Code and Codex use their own attribute names (`claude_code.*`, `codex.*`), not only `gen_ai.*`. A tool shows token and cost views only if it maps these names. This is not tested here.

### 2.2 Claude Code

From the Claude Code monitoring docs. **Not reproduced here** (section 3.2).

- Switch: `CLAUDE_CODE_ENABLE_TELEMETRY=1`, plus the standard `OTEL_*` exporter variables.
- Where the switch can be set: the shell, the user's `~/.claude/settings.json`, or managed settings. **Not** in the repository's `.claude/settings.json` or `.claude/settings.local.json`: Claude Code ignores the exporter variables there, so a repo cannot turn telemetry on or choose where it goes. A repo can only turn signals off.
- Metrics: sessions, cost (USD), tokens, lines of code, commits, PRs, active time, edit decisions.
- Events (logs): `user_prompt`, `api_request`, `api_error`, `tool_decision` (with `source`: `config`, `hook`, `user_…`), `tool_result`. Each event has `session.id` and `prompt.id`.
- Traces: **beta**, with `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`. Tree: `claude_code.interaction` → `claude_code.llm_request`, `claude_code.tool`. A subagent's spans nest under the `claude_code.tool` span of its Agent call. Tool spans carry `tool_use_id`, `subagent_type`, `agent_id`, `parent_agent_id`.
- Hook spans (`claude_code.hook`) need a second, separate beta: `ENABLE_BETA_TRACING_DETAILED=1` and `BETA_TRACING_ENDPOINT`, which also changes where logs and traces go. They show that a hook blocked a call (`num_blocking`), not which check (G1–G8) failed. The check is only in the deny message (spec 5.6).
- Content: prompts, tool inputs and tool outputs are `<REDACTED>` by default. Separate switches turn each one on.
- Trace context: with tracing on, Bash subprocesses get `TRACEPARENT` from the tool span. `claude -p` and SDK sessions read an inbound `TRACEPARENT`. **Interactive sessions ignore it.** The orchestrator runs interactively in VS Code.
- Standard attributes include user and account ids and `user.email`, and, if enabled, the repository URL.

### 2.3 Codex CLI

- Config: an `[otel]` table in `config.toml` (`exporter`, `trace_exporter`, `metrics_exporter`, `environment`, `log_user_prompt`).
- Events: `codex.conversation_starts`, `codex.api_request`, `codex.user_prompt`, `codex.tool_decision`, `codex.tool_result`, and others. Prompts are redacted by default. The docs say `tool_result` carries output snippets.
- An older GitHub issue (openai/codex#12913) said that `codex exec` sends no metrics. It is closed. The experiment in section 3.1 saw metrics.

### 2.4 Backends

The backends differ in which signals they take (traces, metrics, logs), in LLM-specific views, and in set-up work. OTLP transport alone does not give token or cost views for the Claude and Codex attribute names (2.1).

| Backend | Signals | LLM views | Set-up |
|---|---|---|---|
| Jaeger all-in-one | Traces only | No | One process or container |
| `grafana/otel-lgtm` | Traces, metrics, logs (Tempo, Prometheus, Loki, Grafana in one container) | No, only generic dashboards | One container, for development |
| otel-desktop-viewer, otel-tui | Mainly traces | No | One binary, for local debugging |
| Arize Phoenix | Traces | Yes (OpenInference) | One process (pip or container) |
| Laminar, Comet Opik | Traces | Yes | Self-host by container or Helm (vendor claims) |
| Langfuse | Traces | Yes, plus datasets and evals | Several services (web, worker, Postgres, ClickHouse, Redis, object storage). Needs attribute mapping for non-standard names |
| Hosted (Langfuse Cloud, LangSmith, Datadog, Grafana Cloud, SigNoz) | Depends | Depends | Sends the configured fields to a third party. LangSmith self-host is enterprise-only |

No backend was tested with real Claude Code or Codex data in this research.

### 2.5 Alternatives without OTel

- **Hook event dashboards.** Several open-source projects (for example `disler/claude-code-hooks-multi-agent-observability`) register hooks on every event and send them to a local server with a live UI: swim lanes per agent, tool calls, failures. There is no standard format. It adds hooks next to the guard hook. Compatibility with the guard is not checked.
- **Transcripts.** Claude Code writes every session to `~/.claude/projects/<project>/<session>.jsonl` and each subagent to `<session>/subagents/agent-<id>.jsonl` (seen locally). Tools like `ccusage` compute cost from them. The hook input already has `session_id`, `agent_id` and `transcript_path` (S1).
- **Codex JSON stream.** `qa-codex` runs `codex exec --json --ephemeral` (plan, Task 6). `--json` prints every event on stdout. `--ephemeral` stops the session rollout file. Codex still writes its state and log databases in `$HOME/.codex` (S2), but there is no retained, readable record of one QA run unless `qa-codex` keeps the stream.
- **The issue itself.** The comments are the process record, with timestamps. They are append-only by the process rules, not by GitHub (comments can be edited or deleted). Durations, return counts, fallback rate and escalations can be read from them with `gh`, if each measure is defined against the lifecycle rules (section 6, E3).

## 3. Experiments

### 3.1 Codex: author-observed, Codex CLI 0.153.4

These are the author's observations from one run, not independently checked. Raw captures are not kept (they contain private data). To reproduce: start a small OTLP/HTTP receiver on `127.0.0.1` that saves each POST body (about 10 lines of Python stdlib), then run:

```
TRACEPARENT=00-4bf92f35…4736-00f067aa0ba902b7-01 \
codex exec --ignore-user-config --ephemeral -s read-only -C <scratch repo> \
  -c 'otel.exporter={otlp-http={endpoint="http://127.0.0.1:<port>/v1/logs",protocol="json"}}' \
  -c 'otel.trace_exporter={otlp-http={endpoint="…/v1/traces",protocol="json"}}' \
  -c 'otel.metrics_exporter={otlp-http={endpoint="…/v1/metrics",protocol="json"}}' -
```

Prompt: run `echo hi`, then answer "done".

Observed:

1. `--ignore-user-config` does not stop telemetry when `-c` sets the `otel` keys. Logs, traces and metrics all arrived. This matters for `qa-codex`: it uses `--ignore-user-config`, so an `[otel]` block in the user's `config.toml` would be ignored. Only `-c` overrides work.
2. Codex reads `TRACEPARENT` from the environment. Its root span `codex.exec` was a child of the given span, and 17 log records carried the given trace id.
3. Volume: 470 spans for one trivial run (auth, plugin loading, MCP, tool routing, and so on), and 55 metric names. 425 spans were in the given trace. The other 45 were in 13 separate traces (start-up and background work), so not all of a run nests under the caller's span.
4. Content: `codex.user_prompt` had `prompt: [REDACTED]`. But `codex.tool_result` had the tool **arguments** (`{"cmd":"echo hi"}`) and the tool **output** in clear text. Several log records carried the owner's email address. The documented config has no switch to redact tool output; the author found none.

### 3.2 Claude Code: not done

The planned experiment was one `claude -p` run with tracing on, a PreToolUse hook that prints its environment, one Bash call and one subagent launch. The auto-mode permission check denied the nested `claude` run. Section 2.2 is from the docs only.

A headless run would not be enough anyway: the loop runs interactively in VS Code (spec 5.9), and interactive sessions behave differently for trace context. The real check is one launch, one `SendMessage` continuation and one QA retry on the real loop surface, with synthetic data.

## 4. Value for this kit

Telemetry gives **operational indicators** (tokens, time, errors). It does not give **quality evidence** (was the work good?). The kit's open questions need both:

| Question | Kind | What answers it |
|---|---|---|
| Why did a QA run hit the 30-minute timeout? | Operational | Codex spans, or the saved `--json` stream (E2) |
| Why is an issue pending, or which check denied a launch? | Operational | The deny message names the check (spec 5.6). Telemetry shows only that a hook blocked |
| Cost and tokens per issue and per role | Operational | Claude cost metric (per session), Codex token metrics. Per issue needs a correlation key (E1) |
| How often does the Claude fallback run instead of Codex? | Operational | The `Checker:` footer on the QA comments (E3) |
| Does a Jev input fit Jev's limit (#13: state + longest question within 32k tokens)? | Payload size | Tokenize the real inputs. Runtime token totals do not answer this |
| Is `medium` reasoning effort good enough for QA (spec 6.1)? | Quality | Defects that QA missed and that were found later, compared by effort level. Tokens and durations alone do not answer this |
| Does QA pass work with real quality problems (#17)? | Quality | Independently found defects after a PASS. A report over QA's own verdicts cannot find false negatives |
| Does QA often find missing tests (#23)? | Quality, partly operational | QA FAIL reasons on the issues (E3, with a reason category) |
| Is a review before intake needed (#20)? | Quality | Review files and the decision on each finding (spec 8), not issue returns |

Conclusions:

- The cheapest useful data is **process data** that is already on the issues (E3). It shows where the loop spends time and how often it returns or escalates. It does not by itself prove quality.
- Quality questions (#17, #20, and the effort level) need records that do not exist yet: defects found after close, and review decisions. These are cheap to start (for example a label or a line in the issue when a defect escapes), but they are not telemetry.
- Runtime telemetry mainly helps with **debugging** (a hung QA run, a strange tool call) and **cost and tokens**. For one owner and one issue at a time, dashboards and alerts add little. They matter more with parallel mode (#18), many projects, or a team.
- So yes, observability matters for AI-native development. For this kit, the largest part of the process view already exists by design (P3). The gap is in quality records, not in tracing.

## 5. Conflicts with the v1 design

| Design point | Conflict | How an optional integration avoids it |
|---|---|---|
| P3: state lives on the issue | Telemetry is not designed as state: export is batched, config can turn it off, and data can be lost or delayed unless the collector is set up for retries and persistent queues. Backends are not the source of truth | Hooks and scripts never read telemetry for a decision. It is a side channel only |
| P2: facts only | None, as long as no gate reads telemetry | Same rule as above |
| 5.7: "the launch comments are the receipts; there is no separate log" | Telemetry is a separate log | Receipts stay on the issue. Telemetry is diagnostics, not a receipt. Say so in the spec if telemetry is added |
| P4: few agent-facing files | A collector config and env variables add files | Agents need to know nothing about telemetry. The owner sets it in the shell or `~/.claude/settings.json` (a repo cannot, 2.2). README set-up gets an optional step. No role file changes |
| 5.9: settings protection | Project settings are protected from agent writes, and a repo cannot set OTel exporters anyway | Keep telemetry config owner-side. The kit adds nothing to `.claude/settings*.json` for it |
| P5 and the public repo | Telemetry and saved streams contain private data: email, account ids, repository URL, Codex tool arguments and output in clear text (3.1), prompts if enabled | Local backend only by default. Content switches stay off. Nothing from telemetry or saved streams goes into issues, comments or reviews without being checked for private data first |
| Guard hook: fail closed, 60 s deadline (5.6) | If the guard sends telemetry synchronously and the collector hangs, the guard hits its deadline and denies | The guard sends no telemetry |
| `qa-codex` isolation (6.1): `--ignore-user-config` | The user's `[otel]` block is ignored | `qa-codex` passes `-c otel.*` only when the owner opts in (E4) |
| `qa-codex` failure rules (6.2) | Diagnostics could change retries, timeouts, cleanup or comment delivery | A failing log write or exporter never changes the QA result, the retry count or the comment. Tests cover this (E2, E4) |
| Orchestrator runs interactively in VS Code | Interactive sessions ignore inbound `TRACEPARENT`. A trace root is one interaction (one user prompt), not one issue. `OTEL_RESOURCE_ATTRIBUTES` is fixed per process, so it cannot carry the issue number of a loop that works on many issues | Link by IDs instead of by trace tree (E1) |
| Beta status | Claude Code traces and hook spans are beta, and the GenAI conventions are not stable. Names can change | Treat like `network_proxy` (6.1): check after each update. Nothing in the kit depends on span names |

No conflict blocks an optional, owner-side integration. The real limits are private data (P5) and the missing per-issue correlation.

## 6. Replace or improve the comment handoffs?

**Replace: no.** The reason is the accepted contract, not a technical limit of telemetry:

1. **P3 makes the issue the state.** Sections 5.3–5.7 define how the hooks read it: valid results, pending, current result, returns. The launch comments are the receipts (5.7).
2. **Consistent reads for cooperating guards.** The guard holds a local file lock from reading the facts until the launch comment is posted (5.7). This serializes the guards on one machine. It does not make GitHub transactional and does not stop a hand-written comment (P1 says so). But a telemetry backend has no role in this contract at all.
3. **Audience.** The owner reads and answers on the issue (`## Owner: RESUME`). The next role reads its input there.
4. **Public/private split.** A comment is a short, public-safe summary. Telemetry holds private detail.

A better frame: the comments are the **process record** (few events, the source of truth by design, public). Telemetry is the **diagnostic signal** of the runtime (many events, private). They complement each other.

A durable workflow engine (Temporal, LangGraph checkpoints) could hold the state instead of the comments. As the source of truth, it would move state off the issue, against P3. That is a different design and out of scope.

**Improve: yes, in small steps.** Ordered from cheapest. Each needs a groomed issue with acceptance criteria.

| # | Change | Requirements | Depends on |
|---|---|---|---|
| E1 | Link each launch to its runtime IDs (`session_id`, `tool_use_id` from the hook input) | Two variants: (a) the guard writes the IDs into the launch comment (public, opaque IDs); (b) the guard keeps a private local map from the launch comment URL to the IDs. Must work for new launches and `SendMessage` continuations | Owner decision (a) or (b). A check on the real loop surface (3.2) |
| E2 | `qa-codex` keeps the Codex `--json` stream of each attempt | Private folder outside the repo and outside the temporary worktree (which is deleted, 6.1). Owner-only file permissions, bounded retention, one file per attempt and retry. Also kept on timeout (partial). A failing write never changes the QA result (6.2). Tests for timeout and write failure | Nothing. A modest change in `qa-codex`, more than a few lines |
| E3 | A read-only process report over the issue comments | Reuses the issue-state parser (Task 4). Defines each measure against the lifecycle rules: "launch-to-result time" (a launch comment is posted before the call runs and can exist without a run, 5.9); incomplete attempts separately; continuations count as launches (5.3); returns reset after `## Owner: RESUME` (5.4) and differ from launcher retries within one launch (6.2); history and current cycle separately | Task 4 (closed). One script with fixtures |
| E4 | `qa-codex` passes `-c otel.*` when the owner opts in | Opt-in variable, enabled signals chosen explicitly, local destination only (`127.0.0.1`) unless the owner changes it on purpose. The exporter runs in the Codex CLI process; the QA sandbox does not limit it. An exporter failure never changes the QA result. With Claude tracing on, Bash gives `qa-codex` a `TRACEPARENT`, so Codex nests under the orchestrator's tool span (3.1) | The Claude side of 3.2. One backend tested with real data |
| E5 | README: optional section "Local telemetry" | The Claude Code variables go in the shell or `~/.claude/settings.json`, not the repo (2.2). One tested local backend. The Claude Code version it was tested with | E4 for the Codex part |

What stays unsolved: one trace per issue. The interactive orchestrator starts a new trace per user prompt, and its issue loop spans many prompts or one long one. E1 is the practical link between an issue and its traces.

## 7. Options for the owner

1. **Nothing in v1.** Add one `later` issue "Observability of the agent graph (optional)" with a pointer to this file. Lowest risk, because v1 is about proving the guarded loop.
2. **Owner-side only, now.** The owner turns on Claude Code telemetry in their own shell or `~/.claude/settings.json`, with a local backend. No kit change. Exported runtime data then covers the Claude side only. The Codex side stays visible only through the QA comments until E2 or E4.
3. **Small kit changes.** E2 and E4 touch `qa-codex` (Task 6, which has `ready`). If wanted, they belong in Task 6 before the engineer starts, or in a follow-up issue. E1 touches the guard (Task 5, `ready`) and needs the public-or-private decision.

Recommendation: option 1. When the issue is picked up, start with E3 and E2. They need no telemetry backend and are the cheapest. E3 answers the operational questions of section 4. Also start a simple record of defects found after close, because the quality questions (#17, #20, effort level) need it and telemetry cannot give it. E4 and E5 come after the check of 3.2 on the real loop surface.

---

## Sources

- OTel blog, GenAI observability: https://opentelemetry.io/blog/2026/genai-observability/
- GenAI conventions: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md
- GenAI agent spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
- GenAI conventions status: https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke
- Claude Code monitoring: https://code.claude.com/docs/en/monitoring-usage
- Claude Agent SDK observability: https://code.claude.com/docs/en/agent-sdk/observability
- Codex advanced config (OTel): https://learn.chatgpt.com/docs/config-file/config-advanced
- Codex issue on `codex exec` metrics: https://github.com/openai/codex/issues/12913
- OTel Collector resiliency: https://opentelemetry.io/docs/collector/resiliency/
- Jaeger architecture: https://www.jaegertracing.io/docs/latest/architecture/
- Grafana otel-lgtm: https://grafana.com/docs/opentelemetry/docker-lgtm/
- Langfuse OTel integration: https://langfuse.com/integrations/native/opentelemetry
- Langfuse self-hosting: https://langfuse.com/self-hosting
- Arize Phoenix: https://github.com/Arize-ai/phoenix
- LangSmith self-hosted: https://docs.langchain.com/langsmith/self-hosted
- Phoenix vs Langfuse (vendor comparison): https://www.morphllm.com/comparisons/arize-phoenix-vs-langfuse
- LLM observability tools (vendor comparison): https://openobserve.ai/blog/llm-observability-tools/
- Hook event dashboard: https://github.com/disler/claude-code-hooks-multi-agent-observability
- Request for agent context in hook payloads: https://github.com/anthropics/claude-code/issues/16424
- Zoomcamp Article 4 (observability, on-call agent): `docs/references/summaries/04-devops-and-observability-summary.md`
- Local experiment 3.1 and the S1/S2 spike findings in `docs/research/`
