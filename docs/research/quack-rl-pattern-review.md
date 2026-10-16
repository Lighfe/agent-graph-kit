# quack-rl pattern review

This report looks for patterns in the first real project that uses the kit, `Lighfe/quack-rl`. A pattern is something that happened more than once, or a systematic gap. It builds on `docs/research/quack-rl-setup-evaluation.md` (findings M1 to M7) and does not repeat them. Where the data confirms or extends M1 to M7, the text says so.

Snapshot: 2026-10-16, about 09:00 UTC. quack-rl head `a4464c9` on `main`. The project keeps running, so numbers are for this moment. Nothing in quack-rl or on GitHub was changed.

## 1. Scope

What was read:

- All 93 quack-rl issues (74 closed, 19 open), with all comments: about 1 MB of text. Every first line of every comment was tabulated; every `## QA: FAIL`, `## QA: UNVERIFIABLE`, `## QA: UNAVAILABLE`, `## Engineer: BLOCKED`, `Escalated:` and `## Owner: RESUME` comment was read in full; all 9 stage reviews were read (run notes, doc drift, follow-up parts); about 25 issue bodies were read in full.
- Label events, sub-issue and blocker relations, and body-edit counts of all 93 issues (read-only `gh api` calls; the edit history through a GraphQL read query).
- quack-rl project files: `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.claude/skills/`, `.agent-graph-kit.lock`, `docs/team/*`, `docs/process.md`, `pyproject.toml`, the file list, and the whole git log (115 commits). The kit copies in `docs/` were diffed against `plugin/templates/` of this repo.
- Kit side: this repo's `docs/process.md`, `docs/team/*`, `docs/task-template.md`, the plugin templates and launcher, and all 193 kit issues (titles; bodies of the open ones from #146 on).

What could not be read or measured:

- Token counts, cache use, model used per launch, and the orchestrator's session text (final reports, stop-hook messages). They are not on the issues.
- Time that the loop spent between steps (orchestrator latency, git, tests inside the engineer launch). Only receipt and result timestamps are visible.
- Who edited an issue body: the owner, the PM and the planner all use one login. An edit count of 2 means "created, then one edit".
- The stage review for the open stage #87 does not exist yet. The comments of the 14 open issues without comments (#49, #57, #58, #71, #79 to #86, #90 to #93) are empty by design.
- I did not read every `## Engineer: DONE` and `## PM: GROOMED` comment in full. Marker sequences and timestamps cover all of them.

One side note on the kit: while I wrote this report, the kit's own guard `G1` denied a read-only command of mine because it contained the text `qa-codex` (see pattern 12).

## 2. Patterns

### Numbers for the whole project (marker counts)

| Marker | Count | Issues | Note |
| --- | --- | --- | --- |
| `## PM: GROOMED` | 76 | 63 | 78 PM launches |
| `## PM: WAITING` | 1 | 1 | #3, the tool-problem path, worked as designed |
| `## PM: NEEDS OWNER` | 0 | 0 | |
| `## Engineer: DONE` | 93 | 62 | 101 engineer launches |
| `## Engineer: BLOCKED` | 5 | 5 | #1 (synthetic), #14, #24, #31, #72 |
| `## QA: PASS` | 61 | 61 | every QA'd issue ended in PASS |
| `## QA: FAIL` | 24 | 19 | 31 percent of QA'd issues failed at least once |
| `## QA: UNAVAILABLE` | 15 | 13 | 14 are the Codex usage limit, 1 a network error in the pre-step |
| `## QA: UNVERIFIABLE` | 7 | 7 | #3, #53, #60, #67, #68, #70, #73 |
| `## QA: INVALID` | 0 | 0 | |
| `Escalated:` (orchestrator) | 5 | 4 | #24 (twice), #31, #72, #89 |
| `## Owner: RESUME` (real) | 5 | 4 | #24, #31, #72, #89 (twice) |
| Launch without result (miss) | 4 | 3 | #37 engineer 1, #63 QA 1, #89 engineer 2 |
| `## Launch not started` / `stopped by outage` | 0 | 0 | |
| Checker footer `codex` / `claude (fallback)` | 92 / 15 | | |
| Returns reaching the limit of 3 | 3 | | #24, #31, #72 (all escalated at 3; #24 also once at 2) |

QA found real defects: the 24 FAILs mostly name a real gap (a test that only mirrors the code, a missing edge case, a truncated board at width 80, an illegal mask at the terminal step). This is the main proof that QA pays for itself. The patterns below are about where the loop wastes effort, not about QA being wrong.

### P1. The Codex usage limit turns most QA runs into cold fallback runs

- Evidence: 14 of 15 `## QA: UNAVAILABLE` comments say "You've hit your usage limit" (for example [#31](https://github.com/Lighfe/quack-rl/issues/31), [#37](https://github.com/Lighfe/quack-rl/issues/37), [#38](https://github.com/Lighfe/quack-rl/issues/38), [#41](https://github.com/Lighfe/quack-rl/issues/41), [#48](https://github.com/Lighfe/quack-rl/issues/48), [#54](https://github.com/Lighfe/quack-rl/issues/54), [#55](https://github.com/Lighfe/quack-rl/issues/55), [#61](https://github.com/Lighfe/quack-rl/issues/61) to [#63](https://github.com/Lighfe/quack-rl/issues/63), [#67](https://github.com/Lighfe/quack-rl/issues/67), [#68](https://github.com/Lighfe/quack-rl/issues/68)). The comment names the reset time ("try again at 3:26 PM"). The limit hit on 10-09, 10-10, 10-12 and 10-13. 13 of 62 QA'd issues (21 percent) ended with a Claude fallback verdict, 10 of them inside two stages (M2.4 and M2.5).
- Cost: a Codex QA result takes a median of 3.6 minutes (77 results); the fallback takes a median of 9.2 minutes (15 results), about 2.6 times longer, and starts with no context. The `UNAVAILABLE` run itself takes under a minute (median 0.6). The stage reviews of #56 and #40 call the loss of the second-model check "a risk" but propose no change.
- Second effect: the fallback has no browser. QA of #67 and #68 could not repeat a click check (see P3).
- Root cause: `docs/team/orchestrator.md` ("Decisions at each edge": UNAVAILABLE launches the fallback) has no memory of the reset time. Every issue first tries Codex and fails, then starts the fallback. The kit has no hand-off from the failed Codex run to the fallback.
- Proposed kit change: (a) the orchestrator reads the reset time from the `UNAVAILABLE` reason and, until then, launches the fallback directly (the hook G4 allows the fallback only after `UNAVAILABLE`, so the hook needs a matching allowance, or the launcher records a "limit until" time and answers `UNAVAILABLE` at once); (b) the stage review run notes count `UNAVAILABLE` per stage and say so in one line.
- Kit issue: partly. [#189](https://github.com/Lighfe/agent-graph-kit/issues/189) "Reduce delays due to codex QA Engineer limitations" (open, first draft, asks for cheaper models and a hand-off) and [#193](https://github.com/Lighfe/agent-graph-kit/issues/193) "Monitoring: where a run spends time, tokens and compute" (open). Neither says "remember the reset time". Add it to #189.

### P2. Criteria that QA cannot check in its own world (7 UNVERIFIABLE and one FAIL with INVALID criteria)

QA works from the checkout, the newest `## Engineer: DONE` comment and the state files. All seven `UNVERIFIABLE` results, and the `INVALID` criteria of one FAIL, came from criteria that need something else:

- A GitHub fact or an older comment: [#70](https://github.com/Lighfe/quack-rl/issues/70) (QA could not see that follow-up #76 exists) and [#73](https://github.com/Lighfe/quack-rl/issues/73) (the baseline lives in an earlier DONE comment). The stage review of #74 names the cause: "QA sees only the newest engineer comment and has no GitHub access".
- An ignored local folder: [#78](https://github.com/Lighfe/quack-rl/issues/78) (`data/runs/selfplay-1` is git-ignored and absent in QA's checkout; QA FAIL with two `INVALID` criteria).
- A dependency group that the QA sandbox does not install: [#3](https://github.com/Lighfe/quack-rl/issues/3) (`uv sync` offline; fixed by kit #47), [#53](https://github.com/Lighfe/quack-rl/issues/53) (torch), [#60](https://github.com/Lighfe/quack-rl/issues/60) (`sb3_contrib`). The owner then edited the cached launcher by hand (`--group train`), see P6.
- A browser click check that QA must repeat: [#67](https://github.com/Lighfe/quack-rl/issues/67) and [#68](https://github.com/Lighfe/quack-rl/issues/68). The fallback has no `playwright`; under Codex the sandbox blocked Firefox's network call. Two full UNVERIFIABLE cycles (PM, engineer with no code change, QA again) for a criterion that no checker could run.
- Root cause: `docs/team/pm.md` fixes this only after the fact ("After `## QA: UNVERIFIABLE`"). Grooming has no up-front rule such as "write every criterion so it can be checked from the checkout, the newest DONE comment and the state files; do not point to other issues, older comments, ignored folders, optional dependency groups or a browser". `docs/team/qa-engineer.md` line "Start the app and run the browser check in one command" promises a browser that neither checker has.
- Proposed kit change: add that up-front check to the "Definition of done" of `docs/team/pm.md`, with the four cases above as examples. For criteria that need a fact outside QA's world, say that the criterion makes the engineer state the fact inline in `## Engineer: DONE` (this is what quack-rl #80 asks for). Remove the browser line from `docs/team/qa-engineer.md`, or make it conditional on a browser tool being listed. Support optional dependency groups in the Codex pre-step, for example by reading groups from an optional line in `AGENTS.md`, or by `uv sync --all-groups` when the lock has groups.
- Kit issue: partly. [#191](https://github.com/Lighfe/agent-graph-kit/issues/191) "Self-contained github issues" (open) is a two-line stub that points to quack-rl #80; it says nothing about the four cases. [#47](https://github.com/Lighfe/agent-graph-kit/issues/47) (closed) fixed only `uv sync --frozen`. No kit issue for optional dependency groups or for the browser line.

### P3. Criteria that force a result the work cannot give, or that rest on an unchecked premise

Evidence (three escalations and one BLOCKED came from this):

- [#24](https://github.com/Lighfe/quack-rl/issues/24) "bot core": "two runs with the same seed give identical records". `game_id` is random on purpose. Two QA FAILs, one BLOCKED, escalation, owner decision.
- [#14](https://github.com/Lighfe/quack-rl/issues/14) "terminal play": the same `game_id` footer problem, plus a criterion that names `click.getchar` while the locked typer no longer installs click. QA FAIL, BLOCKED, regroom.
- [#31](https://github.com/Lighfe/quack-rl/issues/31) "balance analysis": "each finding proposes a rule-number candidate". Finding 6 found no problem. Two QA FAILs, BLOCKED, escalation. The planner's stage review: "a criterion should not force a result that the data may not give".
- [#72](https://github.com/Lighfe/quack-rl/issues/72) "resume a training run": criteria on the logging behaviour of a library (SB3) that nobody had run. FAIL, BLOCKED, FAIL, escalation. Stage review: "do not write criteria on a library's logging behaviour without running it first".
- Smaller: [#65](https://github.com/Lighfe/quack-rl/issues/65) (checkpoint at exact multiples, SB3 saves at rollout boundaries), [#88](https://github.com/Lighfe/quack-rl/issues/88) (`## Decision` "must end the note": a literal reading failed a good note).
- The M1 stage review of [#2](https://github.com/Lighfe/quack-rl/issues/2) says it plainly: "the criteria were written from the plan without checking the locked dependency versions and the random `game_id`. Plan-to-issue steps should check such facts."
- The project patched this locally with [#30](https://github.com/Lighfe/quack-rl/issues/30) (a game-specific paragraph in its own `pm.md` and `qa-engineer.md`: ignored fields `game_id`, `started_at`, `finished_at`). That fix is project-specific and now shows in `/agk:drift`. The general lesson is not in the kit.
- Root cause: `docs/team/pm.md` makes criteria checkable but has no rule for criteria whose premise can be tested cheaply, and none for "a criterion must have a possible pass outcome" (equality with a random field; "every finding does X" when a finding may be empty). `docs/team/planner.md` Intake step 5 files plan tasks without a premise check.
- Proposed kit change: in `docs/team/pm.md`, a short "Check the premise" rule: for each criterion that names an equality, a library behaviour, a dependency or a count over a set that may be empty, read the code or run the one-line check, and word the criterion so a pass is possible ("for each problem finding", "ignoring fields X"). In `docs/team/planner.md` Intake step 5, a premise check against the lock file and the code for versions and names.
- Kit issue: none.

### P4. Escalation at 2 returns, and the same orchestrator doing diagnosis by hand

- [#24](https://github.com/Lighfe/quack-rl/issues/24): the orchestrator posted `Escalated:` after 2 QA FAILs (16:00), then reverted the labels (16:01), launched the engineer a third time, escalated again (16:02), and wrote "The earlier escalation comment on this issue came too early". The rule is "after 3 returns" (`docs/process.md`, Rules). The stage review of #26 records it. A premature escalation costs an owner click and flips labels three times. The hook only denies the launch at 3 returns; nothing stops an early escalation.
- [#89](https://github.com/Lighfe/quack-rl/issues/89): after two engineer misses the orchestrator ran the full suite itself "in a memory-capped scope" and read the kernel OOM dump to find the cause. The result was useful, but `docs/team/orchestrator.md` says "do not ... test yourself". The kit has no sanctioned way to diagnose a miss (see P9).
- Proposed kit change: `docs/team/orchestrator.md` "Decisions at each edge": say that an escalation for returns needs the count from the rule, with the exact count in the comment, and that a miss pair may be diagnosed read-only (journal, `git log`, a capped test run) and the finding goes into the escalation comment. 
- Kit issue: none.

### P5. Generated files make claims that are false in a plugin project; the stage review reports them again and again, and the project pays a full cycle for each

- Evidence, from the prompt audit in 7 of 9 stage reviews ([#2](https://github.com/Lighfe/quack-rl/issues/2), [#18](https://github.com/Lighfe/quack-rl/issues/18), [#26](https://github.com/Lighfe/quack-rl/issues/26), [#35](https://github.com/Lighfe/quack-rl/issues/35), [#40](https://github.com/Lighfe/quack-rl/issues/40), [#56](https://github.com/Lighfe/quack-rl/issues/56), [#69](https://github.com/Lighfe/quack-rl/issues/69), [#74](https://github.com/Lighfe/quack-rl/issues/74), [#77](https://github.com/Lighfe/quack-rl/issues/77)). The kit templates still contain these false or dangling statements (counted in `plugin/templates/`):
  - `AGENTS.md.tmpl`: "`.claude/skills` is a symlink to `.agents/skills`" (in quack-rl `.claude/skills/` is a real folder with one link inside); "Subagent definitions go to `.claude/agents/`" (the folder does not exist; the agents come from the plugin).
  - `docs/process.md` (2 sites), `docs/team/pm.md`, `docs/team/orchestrator.md`, `docs/checks/hook-activation.md`: cite `docs/specs/agent-graph-kit.md`, which only the kit repo has. `docs/process.md` also cites `docs/research/` and `.claude/agents/planner.md`.
  - `docs/team/pm.md` (3), `docs/team/planner.md`, `docs/checks/hook-activation.md`: cite a README subsection "Auto mode allow entries" and "entry 3", which a plugin project does not have.
  - `docs/process.md`, `docs/team/pm.md` (4), `docs/team/planner.md`: `QA_SANDBOX` in `scripts/qa-codex`; the file is a two-line wrapper and holds no such setting.
  - `.claude/hooks/` is named in 13 places; hooks and agents live in the plugin.
  - `docs/team/planner.md` Doc drift: fact tests `tests/test_doc_paths.py` and `tests/test_spec_citations.py` (only the kit repo has them). Reported "could not run" in three reviews in a row (#18, #26, #35) before the owner decided to remove the part ([#29](https://github.com/Lighfe/quack-rl/issues/29)).
- Cost in quack-rl: seven task issues (six listed here, plus #30) went through the full PM, engineer, QA cycle only to edit kit copies: [#23](https://github.com/Lighfe/quack-rl/issues/23), [#29](https://github.com/Lighfe/quack-rl/issues/29), [#37](https://github.com/Lighfe/quack-rl/issues/37), [#38](https://github.com/Lighfe/quack-rl/issues/38), [#48](https://github.com/Lighfe/quack-rl/issues/48), [#54](https://github.com/Lighfe/quack-rl/issues/54), plus [#30](https://github.com/Lighfe/quack-rl/issues/30). Open ones: [#81](https://github.com/Lighfe/quack-rl/issues/81) (symlink claim), [#83](https://github.com/Lighfe/quack-rl/issues/83) (audit twice, test-run text). Each fix drifts the project from the plugin.
- Noise: the same low findings return in nearly every review (Lovable lane about 30 lines per engineer launch with no `frontend/`, the browser line in `qa-engineer.md`, the audit run twice, "migration-relative" Status line). The audit output was cut off in the reviews of #2, #35 and #74 ("I kept only the tail of its output"), so findings were lost.
- Root cause: the plugin ships the kit repo's own process documents as templates without a "plugin project" pass. This extends M6 of the earlier evaluation (no update route) with the cause behind it.
- Proposed kit change: one pass over `plugin/templates/` (build script `scripts/build_plugin.py` or a test) that checks every path, folder and file name mentioned in a template against what a plugin project has; a fact test in the kit repo for it. Lovable and browser text becomes a conditional include in `setup`. The stage review's prompt audit writes its output to a file and reads it in full, and lists a finding as "known" when an earlier review or an open issue already has it.
- Kit issue: partly. [#192](https://github.com/Lighfe/agent-graph-kit/issues/192) ("/setup writes a claim about .claude/agents/ that is false", open) covers one claim. [#185](https://github.com/Lighfe/agent-graph-kit/issues/185) (stale test-run duration, open) covers one more line. Fixed in the kit: fact-test skip (`b41ed71`), hook-activation document ([#178](https://github.com/Lighfe/agent-graph-kit/issues/178)). Not covered: the symlink claim, `QA_SANDBOX`, README/entry 3 references, spec and hooks references, noise, truncated audit output.

### P6. Drift between project copies and the plugin, and the owner as the update channel

- Evidence: the project edited `process.md` (6 sites), `pm.md`, `planner.md`, `orchestrator.md`, `qa-engineer.md`, `software-engineer.md`, `AGENTS.md` (local diff against the templates: 8 to 22 changed lines per file). The lock file `.agent-graph-kit.lock` still holds the pre-edit hashes and two deleted files. The owner copied new templates by hand once (`789fcc6` "Update agk kit documents") and edited the plugin cache copy of the launcher by hand ([#75](https://github.com/Lighfe/quack-rl/issues/75), `needs-owner`: `UV_SYNC` with `--group train`; the next plugin update overwrites it).
- Two more reasons for drift: three open `later` issues ask to edit role files "(drift from the plugin)" ([#80](https://github.com/Lighfe/quack-rl/issues/80), [#83](https://github.com/Lighfe/quack-rl/issues/83), [#81](https://github.com/Lighfe/quack-rl/issues/81)), and their acceptance criteria include "the owner has been told that this drifts". A criterion about telling the owner is not checkable by looking at a result.
- Root cause: no upstream path for a project to propose a change to a kit file, and no "local overrides" file. Extends M4, M6, M7. No kit issue exists for M4, M6, M7 or for this (search on titles and bodies of kit issues from #170 on found none).
- Proposed kit change: (a) the three drift fixes of the evaluation (M4, M6, M7); (b) a documented route "the project found a defect in a kit file": file the issue in the kit repo with a template, not a local follow-up; the planner's follow-up rule says "kit copy: file upstream" (the planner already knows which files are copies, it said "the same fix probably belongs in the plugin" in the reviews of #18, #26 and #35); (c) project-specific rules (like #30) go in `AGENTS.md`, not in a kit copy, so drift stays clean; (d) [#187](https://github.com/Lighfe/agent-graph-kit/issues/187) so that updates reach projects.
- Kit issue: [#187](https://github.com/Lighfe/agent-graph-kit/issues/187) ("bump the version with every plugin change", open) covers (d). Nothing for (a) to (c).

### P7. Labels and relations: mostly right, with a clear first-intake error and a few loose ends

- Confirmed: M1 (stage issue #2 had `ready` for 13 minutes) and M2 (no `later` on #3 to #14) both belong to the first intake only. All 5 later stages ([#18](https://github.com/Lighfe/quack-rl/issues/18), [#26](https://github.com/Lighfe/quack-rl/issues/26), [#35](https://github.com/Lighfe/quack-rl/issues/35) and later) filed their sub-issues with `later` and relabeled them in one minute at set-up. No later stage issue got `ready`. So the planner works as written after the first stage; the gap is that the first intake had no check (M1, M2 proposals stand).
- New: the stage review of #2 says "the cause is not known (set-up error at intake or a manual label)". The kit gives no way to find it, because label events show only the actor login, which is the same for all.
- New: parked follow-ups use "Needs #43 first" / "Needs #78 closed" as text ([#49](https://github.com/Lighfe/quack-rl/issues/49), [#85](https://github.com/Lighfe/quack-rl/issues/85), [#86](https://github.com/Lighfe/quack-rl/issues/86)) but have no native blocker link. The kit rule says blockers are native links. For parked issues this does no harm until promotion, then the loop picks them with no blocker.
- New: [#30](https://github.com/Lighfe/quack-rl/issues/30) was created with `ready` and no `later` (labeled `ready` at 16:06, same minute as creation). It is a grooming rule found during the run and filed by the orchestrator session. This bypasses "Follow-ups get the label `later`" in `docs/process.md`.
- New: [#17](https://github.com/Lighfe/quack-rl/issues/17) was closed after four days with label `later` and no comment; [#46](https://github.com/Lighfe/quack-rl/issues/46) and [#47](https://github.com/Lighfe/quack-rl/issues/47) were closed as not planned with one comment. Closing parked issues is an owner action the kit does not describe; no harm seen.
- Proposed kit change: the planner's Intake and Stage set-up end with a one-line label check (the earlier M1/M2 proposals); the PM, when it files a follow-up, adds native blockers for "Needs #n" lines; the orchestrator never adds `ready` to a follow-up it files.
- Kit issue: none for any of these (M1, M2 from the earlier evaluation also have no kit issue).

### P8. Issue quality: planner issues were not self-contained; the PM rewrote every one; follow-ups are thin

- Evidence: of 63 groomed issues, every one has at least one body edit after creation (the PM). 35 of 93 issue bodies name a plan or "Task N" ([#3](https://github.com/Lighfe/quack-rl/issues/3) to [#14](https://github.com/Lighfe/quack-rl/issues/14), [#41](https://github.com/Lighfe/quack-rl/issues/41) to [#45](https://github.com/Lighfe/quack-rl/issues/45), [#50](https://github.com/Lighfe/quack-rl/issues/50) to [#53](https://github.com/Lighfe/quack-rl/issues/53), [#59](https://github.com/Lighfe/quack-rl/issues/59) to [#68](https://github.com/Lighfe/quack-rl/issues/68)). The first version of [#5](https://github.com/Lighfe/quack-rl/issues/5) (read via edit history) had five loose criteria ("Every component named in the v1 ruleset is registered") and the constraint "Implement 'Task 3' of `docs/plans/...`: it has the interfaces, the code and the tests". `docs/process.md` says the plan is reached through the issue, not the other way. The PM rewrote it into nine concrete criteria and the engineer finished in one minute of launch time. So the PM does its job, but the planner's issues are plan pointers, which the earlier evaluation M3 ("task N") already noted.
- Current bodies are large: average 2.9 KB, [#72](https://github.com/Lighfe/quack-rl/issues/72) 7.7 KB and [#89](https://github.com/Lighfe/quack-rl/issues/89) 6.2 KB with 10 dense criteria. Big issues correlate with returns (#72 had 3, #24 had 3, #64 had 2).
- Parked follow-ups: [#85](https://github.com/Lighfe/quack-rl/issues/85) and [#86](https://github.com/Lighfe/quack-rl/issues/86) have the single criterion "To be groomed when the owner wants it". They have all four sections but no checkable criterion. They read fine on their own. [#79](https://github.com/Lighfe/quack-rl/issues/79) ("Rules v2 and a new game implementation") is a goal with "To be planned as an intake" as its criterion; it is an intake note, not a task.
- Quack-rl #80 ("Grooming makes criteria that depend on a GitHub fact self-contained") shows three gaps. (1) The follow-up proposes to edit the project's copy of `pm.md` and `software-engineer.md`; the kit is the right place, and the issue says "Out of scope: changes to the plugin itself". (2) Its second criterion ("The owner has been told ...") has no result to point at. (3) It points to "stage M2.6" and a comment of #74 for the reason; the reason is stated only through those links. Sister issue [#81](https://github.com/Lighfe/quack-rl/issues/81) says "line 26 at the time of the review", which a reader cannot reproduce later. Kit [#191](https://github.com/Lighfe/agent-graph-kit/issues/191) is itself a two-line stub that depends on a link to quack-rl #80 and says what should happen but not how to check it.
- Root cause: `docs/team/planner.md` Intake step 5 says "file each plan task as one issue in `docs/task-template.md` format" and has no "issue must stand without the plan" check; the PM definition of done says "an engineer who has never spoken to you could implement it from the issue and the documents it links", and the plan is such a document, so the PM accepts it. A rule for follow-ups (filed by PM, planner, orchestrator) does not ask for a checkable criterion or for the reason in words.
- Proposed kit change: (a) planner Intake: after filing, replace "Task N of plan" with the interface and the cases in the issue (the plan stays as a link for background only), and replace "task N" siblings with `#number` (M3); (b) the follow-up rule in `docs/team/pm.md` and `docs/team/planner.md`: the body states the reason in words (no "see comment ..."), has at least one criterion that a result can show, and a native blocker for any "needs #n"; (c) keep an issue under a size, or split it: criteria over about 10, or a body over about 5 KB, trigger "split or confirm" in the PM check.
- Kit issue: [#191](https://github.com/Lighfe/agent-graph-kit/issues/191) (stub, open) is the only one; it should absorb (a) to (c).

### P9. Compute and machine problems are invisible to the kit

- [#89](https://github.com/Lighfe/quack-rl/issues/89) "Dataset builder": the criteria demand a full build of at least 5,000 games into the user's machine. The builder kept every row in Python lists (`o.tolist()`, about 27 KB per row, 210,000 rows). One `python3` process reached about 11 GB; systemd-oomd killed VS Code twice. Both engineer launches ended with no result (not marked as outage by any hook). Wall time: engineer launch 1 at 07:28, escalation at 08:10, owner RESUME at 08:18 and 08:23 (two RESUME comments, the first empty). The PM was launched again at 08:23. The cause was found by hand from the kernel dump and posted in the "Escalation note" comment.
- Other signs: a fallback QA launch on [#63](https://github.com/Lighfe/quack-rl/issues/63) got no result for 9.8 hours (machine asleep; the retry passed in 2 minutes; one extra receipt remains). The loop stopped at run start on a dirty tree because marimo rewrote a notebook ([#56](https://github.com/Lighfe/quack-rl/issues/56) run notes). The test suite grew from 216 to 819 tests, and a full run takes 2.5 to 9 minutes (stage reviews of #69, #74), run by the engineer and again by every QA launch. The owner asked to switch later subagents to Sonnet because of the session limit (#2 run notes).
- Root cause: `docs/team/software-engineer.md` ("Test runs and background commands") has rules for time (foreground 600000 ms) and nothing for memory, disk or long jobs; `docs/team/pm.md` has no rule that a criterion asking for a large run names a resource bound. The hook has no "launch ended because the machine killed it" category, so an OOM looks like a plain miss and, after two, an owner escalation.
- Proposed kit change: (a) in the engineer file, run any job expected to take more than a minute or to build a large output under a memory cap and write the peak in `## Engineer: DONE` (for example `systemd-run --user --scope -p MemoryMax=...` where available); (b) in the PM file, a criterion that asks for a full-scale run also asks for a smaller smoke run as the check and a measured peak; (c) the orchestrator's escalation for two misses first reads the journal (read-only) and says the likely cause.
- Kit issue: partly. [#193](https://github.com/Lighfe/agent-graph-kit/issues/193) (open, raw idea) has an acceptance line "decision on compute monitoring" and names #89. The concrete rules (a) to (c) are not in it.

### P10. Miss recovery and the tool-problem path worked, with two soft spots

- Worked: the one miss on [#37](https://github.com/Lighfe/quack-rl/issues/37) was continued by a second engineer launch in 4 minutes with no owner. The `PM: WAITING` path on [#3](https://github.com/Lighfe/quack-rl/issues/3) (blocker in another repo) held the issue correctly. No `Launch not started` or outage receipts appeared.
- Soft spot 1: after `PM: WAITING` with a blocker in the kit repo, the stage stood still for 2.9 hours until the owner fixed the kit and the PM could run again (attempt 3). This is M5 of the earlier evaluation, confirmed. In total the first stage waited about 10 hours for `ready` plus 3 hours for the kit fix before the first sub-issue closed at 09:27, and then the other 11 closed in 2 hours.
- Soft spot 2: the same hour-scale stall appears for QA fallback ([#63](https://github.com/Lighfe/quack-rl/issues/63)). The kit has no wall-clock limit for a launch.
- Proposed kit change: a "launch idle for more than N minutes" note in the orchestrator's run notes (it already sees receipts); no new state.
- Kit issue: none.

### P11. Unverifiable-after-fix: engineer reruns for no code change

- Each of the seven `UNVERIFIABLE` outcomes caused (for #3, after the wait for the blocker) a PM launch and an engineer launch. Where the engineer had no code to change, the DONE comment says so (the kit rule allows it). I did not check each one. The kit rule is right (regroomed criteria need a DONE with a new range), but when the PM only rewords a criterion, the engineer step is a pure state-fact comment. Cost is small per case (engineer median 3 minutes); it is mostly a pattern that exists because of P2.
- Proposed kit change: none beyond P2; if P2 lands, the number of these cycles falls.
- Kit issue: none needed.

### P12. Guard false denies

- Run notes of [#31](https://github.com/Lighfe/quack-rl/issues/31) ("a read joined to `gh issue close 31`") and [#69](https://github.com/Lighfe/quack-rl/issues/69) ("G1 on a command that only mentioned the word") show two G1 denies on the orchestrator's own call; I hit the same hook in this review with a Python command that contained the text `qa-codex` in a pipe. Each false deny costs a retry; the hook message names the way around (quoted here-document).
- Kit issue: [#107](https://github.com/Lighfe/agent-graph-kit/issues/107) (closed) covered only issue bodies. No open issue for commands that merely contain the words. I did not test how common this is for the role agents; the run notes show it only for the orchestrator.

### P13. The stage plan did not cover its own spec (one occurrence, serious)

- [#26](https://github.com/Lighfe/quack-rl/issues/26) "M2.1 bots and balance": the stage review said "Met as tooling". An addendum by the orchestrator session, at the owner's request, found four spec parts with no issue (the full balance run [#31](https://github.com/Lighfe/quack-rl/issues/31), a realistic baseline maximum [#32](https://github.com/Lighfe/quack-rl/issues/32), speed measurement [#33](https://github.com/Lighfe/quack-rl/issues/33), a field shortcut [#34](https://github.com/Lighfe/quack-rl/issues/34)). They became the next stage.
- Root cause: `docs/team/planner.md` Intake has no "each spec requirement has an issue" step, and the stage review checks "purpose met" and does not compare the spec section by section.
- Proposed kit change: Intake step 5: a short coverage table in the stage issue's Background (spec section to issue); the stage review reads that table and the spec and names gaps.
- Kit issue: none.

## 3. Time and token cost

What the issues can show (launch receipt to result comment; wall time of agent runs; sums over all 93 issues):

| Role | Launches | Time launch to result | Note |
| --- | --- | --- | --- |
| Engineer, first launch | 63 | 543 min (mean 8.6) | the main work |
| Engineer, after QA FAIL | 22 | 175 min | rework: 23 percent of engineer time |
| Engineer, after regroom or BLOCKED | 15 | 41 min | mostly no code change |
| QA, first run (Codex or fallback) | 62 | 193 min | |
| QA, after a DONE (re-run) | 31 | 141 min | after FAIL or regroom |
| QA, fallback after `UNAVAILABLE` | 16 | 143 min | the cost of P1 |
| PM | 78 | 66 min (median 0.6) | cheapest role |
| Planner (stage review) | 9 | 64 min | |

Total about 1,370 agent-minutes in the issues (about 23 hours), plus idle gaps.

- Engineer plus QA make up 93 percent of agent time. The PM is cheap per launch, and it prevents a lot: every groomed issue got its body edited.
- Rework (engineer after FAIL, QA re-runs, fallback after `UNAVAILABLE`, PM and engineer after UNVERIFIABLE) is about 500 minutes: over a third of all agent time.
- Most expensive single issues by launches and comments: [#72](https://github.com/Lighfe/quack-rl/issues/72) (42 KB of text; 4 engineer launches; 3 returns; 2 owner decisions), [#24](https://github.com/Lighfe/quack-rl/issues/24) (21 comments, 3 returns, 2 escalations), [#64](https://github.com/Lighfe/quack-rl/issues/64) (2 FAILs), [#14](https://github.com/Lighfe/quack-rl/issues/14), [#67](https://github.com/Lighfe/quack-rl/issues/67) (5 QA launches, 2 UNAVAILABLE, 1 UNVERIFIABLE), [#68](https://github.com/Lighfe/quack-rl/issues/68), [#31](https://github.com/Lighfe/quack-rl/issues/31) (22 comments).
- Longest waits (not compute): about 10 hours between the stage setup and `ready` for the first stage; 2.9 hours for the kit fix on #3; 9.8 hours on #63 (machine asleep); 1.2 hours for an owner decision on #31. Other owner waits were 3 to 46 minutes. The owner was close to the loop.
- The simple M1 issues took 3 to 6 minutes of wall time each (#4 to #13), including three agents. That shows the loop is cheap when issues are small and criteria are checkable.

What cannot be measured from issues alone:

- Tokens per role, cache creation and cache read, the model per launch (the owner moved later subagents to Sonnet), and the cost of the orchestrator session itself. [#190](https://github.com/Lighfe/agent-graph-kit/issues/190) and [#193](https://github.com/Lighfe/agent-graph-kit/issues/193) start from this gap and are right to "measure first".
- Time inside a launch (waiting for a full test run, thinking, tool calls) and the time between a result and the next receipt.
- How much of the Codex QA budget each issue used. The usage limit hit often, but the issue data gives no tokens per Codex run. [#189](https://github.com/Lighfe/agent-graph-kit/issues/189) asks for exactly that.
- Whether the three big issues (#24, #31, #72) would have run shorter with different criteria. The comments say yes, but it is a judgement.

## 4. Open quack-rl issues with label `later` where a kit fix exists

Honest result: no open `later` issue of quack-rl is fully fixed in the kit today. These are the ones with a related kit issue or commit. The comments are proposals, not posted.

| quack-rl issue | Kit fix or kit issue | Status of the kit side | Proposed info comment |
| --- | --- | --- | --- |
| [#80](https://github.com/Lighfe/quack-rl/issues/80) Grooming makes criteria that depend on a GitHub fact self-contained | [agent-graph-kit#191](https://github.com/Lighfe/agent-graph-kit/issues/191) "Self-contained github issues" | open, stub, not fixed | "The kit repo has an issue for this (Lighfe/agent-graph-kit#191). A fix in the kit makes the rule available to every project and avoids drift in this project's copies of `pm.md` and `software-engineer.md`. Suggest to keep this issue parked until that issue is groomed, then close it as not planned." |
| [#81](https://github.com/Lighfe/quack-rl/issues/81) Fix the `.claude/skills` symlink claim in AGENTS.md | none; related [agent-graph-kit#192](https://github.com/Lighfe/agent-graph-kit/issues/192) (same kind of claim for `.claude/agents/`) | open; the kit template `plugin/templates/AGENTS.md.tmpl` still has the symlink sentence and no kit issue covers it | "The sentence comes from the kit template. Lighfe/agent-graph-kit#192 covers the same kind of claim for `.claude/agents/`; the symlink sentence is not covered yet. Fix it once in the kit rather than here." (File a kit issue first.) |
| [#83](https://github.com/Lighfe/quack-rl/issues/83) Shorten the prompt audit and test-run text in the role files | [agent-graph-kit#185](https://github.com/Lighfe/agent-graph-kit/issues/185) "Engineer file: drop the test-run duration that goes stale" | open; covers only the duration line, not the double audit run | "Part of this is open in the kit: Lighfe/agent-graph-kit#185 (the stale test-run duration). The double audit run is not covered. Suggest to wait for the kit change and re-run `/agk:drift` before editing the local copy." |
| [#75](https://github.com/Lighfe/quack-rl/issues/75) Keep the qa-codex launcher train-group install across plugin updates (`needs-owner`) | [agent-graph-kit#187](https://github.com/Lighfe/agent-graph-kit/issues/187) (version bump so updates reach projects); fix [agent-graph-kit#47](https://github.com/Lighfe/agent-graph-kit/issues/47) covered only `uv sync --frozen` | no kit issue for optional dependency groups | "Lighfe/agent-graph-kit#47 added `uv sync --frozen` to the QA pre-step, not optional groups like `train`. There is no kit issue for groups yet. Proposed: file one in the kit; until then the hand edit of the cached launcher stays and #187 (versioned updates) will overwrite it on the next plugin update." |
| [#82](https://github.com/Lighfe/quack-rl/issues/82) and [#93](https://github.com/Lighfe/quack-rl/issues/93) Marimo skill fixes | none (the marimo skill is a vendored upstream skill, `marimo-team/skills`); related [agent-graph-kit#188](https://github.com/Lighfe/agent-graph-kit/issues/188) "Integrate marimo" | project-specific | none needed; the fix belongs upstream at `marimo-team/skills` |

Already fixed in the kit, with the matching quack-rl issue already closed locally (no action needed, noted so the duplication is visible): fact tests skipped when absent (kit commit `b41ed71`; quack-rl [#29](https://github.com/Lighfe/quack-rl/issues/29) removed the part by hand), hook-activation document rewritten (kit [#178](https://github.com/Lighfe/agent-graph-kit/issues/178); quack-rl [#48](https://github.com/Lighfe/quack-rl/issues/48)), and `uv sync --frozen` in the QA pre-step (kit [#47](https://github.com/Lighfe/agent-graph-kit/issues/47); quack-rl [#3](https://github.com/Lighfe/quack-rl/issues/3) passed after it).

Issues the project filed against the kit: only two, both by the owner in the kit repo: [#191](https://github.com/Lighfe/agent-graph-kit/issues/191) and [#192](https://github.com/Lighfe/agent-graph-kit/issues/192). The quack-rl issues that mention the kit ([#23](https://github.com/Lighfe/quack-rl/issues/23), [#29](https://github.com/Lighfe/quack-rl/issues/29), [#37](https://github.com/Lighfe/quack-rl/issues/37), [#38](https://github.com/Lighfe/quack-rl/issues/38), [#48](https://github.com/Lighfe/quack-rl/issues/48), [#54](https://github.com/Lighfe/quack-rl/issues/54), [#75](https://github.com/Lighfe/quack-rl/issues/75), [#80](https://github.com/Lighfe/quack-rl/issues/80), [#81](https://github.com/Lighfe/quack-rl/issues/81), [#83](https://github.com/Lighfe/quack-rl/issues/83)) are local fixes of kit files, not kit issues. The seven findings of the earlier evaluation (M1 to M7) still have no kit issue.

## 5. Things that worked well

- QA caught real defects: 24 FAILs on 19 issues, and all 61 QA'd issues ended in PASS. Escalations stopped at 3 returns.
- The PM rewrote every planned issue into checkable criteria in about a minute, and added edge cases (for example the `UnknownComponent` subclass case on #5).
- The tool-problem path worked end to end on [#3](https://github.com/Lighfe/quack-rl/issues/3): UNVERIFIABLE, PM links the kit blocker, WAITING, owner fixes the kit, regroom, PASS.
- Miss recovery without the owner worked on [#37](https://github.com/Lighfe/quack-rl/issues/37). No outage receipts were needed and no secrets appear in any comment.
- The fallback QA kept the loop going through 15 Codex limit hits.
- After the first stage, the planner's labels were right every time (`later` at filing, one relabel at confirmation, no `ready` on a stage issue).
- The stage reviews are strong: each has run notes with counts, a doc-drift section, a plain recommendation, and several found the real cause (the `game_id` problem, the QA world limits). The addendum on #26 shows how a spec gap was found after the fact.
- Hook receipts made the history readable: every launch has an attempt number and an agent name.
- The owner reacted in minutes at every escalation and wrote clear decisions (for example the rewritten criterion on #31).

## Proposed kit issues (none filed; for the owner)

1. PM: write criteria checkable in QA's world, and check the premise (P2, P3). Extend [#191](https://github.com/Lighfe/agent-graph-kit/issues/191).
2. Codex QA: remember the usage-limit reset time and optional dependency groups (P1, P2). Extend [#189](https://github.com/Lighfe/agent-graph-kit/issues/189), new issue for groups.
3. Templates: a path and name check of every template against a plugin project, plus "known findings" and full-output rule for the prompt audit (P5, P6). Extend [#192](https://github.com/Lighfe/agent-graph-kit/issues/192).
4. A kit-defect route from a project to the kit repo, and project rules in `AGENTS.md` instead of kit copies (P6).
5. Resource rules for large jobs in the engineer and PM files, and read-only diagnosis of two misses (P4, P9). Extend [#193](https://github.com/Lighfe/agent-graph-kit/issues/193).
6. Planner: coverage table spec to issues, issues that stand without the plan, native blockers for "needs #n" (P7, P8, P13).
7. The earlier findings M1 to M7, still unfiled.
