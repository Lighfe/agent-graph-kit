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
from issue_state import Blocker, Call

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


# --- Bash classification: real runs (issue #107) ------------------------------------------
#
# The guard reads the command with the tokenizer and looks at every simple command, also inside
# substitutions. A close run (gh … issue … close) or a launcher run (…/qa-codex) is a guarded call
# only in one of two exact forms; any other real run is denied. Text that only mentions the words
# passes. A runner (bash -c, eval, xargs …) counts as a run when the old word rule triggers.


@pytest.mark.parametrize("cmd", ["gh issue clo\\\nse 5", "g\\\nh issue close 5", "scripts/qa-\\\ncodex ROLE=qa ISSUE=5"])
def test_backslash_newline_in_a_word_is_a_real_run_and_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("cmd", ["gh issue list --state closed", "grep -n close notes.md", "GH issue close 5",
                                 "gh issue view 5 --json closed", "echo ghost close", "echo gh closer"])
def test_text_without_both_words_is_not_triggered(cmd):
    assert classify(bash(cmd)) is None


def test_trigger_word_boundaries_are_ascii():
    """With re.ASCII, a non-ASCII letter is no word character, so `\\bgh\\b` matches in `éghé`.
    The old word rule still decides the runner rule and unreadable commands."""
    assert denied(bash("bash -c 'echo éghé close'")).startswith("G1:")
    assert denied(bash("echo éghé close '")).startswith("G1:")
    assert classify(bash("echo éghé close")) is None


# Cases of issue #107 that pass G1: the text only mentions the words.
MENTIONS_PASS = [
    "cat scripts/qa-codex", "wc -l scripts/qa-codex", "git add scripts/qa-codex",
    'git commit -m "Fix gh close handling"',
    "git commit -m \"$(cat <<'EOF'\nAdd qa-codex launcher\nEOF\n)\"",
    "echo gh issue close 5", 'grep "gh issue close 5" AGENTS.md', "gh issue view 5 | grep close",
    "gh pr close 5", 'gh issue create --title "Fix the close check" --body-file /tmp/x.md',
    # former DENIED cases that now pass
    'grep "gh issue close" AGENTS.md', "cat <<'EOF'\ngh issue close 5\nEOF",
]

HEREDOC_BODY = ("cat > /tmp/x/body.md <<'EOF'\n## PM: GROOMED\n\nThe orchestrator runs gh issue close 5.\n"
                "QA runs scripts/qa-codex ROLE=qa ISSUE=5 in the background.\n"
                "Run `gh issue close 5` only after QA PASS.\nEOF")
HEREDOC_BODY_UNQUOTED = ("cat > /tmp/x/body.md <<EOF\n## PM: GROOMED\n\nThe orchestrator runs gh issue close 5.\n"
                         "EOF")


@pytest.mark.parametrize("cmd", [*MENTIONS_PASS, HEREDOC_BODY, HEREDOC_BODY_UNQUOTED])
def test_text_that_only_mentions_the_words_passes(cmd):
    assert classify(bash(cmd)) is None


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


# Real runs that are not the exact form. The cases of the deny criterion of issue #107 come first.
DENIED = [
    " gh issue close 5", "gh  issue close 5", "gh\tissue close 5", "/usr/bin/gh issue close 5",
    "command gh issue close 5", "env gh issue close 5", "time gh issue close 5", "GH_REPO=x/y gh issue close 5",
    "gh issue close 5 > /dev/null", "gh issue close 5 --reason other", "gh issue close $N",
    "gh issue close 5 # done", "gh issue \\\nclose 5",
    "./scripts/qa-codex ROLE=qa ISSUE=5", "uv run scripts/qa-codex ROLE=qa ISSUE=5",
    "python3 scripts/qa-codex ROLE=qa ISSUE=5", "scripts/qa-codex ROLE=qa ISSUE=5 &",
    "scripts/qa-codex ROLE=qa ISSUE=05", "{fd}>/dev/null scripts/qa-codex ROLE=qa ISSUE=5",
    # more forms that are not exact (kept from before issue #107)
    "scripts/qa-codex ROLE=qa ISSUE=5\r", "gh issue close 5 && ls", "gh issue close 5\n\n", "gh issue close 0",
    "gh issue close 05", "gh issue close #5", "gh issue close 5 -R o/r",
    "scripts/qa-codex ROLE=qa ISSUE=0", "scripts/qa-codex ISSUE=5 ROLE=qa",
    "gh issue close 12\r", "gh issue close 12\r\n", "gh issue close", "gh issue close 5 6", "gh issue close 5x",
    "gh issue close -- 5", "gh issue close 5 --reason", "gh issue close 5 --reason 'not planned' --reason completed",
    "gh issue close --reason completed 5", "gh issue close 5 --reason 'Not planned'", "gh issue close 5 -r not planned",
    "gh issue close ٥", "gh issue close $(echo 5)", "scripts/qa-codex ROLE=qa", "scripts/qa-codex",
    "scripts/qa-codex ROLE=qa ISSUE=5 extra", "qa-codex ROLE=qa ISSUE=5", "/abs/scripts/qa-codex ROLE=qa ISSUE=5",
    "x=(a)#; scripts/qa-codex ROLE=qa ISSUE=5", "python3 >/dev/null scripts/qa-codex ROLE=qa ISSUE=5",
]


@pytest.mark.parametrize("cmd", DENIED)
def test_real_runs_not_in_the_exact_form_are_denied_with_g1(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("op", [";", "&&", "||", "|", "&", "\n"])
def test_guarded_call_with_any_operator_is_denied(op):
    assert denied(bash(f"gh issue close 5 {op} ls")).startswith("G1:")
    assert denied(bash(f"ls {op} gh issue close 5")).startswith("G1:")
    assert denied(bash(f"scripts/qa-codex ROLE=qa ISSUE=5 {op} ls")).startswith("G1:")
    assert denied(bash(f"ls {op} scripts/qa-codex ROLE=qa ISSUE=5")).startswith("G1:")


@pytest.mark.parametrize("cmd", [
    "{ gh issue close 5; }", "if true; then gh issue close 5; fi", "! gh issue close 5", "time gh issue close 5",
    "exec gh issue close 5", "env gh issue close 5", "echo <(gh issue close 5)", "echo x#; gh issue close 5",
    "(gh issue close 5)", 'echo "$(gh issue close 5)"', "echo `gh issue close 5`", 'echo "x `gh issue close 5`"',
    "echo `scripts/qa-codex ROLE=qa ISSUE=5`", "f() { gh issue close 5; }", "cat >(gh issue close 5)",
    "cat > /tmp/x/body.md <<EOF\nRun `gh issue close 5` now.\nEOF",
    "cat > /tmp/x/body.md <<EOF\nRun $(gh issue close 5) now.\nEOF",
])
def test_guarded_call_behind_shell_syntax_or_in_a_substitution_is_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("cmd", ["gh issue cl''ose 5", "gh issue c\\lose 5", "gh issue $'close' 5",
                                 "gh 'issue' \"close\" 5", "scripts/qa-cod''ex ROLE=qa ISSUE=5"])
def test_words_are_compared_after_quote_removal(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("cmd", [
    "bash -c 'gh issue close 5'", "echo 'gh issue close 5' | bash", "bash <<'EOF'\ngh issue close 5\nEOF",
    "eval 'gh issue close 5'", "echo 5 | xargs gh issue close", "sh -c 'scripts/qa-codex ROLE=qa ISSUE=5'",
    "/bin/bash -c 'gh issue close 5'", "python3 - <<'EOF'\nimport subprocess\nsubprocess.run('gh issue close 5')\nEOF",
])
def test_runner_rule_denies(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("cmd", [
    "python3 - <<'EOF'\nfrom pathlib import Path\np = Path('docs/x.md')\n"
    "p.write_text(p.read_text().replace('gh issue close', 'the close'))\nEOF",
    "bash -c 'echo gh issue close 5'", "echo gh close | xargs echo",
])
def test_accepted_false_denies_of_the_runner_rule(cmd):
    assert denied(bash(cmd)).startswith("G1:")


# No close run, launcher run or runner: a comment, an array assignment or an expansion decides nothing.
NO_RUN_PASS = [
    "ls # gh close later", "echo gh close # harmless", "a=(x); echo gh close", "x=(gh close); echo $x",
    "a=(x\n# gh issue close 5\ny); echo ok", "declare -a x=(gh close)", "echo $x gh close",
    "echo $(true) gh issue close 5",
]


@pytest.mark.parametrize("cmd", NO_RUN_PASS)
def test_command_without_a_run_passes(cmd):
    assert classify(bash(cmd)) is None


# Known limit (docs/specs/agent-graph-kit.md#bash-rule-of-g1): a command word built with an expansion is not the CLI name. bash runs these
# (see test_bash_runs_the_known_limit), and G1 lets them pass, like `$GH issue close 5`.
KNOWN_LIMIT_PASS = ["$(true)gh issue close 5", '"$x"gh issue close 5', "$GH issue close 5"]


@pytest.mark.parametrize("cmd", KNOWN_LIMIT_PASS)
def test_known_limit_command_word_with_an_expansion_passes(cmd):
    assert classify(bash(cmd)) is None


READ_AS_BASH = [
    "x=(a $(gh issue close 5))", "x=(a\n`gh issue close 5`)",
    "x=(a) gh issue close 5", "echo $(time -p case x in x) gh issue close 5;; esac)",
    "echo $(time -p -- case x in x) gh issue close 5;; esac)", "echo $(coproc x case x in x) gh issue close 5;; esac)",
    "echo $(! case x in x) gh issue close 5;; esac)", "echo $(echo case x in x)#; gh issue close 5\n)",
]


@pytest.mark.parametrize("cmd", READ_AS_BASH)
def test_array_assignment_and_case_are_read_as_bash_reads_them(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.parametrize("cmd", ["a=(x; gh issue close 5)", "a=(x | y) gh close"])
def test_array_assignment_with_an_operator_falls_back_to_the_word_rule(cmd):
    assert denied(bash(cmd)).startswith("G1:")


def test_runner_list_holds_the_required_commands():
    required = {"command", "builtin", "exec", "env", "time", "coproc", "nohup", "sudo", "doas", "nice", "timeout",
                "xargs", "setsid", "stdbuf", "watch", "find", "parallel", "flock", "eval", "source", ".", "function",
                "bash", "sh", "zsh", "dash", "ksh", "fish", "python", "python3", "uv", "uvx", "perl", "ruby", "node",
                "npx", "bunx", "make", "script", "ssh"}
    assert required <= guard.RUNNER_COMMANDS


@pytest.mark.parametrize("cmd", ["bash -c 'echo hi'", "uv run --with pytest pytest", "python3 -c 'print(1)'",
                                 "xargs ls", "find . -name '*.py'"])
def test_runner_without_the_words_passes(cmd):
    assert classify(bash(cmd)) is None


@pytest.mark.parametrize("cmd", ["gh issue close 5 '", "gh issue close 5 $(", "scripts/qa-codex ROLE=qa ISSUE=5 `"])
def test_unreadable_command_with_the_words_is_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


def test_unreadable_command_falls_back_to_the_word_rule(monkeypatch):
    """When the tokenizer fails, the old word rule decides, as before issue #107."""
    def broken(*args, **kwargs):
        raise ValueError("synthetic")

    monkeypatch.setattr(guard, "g8", lambda command: None)
    monkeypatch.setattr(guard, "_lex", broken)
    assert denied(bash("echo gh issue close 5")).startswith("G1:")
    assert denied(bash("cat scripts/qa-codex")).startswith("G1:")
    assert classify(bash("gh issue close 5")) == Call(role="close", agent="", issue=5)
    assert classify(bash("ls")) is None


DENY_TEXTS = ["gh issue close <n>", "scripts/qa-codex ROLE=qa ISSUE=<n>", "whole command", "operators",
              "redirections", "wrappers", "substitutions", "run_in_background", "only mentions", "<<'EOF'"]
NOT_IN_DENY = ["git commit -F", "--body-file", "Read", "Grep", "git add scripts/"]


@pytest.mark.parametrize("cmd", ["gh  issue close 5", "scripts/qa-codex ROLE=qa ISSUE=5 &", "bash -c 'gh issue close 5'"])
def test_deny_message_names_the_forms_and_says_that_mentions_pass(cmd):
    reason = denied(bash(cmd))
    assert reason.startswith("G1:") and reason == guard.TRIGGER_DENY
    for text in DENY_TEXTS:
        assert text in reason
    for text in NOT_IN_DENY:
        assert text not in reason


@pytest.mark.parametrize("cmd", [
    "ls", "gh issue view 5 --comments", "gh issue list --state closed",
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


# Issue #86: read-only parts in a list, and here-document bodies that only mention the files.
SETFILE = ".claude/settings.local.json"
HOOKSGLOB = ".claude/hooks/*.py"
NAMING_BODY = f"Do not edit {SETFILE} or {HOOKSGLOB} by hand.\nThe hooks in {HOOKSGLOB} stay.\n"


@pytest.mark.parametrize("cmd", [
    f"gh issue view 86 --jq .title; grep -n G8 {HOOKSGLOB}",
    f"grep -n g8 {HOOKSGLOB} | head; sed -n 1,5p docs/specs/agent-graph-kit.md",
    f"grep -n x {HOOKSGLOB} && wc -l docs/process.md",
    f"ls {HOOKSGLOB} | wc -l",
    f"cat {SETFILE} | jq .",
    f"cat > /tmp/pm-86-attempt1.md <<'EOF'\n## PM: GROOMED\n\n{NAMING_BODY}EOF",
    f"cat > /tmp/pm-86-attempt1.md <<EOF\n## PM: GROOMED\n\n{NAMING_BODY}EOF",
    f"cat > /tmp/pm-86-attempt1.md <<'EOF'\n{NAMING_BODY}EOF\n",
    f"cat > /tmp/pm-86-attempt1.md <<-EOF\n\t{NAMING_BODY}\tEOF",
])
def test_read_only_parts_and_here_document_bodies_pass_g8(cmd):
    assert guard.g8(cmd) is None
    assert classify(bash(cmd)) is None


@pytest.mark.parametrize("cmd", [
    f'ls {SETFILE}; cp x "$_"',
    f"ls {SETFILE}; cp x ${{_}}",
    f"ls {SETFILE}; cp x ${{_%.json}}.json",
    f'ls {SETFILE} | while read f; do cp x "$f"; done',
    f"ls {SETFILE} | xargs cp x",
    f"ls {SETFILE} | tee /tmp/x",
    f"ls {SETFILE} |& tee /tmp/x",
    f"ls {SETFILE} > /tmp/x",
    f"cat {SETFILE}; cp x {SETFILE}",
    "cd .claude && cp x settings.local.json",
    f"cat <<'EOF' | sh\ncp x {SETFILE}\nEOF",
    f"bash <<'EOF'\ncp x {SETFILE}\nEOF",
    f"cat > {SETFILE} <<'EOF'\n{{}}\nEOF",
    f"cat <<EOF > /tmp/x\n$(cp x {SETFILE})\nEOF",
    f"ls {HOOKSGLOB}; cat $(echo {SETFILE})",
    # data passed on from a mention through a group or a subshell into a pipe
    f"{{ ls {SETFILE}; }} | tee /tmp/x",
    f"(ls {SETFILE}; true) | tee /tmp/x",
    f"if true; then ls {SETFILE}; fi | tee /tmp/x",
    # a runner anywhere, also inside a substitution
    f"ls {SETFILE}; xargs cp x < /tmp/list",
    f"ls {SETFILE}; echo $(bash -c true)",
    f"ls {SETFILE}; f=$(ls {SETFILE}); cp x $f",
    f"/bin/ls {SETFILE}; true",
    # a here-document body that a pipe or a runner reads
    f"cat <<'EOF' | tee /tmp/x\n{SETFILE}\nEOF",
    f"python3 - <<'EOF'\nopen('{SETFILE}', 'w')\nEOF",
])
def test_g8_still_denies_what_may_write(cmd):
    assert denied(bash(cmd)).startswith("G8:")


def test_g8_message_names_the_way_around():
    reason = denied(bash(f"cat {SETFILE}; cp x {SETFILE}"))
    assert "split the command so the parts that name the protected files are read-only commands" in reason
    assert "use the Read or Grep tool" in reason


def test_cannot_be_read_with_a_mention_is_denied_with_g8():
    assert denied(bash(f"ls {HOOKSGLOB}; echo 'unterminated")).startswith("G8:")
    assert classify(bash("ls docs; echo ok")) is None


# --- comment commands (the comment-form check removed in issue #90) -------------------------------------------
# A comment command is not checked for its form any more. It is not a guarded call,
# so it passes unless G8 or the G1 trigger rule denies it. Nothing is read or posted.


def comment_event(cmd, cwd=None):
    event = bash(cmd)
    if cwd is not None:
        event["cwd"] = str(cwd)
    return event


def body_file(tmp_path, content, name="body.md"):
    path = tmp_path / name
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    return path


def decide_nothing_read(event):
    """decide() with read_facts and post_comment that must not be called."""
    def never(*args):
        raise AssertionError("read_facts or post_comment was called")
    return decide(event, never, never, read_blockers=never)


@pytest.mark.parametrize("content", [
    "## PM: GROOMED\n\nRewrote the issue body.\n",
    "## PM: NEEDS OWNER\n\nThe owner posts `## Owner: RESUME`.\n",
    "## Engineer: DONE\nThe owner posts `## Owner: RESUME` outside Claude Code.",
])
def test_body_file_comment_passes_and_reads_nothing(tmp_path, content):
    path = body_file(tmp_path, content)
    assert decide_nothing_read(comment_event(f"gh issue comment 5 --body-file {path}")) is None
    assert decide_nothing_read(comment_event(f"gh issue comment 5 --body-file {path}\n")) is None


@pytest.mark.parametrize("content", [
    "## Owner: RESUME\nGo on.\n",
    "## PM: GROOMED\n\n## Owner: RESUME\n",
    "   ## Owner: RESUME\n",
    "﻿## Owner: RESUME\n",
])
def test_owner_marker_in_the_body_file_passes(tmp_path, content):
    """Issue #78: the guard does not read the body, so an ## Owner: line in it passes."""
    path = body_file(tmp_path, content)
    assert decide_nothing_read(comment_event(f"gh issue comment 5 --body-file {path}")) is None


def test_comment_command_does_not_read_or_resolve_the_body_file(tmp_path):
    """Issue #78: a body file that is missing, a folder or not UTF-8 passes; gh itself fails later."""
    missing = tmp_path / "missing.md"
    bad = body_file(tmp_path, b"## PM: GROOMED\n\xff\xfe\n", name="bad.md")
    for path in (missing, tmp_path, bad):
        assert decide_nothing_read(comment_event(f"gh issue comment 5 --body-file {path}")) is None
    relative = "gh issue comment 5 --body-file body.md"
    assert decide_nothing_read(comment_event(relative)) is None
    for cwd in (5, None, ["x"]):
        event = bash(relative)
        event["cwd"] = cwd
        assert decide_nothing_read(event) is None


# The 21 commands that the comment-form check denied for their form before issue #90.
FORMER_G9_DENIES = [
    'gh issue comment 5 --body "x"', "gh issue comment 5 -b x", "gh issue comment 5 -F /tmp/b.md",
    "gh issue comment 5 --body-file=/tmp/b.md", "echo x | gh issue comment 5 --body-file -",
    "gh issue comment 5 --body-file -", "gh issue comment 5 --body-file - <<'EOF'\n## PM: GROOMED\nEOF",
    "gh issue comment 5 --edit-last --body-file /tmp/b.md", 'gh issue comment 5 --body-file "$TMPDIR/b.md"',
    "gh issue comment 5 --body-file '/tmp/b.md'", "gh pr comment 5 --body-file /tmp/b.md",
    "gh issue comment 5 --body-file /tmp/b.md && echo ok", "gh issue comment 5 --body-file /tmp/b.md; echo ok",
    "gh issue comment 5 --body-file /tmp/b.md | cat", "gh issue com\\\nment 5 --body-file /tmp/b.md",
    "gh issue comment 5 --body-file ~/b.md", "gh issue comment 5 --body-file /tmp/*.md",
    "gh issue comment 05 --body-file /tmp/b.md", "gh  issue comment 5 --body-file /tmp/b.md",
    'git commit -m "gh issue comment fix"', "gh issue close 5 --comment x",
]


def test_former_g9_list_is_complete():
    assert len(FORMER_G9_DENIES) == 21
    assert [c for c in FORMER_G9_DENIES if "close" in c] == ["gh issue close 5 --comment x"]


@pytest.mark.parametrize("cmd", [c for c in FORMER_G9_DENIES if "close" not in c])
def test_former_g9_denies_now_pass(cmd):
    assert decide_nothing_read(comment_event(cmd)) is None


def test_former_g9_deny_with_close_is_denied_by_g1():
    assert decide_nothing_read(comment_event("gh issue close 5 --comment x")).startswith("G1:")


def test_other_comment_form_passes_when_the_file_exists(tmp_path):
    path = body_file(tmp_path, "## PM: GROOMED\n")
    assert decide_nothing_read(comment_event(f"gh issue comment 5 --body-file={path}")) is None


@pytest.mark.parametrize("cmd", [
    # (a) a here-document that writes a body file naming the posting command
    "cat > /tmp/b.md <<'EOF'\n## PM: GROOMED\n\nPost it with gh issue comment 5 --body-file /tmp/b.md.\nEOF",
    # (b) a Python here-document that edits a Markdown file and names the posting command
    "python3 - <<'EOF'\nfrom pathlib import Path\np = Path('docs/process.md')\n"
    "p.write_text(p.read_text().replace('old', 'Post with gh issue comment <n> --body-file <path>.'))\nEOF",
    # (c) a commit message with both former trigger words
    'git commit -m "Explain how agents post with gh issue comment"',
])
def test_writing_text_that_names_the_comment_command_passes(cmd):
    assert "close" not in cmd and "qa-codex" not in cmd and "settings" not in cmd
    assert decide_nothing_read(comment_event(cmd)) is None


@pytest.mark.parametrize("cmd", ["gh issue view 5 --comments", "gh issue view 5 --json comments",
                                 "gh issue view 5 --json body,comments", "git commit -m comment",
                                 "echo gh comments"])
def test_reading_comments_passes(cmd):
    assert decide_nothing_read(comment_event(cmd)) is None


def test_comment_body_file_in_settings_is_denied_with_g8():
    assert denied(bash("gh issue comment 5 --body-file .claude/settings.local.json")).startswith("G8:")


def test_comment_body_file_in_a_close_folder_passes(tmp_path):
    """Before issue #107, G1 denied this for the words gh and close. It runs no close, so it passes."""
    folder = tmp_path / "close"
    folder.mkdir()
    path = body_file(folder, "## PM: GROOMED\n")
    assert decide_nothing_read(comment_event(f"gh issue comment 5 --body-file {path}")) is None


def test_comment_command_makes_no_gh_or_git_call(tmp_path, env):
    path = body_file(tmp_path, "## PM: GROOMED\n")
    code, out = run_guard(bash(f"gh issue comment 5 --body-file {path}"), env, FAKE_GH_FAIL="1")
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_CALLS"]) == [] and lines(env["FAKE_GH_LOG"]) == []


def test_owner_marker_comment_through_main_is_allowed(tmp_path, env, monkeypatch):
    """Issue #78: no deny output, exit code 0 and no gh call."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    path = body_file(tmp_path, "## Owner: RESUME\n")
    stdout = io.StringIO()
    event = bash(f"gh issue comment 7 --body-file {path}")
    assert guard.main(stdin=io.StringIO(json.dumps(event)), stdout=stdout) == 0
    assert stdout.getvalue() == ""
    assert lines(env["FAKE_GH_CALLS"]) == [] and lines(env["FAKE_GH_LOG"]) == []


# --- decide (in-process, fake I/O) ------------------------------------------------------------


class FakeIO:
    def __init__(self, iss, head=FAKE_HEAD, clean=True, blockers=(), open_blockers=0,
                 sub_issues=(issue_state.SubIssue("octo/kit", 3, "closed"),), sub_issue_total=1):
        self.facts = facts(iss, head=head, clean=clean, blockers=None, open_blockers=None)
        self.blockers = (blockers, open_blockers)
        self.sub_issues = (sub_issues, sub_issue_total)
        self.reads, self.posts, self.blocker_reads, self.sub_reads = [], [], [], []

    def read_facts(self, number):
        self.reads.append(number)
        return self.facts

    def read_blockers(self, number):
        self.blocker_reads.append(number)
        return self.blockers

    def read_sub_issues(self, number):
        self.sub_reads.append(number)
        return self.sub_issues

    def decide(self, event):
        return decide(event, self.read_facts, self.post_comment, read_blockers=self.read_blockers,
                      read_sub_issues=self.read_sub_issues)

    def post_comment(self, number, body):
        self.posts.append((number, body))


def test_decide_unguarded_call_reads_nothing():
    fio = FakeIO(issue())
    assert fio.decide(bash("ls")) is None
    assert fio.decide(agent("Explore", "x")) is None
    assert fio.reads == [] and fio.posts == []


def test_decide_g8_reads_nothing():
    fio = FakeIO(issue())
    assert fio.decide(bash("cp x .claude/settings.json")).startswith("G8:")
    assert fio.reads == []


def test_decide_allowed_launch_posts_one_launch_comment():
    fio = FakeIO(issue())
    assert fio.decide(agent("pm", "ROLE=pm ISSUE=7")) is None
    assert fio.reads == [7]
    assert fio.posts == [(7, "## Launch: pm (attempt 1)\nAgent: pm")]


def test_decide_launch_with_tool_use_id_posts_call_line():
    import hashlib
    fio = FakeIO(issue())
    event = {**agent("pm", "ROLE=pm ISSUE=7"), "tool_use_id": "toolu_synthetic_1"}
    assert fio.decide(event) is None
    expected = hashlib.sha256("toolu_synthetic_1".encode()).hexdigest()[:12]
    assert fio.posts == [(7, f"## Launch: pm (attempt 1)\nAgent: pm\nCall: {expected}")]


@pytest.mark.parametrize("tool_use_id", [5, None, ["toolu_synthetic_1"], {"id": "x"}])
def test_decide_launch_with_non_string_tool_use_id_has_no_call_line(tool_use_id):
    fio = FakeIO(issue())
    event = {**agent("pm", "ROLE=pm ISSUE=7"), "tool_use_id": tool_use_id}
    assert fio.decide(event) is None
    assert fio.posts == [(7, "## Launch: pm (attempt 1)\nAgent: pm")]


def test_decide_qa_codex_posts_agent_qa_codex():
    fio = FakeIO(issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b"))
    assert fio.decide(bash("scripts/qa-codex ROLE=qa ISSUE=7")) is None
    assert fio.posts == [(7, "## Launch: qa (attempt 1)\nAgent: qa-codex")]


def test_decide_send_message_posts_continued_round():
    fio = FakeIO(issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b",
                       launch("qa"), "## QA: FAIL"))
    assert fio.decide(send("a1b2c3", "ROLE=engineer ISSUE=7")) is None
    assert fio.posts == [(7, "## Launch: engineer (continued, round 2)\nAgent: a1b2c3")]


def test_decide_close_posts_nothing():
    fio = FakeIO(issue(launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}"))
    assert fio.decide(bash("gh issue close 7")) is None
    assert fio.reads == [7] and fio.posts == []


def test_decide_failed_check_posts_nothing():
    fio = FakeIO(issue(launch("pm"), launch("pm", 2)))  # two misses in a row (issue #132)
    reason = fio.decide(agent("pm", "ROLE=pm ISSUE=7"))
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

    decide(agent("pm", "ROLE=pm ISSUE=7"), read, lambda n, b: events.append("post"), lock=Lock,
           read_blockers=lambda n: events.append("blockers") or ((), 0))
    assert events == ["lock", "read", "blockers", "post", "unlock"]


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
                                "body": body, "comments": [{"body": c, "authorAssociation": "OWNER"} for c in comments]}))


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
    # One PM miss first: the first guard allows the one relaunch, the second guard then sees two
    # misses in a row and denies (issue #132). Without the lock both would see one miss.
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("pm"))
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
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 2)\nAgent: pm"}]
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


@pytest.mark.parametrize("cmd", ["bash -c 'gh issue close 5'", "gh  issue close 5", "/usr/bin/gh issue close 5",
                                 "scripts/qa-codex ROLE=qa ISSUE=5 &", "gh issue close 5 && ls",
                                 "x=(a)#; gh issue close 5", "gh {fd}>/dev/null issue close 5"])
def test_triggered_command_without_form_denies_before_any_gh_call(env, cmd):
    code, out = run_guard(bash(cmd), env, FAKE_GH_FAIL="1", FAKE_GIT_FAIL="1")
    assert code == 0 and deny_reason(out).startswith("G1:")
    assert lines(env["FAKE_GH_CALLS"]) == []


@pytest.mark.parametrize("cmd", ["ls", "gh issue view 5 --comments", "gh issue list --state closed",
                                 "cat scripts/qa-codex", HEREDOC_BODY])
def test_command_without_trigger_prints_nothing_and_makes_no_gh_call(env, cmd):
    code, out = run_guard(bash(cmd), env, FAKE_GH_FAIL="1", FAKE_GIT_FAIL="1")
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
    "ionice gh issue close 5",
    "find . -maxdepth 0 -exec gh issue close 5 \\;", "x=(a)#; gh issue close 5", "x+=(a)#; gh issue close 5",
    "declare -a x=(a)#; gh issue close 5", "echo $(echo case x in x)#; gh issue close 5\n)",
    "echo <(echo case x in x)#; gh issue close 5\n)",
]


@pytest.mark.parametrize("cmd", HIDDEN_CLOSE)
def test_hidden_close_is_denied(cmd):
    assert denied(bash(cmd)).startswith("G1:")


@pytest.mark.skipif(not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists(), reason="no bash")
@pytest.mark.parametrize("cmd", [*HIDDEN_CLOSE, *READ_AS_BASH, *KNOWN_LIMIT_PASS[:2]])
def test_bash_runs_the_hidden_close(cmd, tmp_path):
    """Parity check: the cases above are real. bash, with the fake gh first on PATH, runs `gh issue close`."""
    calls = tmp_path / "calls.jsonl"
    # Even if a real gh ran (it must not), it has no login: a fresh HOME and gh config, no token.
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN")}
    env |= {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_CALLS": str(calls),
            "HOME": str(tmp_path), "GH_CONFIG_DIR": str(tmp_path / "gh"), "XDG_CONFIG_HOME": str(tmp_path)}
    subprocess.run(["bash", "-c", cmd], cwd=tmp_path, env=env, capture_output=True, timeout=30)
    assert any(c[:1] == ["issue"] and "close" in c[1:] for c in lines(calls))


@pytest.mark.skipif(not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists(), reason="no bash")
@pytest.mark.parametrize("cmd", [c for c in [*MENTIONS_PASS, *NO_RUN_PASS, HEREDOC_BODY, HEREDOC_BODY_UNQUOTED]
                                 if not c.startswith("git ")])
def test_bash_runs_no_close_for_the_passing_mentions(cmd, tmp_path):
    """Parity check the other way: the commands that now pass really run no close."""
    calls = tmp_path / "calls.jsonl"
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN")}
    env |= {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_CALLS": str(calls),
            "HOME": str(tmp_path), "GH_CONFIG_DIR": str(tmp_path / "gh"), "XDG_CONFIG_HOME": str(tmp_path)}
    (tmp_path / "x").mkdir()
    cmd = cmd.replace("/tmp/x/", f"{tmp_path}/x/")
    subprocess.run(["bash", "-c", cmd], cwd=tmp_path, env=env, capture_output=True, timeout=30)
    assert not any(c[:1] == ["issue"] and "close" in c[1:] for c in lines(calls))


# --- native blockers (issues #56, #64) ------------------------------------------------------

WAITING_SEQ = (launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: BLOCKED\nwhy",
               launch("pm", 2), "## PM: WAITING\nBlocked by octo/kit#3.")
BLOCKED_BY_PATH = "repos/{owner}/{repo}/issues/7/dependencies/blocked_by"
BLOCKERS_READ = ["api", "--paginate", BLOCKED_BY_PATH, "--jq", ".[] | {repo: .repository.full_name, number, state}"]
COUNT_READ = ["api", "repos/{owner}/{repo}/issues/7", "--jq", ".issue_dependencies_summary.blocked_by"]


def api_blocker(number, state="closed", repo="octo/kit"):
    """One item of the blocked_by REST list, in the shape GitHub returns (synthetic)."""
    return {"number": number, "state": state, "title": f"Blocker {number}", "repository": {"full_name": repo}}


def write_api(env, blocked_by=None, count=None, pages=None):
    """FAKE_GH_API data: the blocker list (one page, or `pages`) and the open-blocker count."""
    data = {"blocked_by": pages if pages is not None else [blocked_by or []]}
    if count is not None:
        data["issue"] = count if isinstance(count, str) else {"issue_dependencies_summary": {"blocked_by": count}}
    path = Path(env["FAKE_GH_ISSUE"]).with_name("api.json")
    path.write_text(json.dumps(data))
    env["FAKE_GH_API"] = str(path)


def test_decide_reads_blockers_for_every_role_launch_but_not_for_close():
    for event, comments in [(agent("pm", "ROLE=pm ISSUE=7"), ()),
                            (agent("software-engineer", "ROLE=engineer ISSUE=7"), (launch("pm"), "## PM: GROOMED")),
                            (send("a1", "ROLE=engineer ISSUE=7"), (launch("pm"), "## PM: GROOMED")),
                            (bash("scripts/qa-codex ROLE=qa ISSUE=7"),
                             (launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b"))]:
        fio = FakeIO(issue(*comments))
        assert fio.decide(event) is None
        assert fio.blocker_reads == [7]
    fio = FakeIO(issue(launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}"))
    assert fio.decide(bash("gh issue close 7")) is None
    assert fio.blocker_reads == []


def test_decide_without_a_blocker_reader_denies_a_role_launch():
    fio = FakeIO(issue())
    with pytest.raises(Deny) as e:  # main() turns a Deny from a reader into the deny output
        decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment)
    assert str(e.value).startswith("guard error") and fio.posts == []


def test_decide_open_blocker_denies_and_posts_nothing():
    fio = FakeIO(issue(*WAITING_SEQ), blockers=(Blocker("octo/kit", 3, "open"),), open_blockers=1)
    reason = fio.decide(agent("pm", "ROLE=pm ISSUE=7"))
    assert reason.startswith("G1:") and "octo/kit#3" in reason
    assert fio.posts == []


def test_decide_reads_blockers_inside_the_lock_before_the_post():
    events = []

    class Lock:
        def __enter__(self):
            events.append("lock")

        def __exit__(self, *exc):
            events.append("unlock")

    decide(agent("pm", "ROLE=pm ISSUE=7"), lambda n: events.append("read") or facts(issue(*WAITING_SEQ)),
           lambda n, b: events.append("post"), lock=Lock,
           read_blockers=lambda n: events.append("blockers") or ((Blocker("octo/kit", 3, "closed"),), 0))
    assert events == ["lock", "read", "blockers", "post", "unlock"]


def test_guard_reads_blockers_with_the_paginated_read_form_and_the_count(env):
    write_api(env, [api_blocker(3)], count=0)
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_SEQ)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert (code, out) == (0, "")
    calls = lines(env["FAKE_GH_CALLS"])
    assert BLOCKERS_READ in calls and COUNT_READ in calls
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 3)\nAgent: pm"}]


def test_guard_allows_no_blocker(env):
    write_api(env, [], count=0)
    assert run_guard(agent("pm", "ROLE=pm ISSUE=7"), env) == (0, "")


def test_guard_denies_one_open_blocker(env):
    write_api(env, [api_blocker(3, "open")], count=1)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    reason = deny_reason(out)
    assert reason.startswith("G1:") and "octo/kit#3" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_denies_several_blockers_one_open(env):
    write_api(env, [api_blocker(3), api_blocker(4, "open"), api_blocker(5, "closed", "other/lib")], count=1)
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("pm"), "## PM: GROOMED")
    reason = deny_reason(run_guard(agent("software-engineer", "ROLE=engineer ISSUE=7"), env)[1])
    assert reason.startswith("G1:") and "octo/kit#4" in reason and "#3" not in reason


def test_guard_allows_a_closed_blocker_in_another_repo(env):
    write_api(env, [api_blocker(9, "closed", "other/lib")], count=0)
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_SEQ)
    assert run_guard(agent("pm", "ROLE=pm ISSUE=7"), env) == (0, "")


def test_guard_reads_every_page_of_blockers(env):
    page1 = [api_blocker(n) for n in range(1, 31)]
    page2 = [api_blocker(31, "open")]
    write_api(env, pages=[page1, page2], count=1)
    reason = deny_reason(run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)[1])
    assert reason.startswith("G1:") and "octo/kit#31" in reason


def test_fake_gh_without_paginate_shows_only_the_first_page(env):
    """Control for the test above: the open blocker on page 2 is found only with --paginate."""
    write_api(env, pages=[[api_blocker(n) for n in range(1, 31)], [api_blocker(31, "open")]], count=1)
    args = [a for a in BLOCKERS_READ if a != "--paginate"]
    out = subprocess.run(["gh", *args], env={**os.environ, **env}, capture_output=True, text=True).stdout
    assert len(out.splitlines()) == 30 and '"number": 31' not in out and '"number":31' not in out


def test_guard_denies_a_count_greater_than_the_open_entries(env):
    write_api(env, [api_blocker(3)], count=1)
    reason = deny_reason(run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)[1])
    assert reason.startswith("G1:") and "cannot read" in reason


def test_guard_denies_waiting_with_an_empty_blocker_list(env):
    write_api(env, [], count=0)
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_SEQ)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    reason = deny_reason(out)
    assert reason.startswith("G2:") and "no blocker" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_close_makes_no_blocker_read(env):
    write_api(env, [api_blocker(3, "open")], count=1)
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}")
    assert run_guard(bash("gh issue close 7"), env) == (0, "")
    assert not any(c[:1] == ["api"] for c in lines(env["FAKE_GH_CALLS"]))


def test_guard_ignores_the_label_waiting(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), labels=("ready", "waiting"))
    assert run_guard(agent("pm", "ROLE=pm ISSUE=7"), env) == (0, "")


@pytest.mark.parametrize("key", ["blocked_by", "issue"])
def test_guard_failing_blocker_read_denies_with_guard_error(env, key):
    write_api(env, [], count=0)
    write_issue(Path(env["FAKE_GH_ISSUE"]), *WAITING_SEQ)
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env, FAKE_GH_API_FAIL=key)
    assert code == 0 and deny_reason(out).startswith("guard error")
    assert lines(env["FAKE_GH_LOG"]) == []


@pytest.mark.parametrize("pages, count", [
    ("not json\n", 0),
    ([[{"number": 3, "state": "open", "repository": {}}]], 0),
    ([[]], "null"),
    ([[]], "x"),
    ([[]], {}),
])
def test_guard_blocker_output_it_cannot_read_denies_with_guard_error(env, pages, count):
    data = {"blocked_by": pages}
    data["issue"] = count if isinstance(count, (str, dict)) else {"issue_dependencies_summary": {"blocked_by": count}}
    path = Path(env["FAKE_GH_ISSUE"]).with_name("api.json")
    path.write_text(json.dumps(data))
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), {**env, "FAKE_GH_API": str(path)})
    assert code == 0 and deny_reason(out).startswith("guard error")
    assert lines(env["FAKE_GH_LOG"]) == []


# --- only the repo owner's comments count (#70) -------------------------------------------------


def write_raw_comments(path, *comments):
    """Issue #7 with comment dicts as given (to set or drop authorAssociation)."""
    path.write_text(json.dumps({"number": 7, "state": "OPEN", "labels": [{"name": "ready"}],
                                "body": "Lane: default\n", "comments": list(comments)}))


def owner(body):
    return {"body": body, "authorAssociation": "OWNER"}


GUARDED_CALLS = {
    "pm": (agent("pm", "ROLE=pm ISSUE=7"), []),
    "engineer": (agent("software-engineer", "ROLE=engineer ISSUE=7"), [launch("pm"), "## PM: GROOMED"]),
    "qa": (bash("scripts/qa-" + "codex ROLE=qa ISSUE=7"),
           [launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: DONE\nCommits: a..b"]),
    "close": (bash("gh issue " + "close 7"), [launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}"]),
}


@pytest.mark.parametrize("role", list(GUARDED_CALLS))
def test_missing_author_data_denies_every_guarded_call(env, role):
    event, before = GUARDED_CALLS[role]
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]), *map(owner, before), {"body": "note"})
    code, out = run_guard(event, env)
    reason = deny_reason(out)
    assert code == 0 and reason.startswith("guard error") and "authorAssociation" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


@pytest.mark.parametrize("role", list(GUARDED_CALLS))
def test_same_calls_with_owner_author_data_are_allowed(env, role):
    event, before = GUARDED_CALLS[role]  # control for the test above
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]), *map(owner, before), owner("note"))
    assert run_guard(event, env) == (0, "")


def test_stranger_receipt_does_not_change_the_attempt(env):
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]),
                       {"body": "## Launch: pm (attempt 1)\nAgent: pm", "authorAssociation": "NONE"})
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert (code, out) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 1)\nAgent: pm"}]


def test_stranger_resume_does_not_resume_through_the_guard(env):
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]), owner(launch("pm")), owner("## PM: NEEDS OWNER"),
                       {"body": "## Owner: RESUME", "authorAssociation": "CONTRIBUTOR"})
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert code == 0 and deny_reason(out).startswith("G2:")
    assert lines(env["FAKE_GH_LOG"]) == []


def test_stranger_resume_variant_does_not_resume_through_the_guard(env):
    # issue #131: the resume match ignores case and extra whitespace, but only for the owner
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]), owner(launch("pm")), owner("## PM: NEEDS OWNER"),
                       {"body": "## OWNER: Resume", "authorAssociation": "CONTRIBUTOR"})
    code, out = run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)
    assert code == 0 and deny_reason(out).startswith("G2:")
    assert lines(env["FAKE_GH_LOG"]) == []


def test_owner_resume_variant_resumes_through_the_guard(env):
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]), owner(launch("pm")), owner("## PM: NEEDS OWNER"),
                       owner("## OWNER: Resume"))
    assert run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)[0] == 0
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: pm (attempt 2)\nAgent: pm"}]


def test_stranger_pass_does_not_close_through_the_guard(env):
    write_raw_comments(Path(env["FAKE_GH_ISSUE"]), owner(launch("pm")), owner("## PM: GROOMED"),
                       owner(launch("engineer")), owner("## Engineer: DONE\nCommits: a..b"),
                       {"body": launch("qa"), "authorAssociation": "NONE"},
                       {"body": f"## QA: PASS\nVerified: {FAKE_HEAD}", "authorAssociation": "NONE"})
    code, out = run_guard(bash("gh issue " + "close 7"), env)
    assert code == 0 and deny_reason(out).startswith("G6:")


# --- close of a stage issue (issue #97) -------------------------------------------------------

SUB_ISSUES_PATH = "repos/{owner}/{repo}/issues/7/sub_issues"
SUB_ISSUES_READ = ["api", "--paginate", SUB_ISSUES_PATH, "--jq", ".[] | {repo: .repository.full_name, number, state}"]
TOTAL_READ = ["api", "repos/{owner}/{repo}/issues/7", "--jq", ".sub_issues_summary.total"]
CLOSE_7 = bash("gh issue " + "close 7")


def write_subs(env, subs=None, total=None, pages=None):
    """FAKE_GH_API data: the sub-issue list (one page, or `pages`) and sub_issues_summary.total
    (default: the number of listed entries)."""
    pages = pages if pages is not None else [subs or []]
    if total is None:
        total = sum(len(p) for p in pages) if isinstance(pages, list) else 0
    data = {"sub_issues": pages,
            "issue": total if isinstance(total, str) else {"sub_issues_summary": {"total": total}}}
    path = Path(env["FAKE_GH_ISSUE"]).with_name("api.json")
    path.write_text(json.dumps(data))
    env["FAKE_GH_API"] = str(path)


def write_stage(env, *comments, labels=("stage",), state="OPEN"):
    data = {"number": 7, "state": state, "labels": [{"name": n} for n in labels], "body": "Stage issue\n",
            "comments": [{"body": c, "authorAssociation": "OWNER"} for c in comments]}
    Path(env["FAKE_GH_ISSUE"]).write_text(json.dumps(data))


def test_decide_reads_sub_issues_only_for_the_close_of_a_stage_issue():
    reads = []

    def read_subs(n):
        reads.append(n)
        return (issue_state.SubIssue("octo/kit", 3, "closed"),), 1

    fio = FakeIO(issue(labels=("stage",)))
    assert decide(CLOSE_7, fio.read_facts, fio.post_comment, read_blockers=fio.read_blockers,
                  read_sub_issues=read_subs) is None
    assert reads == [7] and fio.blocker_reads == [] and fio.posts == []
    reads.clear()
    fio = FakeIO(issue(launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}"))
    assert decide(CLOSE_7, fio.read_facts, fio.post_comment, read_blockers=fio.read_blockers,
                  read_sub_issues=read_subs) is None
    assert reads == []
    fio = FakeIO(issue(labels=("stage", "ready")))
    assert decide(agent("pm", "ROLE=pm ISSUE=7"), fio.read_facts, fio.post_comment,
                  read_blockers=fio.read_blockers, read_sub_issues=read_subs) is None
    assert reads == []  # a role launch is never on the stage path


def test_decide_without_a_sub_issue_reader_denies_a_stage_close():
    fio = FakeIO(issue(labels=("stage",)))
    with pytest.raises(Deny) as e:
        decide(CLOSE_7, fio.read_facts, fio.post_comment)
    assert str(e.value).startswith("guard error")


def test_decide_reads_sub_issues_inside_the_lock():
    events = []

    class Lock:
        def __enter__(self):
            events.append("lock")

        def __exit__(self, *exc):
            events.append("unlock")

    decide(CLOSE_7, lambda n: events.append("read") or facts(issue(labels=("stage",))),
           lambda n, b: events.append("post"), lock=Lock,
           read_sub_issues=lambda n: events.append("subs") or ((issue_state.SubIssue("octo/kit", 3, "closed"),), 1))
    assert events == ["lock", "read", "subs", "unlock"]


def test_guard_stage_close_all_closed_is_allowed_without_ready_and_qa(env):
    write_subs(env, [api_blocker(3), api_blocker(4)])
    write_stage(env)
    assert run_guard(CLOSE_7, env, FAKE_GIT_DIRTY="1") == (0, "")
    calls = lines(env["FAKE_GH_CALLS"])
    assert SUB_ISSUES_READ in calls and TOTAL_READ in calls
    assert BLOCKERS_READ not in calls and COUNT_READ not in calls
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_stage_close_denies_an_open_sub_issue_and_names_it(env):
    write_subs(env, [api_blocker(3), api_blocker(4, "open")])
    write_stage(env)
    reason = deny_reason(run_guard(CLOSE_7, env)[1])
    assert reason.startswith("G6:") and "octo/kit#4" in reason and "octo/kit#3" not in reason


def test_guard_stage_close_counts_not_planned_as_closed(env):
    item = {**api_blocker(3), "state_reason": "not_planned"}
    write_subs(env, [item, api_blocker(4)])
    write_stage(env)
    assert run_guard(CLOSE_7, env) == (0, "")


def test_guard_stage_close_reads_a_sub_issue_in_another_repo(env):
    write_subs(env, [api_blocker(3), api_blocker(9, "open", "other/lib")])
    write_stage(env)
    reason = deny_reason(run_guard(CLOSE_7, env)[1])
    assert reason.startswith("G6:") and "other/lib#9" in reason
    write_subs(env, [api_blocker(9, "closed", "other/lib")])
    assert run_guard(CLOSE_7, env) == (0, "")


def test_guard_stage_close_denies_no_sub_issue(env):
    write_subs(env, [])
    write_stage(env)
    reason = deny_reason(run_guard(CLOSE_7, env)[1])
    assert reason.startswith("G6:") and "no sub-issue" in reason


def test_guard_stage_close_denies_a_total_greater_than_the_list(env):
    write_subs(env, [api_blocker(3)], total=2)
    write_stage(env)
    reason = deny_reason(run_guard(CLOSE_7, env)[1])
    assert reason.startswith("G6:") and "does not hold" in reason


def test_guard_stage_close_denies_a_closed_stage_issue(env):
    write_subs(env, [api_blocker(3)])
    write_stage(env, state="CLOSED")
    assert deny_reason(run_guard(CLOSE_7, env)[1]) == "G1: issue #7 is closed, expected an open issue"


@pytest.mark.parametrize("key", ["sub_issues", "issue"])
def test_guard_stage_close_failing_read_denies_with_guard_error(env, key):
    write_subs(env, [api_blocker(3)])
    write_stage(env)
    code, out = run_guard(CLOSE_7, env, FAKE_GH_API_FAIL=key)
    assert code == 0 and deny_reason(out).startswith("guard error")


@pytest.mark.parametrize("key", ["sub_issues", "issue"])
def test_guard_stage_close_timed_out_read_denies_with_guard_error(env, key):
    """A read that runs past the guard's deadline denies with `guard error` too (issue #97, QA FAIL)."""
    write_subs(env, [api_blocker(3)])
    write_stage(env)
    start = time.monotonic()
    code, out = run_guard(CLOSE_7, env, GUARD_DEADLINE="1", FAKE_GH_API_SLEEP=f"{key}:5")
    assert time.monotonic() - start < 4
    reason = deny_reason(out)
    assert code == 0 and reason.startswith("guard error") and "deadline" in reason


@pytest.mark.parametrize("pages, total", [
    ("not json\n", 0),
    ([[{"number": 3, "state": "closed", "repository": {}}]], 1),
    ([[{"number": "3", "state": "closed", "repository": {"full_name": "octo/kit"}}]], 1),
    ([[{"number": 3, "state": "done", "repository": {"full_name": "octo/kit"}}]], 1),
    ([[api_blocker(3)]], "null"),
    ([[api_blocker(3)]], "-1"),
    ([[api_blocker(3)]], "x"),
])
def test_guard_stage_close_output_it_cannot_read_denies_with_guard_error(env, pages, total):
    write_subs(env, pages=pages, total=total)
    write_stage(env)
    code, out = run_guard(CLOSE_7, env)
    assert code == 0 and deny_reason(out).startswith("guard error")


def test_guard_stage_close_reads_every_page(env):
    write_subs(env, pages=[[api_blocker(n) for n in range(1, 31)], [api_blocker(31, "open")]])
    write_stage(env)
    reason = deny_reason(run_guard(CLOSE_7, env)[1])
    assert reason.startswith("G6:") and "octo/kit#31" in reason


def test_fake_gh_without_paginate_shows_only_the_first_page_of_sub_issues(env):
    """Control for the test above: the open sub-issue on page 2 is found only with --paginate."""
    write_subs(env, pages=[[api_blocker(n) for n in range(1, 31)], [api_blocker(31, "open")]])
    args = [a for a in SUB_ISSUES_READ if a != "--paginate"]
    out = subprocess.run(["gh", *args], env={**os.environ, **env}, capture_output=True, text=True).stdout
    assert len(out.splitlines()) == 30 and '"number":31' not in out


def test_guard_non_stage_close_is_unchanged_and_reads_no_sub_issues(env):
    write_subs(env, [api_blocker(3, "open")])
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}")
    assert run_guard(CLOSE_7, env) == (0, "")
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("qa"), "## QA: PASS\nVerified: " + "d" * 40)
    assert deny_reason(run_guard(CLOSE_7, env)[1]).startswith("G6:")
    write_issue(Path(env["FAKE_GH_ISSUE"]), launch("qa"), f"## QA: PASS\nVerified: {FAKE_HEAD}", labels=())
    assert deny_reason(run_guard(CLOSE_7, env)[1]).startswith("G1:")
    assert not any(c[:1] == ["api"] for c in lines(env["FAKE_GH_CALLS"]))


# --- planner launch on a stage issue (issue #99) -----------------------------------------------

PLANNER_7 = agent("planner", "Review the stage.\nROLE=planner ISSUE=7")
STAGE_REVIEW = "## Planner: STAGE REVIEW"


def planner_receipt(n=1, call=None):
    return launch("planner", n, agent="planner", call=call)


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_planner_launch_is_a_guarded_call_with_role_planner(tool):
    assert classify(agent("planner", "Review it.\nROLE=planner ISSUE=42", tool=tool)) == Call(
        role="planner", agent="planner", issue=42)


@pytest.mark.parametrize("prompt", ["no launch line", "ROLE=planner ISSUE=7\nROLE=planner ISSUE=7",
                                    "ROLE=planner ISSUE=7\nROLE=pm ISSUE=7"])
def test_planner_launch_without_one_launch_line_is_denied(prompt):
    reason = denied(agent("planner", prompt))
    assert reason.startswith("G1:") and "ROLE=<pm|engineer|qa|planner> ISSUE=<number>" in reason


@pytest.mark.parametrize("role", ["pm", "engineer", "qa"])
def test_planner_agent_with_another_role_is_denied(role):
    assert denied(agent("planner", f"ROLE={role} ISSUE=7")) == (
        f"G1: launch line role is {role}, expected planner for agent planner")


@pytest.mark.parametrize("agent_type, role", [("pm", "pm"), ("software-engineer", "engineer"),
                                              ("frontend-engineer", "engineer"), ("qa-engineer", "qa")])
def test_role_agent_with_role_planner_is_denied(agent_type, role):
    assert denied(agent(agent_type, "ROLE=planner ISSUE=7")) == (
        f"G1: launch line role is planner, expected {role} for agent {agent_type}")


def test_launch_hint_names_the_planner():
    assert guard.LAUNCH_HINT == "exactly one line ROLE=<pm|engineer|qa|planner> ISSUE=<number>"
    assert "ROLE=<pm|engineer|qa|planner> ISSUE=<number>" in denied(agent("pm", "no line"))
    assert "ROLE=<pm|engineer|qa|planner> ISSUE=<number>" in denied(send("worker", "no line"))


def test_send_message_with_role_planner_is_denied():
    reason = denied(send("planner-1", "Go on.\nROLE=planner ISSUE=7"))
    assert reason.startswith("G1:") and "cannot be continued" in reason
    assert "new launch of the agent planner" in reason


def test_decide_planner_send_message_reads_nothing():
    fio = FakeIO(issue(labels=("stage",)))
    assert fio.decide(send("planner-1", "ROLE=planner ISSUE=7")).startswith("G1:")
    assert fio.reads == [] and fio.posts == [] and fio.blocker_reads == []


def planner_stage(env, *comments, subs=None, **kw):
    """A stage issue #7 for a planner launch; by default its one sub-issue is closed (issue #119)."""
    write_subs(env, subs if subs is not None else [api_blocker(3)])
    write_stage(env, *comments, **kw)


def test_decide_planner_launch_posts_its_receipt_and_reads_no_blockers():
    fio = FakeIO(issue(labels=("stage",)))
    event = {**PLANNER_7, "tool_use_id": "toolu_synthetic_1"}
    assert fio.decide(event) is None
    h = issue_state.call_hash("toolu_synthetic_1")
    assert fio.posts == [(7, f"## Launch: planner (attempt 1)\nAgent: planner\nCall: {h}")]
    assert fio.blocker_reads == [] and fio.sub_reads == [7]


def test_decide_planner_launch_with_a_raising_blocker_reader_is_allowed():
    fio = FakeIO(issue(labels=("stage",)))

    def boom(n):
        raise Deny("guard error: synthetic blocker read failure")

    assert decide(PLANNER_7, fio.read_facts, fio.post_comment, read_blockers=boom,
                  read_sub_issues=fio.read_sub_issues) is None
    assert fio.posts == [(7, "## Launch: planner (attempt 1)\nAgent: planner")]


def test_decide_without_a_sub_issue_reader_denies_a_planner_launch():
    fio = FakeIO(issue(labels=("stage",)))
    with pytest.raises(Deny) as e:
        decide(PLANNER_7, fio.read_facts, fio.post_comment)
    assert str(e.value).startswith("guard error") and fio.posts == []


def test_decide_planner_launch_reads_sub_issues_inside_the_lock_before_the_post():
    events = []

    class Lock:
        def __enter__(self):
            events.append("lock")

        def __exit__(self, *exc):
            events.append("unlock")

    assert decide(PLANNER_7, lambda n: events.append("read") or facts(issue(labels=("stage",))),
                  lambda n, b: events.append("post"), lock=Lock,
                  read_sub_issues=lambda n: events.append("subs") or (
                      (issue_state.SubIssue("octo/kit", 3, "closed"),), 1)) is None
    assert events == ["lock", "read", "subs", "post", "unlock"]


@pytest.mark.parametrize("event, iss", [
    (PLANNER_7, issue(labels=("ready",))),  # no label stage
    (agent("pm", "ROLE=planner ISSUE=7"), issue(labels=("stage",))),  # denied before any read
    (send("planner-1", "ROLE=planner ISSUE=7"), issue(labels=("stage",))),
])
def test_decide_planner_call_off_the_stage_path_runs_no_sub_issue_read(event, iss):
    fio = FakeIO(iss)
    assert fio.decide(event).startswith("G1:")
    assert fio.sub_reads == [] and fio.posts == []


def test_guard_planner_launch_on_a_stage_issue_is_allowed_and_posts_the_receipt(env):
    planner_stage(env, subs=[api_blocker(3), api_blocker(4)])
    code, out = run_guard({**PLANNER_7, "tool_use_id": "toolu_synthetic_1"}, env)
    assert (code, out) == (0, "")
    h = issue_state.call_hash("toolu_synthetic_1")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": f"## Launch: planner (attempt 1)\nAgent: planner\nCall: {h}"}]
    calls = lines(env["FAKE_GH_CALLS"])
    assert SUB_ISSUES_READ in calls and TOTAL_READ in calls  # the two reads of the stage close
    assert BLOCKERS_READ not in calls and COUNT_READ not in calls  # no blocker read


def test_guard_planner_launch_denies_an_open_sub_issue_and_names_it(env):
    planner_stage(env, subs=[api_blocker(3), api_blocker(4, "open"), api_blocker(5, "open")])
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason.startswith("G1:") and "octo/kit#4" in reason and "octo/kit#5" in reason
    assert "octo/kit#3" not in reason
    assert lines(env["FAKE_GH_LOG"]) == []  # no receipt


def test_guard_planner_launch_denies_an_open_sub_issue_in_another_repo(env):
    planner_stage(env, subs=[api_blocker(3), api_blocker(9, "open", "other/lib")])
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason.startswith("G1:") and "other/lib#9" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_planner_launch_denies_no_sub_issue(env):
    planner_stage(env, subs=[])
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason.startswith("G1:") and "stage issue #7 has no sub-issue" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_planner_launch_denies_a_total_greater_than_the_list(env):
    write_subs(env, [api_blocker(3), api_blocker(4)], total=3)
    write_stage(env)
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason.startswith("G1:") and "count is 3" in reason and "holds 2" in reason
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_planner_launch_reads_every_page_of_sub_issues(env):
    planner_stage(env, subs=None)
    write_subs(env, pages=[[api_blocker(n) for n in range(1, 31)], [api_blocker(31, "open")]])
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason.startswith("G1:") and "octo/kit#31" in reason


@pytest.mark.parametrize("key", ["sub_issues", "issue"])
def test_guard_planner_launch_failing_sub_issue_read_denies_with_guard_error(env, key):
    planner_stage(env)
    code, out = run_guard(PLANNER_7, env, FAKE_GH_API_FAIL=key)
    assert code == 0 and deny_reason(out).startswith("guard error")
    assert lines(env["FAKE_GH_LOG"]) == []


@pytest.mark.parametrize("pages, total", [("not json\n", 0), ([[api_blocker(3)]], "null")])
def test_guard_planner_launch_sub_issue_output_it_cannot_read_denies_with_guard_error(env, pages, total):
    write_subs(env, pages=pages, total=total)
    write_stage(env)
    code, out = run_guard(PLANNER_7, env)
    assert code == 0 and deny_reason(out).startswith("guard error")
    assert lines(env["FAKE_GH_LOG"]) == []


@pytest.mark.parametrize("key", ["sub_issues", "issue"])
def test_guard_planner_launch_without_stage_keeps_its_message_when_a_sub_issue_read_fails(env, key):
    write_subs(env, [api_blocker(3, "open")])
    write_issue(Path(env["FAKE_GH_ISSUE"]), labels=("ready",))
    reason = deny_reason(run_guard(PLANNER_7, env, FAKE_GH_API_FAIL=key)[1])
    assert reason == "G1: issue #7 has no label stage, expected the label stage for a planner launch"
    assert not any(c[:1] == ["api"] for c in lines(env["FAKE_GH_CALLS"]))


def test_guard_planner_launch_on_a_stage_issue_with_ready_is_allowed(env):
    planner_stage(env, labels=("stage", "ready"))
    assert run_guard(PLANNER_7, env) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: planner (attempt 1)\nAgent: planner"}]


@pytest.mark.parametrize("labels", [(), ("ready",)])
def test_guard_planner_launch_without_the_label_stage_is_denied(env, labels):
    write_issue(Path(env["FAKE_GH_ISSUE"]), labels=labels)
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason == "G1: issue #7 has no label stage, expected the label stage for a planner launch"
    assert lines(env["FAKE_GH_LOG"]) == []


def test_guard_planner_launch_on_a_closed_stage_issue_is_denied(env):
    planner_stage(env, state="CLOSED")
    assert deny_reason(run_guard(PLANNER_7, env)[1]) == "G1: issue #7 is closed, expected an open issue"


@pytest.mark.parametrize("label", ["later", "needs-owner"])
def test_guard_planner_launch_with_later_or_needs_owner_is_denied(env, label):
    planner_stage(env, labels=("stage", label))
    assert deny_reason(run_guard(PLANNER_7, env)[1]) == (
        f"G1: issue #7 has the label {label}, expected no label later or needs-owner")


def test_guard_planner_launch_on_a_dirty_tree_is_denied(env):
    planner_stage(env)
    assert deny_reason(run_guard(PLANNER_7, env, FAKE_GIT_DIRTY="1")[1]) == (
        "G1: working tree is not clean, expected a clean tree (git status --porcelain empty)")


def test_guard_planner_launch_after_one_planner_miss_gets_attempt_2(env):
    planner_stage(env, planner_receipt())
    assert run_guard(PLANNER_7, env) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: planner (attempt 2)\nAgent: planner"}]


def test_guard_planner_launch_after_two_planner_misses_is_denied(env):
    planner_stage(env, planner_receipt(), planner_receipt(2))
    reason = deny_reason(run_guard(PLANNER_7, env)[1])
    assert reason == ("G1: issue #7 is pending: the last 2 launches of planner ended without a result "
                      "(## Launch: planner (attempt 1), ## Launch: planner (attempt 2)), "
                      "expected ## Owner: RESUME; escalate the issue")
    assert lines(env["FAKE_GH_LOG"]) == []


@pytest.mark.parametrize("after", [STAGE_REVIEW, "## Owner: RESUME"])
def test_guard_planner_launch_after_a_result_or_resume_gets_attempt_2(env, after):
    planner_stage(env, planner_receipt(), after)
    assert run_guard(PLANNER_7, env) == (0, "")
    assert lines(env["FAKE_GH_LOG"]) == [{"issue": 7, "body": "## Launch: planner (attempt 2)\nAgent: planner"}]


def test_guard_planner_launch_after_two_voided_receipts_is_denied(env):
    from helpers import not_started, stopped
    x, y = "0123456789ab", "ba9876543210"
    planner_stage(env, planner_receipt(1, x), not_started("planner", 1, x), planner_receipt(2, y),
                stopped("planner", 2, y))
    assert deny_reason(run_guard(PLANNER_7, env)[1]).startswith("G1: issue #7: the last 2 launches")


def test_guard_planner_launch_ignores_a_failing_blocker_read(env):
    # the blocker count read and the sub-issue total read share the key "issue"; the failing
    # sub-issue reads are covered above (issue #119)
    planner_stage(env)
    assert run_guard(PLANNER_7, env, FAKE_GH_API_FAIL="blocked_by") == (0, "")
    calls = lines(env["FAKE_GH_CALLS"])
    assert BLOCKERS_READ not in calls and COUNT_READ not in calls


def test_guard_pm_launch_on_a_stage_issue_is_unchanged(env):
    write_stage(env, planner_receipt(), STAGE_REVIEW)
    reason = deny_reason(run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)[1])
    assert reason == "G1: issue #7 has no label ready, expected the label ready"


# --- one miss, two misses in a row (issue #132) -----------------------------------------------

GROOMED_ENG_MISS = (launch("pm"), "## PM: GROOMED", launch("engineer"))


def test_decide_continuation_after_one_miss_posts_the_next_round():
    fio = FakeIO(issue(*GROOMED_ENG_MISS))
    assert fio.decide(send("a1b2c3", "ROLE=engineer ISSUE=7")) is None
    assert fio.posts == [(7, "## Launch: engineer (continued, round 2)\nAgent: a1b2c3")]


def test_decide_relaunch_after_one_miss_posts_the_next_attempt():
    fio = FakeIO(issue(*GROOMED_ENG_MISS))
    assert fio.decide(agent("software-engineer", "ROLE=engineer ISSUE=7")) is None
    assert fio.posts == [(7, "## Launch: engineer (attempt 2)\nAgent: software-engineer")]


def test_guard_relaunch_after_one_miss_is_allowed_then_a_third_is_denied(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *GROOMED_ENG_MISS)
    event = agent("software-engineer", "ROLE=engineer ISSUE=7")
    assert run_guard(event, env) == (0, "")
    reason = deny_reason(run_guard(event, env)[1])
    assert reason.startswith("G1: issue #7 is pending: the last 2 launches of engineer ended without a result")
    assert "## Owner: RESUME" in reason and "did not start" not in reason
    assert [c["body"] for c in lines(env["FAKE_GH_LOG"])] == ["## Launch: engineer (attempt 2)\nAgent: software-engineer"]


def test_guard_close_after_one_miss_is_denied(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *GROOMED_ENG_MISS)
    reason = deny_reason(run_guard(bash("gh issue " + "close 7"), env)[1])
    assert reason.startswith("G1: issue #7 is pending:") and "only engineer may go on" in reason
    assert "## Owner: RESUME" in reason


def test_guard_other_role_after_one_miss_is_denied(env):
    write_issue(Path(env["FAKE_GH_ISSUE"]), *GROOMED_ENG_MISS)
    reason = deny_reason(run_guard(agent("pm", "ROLE=pm ISSUE=7"), env)[1])
    assert reason.startswith("G1: issue #7 is pending:") and "only engineer may go on" in reason
    assert lines(env["FAKE_GH_LOG"]) == []
