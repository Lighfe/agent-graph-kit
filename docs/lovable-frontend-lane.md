# Lovable frontend lane (optional)

The base kit works without this lane. Use it only when a project has a frontend that Lovable builds. The lane is linked from the set-up steps in [README.md](../README.md).

## Prerequisites

Optional, needed only for the frontend lane (skip this block when you do not use Lovable):

- The Claude Code plugin `lovable`. The tool names in `.claude/agents/frontend-engineer.md` depend on it.
- The tools for the install command of `frontend/`. The QA pre-step picks it from the lockfile in `frontend/`: with an npm lockfile (`package-lock.json` or `npm-shrinkwrap.json`) it runs `npm ci`, else with a bun lockfile (`bun.lock` or `bun.lockb`) it runs `bun install --frozen-lockfile`, else it posts `## QA: UNAVAILABLE`. So an npm frontend needs `npm` and `npx`, and a bun frontend needs `bun` on `PATH`.
- A Lovable workspace with enough credits, and a Playwright dependency in the frontend (see "Set-up" below).

## Set-up

Do these steps in order. No MCP tool can make the GitHub connection of a Lovable project, so you do steps 2 to 4 by hand:

1. Create the Lovable project.
2. Connect the Lovable workspace to GitHub (one time per workspace).
3. Connect the project: Project settings -> Git -> GitHub -> Connect.
4. Make the new GitHub repo of the Lovable project public.
5. Add it as the `frontend/` submodule, tracking `main`:

   ```bash
   git submodule add -b main <Lovable repo URL> frontend
   ```

6. Add Playwright as a dev dependency through Lovable (QA needs it for the headless browser). Send the Lovable project a chat prompt, for example:

   > Add `@playwright/test` as a dev dependency, update the lockfile, do not add tests.

   Then check in the Lovable GitHub repo that the new commit changed `package.json` (`@playwright/test` under `devDependencies`) and the lockfile (`bun.lock` or `package-lock.json`).
7. Bump the `frontend` submodule in the project to that commit, and commit the new pointer. The QA worktree checks out the commit that the submodule records, not the newest commit of the Lovable repo:

   ```bash
   git submodule update --remote frontend
   git add frontend
   git commit -m "Bump frontend to the commit with the Playwright dependency"
   ```

8. Add the line `Lovable project: <project id>` to `AGENTS.md`. `frontend-engineer` reads the project id from this line. The id is in the Lovable project URL. Example with a synthetic id:

   ```
   Lovable project: 00000000-0000-4000-8000-000000000000
   ```

9. Set the Lovable project knowledge once per Lovable project (project settings in the Lovable editor). You set it yourself: the `frontend-engineer` has no tool to set project knowledge. The entry holds the standing constraints for all frontend work and the way Lovable works with the `frontend-engineer`, so the loop does not repeat them in every message. Example with a synthetic text:

   ```
   Standing constraints for all work in this project:
   - Do not add a new drawing library.
   - Do not add a new random-number library.
   - Keep the `@playwright/test` dev dependency.

   How you work with the frontend-engineer, who supervises your work:
   - Write a plan first and stop. Do not change code at this point.
   - Implement the plan only after the frontend-engineer has confirmed it.
   - If the frontend-engineer asks for corrections, send a new plan and wait again.
   ```

10. Install the `lovable` plugin.

Nobody edits `frontend/` locally. All frontend changes go through Lovable.

## How Lovable pauses

Lovable can pause a message and wait for input. A plan or a question comes as a finished reply: the `frontend-engineer` checks the plan against the issue and approves or corrects it with a new message. A tool approval comes as an `awaiting_input` pause: the `frontend-engineer` answers it with `respond_to_approval`, never with a new message (a new message rejects the pending tool). It approves a tool that fits the issue and rejects any other. It posts `## Engineer: BLOCKED`, and the issue is escalated to you, when the pause needs a secure form (you answer it in the Lovable editor, the engineer never enters a secret), when the tool concerns credits, a spend limit or a payment, or when it cannot tell what the tool does. A credit or spend-limit pause needs you also when your `AGENTS.md` says Lovable credits need no owner approval. Check that the Lovable workspace has enough credits before a frontend issue gets the label `ready`. If you have an Auto mode allow entry that lists the `frontend-engineer` Lovable tools, it must also list `respond_to_approval`; otherwise a deny of that call ends the launch as `## Engineer: BLOCKED`.

## QA pre-step

The set-up steps are in "Set-up" above.

The QA pre-step installs the frontend dependencies with the install command that follows the lockfile in `frontend/`: an npm lockfile (`package-lock.json` or `npm-shrinkwrap.json`) gives `npm ci`, else a bun lockfile (`bun.lock` or `bun.lockb`) gives `bun install --frozen-lockfile`, else the result is `## QA: UNAVAILABLE`. If both kinds exist, `npm ci` runs. A bun frontend (Lovable projects often use bun) needs `bun` on `PATH`; without it, the result is `## QA: UNAVAILABLE`.

The frontend needs a Playwright dependency: `playwright` or `@playwright/test` (as a dev dependency: step 6 of "Set-up") in `dependencies` or `devDependencies` of `frontend/package.json`, and in its lockfile. Without it, the result is `## QA: UNAVAILABLE`, and nothing is installed. After the install, the pre-step installs the browser with the Playwright CLI of that dependency, through the package manager of the lockfile: `npx --no playwright install chromium` (npm lockfile) or `bun x --no-install playwright install chromium` (bun lockfile). `--no` and `--no-install` stop a registry fetch, so the browser version follows the frontend's lockfile and nothing is fetched from the registry for it. A bun frontend does not need `npx`.

## Accepted risk

This risk is described in "Worktree and pre-step" in [the spec](specs/agent-graph-kit.md#worktree-and-pre-step). The QA pre-step runs code from the repository outside the Codex sandbox, with your environment and access. This happens on three paths: the lifecycle scripts (`preinstall`, `install`, `postinstall`, `prepare`) of `frontend/package.json` and of every dependency with `npm ci`, or of the dependencies bun trusts (`trustedDependencies` and bun's default trusted list) with `bun install`; the package manager config `frontend/.npmrc` or `frontend/bunfig.toml`; and the Playwright CLI from `frontend/node_modules`, which the lockfile decides. This is accepted because the frontend code comes from your own Lovable project and from the loop's engineer (issue #50). The remaining risk includes packages that agents add: a new dependency or version that Lovable or another agent of the loop puts into `package.json` or the lockfile runs with your access at the next QA run, before QA or you have looked at it. Nothing in the loop checks it first. Treat changes to `frontend/package.json`, the lockfile, `.npmrc`, `bunfig.toml` or `trustedDependencies` as review items.
