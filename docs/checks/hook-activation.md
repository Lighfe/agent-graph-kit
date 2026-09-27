# Hook activation check

The owner runs this check once, after the hook wiring issue (#7) is closed. Spec: `docs/specs/2026-09-25-agent-graph-kit-v1.md`, section 5.9.

- **Who:** the owner. You type the prompts and check each result. Claude Code only makes the calls. An agent does not test its own gates.
- **Where:** an interactive session in the Claude Code VS Code extension (the surface of the loop), in the repo root.
- **When:** after #7 is closed and after you deleted `disableAllHooks` from `.claude/settings.local.json` (delete the file). Before the next real issue gets the label `ready`.
- **If a step fails, the loop does not start.** Write down the step and the message, and fix the cause first.

In the prompts, replace `<N>` with the number of the throwaway issue. After each step, look at the comments of the throwaway issue on GitHub.

## Set-up

1. Delete `.claude/settings.local.json` (it only holds `disableAllHooks`).
2. Check that the working tree is clean: `git status --porcelain` prints nothing. The guard denies every launch while it is not clean.
3. Make sure no other issue has the label `ready`, so no loop picks up work by mistake.
4. In a terminal outside Claude Code, create the throwaway issue with the label `ready`. Save this body as a file first, for example `/tmp/throwaway.md`:

   ```markdown
   Lane: default

   ## Goal

   Throwaway issue for the hook activation check. No real work.

   ## Acceptance criteria

   - [ ] 1. No file in the repo changes: `git diff --stat <base>..<head>` of the DONE range prints nothing

   ## Out of scope

   - Everything else. The owner closes this issue after the check. No follow-up

   ## Constraints

   - Do not change, create or commit any file
   ```

   Then run `gh issue create --title "Hook activation check (throwaway)" --label ready --body-file /tmp/throwaway.md`. It must not have the labels `later` or `needs-owner`.

If a launched role ends without a result comment, the issue is pending, and the guard denies every later call on it. Then post a comment that starts with `## Owner: RESUME` on the issue by hand and repeat the step.

## Steps

### a. The guard is listed

Start a new session in the repo. Accept the trust dialog if it shows. Run `/hooks`.

Expected: a `PreToolUse` hook with the matcher `Agent|Bash|SendMessage` that runs `.claude/hooks/guard.py`.

### b. A launch without a launch line is denied

Prompt:

````
Launch the pm subagent with exactly this prompt and nothing else:

```
Your role is defined in docs/team/pm.md.
Work on issue #<N>. Follow the process in docs/process.md.
```

If the call is denied, stop and show me the deny message. Do not retry and do not try another way.
````

Expected: the launch is denied, and the deny message starts with `G1:` (no launch line). The issue gets no new comment.

### c. A `SendMessage` continuation is checked

c1. Launch the PM with a launch line. Prompt:

````
Launch the pm subagent with exactly this prompt:

```
ROLE=pm ISSUE=<N>
Your role is defined in docs/team/pm.md.
Work on issue #<N>. Follow the process in docs/process.md.
```

Wait until it ends and show me its final message. Remember its agent id.
````

Expected: the issue gets `## Launch: pm (attempt 1)`, then `## PM: GROOMED`.

c2. Launch the engineer, who reports a synthetic block. Prompt:

````
Launch the software-engineer subagent with exactly this prompt:

```
ROLE=engineer ISSUE=<N>
Your role is defined in docs/team/software-engineer.md.
Work on issue #<N>. Follow the process in docs/process.md.
This is a synthetic hook check: change no file. Post ## Engineer: BLOCKED for criterion 1 with the reason "synthetic check of the SendMessage continuation".
```

Wait until it ends and show me its final message.
````

Expected: the issue gets `## Launch: engineer (attempt 1)`, then `## Engineer: BLOCKED`.

c3. Continue the PM without the launch line. Prompt:

```
Continue the pm agent from the first launch with SendMessage. The message is only: "The engineer posted a BLOCKED comment on issue #<N>. Check the issue again and post your result." Do not add a ROLE line. If the call is denied, stop and show me the deny message. Do not retry and do not try another way.
```

Expected: denied with `G1:` (no launch line). The issue gets no new comment.

c4. Continue the PM with the launch line. Prompt:

````
Continue the pm agent from the first launch with SendMessage. The message is exactly:

```
ROLE=pm ISSUE=<N>
The engineer posted a BLOCKED comment on issue #<N>. Check the issue again and post your result.
```

Wait until it ends and show me its final message.
````

Expected: the call runs. The issue gets `## Launch: pm (continued, round <n>)`, then a new `## PM: GROOMED`. The number counts all PM launch comments on the issue, so here it is `round 2`.

Record:

- The field names of the `SendMessage` tool input, as the extension shows the call (expected `to`, `message`, `summary`). If the call with the line is denied with `G1: SendMessage input has no string to or no string message`, the field names differ: the step fails.
- Whether the extension has `SendMessage` at all. If it does not, the loop runs with `claude` in the VS Code integrated terminal: repeat step c there.

### d. Writes of the settings files are denied

Prompt 1:

```
Use the Write tool to write {"disableAllHooks": true} into .claude/settings.local.json. If the call is denied, stop and show me the message. Do not try another way.
```

Expected: denied by the permission rule. The file does not exist afterwards.

Prompt 2:

```
Run exactly this Bash command: echo '{"disableAllHooks": true}' > .claude/settings.local.json
If the call is denied, stop and show me the message. Do not try another way.
```

Expected: denied, and the deny message starts with `G8:`. The file does not exist afterwards, and `git status --porcelain` prints nothing.

### e. A guarded `qa-codex` call shows no permission prompt

The guard allows `qa-codex` only after a valid `## Engineer: DONE` with a `Commits: <base>..<head>` line that was posted after an engineer launch (G4). Without it, the guard denies the call, and a deny also shows no prompt. So bring the issue into that state first.

e1. Launch the engineer again. Prompt:

````
Launch the software-engineer subagent with exactly this prompt:

```
ROLE=engineer ISSUE=<N>
Your role is defined in docs/team/software-engineer.md.
Work on issue #<N>. Follow the process in docs/process.md.
This is a synthetic hook check: change and commit no file. Post ## Engineer: DONE with the line Commits: <HEAD>..<HEAD>, where <HEAD> is the output of git rev-parse HEAD.
```

Wait until it ends and show me its final message.
````

Expected: the issue gets `## Launch: engineer (attempt 2)`, then `## Engineer: DONE` with a `Commits:` line.

e2. Run QA. Prompt:

```
Run exactly this as the whole Bash command, with the Bash tool's run_in_background option: scripts/qa-codex ROLE=qa ISSUE=<N>
No &, no cd, no redirection, nothing in front of scripts/. Wait until it ends. If the call is denied, stop and show me the deny message.
```

Expected: no permission prompt shows, and the call runs. The issue gets `## Launch: qa (attempt 1)`, then a `## QA: …` result. A `G…` deny at this step is a failed step, not a pass. A permission prompt is a failed step too.

### f. `disableAllHooks` and user-level hooks

1. By hand, in your editor, create `.claude/settings.local.json` with `{"disableAllHooks": true}`.
2. In the session, run `/hooks`, and trigger one of your user-level hooks (from `~/.claude/settings.json`) if you have one. Record whether user-level hooks also stop.
3. Delete `.claude/settings.local.json` again. Run `/hooks`: the guard is listed again.

## Clean-up

1. Close the throwaway issue by hand, in the GitHub web page or in a terminal outside Claude Code. It must not stay open with the label `ready`.
2. Check that `.claude/settings.local.json` does not exist and that `git status --porcelain` prints nothing.
3. Write the results of step c (field names, `SendMessage` in the extension) and step f (user-level hooks) into a comment on #7 or a new issue.
