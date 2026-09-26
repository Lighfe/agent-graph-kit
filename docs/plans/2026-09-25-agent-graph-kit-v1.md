# agent-graph-kit v1 Implementation Plan

Execution is deferred. In a later session, convert these tasks to issues using docs/task-template.md and follow docs/process.md.

**Goal:** Turn the prose loop PM → Engineer → QA into a graph. Hooks check every prescribed handoff call. Codex is the default QA checker. Frontend work goes to Lovable.

**Architecture:** A `PreToolUse` hook (`.claude/hooks/guard.py`) reads the issue state with one `gh` call. It checks guarantees G1–G7 as small pure functions (`.claude/hooks/issue_state.py`) and posts a launch comment before an allowed launch. `scripts/qa-codex` runs `codex exec` with a JSON schema and posts the QA comment. The `codex-review` skill uses the same runner (`scripts/codex_exec.py`). The frontend lane is one subagent file plus one section in the engineer role file.

**Tech Stack:** Python ≥ 3.11 (stdlib only) run with `uv run --script` (PEP 723), pytest, `gh`, `git`, Codex CLI, Lovable MCP, GitHub Actions.

**Spec:** `docs/specs/2026-09-25-agent-graph-kit-v1.md`

## Global Constraints

- Hooks check only the calls in spec 5.1. All other calls pass (P1).
- Hooks check facts only: labels, comment markers, SHAs, git status. No LLM or Jev judgment blocks anything (P2).
- The state lives on the issue. Hooks and scripts read it with `gh` (P3).
- Few agent-facing files. Each prose change is as small as possible (P4).
- No keys in commits, issues, comments or reviews. Examples are synthetic (P5).
- Python scripts run with `uv run --script` and a PEP 723 header. Plan decision: stdlib only (`dependencies = []`), so the test command below can import every module.
- Test command: `uv run --with pytest pytest`. No network in tests.
- Any hook error (failing `gh`, failing `git`, crash) produces a deny. A crash never lets a call through, except when Claude Code kills the hook at its settings `timeout` (spec 5.6; owner decision 2026-09-26).
- Codex may write its trust entry for a repo into `$HOME/.codex/config.toml` (spec 6.2). Do not change anything else in `$HOME/.codex/`.
- Each deny message names the failed check, for example `G3: current result is ## QA: PASS, expected ## PM: GROOMED or ## QA: FAIL`.
- Result markers are the exact first lines in spec 5.5. The launch line is exactly `ROLE=<role> ISSUE=<number>`.
- `qa-codex`: default timeout 30 minutes. Transient retries wait 1, 3 and 10 minutes. Frontend engineer: time budget 60 minutes per launch.

## Review Focus

1. **Guarded text in commands that are not guarded.** `grep "gh issue close" AGENTS.md`, `cat scripts/qa-codex`, or a commit message that mentions `qa-codex` must pass. `gh  issue close 5` (extra whitespace) is still guarded. `gh issue close` or `qa-codex` in a compound command (`a && gh issue close 5`, `(gh issue close 5)`, `gh issue close 5 &`) or in a command substitution (`echo "$(gh issue close 5)"`) must be denied. Tests are in Task 5.
2. **The hook fails in some way.** If `gh` is missing or offline, `git` fails, the input JSON is broken, or `uv` cannot start, the call is denied, never allowed. Tests are in Task 5, and a smoke check is in Task 7.
3. **Stale or odd comments.** These cases are covered:
   - A late result from an earlier attempt.
   - A result without a launch of its role (not valid, owner decision).
   - A first line with CRLF.
   - A marker with extra text (`## QA: PASS (re-check)` is not a marker).
   - Two launch lines in one prompt.

   Tests are in Task 4 and Task 5.
4. **Codex output that almost matches.** A missing or duplicated criterion id, or a short verified SHA, gives one retry and then `## QA: INVALID`. Criteria are matched by number, not by text. Tests are in Task 6.
5. **An issue without acceptance criteria.** `qa-codex` must post `## QA: INVALID` and must never post a PASS with zero criteria. Tests are in Task 6.

## Notes for the reader

- **Task format.** Each task is one future issue in `docs/task-template.md` format. Files, interfaces, dependencies and steps are under **Constraints** ("guidelines to follow"). Steps are numbered, so that only acceptance criteria use checkboxes. At intake, the `####` headings become `##`.
- **Owner decisions of 2026-09-25** (they fill gaps in the spec):
  1. The Codex QA schema has the criterion verdict `pass | fail | invalid`. If any criterion is `invalid`, the result is `## QA: INVALID`. The overall verdict field stays `pass | fail`, and the script derives the verdict.
  2. paint-math is two tasks. The owner runs the demo loop in paint-math (Tasks 11 and 12).
  3. A result without a launch comment of its role is not valid.
  4. Section 5.8 needs no role-file change. The launch line is only in the orchestrator's prompt template.
- **Owner decisions of 2026-09-26** on the S1–S3 findings are merged into the spec (sections 5.6, 5.7, 5.9, 6, 7, 8, 9, 12.4) and into Tasks 5–11 below. History: `docs/archive/2026-09-26-s1-3-owner-decisions.md`. Where a task below and the spec differ, the spec wins.
- **Plan decisions** (no spec change):
  - The hook module, the guard and `qa-codex` are built before the hooks are wired (Task 7). If the hooks were wired earlier, QA would deadlock: G4 needs `qa-codex`, and G5 needs `## QA: UNAVAILABLE`.
  - The shared Codex runner is `scripts/codex_exec.py`.
  - The comment order comes from the `gh` comments array, not from timestamps.
  - On a Codex failure, `codex-review` writes no file and reports the error to the owner.
  - `qa-codex` reads the range literally from the `## Engineer: DONE` comment (spec 6.1).
  - In AGENTS.md, only the issue list command changes for 5.8. The launch line, the markers and the pending state go into `docs/team/orchestrator.md`.
- **Spec section 11 (Files) is redundant for planning.** The file map below replaces it. The spec is unchanged.
- **Intake notes (later session).** Each "Not in v1" row of spec section 3 becomes an issue with the label `later`, and the note after the dash goes into the issue body. The owner creates the label `later` if it is missing.

## File map

| File | Task | Responsibility |
|---|---|---|
| `docs/research/spike-claude-code-hooks.md` | 1 | S1 findings |
| `docs/research/spike-codex-cli.md` | 2 | S2 findings |
| `docs/research/spike-lovable-mcp.md` | 3 | S3 findings |
| `.claude/hooks/issue_state.py` | 4 | Parse the issue, validity, pending, current result, checks G1–G7, launch comment text |
| `tests/conftest.py`, `tests/helpers.py`, `tests/test_issue_state.py` | 4 | Test set-up, synthetic issues, check tests |
| `.github/workflows/ci.yml` | 4 | CI runs the test command |
| `.claude/hooks/guard.py` | 5 | Hook entry point: classify the call, read facts, post the launch comment, deny on any error |
| `tests/test_guard.py`, `tests/fakes/gh`, `tests/fakes/git` | 5 | Tests for classification and the entry point |
| `scripts/codex_exec.py` | 6 | Run `codex exec` and classify failures (shared) |
| `scripts/qa-codex`, `scripts/qa-result.schema.json` | 6 | Codex QA launcher and result schema |
| `tests/test_qa_codex.py`, `tests/fakes/codex` | 6 | Tests for each failure type |
| `.claude/settings.json` | 7 | Hook registration, allow and deny rules |
| `docs/checks/hook-activation.md` | 7 | Owner's acceptance test after activation |
| `.agents/skills/codex-review/SKILL.md`, `review.py`, `review.schema.json` | 8 | Codex review skill |
| `tests/test_codex_review.py` | 8 | Renderer test |
| `.claude/agents/frontend-engineer.md` | 9 | Frontend lane subagent |
| `README.md` | 10 | Set-up section |
| prose: `AGENTS.md`, `docs/process.md`, `docs/team/*.md`, `docs/task-template.md` | 4, 6, 7, 8, 9 | Smallest changes, listed per task |

## Dependencies

| Task | Depends on |
|---|---|
| 1 S1, 2 S2, 3 S3 | – |
| 4 Issue state and checks | 1 |
| 5 Guard hook | 1, 4 |
| 6 qa-codex | 2, 4 |
| 7 Hook wiring | 1, 4, 5, 6 |
| 8 codex-review | 2, 6, 7 |
| 9 Frontend lane | 2, 3, 7 |
| 10 README set-up | 7, 8, 9 |
| 11 paint-math set-up | 3, 9, 10 |
| 12 paint-math demo run | 11 |

After Task 7 is closed, all later tasks run with the hooks on (spec 12.3).

---

### Task 1: Spike S1 – Claude Code hooks

Lane: default

#### Goal

Find out if Claude Code `PreToolUse` hooks can carry the guarantees of spec section 5, and write the answers with evidence to `docs/research/spike-claude-code-hooks.md`.

#### Acceptance criteria

- [ ] The findings file answers each question below with yes, no or a value, and gives the evidence (the hook input or output, the command, the observed behavior; secrets redacted)
- [ ] Q1: Does a hook before a subagent launch see the agent type and the prompt? Give the exact tool name (`Agent` or `Task`) and the field names
- [ ] Q2: Can the hook deny with a reason that the caller sees? Which output reliably denies: exit code 2, or the JSON `permissionDecision: "deny"`?
- [ ] Q3: Does the deny work in auto mode and in bypass-permissions mode?
- [ ] Q4: Can a Bash hook reliably match `scripts/qa-codex ROLE=qa ISSUE=<n>` and `gh issue close <n>` from `tool_input.command`? Does it also fire for a Bash call with `run_in_background`?
- [ ] Q5: Do hooks fire for tool calls inside subagents?
- [ ] Q6: Can a hook post a comment (a side effect) before the call runs, and does the call wait for the hook?
- [ ] Q7: What happens when the hook script crashes (exit code other than 0 and 2), when `uv` cannot start, and when the hook times out? Does the settings command wrapper `… || { echo "…" >&2; exit 2; }` turn these cases into a deny?
- [ ] Q8: Are project hooks read once at session start (a snapshot), or does an edit of `.claude/settings.json` take effect mid-session? Is a trust or review step needed?
- [ ] The file ends with "Consequences for the plan": for each of Tasks 4, 5 and 7, "holds" or the change that is needed, and "Owner decision needed: yes/no"

#### Out of scope

- Implementing the guard hook (Task 5) or registering it in this repo (Task 7)

#### Constraints

- Run all experiments in a scratch repo outside this repo, for example `$TMPDIR/s1-hooks`. Commit only the findings file.
- Use throwaway issues in a scratch GitHub repo or no issues at all (Q6 can be tested with a local file write instead of `gh`). Do not post test comments on this repo's issues.
- Read the current Claude Code hooks documentation, then confirm each answer by experiment.

**Files:** Create `docs/research/spike-claude-code-hooks.md`

**Steps:**

1. Create the scratch repo with `.claude/settings.json` and a hook that appends its stdin JSON to a log file and exits 0. Matcher: `Agent|Task|Bash`.
2. In a Claude session in the scratch repo, launch a subagent with a prompt that contains `ROLE=pm ISSUE=1`. Read the log (Q1, Q5: let the subagent run a Bash command).
3. Change the hook to deny with `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"G1: test"}}` and exit 0. Try it, then try exit code 2 with a stderr message. Repeat in auto mode and in bypass-permissions mode (Q2, Q3).
4. Log `tool_input.command` for `scripts/qa-codex ROLE=qa ISSUE=1` (a stub script), for `gh issue close 1 --reason completed` (with `gh` replaced by a stub on `PATH`), and for the same qa-codex call with `run_in_background` (Q4).
5. Let the hook `sleep 5` and write a file before it exits. Check that the tool call starts only after that (Q6).
6. Make the hook `exit 1`, make `uv` fail (`PATH` without `uv`), and make the hook sleep longer than its `timeout`. Record for each whether the call runs. Repeat with the `|| exit 2` wrapper (Q7).
7. Edit the hook in `.claude/settings.json` mid-session and check if the change applies (Q8).
8. Write the findings file with the sections Questions and answers, Evidence, and Consequences for the plan. Commit it.

---

### Task 2: Spike S2 – Codex CLI

Lane: default

#### Goal

Find out how `codex exec` behaves for `qa-codex` and `codex-review`, and write the answers with evidence to `docs/research/spike-codex-cli.md`.

#### Acceptance criteria

- [ ] The findings file answers each question below with evidence (command, exit code, the relevant stdout/stderr lines; secrets redacted)
- [ ] Q1: `--output-schema` and `-o`: does the file contain only the final JSON? Which schema rules are required (for example `additionalProperties: false` and all properties required)? What happens when the model output does not match?
- [ ] Q2: Can the prompt come from stdin (`codex exec … -`)? Which flag sets the working directory?
- [ ] Q3: What does each sandbox mode allow: run tests, run the app, write temp files, use the network, run a headless browser?
- [ ] Q4: Can Codex run a headless browser (for example Playwright with Chromium) in a non-interactive run, and with which sandbox setting? Name the most restrictive sandbox that allows QA to exercise the behavior
- [ ] Q5: How does each error show, as exit code and error text: network error, server error, rate limit, usage limit, not logged in, not installed? Give a regex for each that `scripts/codex_exec.py` can use
- [ ] Q6: Timeout behavior: does killing the process group stop all children (browser, dev server)?
- [ ] The file ends with "Consequences for the plan": for each of Tasks 6, 8 and 9, "holds" or the change that is needed, and "Owner decision needed: yes/no". If Q4 is "no", this section says that the owner decides before Task 9 (spec 9.3)

#### Out of scope

- Writing `scripts/codex_exec.py` or `scripts/qa-codex` (Task 6)

#### Constraints

- Run experiments in a scratch directory outside this repo. Commit only the findings file.
- Simulate the errors without harming the owner's set-up: no network (for example `unshare -n` or an offline network namespace), a wrong `CODEX_HOME` for "not logged in", `PATH` without `codex` for "not installed". Rate limit and usage limit: record them if they can be observed, otherwise quote the text from the Codex source or docs and mark it "not observed".
- Never copy an auth token or a key into the findings.

**Files:** Create `docs/research/spike-codex-cli.md`

**Steps:**

1. Write a small schema (`{"type":"object","additionalProperties":false,"required":["ok"],"properties":{"ok":{"type":"boolean"}}}`) and run `codex exec --output-schema s.json -o out.json -` with the prompt on stdin (Q1, Q2).
2. In a scratch project with one test and a tiny web app, run `codex exec` in each sandbox mode with the prompt "run the tests, start the app, write /tmp/x, fetch http://localhost:<port>". Record what worked (Q3).
3. Install Playwright in the scratch project. Ask Codex to open the page headless and report the page title. Try the sandbox modes from strict to open (Q4).
4. Produce each error as described in Constraints (Q5), and a timeout with `timeout` or a kill of the process group (Q6).
5. Write the findings file with the sections Questions and answers, Evidence, Error table (status, exit code, regex), and Consequences for the plan. Commit it.

---

### Task 3: Spike S3 – Lovable MCP

Lane: default

#### Goal

Find out how the frontend engineer can drive Lovable through MCP and pin the exact commit of a Lovable change, and write the answers with evidence to `docs/research/spike-lovable-mcp.md`.

#### Acceptance criteria

- [ ] Q1: How to detect that a Lovable message has finished (tool, field, value). Include how long a small change took
- [ ] Q2: When Lovable's commit reaches GitHub (delay after "finished"), and how to identify the exact commit of one Lovable change (for example an id in the message or edit record that matches a commit, or the commit message)
- [ ] Q3: Can the GitHub connection of a Lovable project be made through MCP? If not, list the manual steps for the owner
- [ ] Q4: The exact MCP tool names that `.claude/agents/frontend-engineer.md` needs in `tools:`
- [ ] Each answer has evidence: tool calls and relevant output, the commit SHAs, with no keys or tokens
- [ ] The file ends with "Consequences for the plan": for each of Tasks 9 and 11, "holds" or the change that is needed, and "Owner decision needed: yes/no"

#### Out of scope

- The paint-math repo and its Lovable project (Task 11)
- The `frontend-engineer` agent (Task 9)

#### Constraints

- Ask the owner before you create a Lovable project or send messages that use credits. Use one throwaway project. The owner deletes it afterwards.
- Commit only the findings file.

**Files:** Create `docs/research/spike-lovable-mcp.md`

**Steps:**

1. List the Lovable MCP tools that are available. Note which ones create projects, send messages, read message status, list edits and read diffs (Q4).
2. After the owner agrees, create a throwaway project with a one-line app. Connect it to a throwaway GitHub repo, through MCP if possible, otherwise record the manual steps (Q3).
3. Send one small change ("change the page title to X"). Poll the message or edit status until it is finished. Record the fields and the time (Q1).
4. Poll `git ls-remote <repo>` until the new commit appears. Record the delay and how the commit maps to the Lovable change (Q2).
5. Write the findings file and commit it.

---

### Task 4: Issue state and checks G1–G7

Lane: default

#### Goal

A stdlib module computes the state of an issue from its `gh` JSON (valid results, pending, current result, returns, lane, SHAs) and runs checks G1–G7 as pure functions. The tests run in CI with the project test command.

#### Acceptance criteria

- [ ] `uv run --with pytest pytest` passes, and runs tests for each of G1–G7 (allow and deny), without network
- [ ] A result counts as valid only if its first line is a marker of its role and it comes after the newest launch comment of that role. A result without any launch of its role is not valid
- [ ] The issue is pending when the newest launch has no result of its role and no `## Owner: RESUME` after it
- [ ] The current result is the newest valid result or `## Owner: RESUME`, whichever is newer
- [ ] G7 counts only `## QA: FAIL` and `## Engineer: BLOCKED` comments after the newest `## Owner: RESUME` that have a launch of their role before them. The launch is denied at 3
- [ ] A first line with `\r` or trailing spaces still matches. `## QA: PASS (re-check)` does not match
- [ ] G6 compares the full 40-character `Verified:` SHA with `HEAD`. A short SHA is not equal
- [ ] `## Launch: <role> (continued, round <n>)` counts as a launch comment of its role for validity, pending, G7 and the launch number (spec 5.3). For a continued call, G3 checks the result but not the agent
- [ ] Each deny message starts with the check id (`G1:` … `G7:`) and names what was found and what was expected. (The launch line itself is checked by the guard in Task 5, also as `G1:`)
- [ ] AGENTS.md shows the test command `uv run --with pytest pytest`, and `.github/workflows/ci.yml` runs exactly this command on push and pull request

#### Out of scope

- Reading the hook input, calling `gh` or `git`, and posting comments (Task 5)
- Registering the hook (Task 7)

#### Constraints

- Depends on S1 (Task 1). If the S1 findings change the design, the owner decides before this task starts.
- Stdlib only. No I/O in `issue_state.py`.

**Files:**
- Create: `.claude/hooks/issue_state.py`, `tests/conftest.py`, `tests/helpers.py`, `tests/test_issue_state.py`, `.github/workflows/ci.yml`
- Modify: `AGENTS.md` (the "Test command" line)

**Interfaces (produced, used by Tasks 5 and 6):**

```python
# .claude/hooks/issue_state.py
MARKERS: dict[str, tuple[str, ...]]   # role -> result markers, spec 5.5
RESUME = "## Owner: RESUME"
AGENT_LANE = {"default": "software-engineer", "frontend": "frontend-engineer"}

@dataclass(frozen=True)
class Issue:
    number: int
    open: bool
    labels: frozenset[str]
    body: str
    comments: tuple[str, ...]          # comment bodies, oldest first

@dataclass(frozen=True)
class Facts:
    issue: Issue
    head: str                          # full SHA of HEAD
    clean: bool                        # git status --porcelain is empty

@dataclass(frozen=True)
class Call:
    role: str                          # "pm" | "engineer" | "qa" | "close"
    agent: str                         # "pm", "software-engineer", "frontend-engineer", "qa-engineer", "qa-codex"; "" for close; the SendMessage target for a continuation
    issue: int
    continued: bool = False            # a SendMessage continuation (spec 5.3)

def parse_issue(data: dict) -> Issue            # from `gh issue view N --json number,state,labels,body,comments`
def first_line(body: str) -> str
def is_pending(issue: Issue) -> bool
def current_result(issue: Issue) -> tuple[int, str] | None   # (comment index, marker)
def returns_since_resume(issue: Issue) -> int
def lane(issue: Issue) -> str | None            # value of the first `Lane: <value>` line of the body
def verified_sha(body: str) -> str | None       # `Verified: <sha>`
def commits_range(body: str) -> tuple[str, str] | None   # `Commits: <base>..<head>`
def newest_done(issue: Issue) -> str | None     # body of the newest valid `## Engineer: DONE`
def attempt(issue: Issue, role: str) -> int     # launches of that role (attempt and continued) + 1
def launch_comment(call: Call, attempt: int) -> str   # "(continued, round <n>)" if call.continued
def check(call: Call, facts: Facts) -> str | None   # None = allow, else the deny message
```

**Steps:**

1. Write `tests/conftest.py` so tests can import the hook and script modules:

   ```python
   import sys
   from pathlib import Path

   ROOT = Path(__file__).resolve().parents[1]
   sys.path[:0] = [str(ROOT / ".claude" / "hooks"), str(ROOT / "scripts"), str(ROOT / "tests")]
   ```

2. Write `tests/helpers.py` with a synthetic-issue builder and synthetic SHAs:

   ```python
   from issue_state import Facts, Issue

   HEAD = "a" * 40
   OLD = "b" * 40

   def launch(role, n=1, agent=None):
       agent = agent or {"pm": "pm", "engineer": "software-engineer", "qa": "qa-codex"}[role]
       return f"## Launch: {role} (attempt {n})\nAgent: {agent}"

   def issue(*comments, labels=("ready",), body="Lane: default\n", open=True):
       return Issue(number=7, open=open, labels=frozenset(labels), body=body, comments=tuple(comments))

   def facts(iss, head=HEAD, clean=True):
       return Facts(issue=iss, head=head, clean=clean)
   ```

3. Write failing tests in `tests/test_issue_state.py`. For example:

   ```python
   from helpers import HEAD, OLD, facts, issue, launch
   from issue_state import Call, check, current_result, is_pending

   ENG = Call(role="engineer", agent="software-engineer", issue=7)
   CLOSE = Call(role="close", agent="", issue=7)

   def test_result_without_launch_is_not_valid():
       assert current_result(issue("## PM: GROOMED")) is None

   def test_newest_launch_without_result_is_pending():
       iss = issue(launch("engineer"), "## Engineer: DONE\nCommits: x..y",
                   launch("qa"), "## QA: FAIL", launch("engineer", 2))
       assert is_pending(iss)
       assert check(ENG, facts(iss)).startswith("G1:")

   def test_resume_ends_pending_and_sends_issue_to_pm():
       iss = issue(launch("engineer"), "## Owner: RESUME")
       assert not is_pending(iss)
       assert check(ENG, facts(iss)).startswith("G3:")

   def test_crlf_first_line_matches_but_suffix_does_not():
       assert current_result(issue(launch("pm"), "## PM: GROOMED\r\nx"))[1] == "## PM: GROOMED"
       assert current_result(issue(launch("qa"), "## QA: PASS (re-check)")) is None

   def test_g6_needs_full_verified_sha_equal_head():
       iss = issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD[:7]}")
       assert check(CLOSE, facts(iss)).startswith("G6:")
       iss = issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")
       assert check(CLOSE, facts(iss)) is None

   def test_g7_denies_third_return():
       iss = issue(launch("pm"), "## PM: GROOMED",
                   launch("engineer"), "## Engineer: DONE\nCommits: x..y", launch("qa"), "## QA: FAIL",
                   launch("engineer", 2), "## Engineer: DONE\nCommits: x..y", launch("qa", 2), "## QA: FAIL",
                   launch("engineer", 3), "## Engineer: DONE\nCommits: x..y", launch("qa", 3), "## QA: FAIL")
       assert check(ENG, facts(iss)).startswith("G7:")
   ```

   Also add allow and deny cases for:
   - G1: dirty tree, closed issue, labels `later` or `needs-owner`, missing `ready`
   - G2: first launch, after BLOCKED, after RESUME, denied after GROOMED
   - G3: the lane does not match the agent, the Lane line is missing
   - G4: after DONE; re-check after PASS with an old SHA (allowed); PASS with SHA = HEAD (denied); DONE without a `Commits:` line (denied)
   - G5: only after UNAVAILABLE
   - continued: a `(continued, round 2)` comment makes the issue pending, makes a following result valid, and counts for `attempt`; a continued engineer call after `## QA: FAIL` passes G3 with any agent name

4. Run `uv run --with pytest pytest tests/test_issue_state.py -v`. Expected: FAIL (`ModuleNotFoundError: issue_state`).
5. Implement `issue_state.py`. The core of validity and pending:

   ```python
   LAUNCH = re.compile(r"^## Launch: (pm|engineer|qa) \((?:attempt|continued, round) (\d+)\)$")

   def first_line(body: str) -> str:
       return body.split("\n", 1)[0].rstrip()

   def _lines(issue): return [first_line(c) for c in issue.comments]

   def _result_role(line):
       return next((r for r, ms in MARKERS.items() if line in ms), None)

   def _launch_role(line):
       m = LAUNCH.match(line)
       return m.group(1) if m else None

   def _newest_launch(lines, role=None):
       idx = [i for i, l in enumerate(lines) if _launch_role(l) and (role is None or _launch_role(l) == role)]
       return idx[-1] if idx else None

   def _valid(lines, i):
       role = _result_role(lines[i])
       j = _newest_launch(lines, role) if role else None
       return j is not None and i > j

   def is_pending(issue):
       lines = _lines(issue)
       j = _newest_launch(lines)
       if j is None:
           return False
       role = _launch_role(lines[j])
       return not any(l == RESUME or _result_role(l) == role for l in lines[j + 1:])
   ```

   Every check is a function `(call, facts) -> str | None`. `check` runs G1, then the role checks: pm → G2, G7; engineer → G3, G7; qa → G4 if `agent == "qa-codex"`, G5 if `agent == "qa-engineer"`; close → G6.
6. Run `uv run --with pytest pytest -v`. Expected: all tests PASS.
7. Replace the test command line in AGENTS.md with: `Test command: uv run --with pytest pytest. Never report tests as passed if no test ran.`
8. Create `.github/workflows/ci.yml`. Use the current major version of `astral-sh/setup-uv`:

   ```yaml
   name: ci
   on: [push, pull_request]
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v6
         - run: uv run --with pytest pytest
   ```

9. Commit: `git add .claude/hooks/issue_state.py tests .github/workflows/ci.yml AGENTS.md && git commit -m "Add issue state module with checks G1-G7, tests and CI"`

---

### Task 5: Guard hook entry point

Lane: default

#### Goal

`.claude/hooks/guard.py` turns a `PreToolUse` event into a guarded call or a pass. It reads the facts with `gh` and `git`, runs the checks from Task 4, and posts the launch comment. Any error produces a deny.

#### Acceptance criteria

- [ ] A subagent launch of `pm`, `software-engineer`, `frontend-engineer` or `qa-engineer` is guarded. Other agent types pass without any `gh` call
- [ ] A launch needs exactly one line `ROLE=<role> ISSUE=<n>` whose role matches the agent. Otherwise it is denied with `G1:`
- [ ] Every Bash command is tokenized (there is no raw-text prefilter). A simple command is guarded if its tokens start with `gh issue close`, or its first word ends in `qa-codex`, or it runs `qa-codex` through `uv` or `python`. `gh  issue close 5` (extra spaces or tabs) is guarded. `grep "gh issue close" AGENTS.md` and `cat scripts/qa-codex` pass
- [ ] A guarded call is denied when the command has any shell operator (`;`, `&&`, `||`, `|`, `&`, newline, `(`, `)`)
- [ ] The text inside `$(…)` or backticks is checked as a command of its own. If it contains a guarded call, the whole command is denied. A heredoc commit message that only mentions `qa-codex` passes
- [ ] A command that cannot be parsed is denied if its text contains `gh` or `qa-codex`, and passes otherwise
- [ ] `gh issue close` is allowed only with exactly one issue number made of digits. `-R`/`--repo`, unknown options, leading `VAR=value` assignments and a missing or second number are denied
- [ ] `qa-codex` is allowed only with exactly the arguments `ROLE=qa ISSUE=<n>`
- [ ] When allowed, a launch posts `## Launch: <role> (attempt <n>)` with the line `Agent: <agent>` before the call runs. Close posts nothing
- [ ] A `SendMessage` call is guarded like a launch: it needs exactly one launch line in its message, otherwise `G1:`. When allowed, it posts `## Launch: <role> (continued, round <n>)` with `Agent: <target>`
- [ ] A Bash command that writes to `.claude/settings*.json` is denied with `G8:`. Cases: `echo '{"disableAllHooks": true}' > .claude/settings.local.json`, `cd .claude && tee settings.local.json`, `cp x .claude/settings.json`, `mv`, `sed -i`, `python -c "…settings.local.json…"`. `cat .claude/settings.json` and `jq . .claude/settings.json` pass. When unsure, deny
- [ ] The guard has one overall deadline (default 60 s) for all its work, including the lock wait. When it is reached, the guard denies with a message that names the deadline. Tests set a short deadline through the environment
- [ ] The guard holds an exclusive file lock (in the git dir) from reading the facts until the launch comment is posted. A test runs two guards for launches on the same issue at the same time: exactly one launch comment is posted, and the other guard denies with `G1:` (pending)
- [ ] A failing `gh`, a failing `git`, a failing comment post, and an internal error each produce the deny JSON on stdout with exit code 0 (tests run the script as a subprocess with fake `gh`/`git` on `PATH`)
- [ ] An allowed call produces no output (the normal permission flow stays on)
- [ ] `uv run --with pytest pytest` passes

#### Out of scope

- Registering the hook in `.claude/settings.json` (Task 7)

#### Constraints

- Depends on S1 (Task 1): the tool name, the input field names and the deny format come from the findings (`docs/research/spike-claude-code-hooks.md`, Q1, Q2, Q7, Q9, Q10).
- The `SendMessage` input fields are not confirmed yet (expected: `to`, `message`, `summary`). Confirm them with a logging hook in a scratch repo, as in S1, before you implement the `SendMessage` branch.
- Uses `issue_state` (Task 4). Stdlib only. Each `gh`/`git` call has a timeout of 20 seconds, and all calls together stay within the overall deadline (spec 5.6). The settings `timeout` (Task 7) is 120 s.
- Never output `"allow"` (S1 Q10: it skips the normal permission check).
- The deny reason contains at most the first line of an error's stderr, cut to 200 characters (P5).

**Files:**
- Create: `.claude/hooks/guard.py`, `tests/test_guard.py`, `tests/fakes/gh`, `tests/fakes/git`

**Interfaces:**
- Consumes: `issue_state.Call`, `Facts`, `parse_issue`, `check`, `attempt`, `launch_comment` (Task 4).
- Produces: `guard.py` (run as `uv run --script .claude/hooks/guard.py`, input on stdin) and:

```python
class Deny(Exception): ...
def split_command(command: str) -> tuple[list[list[str]], int]   # (simple commands, number of operators); raises ValueError
def substitutions(token: str) -> list[str]                  # texts inside $(…) and backticks; raises ValueError if unbalanced
def classify(event: dict) -> Call | None                     # None = not guarded; raises Deny
def decide(event: dict, read_facts, post_comment) -> str | None   # deny reason or None
def main(stdin=sys.stdin, stdout=sys.stdout) -> int          # always returns 0
```

**Steps:**

1. Write failing tests in `tests/test_guard.py` for `classify`:

   ```python
   import pytest
   from guard import Deny, classify

   def bash(cmd): return {"tool_name": "Bash", "tool_input": {"command": cmd}}
   def agent(t, prompt): return {"tool_name": "Agent", "tool_input": {"subagent_type": t, "prompt": prompt}}

   @pytest.mark.parametrize("cmd", ['grep -n "gh issue close" AGENTS.md', "cat scripts/qa-codex",
                                    'git commit -m "run qa-codex later"', "ls",
                                    "git commit -m \"$(cat <<'EOF'\nAdd qa-codex launcher\nEOF\n)\""])
   def test_unguarded_bash_passes(cmd):
       assert classify(bash(cmd)) is None

   @pytest.mark.parametrize("cmd", ["echo hi && gh issue close 5", "gh issue close 5; ls",
                                    "gh issue close 5 -R other/repo", "gh issue close", "gh issue close 5 6",
                                    "GH_REPO=x/y gh issue close 5", "scripts/qa-codex ROLE=qa",
                                    "gh issue close 'unterminated", "(gh issue close 5)", "gh issue close 5 &",
                                    'echo "$(gh issue close 5)"', "echo `scripts/qa-codex ROLE=qa ISSUE=5`"])
   def test_unclear_guarded_bash_is_denied(cmd):
       with pytest.raises(Deny):
           classify(bash(cmd))

   def test_close_and_qa_codex_are_parsed():
       assert classify(bash("gh issue close 12 --reason completed")).issue == 12
       assert classify(bash("gh  issue close 12")).issue == 12
       assert classify(bash("gh\tissue close 12")).issue == 12
       call = classify(bash("scripts/qa-codex ROLE=qa ISSUE=12"))
       assert (call.role, call.agent, call.issue) == ("qa", "qa-codex", 12)

   def test_launch_line_must_match_agent():
       with pytest.raises(Deny):
           classify(agent("pm", "ROLE=engineer ISSUE=3"))
       with pytest.raises(Deny):
           classify(agent("pm", "ROLE=pm ISSUE=3\nROLE=pm ISSUE=4"))
       assert classify(agent("Explore", "anything")) is None
   ```

2. Write failing entry-point tests. They run `guard.py` as a subprocess with `PATH` set to `tests/fakes` first. `tests/fakes/gh` and `tests/fakes/git` are small Python scripts (executable) controlled by the environment:
   - `FAKE_GH_FAIL=1` makes `gh` exit 1.
   - `FAKE_GH_ISSUE=<path>` holds the JSON that `gh issue view` prints.
   - `FAKE_GH_LOG=<path>` records `gh issue comment` bodies.
   - `FAKE_GIT_FAIL=1` makes `git` exit 128.

   The script checks each case:

   ```python
   def run_guard(event, **env):
       p = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), text=True,
                          capture_output=True, env={**os.environ, "PATH": f"{FAKES}:{os.environ['PATH']}", **env})
       return p.returncode, p.stdout

   def is_deny(out): return json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"

   def test_failing_gh_denies(tmp_path):
       code, out = run_guard(bash("gh issue close 5"), FAKE_GH_FAIL="1")
       assert code == 0 and is_deny(out)
   ```

   Also add:
   - failing `git`
   - broken stdin (`{`)
   - an internal error: call `guard.main` in-process with `issue_state.check` monkeypatched to raise
   - a failing comment post
   - an allowed launch that writes exactly one launch comment and prints nothing
3. Run `uv run --with pytest pytest tests/test_guard.py -v`. Expected: FAIL (`ModuleNotFoundError: guard`).
4. Implement `guard.py`:

   ```python
   #!/usr/bin/env -S uv run --script
   # /// script
   # requires-python = ">=3.11"
   # dependencies = []
   # ///
   SUBAGENT_TOOLS = {"Agent", "Task"}           # per S1 findings; SendMessage is a continuation (spec 5.3)
   DEADLINE_S = int(os.environ.get("GUARD_DEADLINE", "60"))   # spec 5.6
   AGENT_ROLE = {"pm": "pm", "software-engineer": "engineer",
                 "frontend-engineer": "engineer", "qa-engineer": "qa"}
   OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}

   def split_command(command):
       lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
       lex.whitespace_split = True
       cmds, cur, ops = [], [], 0
       for tok in lex:
           if tok in OPERATORS:
               ops += 1
               cmds.append(cur); cur = []
           else:
               cur.append(tok)
       cmds.append(cur)
       return [c for c in cmds if c], ops

   def main(stdin=sys.stdin, stdout=sys.stdout):
       try:
           reason = decide(json.load(stdin), read_facts, post_comment)
       except Deny as e:
           reason = str(e)
       except BaseException as e:                 # a crash must never allow the call
           reason = f"guard error: {type(e).__name__}: {str(e)[:200]}"
       if reason:
           stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
               "permissionDecision": "deny", "permissionDecisionReason": reason}}))
       return 0

   if __name__ == "__main__":
       sys.exit(main())
   ```

   How `classify` handles a Bash command (there is no raw-text prefilter, so whitespace variants cannot slip through):
   - If `split_command` raises `ValueError`: it raises `Deny` if the text contains `gh` or `qa-codex`, otherwise it returns `None`.
   - For each token, it calls `substitutions(token)` and classifies each inner text the same way (recursively). If an inner text contains a guarded call, it raises `Deny`.
   - If a simple command is guarded and the operator count is not 0, or there is more than one simple command, it raises `Deny`.
   - Otherwise it parses the single guarded command (close number or `qa-codex` arguments), or returns `None`.
   - A heredoc body line that starts with a guarded call is denied. This is a false deny, which is safe; the engineer rewrites the command.

   `read_facts` runs `gh issue view N --json number,state,labels,body,comments`, `git rev-parse HEAD` and `git status --porcelain`, each with `check=True, timeout=20`. `post_comment` runs `gh issue comment N --body-file -` with the body on stdin.
5. Run `uv run --with pytest pytest -v`. Expected: all tests PASS.
6. Commit: `git add .claude/hooks/guard.py tests && git commit -m "Add guard hook entry point with deny on any error"`

---

### Task 6: Codex QA launcher `qa-codex`

Lane: default

#### Goal

`scripts/qa-codex ROLE=qa ISSUE=<n>` runs Codex QA on the range of the newest `## Engineer: DONE`, validates the JSON, and posts one QA comment. Each failure type follows spec 6.2. `docs/team/qa-engineer.md` describes the QA behavior of spec 7 for both checkers.

#### Acceptance criteria

- [ ] With a fake `codex` that returns valid JSON, the script posts `## QA: PASS` or `## QA: FAIL`, derived from the criterion verdicts, with one line per criterion, `Tests:`, `Verified: <HEAD>` and `Checker: codex`
- [ ] If any criterion verdict is `invalid`, the script posts `## QA: INVALID` and names the criterion and its reason
- [ ] A transient error is retried up to 3 times with waits of 1, 3 and 10 minutes. If all retries fail, the result is `## QA: INVALID`
- [ ] A timeout (default 30 minutes) is retried once, then the result is `## QA: INVALID`. On a timeout, the whole process group is killed
- [ ] Output that does not match the schema, a missing or duplicated criterion id, or a verified SHA other than the full `HEAD` is retried once, then the result is `## QA: INVALID`
- [ ] Each criterion is sent to Codex in full, with the checkbox line and its indented continuation lines (nested bullets), and numbered from 1. Codex answers with the number as `id`. The rendered comment uses the issue's own text for each criterion
- [ ] An unknown error produces `## QA: INVALID` without a retry
- [ ] Codex not installed, not logged in, or usage limit reached produces `## QA: UNAVAILABLE` with the reason
- [ ] An issue without acceptance criteria, or without a `Commits:` line in the newest `## Engineer: DONE`, produces `## QA: INVALID` and never `## QA: PASS`
- [ ] After retries, the footer has `Retries: <n> (<reasons>)`
- [ ] If the comment cannot be posted, the script exits with a non-zero code
- [ ] Codex receives the QA role file, the criteria and the range only. It does not receive the rest of the engineer comment
- [ ] Codex runs in a temporary `git worktree` at the head of the range, and the worktree is removed after the run, also after a failure. A fake `codex` that writes a file leaves the main working tree clean
- [ ] If the worktree has a `frontend/` submodule, a pre-step runs before Codex, outside the sandbox: fetch the submodule commits, `npm ci` in `frontend/`, then the Playwright browser install. If a pre-step command fails, the result is `## QA: UNAVAILABLE` with the command and its first error line. Without `frontend/`, no pre-step runs
- [ ] The `codex exec` command line has the localhost-only profile, the isolation flags, and an explicit model and reasoning effort (`medium`), as listed in Constraints
- [ ] The failure reason comes from the message of the last `turn.failed` event on stdout (`--json`), or from stderr if there is none. It never contains the Codex banner or the prompt text
- [ ] `docs/team/qa-engineer.md` contains the spec 7 behavior, the INVALID result, the delivery rule for `qa-codex` (JSON only, no comment), and the fallback footer `Checker: claude (fallback)`
- [ ] `uv run --with pytest pytest` passes. The tests use fake `codex` and `gh` and no network

#### Out of scope

- Wiring the hook and changing the orchestrator prose (Task 7)
- The review skill (Task 8), which reuses `codex_exec.py`

#### Constraints

- Depends on S2 (Task 2): the flags and the error regexes come from `docs/research/spike-codex-cli.md` (error table, and "Consequences for the plan", #6).
- Owner decisions (spec 6.1, 6.2, 7): localhost-only sandbox; temporary worktree; frontend pre-step outside the sandbox; model and effort set explicitly, `medium` for now.
- The command line, from S2 (`QA_MODEL` is the current default model of the installed Codex CLI, written out; `QA_EFFORT = "medium"`):

  ```text
  codex exec --json --ephemeral --ignore-user-config \
    --disable hooks --disable apps --disable unbounded_connection_retries \
    -c project_doc_max_bytes=0 -c skills.include_instructions=false \
    -m <QA_MODEL> -c model_reasoning_effort="medium" \
    --enable network_proxy \
    -c 'permissions.qa={extends=":workspace",network={enabled=true,allow_local_binding=true,domains={"localhost"="allow","127.0.0.1"="allow"}}}' \
    -c 'default_permissions="qa"' \
    -C <worktree> --output-schema scripts/qa-result.schema.json -o <tmp>/last.json -
  ```

- Open point (spec 9.3): a new worktree may not have the `frontend/` submodule objects. Find out how the pre-step gets them into the worktree (for example `git -C <worktree> submodule update --init frontend`; the Lovable repo is public). Record the method in the `## Engineer: DONE` comment.
- Uses `issue_state.parse_issue`, `newest_done` and `commits_range` from Task 4.
- Stdlib only. The schema is still passed to `codex exec --output-schema`. The script checks the same rules in Python.
- Settings that tests can override through the environment: `QA_CODEX_TIMEOUT` (seconds, default 1800). `main()` takes a `sleep` argument, so tests do not wait.

**Files:**
- Create: `scripts/codex_exec.py`, `scripts/qa-codex` (executable, no extension), `scripts/qa-result.schema.json`, `tests/test_qa_codex.py`, `tests/fakes/codex`, `tests/fakes/npm`, `tests/fakes/npx`
- Modify: `docs/team/qa-engineer.md`, `tests/fakes/gh` (if it needs a new mode)

**Interfaces (produced, used by Task 8):**

```python
# scripts/codex_exec.py
@dataclass(frozen=True)
class CodexRun:
    status: str          # "ok" | "transient" | "timeout" | "invalid_output" | "unavailable" | "unknown"
    output: dict | None
    reason: str

BASE_FLAGS: list[str]    # --json --ephemeral --ignore-user-config and the other isolation flags (S2)
def run_codex(prompt: str, *, schema: Path, sandbox_args: list[str], model: str, effort: str,
              timeout_s: int, cwd: Path) -> CodexRun
def failure_text(stdout: str, stderr: str) -> str           # message of the last turn.failed event, else stderr
def classify_failure(returncode: int, text: str) -> str     # "transient" | "unavailable" | "unknown"
```

```python
# scripts/qa-codex
def parse_criteria(body: str) -> list[str]          # full top-level "- [ ] …" items under "## Acceptance criteria", with indented continuation lines
def validate(output: dict, criteria: list[str], head: str) -> list[str]   # empty list = valid; ids must be exactly 1..len(criteria), once each
def render(output: dict | None, *, criteria: list[str], marker: str, reason: str, head: str, retries: list[str]) -> str
def main(argv: list[str], sleep=time.sleep) -> int
```

`scripts/qa-result.schema.json`:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["verdict", "criteria", "tests", "verified_sha"],
  "properties": {
    "verdict": {"enum": ["pass", "fail"]},
    "criteria": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "verdict", "evidence"],
        "properties": {
          "id": {"type": "integer"},
          "verdict": {"enum": ["pass", "fail", "invalid"]},
          "evidence": {"type": "string"}
        }
      }
    },
    "tests": {
      "type": "object",
      "additionalProperties": false,
      "required": ["command", "result"],
      "properties": {"command": {"type": "string"}, "result": {"type": "string"}}
    },
    "verified_sha": {"type": "string"}
  }
}
```

Comment rendered from valid JSON (the example is synthetic):

```markdown
## QA: FAIL

- [x] A visitor can create an account - PASS
      Ran `app signup demo pw1`; exit 0, user listed
- [ ] A duplicate username shows a visible error - FAIL
      Second signup printed a traceback

Tests: `uv run --with pytest pytest`, 18 passed, 0 failed
Verified: <40-char HEAD>
Checker: codex
Retries: 1 (timeout)
```

**Steps:**

1. Write `tests/fakes/codex`, an executable Python script. It pops the next mode from the file in `FAKE_CODEX_MODES` (one mode per line) and records each call:
   - `ok`: writes a valid JSON file to the `-o` path, with one passing entry for each id from 1 to `FAKE_CODEX_N` and the SHA from `git rev-parse HEAD`.
   - `invalid`: the same, but one criterion verdict is `invalid`.
   - `missing`: leaves out one id.
   - `duplicate`: repeats one id.
   - `short_sha`: writes a short verified SHA.
   - `transient`, `unavailable`, `unknown`: print a `turn.failed` event with the error text of that type from the S2 error table on stdout (the `--json` form), a banner and the prompt on stderr, and exit with its code. For "not installed", the test removes `codex` from `PATH`.
   - `timeout`: runs `sleep 30`.
   - `write`: like `ok`, but first writes a file into its working directory.

   `tests/fakes/npm` and `tests/fakes/npx` record their calls and exit 1 when `FAKE_NPM_FAIL=1`.
2. Write failing tests in `tests/test_qa_codex.py`. A fixture `qa_env` does the set-up: it creates a temporary git repo with one commit, writes a synthetic issue JSON (a body with two criteria, the second with a nested bullet list, and a launch plus a `## Engineer: DONE` comment with `Commits:`) for the fake `gh`, and sets `PATH`, `FAKE_CODEX_MODES`, `FAKE_CODEX_N=2`, `FAKE_GH_LOG` and `QA_CODEX_TIMEOUT=1`. Its `run(modes)` returns the posted comment and the recorded sleeps. Each test runs `main([...], sleep=recorded.append)` in a temporary git repo with fake `gh` and `codex` on `PATH`, and reads the posted comment from `FAKE_GH_LOG`:

   ```python
   @pytest.mark.parametrize("modes,marker,sleeps", [
       (["ok"], "## QA: PASS", []),
       (["invalid"], "## QA: INVALID", []),
       (["transient", "ok"], "## QA: PASS", [60]),
       (["transient"] * 4, "## QA: INVALID", [60, 180, 600]),
       (["timeout", "ok"], "## QA: PASS", []),
       (["timeout", "timeout"], "## QA: INVALID", []),
       (["missing", "ok"], "## QA: PASS", []),
       (["duplicate", "duplicate"], "## QA: INVALID", []),
       (["short_sha", "short_sha"], "## QA: INVALID", []),
       (["unknown"], "## QA: INVALID", []),
       (["unavailable"], "## QA: UNAVAILABLE", []),
   ])
   def test_failure_rules(qa_env, modes, marker, sleeps):
       comment, slept = qa_env.run(modes)
       assert comment.splitlines()[0] == marker
       assert slept == sleeps
   ```

   Also add tests for:
   - no acceptance criteria → INVALID, and codex is not called
   - no `Commits:` line → INVALID
   - a failing post → exit code ≠ 0
   - the footer `Retries: 2 (transient, transient)`
   - the prompt contains the criteria and the range, but not the text of the engineer summary
   - `QA_CODEX_TIMEOUT=1` for the timeout cases
   - the prompt contains the nested bullets of the second criterion, and `parse_criteria` returns 2 items for that body
   - mode `write`: the main working tree is still clean, and no worktree is left (`git worktree list`)
   - a repo with a `frontend/` folder: `npm ci` and the Playwright install are called before `codex`; with `FAKE_NPM_FAIL=1` the result is `## QA: UNAVAILABLE` and `codex` is not called
   - the recorded `codex` arguments contain the model, `model_reasoning_effort="medium"` and `default_permissions="qa"`
   - the reason of a `transient` failure is the `turn.failed` message, not the banner
3. Run `uv run --with pytest pytest tests/test_qa_codex.py -v`. Expected: FAIL.
4. Implement `scripts/codex_exec.py`:

   ```python
   def run_codex(prompt, *, schema, sandbox_args, model, effort, timeout_s, cwd):
       out = Path(tempfile.mkdtemp(prefix="codex-")) / "last.json"   # fresh path per run (S2 Q1)
       cmd = ["codex", "exec", *BASE_FLAGS, "-m", model, "-c", f'model_reasoning_effort="{effort}"',
              *sandbox_args, "-C", str(cwd), "--output-schema", str(schema), "-o", str(out), "-"]
       try:
           p = subprocess.Popen(cmd, cwd=cwd, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, start_new_session=True)
       except FileNotFoundError:
           return CodexRun("unavailable", None, "codex is not installed")
       try:
           stdout, err = p.communicate(prompt, timeout=timeout_s)
       except subprocess.TimeoutExpired:
           os.killpg(p.pid, signal.SIGKILL); p.wait()
           return CodexRun("timeout", None, f"no result after {timeout_s // 60} min")
       if p.returncode != 0:
           text = failure_text(stdout, err)
           return CodexRun(classify_failure(p.returncode, text), None, _first_line(text))
       try:
           return CodexRun("ok", json.loads(out.read_text()), "")
       except (OSError, ValueError) as e:
           return CodexRun("invalid_output", None, f"output is not JSON: {e}")
   ```

   `classify_failure` uses an ordered list `FAILURE_PATTERNS = [(status, regex), ...]` copied from the S2 error table (first match wins). If nothing matches, it returns `"unknown"`.
5. Implement `scripts/qa-codex`:
   - Header: `#!/usr/bin/env -S uv run --script` with PEP 723 `requires-python = ">=3.11"`, `dependencies = []`.
   - Import: insert `Path(__file__).resolve().parents[1] / ".claude" / "hooks"` into `sys.path`, then import `issue_state`. Import `codex_exec` from the script folder.
   - Flow: read the issue, `HEAD`, the criteria and the range. Create the temporary worktree at the head of the range (`git worktree add --detach <tmp> <head>`), remove it in a `finally` block (`git worktree remove --force`). Run the frontend pre-step if the worktree has `frontend/`. Build the prompt from the role file, the numbered criteria ("copy each text exactly into `criteria[].text`"), and the range. Number the criteria from 1 in the prompt and ask for the number as `id`. Then run the retry loop:

   ```python
   LIMITS = {"transient": 3, "timeout": 1, "invalid_output": 1}
   WAITS = (60, 180, 600)
   used, retries = Counter(), []
   while True:
       run = codex_exec.run_codex(prompt, schema=SCHEMA, sandbox_args=QA_SANDBOX, model=QA_MODEL,
                                  effort=QA_EFFORT, timeout_s=timeout, cwd=worktree)
       status, reason = run.status, run.reason
       if status == "ok":
           errors = validate(run.output, criteria, head)
           if not errors:
               break
           status, reason = "invalid_output", "; ".join(errors)
       if status == "unavailable":
           return post(render(None, criteria=criteria, marker="## QA: UNAVAILABLE", reason=reason, head=head, retries=retries))
       if status == "unknown" or used[status] >= LIMITS[status]:
           return post(render(None, criteria=criteria, marker="## QA: INVALID", reason=reason, head=head, retries=retries))
       if status == "transient":
           sleep(WAITS[used["transient"]])
       used[status] += 1
       retries.append(status)
   marker = ("## QA: INVALID" if any(c["verdict"] == "invalid" for c in run.output["criteria"])
             else "## QA: PASS" if all(c["verdict"] == "pass" for c in run.output["criteria"])
             else "## QA: FAIL")
   return post(render(run.output, criteria=criteria, marker=marker, reason="", head=head, retries=retries))
   ```

   `post` returns 0 on success and 1 if `gh issue comment` fails. `QA_SANDBOX` is the list of localhost-only profile flags from Constraints (`--enable network_proxy` and the two `-c` values). Make the file executable: `chmod +x scripts/qa-codex`.
6. Change `docs/team/qa-engineer.md`, as little as possible. Replace the bullet list with:

   ```markdown
   - Read the acceptance criteria from the issue
   - Look at the changes in the commit range you received: `git diff <base>..<head>`. If a submodule changed, use `git diff --submodule=diff <base>..<head>`
   - For each criterion, exercise the behavior: run the command, call the endpoint, open the page, or read the document (for a prose task). Judge if a test really covers the criterion or only mirrors the implementation. Give a verdict with evidence. A criterion without enough evidence cannot pass
   - Run the test command in AGENTS.md as secondary evidence, and say which tests you ran. Without a test suite, write `Tests: not run (no test suite)`
   - Do not change anything in the repo. Report what you find
   ```

   Then make these edits:
   - Change "PASS or FAIL" to "PASS, FAIL or INVALID". Add the sentence: "It is INVALID if you cannot verify a criterion for a technical reason (for example, the browser crashes). Say what failed."
   - Add `## QA: INVALID` to the allowed first lines.
   - Add `Checker: claude (fallback)` to the example and to the definition of done.
   - Add the delivery rule: "When `scripts/qa-codex` runs you, return only the JSON that the schema asks for. Do not post a comment. Give each criterion's number as `id`."
   - Add: "Do not install anything. If you need a tool that is not in the lockfile or the set-up, the criterion fails (undeclared dependency)."
   - Add: "Start the app and run the browser check in one command. A background process does not survive into your next command."
7. Run `uv run --with pytest pytest -v`. Expected: all tests PASS.
8. Commit: `git add scripts tests docs/team/qa-engineer.md && git commit -m "Add qa-codex launcher with failure rules and QA behavior"`

---

### Task 7: Hook wiring and prose switch

Lane: default

#### Goal

The guard hook is registered for this repo, with the settings protection and the allow rules. The prose tells the orchestrator how to launch roles under the hooks. After this issue is closed, the owner activates the hooks and runs the acceptance test (spec 5.9). All later tasks run with the hooks on.

#### Acceptance criteria

- [ ] `.claude/settings.json` registers `guard.py` as a `PreToolUse` hook with the matcher `Agent|Bash|SendMessage` and `timeout` 120. The command is POSIX `sh` and turns any launch failure into a deny (`|| { …; exit 2; }`)
- [ ] `.claude/settings.json` has `permissions.allow` rules `Bash(scripts/qa-codex ROLE=qa ISSUE=*)` and `Bash(gh issue close *)`, and `permissions.deny` rules for `Edit` and `Write` on `.claude/settings*.json` (spec 5.9)
- [ ] `docs/checks/hook-activation.md` has the owner's acceptance test (spec 5.9) with ready-to-paste prompts, one step per check: `/hooks` lists the guard; a launch without a launch line is denied; a `SendMessage` continuation without the line is denied and with the line runs and posts a continued comment (record the input field names and whether the extension has `SendMessage`); writing `disableAllHooks` with `Edit` and with a `Bash` `echo` is denied; a guarded `qa-codex` call shows no permission prompt; `disableAllHooks` put in by hand: check whether user-level hooks also stop, then delete it
- [ ] Smoke check: the settings hook command, run with a subagent event without a launch line on stdin, prints a deny with `G1:`. With a `ls` Bash event, it prints nothing and exits 0. With `PATH` without `uv`, it exits 2. No `gh` call is needed for these three cases
- [ ] A test in `tests/test_settings.py` checks the matcher, the timeout, the allow and deny rules, and that the command contains `guard.py` and the failure wrapper
- [ ] `docs/team/orchestrator.md`:
  - has the launch line in the prompt template and the markers `## QA: UNAVAILABLE`, `## QA: INVALID`
  - explains the pending state and what to do with a deny message
  - launches QA as `scripts/qa-codex ROLE=qa ISSUE=<n>` in the background, and the fallback `qa-engineer` only after `## QA: UNAVAILABLE`
  - uses the issue list command with `-label:later -label:needs-owner`
  - allows continuing a role with `SendMessage`, only with the launch line in the message
  - no longer contains the hand-written return-count query or the manual SHA comparison
- [ ] `AGENTS.md`: the issue list command excludes `later` and `needs-owner`, and the bootstrap sentence no longer says "prose-only"
- [ ] `docs/process.md`: the status line says the hooks enforce the lifecycle, and after `## Owner: RESUME` the issue goes back to the PM
- [ ] `docs/team/pm.md`: a follow-up issue gets the label `later`
- [ ] No other role file changes (owner decision: no change for spec 5.8)
- [ ] `uv run --with pytest pytest` passes

#### Out of scope

- The frontend lane in `orchestrator.md` (Task 9)
- The codex-review lines in AGENTS.md and process.md (Task 8)

#### Constraints

- Depends on S1 (Task 1), Task 4, Task 5 and Task 6.
- Activation (spec 5.9; S1 found that hooks apply at the next tool call, not at session start): before this issue gets `ready`, the owner puts `{"disableAllHooks": true}` into `.claude/settings.local.json`. After the close, the owner deletes it and runs `docs/checks/hook-activation.md`. Do not delete or change `.claude/settings.local.json` in this task.
- This issue is verified and closed with the process that was in force when it started: the Claude `qa-engineer` with the range from `## Engineer: DONE`, the manual `Verified:` SHA check, and `gh issue close`. Do not use `qa-codex` or the new orchestrator prose for this issue. Its comments have no launch receipts, so `qa-codex` would find no valid `## Engineer: DONE`. The new rules start with the next issue in a new session (Task 8).
- `codex-review` (Task 8) reviews the protection built here. Its focus: ways around the `G8` Bash check (`cd .claude` first, variables, `python -c`, `tee`, `cp`, `mv`) and how the allow rules match compound commands (`… ISSUE=1 && rm …`).
- Keep each prose change as small as possible (P4). Do not copy check logic into prose. The deny message is the source of truth.

**Files:**
- Create: `.claude/settings.json`, `tests/test_settings.py`, `docs/checks/hook-activation.md`
- Modify: `docs/team/orchestrator.md`, `AGENTS.md`, `docs/process.md`, `docs/team/pm.md`

**Steps:**

1. Write the failing test `tests/test_settings.py`:

   ```python
   def test_guard_is_registered():
       s = json.loads((ROOT / ".claude" / "settings.json").read_text())
       entry = s["hooks"]["PreToolUse"][0]
       assert set(entry["matcher"].split("|")) >= {"Agent", "Bash", "SendMessage"}
       hook = entry["hooks"][0]
       assert "guard.py" in hook["command"] and "exit 2" in hook["command"] and hook["timeout"] == 120
       assert "Bash(scripts/qa-codex ROLE=qa ISSUE=*)" in s["permissions"]["allow"]
       assert "Bash(gh issue close *)" in s["permissions"]["allow"]
       assert {"Edit(.claude/settings*.json)", "Write(.claude/settings*.json)"} <= set(s["permissions"]["deny"])
   ```

   Check the exact permission-rule syntax for file paths in the current Claude Code docs, and adjust the rule strings and the test if needed.

2. Run `uv run --with pytest pytest tests/test_settings.py -v`. Expected: FAIL (file missing).
3. Create `.claude/settings.json`:

   ```json
   {
     "permissions": {
       "allow": ["Bash(scripts/qa-codex ROLE=qa ISSUE=*)", "Bash(gh issue close *)"],
       "deny": ["Edit(.claude/settings*.json)", "Write(.claude/settings*.json)"]
     },
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Agent|Bash|SendMessage",
           "hooks": [
             {
               "type": "command",
               "command": "uv run --script \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py\" || { echo 'guard hook failed: call denied' >&2; exit 2; }",
               "timeout": 120
             }
           ]
         }
       ]
     }
   }
   ```

4. Run the tests. Expected: PASS. Run the smoke check from the acceptance criteria, for example:

   ```bash
   CMD=$(jq -r '.hooks.PreToolUse[0].hooks[0].command' .claude/settings.json)
   echo '{"tool_name":"Agent","tool_input":{"subagent_type":"pm","prompt":"no line"}}' \
     | CLAUDE_PROJECT_DIR=$PWD sh -c "$CMD"; echo "exit=$?"
   # Expected: deny JSON with "G1: …", exit=0
   echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | CLAUDE_PROJECT_DIR=$PWD sh -c "$CMD"; echo "exit=$?"
   # Expected: no output, exit=0
   echo '{}' | PATH=/usr/bin/nonexistent CLAUDE_PROJECT_DIR=$PWD /bin/sh -c "$CMD"; echo "exit=$?"
   # Expected: "guard hook failed: call denied", exit=2
   ```

5. Change `docs/team/orchestrator.md`:
   - "Launch a subagent" table: Verify → Bash `scripts/qa-codex ROLE=qa ISSUE=<number>`. Run it in the background, because it can run longer than the Bash time limit. Wait until it ends. Verify (fallback) → `qa-engineer`, only after `## QA: UNAVAILABLE`, with the range from the newest `## Engineer: DONE`.
   - Prompt template: add the first line `ROLE=<pm|engineer|qa> ISSUE=<number>`.
   - Replace "Do not reuse a subagent from an earlier step" with: "You may continue a role agent with `SendMessage`, for example the engineer after `## QA: FAIL`. Put the same `ROLE=… ISSUE=…` line first in the message. Without it, the hook denies the call."
   - "Read the result" table: add `## QA: UNAVAILABLE` and `## QA: INVALID`.
   - Add a section "Hooks":

     ```markdown
     ## Hooks

     A hook checks each launch and `gh issue close`. When it allows a launch, it posts `## Launch: <role> (attempt <n>)` on the issue. When it denies a call, the message names the failed check (`G1` … `G7`). Do not work around a deny.

     - `G1` pending: the last launched role ended without a result. Escalate the issue
     - `G1` working tree not clean: stop the loop and ask the owner
     - `G7`: 3 returns. Escalate the issue
     - `G6` verified SHA is not `HEAD`: run `qa-codex` again. This is not a return
     - Any other deny: escalate the issue with the deny message
     ```

   - Decisions table: `## QA: UNAVAILABLE` → launch the `qa-engineer` fallback. `## QA: INVALID` → escalate. `## Engineer: BLOCKED` and `## QA: FAIL` → send back (the hook denies at 3 returns).
   - Delete the section "Count the returns" and its query.
   - "Close an issue": replace the steps with "Run `gh issue close <number>`. The hook checks the verified SHA."
   - Change the issue list command in "Definition of done" to `gh issue list --state open --label ready --search "-label:later -label:needs-owner"`.
6. Change `AGENTS.md`:
   - The first command line becomes `gh issue list --state open --label ready --search "-label:later -label:needs-owner"`.
   - Replace "We build the kit with a prose-only process." with "Hooks in `.claude/hooks/` check the handoff calls (see `docs/process.md`)."
7. Change `docs/process.md`:
   - The Status line becomes: "Status: hooks in `.claude/hooks/` check each launch of a role and each `gh issue close`, and deny the call when the issue is not in the right state. This prose stays the main description. There are no Jev gates yet."
   - In Escalation, add: "After `## Owner: RESUME`, the issue goes back to the PM."
8. Change `docs/team/pm.md`: "File a follow-up issue" becomes "File a follow-up issue with the label `later`".
9. Run `uv run --with pytest pytest`. Expected: PASS.
10. Write `docs/checks/hook-activation.md` from the acceptance criterion above: a short intro (who runs it, when, and that the loop does not start if a step fails), then one numbered step per check with the prompt to paste and the expected result.
11. Commit: `git add .claude/settings.json tests/test_settings.py docs AGENTS.md && git commit -m "Wire guard hook and switch prose to hook-checked launches"`

---

### Task 8: Codex review skill

Lane: default

#### Goal

When the owner asks for a Codex review, the `codex-review` skill runs Codex read-only on a file, folder or commit range and always writes `docs/reviews/<date>-<topic>-codex-review.md`. Each finding gets a decision before the file is committed.

#### Acceptance criteria

- [ ] `.agents/skills/codex-review/SKILL.md` has the name `codex-review`. Its description says that it runs only when the owner asks for a Codex review or types `/codex-review`
- [ ] The skill tells Claude to derive the target (file, folder, or commit range) from the conversation, run `review.py`, give each finding a decision (taken, partly taken, rejected, with a short reason), and commit the review file. When Claude works alone, it commits the review file with its changes
- [ ] `review.py` runs Codex through `codex_exec.run_codex` with `sandbox_args=["-s", "read-only"]`, the same model and reasoning effort as QA (`medium`), a normal (not adversarial) review prompt and `review.schema.json`
- [ ] The review file has the verdict (`approve` or `needs-attention`), the summary, each finding (severity, title, body, file, lines, confidence, recommendation, and `Decision: open`) and the next steps
- [ ] If Codex fails, `review.py` writes no file, exits non-zero and prints the reason
- [ ] The schema credits the openai-codex plugin for Claude Code as its source
- [ ] AGENTS.md has the line "When the owner asks for a Codex review, use the `codex-review` skill."
- [ ] `docs/process.md` has the rule "Do not read old reviews in `docs/reviews/` unless the owner points to one."
- [ ] A pytest test renders a synthetic review JSON to the expected markdown, and `uv run --with pytest pytest` passes
- [ ] This issue has launch comments for pm, engineer and qa (the first task that runs with the hooks on, spec 12.3)
- [ ] A committed review file exists for the settings protection and allow rules of Task 7 (`.claude/settings.json`, the `G8` check in `guard.py`), made with the new skill. Its focus: ways around the `G8` Bash check (`cd .claude` first, variables, `python -c`, `tee`, `cp`, `mv`) and how the allow rules match compound commands (`… ISSUE=1 && rm …`). Each finding has a decision. A finding that is taken becomes a follow-up issue, not a change in this task

#### Out of scope

- Wrapping `/codex:adversarial-review`
- Starting the skill from the loop

#### Constraints

- Depends on S2 (Task 2) and Task 6 (`codex_exec`). A read-only run does not write the Codex trust entry (S2 Q8).
- `review.py` imports `codex_exec` from `scripts/`. Insert `Path(__file__).resolve().parents[3] / "scripts"` into `sys.path`.

**Files:**
- Create: `.agents/skills/codex-review/SKILL.md`, `.agents/skills/codex-review/review.py`, `.agents/skills/codex-review/review.schema.json`, `tests/test_codex_review.py`
- Modify: `AGENTS.md`, `docs/process.md`

**Interfaces:**
- Consumes: `codex_exec.run_codex`, `CodexRun` (Task 6).
- Produces: `uv run --script .agents/skills/codex-review/review.py --target <path-or-range> --topic <slug>` → prints the path of the review file. Also produces `render_review(data: dict, *, topic: str, target: str, date: str) -> str`.

**Steps:**

1. Write the failing test `tests/test_codex_review.py`. It loads `review.py` with `importlib`, renders this synthetic JSON, and compares the result with the expected markdown:

   ```python
   DATA = {"verdict": "needs-attention", "summary": "One gap.",
           "findings": [{"severity": "high", "title": "Missing deny", "body": "Crash allows call.",
                         "file": "guard.py", "line_start": 10, "line_end": 12, "confidence": 0.8,
                         "recommendation": "Catch BaseException."}],
           "next_steps": ["Add test"]}
   EXPECTED = """# Codex review: demo

   - Date: 2026-01-01
   - Target: docs/x.md
   - Verdict: needs-attention

   ## Summary

   One gap.

   ## Findings

   ### 1. [high] Missing deny

   - File: guard.py:10-12
   - Confidence: 0.8

   Crash allows call.

   Recommendation: Catch BaseException.

   Decision: open

   ## Next steps

   - Add test
   """
   ```

2. Run `uv run --with pytest pytest tests/test_codex_review.py -v`. Expected: FAIL.
3. Write `review.schema.json`. It has the same fields as `DATA`, all required, and `additionalProperties: false`. `severity` is one of `critical | high | medium | low`. The top-level `description` is "Adapted from the review schema of the openai-codex plugin for Claude Code."
4. Implement `review.py`:
   - Arguments: `--target`, `--topic`.
   - Prompt: "Review <target> for correctness, gaps and risks. For a commit range, run `git diff <range>`. Report findings in the schema."
   - Call `run_codex(..., sandbox_args=["-s", "read-only"], model=QA_MODEL, effort="medium", timeout_s=1800)`. If the status is not `ok`, print the reason and exit 1.
   - Otherwise write `docs/reviews/<YYYY-MM-DD>-<topic>-codex-review.md` from `render_review` and print its path.
5. Write `SKILL.md` (frontmatter `name: codex-review` and the description from the criteria) with these steps:
   1. Derive the target and a short topic slug.
   2. Run the script.
   3. Go through each finding, with the owner or alone. Replace `Decision: open` with `Decision: taken|partly taken|rejected - <reason>`.
   4. Commit the review file (with your changes, if you worked alone).
   5. For an adversarial review, point the owner to `/codex:adversarial-review`.
6. Add the AGENTS.md line under "Skills and subagents" and the process.md rule under "Work rules".
7. Run `uv run --with pytest pytest`. Expected: PASS.
8. Commit: `git add .agents/skills/codex-review tests/test_codex_review.py AGENTS.md docs/process.md && git commit -m "Add codex-review skill"`
9. Run the skill on the Task 7 settings protection with the focus from the criteria. Give each finding a decision, file a follow-up issue for each taken finding, and commit the review file.

---

### Task 9: Frontend lane

Lane: default

#### Goal

An issue with `Lane: frontend` is implemented by the subagent `frontend-engineer`, which drives Lovable through MCP, pins the submodule to the exact Lovable commit, and posts `## Engineer: DONE` with the range.

#### Acceptance criteria

- [ ] `.claude/agents/frontend-engineer.md` exists. It lists the Lovable MCP tools from the S3 findings, `Bash`, and the read tools. It points to the section "Lane `frontend`" in `docs/team/software-engineer.md` and to `docs/process.md`
- [ ] `docs/team/software-engineer.md` has a section "Lane `frontend`" with the 7 steps of spec 9.2. It uses the detection and commit-pinning method of the S3 findings, the 60-minute budget, and the rule that nobody edits `frontend/` locally
- [ ] `docs/task-template.md` allows `Lane: default` and `Lane: frontend`, and `frontend` only in a repo with a Lovable submodule in `frontend/`
- [ ] `docs/team/orchestrator.md` launches `software-engineer` for `default` and `frontend-engineer` for `frontend`
- [ ] The G3 lane mapping in `issue_state.py` has a test for `frontend` → `frontend-engineer` (allow) and `frontend` → `software-engineer` (deny)
- [ ] `uv run --with pytest pytest` passes

#### Out of scope

- The paint-math repo and the demo (Tasks 11 and 12)

#### Constraints

- Depends on S3 (Task 3) for the method and the tool names (`docs/research/spike-lovable-mcp.md`, "Consequences for the plan"). S2 Q4 showed that Codex can run headless Chromium, so the precondition of spec 9.3 holds.
- `tools:` gets `Read, Grep, Glob, Bash` and the six Lovable tools: `mcp__plugin_lovable_lovable__send_message`, `…__get_message`, `…__list_messages`, `…__list_edits`, `…__get_diff`, `…__get_project`. In the S3 session these tools were deferred and needed `ToolSearch`. Check in a real `frontend-engineer` launch (a scratch project, no real issue) that the tools are reachable, and add `ToolSearch` to `tools:` if they are not.
- The frontend lane is a section in the engineer role file, not a new role file (P4).

**Files:**
- Create: `.claude/agents/frontend-engineer.md`
- Modify: `docs/team/software-engineer.md`, `docs/task-template.md`, `docs/team/orchestrator.md`, `tests/test_issue_state.py`

**Steps:**

1. Add the two G3 lane tests to `tests/test_issue_state.py`. Run them. Expected: PASS if Task 4 implemented `AGENT_LANE`. If they fail, fix `issue_state.py`.
2. Create `.claude/agents/frontend-engineer.md`:

   ```markdown
   ---
   name: frontend-engineer
   description: Use this agent to implement one groomed GitHub issue with Lane frontend, through Lovable.
   tools: Read, Grep, Glob, Bash, mcp__plugin_lovable_lovable__send_message, mcp__plugin_lovable_lovable__get_message, mcp__plugin_lovable_lovable__list_messages, mcp__plugin_lovable_lovable__list_edits, mcp__plugin_lovable_lovable__get_diff, mcp__plugin_lovable_lovable__get_project
   ---

   Read your role definition from the section "Lane `frontend`" in docs/team/software-engineer.md before any other action.
   Follow the process in docs/process.md.
   ```

3. Add the section to `docs/team/software-engineer.md`:

   ```markdown
   ## Lane `frontend`

   You drive Lovable. Nobody edits `frontend/` locally. Lovable does not know about issues or git.

   1. Note the base SHA: `git rev-parse HEAD`
   2. Send Lovable the goal and the acceptance criteria in plain words
   3. Wait until Lovable has finished and its commit is on GitHub:
      - Send with `send_message` (`wait=true`, `timeout_seconds=600`). Keep `message_id` and `thread_id`
      - If the result is still in progress, poll `get_message` until `response.status` is terminal. Read `response.status`, never the top-level `status`
      - `completed`: take `edit_id` and `commit_sha`. `awaiting_input`: only a human can answer in the Lovable editor, so post `## Engineer: BLOCKED` with the reason. `stopped` or `error`: send a follow-up message within the budget, otherwise `## Engineer: BLOCKED`
      - Run `git -C frontend fetch origin` until `git -C frontend merge-base --is-ancestor <commit_sha> origin/main` succeeds. After 5 minutes, post `## Engineer: BLOCKED`
   4. If a criterion is not met, send a follow-up message. Repeat within 60 minutes per launch. When the time runs out, post `## Engineer: BLOCKED` with what is missing
   5. Pin the submodule to `<commit_sha>` of the last message of this launch (a merge commit). Check first that `git -C frontend log -1 --format=%B <commit_sha>` contains `X-Lovable-Edit-ID: <edit_id>`. Never pin a "Changes" commit or the branch tip without this check. Check `git -C frontend diff <old pointer> <commit_sha> --stat` for changes that Lovable did not make in this launch. Commit the pointer update
   6. Run the test command in AGENTS.md, if one exists
   7. Post `## Engineer: DONE` with `Commits: <base>..<head>`
   ```

4. In `docs/task-template.md`, replace the Lane comment with `<!-- default, or frontend (only in a repo with a Lovable submodule in frontend/) -->`.
5. In `docs/team/orchestrator.md`, change the Implement row to "`software-engineer` for `Lane: default`, `frontend-engineer` for `Lane: frontend`".
6. Run `uv run --with pytest pytest`. Expected: PASS.
7. Commit: `git add .claude/agents/frontend-engineer.md docs tests && git commit -m "Add frontend lane with Lovable engineer"`

---

### Task 10: README set-up section

Lane: default

#### Goal

The README tells a new project how to set up the kit (spec 12.4), and the status text matches v1.

#### Acceptance criteria

- [ ] The prerequisites are listed: `gh` (logged in), `uv`, Codex CLI (logged in), the Claude Code plugin `lovable` (frontend lane only; the tool names in `frontend-engineer.md` depend on it)
- [ ] A set-up step adds the Codex trust entry for the project to `$HOME/.codex/config.toml` (spec 6.2), with the exact lines
- [ ] Frontend lane only: the steps to create the Lovable project, connect the workspace to GitHub (one time), connect the project (Project settings → Git → GitHub → Connect), make the new repo public, and add it as the `frontend/` submodule tracking `main`
- [ ] `docs/checks/` is in the list of files to copy
- [ ] Each file to copy is listed, with its path:
  - AGENTS.md, CLAUDE.md
  - `docs/process.md`, `docs/team/`, `docs/task-template.md`
  - `.claude/agents/`, `.claude/hooks/`, the hooks and permissions blocks of `.claude/settings.json`, `docs/checks/`
  - `scripts/qa-codex`, `scripts/codex_exec.py`, `scripts/qa-result.schema.json`
  - `.agents/skills/codex-review/`
  - the symlink `.claude/skills` → `.agents/skills`
- [ ] The files to adjust are listed: the project description and the test command in AGENTS.md; the `frontend/` submodule and the `frontend` lane (Lovable only)
- [ ] The label commands are listed: `gh label create ready`, `gh label create needs-owner`, `gh label create later`
- [ ] A final step says: run the acceptance test in `docs/checks/hook-activation.md` before the first issue gets `ready`
- [ ] The paragraphs "Current bootstrap …" and "Status" describe v1 (hooks, Codex QA, Lovable lane) without the words "prose only" or "not usable yet"

#### Out of scope

- Testing the instructions in a real project (Task 11)

#### Constraints

- Depends on Tasks 7, 8 and 9 (the file list must be final).
- Plain commands the reader can copy. No keys, synthetic repo names only.

**Files:** Modify `README.md`

**Steps:**

1. Check the file list against `git ls-files .claude .agents scripts docs/team docs/process.md docs/task-template.md`. Every kit file must be in the list, and no file in the list may be missing from the repo.
2. Write the section "Set up the kit in a project" with the subsections Prerequisites, Copy, Adjust, Labels and Start. Use a copy example with `cp -r` from a clone at `../agent-graph-kit` and `ln -s ../.agents/skills .claude/skills`.
3. Update the status paragraphs.
4. Commit: `git add README.md && git commit -m "Add README set-up section"`

---

### Task 11: paint-math set-up

Lane: default

#### Goal

The demo repo `paint-math` exists, set up only from the README instructions, with the Lovable submodule and two demo issues. Every missing or wrong README step is fixed in this repo.

#### Acceptance criteria

- [ ] The GitHub repo `paint-math` contains, on `main`, the kit files from the README set-up section, with an adjusted AGENTS.md (project description, test command)
- [ ] `frontend/` is a git submodule that points to the Lovable-managed repo
- [ ] The labels `ready`, `needs-owner` and `later` exist in `paint-math`
- [ ] The hook smoke check from Task 7 (a subagent event without a launch line → a `G1:` deny) passes inside `paint-math`
- [ ] Two issues exist in `paint-math`, in `docs/task-template.md` format, without the label `ready`:
  - Lane `frontend`: the canvas shows the curve of an equation that the user enters
  - Lane `default`: an equation parser and validator with tests
- [ ] Each README gap found during set-up is fixed in this repo's README. The `## Engineer: DONE` comment lists the gaps, or says "no gaps found"

#### Out of scope

- Running the loop in `paint-math` (Task 12)
- Changing the kit files other than the README

#### Constraints

- Depends on S3 (Task 3), Task 9 and Task 10.
- Owner step before this issue gets `ready`: create the empty GitHub repo `paint-math`.
- The Lovable project is made by the owner during this task (spec 9.1; no MCP tool can connect it to GitHub). At the exact point in the set-up where the project must exist, post `## Engineer: BLOCKED` and stop. The comment names that point and gives the owner:
  1. An initial Lovable prompt to create the project (the canvas app of spec 9.4, without the equation feature).
  2. The manual steps: connect the workspace to GitHub (one time), Project settings → Git → GitHub → Connect, make the new repo public, then answer with `## Owner: RESUME` and the repo URL.

  The next engineer launch continues from that point.
- Add the Codex trust entry for `paint-math` with the README step.
- Follow only the README. Do not use knowledge from this repo that the README does not give. Each place where you need such knowledge is a README gap.
- Work in a sibling folder (`../paint-math`). This repo's working tree stays clean except for the README fixes.
- The owner may replace the two issue ideas (spec 9.4).

**Files:** Modify `README.md` (gaps only). Everything else is in the `paint-math` repo.

**Steps:**

1. Clone `paint-math` next to this repo. Follow the README set-up section step by step, and note each gap.
2. At the point where the Lovable project is needed, post `## Engineer: BLOCKED` as in Constraints. After the owner's `## Owner: RESUME` with the repo URL: `git submodule add -b main <Lovable repo URL> frontend`, commit, and push `paint-math`.
3. Create the labels with the README commands.
4. Run the smoke check from Task 7 in `paint-math`.
5. File the two issues with `gh issue create -R <owner>/paint-math --body-file <file>`.
6. Fix the README gaps in this repo and commit: `git commit -m "Fix README set-up gaps found in paint-math"`.

---

### Task 12: paint-math demo run

Lane: default

#### Goal

Both demo issues in `paint-math` went through PM → engineer → Codex QA → close with the hooks active. The evidence is linked on this issue.

#### Acceptance criteria

- [ ] Both `paint-math` demo issues are closed
- [ ] Each of them has launch comments for pm, engineer and qa. The frontend issue shows `Agent: frontend-engineer`, the default issue `Agent: software-engineer`, and both show `Agent: qa-codex` for QA
- [ ] The newest QA comment of each issue is `## QA: PASS` with `Checker: codex`, and its `Verified:` SHA is the commit on which the issue was closed
- [ ] The QA evidence for the frontend issue shows that the UI was exercised in a headless browser (spec 9.3)
- [ ] Each README gap found during the run is fixed in this repo's README. The `## Engineer: DONE` comment lists the gaps with the links to both issues, or says "no gaps found"

#### Out of scope

- Fixing `paint-math` code from this repo
- Items with the label `later` (for example Jev at the handoffs)

#### Constraints

- Depends on Task 11. S2 Q4 showed that browser QA works with the localhost-only profile.
- Owner steps before this issue gets `ready`:
  1. Add `ready` to both `paint-math` issues.
  2. Start a new Claude session in `paint-math` and run the loop (`/goal`) until both issues are closed or escalated.
  3. If an issue is escalated, the owner resolves it with `## Owner: RESUME` and runs the loop again.
- The engineer of this issue only collects evidence and fixes README gaps. It does not run the `paint-math` loop.

**Files:** Modify `README.md` (gaps only)

**Steps:**

1. Read both `paint-math` issues with `gh issue view <n> -R <owner>/paint-math --comments`, and check each criterion above.
2. Fix README gaps and commit: `git commit -m "Fix README gaps found in the paint-math demo"`. If there are no gaps, make no commit and write `Commits: <HEAD>..<HEAD>`.
3. Post `## Engineer: DONE` with the links and the list of gaps.
