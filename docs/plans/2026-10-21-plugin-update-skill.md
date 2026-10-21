# Plugin update skill: plan

Spec: `docs/specs/2026-10-21-plugin-update-skill.md`. Each task is one issue; the issues hold the full text.

Order and blockers:

1. #249 README: only the plugin route, archive the manual route (existing)
2. #251 Role files: no kit-only commands in the copies for plugin projects (existing)
3. Task 3: `/agk:update` skill, safe part. Blocked by #251 (fewer merges to propose)
4. Task 4: `/agk:update` skill, merge proposals and finish. Blocked by task 3
5. #250 README: one update section for a plugin project (existing, rewritten). Blocked by #249 and task 4

## Task 3: skill `update`, safe part

File: `plugin/skills/update/SKILL.md` (and `drift.py` only if the skill needs it). Steps: drift summary, `drift.py --update` from `${CLAUDE_SKILL_DIR}`, list of `changed in both` files, stop message. First find out whether the update runs inside a session; if a deny occurs, print the terminal command and stop. Tests pin the skill shape (name, steps, no cache path typed by the owner). Spec text in `docs/specs/agent-graph-kit.md`.

## Task 4: skill `update`, merge proposals and finish

Extend the skill: per `changed in both` file a proposal with the three change kinds, owner answer per file, write, `--accept`, drift again, hook activation check, commit offer (never push). A "no" leaves the file and the lock entry. `AGENTS.md` and settings stay out.

## Tasks 1, 2 and 5

Existing issues #249, #251 and #250. #250 is rewritten: one section, ends in `/agk:update`.
