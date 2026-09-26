# Codex review: observability research

- Date: 2026-09-26
- Reviewer: Codex (codex exec, read-only)
- Target: docs/research/observability-in-agent-graphs.md

## Verdict

**needs-attention**

The main recommendation is sound: defer integration, preserve issue comments as authoritative state, and explore inexpensive diagnostics first. However, the document overstates backend compatibility and what process metrics can establish, and understates the safety and implementation requirements of E2–E5. These findings call for revisions to the research, not a different v1 architecture.

## Findings

### 1. E2 and E4 need explicit privacy and failure-handling requirements — severity medium, confidence 0.97

- Location: sections 5–6, lines 127–129 and 153–156.
- Problem: A gitignored folder prevents ordinary accidental staging but does not protect retained tool output from other local agents, backups, or later publication. The document itself reports unredacted Codex arguments and output. E2 also needs to preserve partial output on timeout, distinguish retries, and store files outside the temporary worktree that the launcher deletes. E4 specifies an arbitrary endpoint without defining destination validation or exporter-failure behavior. Optional diagnostics must not change QA classification, retry limits, cleanup, or comment delivery: spec §6.1, lines 206–215; §6.2, lines 225–234. P5, line 30, applies to any diagnostic material subsequently published.
- Recommendation: Define private storage, restrictive permissions, bounded retention, per-attempt filenames, and sanitization before publication. Test timeout capture and logging/export failures without changing QA outcomes. For E4, explicitly select enabled signals and a local destination; do not assume the QA tool sandbox constrains the CLI’s exporter. Include these requirements in the estimates: both remain modest changes, but are more than an unconditional “few lines.”

### 2. Claude Code configuration and hook-span claims need correction — severity medium, confidence 0.99

- Location: section 2.2, lines 40–45; section 5, lines 126 and 128; E5, line 156.
- Problem: Current official documentation says repository `.claude/settings.json` and `.claude/settings.local.json` cannot enable or redirect OTel exporters. It also marks `claude_code.hook` spans as requiring detailed beta tracing; the documented beta switch alone does not establish the hook coverage claimed here. Consequently, the project-local setup suggestion can fail, and relying on a hook span to explain a denied check is overstated. [Claude Code monitoring documentation](https://code.claude.com/docs/en/monitoring-usage).
- Recommendation: Recommend shell, user-level, or managed settings and record the supported Claude Code version. Specify the additional hook-tracing requirements and distinguish “a hook blocked” from the actual G1–G8 deny reason. Preserve owner-managed configuration: spec §5.9, lines 191–198, deliberately protects project settings from agent writes.

### 3. OTel transport support does not establish backend or LLM-view compatibility — severity medium, confidence 0.99

- Location: sections 2.1 and 2.4, lines 34 and 56–63; section 7, line 163.
- Problem: “Every OTel backend accepts the data above” is false across logs, metrics, and traces. Jaeger is a tracing backend; `grafana/otel-lgtm` bundles components for multiple signals, so the table’s “generic traces” description also obscures a meaningful difference. Moreover, accepting OTLP spans does not guarantee automatic token, cost, or agent views for vendor-specific Claude/Codex attributes. Langfuse explicitly documents attribute mapping requirements. [Jaeger architecture](https://www.jaegertracing.io/docs/latest/architecture/), [Grafana LGTM](https://grafana.com/docs/opentelemetry/docker-lgtm/), [Langfuse OTel integration](https://langfuse.com/integrations/native/opentelemetry).
- Recommendation: Compare supported signals, protocols, semantic mappings, persistence, and deployment requirements separately. Mark direct Claude/Codex ingestion and LLM views as untested until demonstrated. Remove unsupported superlatives such as “lightest” and “most features,” or provide defined comparison criteria. Hosted export sends whatever fields are configured; it does not inherently send prompts and code.

### 4. The proposed measurements cannot answer several stated quality questions — severity medium, confidence 0.98

- Location: section 4, lines 105–115; E3, line 154; recommendation, line 166.
- Problem: Runtime token totals do not measure whether a particular Jev input fits its context limit. That requires tokenizing the actual state plus longest question, as specified in §3, line 50. Similarly, token counts, durations, and QA’s own verdicts cannot establish whether `medium` reasoning is adequate or whether QA passed defective work. A report cannot discover false negatives absent independently recorded defects. The evidence for a required intake review also concerns reviewed specs and finding dispositions, not merely issue returns: spec §3, lines 54, 57, and 60.
- Recommendation: Distinguish operational indicators from quality evidence. Add direct payload-size measurement for Jev, independently identified escaped defects for QA quality, and review-outcome records for intake policy. Keep E3 first, but narrow the claim that E3 and E2 “answer” all evidence-gated questions.

### 5. E3 needs defined lifecycle semantics before its outputs are trustworthy — severity medium, confidence 0.97

- Location: sections 2.5 and 4, lines 70 and 109–115; E3, line 154.
- Problem: Simple timestamp subtraction and marker counting would misreport this graph. Launch receipts precede execution and can exist even when permission prevents execution (§5.9, line 196). Results must satisfy the newest-launch rule; continuations count as launches; pending attempts may end through owner intervention (§5.3, lines 106–124). Return counts reset after RESUME (§5.4, line 136), while launcher retries occur within one launch (§6.2, line 232). These distinctions affect durations, returns, and fallback denominators.
- Recommendation: Reuse the planned issue-state parser and explicitly define each measure. Call timestamp differences “launch-to-result elapsed time,” report incomplete attempts separately, distinguish retries from returns, and define historical versus current-cycle counts. “One small script” is plausible with parser reuse and focused fixtures, but “depends on nothing” is misleading.

### 6. Section 6 reaches the right conclusion using overly absolute guarantees — severity low, confidence 0.98

- Location: section 2.5, line 70; section 5, line 123; section 6, lines 137–146.
- Problem: GitHub comments are editable and deletable, so they are append-only by process convention, not platform guarantee. The local lock serializes cooperating guards; it does not make GitHub reads and writes transactional or exclude manual comments. P1 explicitly acknowledges unguarded calls (§2, line 26). Conversely, telemetry need not be sampled, and collectors support retries and persistent queues; outages do not invariably lose data. [GitHub comment APIs](https://docs.github.com/en/rest/issues/comments), [OTel collector resiliency](https://opentelemetry.io/docs/collector/resiliency/).
- Recommendation: Ground “replace: no” in the accepted contract: P3 designates issue state, and §§5.3–5.7 define its interpretation and receipts. Describe the lock’s actual scope (§5.7, lines 167–169). A workflow engine would violate P3 if made authoritative, but adding one does not inherently eliminate prose guidance or hook checks.

### 7. “Today,” “no telemetry,” and “nothing local” conflate different states — severity low, confidence 0.99

- Location: section 1, lines 22–23; section 2.5, line 69; section 7, line 163.
- Problem: The process still explicitly says hooks do not exist (`docs/process.md`, line 5), so universal launch receipts describe intended v1 behavior rather than today’s repository. `--ephemeral` suppresses session rollout files, not every local artifact: S2 records state and log database writes (`spike-codex-cli.md`, line 23). Official Codex configuration also lists a default Statsig metrics exporter, making “no telemetry is on” too broad without checking effective configuration. [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
- Recommendation: Separate bootstrap, intended v1, owner-configured exports, and vendor operational telemetry. Say ephemeral QA lacks a retained session rollout unless the launcher captures one. Replace “invisible until E4” with a narrower statement about exported runtime diagnostics; E2 and the QA comments already provide other visibility.

### 8. Experimental evidence and remaining uncertainty need clearer boundaries — severity low, confidence 0.94

- Location: sections 3.1–3.2, lines 76–97; E1 and E4, lines 152–155; sources, line 185.
- Problem: I could not independently verify the reported 470 spans, 55 metric names, trace-parent counts, universal email presence, or absence of a tool-output redaction switch in the tested release. The repository contains the narrative but no linked sanitized receiver implementation or reproducible assertions. The proposed headless Claude experiment also would not establish behavior on the interactive VS Code surface required by spec §5.9, line 198. E1’s IDs are supported by S1, but their complete mapping through continuations and the chosen backend remains untested.
- Recommendation: Label these as author-observed results for Codex 0.153.4, distinct from independently checked documentation. Preserve synthetic reproduction instructions and sanitized assertions, not raw captures. Before implementing E1/E4, verify one launch, continuation, and QA retry on the actual loop surface. Consider a private mapping keyed by the existing launch-comment ID as an alternative to publishing runtime IDs.

## Checked and OK

- The central P1–P5 interpretation is substantially correct: optional diagnostics can coexist with prose guidance, factual checks, issue authority, few agent-facing files, and secret protection. Keeping telemetry outside gate decisions preserves spec §2, lines 26–30.
- Keeping launch comments as receipts matches spec §5.7, lines 167–169. Avoiding synchronous exporter calls inside the guard respects its internal deadline and the fail-open outer-timeout risk in §5.6, lines 159–162, corroborated by S1 Q7.
- Claude Code documents opt-in telemetry, cost/token metrics, beta interaction and subagent tracing, content-redaction controls, outbound Bash trace context, and ignored inbound context for interactive sessions. These are documentation checks, not reproduced runtime results. [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage).
- Codex documents separate telemetry exporters, the listed principal event types, default prompt redaction, and tool-result output snippets. The older metrics issue is closed. [Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced), [issue #12913](https://github.com/openai/codex/issues/12913).
- The primary GenAI documents currently label the conventions and agent spans **Development** and define the named agent/tool operations. This supports the instability warning; I did not exhaustively audit every `gen_ai.*` attribute. [GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md), [agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md).
- Phoenix supports a local Python installation; Langfuse documents its multi-service self-hosting architecture; LangSmith self-hosting requires an Enterprise add-on. [Phoenix](https://github.com/Arize-ai/phoenix), [Langfuse](https://langfuse.com/self-hosting), [LangSmith](https://docs.langchain.com/langsmith/self-hosted).
- The cited hook-dashboard project exists and implements hook-event monitoring. Its compatibility with this kit’s guards was not established. [Project source](https://github.com/disler/claude-code-hooks-multi-agent-observability).
- Deferring integration follows the repository’s intake rules and the evidence available. E3 and a bounded E2 remain reasonable first candidates. No files were modified; no runtime experiments or tests were run.

## Next steps

- Correct the configuration, compatibility, and evidence claims.
- Add lifecycle definitions and privacy requirements to E1–E5; revise their dependencies and estimates.
- Retain option 1, then groom E3 and E2 with focused acceptance criteria.
- Before E4/E5, validate one local backend and the full interactive Claude → launcher → Codex path using synthetic data.
## Decisions

Made by Claude alone. The line numbers in the findings refer to the first version of the research file. The owner can change any decision.

| # | Decision | Reason / what changed |
|---|---|---|
| 1 | Taken | E2 and E4 now list their requirements: private folder outside repo and worktree, owner-only permissions, bounded retention, one file per attempt, partial capture on timeout, local destination, and "a diagnostics failure never changes the QA result". Effort is no longer "a few lines" |
| 2 | Taken | Checked in the Claude Code monitoring docs: a repo's `.claude/settings*.json` cannot set the OTel exporters, and `claude_code.hook` spans need `ENABLE_BETA_TRACING_DETAILED` and `BETA_TRACING_ENDPOINT`. Sections 2.2, 5 and E5 corrected; a new row for spec 5.9. Hook spans show that a hook blocked, not which check |
| 3 | Taken | "Every OTel backend accepts the data" removed. The backend table now compares signals, LLM views and set-up; superlatives removed; "not tested with real data" added; attribute mapping noted in 2.1 |
| 4 | Taken | Section 4 now separates operational indicators from quality evidence. Jev needs payload tokenization; effort level and #17 need defects found after close; #20 needs review decisions. The recommendation adds a record of escaped defects |
| 5 | Taken | E3 now reuses the Task 4 parser and defines its measures against 5.3, 5.4, 5.9 and 6.2 |
| 6 | Taken | Section 6 now grounds "replace: no" in P3 and 5.3–5.7, states the lock's real scope, calls the comments append-only by process rule only, and no longer says telemetry is always lossy |
| 7 | Partly taken | Section 1 separates bootstrap from v1; 2.5 says `--ephemeral` stops the rollout file but not the state and log databases (S2); option 2 no longer says "invisible". The default vendor metrics exporter was not checked, so the doc says vendor telemetry is out of scope instead of making a claim |
| 8 | Partly taken | 3.1 is now labelled author-observed for Codex 0.153.4, with reproduction steps; "every event had the email" corrected to "several log records". Raw captures are not kept, because they contain private data. 3.2 now names the real loop surface as the needed check. E1 gets the private-map variant (b) |
