# Plugin update route: plan

Spec: `docs/specs/2026-10-21-plugin-update-route.md`.

Tasks, in order:

1. Task 1: `drift.py` gets `--accept` and the `dropped` clean-up in `--update`, with tests in `tests/test_drift.py`
2. Task 2: README section "Update a plugin project", drift `SKILL.md` and the living spec describe the complete route. Blocked by task 1
3. Task 3: existing issue "Replace board-game examples in the PM role file" (small cleanup, `docs/team/pm.md`)
4. Task 4: existing issue "PM grooming: check that named commands and files exist, and that no criterion pins a changing assertion", body adapted to this repo
5. Task 5: existing issue "Stage review: run one prompt audit scope instead of two overlapping ones", body adapted
6. Task 6: existing issue "Engineer file: merge the foreground and background test-run bullets", body adapted
7. Task 7: move the owner-addressed line out of `docs/team/software-engineer.md` (doc drift finding of the Stage 15 review)

The plugin version bump is not a task: the orchestrator bumps at the end of the stage.
