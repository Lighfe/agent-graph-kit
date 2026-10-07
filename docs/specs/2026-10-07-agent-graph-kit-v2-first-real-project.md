# Agent graph kit v2: start a real project from the README

- Date: 2026-10-07
- Status: written for the owner's review.
- Input: the stage review on #157 (`## Planner: STAGE REVIEW`), the plugin trial report `docs/reviews/plugin-trial.md` (#163), and the owner's choice of a hybrid between its options 1 and 2.
- Builds on: `docs/specs/2026-10-05-agent-graph-kit-v2-plugin.md` (decisions D1 to D9 stay valid).

---

## 1. Purpose

The owner starts a new public GitHub project, a board game rules-to-RL-environment project with a frontend, and runs the kit on it. From an empty folder, the owner reaches a working kit with the README alone: the default lane, the Lovable frontend lane, and Codex QA. The board game project is the real trial of the plugin route. It replaces a throwaway re-trial.

## 2. Decisions

| # | Decision |
|---|---|
| D1 | The four install gaps that the trial found are fixed first: setup merges its permissions into an existing settings file, the README says how to merge by hand, setup and README cover the steps the v1 route had, and the README says what the owner does before the install |
| D2 | The hook activation checklist (`docs/checks/hook-activation.md`) must run in a new project. It is merged into the task that adds the missing steps, because the README sends a new project to it |
| D3 | The Lovable frontend lane gets its two README set-up steps: the `Lovable project: <id>` line in `AGENTS.md`, and the Lovable project knowledge entry. The check that the frontend engineer reaches the Lovable tools is not part of this stage. The owner finds that out in the board game project |
| D4 | A new README section "Start a new project" walks from creating the public repo to the first working loop. It links to the other steps and does not repeat them. It repeats the public repo rule: no secrets in commits, issues or comments |
| D5 | No throwaway re-trial. The first use in the board game project is the trial |
| D6 | No tracking mechanism is added to this repo. No field-project list, no log file, no change to the planner. When the owner wants feedback from the board game project read, the owner gives its GitHub URL in a session here, and the planner reads its public issues and files kit issues as for any other finding |
| D7 | The `qa-codex` thin wrapper (#165), observability and adoption of existing projects (#15) stay out |

## 3. Scope of each change

| Area | Change |
|---|---|
| `plugin/skills/setup/` | Merge the `permissions` block into an existing `.claude/settings.json`. Keep existing entries and `enabledPlugins`. Write `CLAUDE.md` and the `.gitignore` lines, or the README names the step |
| `README.md`, v2 section | By-hand merge instructions, the four labels, commit and push, trust dialog, hook activation check, a line on what the owner does before step 1, the Lovable steps, and the new section "Start a new project" |
| `docs/checks/hook-activation.md` | No reference to issue #7 as trigger. The `disableAllHooks` step applies only when the local settings file exists. The results go to a target that exists in a new project |

## 4. Failure behavior

- Setup never overwrites a file. When it merges settings, it adds only missing lines and keeps all other content.
- A step that setup cannot do stays a named manual step in the README. Setup reports it.

## 5. Testing

- A test covers both merge cases of the settings file (file holds only `enabledPlugins`, file holds other `permissions` entries).
- The fact tests keep passing (`tests/test_doc_paths.py`, `tests/test_spec_citations.py`).
- The test command is `uv run --with pytest pytest`.
- The README as a whole is checked in practice: the owner follows it for the board game project. Each gap found there becomes an issue in this repo.
