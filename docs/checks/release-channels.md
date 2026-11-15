# Release channels: the owner's checklist

The plugin has two channels. `stable` is for users. `dev` gets every new plugin version first. Agents do not push, set tags or start workflows, so you do the steps below once, by hand, after the stage.

How to use this list:

- Do the steps in order. A step can have more than one action (a, b, c). Each action is one command to copy, or one click.
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

**a.** Click: open `https://github.com/Lighfe/agent-graph-kit/actions` in the browser. In the list on the left, click **release-stable**. Click the button **Run workflow**. Leave "Use workflow from" on `main`. Type `v0.2.0` into the field for the tag. Click the green button **Run workflow**.

You should see: after a few seconds, a new line "release-stable" at the top of the list of runs, with a yellow circle.

If not: when "release-stable" is not in the list on the left, send back the output of `gh workflow list`. When there is no button **Run workflow**, send back a screenshot of the page.

**b.** Wait two minutes. Then copy this command:

```
gh run list --workflow release-stable.yml --limit 1 --json conclusion --jq '.[0].conclusion'
```

You should see:

```
success
```

If not: when the command prints an empty line, the run is not finished; wait one minute and run the command again. When it prints `failure`, send back the output of `gh run view --log-failed $(gh run list --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`.

**c.** Copy this command:

```
git ls-remote origin refs/heads/stable refs/tags/v0.2.0
```

You should see: two lines that start with the same text:

```
e2295d77170c5b6398126f62c4e539a285402b12	refs/heads/stable
e2295d77170c5b6398126f62c4e539a285402b12	refs/tags/v0.2.0
```

If not: send back the output of the command.

**d.** Copy this command:

```
gh release view v0.2.0 --json tagName,isPrerelease,isDraft --jq '.' && gh release list --limit 10
```

You should see: the first line is `{"isDraft":false,"isPrerelease":false,"tagName":"v0.2.0"}`. In the table below it, the row of `v0.2.0` has the word `Latest`.

If not: send back the output of the command.

## Step 4: Install from stable in an empty test project

Your machine already has the marketplace `agent-graph-kit` without a channel. Action a removes it, and action b adds it again on the channel `stable`.

**a.** Copy this command:

```
claude plugin marketplace remove agent-graph-kit
```

You should see: one line that says the marketplace `agent-graph-kit` was removed, and no line with `Error` or `Failed`.

If not: when the output says that no marketplace has this name, go on with action b. For any other output, send it back and stop.

**b.** Copy this command. It makes a new empty folder and adds the channel `stable`:

```
mkdir -p ~/agk-stable-test && cd ~/agk-stable-test && git init -q && claude plugin marketplace add Lighfe/agent-graph-kit#stable
```

You should see: a last line that says the marketplace `agent-graph-kit` was added, and no line with `Error` or `Failed`.

If not: send back the full output of the command.

**c.** Copy this command in the same terminal (the folder is `~/agk-stable-test`):

```
claude plugin install agk@agent-graph-kit --scope project
```

You should see: a last line that says `agk@agent-graph-kit` was installed, and no line with `Error` or `Failed`.

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

You should see: a last line that says the marketplace `agent-graph-kit-dev` was added, and no line with `Error` or `Failed`.

If not: send back the full output of the command.

**b.** Copy this command in the same terminal (the folder is `~/agk-dev-test`):

```
claude plugin install agk@agent-graph-kit-dev --scope project
```

You should see: a last line that says `agk@agent-graph-kit-dev` was installed, and no line with `Error` or `Failed`.

If not: send back the full output of the command.

**c.** Copy this command in the same terminal:

```
claude plugin list
```

You should see: a block `❯ agk@agent-graph-kit-dev` with the line `Version:` and the new version from step 5a.

If not: send back the full output of the command. Name the version that it shows.

## Step 7: Rollback

This step moves `stable` forward to the new tag, and then back to `v0.2.0`. It shows what a user of `stable` gets after a rollback. Both answers in action f are valid results. Write down which one you got.

**a.** Click: open `https://github.com/Lighfe/agent-graph-kit/actions`, click **release-stable** on the left, click **Run workflow**, type the new tag from step 5a (for example `v0.2.1`) into the field for the tag, click the green button **Run workflow**.

You should see: a new line "release-stable" at the top of the list of runs, with a yellow circle.

If not: send back a screenshot of the page.

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

You should see: in the list at the end, the block `❯ agk@agent-graph-kit` has the line `Version:` with the new version from step 5a.

If not: send back the full output of the command. Name the version that it shows.

**d.** Click: open `https://github.com/Lighfe/agent-graph-kit/actions`, click **release-stable** on the left, click **Run workflow**, type `v0.2.0` into the field for the tag, click the green button **Run workflow**.

You should see: a new line "release-stable" at the top of the list of runs, with a yellow circle.

If not: send back a screenshot of the page.

**e.** Wait two minutes. Then copy this command:

```
gh run list --workflow release-stable.yml --limit 1 --json conclusion --jq '.[0].conclusion' && git ls-remote origin refs/heads/stable
```

You should see: the line `success`, and then the line

```
e2295d77170c5b6398126f62c4e539a285402b12	refs/heads/stable
```

If not: when the first line is empty, wait one minute and run the command again. When it is `failure`, send back the output of `gh run view --log-failed $(gh run list --workflow release-stable.yml --limit 1 --json databaseId --jq '.[0].databaseId')`. When the second line shows another text before `refs/heads/stable`, send back the output of the command.

**f.** Copy this command. It updates the first test project again:

```
cd ~/agk-stable-test && claude plugin marketplace update agent-graph-kit && claude plugin update agk@agent-graph-kit --scope project && claude plugin list
```

You should see: in the list at the end, the block `❯ agk@agent-graph-kit` with a line `Version:`. Write down the version in this line. It is one of these two:

- `0.2.0`: the rollback reaches a user who already had the newer version.
- the new version from step 5a: the rollback does not reach this user. Claude Code has no downgrade command, so this can happen. The README then has to name the way back.

If not: when the block is missing, or the version is neither of the two, send back the full output of the command.

**g.** Send back the version that you wrote down in action f, with the words "rollback check". The README text on the rollback depends on it.

You should see: an answer that names the version and says what it means for the README.

If not: put the version into a new issue with the title "Rollback check: result".

## After the checklist

- The two test folders `~/agk-stable-test` and `~/agk-dev-test` can be deleted.
- `stable` is now on `v0.2.0` again. To give users the new version, run "release-stable" with the new tag once more (step 7, actions a and b).
