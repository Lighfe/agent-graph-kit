"""Tests for .claude/hooks/not_started.py (PermissionDenied hook, issue #48).

`handle` is tested in-process with synthetic events and fakes for reading the
issue and posting. `main` is tested in-process and as a subprocess with the
fakes in tests/fakes/ first on PATH, so no real `gh` or `git` runs. All ids
and texts are synthetic.
"""

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import not_started
from helpers import cont, launch
from helpers import not_started as ns_comment
from issue_state import Issue

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "hooks" / "not_started.py"
FAKES = ROOT / "tests" / "fakes"

TOOL_USE_ID = "toolu_synthetic_1"
H = hashlib.sha256(TOOL_USE_ID.encode()).hexdigest()[:12]
OTHER = hashlib.sha256(b"toolu_synthetic_2").hexdigest()[:12]
NO_VERDICT = "Auto mode could not evaluate this action and is blocking it for safety"


def event(tool, tool_input, tool_use_id=TOOL_USE_ID, reason=NO_VERDICT):
    e = {"hook_event_name": "PermissionDenied", "tool_name": tool, "tool_input": tool_input, "reason": reason}
    if tool_use_id is not None:
        e["tool_use_id"] = tool_use_id
    return e


def agent(t, prompt):
    return event("Agent", {"subagent_type": t, "prompt": prompt})


def send(to, message):
    return event("SendMessage", {"to": to, "summary": "synthetic", "message": message})


def bash(cmd):
    return event("Bash", {"command": cmd})


def make_issue(*comments, number=7):
    return Issue(number=number, open=True, labels=frozenset({"ready"}), body="Lane: default\n",
                 comments=tuple(comments))


class Fake:
    def __init__(self, iss=None, read_error=None, post_error=None):
        self.iss = iss if iss is not None else make_issue()
        self.read_error, self.post_error = read_error, post_error
        self.events, self.reads, self.posts = [], [], []

    def read_issue(self, number):
        self.events.append("read")
        self.reads.append(number)
        if self.read_error:
            raise self.read_error
        return self.iss

    def post_comment(self, number, body):
        self.events.append("post")
        if self.post_error:
            raise self.post_error
        self.posts.append((number, body))

    def lock(self):
        fake = self

        class Lock:
            def __enter__(self):
                fake.events.append("lock")

            def __exit__(self, *exc):
                fake.events.append("unlock")

        return Lock()

    def run(self, e):
        return not_started.handle(e, self.read_issue, self.post_comment, lock=self.lock)


# --- 4a-4c: posts ---------------------------------------------------------------------


def test_4a_agent_pm_launch_posts_not_started():
    fake = Fake(make_issue(launch("pm", call=H)))
    fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == [(7, f"## Launch not started: pm (attempt 1)\nCall: {H}\nReason: {NO_VERDICT}")]
    assert fake.events == ["lock", "read", "post", "unlock"]


def test_4b_send_message_continuation_posts_continued_round():
    fake = Fake(make_issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b",
                           launch("qa"), "## QA: FAIL", cont("engineer", 2, "a1b2c3", call=H)))
    fake.run(send("a1b2c3", "ROLE=engineer ISSUE=7"))
    assert fake.posts == [(7, f"## Launch not started: engineer (continued, round 2)\nCall: {H}\n"
                              f"Reason: {NO_VERDICT}")]


def test_4c_codex_qa_launcher_posts_not_started():
    fake = Fake(make_issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b",
                           launch("qa", 1, call=H), number=12))
    fake.run(event("Bash", {"command": "scripts/qa-codex ROLE=qa ISSUE=12"}, reason="Classifier unavailable"))
    assert fake.reads == [12]
    assert fake.posts == [(12, f"## Launch not started: qa (attempt 1)\nCall: {H}\nReason: Classifier unavailable")]


def test_reason_is_first_line_cut_to_200():
    fake = Fake(make_issue(launch("pm", call=H)))
    fake.run(event("Agent", {"subagent_type": "pm", "prompt": "ROLE=pm ISSUE=7"}, reason="r" * 300 + "\nsecond"))
    assert fake.posts[0][1].endswith("\nReason: " + "r" * 200)


# --- 4d-4f: nothing posted --------------------------------------------------------------


@pytest.mark.parametrize("receipt", [launch("pm", call=OTHER), launch("pm")])
def test_4d_newest_receipt_with_other_or_no_call_posts_nothing(receipt):
    fake = Fake(make_issue(receipt))
    fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == []


def test_4d_older_receipt_matches_but_is_not_the_newest():
    fake = Fake(make_issue(launch("pm", call=H), launch("pm", 2, call=OTHER)))
    fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == []


@pytest.mark.parametrize("after", ["## PM: GROOMED", "## PM: NEEDS OWNER\nq", "## Owner: RESUME"])
def test_4e_result_or_resume_after_receipt_posts_nothing(after):
    fake = Fake(make_issue(launch("pm", call=H), after))
    fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == []


def test_already_marked_posts_nothing():
    fake = Fake(make_issue(launch("pm", call=H), ns_comment("pm", 1, H)))
    fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == []


@pytest.mark.parametrize("e", [
    bash("ls"),
    event("Agent", {"prompt": "ROLE=pm ISSUE=7"}),
    agent("Explore", "ROLE=pm ISSUE=7"),
    bash("gh issue close 12"),
    agent("pm", "please groom issue 7"),
    send("a1b2c3", "no launch line"),
    bash("cp x .claude/settings.json"),
    event("Read", {"file_path": "/x"}),
])
def test_4f_unguarded_close_and_bad_launch_read_nothing(e):
    fake = Fake(make_issue(launch("pm", call=H)))
    fake.run(e)
    assert fake.events == []


# --- 4g: failures ---------------------------------------------------------------------


def test_4g_missing_or_non_string_tool_use_id_reads_nothing():
    for tid in (None, 5, ["x"]):
        fake = Fake(make_issue(launch("pm", call=H)))
        fake.run(event("Agent", {"subagent_type": "pm", "prompt": "ROLE=pm ISSUE=7"}, tool_use_id=tid))
        assert fake.events == []


def test_4g_read_failure_raises_to_main_and_posts_nothing():
    fake = Fake(read_error=RuntimeError("synthetic read failure"))
    with pytest.raises(RuntimeError):
        fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == []


def test_facts_of_another_issue_post_nothing():
    fake = Fake(make_issue(launch("pm", call=H), number=8))
    fake.run(agent("pm", "ROLE=pm ISSUE=7"))
    assert fake.posts == []


# --- main (in-process, fake gh and git on PATH) ------------------------------------------


@pytest.fixture
def env(tmp_path, monkeypatch):
    gitdir = tmp_path / "gitdir"
    gitdir.mkdir()
    issue_file = tmp_path / "issue.json"
    write_issue(issue_file, launch("pm", call=H))
    values = {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_ISSUE": str(issue_file),
              "FAKE_GH_LOG": str(tmp_path / "comments.jsonl"), "FAKE_GH_CALLS": str(tmp_path / "calls.jsonl"),
              "FAKE_GIT_DIR": str(gitdir)}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def write_issue(path, *comments):
    path.write_text(json.dumps({"number": 7, "state": "OPEN", "labels": [{"name": "ready"}],
                                "body": "Lane: default\n", "comments": [{"body": c} for c in comments]}))


def lines(path):
    p = Path(path)
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def run_main(stdin_text):
    stdout = io.StringIO()
    code = not_started.main(stdin=io.StringIO(stdin_text), stdout=stdout)
    return code, stdout.getvalue()


def test_5_main_with_4a_posts_and_prints_nothing(env):
    code, out = run_main(json.dumps(agent("pm", "ROLE=pm ISSUE=7")))
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [
        {"issue": 7, "body": f"## Launch not started: pm (attempt 1)\nCall: {H}\nReason: {NO_VERDICT}"}]


def test_5_main_with_4f_prints_nothing_and_makes_no_gh_call(env):
    code, out = run_main(json.dumps(bash("ls")))
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_CALLS"]) == []


@pytest.mark.parametrize("stdin_text", ["{", "", "[]", "null", '"x"'])
def test_4g_main_with_bad_stdin_prints_nothing(env, stdin_text):
    assert run_main(stdin_text) == (0, "")
    assert lines(env["FAKE_GH_CALLS"]) == []


@pytest.mark.parametrize("fail", ["FAKE_GH_VIEW_FAIL", "FAKE_GH_COMMENT_FAIL", "FAKE_GIT_FAIL"])
def test_4g_main_with_failing_io_prints_nothing(env, monkeypatch, fail):
    monkeypatch.setenv(fail, "1")
    assert run_main(json.dumps(agent("pm", "ROLE=pm ISSUE=7"))) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == []


def test_main_crash_prints_nothing(env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(not_started, "handle", boom)
    assert run_main(json.dumps(agent("pm", "ROLE=pm ISSUE=7"))) == (0, "")


def test_main_never_outputs_retry():
    text = SCRIPT.read_text()
    assert '"retry"' not in text and "'retry'" not in text


# --- subprocess ---------------------------------------------------------------------------


def run_script(stdin_text, env, **extra):
    full = {**os.environ, **env, **extra}
    p = subprocess.run([sys.executable, str(SCRIPT)], input=stdin_text, text=True, capture_output=True,
                       env=full, timeout=60)
    return p.returncode, p.stdout


def test_subprocess_posts_and_prints_nothing(env):
    assert run_script(json.dumps(agent("pm", "ROLE=pm ISSUE=7")), env) == (0, "")
    assert len(lines(env["FAKE_GH_LOG"])) == 1


def test_subprocess_holds_the_guard_lock(env):
    import fcntl
    import guard
    lock_path = Path(env["FAKE_GIT_DIR"]) / guard.LOCK_NAME
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        code, out = run_script(json.dumps(agent("pm", "ROLE=pm ISSUE=7")), env, GUARD_DEADLINE="1")
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_CALLS"]) == []  # the deadline ran out while waiting for the lock


def test_script_has_pep723_header_and_imports_the_guard():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env -S uv run --script\n")
    assert "# /// script" in text and "# dependencies = []" in text
    assert "import guard" in text and "import issue_state" in text
