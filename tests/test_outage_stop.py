"""Tests for .claude/hooks/outage_stop.py (SubagentStop hook, issue #52).

`handle` is tested in-process with synthetic events, a synthetic transcript
file, an evidence folder in tmp_path and fakes for reading the issue and
posting. `main` is tested in-process and as a subprocess with the fakes in
tests/fakes/ first on PATH, so no real `gh` or `git` runs. All ids and texts
are synthetic.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import outage_stop
from helpers import cont, launch, not_started, stopped
from issue_state import Issue

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "hooks" / "outage_stop.py"
FAKES = ROOT / "tests" / "fakes"

X = "0123456789ab"
AGENT_ID = "synthetic1"
REASON = "Auto mode could not evaluate this action and is blocking it for safety"


def make_issue(*comments, number=39):
    return Issue(number=number, open=True, labels=frozenset({"ready"}), body="Lane: default\n",
                 comments=tuple(comments))


def write_transcript(path, *entries):
    path.write_text("".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in entries))
    return path


def user(content):
    return {"type": "user", "message": {"role": "user", "content": content}}


class Env:
    """An evidence folder, a transcript and fakes for reading the issue and posting."""

    def __init__(self, tmp_path, iss=None, read_error=None, post_error=None):
        self.folder = tmp_path / "gitdir" / "agent-graph-kit-outage"
        self.transcript = tmp_path / "agent-synthetic1.jsonl"
        self.iss = iss if iss is not None else make_issue(launch("pm", call=X))
        self.read_error, self.post_error = read_error, post_error
        self.events, self.reads, self.posts = [], [], []

    def evidence(self, text=REASON, agent_id=AGENT_ID):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / agent_id).write_text(text)
        return self

    def launch_line(self, content="ROLE=pm ISSUE=39\nYou are the PM.", *before):
        write_transcript(self.transcript, *before, user(content))
        return self

    def event(self, agent_type="pm", agent_id=AGENT_ID, transcript=None):
        return {"hook_event_name": "SubagentStop", "agent_id": agent_id, "agent_type": agent_type,
                "agent_transcript_path": str(transcript or self.transcript), "stop_hook_active": False,
                "last_assistant_message": ""}

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
        env = self

        class Lock:
            def __enter__(self):
                env.events.append("lock")

            def __exit__(self, *exc):
                env.events.append("unlock")

        return Lock()

    def run(self, e):
        return outage_stop.handle(e, self.read_issue, self.post_comment, lock=self.lock,
                                  evidence_dir=lambda: self.folder)

    def evidence_gone(self):
        return not (self.folder / AGENT_ID).exists()


# --- 4a, 4b: posts -----------------------------------------------------------------------


def test_4a_39_case_posts_stop_comment(tmp_path):
    env = Env(tmp_path).evidence().launch_line()
    env.run(env.event())
    assert env.reads == [39]
    assert env.posts == [(39, f"## Launch stopped by outage: pm (attempt 1)\nCall: {X}\nReason: {REASON}")]
    assert env.evidence_gone()


def test_reason_is_the_evidence_content_verbatim(tmp_path):
    content = ("Classifier unavailable" + " " * 200)[:200]
    env = Env(tmp_path).evidence(content).launch_line()
    env.run(env.event())
    assert env.posts == [(39, f"## Launch stopped by outage: pm (attempt 1)\nCall: {X}\nReason: {content}")]


def test_reason_end_to_end_from_the_permission_denied_hook(tmp_path):
    env = Env(tmp_path).launch_line()
    env.folder.parent.mkdir()  # the git dir exists; the evidence folder does not yet
    long = "Classifier unavailable" + " " * 200 + "detail"
    denied = {"hook_event_name": "PermissionDenied", "tool_name": "Bash", "tool_use_id": "toolu_synthetic",
              "tool_input": {"command": "gh issue view 7 --comments"}, "reason": long, "agent_id": AGENT_ID}
    outage_stop.not_started.handle(denied, env.read_issue, env.post_comment, lock=env.lock, evidence_dir=lambda: env.folder)
    assert (env.folder / AGENT_ID).read_text() == long[:200]
    env.run(env.event())
    assert env.posts == [(39, f"## Launch stopped by outage: pm (attempt 1)\nCall: {X}\nReason: {long[:200]}")]
    assert env.evidence_gone()


def test_4b_continuation_posts_continued_round(tmp_path):
    iss = make_issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b",
                     launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1", call=X), number=12)
    env = Env(tmp_path, iss).evidence("Classifier unavailable").launch_line("ROLE=engineer ISSUE=12")
    env.run(env.event("software-engineer"))
    assert env.posts == [(12, f"## Launch stopped by outage: engineer (continued, round 2)\nCall: {X}\n"
                              "Reason: Classifier unavailable")]


def test_frontend_engineer_and_qa_engineer_roles(tmp_path):
    env = Env(tmp_path, make_issue(launch("engineer", agent="frontend-engineer", call=X))).evidence().launch_line(
        "ROLE=engineer ISSUE=39")
    env.run(env.event("frontend-engineer"))
    assert env.posts[0][1].startswith("## Launch stopped by outage: engineer (attempt 1)\n")
    env = Env(tmp_path, make_issue(launch("qa", agent="qa-engineer", call=X))).evidence().launch_line(
        "ROLE=qa ISSUE=39")
    env.run(env.event("qa-engineer"))
    assert env.posts[0][1].startswith("## Launch stopped by outage: qa (attempt 1)\n")


def test_content_as_list_of_text_blocks_and_other_lines_first(tmp_path):
    env = Env(tmp_path).evidence()
    write_transcript(env.transcript, {"type": "summary", "summary": "synthetic"},
                     user([{"type": "text", "text": "Work on this."}, {"type": "text", "text": "ROLE=pm ISSUE=39"}]),
                     user("ROLE=engineer ISSUE=40"))
    env.run(env.event())
    assert len(env.posts) == 1


def test_comment_has_no_agent_id_or_transcript_text(tmp_path):
    env = Env(tmp_path).evidence().launch_line("ROLE=pm ISSUE=39\nsecret-synthetic-prompt-text")
    env.run(env.event())
    body = env.posts[0][1]
    assert AGENT_ID not in body and "secret-synthetic" not in body and "toolu_" not in body


# --- 4c-4i: nothing posted ----------------------------------------------------------------


def test_4c_no_evidence_reads_nothing(tmp_path, monkeypatch):
    env = Env(tmp_path).launch_line()

    def no_transcript(path):
        raise AssertionError("the transcript must not be read without evidence")

    monkeypatch.setattr(outage_stop, "read_launch", no_transcript)
    env.run(env.event())
    assert env.events == []


@pytest.mark.parametrize("after", ["## PM: GROOMED", "## Owner: RESUME"])
def test_4d_result_or_resume_after_receipt_posts_nothing(tmp_path, after):
    env = Env(tmp_path, make_issue(launch("pm", call=X), after)).evidence().launch_line()
    env.run(env.event())
    assert env.posts == []
    assert env.evidence_gone()


@pytest.mark.parametrize("agent_type", ["Explore", "general-purpose", None, 5, ["pm"]])
def test_4e_other_agent_types_read_no_issue(tmp_path, agent_type):
    env = Env(tmp_path).evidence().launch_line()
    env.run(env.event(agent_type))
    assert env.events == []
    assert env.evidence_gone()


def test_4f_agent_type_and_launch_line_role_differ(tmp_path):
    env = Env(tmp_path).evidence().launch_line("ROLE=pm ISSUE=39")
    env.run(env.event("software-engineer"))
    assert env.events == []


@pytest.mark.parametrize("lines", [
    None,  # transcript missing
    ("not json",),
    ({"type": "assistant", "message": {"content": "ROLE=pm ISSUE=39"}},),  # no user line
    (user("please groom issue 39"),),  # no launch line
    (user("ROLE=pm ISSUE=39\nROLE=pm ISSUE=40"),),  # two different launch lines
    (user(5),),
    ({"type": "user"},),
    ("[1, 2]", user("ROLE=pm ISSUE=39")),  # a line that is not an object comes first
])
def test_4g_bad_transcript_posts_nothing(tmp_path, lines):
    env = Env(tmp_path).evidence()
    if lines is not None:
        write_transcript(env.transcript, *lines)
    env.run(env.event())
    assert env.events == []
    assert env.evidence_gone()


def test_4g_transcript_path_not_a_string(tmp_path):
    env = Env(tmp_path).evidence().launch_line()
    e = env.event()
    e["agent_transcript_path"] = 5
    env.run(e)
    assert env.events == []


@pytest.mark.parametrize("marker", [not_started("pm", 1, X), stopped("pm", 1, X)])
def test_4h_already_voided_posts_nothing(tmp_path, marker):
    env = Env(tmp_path, make_issue(launch("pm", call=X), marker)).evidence().launch_line()
    env.run(env.event())
    assert env.posts == []


@pytest.mark.parametrize("receipt", [launch("pm"), launch("engineer", call=X)])
def test_4i_no_call_line_or_other_role_posts_nothing(tmp_path, receipt):
    env = Env(tmp_path, make_issue(receipt)).evidence().launch_line()
    env.run(env.event())
    assert env.posts == []


def test_issue_of_another_number_posts_nothing(tmp_path):
    env = Env(tmp_path, make_issue(launch("pm", call=X), number=40)).evidence().launch_line()
    env.run(env.event())
    assert env.posts == []


@pytest.mark.parametrize("agent_id", ["../x", "a/b", "", "a" * 65, None, 5])
def test_bad_agent_id_reads_nothing(tmp_path, agent_id):
    env = Env(tmp_path).evidence().launch_line()
    env.run(env.event(agent_id=agent_id))
    assert env.events == []
    assert not env.evidence_gone()  # the evidence of another agent stays


def test_non_dict_event_does_nothing(tmp_path):
    env = Env(tmp_path).evidence()
    for e in (None, [], "x"):
        env.run(e)
    assert env.events == [] and not env.evidence_gone()


# --- 4j: failures -------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["read_error", "post_error"])
def test_4j_io_failure_propagates_to_main_and_posts_nothing(tmp_path, kind):
    env = Env(tmp_path, **{kind: RuntimeError("synthetic failure")}).evidence().launch_line()
    with pytest.raises(RuntimeError):
        env.run(env.event())
    assert env.posts == []
    assert env.evidence_gone()


# --- 5: lock order ------------------------------------------------------------------------


def test_5_lock_order(tmp_path):
    env = Env(tmp_path).evidence().launch_line()
    env.run(env.event())
    assert env.events == ["lock", "read", "post", "unlock"]


# --- main (in-process, fake gh and git on PATH) ------------------------------------------


@pytest.fixture
def io_env(tmp_path, monkeypatch):
    gitdir = tmp_path / "gitdir"
    (gitdir / "agent-graph-kit-outage").mkdir(parents=True)
    (gitdir / "agent-graph-kit-outage" / AGENT_ID).write_text(REASON)
    issue_file = tmp_path / "issue.json"
    issue_file.write_text(json.dumps({"number": 39, "state": "OPEN", "labels": [{"name": "ready"}],
                                      "body": "Lane: default\n",
                                      "comments": [{"body": launch("pm", call=X), "authorAssociation": "OWNER"}]}))
    transcript = write_transcript(tmp_path / "agent.jsonl", user("ROLE=pm ISSUE=39\nYou are the PM."))
    values = {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_ISSUE": str(issue_file),
              "FAKE_GH_LOG": str(tmp_path / "comments.jsonl"), "FAKE_GH_CALLS": str(tmp_path / "calls.jsonl"),
              "FAKE_GIT_DIR": str(gitdir)}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    values["EVIDENCE"] = str(gitdir / "agent-graph-kit-outage" / AGENT_ID)
    values["EVENT"] = json.dumps({"hook_event_name": "SubagentStop", "agent_id": AGENT_ID, "agent_type": "pm",
                                  "agent_transcript_path": str(transcript), "stop_hook_active": False,
                                  "last_assistant_message": ""})
    return values


def lines(path):
    p = Path(path)
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def run_main(stdin_text):
    stdout = io.StringIO()
    code = outage_stop.main(stdin=io.StringIO(stdin_text), stdout=stdout)
    return code, stdout.getvalue()


def test_5_main_with_4a_posts_and_prints_nothing(io_env):
    assert run_main(io_env["EVENT"]) == (0, "")
    assert lines(io_env["FAKE_GH_LOG"]) == [
        {"issue": 39, "body": f"## Launch stopped by outage: pm (attempt 1)\nCall: {X}\nReason: {REASON}"}]
    assert not Path(io_env["EVIDENCE"]).exists()


@pytest.mark.parametrize("stdin_text", ["{", "", "[]", "null", '"x"'])
def test_5_main_with_bad_stdin_prints_nothing(io_env, stdin_text):
    assert run_main(stdin_text) == (0, "")
    assert lines(io_env["FAKE_GH_CALLS"]) == []


@pytest.mark.parametrize("fail", ["FAKE_GH_VIEW_FAIL", "FAKE_GH_COMMENT_FAIL", "FAKE_GIT_FAIL"])
def test_4j_main_with_failing_io_prints_nothing(io_env, monkeypatch, fail):
    monkeypatch.setenv(fail, "1")
    assert run_main(io_env["EVENT"]) == (0, "")
    assert lines(io_env["FAKE_GH_LOG"]) == []


def test_main_without_evidence_makes_no_gh_call(io_env):
    os.remove(io_env["EVIDENCE"])
    assert run_main(io_env["EVENT"]) == (0, "")
    assert lines(io_env["FAKE_GH_CALLS"]) == []


def test_main_crash_prints_nothing(io_env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(outage_stop, "handle", boom)
    assert run_main(io_env["EVENT"]) == (0, "")


def test_script_never_outputs_decision_or_block():
    text = SCRIPT.read_text()
    for word in ('"decision"', "'decision'", '"block"', "'block'"):
        assert word not in text


# --- subprocess ---------------------------------------------------------------------------


def run_script(stdin_text, env, **extra):
    full = {**os.environ, **{k: v for k, v in env.items() if k.isupper()}, **extra}
    p = subprocess.run([sys.executable, str(SCRIPT)], input=stdin_text, text=True, capture_output=True,
                       env=full, timeout=60)
    return p.returncode, p.stdout


def test_subprocess_posts_and_prints_nothing(io_env):
    assert run_script(io_env["EVENT"], io_env) == (0, "")
    assert len(lines(io_env["FAKE_GH_LOG"])) == 1


def test_subprocess_holds_the_guard_lock(io_env):
    import fcntl
    import guard
    lock_path = Path(io_env["FAKE_GIT_DIR"]) / guard.LOCK_NAME
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        assert run_script(io_env["EVENT"], io_env, GUARD_DEADLINE="1") == (0, "")
    assert all(call[:2] != ["issue", "view"] for call in lines(io_env["FAKE_GH_CALLS"]))
    assert lines(io_env["FAKE_GH_LOG"]) == []  # the deadline ran out while waiting for the lock


def test_script_has_pep723_header_and_imports_the_guard():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env -S uv run --script\n")
    assert "# /// script" in text and "# dependencies = []" in text
    assert "import guard" in text and "import issue_state" in text
