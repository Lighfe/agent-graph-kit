# README maintenance and overview image

## Purpose

The README tells a new reader that the kit is a working Claude Code plugin (work in progress), and it opens with one picture that shows what the kit is.

## Problem

- The README intro says "Later, this repo becomes a Claude Code plugin." The kit already is one: `agk`, work in progress.
- The README has no picture. A new reader sees only text.

## Requirements

### R1: README text is current

- The sentence "Later, this repo becomes a Claude Code plugin." is gone. The intro says that the kit is a working Claude Code plugin, `agk`, and that it is work in progress.
- Other statements of the intro and of "Status" that are out of date are fixed in the same way. The set-up steps are not changed.

### R2: Overview image at the start of the README

- The image is the first element after the title of `README.md`, with alt text.
- A reader understands two things in five seconds: this is Agentic Graph Engineering, and the kit uses state-of-the-art AI tools.
- The image shows the headline "Agentic Graph Engineering"; the graph of the agent team (orchestrator, planner, PM, software engineer, QA engineer) with handoff edges; and the tools Claude Code, Codex and Lovable.
- Style: it must not look like standard AI-generated art. Dark, technical, system-diagram look; real node names; monospaced labels; one sharp accent colour. No robots, glowing brains or purple gradients.
- The image is made by Lovable, as a one-off project: a single page that is screenshotted to a PNG. The PNG is kept in the repo at `docs/assets/agk-overview.png`. The Lovable project is not part of the repo; its URL is named in the report of the task.

## Non-goals

- A full, in-depth visualization. That comes when the kit is fully developed.
- The Lovable frontend lane (`frontend/` submodule). This repo has none.
- Changes to the plugin files. No plugin version bump.

## Decisions

- QA is enough for the image; the owner does not review it before it enters the README.
- Codex is not available in this stage. QA runs through the `qa-engineer` fallback.
- Lovable cannot return an image. The PNG is a browser screenshot of the Lovable preview.
