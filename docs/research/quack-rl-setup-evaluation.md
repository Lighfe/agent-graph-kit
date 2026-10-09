# quack-rl set-up evaluation

Issue: [#184](https://github.com/Lighfe/agent-graph-kit/issues/184). This report compares the first real project that uses the kit as a plugin, `Lighfe/quack-rl`, with what the kit documents. It only reads quack-rl; nothing there was changed.

## Snapshot

- Checked: 2026-10-09, 07:58 UTC (the project keeps running, so everything below is the state at this time)
- quack-rl head on `main`: `c86845cc92468cf0c7e8567841ea01ea1009fddd` (commit "Add Python project skeleton and quack-rl CLI stub", 2026-10-09 06:30 UTC)
- quack-rl issues read: #1 (closed, throwaway hook check), #2 (stage issue, open), #3 to #14 (the 12 sub-issues, all open). Comments exist only on #1 and #3; #2 and #4 to #14 have none
- Kit side: this repo at `b6884b1`; blocker #47 of this repo (closed 2026-10-09 06:58 UTC)
- Method: issue bodies, comments, timelines and sub-issue/blocker links via read-only `gh`; the project files at the head SHA compared with `plugin/templates/`, `plugin/skills/setup/` and the output of `plugin/skills/drift/drift.py` run on a copy of the project files

Result words: `matches`, `mismatch`, `cannot tell`. A `mismatch` has evidence and one proposed change.

## 1. Issues

### Stage issue #2

| Check | Result |
| --- | --- |
| Sections Purpose, Background, Exit check | matches |
| Label `stage` | matches |
| Never `ready` | mismatch (see M1): `ready` was added 2026-10-09 06:26:14 UTC and removed 06:39:28 UTC. It is gone now |
| Exit check is the default text | matches |
| No `Lane:` line | matches |
| 12 sub-issues, in plan order | matches: the list order is #3 to #14, and the plan has Task 1 to Task 12 (`docs/plans/2026-10-08-m1-terminal-game.md`, headings "### Task 1" to "### Task 12") |
| Each plan task has exactly one issue | matches: M1.1 to M1.12 map to Task 1 to Task 12, one issue each, issue number = task number + 2 |

### Sub-issues #3 to #14

| Check | Result |
| --- | --- |
| Form: `Lane`, `Permissions`, Goal, Acceptance criteria, Out of scope, Constraints | matches on all 12 (5 to 12 checkbox criteria each) |
| Sub-issue links | matches: all 12 are native sub-issues of #2 (`sub_issues_summary.total` = 12) |
| Blockers | matches the plan's chain: #4 blocked by #3, #5 by #4, and so on to #14 by #13. Added 2026-10-08 20:09 UTC at set-up. This is a valid use of native blockers; it means only one sub-issue is eligible at a time |
| Blocker on #3 | matches: #3 is also blocked by Lighfe/agent-graph-kit#47, added by the PM (see section 2) |
| Labels at creation: `later` until the owner confirms | mismatch (M2): none of the 12 sub-issues has a label event for `later`; the only label event on each is `ready`, 2026-10-09 06:26:14 to 06:26:24 UTC |
| Label `ready` on the sub-issues | matches (all 12 have it, none has `later` or `needs-owner`) |
| Out of scope names the sibling task as an issue number | mismatch (M3): #4 and #8 to #13 write "task 3", "task 7" and so on. Only #3 uses `#4`, `#5` (the PM rewrote it) |
| Each criterion can be answered yes or no by looking at a result | cannot tell for #4 to #14: they are not groomed yet; #3 was checked by the PM |

### Throwaway issue #1

- Form: no `Permissions:` line; the PM wrote that it treats it as `none`. mismatch with the task form, but low weight. The text of that issue came from the hook check of that day; the current `plugin/skills/hook-activation-check/` does not contain the body, so the source cannot be found: cannot tell
- Label `ready` set by hand 2026-10-08 11:45 UTC, as the check asks. matches
- Closed by the owner without `## QA: PASS` (the QA launch has no result comment). matches the issue's own text ("The owner closes this issue after the check"); not a loop close

## 2. Comments

Marker check: every first line of every comment is a documented marker (`## Launch: <role> (attempt n)`, `## Launch: <role> (continued, round n)`, `## PM: GROOMED`, `## PM: WAITING`, `## Engineer: BLOCKED`, `## Engineer: DONE`, `## QA: UNVERIFIABLE`). All comments are by `Lighfe` with `authorAssociation` OWNER. A scan for key patterns (`sk-`, `ghp_`, `AKIA`, "api key", "token", "secret", "password") found nothing. Result: matches.

Order on #1 (throwaway): Launch pm 1, PM GROOMED, Launch engineer 1, Engineer BLOCKED, Launch pm (continued, round 2), PM GROOMED, Launch engineer 2, Engineer DONE (with the `Commits:` line, "no code change was needed"), Launch qa 1, no QA result. matches (the missing QA result is the owner close above).

Order on #3 ([comments](https://github.com/Lighfe/quack-rl/issues/3)): Launch pm 1 (06:27:45), PM GROOMED (06:29:21), Launch engineer 1 (06:29:33), Engineer DONE (06:31:07), Launch qa 1 (06:31:18), QA UNVERIFIABLE (06:32:10), Launch pm 2 (06:32:24), PM WAITING (06:33:17). matches: each result follows its launch receipt, and the lifecycle in `docs/process.md` (QA UNVERIFIABLE goes back to the PM) is followed.

Role behavior:

- PM on #3 (groom): matches. It rewrote vague criteria into checkable ones and kept to the template
- Engineer on #3: matches. `## Engineer: DONE` first line, `Commits: a037c4d…c86845c` line, quoted result lines, deviations named. One cosmetic point: the range mixes a full SHA and a short SHA; both resolve
- QA on #3 (`qa-codex`): matches the form. All six commands that run `uv` failed before running ("Failed to download nodejs-wheel-binaries"), and QA marked them `- INVALID` under `## QA: UNVERIFIABLE`, as `docs/process.md` says
- PM on #3 (after UNVERIFIABLE): matches the rule "A tool problem that an issue can fix". The blocked-by link to agent-graph-kit#47 was added at 06:33:05 UTC, 12 seconds before `## PM: WAITING` (06:33:17). The PM left the six criteria unchanged and named the cause
- Orchestrator: cannot tell. The documented orchestrator posts no issue comment after `## PM: WAITING` with an open blocker ("continue with the next issue, with no owner comment", `docs/team/orchestrator.md`). Every other sub-issue is blocked by the one before it, so no sub-issue was eligible, and the documented result is: stop, and tell the owner in the final report. That report is in the session, not on an issue, so this evaluation cannot see it. What the owner reported (the loop re-checked the same blocker until the stop hook hit its cap) is explained by M1
- Who works on a blocker in another repo: the docs say the orchestrator does not promote or pick it (`docs/process.md`, "Promotion of a parked blocker") and the PM said so in its comment, but nothing says what the owner has to do. See M5

## 3. Repo set-up

Files that `/agk:setup` writes, compared with the project at the head SHA. The lock file `.agent-graph-kit.lock` records the sha256 of each file as copied; every file that exists in quack-rl has exactly the locked sha256. So the owner edited none of the copied files (they are all as copied).

| File | Result |
| --- | --- |
| `AGENTS.md` | matches the template with name `quack-rl` and test command `uv run --with pytest pytest` filled in |
| `CLAUDE.md` | matches (exactly `@AGENTS.md`) |
| `docs/process.md`, `docs/task-template.md`, `docs/team/*.md` (5 files), `docs/checks/hook-activation.md` | present. `task-template.md`, `orchestrator.md`, `pm.md`, `qa-engineer.md`, `software-engineer.md` are the same as the plugin today. `process.md`, `planner.md` and `hook-activation.md` are older than the plugin templates: mismatch (M6) in the sense that the kit moved on after set-up; this is not an owner change |
| `scripts/qa-codex` | matches the template today (two lines, `exec qa-codex-launcher "$@"`). The project's own commit `6c4960e` ("Switch scripts/qa-codex to plugin wrapper, drop copied launcher files") replaced an older copied launcher and removed `scripts/codex_exec.py` and `scripts/qa-result.schema.json` |
| `.agent-graph-kit.lock` | mismatch (M4): it still lists `scripts/codex_exec.py` and `scripts/qa-result.schema.json`, which the project deleted and the plugin no longer ships |
| `.gitignore` | matches: has `.claude/settings.local.json` and `__pycache__/`. Extra line `/data/` is the project's own (game records, local only) |
| Settings file (`.claude/` folder, read through the blob) | matches: `permissions.allow` has `Bash(scripts/qa-codex ROLE=qa ISSUE=*)` and `Bash(gh issue close *)`, `permissions.deny` has `Edit(/.claude/settings*.json)`. Extra: `enabledPlugins` `agk@agent-graph-kit: true`, which `claude plugin install --scope project` writes |
| `.claude/hooks/`, `.claude/agents/`, `.agents/skills/`, `.claude/skills` link | absent, and that is correct: the plugin delivers hooks, agents and skills in v2 |
| Labels | matches: `ready`, `needs-owner`, `later`, `stage` exist in the repo (plus the GitHub default labels) |

Project's own files (not from the kit): `README.md`, `pyproject.toml`, `uv.lock`, `.python-version`, `src/`, `tests/`, `docs/specs/`, `docs/rules/`, `docs/plans/`, `docs/reviews/`, `docs/archive/`. Missing files: none. Extra kit-like files: none.

`drift.py` run on the project files gives:

```
unchanged: AGENTS.md
no longer in the plugin: CLAUDE.md          <- wrong, see M7
newer in the plugin: docs/checks/hook-activation.md
newer in the plugin: docs/process.md
unchanged: docs/task-template.md
unchanged: docs/team/orchestrator.md
newer in the plugin: docs/team/planner.md
unchanged: docs/team/pm.md
unchanged: docs/team/qa-engineer.md
unchanged: docs/team/software-engineer.md
deleted from this project: scripts/codex_exec.py
unchanged: scripts/qa-codex
deleted from this project: scripts/qa-result.schema.json
```

What the three "newer in the plugin" files differ in: `process.md` (the status line no longer says "There are no Jev gates yet"), `planner.md` (step 7 of the stage review now says the prompt audit did not run and gives the manual command), `hook-activation.md` (rewritten as optional background).

## 4. README route

The route is `README.md`, "Start a new project", steps 1 to 10. What the repo and issues show:

| Step | Result |
| --- | --- |
| 1 to 3 (repo, trust, plugin install) | matches: `enabledPlugins` is in the settings file |
| 4 (`/agk:setup`) | matches: commit `2aaea6a` "Set up agent-graph-kit loop with /agk:setup" (2026-10-08 11:37 UTC) holds the files and the lock |
| 5 (Codex trust, three Auto mode entries) | cannot tell: they are user-level and not in the repo. The QA ran under Codex (`Checker: codex`), so at least Auto mode entry 1 and the trust worked |
| 6 (four labels) | matches |
| 7 (commit and push) | matches |
| 8 (`/agk:hook-activation-check`) | matches: throwaway issue #1 went through PM, engineer (with a SendMessage continuation) and QA launch |
| 10 (`/stage-start`) | partly: the stage issue, 12 sub-issues, links and blockers exist and are right. The labels are not (M1, M2). The relabel is one batch at 06:26 UTC over #2 to #14, 10 seconds in total, by the owner's login |
| Updating after setup | mismatch (M6): the README "Update the kit in a project" section is the v1 route (copy from a clone of this repo, `cp -r .claude/hooks …`). A plugin project has no clone and no `.claude/hooks`. The only v2 hint is the last line of the steps (`/agk:drift`), which shows `newer in the plugin` but does not say how to take the new file. Commit `6c4960e` shows the owner had to do this update by hand |

## 5. Mismatches and proposed changes

- M1. A stage issue got `ready` and stalled the loop. Evidence: [quack-rl#2 timeline](https://github.com/Lighfe/quack-rl/issues/2) (`labeled ready` 06:26:14, `unlabeled ready` 06:39:28), in the same second as the first sub-issue. Cause in the kit: the stop condition of `/goal` is written as the `gh issue list --state open --label ready --search "-label:later -label:needs-owner"` result (`docs/team/orchestrator.md`, "Done"; `docs/process.md`, "Stop condition for `/goal`"; `AGENTS.md`). That list includes a stage issue with `ready`, and a stage issue never has an open blocker, so "no `ready` issue is without an open blocker" can never be true. The docs do have the other stop clause ("the active stage has open sub-issues, none of them eligible"), but the command a checker runs does not. Nothing flags the label: the guard (`G1`, planner path) says "the label ready is neither required nor denied" and `docs/team/planner.md` only says "never add `ready`" (no check after the relabel). Answer to the question in the issue: yes, the kit should cope with one wrong label. Proposed change (this repo): (a) add `-label:stage` to the list command in `AGENTS.md`, `plugin/templates/AGENTS.md.tmpl`, and the stop wording in `docs/team/orchestrator.md` and `docs/process.md`, so a stage issue is never in the count; (b) at the start of a `/goal` run the orchestrator removes `ready` from an open stage issue and names it in the final report (a label edit it may already do, no owner action); (c) after the relabel step in `docs/team/planner.md`, check that the stage issue has no `ready`.
- M2. The sub-issues never carried `later` before the owner relabeled them. Evidence: label events of #3 to #14 (only `ready`). `docs/team/planner.md`, "Intake" step 5, says each issue is filed with `later`. Effect: the planner's relabel `--remove-label later --add-label ready` gives no sign that the step did not run as written, and for about 10 hours (20:09 to 06:26 UTC) nothing separated "not confirmed" from "no label". The loop did not run in that time, so nothing was worked early. Proposed change (this repo): add a check to `docs/team/planner.md` after filing, "list the sub-issues and confirm each has `later` before asking the owner to confirm the stage", and the same for the stage issue (`stage`, no `ready`). Whether the owner's session skipped the `later` step or the filing call dropped it: cannot tell.
- M3. Out of scope lines name sibling tasks as "task N", not as the issue number. Evidence: quack-rl#4 "Chip behavior (task 3)", and the same form in #8 to #13. `docs/task-template.md` shows `#TASK-NUMBER`, and the plan numbers differ from the issue numbers by 2 (Task 3 is #5). A reader of the issue alone would look for the wrong number. The PM fixed this in #3 while grooming. Proposed change (this repo): in `docs/team/planner.md` "Intake" step 5, add a pass after the last issue is filed that replaces "task N" with `#<issue number>`, since the numbers are known only then.
- M4. The lock file lists files the project and the plugin no longer have. Evidence: `.agent-graph-kit.lock` entries `scripts/codex_exec.py`, `scripts/qa-result.schema.json`; drift prints "deleted from this project" for both. The project removed them on purpose (commit `6c4960e`), the plugin does not ship them, and nothing updates the lock. Proposed change (this repo): in `plugin/skills/drift/drift.py`, when a locked path is missing in the project and has no template, print one line such as `dropped (gone from both): <path>`; and say in the drift skill that the owner can delete such lock entries.
- M5. The docs do not tell the owner what to do with a blocker in another repo. Evidence: the PM comment on [quack-rl#3](https://github.com/Lighfe/quack-rl/issues/3) ("Lighfe/agent-graph-kit#47 is in another repo and has `later`, so the loop does not promote it"), `docs/process.md` ("An open blocker that is not a parked issue … is not promoted … the blocked issue waits"). The loop followed the rules; the owner still had to find out by reading. Proposed change (this repo): in `docs/team/orchestrator.md`, "Next step while a stage is active" step 3 and the final message, say that for an open blocker outside this repo the report starts with one line `Waiting for <owner/repo>#<n>: <title>. Close it, then the loop can start again.`, once, and the loop stops (no re-check).
- M6. A plugin project has no documented way to take new kit files. Evidence: README "Update the kit in a project" (v1 only); drift shows three `newer in the plugin` files in quack-rl. Proposed change (this repo): add a "Update a plugin project" section to `README.md`: run `/agk:drift`; for `newer in the plugin` copy the template over the file; for `changed in both` merge by hand; then re-run setup's lock step or edit the lock. Optionally the drift skill gets a `--update` flag that copies only `newer in the plugin` files and rewrites the lock (separate decision for the owner).
- M7. `drift.py` reports `no longer in the plugin: CLAUDE.md` for an untouched `CLAUDE.md`. Evidence: output above; the template is `plugin/templates/CLAUDE.md.tmpl`, but `state()` looks for `plugin/templates/CLAUDE.md` (only `AGENTS.md` has a special case). Every plugin project gets this wrong line. Proposed change (this repo): in `plugin/skills/drift/drift.py` map `CLAUDE.md` to `CLAUDE.md.tmpl` (compare its sha256 with the lock), and add a test.

Not a mismatch, noted: the QA failure on #3 (`uv sync` offline) is the known gap that #47 fixed. After the fix lands in the plugin, #3 goes back to the PM by the documented rule; no quack-rl change is needed.

## 6. Proposed follow-up issues

Each reads on its own. All are for this repo (Lighfe/agent-graph-kit), none changes quack-rl.

1. A stage issue with the label `ready` must not stall `/goal`. Goal: in a run where the stage issue of the project has `ready`, the loop still stops with the documented stage result. Do: add `-label:stage` to the open-issue list command in `AGENTS.md`, `plugin/templates/AGENTS.md.tmpl`, `docs/team/orchestrator.md` and `docs/process.md` (and the template copies of the last two); let the orchestrator remove `ready` from an open stage issue at run start and name it in the final report; add to `docs/team/planner.md` a check after the relabel that the stage issue has no `ready`. Evidence: the stage issue Lighfe/quack-rl#2 had `ready` from 2026-10-09 06:26 to 06:39 UTC while all sub-issues waited on one blocker; the stop condition could not hold. (Source: this report, M1.)
2. The planner checks the labels after filing and after the relabel. Goal: before the owner confirms a stage, every sub-issue has `later`, the stage issue has `stage` and no `ready`. Evidence: in Lighfe/quack-rl, none of the 12 sub-issues had `later`. Also replace "task N" in Out of scope by the issue number once all issues exist (Lighfe/quack-rl#4 and #8 to #13 show the problem). Change `docs/team/planner.md` and its template copy. (M2 and M3.)
3. Orchestrator: say once what waits for a blocker in another repo. Goal: when the stage stops because every open sub-issue waits for a blocker outside this repo, the final report has one line with that blocker's URL and what must happen, and the loop does not re-check it. Evidence: Lighfe/quack-rl#3 blocked by Lighfe/agent-graph-kit#47. Change `docs/team/orchestrator.md` (and the template copy). (M5.)
4. Fix the drift skill: `CLAUDE.md` is compared with `CLAUDE.md.tmpl`, and a locked path that is gone from both the project and the plugin is shown as dropped. Files: `plugin/skills/drift/drift.py`, its SKILL.md, a test. Evidence: the drift output on the quack-rl files. (M4 and M7.)
5. Write the update route for plugin projects in `README.md`: take the files that `/agk:drift` shows as `newer in the plugin`, merge `changed in both`, refresh the lock. Decide whether a `--update` flag is wanted (owner decision). Evidence: three files of Lighfe/quack-rl are older than the plugin templates, and the README update section only covers the copy route. (M6.)
