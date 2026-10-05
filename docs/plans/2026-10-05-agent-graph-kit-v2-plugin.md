# Agent graph kit v2 (plugin): plan

Each task below becomes one GitHub issue in `docs/task-template.md` format, as a sub-issue of the stage issue. The PM grooms each issue before work starts; the criteria here are the starting point. Tasks 2 to 6 depend on what the probe (task 1) finds, so the PM of each of them reads the probe note first and may sharpen its criteria. This plan is archived once the stage is set up.

**Goal:** A user installs the kit as a Claude Code plugin in a mostly fresh project, runs one setup step, and the loop works.

**Spec:** `docs/specs/2026-10-05-agent-graph-kit-v2-plugin.md`

## Global constraints

- The decisions D1 to D9 of the spec hold. Adoption of existing projects is out of scope (D1).
- This repo keeps its v1 layout and keeps working during the stage (D9). No task breaks the v1 guard, the role files or the loop.
- No second hand-kept copy of a file. Where the plugin needs a file that the v1 layout already has (the hook scripts, the agents, the skills), the plugin gets it from one source: by a build script or by a test that fails when the two differ. The PM of task 2 picks one.
- Python is stdlib only, run with `uv run --script`. Test command: `uv run --with pytest pytest`. No network in tests: `gh` is faked as in the existing hook tests.
- Every `gh issue list` call in code passes `--limit`; every REST list call pages (`--paginate`).
- A change that edits `.claude/hooks/`, the project settings files in `.claude/`, or `QA_SANDBOX` in `scripts/qa-codex` needs the owner first (`needs-owner`, see "Escalation" in `docs/process.md`).
- A scratch or trial project holds only synthetic data. No secrets, no real project names.
- Each issue changes the instruction files that its change makes false, in the same commit.

## Stage issue

| Stage issue | Purpose | Blocked by |
|---|---|---|
| Stage 7: The kit as a Claude Code plugin (v2) | A user installs the kit as a plugin in a mostly fresh project, runs one setup step, and the loop works | Stage 6 (the finished stage) |

The stage issue has the label `stage` and the sections `## Purpose`, `## Background`, `## Exit check`.

Order: 1, 2, 3, 4, 5, 6, each blocked by the one before. Tasks 3 and 4 could run in parallel after task 2, but both edit the same setup files, so they run one after the other.

---

### Task 1: Probe: a plugin delivers the hooks, agents and `bin/`

Lane: default
Permissions: create and delete a scratch GitHub repo with `gh repo create` and `gh repo delete`; install a plugin from a local path in a scratch Claude Code session

**Goal:** There is evidence whether the kit's hooks, agents and launcher can be delivered by a Claude Code plugin, so the later tasks build on facts.

**Acceptance criteria**
- [ ] A note `docs/research/spike-plugin-delivery.md` states the Claude Code version and answers each question of section 4 of the spec, with the exact command or file and its output (shortened, no secrets): (1) the PreToolUse guard hook fires from a plugin and denies a call the v1 guard denies; (2) the PermissionDenied and SubagentStop hooks fire from a plugin; (3) `${CLAUDE_PLUGIN_ROOT}` resolves in the hook command; (4) the plugin `bin/` is on the PATH of the Bash tool, in the main session and inside a subagent; (5) a plugin agent reads the role files from the project's copied `docs/` at the same paths; (6) which front matter keys of an agent Claude Code ignores for a plugin agent
- [ ] The note ends with "Consequences": for each question, "works", "does not work" or "not observed" (with the reason), and what that means for D3, D4 and D6 of the spec. When answer 1, 2 or 5 is "does not work", the note says so in its first line
- [ ] The note says whether the thin wrapper of D6 works, with the test that shows it
- [ ] The scratch repo and the scratch plugin are removed again; the note shows the final state
- [ ] The test command `uv run --with pytest pytest` passes

**Out of scope**
- Building the plugin (task 2)
- Any change to this repo's hooks, settings or role files

**Constraints**
- Commit only the note. The scratch plugin and project live outside the repo (in the session scratch directory) and are throwaway
- Use `claude plugin validate` where it applies and quote its output

### Task 2: Plugin skeleton

Lane: default
Permissions: none

**Goal:** The kit has a plugin folder that passes `claude plugin validate` and carries the hooks, agents and skills of D3, while this repo keeps working as before.

**Acceptance criteria**
- [ ] A plugin folder with `.claude-plugin/plugin.json`, `hooks/hooks.json` (the three hooks, scripts run from `${CLAUDE_PLUGIN_ROOT}`), the five agents and the skills `stage-start` and `codex-review`
- [ ] The plugin gets the hook scripts, agents and skills from one source with this repo's v1 files (see the global constraint); a test fails when they differ
- [ ] A test runs `claude plugin validate` in strict mode on the plugin folder and passes. When the `claude` command is not available, the test is skipped with a clear message and never reported as passed
- [ ] The v1 guard tests and all other tests still pass; `.claude/settings.json` and `.claude/hooks/` of this repo are unchanged
- [ ] The result of the probe is applied: where the note says "does not work", the issue stops and posts `## Engineer: BLOCKED` with the finding instead of working around it
- [ ] The test command `uv run --with pytest pytest` passes

**Out of scope**
- The setup skill (task 3), the drift check (task 4), the install README (task 5)
- Switching this repo to the plugin (D9)

**Constraints**
- Blocked by task 1

### Task 3: Setup skill

Lane: default
Permissions: none

**Goal:** One setup step turns a mostly fresh project into a project the loop can run in, and reports what the owner still has to do by hand.

**Acceptance criteria**
- [ ] A plugin skill `setup` (name chosen by the PM) that, in a project root: copies `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/`, the three `qa-codex` files (as D6, or the wrapper when the note of task 1 says it works and the owner has said so), and an `AGENTS.md` template with the project name and the test command filled in from the owner's answers
- [ ] The copy logic is a script with tests on a temporary directory: a fresh directory gets every file; an existing target file is never overwritten and is reported with its difference; the script never writes outside the project root
- [ ] The script records a fingerprint per copied file in one lock file in the project, in the form that task 4 reads
- [ ] The script adds the permission block (allow rules, the deny rule for `settings.json`) to the project's `.claude/settings.json`, or, when that file exists, prints the exact lines to merge and does not edit it. A test covers both cases
- [ ] The script checks the manual entries and reports each one that is missing with its exact fix: `gh` login, `uv`, Codex login, the Codex trust entry, and the three Auto mode entries (text from the README). It cannot read the user-level Auto mode entries, so it prints them as "check by hand" and never as passed
- [ ] The skill states that the Lovable lane is a separate, optional step (D8)
- [ ] The test command `uv run --with pytest pytest` passes

**Out of scope**
- The drift check (task 4)
- The Lovable walk-through (task 5 documents it)

**Constraints**
- Blocked by task 2. Python stdlib only

### Task 4: Drift check

Lane: default
Permissions: none

**Goal:** The owner can see, per copied file, whether it is unchanged, changed in this project, or newer in the plugin, and nothing is overwritten.

**Acceptance criteria**
- [ ] A plugin skill or command `drift` (name chosen by the PM) runs a script that reads the lock file of task 3 and reports one line per copied file: `unchanged`, `changed in this project`, `newer in the plugin`, or `changed in both`
- [ ] A test on a temporary directory covers each of the four states, a file that was deleted from the project, and a missing lock file (reported as "not set up", never as unchanged)
- [ ] The script writes no file in the project
- [ ] The test command `uv run --with pytest pytest` passes

**Out of scope**
- A merge or update step: the owner decides what to do with each answer

**Constraints**
- Blocked by task 3

### Task 5: Install documentation for v2

Lane: default
Permissions: none

**Goal:** A short, exact README section replaces the ten manual steps of v1: install the plugin, run the setup, do the remaining manual steps.

**Acceptance criteria**
- [ ] `README.md` has a v2 section that gives the install command for the plugin, the setup command, and the remaining manual steps in order, each with its exact command or text (accounts and logins, Codex trust entry, the three Auto mode entries)
- [ ] The v1 section stays and is marked as the manual route
- [ ] The Lovable lane is a separate optional section: create the Lovable project, add `Lovable project: <id>` to `AGENTS.md`, install the `lovable` plugin
- [ ] Every command and path in the README exists: the doc tests (`tests/test_doc_paths.py`) pass
- [ ] The living spec `docs/specs/agent-graph-kit.md` names the plugin parts where it states how the kit is installed
- [ ] The test command `uv run --with pytest pytest` passes

**Out of scope**
- Adoption of existing projects (D1)

**Constraints**
- Blocked by task 4

### Task 6: Trial in a fresh throwaway project

Lane: default
Permissions: create and delete a throwaway GitHub repo with `gh repo create` and `gh repo delete`; Codex QA run (spends Codex quota); the owner's user-level Auto mode entries for the trial project

**Goal:** The plugin has run one task through the loop in a fresh project, and the findings are on record.

**Acceptance criteria**
- [ ] A report `docs/reviews/plugin-trial.md` lists each step as done in a fresh throwaway project that holds only synthetic data: create the repo, install the plugin, run the setup, do the manual steps from the README, file one small task issue, run PM, engineer and QA, close the issue
- [ ] For each step the report says "worked", "needed a change" or "failed", with the command and its output (shortened, no secrets) and the README line that was wrong or missing
- [ ] Each finding that asks for a change becomes a follow-up issue in `docs/task-template.md` format with the label `later` and the line `Source:` pointing at the report
- [ ] The throwaway repo is deleted after the trial; the report shows the final state
- [ ] The test command `uv run --with pytest pytest` passes

**Out of scope**
- Fixing the findings in this issue

**Constraints**
- Blocked by task 5. The owner is present for the manual steps (user-level entries, logins)

---

## Self-review

- Spec coverage: D1 (out of scope everywhere), D2 and D7 (task 3), D3 (task 2), D4 and D5 (tasks 3 and 4), D6 (tasks 1 and 3), D8 (tasks 3 and 5), D9 (global constraint, task 2). Section 4 questions: task 1. Section 6 tests: tasks 2 to 4 and 6.
- No placeholders. The names of the setup and drift skills are left to the PM on purpose; the spec does not fix them.
