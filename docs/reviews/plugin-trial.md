# Plugin trial

Trial of the v2 plugin route in a fresh throwaway project (issue #163). The project was a private GitHub repo `agk-trial-kolibri` with synthetic data only. It was created for the trial and deleted at the end. Commands are shortened; no secrets appear.

Date: 2026-10-06. Claude Code 2.1.289. The plugin source was the local checkout (HEAD `9220dce`), because the GitHub copy is behind (step 2).

## Steps

| # | Step | Result |
|---|------|--------|
| 1 | Create the repo | worked |
| 2 | Add the marketplace and install the plugin (README, "Install the kit as a plugin (v2)", step 1) | failed, then needed a change |
| 3 | Run `/agk:setup` (step 2) | worked, with findings |
| 4 | Manual steps (step 3: `gh` login, Codex login, Codex trust entry, Auto mode entries) | needed a change |
| 5 | File one small task issue | worked |
| 6 | Run PM, engineer, QA | PM worked; engineer failed (ended BLOCKED); QA failed (not run, no `## Engineer: DONE`) |
| 7 | Close the issue | failed (no `## QA: PASS`, issue stayed open) |
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

- 3.4 Auto mode entries: set by the owner before the trial (the issue's `Permissions:` line). The script does not check them, as designed ("Check by hand: the three Auto mode entries").
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

### 6. PM, engineer, QA: partly

Run with `claude -p "<orchestrator prompt>" --permission-mode auto` in the trial project. The plugin hooks and agents loaded and the launch comments appeared.

```text
## Launch: pm (attempt 1)       -> ## PM: GROOMED
## Launch: engineer (attempt 1) -> ## Engineer: BLOCKED
## Launch: pm (attempt 2)       -> ## PM: NEEDS OWNER
Escalated by the orchestrator: label ready removed, needs-owner added
```

- PM: worked. It narrowed the request to a research note with at least 10 synthetic German prompts, and pinned the model to `Aleph-Alpha/Kolibri-1`.
- Engineer: BLOCKED, as the issue's out-of-scope section allows. The model needs a GPU. The machine has no GPU, about 5 GB free RAM and no torch. The engineer made no change and no commit.
- QA: failed (not run), because the loop needs `## Engineer: DONE` first. The Codex QA launch (`scripts/qa-codex`) is therefore not tested by this trial. An agent may not post `## Owner: RESUME`, so I did not resume the issue.

### 7. Close: failed

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

- #166 Plugin install from GitHub: publish the plugin and re-check the README route
- #167 Setup: merge permissions into an existing settings file
- #168 Setup and README: add the steps the v2 route lacks
- #169 README: say how to merge the settings lines by hand

## Not covered

QA by Codex, closing an issue and the hook activation check were not run, because the trial task ended BLOCKED. The issue counts the trial as done when the loop ran, even when the task ends BLOCKED. A second trial with a task that the machine can run would cover these three steps.
