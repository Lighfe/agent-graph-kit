"""Tests for scripts/qa-codex and scripts/codex_exec.py.

Each flow test runs `main([...], sleep=recorded.append)` in a temporary git repo, with the
fakes `gh`, `codex`, `npm` and `npx` from tests/fakes/ first on PATH. No real `gh` or
`codex` runs and no test uses the network. All issue data is synthetic.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

import codex_exec

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
        for key in ("FAKE_GH_FAIL", "FAKE_GH_COMMENT_FAIL", "FAKE_NPM_FAIL", "GIT_DIR", "GIT_WORK_TREE"):
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


def test_stale_range_head_is_invalid(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head=qa_env.base)])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert qa_env.base in comment and qa_env.head in comment
    assert qa_env.calls("codex") == []


def test_unknown_range_head_is_invalid(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head="f" * 40)])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: INVALID"
    assert "f" * 40 in comment and qa_env.head in comment
    assert qa_env.calls("codex") == []


def test_short_range_head_that_resolves_to_head_is_accepted(qa_env):
    qa_env.write_issue(comments=["## Launch: engineer (attempt 1)\nAgent: software-engineer",
                                 qa_env.done(head=qa_env.head[:10])])
    comment, _ = qa_env.run(["ok"])
    assert comment.splitlines()[0] == "## QA: PASS"
    assert f"Verified: {qa_env.head}" in comment


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
