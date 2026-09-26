# Owner decisions after spikes S1–S3

Date: 2026-09-26
Sources: `spike-claude-code-hooks.md` (S1), `spike-codex-cli.md` (S2), `spike-lovable-mcp.md` (S3), each "Consequences for the plan".

## Codex trust entry (#6, #10)

- **Decision:** Accept the trust entry in `$HOME/.codex/config.toml`.
- **Reason:** Each Codex run with a writable sandbox writes `trust_level = "trusted"` for a repo that has no entry yet. No flag stops this. QA runs are not affected, because `--ignore-user-config` ignores the trust list.
- **Actions:**
  - Add the entry as a set-up step (README #10 or the plugin init command). Codex then writes nothing during the loop.
  - One-off now: add the entry for paint-math.
  - Remove "do not touch `~/.codex/config.toml`" from future issue constraints, or change it to allow this entry.
- **Remaining risk:** Manual `codex` sessions in a trusted repo load the repo's `.codex/config.toml` and `.codex/hooks.json`. Treat a new `.codex/` folder in a diff as a review item.

## QA sandbox (#6)

- **Decision:** Use the localhost-only profile (`--enable network_proxy`, permissions profile `qa`).
- **Reason:** QA tests the checked-out code and needs no GitHub. Codex runs outside the Claude Code hooks, so the sandbox is its only limit. With full network, Codex has the owner's `gh` login.
- **Remaining risk:** `network_proxy` is experimental. Check it after each Codex update.

## Frontend dependencies before QA (#6, #9, #10)

- **Decision:** `qa-codex` runs a fixed pre-step before `codex exec`, outside the sandbox: `npm ci`, then the Playwright browser install.
- **Rules:**
  - If the pre-step fails, the status is `unavailable`.
  - If QA needs a tool that is not in the lockfile or the set-up, the result is QA FAIL back to the engineer (undeclared dependency). No install escalation.
- **Reason:** `codex exec` cannot pause for an install. The steps are fixed and need no LLM decision.

## Working tree changes during QA (#6)

- **Decision:** `qa-codex` runs Codex in a temporary `git worktree` at the commit under test, and deletes the worktree after the run.
- **Reason:** Codex can write files in the working tree in every sandbox, also with no network. In the main tree this makes G1 deny the next launch, and a PASS can apply to code that is not in `HEAD`.
- **Open point:** S3 (#6) says `git diff --submodule=diff` needs no network only in the clone where the engineer fetched the `frontend/` commits. A new worktree may not have the submodule objects. Check how the worktree gets them. The fetch must happen in the pre-step, outside the sandbox. The Lovable repo is public (see "paint-math set-up"), so the fetch needs no credentials.

## Reasoning effort and model (#6, #8)

- **Decision:** `qa-codex` and `codex-review` set the model and the reasoning effort explicitly. Start with `medium` for all runs, and record the results.
- **Reason:** `--ignore-user-config` also removes the user's model and effort. The built-in default effort is `none`.
- **Later:**
  - Add a `qa-depth: low | medium | high` field that the PM sets when it writes the issue, or a fixed rule based on the changed paths. The engineer never sets the QA depth.
  - Change the model to GPT-6 Sol when a stable Codex CLI release lists it (in the CLI version `0.153.4` used in S2, it is not available).

## Guard hook timeout (#5, #7)

- **Decision:** Accept that a guard killed at its timeout lets the call through (fail-open).
- **Actions:**
  - The guard has one overall deadline (about 60 s) for all its work, including the wait for the file lock. At the deadline, it denies.
  - The settings `timeout` (#7) is higher than the deadline (about 120 s).
  - Change spec 5.6 to: "A crash must never let the call through, except when Claude Code kills the hook at its timeout."
- **Remaining risk:** Only a hung machine causes a fail-open.

## Hook activation and settings protection (#7)

- **Decision:** Use the tested activation procedure, and protect the settings files.
- **Activation:**
  1. Before Task 7, put `{"disableAllHooks": true}` into `.claude/settings.local.json` (not committed).
  2. Run and close Task 7.
  3. The owner deletes the file. The hooks apply from the next tool call.
- **Protection:**
  - `permissions.deny` rules for `Edit` and `Write` on `.claude/settings*.json`.
  - The guard denies `Bash` commands that write to `.claude/settings*.json`.
- **Reason:** Each agent that can write files can put `disableAllHooks` into the local settings file. The change applies at the next tool call, and the guard does not see `Edit` or `Write` calls.
- **Review:** `codex-review` (#8) reviews the Task 7 implementation of the protection. Focus: ways around the `Bash` check, for example `cd .claude` first, variables, `python -c`, `tee`, `cp` or `mv`.
- **Not done:** No warning when `disableAllHooks` is still present. Remaining risk: if the owner forgets step 3, all guards stay off, and nothing shows it.

## Allow rules for the guarded calls (#7)

- **Decision:** Add two allow rules in the project settings:
  - `Bash(scripts/qa-codex ROLE=qa ISSUE=*)`
  - `Bash(gh issue close *)`
- **Reason:** The guard posts the launch comment before the permission check. If a prompt or a missing allow rule then stops the call, the issue stays pending and the orchestrator escalates without a real problem.
- **Effect:** Claude Code no longer asks the owner before these two calls. The guard runs first, and its deny still stops the call.
- **Notes:**
  - Project allow rules apply only after the folder is trusted.
  - Add to the `codex-review` of the settings protection: how the rules match compound commands, for example `… ISSUE=1 && rm …`.

## `SendMessage` continuation (#5, #7)

- **Decision:** Allow `SendMessage` to continue a role agent, and guard it like a launch. No deny rule, no new launch after a QA FAIL.
- **Reason:** The same engineer gets the QA feedback with its own context. A `SendMessage` call has no `Agent` call, so without a guard it has no launch comment and no checks.
- **Actions:**
  - Add `SendMessage` to the guard matcher (`Agent|Bash|SendMessage`).
  - The orchestrator writes the same `ROLE=… ISSUE=…` line into the message as in a launch prompt.
  - The guard reads the line, runs the checks and posts a "continued, round N" comment. A message without the line is denied.
  - Prose rule for the orchestrator: continue a role only with this line.
- **Check in the spec:** If the return limit counts launch comments, count "continued" comments too.
- **Cost note:** Each follow-up message renders the agent's frontmatter skills again and fires SubagentStart hooks again.
- **Surface:** The owner runs the loop in the Claude Code VS Code extension. The Claude Desktop Code tab blocks `SendMessage`; the terminal CLI has it. For the VS Code extension it is not known. The acceptance test (step 3) checks it. If the extension blocks it, run the loop with `claude` in the VS Code integrated terminal.

## Acceptance test after hook activation (#7)

- **Decision:** The owner runs this test in an interactive session in the VS Code extension (the surface of the loop), on a throwaway issue.
- **When:** After Task 7 is closed and the owner has deleted `disableAllHooks`. Before the next real issue gets the `ready` label. If a step fails, the loop does not start.
- **Who:** The owner types the prompts and checks each result. Claude Code only makes the calls. An agent does not test its own gates.
- **Task 7 deliverable:** Write the checklist with ready-to-paste prompts into `docs/checks/hook-activation.md`.
- **Steps:**
  1. Start a session in the repo and accept the trust dialog. Run `/hooks` and confirm that the guard is listed.
  2. Launch a subagent without a `ROLE=… ISSUE=…` line. The guard denies it.
  3. Launch a subagent with a correct line, let it finish, then continue it with `SendMessage`. Without the line: denied. With the line: runs, and the issue gets a "continued" comment. Record the field names in the hook input (expected: `to`, `message`, `summary`) and whether `SendMessage` is available in the extension.
  4. Ask the agent to write `disableAllHooks` into `.claude/settings.local.json`, first with `Edit`, then with a `Bash` `echo`. Both are denied.
  5. Run one guarded `qa-codex` call. No permission prompt appears.
  6. The owner puts `{"disableAllHooks": true}` into the local file by hand. Check whether user-level hooks also stop. Then delete the file.

## paint-math set-up (#11)

- **Decision:** The owner creates the Lovable project, connects it to GitHub and makes the Lovable repo public.
- **Reason:** No MCP tool can connect a Lovable project to GitHub (S3). A public repo needs no read access for the loop machine, the engineer fetch or the Codex QA diff.
- **Actions for the agent in #11:**
  - Tell the owner the exact point in the set-up where the Lovable project must exist, and stop until the owner confirms it.
  - Give the owner an initial Lovable prompt to create the project.
  - Give the owner the manual steps from S3: connect the workspace to GitHub (one time), then Project settings → Git → GitHub → Connect, then make the new repo public, then send the repo URL.
- **Notes:**
  - The submodule tracks the branch that Lovable syncs (the default branch, `main`).
  - Add the Codex trust entry for paint-math (see "Codex trust entry").

## `ready` label (process)

- **Decision:** The orchestrator adds the `ready` label only when the owner explicitly asks for it, or when the case is not ambiguous.
- **Reason:** In the S1–S3 loop, the orchestrator added the label to #3 based on its own reading of the owner's goal.

## Still open

- Nothing from S1–S3.