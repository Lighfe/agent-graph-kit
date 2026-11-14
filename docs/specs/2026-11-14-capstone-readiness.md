# Capstone readiness: README, release channels, alerts

## Purpose

The owner submits this repo as the final project of the DataTalksClub AI Dev Tools Zoomcamp (criteria: https://github.com/DataTalksClub/ai-dev-tools-zoomcamp/tree/main/project). The plugin `agk` is the application. A peer reviewer who opens the repo understands in a few minutes what problem the kit solves, how it works, how to set it up, how it is tested and released, and how its work is monitored. The kit also gains a real release path (dev and stable channels with a manual production step) and two alerts on what hurts the user of the kit.

## Why now

The OTel monitoring stage (Stage 21) is done and released as 0.2.0. The README still describes older states of the kit ("v1", "v2", the SQLite board, the run record), the Lovable lane fills half of it, and the course criteria for CI/CD and alerting are not met.

## Goals

- The README tells the owner's story (purpose), says what the kit does, and walks a new user through set-up in one route
- The tests, the release path, the containers and the boards are easy to find from the README, in its normal sections
- A version bump at stage end reaches a `dev` channel automatically after the tests pass; the `stable` channel moves only by a manual GitHub Actions run; an older release can be put back
- Two Grafana alerts exist: a runaway issue and a stuck launch
- A new overview picture opens the README

## Non-goals

- On-call agent (owner decision: not done)
- Traces and a shared trace ID across signals
- The board fixes from the Stage 21 review (active time per role, steps of a launch, launches-table faults, smaller query fixes, personal data in the Collector, the project list on `up`). They go to the next stage, together with what the owner finds while looking at the boards
- Alert delivery by e-mail, chat or desktop notification (it would need a secret or a new host process)
- A demo video
- Retiring the run record itself. Only its README section goes

## Anti-goals

- A README that reads like a feature list or marketing. It is the owner's story plus a working route
- A picture that looks like standard AI art, or that shows the flow wrongly
- A release step that lets an untested version reach `stable`
- A rough sketch ending up as the final picture

## Visibility

The README shows each part of the work in its natural place: the problem in Purpose, the behaviour in What the kit does, the containers and the boards in Monitoring, the tests and the release path in Development and release. The README has no list or table of course criteria, and no file in the repo maps the course criteria to evidence. The owner keeps such a checklist privately, outside git.

## Parts

### Part A: README rework

New order of `README.md`:

1. Title and the new picture (Part E)
2. **Purpose**: the owner's draft below, with only these corrections: "rouge" to "rogue", "oppsosite" to "opposite", "loose" to "lose", and small grammar fixes that do not change the meaning. The version in the development note is the released version at the time of writing (0.2.0 or later)
3. **What the kit does**: short. What happens after `/stage-start` (the planner plans a stage with you: spec, plan, issues), after `/goal` (the orchestrator runs each issue through PM, engineer and QA; hooks check every handoff; the stage ends with a stage review), and what the owner sees at the end (closed issues, a stage review, a released plugin version, the boards)
4. **Set-up the Agent Graph Kit**: replaces "Start a new project". Prerequisites name the superpowers plugin (Part B). Everything from "Project set-up reference" that a user still needs moves into the steps: the repo-owner rule (one line), the Codex trust entry, the Auto mode entries (all four, including the run-record writer entry while the orchestrator still writes the run record). The section "Project set-up reference" is removed. Install commands use the `stable` channel; a line names the `dev` channel for testing
5. **Update the kit**: as today, adapted to the channels
6. **Monitoring**: replaces "Run record" and "Monitoring board (optional)" (the SQLite board no longer exists). What the boards show, the two commands (`board.py up`, `board.py down`), URL and password file, the alerts, a link to `plugin/skills/monitor/SKILL.md`, and one screenshot of a board that shows correct numbers (token panels; not the active-time panels, which are known to be wrong). The engineer takes it on the owner's machine with the stack up and the Stage 21 data, with a headless browser; no owner step
7. **Development note**: the owner's dogfooding text
8. **Development and release**: how the tests run (unit and integration, one command, CI on every push and pull request), and how a release goes (version bump at stage end, tests, `dev`, manual run to `stable`, rollback). Short, with the commands
9. **Docs**: links to the living spec, specs, process, team, archive

Also:

- The terms "v1" and "v2" are gone from the README
- The Lovable frontend lane (set-up steps, QA pre-step, accepted risk) moves to `docs/lovable-frontend-lane.md` without loss of content; the README keeps one line and a link in the set-up steps
- "How the hooks work" stays as one line with its link
- Every README anchor that other files or tests point to is updated with them; the tests that check README text are changed to the new text, not deleted

Owner's purpose draft (source text for item 2 and 7):

```
# Purpose

When pursuing AI driven development projects I continuously ran into the following issues:
- Agents going "rouge" and taking the initiative where I didn't want that
- Also the oppsosite: Agents relying too much on me and escalating unnecessary
- Documentation drift and out-of-date specs lurking somewhere
- Spec-driven development turns into maintaining, fixing, patching specs with more and more overhead
- Project, scope, code and docs grow larger and larger and both AI and I loose focus
- Project hitting a dead-end where I realize that we had a faulty assumption or took a wrong turn at some point

The meta-question I've been pursuing in this project is: << How do I want to work with AI agents following a spec-driven development approach? >>

The Agent Graph Kit is a project for my personal use that sets up my agentic graph engineering exactly the way that I want to work, heavily inspired by the AI-Native Development approach from Alexey Grigorev (DataTalks.Club). It allows me to start any new project and have my agents behave the way that I want from the get go.

On two things I focused here:
1. A principled AI development approach that follows the graph engineering paradigm
2. Staying in the loop as human driving direction and purpose of the projects while not having to babysit agents at the same time

Three things this project is not:
1. The most time- and token efficient way to build applications
2. An AI safety harness. While I use hooks to enforce certain behaviors, these cannot withhold malicious attacks.
3. State-of-the-art Agentic AI. There are most likely better existing (open source) products out there that already solved very similar issues. This plugin itself makes heavy use of Jesse Vincent's superpowers plugin, e.g. for brainstorming and writing the spec/plan.

## Development Note

The plugin was developed with a software development method called "dogfooding": While improving the agent graph kit, I used the agent graph kit itself for development. The product can be found in the plugin/ folder. But at the same time you can see that the very same agents, hooks, and skills can be found at project root. As an addition to testing on this project only, the plugin was installed on new test projects as well as on real development project: https://github.com/Lighfe/quack-rl

In docs/archive you can see the documented development process. I started first with the agents and hooks, then made those available as claude marketplace plugin. Process improvements and streamlined skills have followed. Monitoring with OpenTelemetry and Grafana dashboard is the newest addition for version 0.2.0.
The agent-graph-kit plugin is publicly available on claude marketplace and can be conveniently set-up and updated.
```

### Part B: superpowers as a prerequisite

The planner uses the superpowers skills (brainstorming, writing-plans), but neither the README nor `/agk:setup` names the superpowers plugin. The README prerequisites name it with its install command. `/agk:setup` checks whether the superpowers plugin is installed (user or project scope) and, when it is not, prints the install command as a manual step. Setup does not install it.

### Part C: Release channels (CI/CD)

Facts from the Claude Code plugin docs (checked 2026-11-14):

- A marketplace can be added at a ref: `claude plugin marketplace add owner/repo#ref`
- Claude Code has no release channels; the documented pattern is two marketplaces, each at its own ref, with different marketplace `name` values
- Users get a new copy only when the plugin version changes
- No downgrade command exists

Design:

- `main` stays the work branch. No user installs from it after this stage
- **CD to dev**: a GitHub Actions workflow runs on a push to `main`. When the plugin version in `plugin/.claude-plugin/plugin.json` has no tag yet, it runs the test command, and only when the tests pass: creates the tag `v<version>`, creates a GitHub pre-release for it, and moves the branch `dev` to that commit with the marketplace name `agent-graph-kit-dev` in `.claude-plugin/marketplace.json` of that branch. A push without a version change does nothing beyond the normal CI
- **Production**: a second workflow with a manual start (`workflow_dispatch`) and one input, the tag. It checks that the tag exists and that its CI run passed, moves the branch `stable` to that tag (marketplace name `agent-graph-kit`), and marks the release as the latest release
- **Rollback**: run the production workflow with an older tag. The task checks in a real install whether a user on the newer version gets the older copy; when not, it documents the working way back in the README (for example a pinned ref)
- The stage-end bump by the orchestrator stays as it is (`scripts/bump_plugin_version.py`); the owner's push of that commit starts CD
- The existing CI workflow keeps running the tests on every push and pull request
- The README install commands use `#stable`; the update section covers both channels and the rollback
- Agents commit but do not push, tag or start workflows. The stage builds and tests the workflows offline (the logic that decides "new version, tag it" and "move `stable` to this tag" lives in a script with unit tests; the workflow files are checked with a linter). The live steps are the owner's, after the stage, from a checklist `docs/checks/release-channels.md`:
  - push `main`, set the tag `v0.2.0` on `e2295d7`, start the production run for `v0.2.0`, push the next version bump and see `dev` move, install from `dev` and `stable` in a test project, run the rollback
  - each step is one copy-paste command or one named click, followed by "you should see: …" with the exact expected output, and "if not: …" with what to send back
  - plain words, numbered steps, no step that needs knowledge of the workflow internals
- `.claude-plugin/marketplace.json` on `main` stays as it is (name `agent-graph-kit`). Existing users who added the marketplace without a ref switch with `claude plugin marketplace remove agent-graph-kit` and an add with `#stable`; the README says so
- First release: the tag `v0.2.0` is set on the release commit of Stage 21 (`e2295d7`), and `stable` starts there, so the rollback check has an older tag to go back to

### Part D: Alerts

Two Grafana alert rules, provisioned from files in the monitor skill (`grafana/provisioning/alerting/`), shown in the Grafana alert list. No contact point that needs a secret.

- **Runaway issue**: fires when one issue's tokens exceed a limit. The count is the same as on the boards: `agk:tokens:1m` with all token kinds (cache included), Claude and Codex together, summed per project and issue over the issue's whole life (within Prometheus retention). The default limit is twice the largest issue of Stage 21 on real data, rounded to a whole million; the builder reads it from Prometheus and names the number and the query in `## Engineer: DONE`. Matches the owner's story of agents going "rogue"
- **Stuck launch**: fires when `agk_marker` shows the same launch in work for 45 minutes and no tokens were counted for that issue in that time. Codex tokens are part of `agk:tokens:1m` (role `qa-codex`), so a long Codex QA run that uses tokens does not count as stuck
- Both limits are environment variables in `compose.yaml` with the defaults above, read by the Grafana provisioning; the README and `SKILL.md` name them
- Tests check the rule files (query, threshold, duration) without starting Grafana, in the style of the existing board tests; a live check shows both rules loaded in Grafana

### Part E: Overview picture

Replaces `docs/assets/agk-overview.png`. Decided with the owner on throwaway sketches:

- Style: whiteboard sketch. Off-white paper, hand-drawn lines (slight roughness), font Kalam, logos as coloured stickers
- "You": a pixel-art person with teal hair, glasses, medium-brown skin and neutral clothes (magenta top). Not a man or woman stereotype
- Two loops, each in its own colour: **one stage** (orange: You, `/stage-start`, Planner, "stage ready, `/goal`", Orchestrator, "stage review" back to You) and **one issue** (blue, inside a "GitHub Issues: every handoff is a comment" area: PM, Software engineer, QA engineer; FAIL goes back to the engineer; PASS closes at the orchestrator). The orchestrator launches into the issue loop; a shield marks "hooks check every handoff"
- Bottom: "Monitoring: OTel, Prometheus, Loki, Grafana, in Docker" and "Release: GitHub Actions, dev / stable"
- Real logos for: Claude (planner, orchestrator, PM, engineer, Claude QA), OpenAI/Codex (QA), Lovable (engineer, as the optional frontend lane), GitHub, GitHub Actions, OpenTelemetry, Prometheus, Grafana, Loki, Docker, superpowers (planner). Where no official logo is available, a clean text badge
- Every label is readable: no line crosses text
- The picture is built from scratch as a source file kept in the repo (SVG or HTML) and rendered to PNG; logo sources and licences are listed next to it. The throwaway sketches are not used as source
- The picture goes into the README after `## QA: PASS`. The owner checks it at the stage review; changes become a follow-up

### Part F: Integration tests made visible

The suite already has tests that run real tools or whole flows (for example the setup run in a temp project, the stack and rule checks). Mark them with a pytest marker `integration`, register the marker, and name in the README (Development and release) how to run each group. The single test command stays `uv run --with pytest pytest` and runs both.

## Decided by the owner

- The plugin is the application for the capstone
- Scope "B": README, superpowers prerequisite, Lovable doc, picture, release channels, alerts, integration tests visible. Not the board fixes, not traces, no on-call agent
- CD to dev at each version bump (stage end), not at every merge
- Two release branches `dev` and `stable`, production by a manual run
- Both alerts: runaway issue and stuck launch
- README items: the purpose draft, Lovable to its own file, no "v1"/"v2", no "Project set-up reference", "Start a new project" renamed to "Set-up the Agent Graph Kit", Monitoring section with screenshot instead of Run record, superpowers in set-up, a new picture
- Picture: whiteboard style, teal-hair person, two loops, real logos; the owner checks it after it is in, at the stage review
- The live release steps are done by the owner after the stage, from a clear, easy checklist; no agent gets push or workflow permissions
- The owner looks at the boards on their own; the findings go to the next stage. First findings (2026-11-14, only two issues had data): "Tokens per stage, by role" should not be stacked; on "Selected stage: tokens per issue, by role" the issues do not add up to the stage total

## My calls (planner)

- Font Kalam (the owner approved the sketch that used it)
- The run record's Auto mode entry stays in the set-up steps while the orchestrator still writes the run record
- Alerts are visible in Grafana only; no notification channel
- Runaway limit from real data (twice the largest Stage 21 issue), counted like the boards; 45 minutes for a stuck launch; limits as environment variables in `compose.yaml`
- The stuck-launch alert counts Codex tokens, so no Codex caveat
- `marketplace.json` on `main` stays; current users switch with remove and add `#stable`
- First release: tag `v0.2.0` on `e2295d7`, `stable` starts there

## Left to the builder

- Exact wording of "What the kit does", within the content above
- Workflow file names and how the `dev`/`stable` branches carry their marketplace name (commit on the branch, or a generated file)
- The PromQL of the alert rules
- The tool used to render the picture to PNG
- Which tests get the `integration` marker, as long as the README names what the integration tests cover
