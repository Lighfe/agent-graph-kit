# Start a real project from the README: plan

Plan for the stage that follows #157. It makes the v2 plugin route complete enough that the owner can start a new public project (board game, rules to an RL environment, then a frontend) from the README alone.

**Spec:** `docs/specs/2026-10-07-agent-graph-kit-v2-first-real-project.md`

**How this plan is used:** each task below becomes one issue in the `docs/task-template.md` format, with the label `later` until the owner confirms the stage. Existing issues are linked, not copied. Do not use the superpowers skills subagent-driven-development and executing-plans (see `AGENTS.md`). The loop runs the issues (`docs/process.md`).

## Global constraints

- Test command: `uv run --with pytest pytest`. The fact tests (`tests/test_doc_paths.py`, `tests/test_spec_citations.py`) stay green.
- Public repo rule: no secrets, real project ids or real account data in README text, tests or issues. Use synthetic examples.
- No change to `.claude/hooks/`, the project settings files in `.claude/`, or `QA_SANDBOX` in `scripts/qa-codex`. If a task needs one, the PM files it as `needs-owner`.
- No tracking mechanism for field projects (spec decision D6).

## Review focus

- Settings merge, file is not valid JSON: setup must stop and report, not overwrite (covered in #167).
- Settings merge, file already holds every kit line: setup must change nothing and say so (covered in #167).
- A README step that a new project cannot follow because it names a path that exists only in this repo (covered in #54 and in the last task).

## Order of the tasks

README and setup edits are chained, so two tasks never edit the same file at once.

| # | Issue | Blocked by |
|---|---|---|
| 1 | #167 Setup: merge permissions into an existing settings file (existing, unchanged) | none |
| 2 | #169 README: how to merge the settings lines by hand (existing, unchanged) | #167 |
| 3 | #54 Hook activation checklist usable in a new project (existing, unchanged) | none |
| 4 | #168 Setup and README: the steps the v2 route lacks (existing, unchanged) | #167, #54 |
| 5 | #166 README: what the owner does before step 1 (existing, body edited, see Task A) | #168 |
| 6 | #46 README v2: the Lovable lane steps (existing, body rewritten, see Task B) | #166 |
| 7 | #63 README: Lovable project knowledge entry (existing, criteria written, see Task C) | #46 |
| 8 | New: README "Start a new project" (see Task D) | #169, #168, #166, #46, #63 |

#165 (the `qa-codex` thin wrapper), #137 and the parked Lovable check #45 stay parked.

## Task A: edit #166

Why: its second criterion asks for a live install in an empty throwaway project. That is a user-level action that needs a permission. The board game start is the real check (spec D5), so the live check moves there.

New body of #166 (replace the whole body):

```markdown
Lane: default
Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md
Permissions: none

## Goal

The README route "Install the kit as a plugin (v2)" tells the owner what to do before step 1, so that `claude plugin marketplace add Lighfe/agent-graph-kit` finds the plugin.

## Acceptance criteria

- [ ] The README v2 section says that the plugin commits must be on `origin/main` on GitHub before step 1, and gives the command to check it (`git status -sb` shows no "ahead")
- [ ] The README says what `claude plugin marketplace add` prints when the marketplace file is not found on GitHub, and that the cause is an unpushed `main`
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- A live install from GitHub in a throwaway project. The first use in the owner's new project is that check
- Changing the plugin files

## Constraints

- Files: `README.md`
```

## Task B: rewrite #46

Why: the v2 section "Lovable frontend lane (optional, v2)" has three lines. The full steps (GitHub connection, `frontend/` submodule, Playwright dependency, bun or npm lockfile) are only in the v1 section "Frontend lane (optional)". The old body of #46 also names a paint-math issue that no longer applies.

New title: `README v2: the Lovable lane steps in the plugin route`

New body of #46 (replace the whole body):

```markdown
Lane: default
Permissions: none

## Goal

A project that installed the plugin can add the Lovable frontend lane by following the v2 section of the README alone, including the line `Lovable project: <id>` in `AGENTS.md` that `frontend-engineer` reads.

## Acceptance criteria

- [ ] The README section "Lovable frontend lane (optional, v2)" lists the steps in order: create the Lovable project, connect the workspace and the project to GitHub, make the Lovable repo public, add it as the `frontend/` submodule tracking `main`, add `@playwright/test` through Lovable and check the commit, bump the submodule pointer, install the `lovable` plugin
- [ ] It has a step that adds the line `Lovable project: <project id>` to `AGENTS.md`, with a synthetic example id
- [ ] It says that a Lovable credit check-in ends in `## Engineer: BLOCKED` and that the owner checks the credits before a frontend issue gets `ready`
- [ ] The text is written once: either the v2 section holds the steps and the v1 section links to it, or the v2 section links to the v1 section "Frontend lane (optional)". No second copy of the steps
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- The project knowledge entry (#63)
- Checking that `frontend-engineer` reaches the Lovable tools (#45). The owner finds that out in the first real project
- Changes to the `frontend-engineer` flow

## Constraints

- Files: `README.md`
- No real project ids: use a synthetic example
```

## Task C: write the criteria of #63

Why: its body says the PM writes the criteria. The stage names them now, so the PM only checks them.

Append to #63, in place of "To be written by the PM": keep the Goal and Background as they are, and use these criteria and constraints.

```markdown
## Acceptance criteria

- [ ] The README Lovable lane section has one step that sets the Lovable project knowledge once per Lovable project, with a synthetic example text
- [ ] The example text names standing constraints for frontend work (for example: no new drawing or random-number library, keep the `@playwright/test` dev dependency) and says that Lovable plans first and implements only after the `frontend-engineer` confirms
- [ ] The example text does not tell Lovable to implement a plan without that confirmation
- [ ] The step says that the owner sets it, because the `frontend-engineer` has no tool to set project knowledge
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- Changes to the `frontend-engineer` flow (#62)

## Constraints

- Files: `README.md` (the Lovable lane section that #46 completes)
- No secrets or real project ids in the example
```

## Task D: new issue "README: start a new project from scratch"

Why: the owner creates a new public repo and needs the order from an empty folder to the first working loop. The v2 section starts at "run these steps in the root of the project", so the repo creation is missing.

```markdown
Lane: default
Permissions: none

## Goal

The README has one section, "Start a new project", that takes the owner from an empty folder to a first working loop in the right order. It links to the existing steps and does not repeat them.

## Acceptance criteria

- [ ] The section starts with creating the project folder and the public GitHub repo (`gh repo create <name> --public --source . --push` or the web steps), and names the first push of `main`
- [ ] It states the public repo rule: no secrets, no real account data, no full third-party articles in commits, issues or comments; keys stay in the user environment
- [ ] It lists the order with a link for each step: install the plugin ("Install the kit as a plugin (v2)"), run `/agk:setup`, the manual steps (`gh` login, Codex login, Codex trust entry, the three Auto mode entries), the labels, commit and push, trust dialog, hook activation check, the Lovable lane (optional), then `/stage-start`
- [ ] It names which of these spend quota (a Codex QA run, Lovable credits) and which write to GitHub (repo creation, labels)
- [ ] It says where to report a kit problem: an issue in `Lighfe/agent-graph-kit` with the failing command, the message and the issue where it happened, with secrets redacted
- [ ] Every link and path in the section exists in a new project or in this repo's README (`tests/test_doc_paths.py` passes)
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- Repeating the steps that other sections already hold
- A tracking list or log of projects that run on the kit

## Constraints

- Files: `README.md`
- Public repo rule applies to the examples: use synthetic names
```

## Stage issue

Write it in the form "Stage issue" of `docs/task-template.md`.

```markdown
## Purpose

The owner starts a new public project (board game rules to an RL environment, then a frontend) and reaches a working kit from the README alone: default lane, Lovable frontend lane and Codex QA.

## Background

- Spec: `docs/specs/2026-10-07-agent-graph-kit-v2-first-real-project.md`. Plan: `docs/plans/2026-10-07-first-real-project.md`.
- It follows #157. The plugin works, but the trial found gaps in the install route: setup does not merge permissions into an existing settings file, and the README lacks steps that the v1 route had.
- The owner chose to use the plugin in the real project now. There is no throwaway re-trial. The first use in the real project is the trial, and each gap found there becomes an issue in this repo.
- README edits are chained with blockers so two tasks never edit the file at once.
- Not in this stage: the `qa-codex` thin wrapper (#165), adoption of existing projects (#15), the Lovable tool check (#45).

## Exit check

Every sub-issue is closed and the purpose is met.
```

## Steps after the owner confirms

1. File the stage issue with the label `stage`. Add the sub-issues in the order of the table, then set the blockers of the table.
2. Edit #166 and #46 (new title and body), and #63 as in Tasks A to C. File Task D with the label `later`.
3. Name every `Permissions:` entry that is not `none` to the owner. The plan has none.
4. After the owner confirms: on each sub-issue, `gh issue edit <n> --remove-label later --add-label ready`. Close #157. Move the plan to `docs/archive/` only when this stage is set up (it is the only stage of this plan), and commit.
