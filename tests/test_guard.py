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
from guard import Deny, classify, decide
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


# --- launches ----------------------------------------------------------------------


def test_launch_line_must_match_agent():
    with pytest.raises(Deny):
        classify(agent("pm", "ROLE=engineer ISSUE=3"))
    with pytest.raises(Deny):
        classify(agent("pm", "ROLE=pm ISSUE=3\nROLE=pm ISSUE=4"))
    assert classify(agent("Explore", "anything")) is None


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


# --- Bash classification: the trigger rule ------------------------------------------------
#
# A command that mentions `gh` and `close`, or `qa-codex`, is triggered. A triggered command
# is a guarded call only in one of two exact forms; any other triggered command is denied.


@pytest.mark.parametrize("cmd", ["gh issue clo\\\nse 5", "g\\\nh issue close 5", "scripts/qa-\\\ncodex ROLE=qa ISSUE=5"])
def test_backslash_newline_copy_is_triggered_and_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("cmd", ["gh issue list --state closed", "grep -n close notes.md", "GH issue close 5",
                                 "gh issue view 5 --json closed", "echo ghost close", "echo gh closer"])
def test_text_without_both_words_is_not_triggered(cmd):
    assert classify(bash(cmd)) is None


def test_trigger_word_boundaries_are_ascii():
    """With re.ASCII, a non-ASCII letter is no word character, so `\\bgh\\b` matches in `éghé`."""
    assert denied(bash("echo éghé close")).startswith("G1:")


ALLOWED = [
    ("gh issue close 12", "close"), ("gh issue close 12 --reason completed", "close"),
    ("gh issue close 12 --reason=completed", "close"), ("gh issue close 12 -r 'not planned'", "close"),
    ('gh issue close 12 --reason "not planned"', "close"), ("gh issue close 12  \n", "close"),
    ("gh issue close 12\t", "close"), ("scripts/qa-codex ROLE=qa ISSUE=12", "qa"),
    ("scripts/qa-codex ROLE=qa ISSUE=12 \n", "qa"),
]


@pytest.mark.parametrize("cmd, kind", ALLOWED)
def test_allowed_forms_are_the_guarded_call(cmd, kind):
    expected = Call(role="close", agent="", issue=12) if kind == "close" else Call(role="qa", agent="qa-codex", issue=12)
    assert classify(bash(cmd)) == expected


def test_qa_codex_in_the_background_is_the_guarded_call():
    event = {"tool_name": "Bash", "tool_input": {"command": "scripts/qa-codex ROLE=qa ISSUE=12",
                                                  "run_in_background": True}}
    assert classify(event) == Call(role="qa", agent="qa-codex", issue=12)


# The cases of the deny criterion, word for word, and the accepted false denies.
DENIED = [
    "scripts/qa-codex ROLE=qa ISSUE=5\r", " gh issue close 5", "gh  issue close 5", "gh\tissue close 5",
    "/usr/bin/gh issue close 5", "command gh issue close 5", "scripts/qa-codex ROLE=qa ISSUE=5 &",
    "gh issue close 5 > /dev/null", "gh issue close 5 && ls", "gh issue close 5\n\n", "gh issue close 0",
    "gh issue close 05", "gh issue close #5", "gh issue close 5 --reason other", "gh issue close 5 -R o/r",
    "gh issue close 5 --comment x", "scripts/qa-codex ROLE=qa ISSUE=0", "scripts/qa-codex ISSUE=5 ROLE=qa",
    "./scripts/qa-codex ROLE=qa ISSUE=5", "uv run scripts/qa-codex ROLE=qa ISSUE=5", "cat scripts/qa-codex",
    "git add scripts/qa-codex", 'git commit -m "Fix gh close handling"', "gh issue view 5 | grep close",
    "gh pr close 5", "git commit -m \"$(cat <<'EOF'\nAdd qa-codex launcher\nEOF\n)\"",
    # more forms that are not exact
    "gh issue close 12\r", "gh issue close 12\r\n", "gh issue close", "gh issue close 5 6", "gh issue close 5x",
    "gh issue close -- 5", "gh issue close 5 --reason", "gh issue close 5 --reason 'not planned' --reason completed",
    "gh issue close --reason completed 5", "gh issue close 5 --reason 'Not planned'", "gh issue close 5 -r not planned",
    "gh issue close ٥", "GH_REPO=x/y gh issue close 5", "gh issue close $N", "gh issue close $(echo 5)",
    "gh issue \\\nclose 5", "gh issue close 5 # done", "scripts/qa-codex ROLE=qa", "scripts/qa-codex",
    "scripts/qa-codex ROLE=qa ISSUE=5 extra", "scripts/qa-codex ROLE=qa ISSUE=05", "qa-codex ROLE=qa ISSUE=5",
    "python3 scripts/qa-codex ROLE=qa ISSUE=5", "/abs/scripts/qa-codex ROLE=qa ISSUE=5",
    'grep "gh issue close" AGENTS.md', "wc -l scripts/qa-codex", "echo gh issue close 5",
    "cat <<'EOF'\ngh issue close 5\nEOF", "x=(a)#; scripts/qa-codex ROLE=qa ISSUE=5",
    "{fd}>/dev/null scripts/qa-codex ROLE=qa ISSUE=5", "python3 >/dev/null scripts/qa-codex ROLE=qa ISSUE=5",
]


@pytest.mark.parametrize("cmd", DENIED)
def test_other_triggered_commands_are_denied_with_g1(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("op", [";", "&&", "||", "|", "&", "\n"])
def test_guarded_call_with_any_operator_is_denied(op):
    assert denied(bash(f"gh issue close 5 {op} ls")).startswith("G1:")
    assert denied(bash(f"ls {op} gh issue close 5")).startswith("G1:")
    assert denied(bash(f"scripts/qa-codex ROLE=qa ISSUE=5 {op} ls")).startswith("G1:")


@pytest.mark.parametrize("cmd", [
    "{ gh issue close 5; }", "if true; then gh issue close 5; fi", "! gh issue close 5", "time gh issue close 5",
    "exec gh issue close 5", "env gh issue close 5", "echo <(gh issue close 5)", "echo x#; gh issue close 5",
    "(gh issue close 5)", 'echo "$(gh issue close 5)"', "echo `gh issue close 5`",
    "echo `scripts/qa-codex ROLE=qa ISSUE=5`",
])
def test_guarded_call_behind_shell_syntax_or_in_a_substitution_is_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


DENY_TEXTS = ["gh issue close <n>", "scripts/qa-codex ROLE=qa ISSUE=<n>", "git commit -F", "--body-file", "Read",
              "Grep", "git add scripts/", "run_in_background"]


@pytest.mark.parametrize("cmd", ["cat scripts/qa-codex", "gh  issue close 5", "scripts/qa-codex ROLE=qa ISSUE=5 &"])
def test_deny_message_names_the_forms_and_the_ways_around(cmd):
    reason = denied(bash(cmd))
    assert reason.startswith("G1:")
    for text in DENY_TEXTS:
        assert text in reason


def test_trigger_rule_uses_no_tokenizer(monkeypatch):
    """With G8 switched off and the tokenizer broken, the trigger rule still decides."""
    def no_lexer(*args, **kwargs):
        raise AssertionError("the tokenizer must not be used for guarded calls")

    monkeypatch.setattr(guard, "g8", lambda command: None)
    monkeypatch.setattr(guard, "_lex", no_lexer)
    assert classify(bash("gh issue close 5")) == Call(role="close", agent="", issue=5)
    assert denied(bash("gh  issue close 5")).startswith("G1:")
    assert classify(bash("ls")) is None


@pytest.mark.parametrize("cmd", [
    "ls", "gh issue view 5 --comments", "gh issue comment 5 --body-file /tmp/x.md", "gh issue list --state closed",
    "", "ls scripts/", "which gh", "echo gh issue list", "git log --oneline -5", "uv run --with pytest pytest",
    "git commit -m 'Close the loop'", "git add scripts/", "echo x#y", "(( i++ ))", "echo $((1<<2))",
    "for (( i=0; i<3; i++ )); do echo $i; done", "exec {fd}>/dev/null", "echo $'\\c'", "function f { echo hi; }",
    "echo 'unterminated", 'echo "open', "echo $(ls", "echo x\\", "echo `gh", "echo gh\\", "a[0]=x", "[[ a == b ]]",
])
def test_command_without_trigger_is_not_guarded(cmd):
    assert classify(bash(cmd)) is None


def test_long_or_deeply_nested_commands_are_no_crash():
    assert classify(bash("echo " + "${" * 3000)) is None
    assert denied(bash("gh issue close 5 " + "$(" * 3000)).startswith("G1:")
    assert classify(bash("cat <<'EOF'\n" + "x ${\n" * 3000 + "EOF")) is None


def test_every_function_and_constant_is_reached_from_main():
    """Dead code of the old classifier is removed. A top-level function, class or constant must be
    reached from main through the names it uses; a method must be used as an attribute somewhere."""
    import ast
    tree = ast.parse(GUARD.read_text())
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        defs[name.id] = node
    uses = {name: {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} for name, node in defs.items()}
    reached, todo = set(), ["main"]
    while todo:
        name = todo.pop()
        if name in reached or name not in defs:
            continue
        reached.add(name)
        todo.extend(uses[name])
    assert sorted(set(defs) - reached) == []
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for method in (m for m in cls.body if isinstance(m, ast.FunctionDef)):
            assert method.name.startswith("__") or method.name in attributes, f"{cls.name}.{method.name} is unused"


def test_old_classifier_is_gone():
    for name in ("split_command", "substitutions", "_find_guarded", "_classify_text", "_line_check", "_has_guarded",
                 "WRAPPERS", "PREFIX_WORDS", "RUNNERS"):
        assert not hasattr(guard, name), name


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


def test_g8_runs_before_the_trigger_rule():
    assert denied(bash("cp scripts/qa-codex .claude/settings.json")).startswith("G8:")


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


def test_decide_launch_with_tool_use_id_posts_call_line():
    import hashlib
    fio = FakeIO(issue())
    event = {**agent("pm", "ROLE=pm ISSUE=7"), "tool_use_id": "toolu_synthetic_1"}
    assert decide(event, fio.read_facts, fio.post_comment) is None
    expected = hashlib.sha256("toolu_synthetic_1".encode()).hexdigest()[:12]
    assert fio.posts == [(7, f"## Launch: pm (attempt 1)\nAgent: pm\nCall: {expected}")]


@pytest.mark.parametrize("tool_use_id", [5, None, ["toolu_synthetic_1"], {"id": "x"}])
def test_decide_launch_with_non_string_tool_use_id_has_no_call_line(tool_use_id):
    fio = FakeIO(issue())
    event = {**agent("pm", "ROLE=pm ISSUE=7"), "tool_use_id": tool_use_id}
    assert decide(event, fio.read_facts, fio.post_comment) is None
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


def test_allowed_launch_with_tool_use_id_posts_call_line(env):
    import hashlib
    code, out = run_guard({**agent("pm", "ROLE=pm ISSUE=7"), "tool_use_id": "toolu_synthetic_1"}, env)
    assert (code, out) == (0, "")
    h = hashlib.sha256(b"toolu_synthetic_1").hexdigest()[:12]
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": f"## Launch: pm (attempt 1)\nAgent: pm\nCall: {h}"}]


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


def test_null_comments_deny_with_guard_error_and_post_nothing(env):
    data = json.loads(Path(env["FAKE_GH_ISSUE"]).read_text())
    data["comments"] = None
    Path(env["FAKE_GH_ISSUE"]).write_text(json.dumps(data))
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert code == 0 and deny_reason(out).startswith("guard error:")
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


@pytest.mark.parametrize("cmd", ["cat scripts/qa-codex", "gh  issue close 5", "/usr/bin/gh issue close 5",
                                 "scripts/qa-codex ROLE=qa ISSUE=5 &", "gh issue close 5 && ls",
                                 "x=(a)#; gh issue close 5", "gh {fd}>/dev/null issue close 5"])
def test_triggered_command_without_form_denies_before_any_gh_call(env, cmd):
    code, out = run_guard(bash(cmd), env, FAKE_GH_FAIL="1")
    assert code == 0 and deny_reason(out).startswith("G1:")
    assert lines(env["FAKE_GH_CALLS"]) == []


@pytest.mark.parametrize("cmd", ["ls", "gh issue view 5 --comments", "gh issue comment 5 --body-file /tmp/x.md",
                                 "gh issue list --state closed"])
def test_command_without_trigger_prints_nothing_and_makes_no_gh_call(env, cmd):
    code, out = run_guard(bash(cmd), env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_CALLS"]) == []


def test_allowed_qa_codex_in_the_background_posts_its_launch_comment(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("pm"), "## PM: GROOMED", launch("engineer"),
                "## Engineer: DONE\nCommits: a..b")
    event = {"tool_name": "Bash", "tool_input": {"command": "scripts/qa-codex ROLE=qa ISSUE=7",
                                                  "run_in_background": True}}
    code, out = run_guard(event, env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: qa (attempt 1)\nAgent: qa-codex"}]


# Bypasses of the old tokenizer (QA rounds 1 to 3). For every command here, bash runs
# `gh issue close` (see test_bash_runs_the_hidden_close). The trigger rule denies them.
HIDDEN_CLOSE = [
    "ls # don't forget\ngh issue close 5 # it's done", "ls # it's\ngh issue close 5 #'",
    "echo $'it\\'s'\ngh issue close 5 #'", "echo ${x:- #} ; gh issue close 5",
    "gh 2>/dev/null issue close 5", "gh issue >/dev/null close 5", "gh <<<x issue close 5",
    "echo $(case x in x) gh issue close 5;; esac)", "echo `echo \\`gh issue close 5\\``",
    "coproc gh issue close 5", "timeout 5 gh issue close 5", "env -u X gh issue close 5",
    "gh issue -R o/r close 5", "gh {fd}>/dev/null issue close 5", "{fd}>/dev/null gh issue close 5",
    "(( 1<<2 ))\ngh issue close 5", "echo $[1<<2]\ngh issue close 5", "echo $'\\c'; gh issue close 5 #'",
    "function f { gh issue close 5; }\nf", "echo $(time -p case x in x) gh issue close 5;; esac)",
    "echo $(coproc case x in x) gh issue close 5;; esac)", "a=(x; echo ')\ngh issue close 5 #'",
    "$(true)gh issue close 5", '"$x"gh issue close 5', "ionice gh issue close 5",
    "find . -maxdepth 0 -exec gh issue close 5 \\;", "x=(a)#; gh issue close 5", "x+=(a)#; gh issue close 5",
    "declare -a x=(a)#; gh issue close 5", "echo $(echo case x in x)#; gh issue close 5\n)",
    "echo <(echo case x in x)#; gh issue close 5\n)",
]


@pytest.mark.parametrize("cmd", HIDDEN_CLOSE)
def test_hidden_close_is_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.skipif(not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists(), reason="no bash")
@pytest.mark.parametrize("cmd", HIDDEN_CLOSE)
def test_bash_runs_the_hidden_close(cmd, tmp_path):
    """Parity check: the cases above are real. bash, with the fake gh first on PATH, runs `gh issue close`."""
    calls = tmp_path / "calls.jsonl"
    # Even if a real gh ran (it must not), it has no login: a fresh HOME and gh config, no token.
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN")}
    env |= {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_CALLS": str(calls),
            "HOME": str(tmp_path), "GH_CONFIG_DIR": str(tmp_path / "gh"), "XDG_CONFIG_HOME": str(tmp_path)}
    subprocess.run(["bash", "-c", cmd], cwd=tmp_path, env=env, capture_output=True, timeout=30)
    assert any(c[:1] == ["issue"] and "close" in c[1:] for c in lines(calls))


# --- PM: WAITING, the blocker read (issue #56) ------------------------------------------------

WAITING_ON_3 = (launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: BLOCKED\nwhy",
                launch("pm", 2), "## PM: WAITING\nWaiting on: #3")


def test_decide_reads_blocker_only_after_waiting():
    reads = []

    def read_blocker(n):
        reads.append(n)
        return False

    fio = FakeIO(issue(*WAITING_ON_3))
    assert decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment,
                  read_blocker=read_blocker) is None
    assert reads == [3]
    assert fio.posts == [(7, "## Launch: pm (attempt 3)\nAgent: pm")]
    reads.clear()
    fio = FakeIO(issue(*WAITING_ON_3[:4]))
    assert decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment,
                  read_blocker=read_blocker) is None
    assert reads == []


def test_decide_open_blocker_denies_and_posts_nothing():
    fio = FakeIO(issue(*WAITING_ON_3))
    reason = decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment, read_blocker=lambda n: True)
    assert reason.startswith("G2:") and "#3" in reason and "open" in reason
    assert fio.posts == []


def test_decide_reads_blocker_inside_the_lock_before_the_post():
    events = []

    class Lock:
        def __enter__(self):
            events.append("lock")

        def __exit__(self, *exc):
            events.append("unlock")

    decide(agent("pm", "ROLE=pm ISSUE=7"), lambda n: facts(issue(*WAITING_ON_3)),
           lambda n, b: events.append("post"), lock=Lock,
           read_blocker=lambda n: events.append("blocker") or False)
    assert events == ["lock", "blocker", "post", "unlock"]


def test_guard_views_the_closed_blocker_and_allows(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_ON_3)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_STATES='{"3": "CLOSED"}')
    assert (code, out) == (0, "")
    calls = lines(env["FAKE_GH_CALLS"])
    assert ["issue", "view", "3", "--json", "state"] in calls
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 3)\nAgent: pm"}]


def test_guard_denies_open_blocker(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_ON_3)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_STATES='{"3": "OPEN"}')
    reason = deny_reason(out)
    assert reason.startswith("G2:") and "#3" in reason and "open" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_makes_no_second_view_after_blocked(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_ON_3[:4])
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_STATES='{"3": "CLOSED"}')
    assert (code, out) == (0, "")
    views = [c for c in lines(env["FAKE_GH_CALLS"]) if c[:2] == ["issue", "view"]]
    assert len(views) == 1 and views[0][2] == "7"


@pytest.mark.parametrize("states", ["{}", '{"3": "MERGED"}', '{"3": 5}'])
def test_guard_failing_blocker_read_denies_with_guard_error(env, states):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_ON_3)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_STATES=states)
    assert code == 0 and deny_reason(out).startswith("guard error")
    assert lines(env["FAKE_GH_LOG"]) == []
