# Agent graph kit v2: the Claude Code plugin

- Date: 2026-10-05
- Status: approved by the owner on 2026-10-05.
- Input: the plugin manifest reference of Claude Code (hooks, agents, skills, `bin/`, `userConfig`, `settings.json` limits) and `README.md` section "Set up the kit in a project" (the manual v1 set-up).

---

## 1. Purpose

v1 is done: the kit works in this repo, and the owner carried it by hand to a second project. v2 makes the kit a Claude Code plugin. A user installs the plugin in a mostly fresh project, runs one setup step, and the loop works. The owner then uses the plugin in other projects and learns from that use.

## 2. Decisions

| # | Decision |
|---|---|
| D1 | v2 targets a mostly fresh project. Adopting the kit in an existing project is not part of v2. It stays parked (#15) as a possible later set-up skill |
| D2 | Manual steps are fine in a small number: accounts and logins, the Auto mode entries, the Codex trust entry. Each one is written down exactly and reproducibly. The setup step checks them and reports what is missing. Automate only where it helps |
| D3 | The plugin carries: the guard hooks, the denied-launch and outage marker hooks, the agents, and the skills (`stage-start`, `codex-review`, setup). Hooks run from the plugin, so a task cannot edit them by accident |
| D4 | The project gets a copy, made once by the setup step: `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/`, and an `AGENTS.md` template filled in with the project facts. Agents read them at the same paths as in v1. The owner may tune the copy per project |
| D5 | The setup step records a fingerprint of each copied file. A drift check compares three things per file: the fingerprint, the project file and the plugin file. It reports one of: unchanged, changed in this project, newer in the plugin. It never overwrites a file |
| D6 | `qa-codex` starts as a copy in the project (`scripts/qa-codex`, `scripts/codex_exec.py`, `scripts/qa-result.schema.json`). The guard form, the allow rule and Auto mode entry 1 stay as in v1. A probe tests a thin wrapper: a project file `scripts/qa-codex` that only starts the real launcher from the plugin `bin/`. If the probe passes, a later task switches to the wrapper. If it fails, the copy stays |
| D7 | The permission block (allow rules, the deny rule for `settings.json`) cannot ship in a plugin. The setup step adds it to the project settings, or tells the owner how |
| D8 | The Lovable frontend lane is optional and a second step. A fresh project has no Lovable project id. A skill or README section walks the owner through creating the Lovable project and then writes the id into `AGENTS.md`. The base kit works without it |
| D9 | `claude plugin validate` runs as a test. This repo keeps working as a kit repo during the work, with the v1 layout, until the owner decides to switch it to the plugin |

## 3. Plugin parts and where each lives

| Part | Where | Why |
|---|---|---|
| Guard hooks, denied-launch hook, outage-stop hook | Plugin (`hooks/hooks.json`, scripts under `${CLAUDE_PLUGIN_ROOT}`) | They enforce the rules |
| Agents, skills | Plugin | They are the kit's tools |
| `docs/process.md`, `docs/team/`, `docs/task-template.md`, `docs/checks/` | Copied once into the project | The owner may tune them. The drift check watches them |
| `AGENTS.md` | Template, copied once and filled in | It holds project facts: name, test command |
| `scripts/qa-codex` and its two files | Copied once (D6) | Keeps the guard form unchanged |
| Permission block, Auto mode entries, Codex trust entry, Lovable project | Manual or setup-assisted | A plugin cannot set them |

## 4. Open questions that the probe answers

The probe runs first, in a scratch project, with a minimal plugin. Each answer is a fact in a research note, not an opinion.

1. Does the PreToolUse guard hook fire when a plugin delivers it?
2. Do the PermissionDenied and SubagentStop hooks fire when a plugin delivers them?
3. Does `${CLAUDE_PLUGIN_ROOT}` resolve in the hook command, and does the hook script still find its inputs (the issue state comes from `gh`, not from files)?
4. Is the plugin `bin/` on the PATH of the Bash tool, also inside a subagent? (decides D6)
5. Do the agents, delivered by the plugin, read the role files from the project's copied `docs/` at the same paths?
6. Which agent front matter keys does Claude Code ignore for plugin agents?

If answer 1, 2 or 5 is "no", the work stops after the probe and the owner decides how to go on.

## 5. Failure behavior

- A missing manual entry never blocks the install. The setup step reports it and gives the exact fix.
- The setup step never overwrites a file. When a target file exists, it reports the difference and stops that copy.
- The drift check only reports.

## 6. Testing

- `claude plugin validate` passes (strict).
- Fact tests keep passing (`tests/test_doc_paths.py`, `tests/test_spec_citations.py`).
- The setup step and the drift check each get tests on a temporary directory.
- The trial: install the plugin in a fresh throwaway project and run one task through the loop (PM, engineer, QA, close). Findings become new issues.

## 7. Tasks

In this order. Each is one issue. The first one gates the others.

1. Probe: a plugin delivers the hooks, agents and `bin/` (section 4). Output: a research note
2. Plugin skeleton: manifest, layout, hooks in plugin form, agents and skills moved in, `claude plugin validate` as a test
3. Setup skill: copy the project files, record fingerprints, add the permission block, check the manual entries, report what is missing
4. Drift check
5. Install documentation for v2: a short README that replaces the ten manual steps, the remaining manual steps written out exactly, Lovable as an optional second step
6. Trial in a fresh throwaway project

Out of scope: adoption of existing projects (D1), the thin wrapper switch (D6, only after the probe), organization-owned repos (#75), Jev.
