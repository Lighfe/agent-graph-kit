# Codex review: bootstrap setup

- Date: 2026-09-24
- Reviewer: Codex (read-only, through the codex-rescue subagent)
- Scope: all uncommitted bootstrap files, except `docs/references/local/`
- Status: findings only. No finding is applied yet.

---

The bootstrap has a clear role split, a compact issue template, and explicit boundaries around the accepted decisions. Its main weaknesses are in recovery and handoff state: an old comment can satisfy a new step, partially completed work can spill into another issue, and PM–engineer retries have no termination rule. Several instructions also conflict with the prose-only starting point or with each other. The research is largely supported by current official documentation, but some recommendations overstate enforcement or discard information the orchestrator needs. This review was strictly read-only; no `gh` commands or tests were run, and `docs/references/local/` was not read.

## Findings

### High

**H1. Results are not bound to the current attempt or verified revision.**

**Files:** `docs/team/orchestrator.md:31–43,69`; `docs/team/software-engineer.md:15–20`; `docs/team/qa-engineer.md:27–35`.

The orchestrator reads "the newest comment of the role," but no comment must identify its launch, implementation revision, or acceptance-criteria version. Closing additionally requires that "no engineer change came after" PASS, which issue comments alone cannot establish.

**Failure scenario:** An issue already has an Engineer DONE. A subsequent engineer attempt fails before posting; the old DONE still exists, so the missing-result rule does not trigger. Similarly, after a restart, an old QA PASS can appear valid even though code or criteria changed.

**Suggested fix:** Give each attempt an identifier recorded on the issue and require matching result comments. Include implementation and verified commit IDs plus a reference to the criteria reviewed. Before closing, inspect repository state to establish that it still matches QA's evidence; do not infer this solely from comment order.

**H2. Escalation can carry unfinished changes into the next issue.**

**Files:** `docs/team/software-engineer.md:11,17–20`; `docs/team/orchestrator.md:59–65`.

The engineer must stop immediately on a blocked criterion; the committed-work requirement applies to DONE. The orchestrator then removes `ready` and continues with another issue, without a workspace handoff rule.

**Failure scenario:** The engineer implements one criterion, leaves edits uncommitted, and discovers that another criterion is impossible. PM escalates. The next issue's engineer starts in the same checkout and can accidentally commit or test the previous issue's unfinished changes.

**Suggested fix:** Define a sequential-workspace checkpoint before switching issues: record partial changes and commits, inspect the working tree, and escalate if it cannot safely be handed over. Do not silently discard or include another task's work. This can be specified without deciding O6 or introducing parallel worktrees.

### Medium

**M1. The FAIL-counter reset cannot be reconstructed from the prescribed comment read.**

**File:** `docs/team/orchestrator.md:31,54–57,61–65`.

The counter resets when the owner "added the label `ready` again," but that boundary is a label event, not a required comment marker. The prescribed issue read does not establish when that event occurred; the GitHub CLI documentation (https://cli.github.com/manual/gh_issue_view) distinguishes comments and current labels and does not expose label-event history through the listed JSON fields.

**Failure scenario:** After three FAILs, the owner responds and re-adds `ready`. A restarted orchestrator cannot reliably determine which FAILs belong to the new attempt and may immediately escalate again or incorrectly reset the count.

**Suggested fix:** Persist an explicit resume/attempt boundary in comments, or prescribe reading label timeline events. Count FAILs within that identifiable attempt and handle counts of three or more.

**M2. The PM–engineer blocked path has no termination condition.**

**Files:** `docs/process.md:33,47`; `docs/team/orchestrator.md:49–55`; `docs/team/pm.md:21`.

Only QA FAILs are counted. Engineer BLOCKED sends the issue to PM, and PM GROOMED sends it directly back to the engineer.

**Failure scenario:** PM repeatedly rephrases an impossible criterion and considers it resolved; each fresh engineer identifies the same blocker. QA never runs, so the three-FAIL limit never applies.

**Suggested fix:** Ask the owner to define a bounded retry or repeated-blocker rule, then record its counter on the issue. The review should not choose the escalation threshold on the owner's behalf.

**M3. The escalation instructions disagree about whether the loop stops.**

**Files:** `docs/process.md:47`; `docs/team/orchestrator.md:59–65,77–81`.

The process says "stop and ask the owner" after three FAILs, while the orchestrator says to remove `ready` and "continue with the next issue." Its definition of done also requires PM, engineer, and QA to have performed their steps even when an issue is escalated before implementation.

**Failure scenario:** One orchestrator stops the entire run; another continues. An initial PM NEEDS OWNER cannot satisfy the literal definition of done unless engineer and QA are launched unnecessarily.

**Suggested fix:** Clarify whether "stop" means the issue or the whole loop, using the owner's intended policy. Give escalated issues a separate completion condition requiring only the steps actually reached.

**M4. QA's rules do not support the documented prose-only bootstrap.**

**Files:** `AGENTS.md:21`; `docs/team/qa-engineer.md:6–7,29–35`; `docs/team/software-engineer.md:8,16`.

AGENTS.md explicitly says there is no test command yet. QA nevertheless must run it, include its result, and treat only acceptance criteria and "running code" as evidence. Unlike the engineer's completion criteria, QA's own rules contain no no-suite exception.

**Failure scenario:** A documentation issue is correctly implemented, but QA cannot follow its instructions literally: there is no running code or test command. It either invents validation, rejects valid prose work, or silently overrides its role.

**Suggested fix:** Explicitly permit criterion-specific document inspection and manual evidence for prose tasks. Require "not run—no test suite" where applicable and distinguish that from a test PASS.

**M5. Handoffs repeatedly load growing threads and leave QA to rediscover the change scope.**

**Files:** `docs/team/orchestrator.md:13–19,31`; `docs/team/software-engineer.md:17–18`; `docs/research/agent-definitions.md:139–144`.

Every fresh step is followed by a full comment-thread read. QA receives only the issue number, while the engineer commits its work without recording a required commit range. The research correctly identifies these costs, but its proposals are not part of the operative process.

**Failure scenario:** Each retry adds more reports that later reads load again. QA must search history to identify committed changes; a plain working-tree diff may be empty. Detailed subagent final messages can duplicate the issue evidence in the parent context.

**Suggested fix:** Record a factual base/head range and pass it with the issue number. Require short final returns containing the marker and comment link. Read bounded routing metadata first, then the relevant evidence and criteria when needed.

**M6. The proposed optimized comment query breaks the role-selection contract.**

**Files:** `docs/research/agent-definitions.md:142`; `docs/team/orchestrator.md:33–43,57`.

The example selects `.comments[-1]`, meaning the latest comment overall, rather than the latest matching role result. Returning only its first line also drops identity and timing information.

**Failure scenario:** An owner adds a clarification after QA PASS. The optimized read returns the clarification and treats QA's result as missing. It also cannot supply the attempt boundary needed for counting FAILs.

**Suggested fix:** Filter by exact role marker and current attempt, retaining comment ID/link and timestamp. Fetch the selected result's full evidence separately.

**M7. Public-output rules protect commits but omit issue evidence.**

**Files:** `AGENTS.md:51–54`; `docs/team/orchestrator.md:61`; `docs/team/qa-engineer.md:20–24,30–32`.

The public-repo rules prohibit committing secrets and third-party articles. Agents are also instructed to publish blockers, observations, and test results to issues, with no corresponding instruction to sanitize that evidence.

**Failure scenario:** A failure report includes a credential-bearing URL, real account details, or sensitive command output. The information is published in a public issue despite never entering a commit; `.gitignore` cannot protect that path.

**Suggested fix:** Extend the existing public-repo rule to issue bodies, comments, and reports. Require redacted evidence and synthetic examples. No actual leaked credential was found in the reviewed files.

### Low

**L1. Research overstates what tool restrictions enforce.**

**File:** `docs/research/agent-definitions.md:50–66,150–161`.

The research says tool limits turn prose rules "into facts" and lists "None found" as the gap for preventing a second orchestrator by removing `Agent`. It correctly acknowledges elsewhere that Bash still permits writes.

**Failure scenario:** A future configuration is treated as enforcing read-only behavior or preventing all delegation, although Bash can write files or launch another agent CLI when available.

**Suggested fix:** Describe these as restrictions on specific tool interfaces, not complete behavioral guarantees. Extend the Bash caveat to subprocess delegation. This is low severity because the proposed limits are not applied and the file already acknowledges part of the limitation. The Claude Code tool documentation (https://code.claude.com/docs/en/sub-agents#available-tools) supports tool filtering, not a general shell sandbox.

**L2. QA has two incompatible first-line requirements.**

**File:** `docs/team/qa-engineer.md:13,29`.

Line 13 requires exactly `## QA: PASS` or `## QA: FAIL`; the definition of done says the comment "starts with PASS or FAIL."

**Failure scenario:** QA follows the shorter completion wording and posts `PASS`, which the orchestrator rejects as malformed.

**Suggested fix:** Repeat the exact marker strings in the definition of done, or refer directly to the canonical format above.

**L3. The README does not clearly distinguish current worker support from the unresolved O1/O5 design.**

**Files:** `README.md:5–13`; `docs/team/orchestrator.md:15–19`; `docs/research/agent-definitions.md:121,162`.

The README presents Codex CLI as an existing worker alongside Claude subagents and marks only Lovable as planned. The actual launch table contains only Claude subagents, while the research explicitly leaves Codex assignment and invocation unresolved.

**Failure scenario:** A contributor treats Codex integration as an established part of the bootstrap and implements around an assumed launch mechanism.

**Suggested fix:** Label the introductory worker list as the target architecture and state the current bootstrap mapping separately, with O1/O5 still open. This is low severity because "Bootstrap. Not usable yet" already signals incompleteness; it is ambiguous wording, not evidence that those questions were actually decided.

## Checked and OK

- Read all requested files and all three `.claude/agents/*.md` definitions; their names match the orchestrator's launch table and their role-file pointers resolve.
- `CLAUDE.md` contains the supported `@AGENTS.md` import. Claude Code documentation (https://code.claude.com/docs/en/memory#remove-an-earlier-agents-md-workaround) explicitly permits retaining this arrangement.
- `.claude/skills` is a valid relative symlink to `../.agents/skills`; the target exists and contains `.gitkeep`.
- `.gitignore` excludes local reference material, `.env` variants, and local Claude settings; `.env.example` is intentionally allowed. These matches were checked without reading excluded content.
- LICENSE contains the complete MIT notice and disclaimer, with year and holder filled in.
- The four template sections and Lane field agree with PM and orchestrator validation requirements.
- D7's excluded skills and D8's folder conventions are consistently preserved. Reviewer and parallel-mode definitions are explicitly deferred.
- The absence of hooks and CI gates is explicitly consistent with D10's bootstrap stage.
- Core research claims about Claude frontmatter, model precedence, permission inheritance, fresh custom-agent context, and skill preloading are supported by the official subagent documentation (https://code.claude.com/docs/en/sub-agents).
- Core Codex claims about TOML agent files, required fields, configuration overrides, and inherited runtime permissions are supported by official OpenAI documentation (https://learn.chatgpt.com/docs/agent-configuration/subagents).
- The installed `requesting-code-review` skill supports the research's description of commit-range handoffs.
- No test suite was claimed to pass; AGENTS.md explicitly records that none exists yet.
