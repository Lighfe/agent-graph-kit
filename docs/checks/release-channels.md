# Release channels: the owner's checklist

The plugin has two channels. `stable` is for users. `dev` gets every new plugin version first. Agents do not push, set tags or start workflows, so you do the steps below once, by hand, after the stage.

How to use this list:

- Do the steps in order. A step can have more than one action (a, b, c). Each action is one command to copy, one page to open, one click, or one value to type.
- Run the commands in a terminal in the repo folder of `agent-graph-kit`, unless the action names another folder.
- After each action, compare what you see with "You should see". When it is different, stop and do what "If not" says. "Send back" means: paste the text into a Claude Code session in this repo, or into a new issue.
- You need `git`, `gh` (logged in) and `claude` on this machine.

The tag `v0.2.0` goes first, before the push of `main`. Do not change this order.

## Step 1: Set the tag v0.2.0 on the Stage 21 release commit

**a.** Copy this command:

```
git tag v0.2.0 e2295d7 && git push origin v0.2.0
```

You should see: the last line is

```
 * [new tag]         v0.2.0 -> v0.2.0
```

If not: send back the full output of the command. If the output says `tag 'v0.2.0' already exists`, also send back the output of `git rev-parse v0.2.0^{commit}`.

## Step 2: Push main

**a.** Copy this command:

```
git push origin main
```

You should see: the last line ends with `main -> main`.

If not: send back the full output of the command.

**b.** Wait two minutes. Then copy this command:

```
gh run list --workflow release-dev.yml --limit 1 --json conclusion,headBranch --jq '.[0]'
```

You should see:

```
{"conclusion":"success","headBranch":"main"}
```

If not: when `conclusion` is `""`, the run is not finished; wait one minute and run the command again. When it is `failure`, or the command prints nothing, send back the output of `gh run view --log-failed $(gh run list --workflow release-dev.yml --limit 1 --json databaseId --jq '.[0].databaseId')`.

## Step 3: Run "release-stable" with v0.2.0

Actions a to d are in the browser, in the GitHub Actions tab of the repo.

**a.** Open this page in the browser:

```
https://github.com/Lighfe/agent-graph-kit/actions/workflows/release-stable.yml
```

You should see: the heading `release-stable`, and above the list of runs the line `This workflow has a workflow_dispatch event trigger.` with the button `Run workflow` at its right end.

If not: when the page says that it is not found, send back the output of `gh workflow list`. When the button `Run workflow` is missing, send back a screenshot of the page.

**b.** Click **Run workflow** (the button at the right end of the line `This workflow has a workflow_dispatch event trigger.`).

You should see: a small panel opens. It has `Use workflow from` with the button `Branch: main`, a text field with the label `The version tag that the branch stable moves to, for example v0.2.0`, and a green button `Run workflow`.

If not: when the button shows another branch than `main`, send back a screenshot of the panel and stop. When no panel opens, send back a screenshot of the page.

**c.** Type `v0.2.0` into the text field `The version tag that the branch stable moves to, for example v0.2.0`.

You should see: the field shows exactly `v0.2.0`, with no space before or after it.

If not: clear the field and type it again. When the field cannot be changed, send back a screenshot of the panel.

**d.** Click the green button **Run workflow** at the bottom of the panel.

You should see: the panel closes, and at the top of the page the message `Workflow run was successfully requested.`

If not: send back a screenshot of the page.

**e.** Wait two minutes. Then copy this command:

```
gh run list --workflow release-stable.yml --limit 1 --json conclusion --jq '.[0].conclusion'
```

You should see:

```
success
```

If not: when the command prints an empty line, the run is not finished; wait one minute and run the command again. When it prints `failure`, send back the output of `gh run view --log-failed $(gh run list --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`.

**f.** Copy this command:

```
git ls-remote origin refs/heads/stable refs/tags/v0.2.0
```

You should see: two lines that start with the same text:

```
e2295d77170c5b6398126f62c4e539a285402b12	refs/heads/stable
e2295d77170c5b6398126f62c4e539a285402b12	refs/tags/v0.2.0
```

If not: send back the output of the command.

**g.** Copy this command:

```
gh release view v0.2.0 --json tagName,isPrerelease,isDraft --jq '.' && gh release list --limit 10
```

You should see: the first line is `{"isDraft":false,"isPrerelease":false,"tagName":"v0.2.0"}`. In the table below it, the row of `v0.2.0` has the word `Latest`.

If not: send back the output of the command.

## Step 4: Install from stable in an empty test project

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

If not: send back the full output of the command. An output with `Remote branch stable not found` means that step 3 did not move the branch `stable`.

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
    Version: 0.2.0
    Scope: project
    Status: ✔ enabled
```

If not: send back the full output of the command. Name the version that it shows.

## Step 5: See the first release on dev

This step needs a pushed `main` with a plugin version newer than 0.2.0. Action a tells you whether that is the case now.

**a.** Copy this command in the repo folder of `agent-graph-kit`:

```
git fetch -q origin && git show origin/main:plugin/.claude-plugin/plugin.json | grep '"version"'
```

You should see: one line like `  "version": "0.2.1",` with a version newer than `0.2.0`. Write this version down. The steps below call it the new version, and `v` plus this version (for example `v0.2.1`) the new tag.

If not: when the line shows `"version": "0.2.0"`, the push in step 2 had no new version. This is normal. Stop here. After the next stage ends and you have pushed `main` again, start this step again from action a. For any other output, send it back.

**b.** Copy this command:

```
gh run list --workflow release-dev.yml --limit 1 --json conclusion,headBranch --jq '.[0]'
```

You should see:

```
{"conclusion":"success","headBranch":"main"}
```

If not: when `conclusion` is `""`, the run is not finished (it runs all tests, this takes some minutes); wait and run the command again. When it is `failure`, send back the output of `gh run view --log-failed $(gh run list --workflow release-dev.yml --limit 1 --json databaseId --jq '.[0].databaseId')`.

**c.** Copy this command:

```
git ls-remote origin 'refs/tags/v*' refs/heads/dev
```

You should see: one line that ends with `refs/heads/dev`, one line that ends with `refs/tags/v0.2.0`, and one line that ends with `refs/tags/` and the new tag.

If not: send back the output of the command.

**d.** Copy this command:

```
gh release list --limit 10
```

You should see: a row for the new tag with the word `Pre-release`. The row of `v0.2.0` still has the word `Latest`.

If not: send back the output of the command.

**e.** Copy this command:

```
git fetch -q origin dev && git show FETCH_HEAD:.claude-plugin/marketplace.json | grep -m1 '"name"' && git show FETCH_HEAD:plugin/.claude-plugin/plugin.json | grep '"version"'
```

You should see: two lines. The first is `  "name": "agent-graph-kit-dev",`. The second shows the new version.

If not: send back the output of the command.

## Step 6: Install from dev in a second test project

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

You should see: this block in the list, where the line `Version:` shows the new version from step 5a (here the example `0.2.1`):

```
  ❯ agk@agent-graph-kit-dev
    Version: 0.2.1
    Scope: project
    Status: ✔ enabled
```

If not: send back the full output of the command. Name the version that it shows.

## Step 7: Rollback

This step moves `stable` forward to the new tag, and then back to `v0.2.0`. It shows what a user of `stable` gets after a rollback. Both answers in action f are valid results. Write down which one you got.

The commands below use the example `v0.2.1` (and `0.2.1`) for the new tag. When your new tag from step 5a is another one, change it in the command before you press Enter, and read it in the same way in "You should see".

**a.** Copy this command in the repo folder of `agent-graph-kit`. It runs "release-stable" with the new tag:

```
gh workflow run release-stable.yml -f tag=v0.2.1
```

You should see: the first line is exactly

```
✓ Created workflow_dispatch event for release-stable.yml at main
```

If not: send back the full output of the command.

**b.** Wait two minutes. Then copy this command:

```
gh run list --workflow release-stable.yml --limit 1 --json conclusion --jq '.[0].conclusion'
```

You should see:

```
success
```

If not: when the command prints an empty line, wait one minute and run it again. When it prints `failure`, send back the output of `gh run view --log-failed $(gh run list --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`.

**c.** Copy this command. It updates the first test project:

```
cd ~/agk-stable-test && claude plugin marketplace update agent-graph-kit && claude plugin update agk@agent-graph-kit --scope project && claude plugin list
```

You should see: first these four lines:

```
Updating marketplace: agent-graph-kit...Refreshing marketplace cache (timeout: 120s)…
✔ Successfully updated marketplace: agent-graph-kit
Checking for updates for plugin "agk@agent-graph-kit" at project scope…
✔ Plugin "agk" updated from 0.2.0 to 0.2.1 for scope project. Restart to apply changes.
```

and then, in the list at the end, this block:

```
  ❯ agk@agent-graph-kit
    Version: 0.2.1
    Scope: project
    Status: ✔ enabled
```

If not: send back the full output of the command. Name the version that it shows.

**d.** Copy this command. It runs "release-stable" with `v0.2.0` (the rollback). It works in any folder:

```
gh workflow run release-stable.yml --repo Lighfe/agent-graph-kit -f tag=v0.2.0
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
e2295d77170c5b6398126f62c4e539a285402b12	refs/heads/stable
```

If not: when the first line is empty, wait one minute and run the command again. When it is `failure`, send back the output of `gh run view --repo Lighfe/agent-graph-kit --log-failed $(gh run list --repo Lighfe/agent-graph-kit --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`. When the second line shows another text before `refs/heads/stable`, send back the output of the command.

**f.** Copy this command. It updates the first test project again:

```
cd ~/agk-stable-test && claude plugin marketplace update agent-graph-kit && claude plugin update agk@agent-graph-kit --scope project && claude plugin list
```

You should see: first the same three lines as in action c, then one of these two results. Write down which one you got:

- The rollback reaches a user who already had the newer version. The fourth line is `✔ Plugin "agk" updated from 0.2.1 to 0.2.0 for scope project. Restart to apply changes.`, and in the list the block `❯ agk@agent-graph-kit` has the line `    Version: 0.2.0`.
- The rollback does not reach this user. The fourth line is `✔ agk is already at the latest version (0.2.1).`, and in the list the block `❯ agk@agent-graph-kit` has the line `    Version: 0.2.1`. Claude Code has no downgrade command, so this can happen. The README then has to name the way back.

If not: when the block is missing, or the version is neither of the two, send back the full output of the command.

**g.** Send back the version that you wrote down in action f, with the words "rollback check". The README text on the rollback depends on it.

You should see: an answer that names the version and says what it means for the README.

If not: put the version into a new issue with the title "Rollback check: result".

## After the checklist

- The two test folders `~/agk-stable-test` and `~/agk-dev-test` can be deleted.
- `stable` is now on `v0.2.0` again. To give users the new version, run "release-stable" with the new tag once more (step 7, actions a and b).
