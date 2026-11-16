# Release channels: the owner's checklist

The plugin has two channels. `stable` is for users. `dev` gets every new plugin version first. Agents do not push, set tags or start workflows, so you do the steps below once, by hand.

## State on GitHub

This is the state of 2026-11-16. The tag, the push of `main` and the first runs of both channels are done. Do not do them again.

- `main` is at `ffb5378` (plugin 0.2.1)
- The tag `v0.2.0` is at `59ac226`, with a pre-release. The workflow `ci` passed there. It stays there
- The tag `v0.2.1` is at `ffb5378`. Its release is the latest release
- The branch `dev` is at `b2ae99e`. `release-dev` made it from `ffb5378`, with the marketplace name `agent-graph-kit-dev`
- The branch `stable` is at `ffb5378`. A manual run of `release-stable` with `v0.2.1` moved it there

Still open are three steps: install from `stable`, install from `dev`, and the rollback check.

How to use this list:

- Do the steps in order. A step can have more than one action (a, b, c). Each action is one command to copy, one page to open, one click, or one value to type.
- Run the commands in a terminal in the repo folder of `agent-graph-kit`, unless the action names another folder.
- After each action, compare what you see with "You should see". When it is different, stop and do what "If not" says. "Send back" means: paste the text into a Claude Code session in this repo, or into a new issue.
- You need `git`, `gh` (logged in) and `claude` on this machine.

## Step 1: Install from stable in an empty test project

Your machine already has the marketplace `agent-graph-kit` without a channel. Action a removes it, and action b adds it again on the channel `stable`. The removal also uninstalls the old copy of `agk` (version 0.1.10) that came from this marketplace.

**a.** Copy this command:

```
claude plugin marketplace remove agent-graph-kit
```

You should see: exactly this:

```
✔ Successfully removed marketplace: agent-graph-kit
Also uninstalled 1 plugin from this marketplace:
  agk@agent-graph-kit
The removal also deletes their saved options, secrets and data where it can.
To use a plugin again, add the marketplace back and reinstall the plugin.
```

The first line is the one that counts. When no plugin from the marketplace was installed, only the first line is there; when more copies were installed, the second line has another number and the copies are listed below it. Both are fine.

If not: when the output is `✘ Failed to remove marketplace: Marketplace 'agent-graph-kit' not found`, go on with action b. For any other output, send it back and stop.

**b.** Copy this command. It makes a new empty folder and adds the channel `stable`:

```
mkdir -p ~/agk-stable-test && cd ~/agk-stable-test && git init -q && claude plugin marketplace add Lighfe/agent-graph-kit#stable
```

You should see: exactly this:

```
Adding marketplace…Cloning via SSH: git@github.com:Lighfe/agent-graph-kit.git
Refreshing marketplace cache (timeout: 120s)…
Cloning repository (timeout: 120s): git@github.com:Lighfe/agent-graph-kit.git (ref: stable)
Clone complete, validating marketplace…
Cleaning up old marketplace cache…
✔ Successfully added marketplace: agent-graph-kit (declared in user settings)
```

The last line is the one that counts.

If not: send back the full output of the command. An output with `Remote branch stable not found` means that the manual run of `release-stable` did not move the branch `stable`.

**c.** Copy this command in the same terminal (the folder is `~/agk-stable-test`):

```
claude plugin install agk@agent-graph-kit --scope project
```

You should see: exactly this one line:

```
Installing plugin "agk@agent-graph-kit"...✔ Successfully installed plugin: agk@agent-graph-kit (scope: project)
```

If not: send back the full output of the command.

**d.** Copy this command in the same terminal:

```
claude plugin list
```

You should see: this block in the list, with exactly this version:

```
  ❯ agk@agent-graph-kit
    Version: 0.2.1
    Scope: project
    Status: ✔ enabled
```

If not: send back the full output of the command. Name the version that it shows.

## Step 2: Install from dev in a second test project

**a.** Copy this command. It makes a second empty folder and adds the channel `dev`:

```
mkdir -p ~/agk-dev-test && cd ~/agk-dev-test && git init -q && claude plugin marketplace add Lighfe/agent-graph-kit#dev
```

You should see: exactly this:

```
Adding marketplace…Cloning via SSH: git@github.com:Lighfe/agent-graph-kit.git
Refreshing marketplace cache (timeout: 120s)…
Cloning repository (timeout: 120s): git@github.com:Lighfe/agent-graph-kit.git (ref: dev)
Clone complete, validating marketplace…
Cleaning up old marketplace cache…
✔ Successfully added marketplace: agent-graph-kit-dev (declared in user settings)
```

The last line is the one that counts.

If not: send back the full output of the command.

**b.** Copy this command in the same terminal (the folder is `~/agk-dev-test`):

```
claude plugin install agk@agent-graph-kit-dev --scope project
```

You should see: exactly this one line:

```
Installing plugin "agk@agent-graph-kit-dev"...✔ Successfully installed plugin: agk@agent-graph-kit-dev (scope: project)
```

If not: send back the full output of the command.

**c.** Copy this command in the same terminal:

```
claude plugin list
```

You should see: this block in the list, where the line `Version:` shows `0.2.1`:

```
  ❯ agk@agent-graph-kit-dev
    Version: 0.2.1
    Scope: project
    Status: ✔ enabled
```

If not: send back the full output of the command. Name the version that it shows.

## Step 3: Rollback

This step moves `stable` back to `v0.2.0`, and then forward to `v0.2.1` again. It shows what a user of `stable` gets after a rollback. Both answers in action c are valid results. Write down which one you got.

**a.** Copy this command. It runs "release-stable" with `v0.2.0` (the rollback). It works in any folder:

```
gh workflow run release-stable.yml --repo Lighfe/agent-graph-kit -f tag=v0.2.0
```

You should see: the first line is exactly

```
✓ Created workflow_dispatch event for release-stable.yml at main
```

If not: send back the full output of the command.

**b.** Wait two minutes. Then copy this command:

```
gh run list --repo Lighfe/agent-graph-kit --workflow release-stable.yml --limit 1 --json conclusion --jq '.[0].conclusion' && git ls-remote https://github.com/Lighfe/agent-graph-kit.git refs/heads/stable
```

You should see: the line `success`, and then the line

```
59ac2264c605c8fc0d895c69790ac2a2763fd912	refs/heads/stable
```

If not: when the first line is empty, wait one minute and run the command again. When it is `failure`, send back the output of `gh run view --repo Lighfe/agent-graph-kit --log-failed $(gh run list --repo Lighfe/agent-graph-kit --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`. When the second line shows another text before `refs/heads/stable`, send back the output of the command.

**c.** Copy this command. It updates the first test project:

```
cd ~/agk-stable-test && claude plugin marketplace update agent-graph-kit && claude plugin update agk@agent-graph-kit --scope project && claude plugin list
```

You should see: first these three lines:

```
Updating marketplace: agent-graph-kit...Refreshing marketplace cache (timeout: 120s)…
✔ Successfully updated marketplace: agent-graph-kit
Checking for updates for plugin "agk@agent-graph-kit" at project scope…
```

then one of these two results. Write down which one you got:

- The rollback reaches a user who already had the newer version. The fourth line is `✔ Plugin "agk" updated from 0.2.1 to 0.2.0 for scope project. Restart to apply changes.`, and in the list the block `❯ agk@agent-graph-kit` has the line `    Version: 0.2.0`.
- The rollback does not reach this user. The fourth line is `✔ agk is already at the latest version (0.2.1).`, and in the list the block `❯ agk@agent-graph-kit` has the line `    Version: 0.2.1`. Claude Code has no downgrade command, so this can happen. The README then has to name the way back.

If not: when the block is missing, or the version is neither of the two, send back the full output of the command.

**d.** Copy this command. It runs "release-stable" with `v0.2.1` again, so users get 0.2.1 again. It works in any folder:

```
gh workflow run release-stable.yml --repo Lighfe/agent-graph-kit -f tag=v0.2.1
```

You should see: the first line is exactly

```
✓ Created workflow_dispatch event for release-stable.yml at main
```

If not: send back the full output of the command.

**e.** Wait two minutes. Then copy this command:

```
gh run list --repo Lighfe/agent-graph-kit --workflow release-stable.yml --limit 1 --json conclusion --jq '.[0].conclusion' && git ls-remote https://github.com/Lighfe/agent-graph-kit.git refs/heads/stable
```

You should see: the line `success`, and then the line

```
ffb5378d3c939b1f188e512110f393972605089c	refs/heads/stable
```

If not: when the first line is empty, wait one minute and run the command again. When it is `failure`, send back the output of `gh run view --repo Lighfe/agent-graph-kit --log-failed $(gh run list --repo Lighfe/agent-graph-kit --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`. When the second line shows another text before `refs/heads/stable`, send back the output of the command.

## After the checklist

- Give the planner the result that you wrote down in step 3, action c. It decides the README text on the way back after a rollback (follow-up #344).
- The two test folders `~/agk-stable-test` and `~/agk-dev-test` can be deleted.
- `stable` is on `v0.2.1` again, so users get 0.2.1.
