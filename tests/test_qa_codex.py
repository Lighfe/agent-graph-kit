"""Tests for scripts/qa-codex and scripts/codex_exec.py.

Each flow test runs `main([...], sleep=recorded.append)` in a temporary git repo, with the
fakes `gh`, `codex`, `npm` and `npx` from tests/fakes/ first on PATH. No real `gh` or
`codex` runs and no test uses the network. All issue data is synthetic.
"""

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

import codex_exec
import issue_state

ROOT = Path(__file__).resolve().parents[1]
FAKES = ROOT / "tests" / "fakes"
SCRIPT = ROOT / "scripts" / "qa-codex"


def _load():
    loader = SourceFileLoader("qa_codex", str(SCRIPT))
    spec = importlib.util.spec_from_loader("qa_codex", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


qa = _load()

CRIT_1 = "A visitor can create an account"
CRIT_2 = "A duplicate username shows a visible error:\n  - the error names the username\n  - the form keeps the input"
ENGINEER_SUMMARY = "SECRET-SUMMARY: I built the thing and it is great"

BODY = f"""Lane: default

## Goal

Synthetic goal.

## Acceptance criteria

- [ ] {CRIT_1}
- [ ] {CRIT_2}

## Out of scope

- [ ] Not a criterion
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def alive(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


class QaEnv:
    def __init__(self, tmp, monkeypatch):
        self.tmp = tmp
        self.mp = monkeypatch
        self.bin = tmp / "bin"
        self.bin.mkdir()
        for tool in ("gh", "codex", "npm", "npx"):
            (self.bin / tool).symlink_to(FAKES / tool)
        path = os.pathsep.join([str(self.bin), str(Path(shutil.which("git")).parent),
                                str(Path(sys.executable).parent)])
        env = {
            "PATH": path,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Synthetic", "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
            "GIT_COMMITTER_NAME": "Synthetic", "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
            "FAKE_GH_ISSUE": str(tmp / "issue.json"),
            "FAKE_GH_LOG": str(tmp / "gh.log"),
            "FAKE_GH_CALLS": str(tmp / "gh-calls.log"),
            "FAKE_CODEX_MODES": str(tmp / "modes"),
            "FAKE_CODEX_N": "2",
            "FAKE_CODEX_PID": str(tmp / "child.pid"),
            "FAKE_TOOL_LOG": str(tmp / "tools.log"),
            "QA_CODEX_TIMEOUT": "1",
        }
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        for key in ("FAKE_GH_FAIL", "FAKE_GH_COMMENT_FAIL", "FAKE_NPM_FAIL", "FAKE_NPM_WAIT", "GIT_DIR", "GIT_WORK_TREE"):
            monkeypatch.delenv(key, raising=False)
        self.repo = tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("synthetic\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.txt").write_text("feature\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "feature")
        self.head = git(self.repo, "rev-parse", "HEAD")
        monkeypatch.chdir(self.repo)
        self.write_issue()

    def done(self, head=None):
        return (f"## Engineer: DONE\n\n{ENGINEER_SUMMARY}\n\n"
                f"Commits: {self.base}..{head or self.head}\n")

    def write_issue(self, body=BODY, comments=None):
        if comments is None:
            comments = ["## Launch: engineer (attempt 1)\nAgent: software-engineer", self.done()]
        data = {"number": 7, "state": "OPEN", "labels": [{"name": "ready"}], "body": body,
                "comments": [{"body": c} for c in comments]}
        (self.tmp / "issue.json").write_text(json.dumps(data))

    def run(self, modes, argv=("ROLE=qa", "ISSUE=7")):
        (self.tmp / "modes").write_text("".join(m + "\n" for m in modes))
        slept = []
        self.code = qa.main(list(argv), sleep=slept.append)
        comments = self.comments()
        return (comments[-1] if comments else None), slept

    def comments(self):
        log = self.tmp / "gh.log"
        if not log.exists():
            return []
        return [json.loads(line)["body"] for line in log.read_text().splitlines()]

    def calls(self, tool=None):
        log = self.tmp / "tools.log"
        if not log.exists():
            return []
        records = [json.loads(line) for line in log.read_text().splitlines()]
        return [r for r in records if tool is None or r["tool"] == tool]


@pytest.fixture
def qa_env(tmp_path, monkeypatch):
    return QaEnv(tmp_path, monkeypatch)


# --- failure rules (spec 6.2) ----------------------------------------------------


@pytest.mark.parametrize("modes,marker,sleeps", [
    (["ok"], "## QA: PASS", []),
    (["invalid"], "## QA: INVALID", []),
    (["transient", "ok"], "## QA: PASS", [60]),
    (["transient"] * 4, "## QA: INVALID", [60, 180, 600]),
    (["crash", "ok"], "## QA: PASS", [60]),
    (["crash"] * 4, "## QA: INVALID", [60, 180, 600]),
    (["panic", "ok"], "## QA: PASS", [60]),
    (["panic"] * 4, "## QA: INVALID", [60, 180, 600]),
    (["timeout", "ok"], "## QA: PASS", []),
    (["timeout", "timeout"], "## QA: INVALID", []),
    (["missing", "ok"], "## QA: PASS", []),
    (["missing", "missing"], "## QA: INVALID", []),
    (["duplicate", "duplicate"], "## QA: INVALID", []),
    (["short_sha", "short_sha"], "## QA: INVALID", []),
    (["short_sha", "ok"], "## QA: PASS", []),
    (["unknown"], "## QA: INVALID", []),
    (["unavailable"], "## QA: UNAVAILABLE", []),
    (["nologin"], "## QA: UNAVAILABLE", []),
    (["fail"], "## QA: FAIL", []),
    (["empty", "ok"], "## QA: PASS", []),
    (["extra", "ok"], "## QA: PASS", []),
    (["empty", "empty"], "## QA: INVALID", []),
    (["extra", "extra"], "## QA: INVALID", []),
])
def test_failure_rules(qa_env, modes, marker, sleeps):
    comment, slept = qa_env.run(modes)
    assert comment.splitlines()[0] == marker
    assert slept == sleeps
    assert qa_env.code == 0
    assert len(qa_env.comments()) == 1
    assert len(qa_env.calls("codex")) == len(modes)


def test_pass_comment_format(qa_env):
    comment, _ = qa_env.run(["ok"])
    lines = comment.splitlines()
    assert lines[0] == "## QA: PASS"
    assert f"- [x] {CRIT_1} - PASS" in lines
    assert "- [x] A duplicate username shows a visible error: - PASS" in lines
    assert "  - the error names the username" in lines  # the issue's own text, nested bullets kept
    assert "      synthetic evidence 1" in lines
    assert "Tests: `uv run --with pytest pytest`, 3 passed, 0 failed" in lines
    assert f"Verified: {qa_env.head}" in lines
    assert lines[lines.index(f"Verified: {qa_env.head}") - 1] == f"Done head: {qa_env.head}"
    assert "Checker: codex" in lines
    assert not any(line.startswith("Retries:") for line in lines)


def test_top_level_verdict_is_ignored(qa_env):
    comment, _ = qa_env.run(["fail"])
    lines = comment.splitlines()
    assert lines[0] == "## QA: FAIL"
    assert f"- [x] {CRIT_1} - PASS" in lines
    assert "- [ ] A duplicate username shows a visible error: - FAIL" in lines
    assert "      second signup printed a traceback" in lines


def test_invalid_criterion_is_named_with_reason(qa_env):
    comment, _ = qa_env.run(["invalid"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert f"- [ ] {CRIT_1} - INVALID" in comment
    assert "criterion 1" in comment and "the browser crashed" in comment


def test_retry_footer(qa_env):
    comment, slept = qa_env.run(["transient", "transient", "ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    assert "Retries: 2 (transient, transient)" in comment.splitlines()
    assert slept == [60, 180]


def test_retry_footer_on_invalid(qa_env):
    comment, _ = qa_env.run(["timeout", "timeout"])
    assert "Retries: 1 (timeout)" in comment.splitlines()
    comment, _ = qa_env.run(["empty", "ok"])
    assert "Retries: 1 (invalid_output)" in comment.splitlines()


def test_timeout_is_read_from_environment_and_kills_the_group(qa_env):
    assert os.environ["QA_CODEX_TIMEOUT"] == "1"
    started = time.monotonic()
    comment, _ = qa_env.run(["timeout", "timeout"])
    assert time.monotonic() - started < 20  # the child sleeps 30 s
    assert comment.splitlines()[0] == "## QA: INVALID"
    pid = int((qa_env.tmp / "child.pid").read_text())
    deadline = time.monotonic() + 3
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(pid)


def test_timeout_then_ok_kills_the_child(qa_env):
    comment, _ = qa_env.run(["timeout", "ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    pid = int((qa_env.tmp / "child.pid").read_text())
    deadline = time.monotonic() + 3
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(pid)


def test_schema_error_reasons_are_named(qa_env):
    comment, _ = qa_env.run(["duplicate", "duplicate"])
    assert "id 1" in comment and "id 2" in comment
    comment, _ = qa_env.run(["short_sha", "short_sha"])
    assert qa_env.head in comment
    comment, _ = qa_env.run(["extra", "extra"])
    assert "note" in comment


def test_transient_reason_is_the_turn_failed_message(qa_env):
    comment, _ = qa_env.run(["transient"] * 4)
    assert "We're currently experiencing high demand" in comment
    assert "OpenAI Codex" not in comment
    assert "Acceptance criteria" not in comment
    assert CRIT_1 not in comment  # no prompt text


def test_crash_is_transient_and_names_the_signal(qa_env):
    comment, slept = qa_env.run(["crash", "transient", "ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    assert "Retries: 2 (transient, transient)" in comment.splitlines()
    assert slept == [60, 180]
    comment, _ = qa_env.run(["crash"] * 4)
    assert "Reason: codex crashed (signal SIGSEGV)" in comment.splitlines()
    assert "OpenAI Codex" not in comment
    assert CRIT_1 not in comment  # no prompt text


def test_panic_reason_is_the_panic_line(qa_env):
    comment, _ = qa_env.run(["panic"] * 4)
    assert comment.splitlines()[0] == "## QA: INVALID"
    reason = [line for line in comment.splitlines() if line.startswith("Reason:")]
    assert reason == ["Reason: codex crashed (panic): thread 'main' panicked at "
                      "codex-rs/core/src/synthetic.rs:12:5:"]
    assert "OpenAI Codex" not in comment
    assert CRIT_1 not in comment


def test_unavailable_reason(qa_env):
    comment, _ = qa_env.run(["unavailable"])
    assert "You've hit your usage limit" in comment
    assert "OpenAI Codex" not in comment
    assert len(qa_env.calls("codex")) == 1


def test_codex_not_installed_is_unavailable(qa_env):
    (qa_env.bin / "codex").unlink()
    assert shutil.which("codex", path=os.environ["PATH"]) is None
    comment, slept = qa_env.run([])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert "not installed" in comment
    assert slept == []


def test_unknown_error_is_not_retried(qa_env):
    comment, _ = qa_env.run(["unknown", "ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "invalid_json_schema" in comment
    assert len(qa_env.calls("codex")) == 1


# --- the issue and the range --------------------------------------------------------


def test_no_acceptance_criteria_is_invalid(qa_env):
    qa_env.write_issue(body="Lane: default\n\n## Goal\n\nNothing to check.\n")
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "acceptance criteria" in comment
    assert qa_env.calls("codex") == []


def test_empty_acceptance_criteria_section_is_invalid(qa_env):
    qa_env.write_issue(body="## Acceptance criteria\n\nSee the plan.\n\n## Out of scope\n\n- [ ] x\n")
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert qa_env.calls("codex") == []


def test_no_commits_line_is_invalid(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 "## Engineer: DONE\n\nNo range here.\n"])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "Commits:" in comment
    assert qa_env.calls("codex") == []


@pytest.mark.parametrize("comments", [
    [],
    ["## Engineer: DONE\n\nCommits: {base}..{head}\n"],  # no engineer launch: not valid
    ["## Launch: engineer (attempt 1)\nAgent: software-engineer", "## Engineer: BLOCKED\n\nstuck\n"],
])
def test_no_valid_done_is_invalid(qa_env, comments):
    qa_env.write_issue(comments=[c.format(base=qa_env.base, head=qa_env.head) for c in comments])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "## Engineer: DONE" in comment
    assert qa_env.calls("codex") == []


def test_unknown_range_head_is_invalid(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head="f" * 40)])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    reason = next(line for line in comment.splitlines() if line.startswith("Reason:"))
    assert "f" * 40 in reason
    assert qa_env.calls("codex") == []


def test_short_range_head_that_resolves_to_head_is_accepted(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head=qa_env.head[:10])])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    assert f"Done head: {qa_env.head}" in comment.splitlines()
    assert f"Verified: {qa_env.head}" in comment


# --- the re-check: HEAD moved past the DONE head (issue #36) ------------------------


def _commit_on_top(qa_env, name="later.txt"):
    (qa_env.repo / name).write_text("later\n")
    git(qa_env.repo, "add", ".")
    git(qa_env.repo, "commit", "-q", "-m", "later")
    return git(qa_env.repo, "rev-parse", "HEAD")


def _record_git(qa_env):
    """Record every git call of qa-codex (to see whether a worktree was created)."""
    calls = []
    real = qa._git

    def recording(*args, cwd=None):
        calls.append(list(args))
        return real(*args, cwd=cwd)

    qa_env.mp.setattr(qa, "_git", recording)
    return calls


@pytest.mark.parametrize("modes,marker", [(["ok"], "## QA: PASS"), (["fail"], "## QA: FAIL")])
def test_recheck_after_head_moved_verifies_base_to_head(qa_env, modes, marker):
    c = _commit_on_top(qa_env)
    comment, _ = qa_env.run(modes)  # the DONE still names Commits: base..B (qa_env.head)
    lines = comment.splitlines()
    assert lines[0] == marker
    (call,) = qa_env.calls("codex")
    assert "later.txt" in call["tree"]  # the worktree is at C, not at B
    worktree = call["argv"][call["argv"].index("-C") + 1]
    assert call["cwd"] == worktree
    assert f"Commit range: {qa_env.base}..{c}\n" in call["stdin"]
    assert f"..{qa_env.head}" not in call["stdin"]
    i = lines.index(f"Verified: {c}")
    assert lines[i - 1] == f"Done head: {qa_env.head}"
    assert issue_state.verified_sha(comment) == c


def test_recheck_with_short_done_head_shows_the_full_sha(qa_env):
    c = _commit_on_top(qa_env)
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head=qa_env.head[:7])])
    comment, _ = qa_env.run(["ok"])
    lines = comment.splitlines()
    assert lines[0] == "## QA: PASS"
    assert f"Done head: {qa_env.head}" in lines
    assert f"Verified: {c}" in lines
    assert f"Commit range: {qa_env.base}..{c}\n" in qa_env.calls("codex")[0]["stdin"]


def test_recheck_still_validates_verified_sha_against_head(qa_env):
    c = _commit_on_top(qa_env)
    comment, _ = qa_env.run(["short_sha", "short_sha"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert f"expected HEAD {c}" in comment
    assert len(qa_env.calls("codex")) == 2


def _assert_not_an_ancestor(qa_env, comment, done_head, head, git_calls):
    assert comment.splitlines()[0] == "## QA: INVALID"
    reason = next(line for line in comment.splitlines() if line.startswith("Reason:"))
    assert done_head in reason and head in reason
    assert "not an ancestor" in reason
    assert "new `## Engineer: DONE`" in reason
    assert qa_env.calls("codex") == []
    assert not any(args[:2] == ["worktree", "add"] for args in git_calls)
    assert "Verified:" not in comment and "Done head:" not in comment
    assert qa_env.code == 0


def test_done_head_on_a_side_branch_is_invalid(qa_env):
    # as after a rebase or an amend: the DONE head is not in the history of HEAD
    git(qa_env.repo, "checkout", "-q", "-b", "side", qa_env.base)
    (qa_env.repo / "side.txt").write_text("side\n")
    git(qa_env.repo, "add", ".")
    git(qa_env.repo, "commit", "-q", "-m", "side")
    side = git(qa_env.repo, "rev-parse", "HEAD")
    git(qa_env.repo, "checkout", "-q", "main")
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head=side)])
    calls = _record_git(qa_env)
    comment, _ = qa_env.run(["ok"])
    _assert_not_an_ancestor(qa_env, comment, side, qa_env.head, calls)


def test_head_reset_before_the_done_head_is_invalid(qa_env):
    git(qa_env.repo, "reset", "-q", "--hard", qa_env.base)  # HEAD is now the parent of the DONE head
    calls = _record_git(qa_env)
    comment, _ = qa_env.run(["ok"])
    _assert_not_an_ancestor(qa_env, comment, qa_env.head, qa_env.base, calls)


def test_unknown_done_head_creates_no_worktree(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head="f" * 40)])
    calls = _record_git(qa_env)
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert not any(args[:2] == ["worktree", "add"] for args in calls)


def test_render_places_done_head_before_verified():
    text = qa.render(good(), criteria=["a", "b"], marker="## QA: PASS", reason="", head=HEAD,
                     done_head="d" * 40, retries=[])
    lines = text.splitlines()
    assert lines[lines.index(f"Verified: {HEAD}") - 1] == f"Done head: {'d' * 40}"
    assert issue_state.verified_sha(text) == HEAD


def test_newest_done_is_used(qa_env):
    qa_env.write_issue(comments=[
        "## Launch: engineer (attempt 1)\nAgent: software-engineer", qa_env.done(head=qa_env.base),
        "## Launch: qa (attempt 1)\nAgent: qa-codex", "## QA: FAIL\n\nsynthetic",
        "## Launch: engineer (attempt 2)\nAgent: software-engineer", qa_env.done()])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: PASS"


# --- the prompt and the command line ------------------------------------------------


def test_prompt_has_role_criteria_and_range_only(qa_env):
    qa_env.run(["ok"])
    (call,) = qa_env.calls("codex")
    prompt = call["stdin"]
    assert (ROOT / "docs" / "team" / "qa-engineer.md").read_text().strip() in prompt
    assert f"{qa_env.base}..{qa_env.head}" in prompt
    assert f"- [ ] {CRIT_1}" in prompt
    assert f"- [ ] {CRIT_2}" in prompt  # nested bullets of criterion 2 included
    assert "Criterion 1" in prompt and "Criterion 2" in prompt
    assert ENGINEER_SUMMARY not in prompt
    assert "Engineer: DONE" not in prompt
    assert "Not a criterion" not in prompt
    assert "Synthetic goal" not in prompt


def test_command_line(qa_env):
    qa_env.run(["ok"])
    (call,) = qa_env.calls("codex")
    argv = call["argv"]
    assert argv[0] == "exec"
    for flag in ("--json", "--ephemeral", "--ignore-user-config"):
        assert flag in argv
    pairs = list(zip(argv, argv[1:]))
    for pair in [("--disable", "hooks"), ("--disable", "apps"), ("--disable", "unbounded_connection_retries"),
                 ("-c", "project_doc_max_bytes=0"), ("-c", "skills.include_instructions=false"),
                 ("-m", qa.QA_MODEL), ("-c", 'model_reasoning_effort="medium"'),
                 ("--enable", "network_proxy"), ("-c", 'default_permissions="qa"'),
                 ("-c", 'permissions.qa={extends=":workspace",network={enabled=true,allow_local_binding=true,'
                        'domains={"localhost"="allow","127.0.0.1"="allow"}}}')]:
        assert pair in pairs
    assert qa.QA_MODEL == "gpt-6-astra"
    assert ("--output-schema", str(ROOT / "scripts" / "qa-result.schema.json")) in pairs
    assert argv[-1] == "-"
    worktree = argv[argv.index("-C") + 1]
    assert call["cwd"] == worktree
    assert Path(worktree).resolve() != qa_env.repo.resolve()
    assert "--skip-git-repo-check" not in argv
    assert "danger-full-access" not in " ".join(argv)


# --- the worktree -----------------------------------------------------------------


def test_worktree_is_removed_and_main_tree_stays_clean(qa_env):
    comment, _ = qa_env.run(["write"])
    assert comment.splitlines()[0] == "## QA: PASS"
    (call,) = qa_env.calls("codex")
    assert not Path(call["argv"][call["argv"].index("-C") + 1]).exists()
    assert git(qa_env.repo, "status", "--porcelain") == ""
    assert len(git(qa_env.repo, "worktree", "list").splitlines()) == 1


@pytest.mark.parametrize("modes", [["unknown"], ["timeout", "timeout"], ["write", "unavailable"]])
def test_worktree_is_removed_after_failure(qa_env, modes):
    qa_env.run(modes)
    assert git(qa_env.repo, "status", "--porcelain") == ""
    assert len(git(qa_env.repo, "worktree", "list").splitlines()) == 1


# --- the frontend pre-step ----------------------------------------------------------


@pytest.fixture
def frontend_env(qa_env, monkeypatch):
    fe = qa_env.tmp / "fe"
    fe.mkdir()
    git(fe, "init", "-q", "-b", "main")
    (fe / "package.json").write_text('{"name": "synthetic-frontend"}\n')
    (fe / ".gitignore").write_text("node_modules/\n")
    git(fe, "add", ".")
    git(fe, "commit", "-q", "-m", "frontend")
    git(qa_env.repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(fe), "frontend")
    git(qa_env.repo, "commit", "-q", "-m", "add frontend")
    qa_env.head = git(qa_env.repo, "rev-parse", "HEAD")
    qa_env.write_issue()
    # the local submodule URL needs the file protocol; the real one is a public https URL
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    return qa_env


def test_frontend_pre_step_runs_before_codex(frontend_env):
    comment, _ = frontend_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    calls = frontend_env.calls()
    assert [c["tool"] for c in calls] == ["npm", "npx", "codex"]
    worktree = Path(calls[2]["argv"][calls[2]["argv"].index("-C") + 1])
    assert calls[0]["argv"] == ["ci"]
    assert calls[1]["argv"] == ["playwright", "install", "chromium"]
    for call in calls[:2]:
        assert Path(call["cwd"]) == worktree / "frontend"
        assert "package.json" in call["files"]  # the submodule commits were fetched
    assert git(frontend_env.repo, "status", "--porcelain") == ""
    assert len(git(frontend_env.repo, "worktree", "list").splitlines()) == 1
    worktrees = frontend_env.repo / ".git" / "worktrees"
    assert not worktrees.exists() or list(worktrees.iterdir()) == []  # the submodule clone went with it
    assert not worktree.exists()


def test_frontend_pre_step_failure_is_unavailable(frontend_env, monkeypatch):
    monkeypatch.setenv("FAKE_NPM_FAIL", "1")
    comment, _ = frontend_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert "npm ci" in comment
    assert "npm ERR! synthetic failure" in comment
    assert "second line" not in comment
    assert frontend_env.calls("codex") == []
    assert frontend_env.calls("npx") == []
    assert len(git(frontend_env.repo, "worktree", "list").splitlines()) == 1


def test_frontend_fetch_failure_is_unavailable(frontend_env, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "never")
    comment, _ = frontend_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert "submodule update" in comment
    assert frontend_env.calls("codex") == []
    assert frontend_env.calls("npm") == []


def test_no_frontend_no_pre_step(qa_env):
    (qa_env.repo / "frontend").mkdir()
    (qa_env.repo / "frontend" / "package.json").write_text("{}\n")
    git(qa_env.repo, "add", ".")
    git(qa_env.repo, "commit", "-q", "-m", "plain frontend folder, not a submodule")
    qa_env.head = git(qa_env.repo, "rev-parse", "HEAD")
    qa_env.write_issue()
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    assert [c["tool"] for c in qa_env.calls()] == ["codex"]


# --- clean retries ---------------------------------------------------------------------


def test_retry_starts_from_the_committed_state(frontend_env):
    comment, slept = frontend_env.run(["dirty", "ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    assert "Retries: 1 (transient)" in comment.splitlines()
    assert slept == [60]
    first, second = frontend_env.calls("codex")
    assert first["tree"]["frontend/package.json"] == '{"name": "synthetic-frontend"}\n'
    tree = second["tree"]
    assert tree["frontend/package.json"] == '{"name": "synthetic-frontend"}\n'
    assert "frontend/untracked.txt" not in tree
    assert "root-untracked.txt" not in tree
    assert tree["frontend/node_modules/keep.txt"] == "installed\n"
    assert [c["tool"] for c in frontend_env.calls()] == ["npm", "npx", "codex", "codex"]  # no second pre-step
    assert len(git(frontend_env.repo, "worktree", "list").splitlines()) == 1


def test_failing_reset_is_invalid(qa_env, monkeypatch):
    real_git = qa._git

    def failing_git(*args, cwd=None):
        if args[0] == "clean":
            return subprocess.CompletedProcess(["git", *args], 1, "", "fatal: synthetic clean failure\n")
        return real_git(*args, cwd=cwd)

    monkeypatch.setattr(qa, "_git", failing_git)
    comment, _ = qa_env.run(["transient", "ok"])
    lines = comment.splitlines()
    assert lines[0] == "## QA: INVALID"
    reason = next(line for line in lines if line.startswith("Reason:"))
    assert "`git clean -ffdq`" in reason and "synthetic clean failure" in reason
    assert len(qa_env.calls("codex")) == 1
    assert len(git(qa_env.repo, "worktree", "list").splitlines()) == 1


def test_reset_covers_nested_submodules(qa_env, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    repos = {}
    for name, child in (("inner", None), ("middle", "inner"), ("outer", "middle")):
        repo = qa_env.tmp / name
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / f"{name}.txt").write_text(f"{name}\n")
        (repo / ".gitignore").write_text("ignored/\n")
        if child:
            git(repo, "submodule", "add", "-q", str(repos[child]), child)
            git(repo, "submodule", "update", "-q", "--init", "--recursive")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", name)
        repos[name] = repo
    clone = qa_env.tmp / "clone"
    git(qa_env.tmp, "clone", "-q", "--recurse-submodules", str(repos["outer"]), str(clone))
    head = git(clone, "rev-parse", "HEAD")
    folders = {"outer": clone, "middle": clone / "middle", "inner": clone / "middle" / "inner"}
    recorded = {name: git(folder, "rev-parse", "HEAD") for name, folder in folders.items()}
    for name, folder in folders.items():
        (folder / f"{name}.txt").write_text("changed\n")
        (folder / "untracked.txt").write_text("untracked\n")
        (folder / "ignored").mkdir()
        (folder / "ignored" / "keep.txt").write_text("kept\n")
    (folders["inner"] / "extra.txt").write_text("x\n")
    git(folders["inner"], "add", ".")
    git(folders["inner"], "commit", "-q", "-m", "moved the submodule HEAD")

    assert qa._reset_worktree(clone, head) is None

    for name, folder in folders.items():
        assert git(folder, "rev-parse", "HEAD") == recorded[name]
        assert (folder / f"{name}.txt").read_text() == f"{name}\n"
        assert not (folder / "untracked.txt").exists()
        assert (folder / "ignored" / "keep.txt").read_text() == "kept\n"
    assert not (folders["inner"] / "extra.txt").exists()


# --- interrupts -------------------------------------------------------------------------


def _wait_for_pid(path, proc, limit=20):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        assert proc.poll() is None, proc.communicate()
        try:
            return int(path.read_text())
        except (OSError, ValueError):
            time.sleep(0.05)
    raise AssertionError(f"no PID in {path}")


def _interrupt(qa_env, pid_file, sig):
    """Run qa-codex as a subprocess, send `sig` to it once the fake child runs. The child's PID."""
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "ROLE=qa", "ISSUE=7"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        pid = _wait_for_pid(pid_file, proc)
        proc.send_signal(sig)
        started = time.monotonic()
        proc.communicate(timeout=10)
        while alive(pid) and time.monotonic() - started < 10:
            time.sleep(0.05)
        assert time.monotonic() - started < 10
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    assert proc.returncode == 128 + sig
    assert not alive(pid)
    assert len(git(qa_env.repo, "worktree", "list").splitlines()) == 1
    worktrees = qa_env.repo / ".git" / "worktrees"
    assert not worktrees.exists() or list(worktrees.iterdir()) == []
    assert qa_env.comments() == []
    return pid


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_interrupt_during_codex_cleans_up(qa_env, monkeypatch, sig):
    monkeypatch.setenv("QA_CODEX_TIMEOUT", "600")
    (qa_env.tmp / "modes").write_text("timeout\n")
    _interrupt(qa_env, qa_env.tmp / "child.pid", sig)
    assert len(qa_env.calls("codex")) == 1


def test_interrupt_during_pre_step_cleans_up(frontend_env, monkeypatch):
    monkeypatch.setenv("QA_PRESTEP_TIMEOUT", "600")
    monkeypatch.setenv("FAKE_NPM_WAIT", str(frontend_env.tmp / "npm.pid"))
    _interrupt(frontend_env, frontend_env.tmp / "npm.pid", signal.SIGTERM)
    assert frontend_env.calls("codex") == []
    assert [c["tool"] for c in frontend_env.calls()] == ["npm"]


def _worktrees_gone(qa_env):
    assert len(git(qa_env.repo, "worktree", "list").splitlines()) == 1
    (call,) = qa_env.calls("codex")
    worktree = Path(call["argv"][call["argv"].index("-C") + 1])
    assert not worktree.exists() and not worktree.parent.exists()  # the worktree and its temp folder


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_interrupt_during_retry_wait_cleans_up(qa_env, sig):
    (qa_env.tmp / "modes").write_text("transient\nok\n")
    code = qa.main(["ROLE=qa", "ISSUE=7"], sleep=lambda s: os.kill(os.getpid(), sig) or time.sleep(1))
    assert code == 128 + sig
    assert qa_env.comments() == []
    _worktrees_gone(qa_env)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL  # the handlers are restored


def test_second_signal_does_not_stop_the_cleanup(qa_env, monkeypatch):
    real_remove = qa._remove_worktree
    seen = []

    def remove(repo, worktree):
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGTERM)
        seen.append(worktree)
        real_remove(repo, worktree)

    monkeypatch.setattr(qa, "_remove_worktree", remove)
    (qa_env.tmp / "modes").write_text("transient\nok\n")
    code = qa.main(["ROLE=qa", "ISSUE=7"], sleep=lambda s: os.kill(os.getpid(), signal.SIGHUP) or time.sleep(1))
    assert code == 128 + signal.SIGHUP
    assert len(seen) == 1
    assert qa_env.comments() == []
    _worktrees_gone(qa_env)


# --- a signal during the cleanup (finally block of _main) --------------------------------


def _signal_in(monkeypatch, module, name, *sigs):
    """Wrap `module.name` so it sends `sigs` to this process, then runs. Returns the call args."""
    real = getattr(module, name)
    seen = []

    def wrapped(*args):
        seen.append(args)
        for sig in sigs:
            os.kill(os.getpid(), sig)
        return real(*args)

    monkeypatch.setattr(module, name, wrapped)
    return seen


def _removed(qa_env, worktree):
    assert len(git(qa_env.repo, "worktree", "list").splitlines()) == 1
    assert not worktree.exists() and not worktree.parent.exists()  # the worktree and its temp folder


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_signal_during_worktree_removal_finishes_the_cleanup(qa_env, monkeypatch, sig):
    seen = _signal_in(monkeypatch, qa, "_remove_worktree", sig)
    comment, _ = qa_env.run(["ok"])
    assert len(seen) == 1
    _removed(qa_env, seen[0][1])
    _worktrees_gone(qa_env)
    assert qa_env.code == 128 + sig
    assert comment is None and qa_env.comments() == []
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL  # the handlers are restored


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_signal_during_kill_children_in_cleanup_finishes_the_cleanup(qa_env, monkeypatch, sig):
    calls = []
    real_kill = codex_exec.kill_children

    def kill_children():
        calls.append(1)
        if len(calls) == 1:  # the first call is the one at the start of the finally block of _main
            os.kill(os.getpid(), sig)
        real_kill()

    monkeypatch.setattr(codex_exec, "kill_children", kill_children)
    comment, _ = qa_env.run(["ok"])
    _worktrees_gone(qa_env)
    assert qa_env.code == 128 + sig
    assert comment is None and qa_env.comments() == []
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_second_signal_during_worktree_removal_keeps_the_first(qa_env, monkeypatch):
    seen = _signal_in(monkeypatch, qa, "_remove_worktree", signal.SIGTERM, signal.SIGINT)
    comment, _ = qa_env.run(["ok"])
    assert len(seen) == 1
    _removed(qa_env, seen[0][1])
    assert qa_env.code == 128 + signal.SIGTERM
    assert comment is None and qa_env.comments() == []


def test_signal_during_cleanup_after_a_posted_comment(frontend_env, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_NPM_FAIL", "1")
    seen = _signal_in(monkeypatch, qa, "_remove_worktree", signal.SIGTERM)
    frontend_env.run(["ok"])
    assert frontend_env.code == 128 + signal.SIGTERM
    comments = frontend_env.comments()
    assert len(comments) == 1 and comments[0].splitlines()[0] == "## QA: UNAVAILABLE"
    assert len(seen) == 1
    _removed(frontend_env, seen[0][1])
    err = capsys.readouterr().err
    assert "SIGTERM" in err
    assert "no comment posted" not in err


# --- gh failures and arguments -------------------------------------------------------


def test_failing_post_exits_non_zero(qa_env, monkeypatch):
    monkeypatch.setenv("FAKE_GH_COMMENT_FAIL", "1")
    comment, _ = qa_env.run(["ok"])
    assert comment is None
    assert qa_env.code != 0


def test_failing_issue_view_exits_non_zero(qa_env, monkeypatch):
    monkeypatch.setenv("FAKE_GH_FAIL", "1")
    comment, _ = qa_env.run(["ok"])
    assert comment is None
    assert qa_env.code != 0
    assert qa_env.calls("codex") == []


@pytest.mark.parametrize("argv", [[], ["ROLE=qa"], ["ROLE=pm", "ISSUE=7"], ["ROLE=qa", "ISSUE=x"],
                                  ["ROLE=qa", "ISSUE=7", "extra"], ["ISSUE=7", "ROLE=qa"],
                                  ["ROLE=qa", "ISSUE=07"], ["ROLE=qa", "ISSUE=-7"]])
def test_wrong_arguments_exit_non_zero(qa_env, argv):
    comment, _ = qa_env.run(["ok"], argv=argv)
    assert comment is None
    assert qa_env.code != 0
    assert qa_env.calls("codex") == []
    assert not (qa_env.tmp / "gh-calls.log").exists()


def test_script_entry_point_rejects_wrong_arguments(qa_env):
    p = subprocess.run([sys.executable, str(SCRIPT), "ROLE=qa"], capture_output=True, text=True)
    assert p.returncode != 0
    assert "ROLE=qa ISSUE=<n>" in p.stderr
    assert not (qa_env.tmp / "gh-calls.log").exists()


def test_script_is_executable_with_uv_header():
    assert os.access(SCRIPT, os.X_OK)
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env -S uv run --script\n")
    assert "# /// script" in text and "dependencies = []" in text


# --- parse_criteria ----------------------------------------------------------------


def test_parse_criteria_keeps_nested_bullets():
    assert qa.parse_criteria(BODY) == [CRIT_1, CRIT_2]


@pytest.mark.parametrize("box", ["[x]", "[X]"])
def test_parse_criteria_counts_checked_items(box):
    assert qa.parse_criteria(BODY.replace("- [ ] A visitor", f"- {box} A visitor")) == [CRIT_1, CRIT_2]


def test_parse_criteria_crlf():
    assert qa.parse_criteria(BODY.replace("\n", "\r\n")) == [CRIT_1, CRIT_2]


def test_parse_criteria_edge_cases():
    assert qa.parse_criteria("") == []
    assert qa.parse_criteria("## Goal\n\n- [ ] not here\n") == []
    body = ("## Acceptance criteria\n\n- [ ] one\n  continued\n\n  after a blank line\n"
            "lazy continuation\n\nPlain text after a blank line ends the item\n- [ ] two\n"
            "  - [ ] a nested checkbox is part of two\n\n"
            "### A sub heading does not end the section\n- [ ] three\n\n## Out of scope\n\n- [ ] four\n")
    assert qa.parse_criteria(body) == [
        "one\n  continued\n\n  after a blank line\nlazy continuation",
        "two\n  - [ ] a nested checkbox is part of two",
        "three",
    ]


def test_prompt_numbers_criteria_from_one():
    prompt = qa.build_prompt([CRIT_1, CRIT_2], "b" * 40, "a" * 40)
    first = prompt.index(f"Criterion 1:\n- [ ] {CRIT_1}")
    assert first < prompt.index(f"Criterion 2:\n- [ ] {CRIT_2}")
    assert "Criterion 0" not in prompt and "Criterion 3" not in prompt
    assert f"{'b' * 40}..{'a' * 40}" in prompt


# --- validate ----------------------------------------------------------------------


HEAD = "a" * 40


def good(n=2):
    return {"verdict": "pass",
            "criteria": [{"id": i, "verdict": "pass", "evidence": "e"} for i in range(1, n + 1)],
            "tests": {"command": "c", "result": "r"}, "verified_sha": HEAD}


def test_validate_accepts_good_output():
    assert qa.validate(good(), ["a", "b"], HEAD) == []


@pytest.mark.parametrize("change", [
    lambda o: o.pop("tests"),
    lambda o: o.update(extra=1),
    lambda o: o.update(verdict="invalid"),
    lambda o: o["criteria"][0].update(verdict="maybe"),
    lambda o: o["criteria"][0].update(id="1"),
    lambda o: o["criteria"][0].update(id=True),
    lambda o: o["criteria"][0].pop("evidence"),
    lambda o: o["criteria"][0].update(note="x"),
    lambda o: o["tests"].update(extra="x"),
    lambda o: o["tests"].update(result=3),
    lambda o: o.update(criteria={}),
    lambda o: o.update(verified_sha=HEAD[:7]),
    lambda o: o.update(verified_sha=None),
    lambda o: o["criteria"].pop(),
    lambda o: o["criteria"].append({"id": 3, "verdict": "pass", "evidence": "e"}),
    lambda o: o["criteria"].__setitem__(1, {"id": 1, "verdict": "pass", "evidence": "e"}),
    lambda o: o["criteria"].__setitem__(1, {"id": 0, "verdict": "pass", "evidence": "e"}),
])
def test_validate_rejects(change):
    output = good()
    change(output)
    assert qa.validate(output, ["a", "b"], HEAD) != []


@pytest.mark.parametrize("output", [None, [], "text", 3])
def test_validate_rejects_non_objects(output):
    assert qa.validate(output, ["a"], HEAD) != []


def test_schema_file_matches_the_issue():
    schema = json.loads((ROOT / "scripts" / "qa-result.schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["verdict", "criteria", "tests", "verified_sha"]
    item = schema["properties"]["criteria"]["items"]
    assert item["required"] == ["id", "verdict", "evidence"]
    assert item["properties"]["verdict"]["enum"] == ["pass", "fail", "invalid"]
    assert "text" not in item["properties"]


# --- render ------------------------------------------------------------------------


def test_render_without_output():
    text = qa.render(None, criteria=["a"], marker="## QA: UNAVAILABLE", reason="codex is not installed",
                     head=HEAD, retries=["transient", "timeout"])
    lines = text.splitlines()
    assert lines[0] == "## QA: UNAVAILABLE"
    assert "Reason: codex is not installed" in lines
    assert "Checker: codex" in lines
    assert "Retries: 2 (transient, timeout)" in lines
    assert "## QA: PASS" not in text


# --- codex_exec ----------------------------------------------------------------------


@pytest.mark.parametrize("line,status", [
    ("sh: 1: codex: not found", "unavailable"),
    ("env: 'codex': No such file or directory", "unavailable"),
    ("ERROR: unexpected status 401 Unauthorized: Missing bearer", "unavailable"),
    ("Not logged in", "unavailable"),
    ("You've hit your usage limit. Try again later.", "unavailable"),
    ("Quota exceeded. Check your plan and billing details.", "unavailable"),
    ("ERROR: exceeded retry limit, last status: 429 Too Many Requests", "transient"),
    ("rate limit exceeded: Rate limit reached (synthetic). Please try again in 1s.", "transient"),
    ("We're currently experiencing high demand, which may cause temporary errors.", "transient"),
    ("Selected model is at capacity. Please try a different model.", "transient"),
    ("unexpected status 502 Bad Gateway: synthetic", "transient"),
    ("ERROR: Connection failed: error sending request", "transient"),
    ('{"type": "error", "error": {"code": "invalid_json_schema"}}', "unknown"),
    ("ERROR: Reconnecting... 2/5", "unknown"),
    ("2026-09-26T13:12:14.490070Z ERROR codex_api: failed: HTTP error: 401 Unauthorized", "unknown"),
])
def test_classify_failure(line, status):
    assert codex_exec.classify_failure(1, line) == status


@pytest.mark.parametrize("returncode,text,status", [
    (-11, "", "transient"),                                     # killed by SIGSEGV
    (-6, "", "transient"),                                      # SIGABRT (panic = abort)
    (-9, "OpenAI Codex v0.153.4\nuser\nprompt", "transient"),  # SIGKILL, e.g. the OOM killer
    (139, "", "transient"),                                     # 128 + SIGSEGV, as a shell reports it
    (101, "thread 'main' panicked at src/x.rs:1:1:\nboom", "transient"),
    (1, "thread 'tokio-runtime-worker' panicked at src/x.rs:1:1:", "transient"),
    (-11, "ERROR: You've hit your usage limit. Try again later.", "unavailable"),  # the table wins
    (1, "", "unknown"),
    (1, "ERROR: invalid_json_schema", "unknown"),
    (2, "error: unexpected argument '--bad' found", "unknown"),
    (127, "", "unknown"),
    (128, "", "unknown"),
    (101, "boom", "unknown"),                                    # exit 101 without a panic line
])
def test_classify_failure_crashed_process(returncode, text, status):
    assert codex_exec.classify_failure(returncode, text) == status


@pytest.mark.parametrize("returncode,stderr,reason", [
    (-11, "", "codex crashed (signal SIGSEGV)"),
    (137, "OpenAI Codex v0.153.4\nuser\nprompt text", "codex crashed (signal SIGKILL)"),
    (101, "OpenAI Codex v0.153.4\nuser\nprompt text\nthread 'main' panicked at a.rs:1:1:\nboom\nnote: x",
     "codex crashed (panic): thread 'main' panicked at a.rs:1:1:"),
])
def test_crash_reason(returncode, stderr, reason):
    assert codex_exec.crash_reason(returncode, "", stderr) == reason


def test_crash_reason_is_none_without_a_crash():
    assert codex_exec.crash_reason(1, "", "ERROR: something") is None
    assert codex_exec.crash_reason(-11, "", "ERROR: You've hit your usage limit.") is None


def test_failure_text_prefers_last_turn_failed():
    stdout = "\n".join(json.dumps(e) for e in [
        {"type": "turn.failed", "error": {"message": "first"}},
        {"type": "error", "message": "not this"},
        {"type": "turn.failed", "error": {"message": "second"}}]) + "\nnot json\n"
    assert codex_exec.failure_text(stdout, "OpenAI Codex v0.153.4\nuser\nprompt") == "second"


def test_failure_text_falls_back_to_stderr():
    assert codex_exec.failure_text("", "log line\nError loading config.toml: bad") == \
        "log line\nError loading config.toml: bad"


def test_base_flags():
    assert codex_exec.BASE_FLAGS[:3] == ["--json", "--ephemeral", "--ignore-user-config"]
    assert "unbounded_connection_retries" in codex_exec.BASE_FLAGS


# --- docs/team/qa-engineer.md (spec 7) ---------------------------------------------------


def test_qa_role_file_has_spec_7_behavior():
    text = (ROOT / "docs" / "team" / "qa-engineer.md").read_text()
    for needle in [
        "exercise the behavior",
        "only mirrors the implementation",
        "A criterion without enough evidence cannot pass",
        "secondary evidence",
        "git diff --submodule=diff <base>..<head>",
        "Do not install anything",
        "the criterion fails (undeclared dependency)",
        "PASS, FAIL or INVALID",
        "It is INVALID if you cannot verify a criterion for a technical reason",
        "`## QA: INVALID`",
        "When `scripts/qa-codex` runs you, return only the JSON that the schema asks for. Do not post a comment.",
        "Give each criterion's number as `id`",
        "Checker: claude (fallback)",
        "Start the app and run the browser check in one command",
    ]:
        assert needle in text, needle
    assert text.count("Checker: claude (fallback)") == 2  # the example and the definition of done


# --- redaction (spec P5) -----------------------------------------------------------------
# All secrets below are synthetic. The env vars are set with monkeypatch, never read.

ENV_SECRET = "synthEnvSecretValue0123456789ABCDEF"
GH_TOKEN_SYN = "ghp_" + "Z9" * 15
SK_KEY_SYN = "sk-proj-" + "q7_W-" * 6

# A fake codex that the test scripts: SCRIPTED_CODEX=<path> to a JSON file with either
# {"message": ...} (turn.failed, exit 1) or {"output": ...} (written to the -o file; the value
# "HEAD" of verified_sha becomes `git rev-parse HEAD`).
SCRIPTED_CODEX = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
args = sys.argv[1:]
sys.stdin.read()
with open(os.environ["SCRIPTED_CODEX"], encoding="utf-8") as f:
    spec = json.load(f)
if "message" in spec:
    print(json.dumps({"type": "turn.failed", "error": {"message": spec["message"]}}))
    sys.exit(1)
out = spec["output"]
if out.get("verified_sha") == "HEAD":
    out["verified_sha"] = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                         check=True).stdout.strip()
with open(args[args.index("-o") + 1], "w", encoding="utf-8") as f:
    json.dump(out, f)
'''

# A fake npm whose failure line is SCRIPTED_NPM_LINE.
SCRIPTED_NPM = r'''#!/usr/bin/env python3
import os, sys
sys.stderr.write("npm ERR! " + os.environ["SCRIPTED_NPM_LINE"] + "\n")
sys.exit(1)
'''


def _install(qa_env, tool, source):
    path = qa_env.bin / tool
    path.unlink()
    path.write_text(source)
    path.chmod(0o755)


def _scripted(qa_env, monkeypatch, spec):
    _install(qa_env, "codex", SCRIPTED_CODEX)
    (qa_env.tmp / "scripted.json").write_text(json.dumps(spec))
    monkeypatch.setenv("SCRIPTED_CODEX", str(qa_env.tmp / "scripted.json"))


def _output(evidence=("e1", "e2"), verdicts=("pass", "pass"), verdict="pass"):
    return {"verdict": verdict,
            "criteria": [{"id": i, "verdict": v, "evidence": e}
                         for i, (v, e) in enumerate(zip(verdicts, evidence), 1)],
            "tests": {"command": "uv run --with pytest pytest", "result": "3 passed"},
            "verified_sha": "HEAD"}


def _no_part(secret, text, n=8):
    return all(secret[i:i + n] not in text for i in range(len(secret) - n + 1))


@pytest.fixture
def secret_env(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", ENV_SECRET)
    return ENV_SECRET


@pytest.mark.parametrize("verdicts,marker", [(("pass", "pass"), "## QA: PASS"),
                                             (("pass", "fail"), "## QA: FAIL")])
def test_evidence_secrets_are_redacted(qa_env, monkeypatch, secret_env, verdicts, marker):
    evidence = (f"the log printed {secret_env} and Authorization: Basic c3ludGg6c2VjcmV0",
                f"saw {GH_TOKEN_SYN}, {SK_KEY_SYN} and https://x.invalid/?access_token=abc123def&x=1")
    _scripted(qa_env, monkeypatch, {"output": _output(evidence, verdicts)})
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == marker
    assert "[redacted]" in comment
    for secret in (secret_env, GH_TOKEN_SYN, SK_KEY_SYN, "c3ludGg6c2VjcmV0", "abc123def"):
        assert secret not in comment, secret
    assert "access_token=[redacted]&x=1" in comment
    assert "Authorization: [redacted]" in comment


def test_invalid_criterion_reason_is_redacted(qa_env, monkeypatch, secret_env):
    _scripted(qa_env, monkeypatch, {"output": _output((f"cannot log in with {secret_env}", "ok"),
                                                      ("invalid", "pass"))})
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == "## QA: INVALID"
    reason = next(line for line in comment.splitlines() if line.startswith("Reason:"))
    assert "criterion 1" in reason and "[redacted]" in reason
    assert secret_env not in comment


def test_schema_error_is_redacted(qa_env, monkeypatch, secret_env):
    _scripted(qa_env, monkeypatch, {"output": _output(verdict=f"Bearer {secret_env}x")})
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "output does not match the schema" in comment
    assert "[redacted]" in comment
    assert secret_env not in comment


def test_codex_failure_message_is_redacted(qa_env, monkeypatch, secret_env):
    _scripted(qa_env, monkeypatch, {"message": f"request failed with key {secret_env} and Bearer abcdefgh123"})
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "[redacted]" in comment
    assert secret_env not in comment and "abcdefgh123" not in comment


def test_codex_failure_message_cut_does_not_leak(qa_env, monkeypatch, secret_env):
    message = "x" * (codex_exec.REASON_MAX - 3 - 20) + " " + secret_env + " tail"
    _scripted(qa_env, monkeypatch, {"message": message})
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert _no_part(secret_env, comment)


def test_one_line_redacts_before_the_cut(secret_env):
    line = codex_exec._one_line("x" * (codex_exec.REASON_MAX - 20) + GH_TOKEN_SYN + " " + secret_env)
    assert len(line) <= codex_exec.REASON_MAX
    assert _no_part(secret_env, line) and _no_part(GH_TOKEN_SYN, line)


def test_pre_step_output_is_redacted(frontend_env, monkeypatch, secret_env):
    _install(frontend_env, "npm", SCRIPTED_NPM)
    monkeypatch.setenv("SCRIPTED_NPM_LINE", f"could not fetch with token={secret_env}")
    comment, _ = frontend_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert "[redacted]" in comment
    assert secret_env not in comment


def test_pre_step_line_cut_does_not_leak(frontend_env, monkeypatch, secret_env):
    _install(frontend_env, "npm", SCRIPTED_NPM)
    prefix = "x" * (codex_exec.REASON_MAX - len("npm ERR! ") - 20) + " "
    monkeypatch.setenv("SCRIPTED_NPM_LINE", prefix + secret_env + " tail")
    comment, _ = frontend_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert _no_part(secret_env, comment)


def test_redact_env_values_longest_first(monkeypatch):
    monkeypatch.setenv("SHORT_TOKEN", "abcdefgh")
    monkeypatch.setenv("LONG_Secret", "abcdefgh-and-more")
    monkeypatch.setenv("TINY_PASSWORD", "seven77")  # under 8 characters: kept
    monkeypatch.setenv("PLAIN_NAME", "notasecretvalue")
    text = "a abcdefgh-and-more b abcdefgh c seven77 d notasecretvalue"
    assert codex_exec.redact(text) == "a [redacted] b [redacted] c seven77 d notasecretvalue"


def test_redact_env_name_is_case_insensitive(monkeypatch):
    for name in ("my_key", "gh_Token", "app_secret", "db_password"):
        monkeypatch.setenv(name, f"value-of-{name}")
    text = " ".join(f"value-of-{n}" for n in ("my_key", "gh_Token", "app_secret", "db_password"))
    assert codex_exec.redact(text) == " ".join(["[redacted]"] * 4)


@pytest.mark.parametrize("text,expected", [
    ("Authorization: Basic abc", "Authorization: [redacted]"),
    ("x\nauthorization: token abc def\ny", "x\nauthorization: [redacted]\ny"),
    ("use Bearer abcdefgh now", "use Bearer [redacted] now"),
    ("use bearer abcdefg now", "use bearer abcdefg now"),  # 7 characters: kept
    ("t " + "ghp_" + "a1" * 10 + " e", "t [redacted] e"),
    ("t " + "GHO_" + "A1" * 10, "t [redacted]"),
    ("t " + "ghs_" + "a1" * 10, "t [redacted]"),
    ("t " + "ghu_" + "a1" * 10, "t [redacted]"),
    ("t " + "ghr_" + "a1" * 10, "t [redacted]"),
    ("t " + "ghp_" + "a" * 19, "t " + "ghp_" + "a" * 19),  # 19 characters: kept
    ("t github_pat_" + "a_1" * 7 + " e", "t [redacted] e"),
    ("t sk-" + "a_b-" * 5 + " e", "t [redacted] e"),
    ("t SK-PROJ-" + "ab12" * 5, "t [redacted]"),
    ("t sk-" + "a" * 19, "t sk-" + "a" * 19),
    ("?token=abc&key=def ", "?token=[redacted]&key=[redacted] "),
    ("api_key=abc123'x", "api_key=[redacted]'x"),
    ("ACCESS_TOKEN=abc\"x", "ACCESS_TOKEN=[redacted]\"x"),
    ("password=hunter2`x", "password=[redacted]`x"),
    ("Password=a b", "Password=[redacted] b"),
])
def test_redact_patterns(text, expected):
    assert codex_exec.redact(text, environ={}) == expected


def test_redact_keeps_a_normal_pass_comment(secret_env, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_GH_TOKEN", GH_TOKEN_SYN)
    head = "0123456789abcdef0123456789abcdef01234567"
    output = {"verdict": "pass", "criteria": [
        {"id": 1, "verdict": "pass", "evidence": "created an account with the form, got a 201"},
        {"id": 2, "verdict": "pass", "evidence": "the error names the username; the input is kept"}],
        "tests": {"command": "uv run --with pytest pytest", "result": "42 passed, 0 failed"},
        "verified_sha": head}
    text = qa.render(output, criteria=[CRIT_1, CRIT_2], marker="## QA: PASS", reason="", head=head,
                     retries=["transient"], done_head="fedcba9876543210fedcba9876543210fedcba98")
    assert codex_exec.redact(text) == text
    lines = text.splitlines()
    assert lines[0] == "## QA: PASS"
    assert "Done head: fedcba9876543210fedcba9876543210fedcba98" in lines
    assert f"Verified: {head}" in lines and "Checker: codex" in lines and "Retries: 1 (transient)" in lines


def test_normal_pass_comment_is_posted_unchanged(qa_env, secret_env):
    comment, _ = qa_env.run(["ok"])
    output = {"verdict": "pass", "criteria": [
        {"id": i, "verdict": "pass", "evidence": f"synthetic evidence {i}"} for i in (1, 2)],
        "tests": {"command": "uv run --with pytest pytest", "result": "3 passed, 0 failed"},
        "verified_sha": qa_env.head}
    assert comment == qa.render(output, criteria=[CRIT_1, CRIT_2], marker="## QA: PASS", reason="",
                                head=qa_env.head, retries=[], done_head=qa_env.head)


def test_one_post_path_through_redact():
    source = SCRIPT.read_text()
    assert source.count('"comment"') == 1  # the only `gh issue comment` call
    post = source[source.index("def _post("):source.index("def _parse_args(")]
    assert '"issue", "comment"' in post
    assert "input=codex_exec.redact(body)" in post


def test_prompt_forbids_quoting_secrets():
    prompt = qa.build_prompt([CRIT_1], "b" * 40, "a" * 40)
    assert "Do not quote secrets (keys, tokens, passwords) in your evidence" in prompt


# --- multi-line secrets (#37) -------------------------------------------------------------
# A synthetic secret of several unique lines in an env var whose name matches SECRET_NAME.
# "Leaks": the whole value, or any one of its lines, is a substring of what `gh` receives.

MULTI_SECRET = ("-----BEGIN FAKE KEY-----\nAAAAfakefakefake1111\nBBBBfakefakefake2222\n"
                "-----END FAKE KEY-----")

# A fake tool that writes SCRIPTED_STDERR and SCRIPTED_STDOUT (JSON strings) and exits 1.
SCRIPTED_FAILURE = r'''#!/usr/bin/env python3
import json, os, sys
if not sys.stdin.isatty():
    try:
        sys.stdin.read()
    except OSError:
        pass
sys.stdout.write(json.loads(os.environ.get("SCRIPTED_STDOUT", '""')))
sys.stderr.write(json.loads(os.environ.get("SCRIPTED_STDERR", '""')))
sys.exit(int(os.environ.get("SCRIPTED_EXIT", "1")))
'''


def _leaks(secret, text):
    return secret in text or any(line in text for line in secret.splitlines())


@pytest.fixture
def multi_secret(monkeypatch):
    monkeypatch.setenv("FAKE_API_KEY", MULTI_SECRET)
    lines = MULTI_SECRET.splitlines()
    assert len(lines) >= 3 and len(set(lines)) == len(lines) and all(len(x) >= 8 for x in lines)
    return MULTI_SECRET


def _scripted_failure(env, monkeypatch, tool, stdout="", stderr="", code=1):
    _install(env, tool, SCRIPTED_FAILURE)
    monkeypatch.setenv("SCRIPTED_STDOUT", json.dumps(stdout))
    monkeypatch.setenv("SCRIPTED_STDERR", json.dumps(stderr))
    monkeypatch.setenv("SCRIPTED_EXIT", str(code))


@pytest.mark.parametrize("verdicts,marker", [(("pass", "pass"), "## QA: PASS"),
                                             (("pass", "fail"), "## QA: FAIL"),
                                             (("invalid", "pass"), "## QA: INVALID")])
@pytest.mark.parametrize("where", [0, 1])
def test_multi_line_secret_in_evidence_does_not_leak(qa_env, monkeypatch, multi_secret, verdicts, marker,
                                                     where):
    evidence = ["checked the form", "checked the error"]
    evidence[where] = f"the log printed the key:\n{multi_secret}\nand then stopped"
    _scripted(qa_env, monkeypatch, {"output": _output(tuple(evidence), verdicts)})
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == marker
    assert "[redacted]" in comment
    assert not _leaks(multi_secret, comment), comment
    if marker == "## QA: INVALID":
        reason = next(line for line in comment.splitlines() if line.startswith("Reason:"))
        assert "criterion 1" in reason


@pytest.mark.parametrize("stream", ["stderr", "stdout"])
def test_multi_line_secret_in_pre_step_output_does_not_leak(frontend_env, monkeypatch, multi_secret, stream):
    text = f"npm WARN setup\nnpm ERR! could not fetch with the key {multi_secret}\nnpm ERR! done\n"
    _scripted_failure(frontend_env, monkeypatch, "npm", **{stream: text})
    comment, _ = frontend_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert "pre-step `npm ci` failed: npm ERR! could not fetch with the key [redacted]" in comment
    assert not _leaks(multi_secret, comment), comment


def test_multi_line_secret_in_codex_stderr_does_not_leak(qa_env, monkeypatch, multi_secret):
    stderr = ("OpenAI Codex v0.153.4 (fake)\n--------\n"
              f"ERROR: unexpected status 401 Unauthorized: key {multi_secret}\nmore\n")
    _scripted_failure(qa_env, monkeypatch, "codex", stdout='{"type": "thread.started"}\n', stderr=stderr)
    comment, _ = qa_env.run([])
    assert comment.splitlines()[0] == "## QA: UNAVAILABLE"
    assert "Reason: ERROR: unexpected status 401 Unauthorized: key [redacted]" in comment
    assert not _leaks(multi_secret, comment), comment


def test_failure_reason_redacts_before_picking_a_line(multi_secret):
    stderr = f"banner\nERROR: rate limit exceeded: key {multi_secret}\n"
    reason = codex_exec.failure_reason("", stderr)
    assert reason == "ERROR: rate limit exceeded: key [redacted]"
    last = codex_exec.failure_reason("", f"banner\nno pattern here {multi_secret}\n")
    assert "[redacted]" in last and not _leaks(multi_secret, last)


def test_panic_reason_redacts_before_picking_the_line(multi_secret):
    stderr = f"banner\nthread 'main' panicked at x.rs:1:2: key {multi_secret}\n"
    reason = codex_exec.crash_reason(101, "", stderr)
    assert reason == "codex crashed (panic): thread 'main' panicked at x.rs:1:2: key [redacted]"
    assert codex_exec.classify_failure(101, stderr) == "transient"


def test_multi_line_reason_is_still_cut_to_reason_max(multi_secret):
    stderr = "ERROR: rate limit exceeded: " + "x" * codex_exec.REASON_MAX + f" {multi_secret}\n"
    reason = codex_exec.failure_reason("", stderr)
    assert len(reason) <= codex_exec.REASON_MAX and reason.endswith("...")
    assert not _leaks(multi_secret, reason)
