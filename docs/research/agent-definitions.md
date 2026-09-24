# Agent definition files

Research on what can go into agent definition files for the PM, software engineer and QA roles.

- Research date: 2026-09-24
- Base: the Zoomcamp approach. Thin definitions in `.claude/agents/` point to the role files in `docs/team/`.
- Sources: official documentation only. Each fact has a link. **[Unverified]** marks a claim that the official documentation does not confirm.
- Status: research input. The owner decided on the proposals on 2026-09-24 (see section 8). O1 stays open.

Main sources:

- Claude Code subagents: https://code.claude.com/docs/en/sub-agents (CC-SUB)
- Claude Code memory (CLAUDE.md, AGENTS.md): https://code.claude.com/docs/en/memory (CC-MEM)
- Codex subagents and custom agents: https://developers.openai.com/codex/subagents (CX-SUB)
- Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md (CX-AGENTS)

---

## 1. Frontmatter fields (Claude Code)

Source: CC-SUB, section "Frontmatter reference". Only `name` and `description` are required. Claude Code silently ignores an unknown field, so field names must match exactly (camelCase).

| Field | What it does | Relevant for us |
|---|---|---|
| `name` | Unique ID. Hooks receive it as `agent_type`. No `:` allowed | Yes |
| `description` | Tells the main session when to delegate to this agent | Yes |
| `tools` | Allowlist of tools. If omitted, the agent inherits all tools | Yes (Q2) |
| `disallowedTools` | Denylist, removed from the inherited or listed tools. `Bash(git push *)` removes the whole Bash tool | Yes (Q2) |
| `model` | `sonnet`, `opus`, `haiku`, `fable`, a full model ID, or `inherit` | Input for O1 (Q6) |
| `effort` | Effort level for this agent: `low` to `max`. Overrides the session level | Input for O1 |
| `permissionMode` | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan` | Limited, see Q2 |
| `maxTurns` | Maximum agentic turns. Output is marked partial at the limit | Possible loop guard |
| `skills` | Preloads the full content of the listed skills at startup | See Q4 |
| `mcpServers` | MCP servers only for this agent | Later (Lovable, O4) |
| `hooks` | Hooks active only while this agent runs | Later (D3, the plan decides) |
| `memory` | Persistent memory directory: `user`, `project`, `local` | Not now |
| `background` | Always run in the background | Not now |
| `omitClaudeMd` | Start without the CLAUDE.md / AGENTS.md files | Do not use (Q3) |
| `isolation` | `worktree`: run in a temporary git worktree | Parallel mode, O6 |
| `color` | Display color | Cosmetic |
| `initialPrompt` | First user turn, only when the agent is the main session (`--agent`) | Not now |
| `experimental` | `cacheTtl`: prompt cache lifetime for this agent | Not now |

The markdown body after the frontmatter becomes the system prompt of the subagent. The subagent does not get the Claude Code system prompt (CC-SUB, "Write subagent files").

## 2. Tool limits: restrictions on tool interfaces

Source: CC-SUB, "Available tools".

- `tools: Read, Grep, Glob, Bash` gives an agent that "can't edit files, write files, or use any MCP tools".
- `disallowedTools: Write, Edit` removes only these tools.
- These fields restrict the tool interfaces of an agent. They are not a sandbox and not a guarantee of behavior. The documentation supports tool filtering, not a general shell sandbox (CC-SUB, "Available tools").
- If `Agent` is not in the `tools` list (or is in `disallowedTools`), the agent cannot start subagents of its own (CC-SUB, "Let subagents spawn their own subagents"). By default, a subagent can nest subagents up to three layers deep.

| Prose rule now | Frontmatter that restricts the tool interface | Gap that remains |
|---|---|---|
| QA: "Nothing in the code was changed" | `tools: Read, Grep, Glob, Bash` (no Edit, no Write) | Bash can still write files (`sed -i`, `>`) and run `git commit` |
| PM: "Do not write any code" | `tools: Read, Grep, Glob, Bash` | Same Bash gap. The PM needs Bash for `gh` |
| All roles: no second orchestrator (D7) | No `Agent` tool (PM, QA: leave it out of `tools`; engineer: `disallowedTools: Agent`) | Bash can start another agent as a subprocess, for example `claude -p` or `codex exec` |
| QA and PM: no MCP writes | `tools` allowlist without MCP tools | None found |

**Bash caveat.** Every role keeps Bash. With Bash, an agent can write files, commit, and start other agents as subprocesses (subprocess delegation). The tool limits above do not stop this.

Ways to close the Bash gap (not decided, see D3 and the plan):

- A `PreToolUse` hook in the agent frontmatter that checks each Bash command (CC-SUB, "Conditional rules with hooks").
- A `permissions.deny` rule such as `Bash(git push *)`. This applies to the whole session, including the main session (CC-SUB, "Available tools").

Limit of `permissionMode`: when the main session runs in `auto`, `acceptEdits` or `bypassPermissions`, Claude Code ignores the `permissionMode` of the subagent (CC-SUB, "Permission modes"). The owner often works in auto mode. Thus, `permissionMode: plan` is not a reliable read-only limit for us. Use `tools` for this.

## 3. Does a subagent load AGENTS.md / CLAUDE.md?

Yes, for Claude Code. A non-fork subagent loads "every level of the CLAUDE.md hierarchy the main conversation loads, including ... any `AGENTS.md` files loaded as project instructions" (CC-SUB, "What loads at startup").

- Our `CLAUDE.md` is `@AGENTS.md`. `@path` imports are expanded (CC-MEM, "Import additional files"). Thus, each subagent receives AGENTS.md.
- `omitClaudeMd: true` turns this off. Do not use it: AGENTS.md holds the commands and the test-command rule.
- The subagent does not see the conversation history. It gets its system prompt, the delegation message, the CLAUDE.md files, a git status snapshot, and the preloaded skills (CC-SUB, "What loads at startup").
- `docs/process.md` and `docs/team/*.md` are not loaded automatically. The agent must read them.

For Codex: Codex reads `AGENTS.md` "before doing any work" (CX-AGENTS). **[Unverified]** The Codex documentation does not say explicitly that a spawned subagent reads AGENTS.md. CX-SUB says only that custom agent files are "configuration layers for spawned sessions".

## 4. Thin pointer vs. full role text in the body

| | Thin pointer (now) | Full role text in the body |
|---|---|---|
| Single source | Yes. `docs/team/*.md` is the only copy | No. Two copies can drift apart |
| Codex compatibility | Yes. A Codex TOML file can point to the same `docs/team/` file | No. Codex does not read `.claude/agents/*.md` (see Q5) |
| Reliability | The agent must read the file. A prose instruction is not a guarantee | The body is the system prompt. It is always present |
| Tokens | One extra Read call per launch (role files are 20 to 40 lines) | No extra call. The same text is in the context |
| Readable for Zoomcamp readers | Yes (Article 5 pattern) | Yes |

Other facts:

- **[Unverified]** An `@path` import inside the agent body. CC-MEM documents `@` imports only for CLAUDE.md and AGENTS.md, not for agent files. Do not rely on it.
- `skills:` preloads the full skill text into the subagent (CC-SUB, "Preload skills into subagents"). This is reliable, but it costs tokens on each launch. Without the field, the subagent can still load a skill with the Skill tool when it needs it. **[Unverified]** The documentation does not say whether `skills:` accepts plugin skills such as `superpowers:test-driven-development`.
- The documentation recommends that rules which must reach a subagent go in the delegation prompt, because the main session keeps the full context (CC-SUB, "What loads at startup").

## 5. Codex agent definition files

Source: CX-SUB, "Custom agents".

- Location: `.codex/agents/` (project) or `~/.codex/agents/` (personal).
- Format: **TOML**, one agent per file. Not markdown.
- Required fields: `name`, `description`, `developer_instructions`.
- Optional: any `config.toml` key, for example `model`, `model_reasoning_effort`, `sandbox_mode` (for example `read-only`), `mcp_servers`, `skills.config`.
- Codex delegates to subagents when the user asks, or when AGENTS.md or skill instructions request it.
- Subagents inherit the sandbox policy of the parent. Live overrides of the parent (for example `--yolo`) also apply to the child, "even if the selected custom agent file sets different defaults".

Contradiction with Article 5: the article says that most assistants read `.agents/agents/<NAME>.md`. The Codex documentation names only `.codex/agents/*.toml`. **[Unverified]** for Codex: `.agents/agents/`.

Consequence: one role for both vendors needs two thin files (`.claude/agents/<role>.md` and `.codex/agents/<role>.toml`). Both point to `docs/team/<role>.md`.

## 6. A different model per role (input for O1)

Claude Code: yes. Each agent file can set `model` and `effort` (CC-SUB, "Choose a model"). The order of resolution is:

1. The `model` value in the Agent tool call
2. The `model` field in the agent file (`inherit` = model of the main session)
3. The environment variable `CLAUDE_CODE_SUBAGENT_MODEL`
4. The model of the main session

`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` makes Claude Code ignore the `model` field of all agent files.

Limit: `model` accepts only Claude models. A role on Codex (for example QA by a different vendor, see O1) cannot be a `.claude/agents/` file. It needs another start mechanism, for example `codex exec` through Bash (open question O5, not verified).

Codex: yes. `model` and `model_reasoning_effort` in the TOML file take precedence (CX-SUB, "Custom agents").

---

## 7. Token use at the handoffs (owner question)

Question: the orchestrator gives QA only the issue number, and it reads full issue comments. How do other setups do this?

What the sources show:

- The official Claude Code `code-reviewer` example tells the reviewer to "Run git diff to see recent changes" and to "Focus on modified files" (CC-SUB, "Code reviewer"). The review scope is the diff, not the whole repo.
- The superpowers skill `requesting-code-review` (installed plugin, not official vendor documentation) gives the reviewer a git range (`BASE_SHA`, `HEAD_SHA`), a short description, and a pointer to the requirements. The rule is "precisely crafted context ... never your session's history".
- Codex: "subagent workflows consume more tokens than comparable single-agent runs". Subagents should return summaries, not raw output (CX-SUB).
- Claude Code: subagent results return to the main conversation. Many detailed results "can consume significant context" (CC-SUB, "Run parallel research").
- AGENTS.md loads into every subagent (Q3). Its size is paid on each launch.

Observations for our process (accepted by the owner on 2026-09-24, applied to `docs/team/`):

1. **QA scope.** Now, QA gets only the issue number and must find the changes itself. A git range is a fact, not an implementation claim. Proposal: the `## Engineer: DONE` comment lists the commit range. The orchestrator gives QA the issue number and this range. QA still ignores what the engineer says the code does.
2. **Reading results.** `gh issue view <n> --comments` loads the full thread, and the thread grows with each FAIL loop. `gh issue view` supports `--json` and `--jq` (checked locally, gh 2.98.0; manual: https://cli.github.com/manual/gh_issue_view). The orchestrator filters the comments by the exact role marker, takes the newest match, and reads only its first line and URL. See `docs/team/orchestrator.md` for the command. (An earlier version of this item used `.comments[-1]`, the newest comment of any author. That was wrong, see Codex finding M6.)
3. **Subagent final report.** The final message of each subagent enters the orchestrator context. Proposal: each role ends with a short final message (the marker line and the comment link), because the full result is on the issue.
4. **The markers themselves** cost almost nothing: one line per comment. The cost is in how much the orchestrator reads (item 2).

---

## 8. Recommendation for our three agent files

Keep the thin pointer (Q4). Add tool limits that restrict the tool interfaces (Q2). Do not set `model` or `effort` until O1 is decided.

Decision (owner, 2026-09-24): accepted and applied to `.claude/agents/`. The proposals in section 7 are also accepted and applied to `docs/team/`.

| File | Frontmatter change | Body |
|---|---|---|
| `pm.md` | `tools: Read, Grep, Glob, Bash` | Pointer to `docs/team/pm.md` and `docs/process.md`. "Read your role file before any other action." |
| `software-engineer.md` | `disallowedTools: Agent` | Pointer to `docs/team/software-engineer.md` and `docs/process.md` |
| `qa-engineer.md` | `tools: Read, Grep, Glob, Bash` | Pointer to `docs/team/qa-engineer.md` and `docs/process.md` |

Notes:

- No `orchestrator` agent file. The orchestrator is the main session. `claude --agent orchestrator` would replace the Claude Code system prompt entirely (CC-SUB, "Invoke subagents explicitly"). The main session already gets AGENTS.md, which points to `docs/process.md` and `docs/team/orchestrator.md`.
- The Bash gap (Q2) stays open until the plan decides on hooks (D3).
- `.codex/agents/*.toml` files only when O1 gives a role to Codex.
- Do not use `permissionMode` as a limit (Q2) or `omitClaudeMd` (Q3).
