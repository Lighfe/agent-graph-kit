# Capstone readiness Implementation Plan

> **For agentic workers:** each task below becomes one GitHub issue in `docs/task-template.md` format and runs through the loop in `docs/process.md` (PM, engineer, QA). Do not use subagent-driven-development or executing-plans (see `AGENTS.md`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the repo ready for the AI Dev Tools Zoomcamp capstone: a reworked README with a new picture, a superpowers prerequisite check, release channels `dev`/`stable`, two Grafana alerts, and visible integration tests.

**Architecture:** Docs and small Python scripts in the existing style (standard library, `uv run --script`, pytest). Release logic lives in a tested script; the GitHub workflows only call it. Alerts are Grafana provisioning files in the monitor skill. The picture is a source file in the repo rendered to PNG.

**Tech Stack:** Python 3.10+, pytest, GitHub Actions, Grafana 13 file provisioning, Prometheus rules, headless Chromium (Playwright cache) for screenshots.

**Spec:** `docs/specs/2026-11-14-capstone-readiness.md`

## Global Constraints

- Test command: `uv run --with pytest pytest`; it must pass at the end of each task
- Public repo: no secrets, no real account data, synthetic examples only
- Agents commit, never push, tag or start workflows (`gh workflow run`)
- No plugin version bump in a task (the orchestrator bumps at stage end)
- README has no list or table of course criteria; no repo file maps course criteria to evidence
- The terms "v1" and "v2" do not appear in `README.md`
- Monitor stack: built-in Grafana panels and features only, every port on `127.0.0.1`, no credential in a container
- Tests that check doc text are changed to the new text, not deleted

## Review Focus

- Release script on a version that already has a tag: must do nothing (no second tag, no `dev` move) — test in Task 2
- Release script on a version string that is not `X.Y.Z`: must exit 1 with a message, not tag — test in Task 2
- Production run with a tag that does not exist or whose CI failed: must stop before `stable` moves — test in Task 2
- Alert rule with no data (stack just started, no issue yet): must be `OK`/no data, not firing — test in Task 3
- Setup on a machine where `installed_plugins.json` is missing or not JSON: superpowers line says `CHECK BY HAND`, setup does not crash — test in Task 1

---

### Task 1: superpowers as a checked prerequisite of `/agk:setup`

**Files:**
- Modify: `plugin/skills/setup/setup.py` (`manual_checks`)
- Modify: `plugin/skills/setup/SKILL.md` (list of manual checks)
- Test: `tests/test_setup.py`

**Interfaces:**
- Produces: `superpowers_installed(home: Path) -> bool | None` in `setup.py` (True: a key starting with `superpowers@` in `<home>/.claude/plugins/installed_plugins.json` under `plugins`; False: file readable, no such key; None: file missing or not JSON)
- Produces: setup output line `OK            superpowers plugin`, or `MISSING       superpowers plugin` with `fix: claude plugin install superpowers@claude-plugins-official`, or `CHECK BY HAND superpowers plugin`

- [ ] **Step 1: Write failing tests** `test_superpowers_installed_true`, `..._false`, `..._missing_file_is_none`, `..._bad_json_is_none` (synthetic `installed_plugins.json` in `tmp_path`), and `test_manual_checks_prints_superpowers_fix` asserting the `MISSING` line and the exact install command in stdout
- [ ] **Step 2: Run** `uv run --with pytest pytest tests/test_setup.py -k superpowers -v` — Expected: FAIL (function not defined)
- [ ] **Step 3: Implement** `superpowers_installed` and the line in `manual_checks`, after the Codex login line
- [ ] **Step 4: Run** the full test command — Expected: PASS
- [ ] **Step 5: Commit** `Setup: check that the superpowers plugin is installed`

### Task 2: Release channels `dev` and `stable`

**Files:**
- Create: `scripts/release_channels.py`
- Create: `.github/workflows/release-dev.yml`, `.github/workflows/release-stable.yml`
- Create: `docs/checks/release-channels.md` (the owner's checklist)
- Test: `tests/test_release_channels.py`

**Interfaces:**
- Produces: `scripts/release_channels.py` (standard library, `uv run --script`):
  - `plugin_version(root: Path) -> str` reads `plugin/.claude-plugin/plugin.json`; exits 1 with `not a version: <v>` unless `X.Y.Z`
  - `needs_release(version: str, tags: list[str]) -> bool` — True when `v<version>` is not in `tags`
  - `channel_marketplace(text: str, channel: str) -> str` — returns `.claude-plugin/marketplace.json` text with `name` set to `agent-graph-kit-dev` for `dev` and `agent-graph-kit` for `stable`; any other channel raises `ValueError`
  - CLI: `release_channels.py check` prints `release v<version>` or `no release`; `release_channels.py marketplace <channel>` rewrites the file in place
- Workflow `release-dev.yml`: on push to `main`; runs `check`; when `release …`: runs the test command, creates tag `v<version>`, GitHub pre-release, and force-moves branch `dev` to a commit on top of that tag that only changes the marketplace name (`marketplace dev`). Permissions `contents: write`
- Workflow `release-stable.yml`: `workflow_dispatch` with input `tag`; fails when the tag does not exist or the `release-dev` run for it did not succeed; moves branch `stable` the same way (`marketplace stable`); marks the release as latest

- [ ] **Step 1: Write failing tests**: `needs_release("0.2.1", ["v0.2.0"]) is True`; `needs_release("0.2.0", ["v0.2.0"]) is False`; `plugin_version` on `"0.2"` exits 1 with `not a version`; `channel_marketplace(text, "dev")` gives name `agent-graph-kit-dev` and keeps `plugins` unchanged; `"stable"` gives `agent-graph-kit`; `"main"` raises `ValueError`
- [ ] **Step 2: Run** `uv run --with pytest pytest tests/test_release_channels.py -v` — Expected: FAIL
- [ ] **Step 3: Implement** `scripts/release_channels.py`
- [ ] **Step 4: Write the two workflows**; add a test that loads both YAML files and checks: triggers (`push` on `main`; `workflow_dispatch` with input `tag`), `contents: write`, the test command step before any tag step, and that each calls `release_channels.py`. Check both with `actionlint` when it is available (name the version in DONE), else say so
- [ ] **Step 5: Write `docs/checks/release-channels.md`**: numbered steps for the owner, each one copy-paste command or one named click, then "You should see: …" with the exact expected output, then "If not: …" with what to send back. Steps: (1) push `main`; (2) tag `v0.2.0` on `e2295d7` and push the tag; (3) Actions tab, run "release-stable" with `v0.2.0`; (4) in an empty test project add `Lighfe/agent-graph-kit#stable` and install, see version 0.2.0; (5) after the next stage-end bump is pushed, see the new tag, the pre-release and `dev` moved; (6) add `#dev` (name `agent-graph-kit-dev`) in a test project, see the new version; (7) rollback: run "release-stable" with the older tag, update in the test project, record what version it shows. Plain words; no workflow internals
- [ ] **Step 6: Run** the full test command — Expected: PASS
- [ ] **Step 7: Commit** `Release channels: dev on version bump, stable by a manual run`

### Task 3: Alerts: runaway issue and stuck launch

**Files:**
- Create: `plugin/skills/monitor/grafana/provisioning/alerting/agk-alerts.yaml`
- Modify: `plugin/skills/monitor/compose.yaml` (Grafana env: `AGK_ALERT_ISSUE_TOKENS`, `AGK_ALERT_STUCK_MINUTES`)
- Modify: `plugin/skills/monitor/SKILL.md` (section "Alerts")
- Test: `tests/test_monitor_alerts.py`

**Interfaces:**
- Consumes: `agk:tokens:1m` (labels `agk_project`, `stage`, `issue`, `role`, `kind`, `model`) and `agk_marker{agk_project, stage, issue, role, launch}`
- Produces: two provisioned rules in folder "agk", titles `Runaway issue` and `Stuck launch`, data source uid `agk-prometheus`, no contact point that needs a secret; `noDataState: OK`

- [ ] **Step 1: Read the default runaway limit from real data**: with the stack up (`board.py up`), query the token sum per issue of the Stage 21 issues; limit = 2 × largest, rounded to a whole million. Note number and query for DONE
- [ ] **Step 2: Write failing tests**: the file parses; two rules with the titles above; runaway query sums `agk:tokens:1m` by `agk_project, issue` over the issue's life and compares with `${AGK_ALERT_ISSUE_TOKENS}`; stuck rule uses `agk_marker` with `for` of `${AGK_ALERT_STUCK_MINUTES}m` and no token increase for that issue; `noDataState` is `OK`; compose sets both variables with defaults (runaway from step 1, stuck `45`); all ports still on `127.0.0.1`
- [ ] **Step 3: Run** `uv run --with pytest pytest tests/test_monitor_alerts.py -v` — Expected: FAIL
- [ ] **Step 4: Implement** the provisioning file and the compose variables (check that Grafana expands environment variables in alert provisioning files; if not, `board.py` writes the values)
- [ ] **Step 5: Live check**: `board.py up`, then the Grafana API (`/api/v1/provisioning/alert-rules`, admin password from the password file, not printed) lists both rules, state not firing on current data. Record in DONE
- [ ] **Step 6: Write SKILL.md "Alerts"**: what each alert means, the two variables, where to see them in Grafana
- [ ] **Step 7: Run** the full test command — Expected: PASS
- [ ] **Step 8: Commit** `Monitor: alerts for a runaway issue and a stuck launch`

### Task 4: Integration tests marked

**Files:**
- Modify: `tests/conftest.py` (register marker `integration`)
- Modify: test files whose tests run a real tool or a whole flow (for example `tests/test_setup.py` runs, `tests/test_monitor_rules.py` promtool tests, `tests/test_qa_codex.py` launcher flows)
- Test: `tests/test_markers.py`

**Interfaces:**
- Produces: `pytest -m integration` and `pytest -m "not integration"` select the two groups; the plain test command runs both

- [ ] **Step 1: Write failing test** `test_integration_marker_registered_and_used`: running `pytest --collect-only -q -m integration` in a subprocess collects at least 20 tests and no `PytestUnknownMarkWarning`
- [ ] **Step 2: Run** it — Expected: FAIL
- [ ] **Step 3: Register the marker** in `conftest.py` (`pytest_configure`, `config.addinivalue_line("markers", "integration: runs a real tool or a whole flow")`) and mark the tests. A test counts as integration when it starts a subprocess of a real tool or script, or runs a flow over several components
- [ ] **Step 4: Run** the full test command — Expected: PASS; note both group counts for DONE
- [ ] **Step 5: Commit** `Tests: mark integration tests`

### Task 5: Lovable frontend lane in its own file

**Files:**
- Create: `docs/lovable-frontend-lane.md`
- Modify: `README.md` (remove "Lovable frontend lane (optional, v2)" and "Frontend lane (optional)"; one line with the link in the set-up steps and in Prerequisites)
- Modify: `tests/test_readme_lovable_v2.py` (rename to `tests/test_lovable_lane_doc.py`, read the new file), `tests/test_doc_paths.py` (`README_SECTIONS`)

**Interfaces:**
- Produces: `docs/lovable-frontend-lane.md` with sections "Set-up", "QA pre-step", "Accepted risk", "How Lovable pauses"; the README links it as `docs/lovable-frontend-lane.md`

- [ ] **Step 1: Change the tests** to read `docs/lovable-frontend-lane.md` (same step order and content checks); add `test_readme_links_lovable_doc` and `test_readme_has_no_lovable_steps` (`git submodule add -b main` not in README)
- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Move the content** without loss; no "v2" in headings
- [ ] **Step 4: Run** the full test command — Expected: PASS
- [ ] **Step 5: Commit** `Docs: Lovable frontend lane in its own file`

### Task 6: README rework

**Files:**
- Modify: `README.md`
- Create: `docs/assets/monitoring-board.png` (screenshot)
- Modify: tests that read README sections: `tests/test_doc_paths.py`, `tests/test_docs_orchestrator_run_record.py`, `tests/test_docs_planner_relabel.py`, `tests/test_docs_plugin_update_route.py`, `tests/test_setup.py`, `tests/test_plugin.py`, `tests/test_docs_memory_rule.py`, `tests/test_docs_spend_waiver_awaiting_input.py`
- Modify: files that link README anchors that change (find with `grep -rn "README.md#"`), and `plugin/skills/setup/setup.py` text that names README sections

**Interfaces:**
- Consumes: Task 1 output line and install command; Task 2 channel names, install commands (`Lighfe/agent-graph-kit#stable`, `#dev`), `docs/checks/release-channels.md`; Task 3 alert names and variables; Task 4 marker; Task 5 doc path
- Produces: README sections in this order: title + picture, `## Purpose`, `## What the kit does`, `## Set-up the Agent Graph Kit`, `## Update the kit`, `## Monitoring`, `## Development note`, `## Development and release`, `## Docs`

- [ ] **Step 1: Change the README tests** to the new section names and content: Purpose holds the owner's text with "rogue", "opposite", "lose"; no "v1"/"v2" in README; no "Project set-up reference", no "Run record" heading, no "Monitoring board (optional)"; set-up Prerequisites name superpowers with `claude plugin install superpowers@claude-plugins-official`; the four Auto mode entries, the Codex trust entry and the repo-owner rule are inside the set-up section; install commands use `#stable`; "Update the kit" names both channels and the switch of an older install (`claude plugin marketplace remove agent-graph-kit`, then the add with `#stable`); Monitoring names `board.py up`/`down`, `http://127.0.0.1:3000`, the password file, both alerts, and shows `docs/assets/monitoring-board.png`; Development and release names the test command, `-m integration`, the CI on push and pull request, `dev`/`stable`, the rollback, and links `docs/checks/release-channels.md`; no course criteria list
- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Rewrite the README** per Part A of the spec (purpose text from the spec, corrected only as listed there; "What the kit does" short)
- [ ] **Step 4: Screenshot**: `board.py up`, headless Chromium to the board with the token panels for Stage 21 (not the active-time panels), saved as `docs/assets/monitoring-board.png`; no personal data visible (check the image: no e-mail, no account id)
- [ ] **Step 5: Fix every link** to a removed or renamed README anchor
- [ ] **Step 6: Run** the full test command — Expected: PASS
- [ ] **Step 7: Commit** `README: purpose, one set-up route, monitoring, development and release`

### Task 7: New overview picture

**Files:**
- Create: `docs/assets/overview/` (source file `overview.svg` or `overview.html`, logo SVGs, `LICENSES.md` with source and licence of each logo and the font)
- Replace: `docs/assets/agk-overview.png`
- Modify: `README.md` (alt text only)
- Test: `tests/test_overview_picture.py`

**Interfaces:**
- Consumes: Task 6 README (picture at the top, path `docs/assets/agk-overview.png`)

Content and style (spec Part E): whiteboard look (off-white paper, slightly rough hand-drawn lines, font Kalam, logos as coloured stickers); "You" is a pixel-art person with teal hair, glasses, medium-brown skin and a magenta top; loop "one stage" in orange (You → `/stage-start` → Planner → "stage ready, /goal" → Orchestrator → "stage review" → You); loop "one issue" in blue inside "GitHub Issues: every handoff is a comment" (PM → Software engineer → QA engineer; FAIL back to the engineer; PASS closes at the orchestrator); orchestrator "launch" into the issue loop with a shield "hooks check every handoff"; bottom: "Monitoring: OTel → Prometheus · Loki → Grafana, in Docker" and "Release: GitHub Actions → dev / stable". Real logos: Claude, OpenAI (Codex), Lovable (engineer, optional lane), GitHub, GitHub Actions, OpenTelemetry, Prometheus, Grafana, Loki, Docker, superpowers; a clean text badge where no official logo exists. No line crosses a label. Built from scratch; the brainstorm sketches are not used.

- [ ] **Step 1: Write failing tests**: source file exists; `LICENSES.md` names every logo file in the folder; PNG at least 1600 px wide; README alt text names "one stage" and "one issue"
- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Build** the source, fetch the logos (for example Simple Icons, pinned version), render to PNG with headless Chromium
- [ ] **Step 4: Check the PNG by eye** against the content list above; attach the list with a yes per item to DONE
- [ ] **Step 5: Run** the full test command — Expected: PASS
- [ ] **Step 6: Commit** `README: new overview picture`

## Order and blockers

Tasks 1, 2, 3, 4 and 5 are independent. Task 6 is blocked by 1 to 5. Task 7 is blocked by 6.
