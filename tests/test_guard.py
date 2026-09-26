"""Tests for .claude/hooks/guard.py.

Classification and `decide` are tested in-process with synthetic events.
The entry point is tested as a subprocess with the fakes in tests/fakes/
first on PATH, so no real `gh` or `git` runs and no test uses the network.
All issue data is synthetic.
"""

import fcntl
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import guard
import issue_state
from guard import Deny, classify, decide, split_command, substitutions
from helpers import cont, facts, issue, launch
from issue_state import Call

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard.py"
FAKES = ROOT / "tests" / "fakes"
FAKE_HEAD = "c" * 40


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def agent(t, prompt, tool="Agent"):
    return {"tool_name": tool, "tool_input": {"subagent_type": t, "prompt": prompt}}


def send(to, message):
    return {"tool_name": "SendMessage", "tool_input": {"to": to, "summary": "synthetic", "message": message}}


def denied(event):
    with pytest.raises(Deny) as e:
        classify(event)
    return str(e.value)


# --- plan step 1 -----------------------------------------------------------------


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


# --- launches ----------------------------------------------------------------------


@pytest.mark.parametrize("tool", ["Agent", "Task"])
@pytest.mark.parametrize("agent_type, role", [("pm", "pm"), ("software-engineer", "engineer"),
                                              ("frontend-engineer", "engineer"), ("qa-engineer", "qa")])
def test_role_launches_are_guarded(tool, agent_type, role):
    call = classify(agent(agent_type, f"Groom it.\nROLE={role} ISSUE=42\nThanks.", tool=tool))
    assert call == Call(role=role, agent=agent_type, issue=42)


@pytest.mark.parametrize("event", [
    agent("Explore", "ROLE=pm ISSUE=1"),
    agent("general-purpose", "no launch line"),
    {"tool_name": "Agent", "tool_input": {"prompt": "no subagent_type", "description": "x"}},
    {"tool_name": "Read", "tool_input": {"file_path": "x"}},
])
def test_other_agents_and_tools_pass(event):
    assert classify(event) is None


@pytest.mark.parametrize("prompt", ["ROLE=pm ISSUE=3\r", "ROLE=pm ISSUE=3   ", "x\r\nROLE=pm ISSUE=3\r\ny",
                                    "ROLE=pm ISSUE=3 \r"])
def test_launch_line_ignores_trailing_cr_and_spaces(prompt):
    assert classify(agent("pm", prompt)).issue == 3


@pytest.mark.parametrize("prompt", [
    "", "no line here", "ROLE=pm ISSUE=3 please", "Launch: ROLE=pm ISSUE=3", " ROLE=pm ISSUE=3",
    "ROLE=pm  ISSUE=3", "ROLE=pm ISSUE=#3", "ROLE=pm ISSUE=", "ROLE=pm ISSUE=٣",
    "ROLE=pm ISSUE=3\nROLE=pm ISSUE=3", "ROLE=pm ISSUE=3\nROLE=qa ISSUE=3", "ROLE=engineer ISSUE=3",
])
def test_bad_launch_lines_are_denied_with_g1(prompt):
    assert denied(agent("pm", prompt)).startswith("G1:")


def test_qa_engineer_needs_role_qa():
    assert denied(agent("qa-engineer", "ROLE=engineer ISSUE=3")).startswith("G1:")


@pytest.mark.parametrize("tool_input", [{"subagent_type": "pm"}, {"subagent_type": "pm", "prompt": None},
                                        {"subagent_type": "pm", "prompt": ["ROLE=pm ISSUE=3"]}])
def test_launch_without_string_prompt_is_denied(tool_input):
    assert denied({"tool_name": "Agent", "tool_input": tool_input}).startswith("G1:")


def test_send_message_is_a_continuation():
    call = classify(send("a1b2c3", "Fix the QA findings.\nROLE=engineer ISSUE=9"))
    assert call == Call(role="engineer", agent="a1b2c3", issue=9, continued=True)


@pytest.mark.parametrize("message", ["no line", "ROLE=pm ISSUE=1\nROLE=pm ISSUE=1", "ROLE=admin ISSUE=1"])
def test_send_message_needs_exactly_one_launch_line(message):
    assert denied(send("worker", message)).startswith("G1:")


@pytest.mark.parametrize("tool_input", [
    {"message": "ROLE=pm ISSUE=1"},
    {"to": None, "message": "ROLE=pm ISSUE=1"},
    {"to": 5, "message": "ROLE=pm ISSUE=1"},
    {"to": "worker"},
    {"to": "worker", "message": {"type": "shutdown_request"}},
    {"recipient": "worker", "content": "ROLE=pm ISSUE=1"},
])
def test_send_message_without_string_target_or_message_is_denied(tool_input):
    assert denied({"tool_name": "SendMessage", "tool_input": tool_input}).startswith("G1:")


@pytest.mark.parametrize("event", [
    [], "x", {"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": "gh issue close 5"},
    {"tool_name": "Bash", "tool_input": {"command": ["gh", "issue", "close", "5"]}},
    {"tool_input": {"command": "ls"}},
])
def test_malformed_events_are_denied(event):
    with pytest.raises(Deny):
        classify(event)


# --- Bash classification -------------------------------------------------------------


@pytest.mark.parametrize("cmd", [
    "gh issue close 5", "gh  issue close 5", "gh issue  close\t5", "/usr/bin/gh issue close 5",
    "gh issue close 5 --reason completed", "gh issue close 5 --reason=completed", "gh issue close 5 -r completed",
    "gh issue close 5 -r 'not planned'", 'gh issue close --reason "not planned" 5', "gh issue close 007",
])
def test_allowed_close_forms(cmd):
    call = classify(bash(cmd))
    assert call.role == "close" and call.agent == "" and call.issue in (5, 7)


@pytest.mark.parametrize("cmd", [
    "scripts/qa-codex ROLE=qa ISSUE=12", "./scripts/qa-codex ROLE=qa ISSUE=12", "qa-codex ROLE=qa ISSUE=12",
    "uv run --script scripts/qa-codex ROLE=qa ISSUE=12", "python3 scripts/qa-codex ROLE=qa ISSUE=12",
    "python scripts/qa-codex ROLE=qa ISSUE=12",
])
def test_allowed_qa_codex_forms(cmd):
    assert classify(bash(cmd)) == Call(role="qa", agent="qa-codex", issue=12)


@pytest.mark.parametrize("cmd", [
    'grep "gh issue close" AGENTS.md', "cat scripts/qa-codex", "ls scripts/", "gh issue view 5 --comments",
    "gh issue list --state open --label ready", "gh issue comment 5 --body-file /tmp/x", "gh pr close 5",
    "echo gh", "git log --oneline -5", "uv run --with pytest pytest", "python3 -m pytest tests/test_qa_codex.py",
    "echo x#y", "git commit -m 'a `gh` b'", "wc -l scripts/qa-codex", "",
    "cat <<'EOF'\ngh issue close 5\nEOF",
    "git commit -m \"$(cat <<'EOF'\nDon't run qa-codex through gh\nEOF\n)\"",
])
def test_unguarded_commands_pass(cmd):
    assert classify(bash(cmd)) is None


@pytest.mark.parametrize("op", [";", "&&", "||", "|", "&", "\n"])
def test_guarded_call_with_any_operator_is_denied(op):
    denied(bash(f"gh issue close 5 {op} ls"))
    denied(bash(f"ls {op} gh issue close 5"))
    denied(bash(f"scripts/qa-codex ROLE=qa ISSUE=5 {op} ls"))


@pytest.mark.parametrize("cmd", [
    "{ gh issue close 5; }", "if true; then gh issue close 5; fi", "! gh issue close 5", "time gh issue close 5",
    "exec gh issue close 5", "command gh issue close 5", "env gh issue close 5", "echo <(gh issue close 5)",
    "echo x#; gh issue close 5", "(gh issue close 5)", "time -p gh issue close 5", "env -i gh issue close 5",
    "while gh issue close 5; do :; done", "> /dev/null gh issue close 5", "2>/dev/null gh issue close 5",
    "exec scripts/qa-codex ROLE=qa ISSUE=5", "ROLE=qa scripts/qa-codex ROLE=qa ISSUE=5",
    "cat > x <(scripts/qa-codex ROLE=qa ISSUE=5)",
])
def test_guarded_call_behind_shell_syntax_or_prefix_is_denied(cmd):
    denied(bash(cmd))


@pytest.mark.parametrize("cmd", [
    'echo "$(gh issue close 5)"', "echo $(gh issue close 5)", "echo `gh issue close 5`",
    'x=$(scripts/qa-codex ROLE=qa ISSUE=5)', 'echo "a $(echo "$(gh issue close 5)") b"',
    "cat <<EOF\n$(gh issue close 5)\nEOF", "cat <<EOF\n`gh issue close 5`\nEOF",
    "echo $(( $(gh issue close 5) + 1 ))",
])
def test_guarded_call_in_substitution_is_denied(cmd):
    denied(bash(cmd))


@pytest.mark.parametrize("cmd", ["gh issue close 'unterminated", 'echo "qa-codex', "echo $(gh issue close 5",
                                 "echo `gh", "echo gh\\"])
def test_unparseable_command_mentioning_guarded_text_is_denied(cmd):
    denied(bash(cmd))


@pytest.mark.parametrize("cmd", ["echo 'unterminated", 'echo "open', "echo $(ls", "echo x\\"])
def test_unparseable_command_without_guarded_text_passes(cmd):
    assert classify(bash(cmd)) is None


@pytest.mark.parametrize("cmd", [
    "gh issue close 5 -R other/repo", "gh issue close 5 --repo other/repo", "gh issue close 5 --repo=o/r",
    "gh issue close 5 --comment done", "gh issue close 5 -c done", "gh issue close -- 5",
    "gh issue close 5 > /dev/null", "gh issue close 5 2>&1", "gh issue close 5 >/dev/null",
    "GH_REPO=x/y gh issue close 5", "gh issue close", "gh issue close 5 6", "gh issue close '#5'",
    "gh issue close https://github.com/o/r/issues/5", "gh issue close 5 --reason done",
    "gh issue close 5 --reason", "gh issue close 5 -r completed -r completed", "gh issue close 5x",
    "gh issue close $N", "gh issue close $(echo 5)", "gh issue close -5",
])
def test_close_with_unclear_arguments_is_denied(cmd):
    denied(bash(cmd))


@pytest.mark.parametrize("cmd", [
    "scripts/qa-codex ISSUE=5 ROLE=qa", "scripts/qa-codex ROLE=qa", "scripts/qa-codex ROLE=qa ISSUE=5 extra",
    "scripts/qa-codex ROLE=qa ISSUE=5 > out.txt", "scripts/qa-codex ROLE=qa ISSUE=5 2>&1", "scripts/qa-codex",
    "scripts/qa-codex ROLE=pm ISSUE=5", "scripts/qa-codex ROLE=qa ISSUE=x", "scripts/qa-codex ROLE=qa ISSUE=#5",
    "uv run --script scripts/qa-codex ROLE=qa", "python3 scripts/qa-codex ISSUE=5 ROLE=qa",
    "scripts/qa-codex --help",
])
def test_qa_codex_with_wrong_arguments_is_denied(cmd):
    denied(bash(cmd))


# --- G8 settings protection --------------------------------------------------------------


@pytest.mark.parametrize("cmd", [
    """echo '{"disableAllHooks": true}' > .claude/settings.local.json""",
    "cd .claude && tee settings.local.json", "cp x .claude/settings.json", "mv x .claude/settings.json",
    "sed -i s/a/b/ .claude/settings.json", """python -c "open('.claude/settings.local.json','w')\"""",
    "cat x > .claude/settings.json", "cat .claude/settings.json | tee .claude/settings.local.json",
    "cp x .claude/Settings.JSON", "cp x .claude/set*", "git checkout -- .claude/settings.json",
    "cp x '.claude/set'*", 'cp x .claude/"sett"ings.json', "cp x .claude/settings?json",
    "cat .claude/settings.json > /tmp/x", "cat $(cp x .claude/settings.json)", "cat 'settings.json",
    "git add .claude/settings.json", "cp x ~/.claude/settings.json", "/bin/cat .claude/settings.json",
    "python3 <<'EOF'\nopen('.claude/settings.local.json', 'w')\nEOF",
])
def test_writes_to_settings_are_denied_with_g8(cmd):
    assert denied(bash(cmd)).startswith("G8:")


@pytest.mark.parametrize("cmd", [
    "cat .claude/settings.json", "jq . .claude/settings.json", "ls .claude", "ls .claude/*",
    "head -n 5 .claude/settings.json", "tail .claude/settings.local.json", "wc -l .claude/settings.json",
    "grep -n disableAllHooks .claude/settings.json", "ls .claude/hooks", "cat docs/process.md",
])
def test_reading_settings_passes(cmd):
    assert classify(bash(cmd)) is None


def test_g8_runs_before_guarded_classification():
    assert denied(bash("gh issue close 5 > .claude/settings.json")).startswith("G8:")


# --- split_command and substitutions ---------------------------------------------------------


def test_split_command():
    assert split_command("gh  issue\tclose 5") == ([["gh", "issue", "close", "5"]], 0)
    assert split_command("a && b | c; d\ne") == ([["a"], ["b"], ["c"], ["d"], ["e"]], 4)
    assert split_command("echo x#; ls") == ([["echo", "x#"], ["ls"]], 1)
    assert split_command("echo 'a b' \"c d\"") == ([["echo", "a b", "c d"]], 0)
    assert split_command("echo x > out 2>&1") == ([["echo", "x", ">", "out", ">&", "1"]], 0)
    assert split_command("echo \\\nx") == ([["echo", "x"]], 0)
    assert split_command("") == ([], 0)
    with pytest.raises(ValueError):
        split_command("echo 'open")


def test_substitutions():
    assert substitutions("$(gh issue close 5)") == ["gh issue close 5"]
    assert substitutions("a`b c`d$(e)") == ["b c", "e"]
    assert substitutions("plain") == []
    with pytest.raises(ValueError):
        substitutions("$(unbalanced")
    with pytest.raises(ValueError):
        substitutions("`unbalanced")


# --- decide (in-process, fake I/O) ------------------------------------------------------------


class FakeIO:
    def __init__(self, iss, head=FAKE_HEAD, clean=True):
        self.facts = facts(iss, head=head, clean=clean)
        self.reads, self.posts = [], []

    def read_facts(self, number):
        self.reads.append(number)
        return self.facts

    def post_comment(self, number, body):
        self.posts.append((number, body))


def test_decide_unguarded_call_reads_nothing():
    fio = FakeIO(issue())
    assert decide(bash("ls"), fio.read_facts, fio.post_comment) is None
    assert decide(agent("Explore", "x"), fio.read_facts, fio.post_comment) is None
    assert fio.reads == [] and fio.posts == []


def test_decide_g8_reads_nothing():
    fio = FakeIO(issue())
    assert decide(bash("cp x .claude/settings.json"), fio.read_facts, fio.post_comment).startswith("G8:")
    assert fio.reads == []


def test_decide_allowed_launch_posts_one_launch_comment():
    fio = FakeIO(issue())
    assert decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment) is None
    assert fio.reads == [7]
    assert fio.posts == [(7, "## Launch: pm (attempt 1)\nAgent: pm")]


def test_decide_qa_codex_posts_agent_qa_codex():
    fio = FakeIO(issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b"))
    assert decide(bash("scripts/qa-codex ROLE=qa ISSUE=7"), fio.read_facts, fio.post_comment) is None
    assert fio.posts == [(7, "## Launch: qa (attempt 1)\nAgent: qa-codex")]


def test_decide_send_message_posts_continued_round():
    fio = FakeIO(issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b",
                       launch("qa"), "## QA: FAIL"))
    assert decide(send("a1b2c3", "ROLE=engineer ISSUE=7"), fio.read_facts, fio.post_comment) is None
    assert fio.posts == [(7, "## Launch: engineer (continued, round 2)\nAgent: a1b2c3")]


def test_decide_close_posts_nothing():
    fio = FakeIO(issue(launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}"))
    assert decide(bash("gh issue close 7"), fio.read_facts, fio.post_comment) is None
    assert fio.reads == [7] and fio.posts == []


def test_decide_failed_check_posts_nothing():
    fio = FakeIO(issue(launch("pm")))
    reason = decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment)
    assert reason.startswith("G1:") and "pending" in reason
    assert fio.posts == []


def test_decide_holds_the_lock_from_read_to_post():
    events = []

    class Lock:
        def __enter__(self):
            events.append("lock")

        def __exit__(self, *exc):
            events.append("unlock")

    def read(n):
        events.append("read")
        return facts(issue())

    decide(agent("pm", "ROLE=pm ISSUE=7"), read, lambda n, b: events.append("post"), lock=Lock)
    assert events == ["lock", "read", "post", "unlock"]


# --- entry point (subprocess with fakes) --------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    """Environment for a guard subprocess: fakes first on PATH, synthetic issue #7."""
    gitdir = tmp_path / "gitdir"
    gitdir.mkdir()
    issue_file = tmp_path / "issue.json"
    write_issue(issue_file)
    return {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_ISSUE": str(issue_file),
            "FAKE_GH_LOG": str(tmp_path / "comments.jsonl"), "FAKE_GH_CALLS": str(tmp_path / "calls.jsonl"),
            "FAKE_GIT_DIR": str(gitdir)}


def write_issue(path, *comments, labels=("ready",), body="Lane: default\n"):
    path.write_text(json.dumps({"number": 7, "state": "OPEN", "labels": [{"name": n} for n in labels],
                                "body": body, "comments": [{"body": c} for c in comments]}))


def lines(path):
    p = Path(path)
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def run_guard(event, env, stdin=None, **extra):
    full = {**os.environ, **env, **extra}
    data = stdin if stdin is not None else json.dumps(event)
    p = subprocess.run([sys.executable, str(GUARD)], input=data, text=True, capture_output=True,
                       env=full, timeout=60)
    return p.returncode, p.stdout


def deny_reason(out):
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse" and hso["permissionDecision"] == "deny"
    return hso["permissionDecisionReason"]


def test_allowed_launch_posts_one_comment_and_prints_nothing(env):
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 1)\nAgent: pm"}]


def test_allowed_close_prints_nothing_and_posts_nothing(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}")
    code, out = run_guard(bash("gh issue close 7 --reason completed"), env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == []


def test_allowed_send_message_posts_continued_comment(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("pm"), "## PM: GROOMED", launch("engineer"),
                "## Engineer: DONE\nCommits: a..b", launch("qa"), "## QA: FAIL")
    code, out = run_guard(send("a1b2c3", "ROLE=engineer ISSUE=7"), env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: engineer (continued, round 2)\n"
                                                             "Agent: a1b2c3"}]


@pytest.mark.parametrize("event", [agent("Explore", "ROLE=pm ISSUE=7"), bash("ls -la"), bash("cat .claude/x"),
                                   {"tool_name": "Agent", "tool_input": {"prompt": "ROLE=pm ISSUE=7"}}])
def test_unguarded_call_makes_no_gh_call(env, event):
    code, out = run_guard(event, env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_CALLS"]) == []


def test_g8_makes_no_gh_call(env):
    code, out = run_guard(bash("cp x .claude/settings.json"), env)
    assert code == 0 and deny_reason(out).startswith("G8:")
    assert lines(env["FAKE_GH_CALLS"]) == []


def test_check_deny_names_the_check(env):
    code, out = run_guard(agent("software-engineer", "ROLE=engineer ISSUE=7"), env)
    assert code == 0 and deny_reason(out).startswith("G3:")
    assert lines(env["FAKE_GH_LOG"]) == []


@pytest.mark.parametrize("extra", [{"FAKE_GH_FAIL": "1"}, {"FAKE_GIT_FAIL": "1"}, {"FAKE_GIT_DIRTY": "1"},
                                   {"FAKE_GH_COMMENT_FAIL": "1"}])
def test_failures_deny(env, extra):
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, **extra)
    assert code == 0 and deny_reason(out)


def test_failing_gh_on_close_denies(env):
    code, out = run_guard(bash("gh issue close 5"), env, FAKE_GH_FAIL="1")
    assert code == 0 and "gh" in deny_reason(out)


def test_failing_comment_post_is_named(env):
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_COMMENT_FAIL="1")
    assert "gh issue comment" in deny_reason(out)


def test_gh_not_on_path_denies(env, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(FAKES / "git")
    (bin_dir / "python3").symlink_to(sys.executable)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, PATH=str(bin_dir))
    reason = deny_reason(out)
    assert code == 0 and "gh" in reason and "not found" in reason


@pytest.mark.parametrize("stdin", ["{", "", "[]", '"x"', "5", "null"])
def test_broken_or_non_object_stdin_denies(env, stdin):
    code, out = run_guard(None, env, stdin=stdin)
    assert code == 0 and deny_reason(out)


def test_multi_line_stderr_is_cut_to_its_first_line(env):
    token = "SYNTHETIC_TOKEN_0123456789"
    first = "e" * 300
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_FAIL="1",
                          FAKE_GH_STDERR=f"{first}\n{token}\n")
    reason = deny_reason(out)
    assert token not in out
    assert "e" * 200 in reason and "e" * 201 not in reason


def test_deadline_denies_when_gh_hangs(env):
    start = time.monotonic()
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, GUARD_DEADLINE="2", FAKE_GH_SLEEP="30")
    assert time.monotonic() - start < 10
    assert code == 0 and "deadline" in deny_reason(out)
    assert lines(env["FAKE_GH_LOG"]) == []


def test_deadline_denies_when_lock_is_held(env):
    lock_path = Path(env["FAKE_GIT_DIR"]) / guard.LOCK_NAME
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        start = time.monotonic()
        code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, GUARD_DEADLINE="2")
        elapsed = time.monotonic() - start
    assert elapsed < 10
    assert code == 0 and "deadline" in deny_reason(out)
    assert lines(env["FAKE_GH_CALLS"]) == []


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_invalid_deadline_denies(env, value):
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, GUARD_DEADLINE=value)
    assert code == 0 and deny_reason(out)


def test_lock_serializes_two_launches_on_the_same_issue(env):
    full = {**os.environ, **env, "FAKE_GH_SLEEP": "1"}
    data = json.dumps(agent("pm", "ROLE=pm ISSUE=7"))
    procs = [subprocess.Popen([sys.executable, str(GUARD)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, env=full) for _ in range(2)]
    for p in procs:  # both guards get their input before either is awaited, so they overlap
        p.stdin.write(data)
        p.stdin.close()
    outs = [p.stdout.read() for p in procs]
    for p in procs:
        p.wait(timeout=60)
        p.stdout.close()
    assert [p.returncode for p in procs] == [0, 0]
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 1)\nAgent: pm"}]
    assert sorted(outs, key=len)[0] == ""
    reason = deny_reason(sorted(outs, key=len)[1])
    assert reason.startswith("G1:") and "pending" in reason


def test_lock_file_is_in_the_git_dir(env):
    run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert (Path(env["FAKE_GIT_DIR"]) / guard.LOCK_NAME).exists()


def test_internal_error_denies_in_process(env, monkeypatch):
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic crash\nsecond line")

    monkeypatch.setattr(issue_state, "check", boom)
    stdout = io.StringIO()
    assert guard.main(stdin=io.StringIO(json.dumps(agent("pm", "ROLE=pm ISSUE=7"))), stdout=stdout) == 0
    reason = deny_reason(stdout.getvalue())
    assert "RuntimeError" in reason and "second line" not in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_main_allowed_in_process_prints_nothing(env, monkeypatch):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    stdout = io.StringIO()
    assert guard.main(stdin=io.StringIO(json.dumps(agent("pm", "ROLE=pm ISSUE=7"))), stdout=stdout) == 0
    assert stdout.getvalue() == ""


def test_guard_never_outputs_allow():
    assert '"allow"' not in GUARD.read_text()
    assert "'allow'" not in GUARD.read_text()


def test_guard_script_has_pep723_header_and_stdlib_only():
    text = GUARD.read_text()
    assert text.startswith("#!/usr/bin/env -S uv run --script\n")
    assert "# /// script" in text and "# dependencies = []" in text
