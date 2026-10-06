# Plugin trial

Trial of the v2 plugin route in a fresh throwaway project (issue #163). The project was a private GitHub repo `agk-trial-kolibri` with synthetic data only. It was created for the trial and deleted at the end. Commands are shortened; no secrets appear.

Date: 2026-10-06. Claude Code 2.1.289. The plugin source was the local checkout (HEAD `9220dce`), because the GitHub copy is behind (step 2).

## Steps

| # | Step | Result |
|---|------|--------|
| 1 | Create the repo | worked |
| 2 | Add the marketplace and install the plugin (README, "Install the kit as a plugin (v2)", step 1) | failed, then needed a change |
| 3 | Run `/agk:setup` (step 2) | worked, with findings |
| 4 | Manual steps (step 3: `gh` login, Codex login, Codex trust entry, Auto mode entries) | needed a change; 3.4 failed (entries 2 and 3 not set, owner-only) |
| 5 | File one small task issue | worked |
| 6 | Run PM, engineer, QA | PM worked; engineer failed (ended BLOCKED); QA not reached (engineer ended BLOCKED, as the issue allows) |
| 7 | Close the issue | not reached (no `## QA: PASS`; trial issue state: OPEN, label `needs-owner`) |
| 8 | Delete the repo | worked |

### 1. Create the repo: worked

```text
$ gh repo create agk-trial-kolibri --private --clone
https://github.com/Lighfe/agk-trial-kolibri
$ git checkout -B main && git commit --allow-empty -m "Initial commit" && git push -u origin main
```

### 2. Marketplace and plugin install: failed, then needed a change

README step 1, as written:

```text
$ claude plugin marketplace add Lighfe/agent-graph-kit
Failed to add marketplace: Marketplace file not found at .../Lighfe-agent-graph-kit/.claude-plugin/marketplace.json
$ claude plugin install agk@agent-graph-kit --scope project
Failed to install plugin "agk@agent-graph-kit": Plugin "agk" not found in marketplace
```

Cause: `origin/main` was 4 commits behind. The commits with `.claude-plugin/marketplace.json`, the setup skill and the README section (#160 to #162) were not pushed. The README does not say that the owner must push first. Workaround used:

```text
$ claude plugin marketplace add /home/julian/.../agent-graph-kit
Successfully added marketplace: agent-graph-kit
$ claude plugin install agk@agent-graph-kit --scope project
Successfully installed plugin: agk@agent-graph-kit (scope: project)
```

The install created `.claude/settings.json` with only `enabledPlugins`. This matters in step 3.

Follow-up: #166.

### 3. `/agk:setup`: worked, with findings

Run non-interactively: `claude -p "/agk:setup <name> <test command>"`. Output (shortened):

```text
The script copied 12 files and wrote .agent-graph-kit.lock with 12 entries.
Existing file, not touched: .claude/settings.json (merge by hand:
  allow Bash(scripts/qa-codex ROLE=qa ISSUE=*), Bash(gh issue close *);
  deny Edit(/.claude/settings*.json))
Missing: Codex trust entry
Check by hand: the three Auto mode entries
gh login, uv, Codex login: OK
```

Findings:

- Because the plugin install had already created `.claude/settings.json`, the setup never writes its `permissions` block, and the README order (install, then setup) makes this the normal case. The owner merges the lines by hand. Follow-up: #167.
- Setup writes `AGENTS.md` but no `CLAUDE.md`, and no `.gitignore` lines. The v1 route had both.
- Nothing in the v2 section names the four labels (`ready`, `needs-owner`, `later`, `stage`). The loop needs them. I created them with `gh label create`.
- The v2 section does not say to commit and push the copied files, to accept the trust dialog (without it Claude Code printed `Ignoring 2 permissions.allow entries from .claude/settings.json: this workspace has not been trusted`), or to run `docs/checks/hook-activation.md`. These are the "Start" steps of the v1 route.

Follow-up for the last three points: #168.

### 4. Manual steps: needed a change

README line: step 3 of "Install the kit as a plugin (v2)" (3.1 `gh` login, 3.2 Codex login, 3.3 Codex trust entry, 3.4 Auto mode entries).

- 3.1 `gh` login: worked.

  ```text
  $ gh auth status
  github.com
    Logged in to github.com account <owner> (keyring)
  ```

- 3.2 Codex login: worked. The setup script reported `Codex login: OK` (see step 3), so no login was needed.
- 3.3 Codex trust entry: worked. I appended the README block (lines 53 to 58) to `~/.codex/config.toml` with the absolute project path, and checked that the setup check no longer listed "Missing: Codex trust entry". After the trial I restored the file to its earlier content (the block is gone).

  ```text
  $ printf '\n[projects."<trial project path>"]\ntrust_level = "trusted"\n' >> ~/.codex/config.toml
  $ claude -p "/agk:setup ..."   # second run: no "Missing: Codex trust entry" line
  ```

- 3.4 Auto mode entries: failed. README.md line 60 asks for all three entries, and entries 2 and 3 were not set. Only the owner can set user-level Auto mode entries, so the trial could not do this step in full. Nothing in the trial was affected (see below), but the step is not done as the README asks. The README names three entries: entry 1 QA launch (`scripts/qa-codex ROLE=qa ISSUE=<number>`), entry 2 PM edits (`gh issue edit` after `## Owner: RESUME`) and entry 3 planner relabel (`gh issue edit <n> --remove-label later --add-label ready`). The setup script does not check them, as designed ("Check by hand: the three Auto mode entries"). I checked by hand with a read-only `jq` command on the user-level settings file (`~/.claude/settings.json`). It prints only whether each entry text matches, not the texts:

  ```text
  $ jq '[.autoMode.allow[] | {qa: contains("qa-codex"), pm: contains("gh issue edit"), planner: contains("remove-label later")}]' ~/.claude/settings.json
  ```

  Result: entry 1 (QA launch) was set: two entries name `qa-codex`, one for this repo and one for another project. Entry 2 (PM edits) was not set. Entry 3 (planner relabel) was not set. The other entries in the file (`gh repo create` and `gh repo delete`, plugin install) are not among the three README entries. The trial needed neither entry 2 nor entry 3: no `## Owner: RESUME` edit and no stage relabel happened. The PM and engineer launches ran in Auto mode without a classifier denial. Entry 1 was not exercised, because QA was not reached (step 6). No README line was wrong for 3.4.
- Needed a change: the README says "merge by hand" for the project settings file without naming how. In the main session, `printf` and `cat >` commands that name `.claude/settings.json` were denied by the kit's guard:

  ```text
  $ printf '...' > .claude/settings.json
  G8: the command may write to .claude/settings*.json ... denied
  ```

  The Write tool worked. The guard is expected behavior; the README lacks the hint. Follow-up: #169.

### 5. Task issue: worked

The owner's one-line request, filed with the label `ready`:

```text
Use a Hugging Face model named Kolibri and try different German question prompts
until the model answers "I don't know" or the German equivalent.
```

`gh issue create ... --label ready` returned issue #1.

### 6. PM, engineer, QA: PM worked, engineer BLOCKED, QA not reached

Run with `claude -p "<orchestrator prompt>" --permission-mode auto` in the trial project. The plugin hooks and agents loaded and the launch comments appeared.

```text
## Launch: pm (attempt 1)       -> ## PM: GROOMED
## Launch: engineer (attempt 1) -> ## Engineer: BLOCKED
## Launch: pm (attempt 2)       -> ## PM: NEEDS OWNER
Escalated by the orchestrator: label ready removed, needs-owner added
```

- PM: worked. It narrowed the request to a research note with at least 10 synthetic German prompts, and pinned the model to `Aleph-Alpha/Kolibri-1`.
- Engineer: BLOCKED, as the issue's out-of-scope section allows. The model needs a GPU. The machine has no GPU, about 5 GB free RAM and no torch. The engineer made no change and no commit.
- QA: not reached, because the loop needs `## Engineer: DONE` first. The Codex QA launch (`scripts/qa-codex`) is therefore not tested by this trial. An agent may not post `## Owner: RESUME`, so I did not resume the issue.

### 7. Close: not reached

Command: none was run, because the close needs `## QA: PASS` (`gh issue close` is the orchestrator's step after QA). The orchestrator escalated instead, so the issue stayed open. State after the run:

```text
$ gh issue view 1 --json state,labels
{"state":"OPEN","labels":[{"name":"needs-owner"}]}
```

README line: none wrong. The README does not describe what the owner does after a BLOCKED engineer in a trial.

### 8. Delete the repo: worked

```text
$ gh repo delete Lighfe/agk-trial-kolibri --yes
$ gh repo view Lighfe/agk-trial-kolibri
GraphQL: Could not resolve to a Repository with the name 'Lighfe/agk-trial-kolibri'.
```

Final state: the repo is gone, the Codex trust entry is removed, the local marketplace entry is removed, the working tree of this repo is clean.

## Follow-up issues (label `later`)

The complete bodies and labels are in the appendix below. Copied with `gh issue view <n> --json title,labels,body` (the `Source:` line is the line of the body that starts with `Source`):

| Issue | Title | Label | `Source:` line |
| --- | --- | --- | --- |
| #166 | Plugin install from GitHub: publish the plugin and re-check the README route | `later` | `Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md` |
| #167 | Setup: merge permissions into an existing settings file | `later` | `Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md` |
| #168 | Setup and README: add the steps the v2 route lacks | `later` | `Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md` |
| #169 | README: say how to merge the settings lines by hand | `later` | `Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md` |

Note on #166: the install route `claude plugin marketplace add Lighfe/agent-graph-kit` worked after the owner pushed `main`. The orchestrator checked it on 2026-10-06: the marketplace was added, lists plugin `agk` with source `./plugin`, and was removed again.

## Not covered

QA by Codex, closing an issue and the hook activation check were not run, because the trial task ended BLOCKED. The issue counts the trial as done when the loop ran, even when the task ends BLOCKED. A second trial with a task that the machine can run would cover these three steps.

## Appendix: follow-up issues as filed

Copied with `gh issue view <n> --json title,labels,body`. The label is `later` on each. No secrets appear.

### #166: Plugin install from GitHub: publish the plugin and re-check the README route

Labels: `later`

````text
Lane: default
Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md
Permissions: none

## Goal

The README route "Install the kit as a plugin (v2)" works against GitHub: the marketplace add and the plugin install succeed in a fresh project.

## Acceptance criteria

- [ ] After the plugin commits are on `origin/main`, `claude plugin marketplace add Lighfe/agent-graph-kit` and `claude plugin install agk@agent-graph-kit --scope project` both succeed in an empty throwaway project
- [ ] The README says what the owner must do once before step 1 (push or release), if anything
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- Changing the plugin files

## Constraints

- Files: `README.md`. The push itself is an owner action
````

### #167: Setup: merge permissions into an existing settings file

Labels: `later`

````text
Lane: default
Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md
Permissions: none

## Goal

`/agk:setup` writes the permissions block of `.claude/settings.json` also after `claude plugin install --scope project`, which already created that file.

## Acceptance criteria

- [ ] When `.claude/settings.json` exists and holds only `enabledPlugins`, setup merges the `permissions` block into it without losing `enabledPlugins`
- [ ] When the file holds other `permissions` entries, setup keeps them and adds only the missing lines
- [ ] A test covers both cases
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- Hooks (the plugin delivers them)

## Constraints

- Files: `plugin/skills/setup/`, its tests, `README.md`
````

### #168: Setup and README: add the steps the v2 route lacks

Labels: `later`

````text
Lane: default
Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md
Permissions: none

## Goal

After `/agk:setup` and the README steps, a new project has everything the loop needs: the steps the v1 route had and the v2 route lacks are done by setup or named in the README.

## Acceptance criteria

- [ ] Setup writes `CLAUDE.md` with `@AGENTS.md` (the trial project had only `AGENTS.md`), or the README names the step
- [ ] Setup writes the `.gitignore` lines (`.claude/settings.local.json`, `__pycache__/`), or the README names the step
- [ ] The README names the four labels (`ready`, `needs-owner`, `later`, `stage`) with the `gh label create` commands, or setup creates them
- [ ] The README names the steps: commit and push the setup files, open the project in Claude Code and accept the trust dialog (without it the project `permissions.allow` entries are ignored), and run the hook activation check in `docs/checks/hook-activation.md` before the first `ready` issue
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- The Lovable lane

## Constraints

- Files: `plugin/skills/setup/`, its tests, `README.md`
````

### #169: README: say how to merge the settings lines by hand

Labels: `later`

````text
Lane: default
Source: https://github.com/Lighfe/agent-graph-kit/blob/main/docs/reviews/plugin-trial.md
Permissions: none

## Goal

The README step that tells the owner to merge the permission lines into `.claude/settings.json` by hand says how to do it, so the owner does not hit the kit's guard.

## Acceptance criteria

- [ ] The README v2 section says that the merge needs an editor, a terminal outside Claude Code, or the Write tool, because the kit's guard denies `printf` and `cat >` commands that name `.claude/settings.json` in the main session
- [ ] The README names the lines to merge in one place that the setup output points to
- [ ] The test command `uv run --with pytest pytest` passes

## Out of scope

- Changing the guard
- Merging the settings automatically (see #167)

## Constraints

- Files: `README.md`
````
