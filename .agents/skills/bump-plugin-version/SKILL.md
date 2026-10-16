---
name: bump-plugin-version
description: Release the agk plugin with a new version. Use only in this repo, once, as the last task of a stage that changed the plugin ("Bump the plugin version").
---

# Bump the plugin version

The plugin cache of an installed project is keyed by the version in `plugin/.claude-plugin/plugin.json`. A changed plugin with the same version never reaches a project. So the version is raised once per stage, as the last task of the stage, not in each task.

Run these steps in order, once:

1. Run `scripts/build_plugin.py` so the generated copies in `plugin/` match their sources.
2. Raise the patch number of `version` in `plugin/.claude-plugin/plugin.json` (for example `0.1.1` to `0.1.2`).
3. Write the new `version` and the output of `scripts/build_plugin.py --hash` as `sha256` to `scripts/plugin-release.json`.
4. Run the tests: `uv run --with pytest pytest`.
5. Run `scripts/build_plugin.py --release-status`. It must print `released`.

This skill is for this repo only. It is not part of the plugin.
