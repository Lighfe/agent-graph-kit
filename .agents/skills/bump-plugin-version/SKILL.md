---
name: bump-plugin-version
description: Release the agk plugin with a new version. Use only in this repo; the orchestrator runs it once at the end of a stage that changed the plugin.
---

# Bump the plugin version

The plugin cache of an installed project is keyed by the version in `plugin/.claude-plugin/plugin.json`. A changed plugin with the same version never reaches a project. So the version is raised once per stage, at the end of the stage, not in each task.

Run `uv run scripts/bump_plugin_version.py`. It builds the plugin copies, raises the patch number, writes `scripts/plugin-release.json` and checks that `scripts/build_plugin.py --release-status` prints `released`. When the status is `released` already, it changes nothing. When a step fails, it restores both files and exits non-zero.

Then run the test command of `AGENTS.md` and commit the bump.

This skill is for this repo only. It is not part of the plugin.
