# How the hooks work

This document is optional background. You do not need it to start a project. The check that the hooks are active is run for you by `/agk:hook-activation-check` (a step of the route in the README, `## Start a new project`). Read this when you want to know what the hooks do, or see a deny yourself. Spec: `docs/specs/agent-graph-kit.md`, heading "G8 Settings protection".

## The three hooks

The hooks are registered in `.claude/settings.json` and apply from the next tool call after that file is in place.

- **Guard hook** (`.claude/hooks/guard.py`, a `PreToolUse` hook with the matcher `Agent|Bash|SendMessage`). It checks every launch of a role, every `SendMessage` continuation, the `qa-codex` call and the `gh issue close` call against the state of the issue. It also denies writes to the settings files and to `.claude/hooks/`. A call that breaks a rule is denied before it runs, and the deny message tells why.
- **Not-started hook** (`.claude/hooks/not_started.py`, a `PermissionDenied` hook). When Claude Code or the Auto mode classifier denies a guarded launch before it ran, this hook posts `## Launch not started: …` on the issue. A launch that did not start is not a pending launch and not a return.
- **Outage stop hook** (`.claude/hooks/outage_stop.py`, a `SubagentStop` hook). When an Auto mode outage stopped a role agent, this hook posts `## Launch stopped by outage: …` on the issue. The orchestrator then launches the same step again, without the owner.

If hooks are off (`{"disableAllHooks": true}` in `.claude/settings.local.json`), none of this runs, and there is no warning. `/agk:hook-activation-check` fails when that file turns the hooks off.

## What a deny looks like

A deny message starts with the gate name and a colon, says what is wrong, and says what is expected. Example: a launch of the PM with no launch line.

```text
G1: the launch prompt has no launch line, expected exactly one line ROLE=<pm|engineer|qa|planner> ISSUE=<number>
```

The call does not run, and the issue gets no new comment. Fix the call as the message says. A deny of a write to a settings file starts with `G8:`.

## Optional: if you want to see a deny yourself

You do not have to do this. The check skill already does the check. Run these steps by hand only to see the hooks work. Use an interactive session in the Claude Code VS Code extension, in the repo root, in Auto mode. Use a throwaway issue; replace `<N>` with its number and close it when you are done.

1. Check that the guard is listed. Run `/hooks`. Expected: a `PreToolUse` hook with the matcher `Agent|Bash|SendMessage` that runs `.claude/hooks/guard.py`.
2. A launch without a launch line is denied. Prompt:

   ````
   Launch the pm subagent with exactly this prompt and nothing else:

   ```
   Your role is defined in docs/team/pm.md.
   Work on issue #<N>. Follow the process in docs/process.md.
   ```

   If the call is denied, stop and show me the deny message. Do not retry and do not try another way.
   ````

   Expected: denied, and the message starts with `G1:`.
3. A write of a settings file is denied. Prompt:

   ```
   Run exactly this Bash command: echo '{"disableAllHooks": true}' > .claude/settings.local.json
   If the call is denied, stop and show me the deny message. Do not try another way.
   ```

   Expected: denied, and the message starts with `G8:`. The file does not exist afterwards.
4. See hooks go off and on. The probe is a harmless read that the guard denies with `G8:`. It pipes the `cat` into `tee`, because a lone `cat` of the settings file is a read-only command, so G8 lets it pass. Prompt (the same for each run):

   ```
   Run exactly this Bash command: cat .claude/settings.json | tee /dev/null
   If the call is denied, stop and show me the deny message. Do not try another way.
   ```

   1. Run the probe. Expected: denied with `G8:`.
   2. By hand, in your editor, create `.claude/settings.local.json` with `{"disableAllHooks": true}`.
   3. Run the probe again. Expected: it runs and prints the file. Hooks are off, so this is the expected result. Do not launch any role while hooks are off.
   4. Delete `.claude/settings.local.json` again.
   5. Run the probe a third time. Expected: denied again with `G8:`.

When you are done, check that `.claude/settings.local.json` does not exist, that `git status --porcelain` prints nothing, and that the throwaway issue is closed.
