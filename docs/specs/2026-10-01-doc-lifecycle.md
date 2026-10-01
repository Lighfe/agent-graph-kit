# How long each kind of agent-readable doc lives

Issue: #84. Date: 2026-10-01.
Status: proposal, owner decides
Inputs: the research report `docs/research/big-picture-and-lean-docs.md` (sections "3. Problem B: lean and true agent-readable docs", "6.1 Doc audit, sampled", "7. Patterns" and "9. Open questions for the adaptation step") and the spike report `docs/research/spike-prompt-audit.md` (#81).

This proposal says which agent-readable docs of this kit are written once and then put away, which are kept up to date, when a doc is archived or deleted, and what keeps the living ones true. Nothing here moves, archives, splits or deletes a doc, and nothing adds a check: that is the follow-up work at the end (issue #87, label `later`). This proposal replaces issue #16 ("Doc decluttering (librarian)") as the place where this is decided. The owner decides.

## Summary of the recommendation

- **Four lifecycles, and the folder tells which one a doc has.** Instruction files (AGENTS.md, process, roles, subagents, template, skills, README) and one living behavior spec are kept up to date. Plans, proposals and one-time check runbooks are archived after use. Research reports and the archive are written once. Reviews and owner notes are deleted once their content is in issues.
- **The v1 spec is split.** The parts that the code implements and that no other file states (the principles, the launch contract with the hook guarantees, the `qa-codex` contract) become one living behavior spec without a date in its name. The full v1 spec, as it is, moves to `docs/archive/` as the record of the v1 design.
- **Code points to names, not numbers.** The about 44 code lines that cite "spec 5.3" and the like cite a heading anchor of the living spec or a guarantee ID (G1 to G9) instead, and a test checks that each cited anchor exists.
- **Two layers find drift.** On every change, tests in the normal test command check facts (named paths exist, cited anchors exist, size caps). At the end of each stage, the orchestrator runs `/doctor prompt-audit` twice (default scope and `docs/`) and files the findings as one parked issue. Updates go through the PM, engineer and QA loop; archive and delete are the owner's call.
- **Agents read the put-away folders only when pointed to.** The rule that exists today for old reviews extends to `docs/archive/`, `docs/plans/`, `docs/research/`, `docs/reviews/`, `docs/owner-notes/` and `docs/references/`.
- **Review output lives in the issues** that its findings became; the review file is deleted from the tree when every finding has a decision.
- **No scheduled doc agent yet.** A scheduled agent that only opens issues fits "hooks check facts only", but the stage-end audit comes first.
- **Size limits stay soft except where a tool cuts text off.** The one hard cap is the Codex 32 KiB limit for the combined `AGENTS.md`; line budgets are reported, not enforced; a new kind of agent-facing file needs the owner.

## The lifecycle of each kind of doc

The four lifecycles:

- **Written once:** the doc is not edited after it is done. It stays where it is. Agents read it only when pointed to.
- **Kept up to date:** the doc says how things are now. A change that makes it false updates it in the same commit.
- **Archived after use:** the doc is input for one step (intake, one decision, one run). After that step it moves unchanged to `docs/archive/`.
- **Deleted:** the doc is removed from the tree once its content lives elsewhere (issues). Git history keeps it.

| Kind of doc | Where | Lifecycle | Reason |
|---|---|---|---|
| AGENTS.md and CLAUDE.md | repo root | kept up to date | Loaded into every session; a stale line is followed (research 3.3: instructions in context files are well followed) |
| Process | `docs/process.md` | kept up to date | The main description of how work is organized (principle "prose guides, hooks check") |
| Role files | `docs/team/` | kept up to date | Each launch of a role reads its file; it must match the hooks and the process |
| Subagent definitions | `.claude/agents/` | kept up to date | Read by Claude Code at each launch; they only point to the role files, so they change rarely |
| Task template | `docs/task-template.md` | kept up to date | The PM grooms every issue into this form; the hooks read markers that the form defines |
| Skills | `.agents/skills/` | kept up to date | Loaded by description and run as code; the text must match the script it runs |
| README | `README.md` | kept up to date | The set-up steps for a person who adopts the kit; a wrong step breaks the set-up |
| Behavior specs | `docs/specs/`, one living file without a date in its name | kept up to date | The one place that says how the hooks and `qa-codex` behave now; every source in research 3.1 keeps its behavior spec living |
| Proposals | `docs/specs/<date>-<topic>.md` with `Status: proposal, owner decides` (this file, `docs/specs/2026-10-01-big-picture.md`) | archived after use | Input for one owner decision and one set of edits; once the edits are issues, the proposal is history |
| Plans | `docs/plans/` | archived after use | Input for intake only; once the tasks are issues, the issues hold the work (research 3.1: execution plans are one-off in every source) |
| Research and spike reports | `docs/research/` | written once | Dated evidence that issues and proposals cite; a later finding gets a new report, not an edit |
| Check docs | `docs/checks/` | archived after use | A one-time runbook for one acceptance run (spike finding F6: `docs/checks/hook-activation.md` is tied to the closed issue #7) |
| Reviews | `docs/reviews/` | deleted | Review data lives as long as its findings are open; the findings then live in issues (question on review output below) |
| Archive | `docs/archive/` | written once | The record of finished plans, proposals, runbooks and the v1 spec; nothing in it is edited |
| Owner notes | `docs/owner-notes/` | deleted | The owner's questions for the team; once each point is in an issue or a proposal, the note has no further reader. The owner deletes it |
| Reference summaries (not on the issue's list; for completeness) | `docs/references/summaries/` | written once | Summaries of course articles, read only when an issue points to one |

## Is the v1 spec a plan, a description of how the system behaves, or a mix that should be split?

Recommended: **a mix; split it into one living behavior spec and an archived v1 record**, owner decides.

The v1 spec (`docs/specs/2026-09-25-agent-graph-kit-v1.md`, 490 lines) holds three kinds of text:

- **How the system behaves now, and stated nowhere else:** the principles (section "2. Principles"), the launch contract and hook guarantees (section "5. Launch contract and hook guarantees": guarded calls, launch line, launch comments, checks G1 to G9, result markers, failure behavior, settings protection) and the `qa-codex` contract (section "6. Codex QA launcher"). The hooks and `qa-codex` implement this text, and the code cites it.
- **How the system behaves now, but also stated in a living file:** QA behavior (section 7, also in `docs/team/qa-engineer.md` and `docs/team/pm.md`), the Codex review skill (section 8, also in `.agents/skills/codex-review/SKILL.md`), the Lovable lane (section 9, also in `docs/team/software-engineer.md` and the README) and the `later` label (section 10, also in `docs/process.md`).
- **Plan and history:** scope and "Not in v1" (section 3, whose items are also open issues with the label `later`), the file list (section 11), tests, CI and the end-to-end proof (section 12) and the spikes (section 13).

The split:

1. A new living file `docs/specs/agent-graph-kit.md` (no date in the name, because it is not a snapshot) holds the principles, the launch contract and the `qa-codex` contract, taken over from the v1 spec with stable headings. Nothing else.
2. Before that, each behavior statement of sections 7 to 10 is checked against its living file; a statement that is missing there is moved there, not into the new spec.
3. The full v1 spec moves unchanged to `docs/archive/`, as the record of the v1 design.
4. An issue that changes the launch contract or `qa-codex` names `docs/specs/agent-graph-kit.md` in its files and has a criterion for the changed text. The issue holds the change and its reason; the living spec holds the state after the change. These are not two copies of the same data: one lives as long as the change, the other as long as the behavior (research pattern P9, "storage lifetime matches data lifetime").

Rejected options:

- **It is a plan; archive the whole spec after intake:** no source in the research does this for a behavior spec (research section 10), and the hook guarantees would then live only in the code and in closed issues.
- **It is a behavior spec; keep it living as it is:** sections 7 to 10 would stay a second copy of the role files, the skill and the process, which is the double bookkeeping the owner reported (research 6.1, finding 1: 18 of 19 spec edits after Task 5 changed another file in the same commit); sections 3, 11, 12 and 13 would keep rotting.
- **Move the contract into the code's docstrings and keep no spec:** the PM grooms hook issues from prose, and the contract (what each guarantee allows and denies) is longer than a docstring; it also loses the single place that the principles live.

Reason: the research found execution plans one-off and behavior specs living in every source that has them. The v1 spec is both, so the split follows the evidence, and it keeps only the part that has no other living copy.

## If the spec is split, what replaces the code references to spec section numbers?

Recommended: **heading anchors of the living spec and the guarantee IDs, checked by a test**, owner decides.

Today about 44 lines in `.claude/hooks/`, `scripts/`, `tests/` and `.agents/skills/codex-review/review.py` cite section numbers such as "spec 5.3" or "spec 6.2" (the spike counted 42 at its commit; the README cites a few more). Section numbers change when the spec is split or renumbered.

The replacement:

- A code comment cites the living spec by file and heading anchor, for example `docs/specs/agent-graph-kit.md#launch-comments`, or by a guarantee ID that the spec defines, for example `G7`.
- The headings of the living spec are stable names; a heading is renamed only together with every citation.
- A test in the normal test command collects every cited anchor and guarantee ID from the code and fails when the living spec has no such heading or ID. This is a fact check on every change.
- The README's citations ("spec 6.2", "spec 9.1", "spec 5.9", "spec 6.1") are replaced the same way.

Rejected options:

- **Keep the section numbers and point them at the archived v1 spec:** the code would send readers to a frozen document that agents should not read unless pointed to, and to text that may no longer be true.
- **Remove the references:** a reader of `guard.py` would lose the pointer to the rule a check implements.
- **Cite issue numbers instead:** an issue says why a change was made, not how the system behaves now; several issues changed the same guarantee.

Reason: names survive a split and a renumbering, and a test can check that each name still exists, without judgment.

## For each kind that is kept up to date: which check finds drift, and who decides to update, archive or delete?

Recommended: **a fact check on every change plus a `/doctor prompt-audit` run at the end of each stage**, owner decides.

Two layers, as in the strongest reports of the research (section 3.2):

- **On every change (facts, in the test command and CI):** a new test file checks (a) that every repo path named in an agent-facing file exists, (b) that every anchor or guarantee ID that the code cites exists in the living spec, (c) the size cap (question on limits below). No judgment, so it fits the principle "facts only".
- **At the end of each stage (on demand, by the orchestrator):** when a stage ends (as proposed in `docs/specs/2026-10-01-big-picture.md`), the orchestrator runs `claude -p "/doctor prompt-audit"` and `claude -p "/doctor prompt-audit docs/"` and files all findings as one issue with the label `later` and a `Source:` line naming the commit. The audit changes no file. No scheduled agent (question on a scheduled agent below).

**Is `/doctor prompt-audit` one of the checks?** Yes, for some kinds. The spike report `docs/research/spike-prompt-audit.md` (#81) ran it on this repo:

- It covers AGENTS.md, CLAUDE.md, the subagent definitions and the skill text (`SKILL.md`) in its default scope, and `docs/process.md`, `docs/task-template.md`, the role files and `docs/checks/` when pointed at `docs/`. The `docs/` run found a real conflict (`docs/process.md` says QA "only outputs PASS or FAIL", while the QA role has four verdicts).
- It does not cover: plans, specs (also not the living behavior spec), research and reviews (it skips them on purpose as "not instructions"); code references to doc sections (they are in `.py` files and scripts, which it does not audit; it found 0 of about 44); the README (it read it only to check facts); skill code such as `review.py`; duplicates between docs and GitHub issues; and gaps between the text and practice. From inside the loop it also reads no GitHub issues and no git history without approval.

Per kind:

| Kind (kept up to date) | On every change | At stage end | Not covered by any check |
|---|---|---|---|
| AGENTS.md and CLAUDE.md | paths exist; size cap | prompt-audit, default scope | gaps between text and practice |
| `docs/process.md` | paths exist | prompt-audit, `docs/` | gaps between text and practice |
| Role files | paths exist | prompt-audit, `docs/` | same |
| Subagent definitions | paths exist (the role file they point to) | prompt-audit, default scope | – |
| `docs/task-template.md` | – | prompt-audit, `docs/` | whether the hooks parse what the template asks for (the hook tests cover the markers) |
| Skills | paths exist | prompt-audit, default scope (`SKILL.md` only) | skill code against its text |
| README | paths exist | – | whether the set-up steps still work (checked when a repo adopts the kit, #15) |
| Living behavior spec | cited anchors and IDs exist | – | whether the text matches what the hooks do; the PM checks this while grooming any issue that touches `.claude/hooks/` or `scripts/qa-codex` |

Who decides:

- **Update:** the PM, while grooming, puts the doc into the issue's files and criteria; the engineer edits it in the same commit as the change; QA checks it. A finding from the stage-end audit is a parked issue that goes through the same loop once it is promoted.
- **Archive or delete:** the owner. An agent may propose it (in a finding or a follow-up issue) but never moves or deletes a doc on its own; nobody in the research reported an agent that deletes docs on its own (research 3.2).
- **Gaps between text and practice:** no check finds them; the owner reports them, as in research 6.1 finding 7.

Rejected options:

- **Only on demand, when the owner asks:** research 3.2 found that nobody reported a one-time clean-up that stayed clean.
- **A scheduled audit from the start:** see the question on a scheduled agent below; the stage end is a natural point that the loop already passes.
- **A hook that denies a call when a doc is stale:** staleness is a judgment, so a hook on it breaks "facts only".
- **One librarian role (#16):** no source in the research solved drift with one role; the checks above need no new role file.

Reason: the fact layer catches the breaks that are cheap to find (paths, anchors, size); the audit catches conflicts between instruction files, which the facts cannot see; both are cheap, and the audit's blind spots are covered by the PM's grooming and the owner.

## Which folders should agents not read unless the owner points to them?

Recommended: **`docs/archive/`, `docs/plans/`, `docs/research/`, `docs/reviews/`, `docs/owner-notes/` and `docs/references/`; "pointed to" means by the owner or by the issue being worked on**, owner decides.

Today `docs/process.md` has this rule only for old reviews. The extended rule is one line in the work rules of `docs/process.md`:

- Do not read `docs/archive/`, `docs/plans/`, `docs/research/`, `docs/reviews/`, `docs/owner-notes/` or `docs/references/` unless the owner or the issue you work on points to a file there.

The issue clause is needed because issues cite research and plans as inputs (this issue cites two research reports). `docs/specs/` stays readable: it holds the living behavior spec and open proposals only, after the old ones are archived.

Rejected options:

- **Only old reviews, as today:** it leaves 1,944 lines of research, the 1,337-line plan and the archive in the agent's path (research 6.1, finding 8).
- **A hook or a permission rule that denies reads of these folders:** reads are not handoff calls, and the principle "prose guides, hooks check" keeps hooks to handoff calls; a deny would also block the issue clause.
- **Move these folders out of the repo:** research and the archive are cited by issues and proposals in this public repo; moving them breaks the links.

Reason: agents read what is put in front of them (research 3.3: 60.5 % of doc reads were agent-facing files), and stale text that is read gets followed. One line keeps the put-away folders out of the default path without a new file.

## Where does review output live once its findings are issues?

Recommended: **in the issues; the review file is deleted from the tree when every finding has a decision**, owner decides.

How it works:

- The `codex-review` skill keeps writing `docs/reviews/<date>-<topic>-codex-review.md`, as today. Each finding starts with `Decision: open`.
- Whoever works on the review decides each finding (taken, partly taken, rejected). A taken finding that needs more work becomes an issue whose body holds the finding text and a `Source:` line with a link to the review file at the commit that added it (a permalink with the SHA, which keeps working after the file is deleted).
- When no finding is `open`, the review file is deleted in the commit that records the last decision. Git history keeps it.

Rejected options:

- **Keep every review file in `docs/reviews/`, as today:** the folder grows by one file per review (12 files today), and the findings are already in issues or in the reviewed change.
- **Move it to `docs/archive/`:** the archive would grow by one file per review instead.
- **Post the review as an issue comment and write no file:** a review before intake (of a spec or plan) has no issue to comment on, and the skill would need a second output path.

Reason: review data lives as long as its open findings (research pattern P9); the research reports a permanent file for short-lived data as a failure that needed a sweeper (GSD Core, research 3.4).

## Does a scheduled agent that only opens issues or pull requests fit "hooks check facts only"?

Recommended: **yes, it fits; but start with the stage-end audit and add a scheduled agent only when those runs show a need. If one is added, it opens issues, not pull requests**, owner decides.

The principle "facts only" says what may block a call: hooks check facts, and no judgment of a model blocks anything. A scheduled agent that opens an issue or a pull request blocks nothing; its judgment becomes an input that the PM grooms and the owner promotes, like a review finding. So it does not break the principle.

Why issues, not pull requests: a pull request would change docs outside the PM, engineer and QA loop and outside the hooks, which guard the loop's calls on issues. An issue with the label `later` and a `Source:` line enters the loop like any follow-up.

Why not now: the stage-end audit (question on drift checks above) runs at a point the loop already passes, with no schedule, no extra credentials and no new file. A scheduled run (for example a Claude Code routine) adds a job that runs when no stage ended and nothing changed.

Rejected options:

- **A scheduled agent that opens pull requests with auto-merge (the GitHub Next doc updater):** changes reach `main` without the loop and without QA; even there, 2 of 59 updater and 15 of 103 unbloat pull requests were not merged (research P7).
- **A scheduled agent now:** costs a schedule and runs before the stage-end audit has shown what it finds.
- **No automated check at all:** a one-time clean-up was never reported to stay clean (research 3.2).

Reason: the principle restricts what blocks, not what proposes. Proposing through issues keeps every doc change inside the guarded loop.

## How strict should the limits on file size and number of files be, given that one study found longer files cost more tokens but did not lower adherence?

Recommended: **soft budgets for size, one hard cap where a tool cuts text off, and a firm limit on the number of kinds of agent-facing files**, owner decides.

The evidence (research 3.3): Claude Code's docs advise under 200 lines per CLAUDE.md; Codex stops adding `AGENTS.md` text at 32 KiB, with no warning; Gloaguen et al. found that context files cost over 20 % more inference and that overviews do not help; McMillan found no effect of file size (25 to 500 lines) on adherence, for one trivial instruction. Together: length costs tokens and relevance, and a silent cut-off loses text.

The limits:

- **Hard cap (test fails):** the combined size of `AGENTS.md` (and what it imports) stays under 32 KiB, because Codex silently drops what is past it.
- **Soft budgets (reported, do not fail):** AGENTS.md and CLAUDE.md under 200 lines; each role file and `docs/process.md` under 200 lines. The stage-end report lists the line counts. Today all are under it (AGENTS.md 55, `docs/process.md` 72, the largest role file `docs/team/orchestrator.md` 135).
- **Number of files:** the kinds in the lifecycle table above are the agent-facing kinds. A new kind, or a new always-loaded file, needs the owner (principle "few files"). Within a kind (one more skill, one more role) the PM may add a file when an issue needs it.
- **Overviews:** no file holds a layout or architecture overview that an agent can read from the code (Gloaguen; Claude Code's `/doctor` trim check proposes cutting such text).

Rejected options:

- **Hard line caps on every agent-facing file:** the evidence does not show that length lowers adherence, and a failing cap needs an escape hatch, which GSD Core reports became its own drift problem (research 3.4).
- **No limits:** the 32 KiB cut-off is silent, and cost grows with every line in every session.

Reason: the one limit with a proven failure (silent cut-off) is a hard fact check; the rest is cost, which a budget and the owner's view of the stage report handle without false alarms.

## Fit with the kit principles

From the v1 spec, section "2. Principles":

- **Prose guides, hooks check.** The lifecycle rules and the reading rule are prose in `docs/process.md`. No hook is added; the new checks are tests.
- **Facts only.** The every-change checks are facts (paths, anchors, a byte count). The audit and any scheduled agent only propose, through issues.
- **State lives on the issue.** Review findings and audit findings live in issues; the review file and the owner note are deleted once that is so.
- **Few files.** The proposal adds one living spec and removes, from the default path, the v1 spec, the plan, the proposals, the runbook, the reviews and the owner notes. No new agent-facing kind.
- **No secrets.** Unchanged.

In another repo that adopts the kit (#14, #15): the lifecycle table and the reading rule ship in `docs/process.md`; the fact-check test ships with the kit's tests and reads the adopting repo's own agent-facing files; the stage-end audit needs only `claude -p`.

## Sources

Besides the research report and the spike report:

- Kit spec v1, `docs/specs/2026-09-25-agent-graph-kit-v1.md`, read at commit `d64d110` on 2026-10-01.
- Sibling proposal, `docs/specs/2026-10-01-big-picture.md` (#83), read at commit `d64d110` on 2026-10-01.
- Process, `docs/process.md`, and the role files in `docs/team/`, read at commit `d64d110` on 2026-10-01.
- Codex review skill, `.agents/skills/codex-review/SKILL.md`, read at commit `d64d110` on 2026-10-01.
- Owner note, `docs/owner-notes/20260926-note.md`, read at commit `d64d110` on 2026-10-01.
- Code references to spec sections: `grep` over `.claude/hooks/`, `scripts/`, `tests/` and `.agents/` at commit `d64d110`.

## Follow-up work

If the owner accepts the proposal, it needs this work. These are items in this file, not issues; most of them belong to issue #87 ("Carry out the chosen doc lifecycle", label `later`).

- **Split the v1 spec:** check sections 7 to 10 against their living files and move missing statements there; create `docs/specs/agent-graph-kit.md` with the principles, the launch contract and the `qa-codex` contract under stable headings; move the full v1 spec unchanged to `docs/archive/`.
- **Replace the section-number citations** in `.claude/hooks/`, `scripts/`, `tests/`, `.agents/skills/codex-review/review.py` and the README with anchors or guarantee IDs.
- **Fact-check test:** one new test file for named paths, cited anchors and IDs, and the 32 KiB cap for `AGENTS.md`; line counts reported, not enforced.
- **`docs/process.md`:** the lifecycle table in short form; replace the reviews-only reading rule with the folder list; the rule that an issue changing the contract names the living spec.
- **`docs/team/orchestrator.md`:** run the two prompt-audit commands at stage end and file one parked issue; list line counts in the stage report (depends on the stage model of #83).
- **`docs/team/pm.md`:** when grooming an issue that touches `.claude/hooks/` or `scripts/qa-codex`, include the living spec in the files and criteria.
- **`codex-review` skill and `docs/process.md`:** the finding issues carry a `Source:` permalink; the review file is deleted when no finding is `open`.
- **Archive after use:** move the v1 plan, the two proposals (this file and `docs/specs/2026-10-01-big-picture.md`, once their follow-ups are issues) and `docs/checks/hook-activation.md` to `docs/archive/`.
- **Delete:** the existing files in `docs/reviews/` whose findings all have a decision; ask the owner about `docs/owner-notes/20260926-note.md`, whose questions #83 and #84 now answer.
- **Classify the observability spec** (`docs/specs/2026-09-26-agent-graph-observability.md`, status deferred): its items are `later` issues, so it is a plan to archive, unless the owner wants it kept as input.
- **Issue #16 (librarian):** the owner decides whether to close it as replaced by this proposal.
- **Issue #66:** it points to a file in `docs/archive/`; check it against the reading rule when it is groomed.
- **Later option:** a scheduled agent that opens parked issues, only if the stage-end audits show drift between stages.
