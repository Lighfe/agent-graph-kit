---
name: hook-activation-check
description: Check by itself that the kit works in the current project - hooks registered, guard denies, qa-codex loads, tools and logins present. Use when the owner types /agk:hook-activation-check, or asks whether the kit is set up right. Read-only.
---

# Hook activation check

This skill runs 4 checks and prints one line per check, then one result line. It writes no file in the project, posts no GitHub comment, creates or edits no issue and starts no Codex run.

## Steps

1. Run the script from this skill's folder, in the project root (the git root of the project):

   ```bash
   uv run --script "${CLAUDE_SKILL_DIR}/check.py" --root "<project root>"
   ```

2. Show the owner the output. Each line starts with `OK` or `FAILED`:
   - Check 1: every event of the plugin `hooks.json` (`PreToolUse`, `SubagentStop`, `PermissionDenied`) is registered
     The evidence is an `enabledPlugins` entry `agk@<marketplace>` set to `true`, or the event in the `hooks` of a settings file (user, project or local). `disableAllHooks: true` in any of them fails the check.
   - Check 2: the guard denies `gh issue close 1 && true` with a `G1` message (a synthetic input, no GitHub call)
   - Check 3: `scripts/qa-codex --self-check` loads all its modules and ends without `gh` or `codex`
   - Check 4: `gh`, `uv` and `codex` are on the path, and `gh` and `codex` are logged in
   - The last line is `OK` only when all 4 checks are `OK`, otherwise `FAILED`
3. For each `FAILED` line, tell the owner the reason it names. Do not fix anything by hand.
4. The trust dialog of Claude Code cannot be read by a script. If the hooks do not run, tell the owner to check that dialog.
