"""Tests for the step extractor `plugin/skills/monitor/steps.py` and its call in `run_record.py write`
(issue #263). All transcripts are synthetic."""

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugin" / "skills" / "monitor" / "steps.py"
RR_SRC = ROOT / "plugin" / "skills" / "run-record" / "run_record.py"
FAKES = ROOT / "tests" / "fakes"
FIXTURES = FAKES / "monitor"


def load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = load("steps_under_test", SRC)
rr = load("run_record_for_steps", RR_SRC)


# --- synthetic transcript lines ---------------------------------------------------------------

def user(text, t="2026-11-04T10:00:00.000Z"):
    return {"type": "user", "timestamp": t, "message": {"role": "user", "content": text}}


def results(*items, t="2026-11-04T10:00:30.000Z"):
    """A user line with tool results: items are (tool_use_id, content, is_error or None)."""
    blocks = []
    for tid, content, err in items:
        b = {"type": "tool_result", "tool_use_id": tid, "content": content}
        if err is not None:
            b["is_error"] = err
        blocks.append(b)
    return {"type": "user", "timestamp": t, "message": {"role": "user", "content": blocks}}


def usage(i=1, o=2, cc=3, cr=4):
    return {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}


def asst(mid, blocks, t="2026-11-04T10:00:10.000Z", model="claude-x", u=None):
    return {"type": "assistant", "timestamp": t,
            "message": {"id": mid, "model": model, "role": "assistant", "content": blocks, "usage": u or usage()}}


def tool(tid, name, **inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def thinking(text="pondering"):
    return {"type": "thinking", "thinking": text, "signature": "sig"}


def text(t):
    return {"type": "text", "text": t}


def write(path, rows, tail=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows) + tail)
    return path


def steps_file():
    return Path(os.environ["STEPS_FILE"])


def read_rows():
    p = steps_file()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def collect(folder, *extra, project="o/r"):
    return st.main(["collect", "--project", project, "--transcripts", str(folder), *extra])


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    """Put the fake `gh` first on PATH; return the call log path and the FAKE_GH_API file."""
    monkeypatch.setenv("PATH", f"{FAKES}{os.pathsep}{os.environ['PATH']}")
    calls = tmp_path / "gh-calls.jsonl"
    api = tmp_path / "gh-api.json"
    monkeypatch.setenv("FAKE_GH_CALLS", str(calls))
    monkeypatch.setenv("FAKE_GH_API", str(api))
    monkeypatch.setenv("RUN_RECORD_FILE", str(tmp_path / "state" / "run-record.jsonl"))
    return calls, api


def gh_calls(calls):
    return [json.loads(x) for x in calls.read_text().splitlines()] if calls.exists() else []


# --- one row per message ----------------------------------------------------------------------

def test_split_message_is_one_row_with_both_tools_and_usage_once(tmp_path):
    write(tmp_path / "tr" / "launch-a.jsonl", [
        user("ROLE=engineer ISSUE=7"),
        asst("m1", [thinking()], t="2026-11-04T10:00:10.000Z", u=usage(10, 20, 30, 40)),
        asst("m1", [tool("t1", "Read", file_path="/repo/src/a.py")], t="2026-11-04T10:00:10.500Z", u=usage(10, 20, 30, 40)),
        asst("m1", [tool("t2", "Bash", command="ls -la")], t="2026-11-04T10:00:11.000Z", u=usage(10, 20, 30, 40)),
        results(("t1", "abcde", None), ("t2", [text("12"), text("345")], None)),
        asst("m2", [text("done")], t="2026-11-04T10:01:10.000Z", u=usage(1, 1, 1, 1)),
    ])
    assert collect(tmp_path / "tr", "--stage", "3") == 0
    rows = read_rows()
    assert len(rows) == 2
    row = rows[0]
    assert list(row) == list(st.FIELDS)
    assert row["v"] == 1 and row["id"] == "o/r:launch-a:m1" and row["launch"] == "launch-a"
    assert (row["project"], row["stage"], row["issue"], row["role"]) == ("o/r", 3, 7, "engineer")
    assert row["tool"] == ["Read", "Bash"] and row["target"] == ["/repo/src/a.py", "ls -la"]
    assert (row["input_tokens"], row["output_tokens"], row["cache_creation_tokens"], row["cache_read_tokens"]) == (10, 20, 30, 40)
    assert row["context_tokens"] == 80
    assert row["result_chars"] == 10 and row["is_error"] is False
    assert row["seq"] == 1 and row["time"] == "2026-11-04T10:00:10.000Z" and row["duration_s"] == 60.0
    assert row["model"] == "claude-x"
    last = rows[1]
    assert last["seq"] == 2 and last["duration_s"] is None
    assert (last["tool"], last["target"], last["result_chars"], last["is_error"]) == ([], [], 0, False)


def test_launch_is_the_run_record_launch_part(tmp_path, monkeypatch):
    """`launch` equals the second part of the run-record `id` of the same transcript."""
    write(tmp_path / "tr" / "s1" / "subagents" / "agent-abc.jsonl", [
        user("ROLE=pm ISSUE=5"), asst("m1", [text("x")])])
    monkeypatch.setenv("RUN_RECORD_FILE", str(tmp_path / "rec.jsonl"))
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([{"number": 5, "comments": []}]))
    lines = rr.build_lines("o/r", 9, rr.load_issues(issues), tmp_path / "tr")
    (row,) = st.launch_rows(tmp_path / "tr" / "s1" / "subagents" / "agent-abc.jsonl", "o/r", lambda _i: 9)
    assert row["launch"] == lines[0]["id"].split(":")[1] == "agent-abc"


def test_targets_and_kit_docs(tmp_path):
    long = "echo " + "x" * 400
    write(tmp_path / "tr" / "l.jsonl", [
        user("ROLE=qa ISSUE=7"),
        asst("m1", [tool("a", "Read", file_path="/home/u/repo/AGENTS.md"),
                    tool("b", "Edit", file_path="src/b.py", old_string="x", new_string="y"),
                    tool("c", "Write", file_path="src/c.py", content="z"),
                    tool("d", "NotebookEdit", notebook_path="n.ipynb", new_source="q"),
                    tool("e", "Bash", command=long),
                    tool("f", "Agent", subagent_type="qa-engineer", prompt="secret"),
                    tool("g", "Grep", pattern="foo")]),
        asst("m2", [tool("h", "Read", file_path="docs/process.md")], t="2026-11-04T10:00:20Z"),
        asst("m3", [tool("i", "Read", file_path="/r/docs/team/pm.md")], t="2026-11-04T10:00:30Z"),
        asst("m4", [tool("j", "Read", file_path="/r/docs/task-template.md")], t="2026-11-04T10:00:40Z"),
        asst("m5", [tool("k", "Read", file_path="/r/docs/specs/x.md")], t="2026-11-04T10:00:50Z"),
        asst("m6", [tool("l", "Edit", file_path="/r/AGENTS.md")], t="2026-11-04T10:01:00Z"),
    ])
    collect(tmp_path / "tr", "--stage", "1")
    rows = read_rows()
    assert rows[0]["tool"] == ["Read", "Edit", "Write", "NotebookEdit", "Bash", "Agent", "Grep"]
    assert rows[0]["target"] == ["/home/u/repo/AGENTS.md", "src/b.py", "src/c.py", "n.ipynb", long[:300], "qa-engineer", None]
    assert len(rows[0]["target"][4]) == 300
    assert [r["kit_doc"] for r in rows] == ["/home/u/repo/AGENTS.md", "docs/process.md", "/r/docs/team/pm.md",
                                           "/r/docs/task-template.md", None, None]


def test_result_chars_and_is_error(tmp_path):
    write(tmp_path / "tr" / "l.jsonl", [
        user("ROLE=qa ISSUE=7"),
        asst("m1", [tool("a", "Bash", command="false"), tool("b", "Read", file_path="x")]),
        results(("a", "boom!", True), ("b", [text("abc"), {"type": "image", "source": {}}], False)),
        asst("m2", [tool("c", "Bash", command="true")], t="2026-11-04T10:00:40Z"),
        results(("c", "ok", None)),
    ])
    collect(tmp_path / "tr", "--stage", "1")
    rows = read_rows()
    assert (rows[0]["result_chars"], rows[0]["is_error"]) == (8, True)
    assert (rows[1]["result_chars"], rows[1]["is_error"]) == (2, False)


# --- role and issue ---------------------------------------------------------------------------

GOAL = "<command-name>/goal</command-name>\n            <command-message>goal</command-message>"
STAGE = "<command-message>stage-start</command-message>\n<command-name>/stage-start</command-name>"
AGK_STAGE = "<command-message>agk:stage-start</command-message>\n<command-name>/agk:stage-start</command-name>"
OTHER = "<command-message>doctor</command-message>\n<command-name>/doctor</command-name>"


@pytest.mark.parametrize("prompts, role", [
    ([GOAL], "orchestrator"),
    ([STAGE], "planner"),
    ([AGK_STAGE], "planner"),
    ([OTHER, STAGE, GOAL], "planner"),
    ([OTHER, GOAL, STAGE], "orchestrator"),
    (["hello", OTHER], "main"),
    (["hello"], "main"),
])
def test_role_without_role_prompt(tmp_path, prompts, role):
    write(tmp_path / "tr" / "main-1.jsonl", [*(user(p) for p in prompts), asst("m1", [text("hi")])])
    collect(tmp_path / "tr", "--stage", "2")
    (row,) = read_rows()
    assert (row["role"], row["issue"]) == (role, None)


def test_role_prompt_only_counts_in_first_user_line(tmp_path):
    write(tmp_path / "tr" / "x.jsonl", [user("hello"), user("ROLE=qa ISSUE=5"), asst("m1", [text("hi")])])
    collect(tmp_path / "tr", "--stage", "2")
    (row,) = read_rows()
    assert (row["role"], row["issue"]) == ("main", None)


def test_role_prompt_in_text_parts(tmp_path):
    first = {"type": "user", "timestamp": "2026-11-04T10:00:00Z",
             "message": {"content": [text("ROLE=pm ISSUE=12\nWork on it")]}}
    write(tmp_path / "tr" / "x.jsonl", [first, asst("m1", [text("hi")])])
    collect(tmp_path / "tr", "--stage", "2")
    (row,) = read_rows()
    assert (row["role"], row["issue"]) == ("pm", 12)


# --- stage ------------------------------------------------------------------------------------

def two_launches(tmp_path, issue=7):
    write(tmp_path / "tr" / "a.jsonl", [user(f"ROLE=pm ISSUE={issue}"), asst("m1", [text("x")])])
    write(tmp_path / "tr" / "b.jsonl", [user(f"ROLE=engineer ISSUE={issue}"), asst("m2", [text("y")])])


def test_stage_argument_wins_and_no_gh_call(tmp_path, fake_gh):
    calls, _ = fake_gh
    two_launches(tmp_path)
    assert collect(tmp_path / "tr", "--stage", "4") == 0
    assert {r["stage"] for r in read_rows()} == {4}
    assert gh_calls(calls) == []


def test_stage_from_run_record_line(tmp_path, fake_gh):
    calls, _ = fake_gh
    rec = Path(os.environ["RUN_RECORD_FILE"])
    rec.parent.mkdir(parents=True)
    rec.write_text(json.dumps({"id": "o/r:issue:7", "project": "o/r", "stage": 11, "issue": 7}) + "\n"
                   + json.dumps({"id": "x/y:issue:7", "project": "x/y", "stage": 99, "issue": 7}) + "\n")
    two_launches(tmp_path)
    assert collect(tmp_path / "tr") == 0
    assert {r["stage"] for r in read_rows()} == {11}
    assert gh_calls(calls) == []


def test_stage_from_gh_parent_one_call_per_issue(tmp_path, fake_gh):
    calls, api = fake_gh
    api.write_text(json.dumps({"parent": {"7": {"number": 21, "title": "Stage"}}}))
    two_launches(tmp_path)
    write(tmp_path / "tr" / "main.jsonl", [user(GOAL), asst("m3", [text("z")])])
    assert collect(tmp_path / "tr") == 0
    rows = read_rows()
    assert {r["stage"] for r in rows if r["issue"] == 7} == {21}
    assert [r["stage"] for r in rows if r["issue"] is None] == [None]
    assert gh_calls(calls) == [["api", "repos/{owner}/{repo}/issues/7/parent"]]


def test_stage_null_when_gh_fails(tmp_path, fake_gh, monkeypatch):
    calls, _ = fake_gh
    monkeypatch.setenv("FAKE_GH_FAIL", "1")
    two_launches(tmp_path)
    assert collect(tmp_path / "tr") == 0
    rows = read_rows()
    assert len(rows) == 2 and {r["stage"] for r in rows} == {None}
    assert len(gh_calls(calls)) == 1


def test_stage_null_when_issue_has_no_parent(tmp_path, fake_gh):
    two_launches(tmp_path)
    assert collect(tmp_path / "tr") == 0
    assert {r["stage"] for r in read_rows()} == {None}


# --- repeat, cut line, missing folder ---------------------------------------------------------

def test_second_collect_adds_no_row(tmp_path, capsys):
    two_launches(tmp_path)
    collect(tmp_path / "tr", "--stage", "1")
    first = steps_file().read_text()
    collect(tmp_path / "tr", "--stage", "1")
    assert steps_file().read_text() == first
    assert "Wrote 0 step rows" in capsys.readouterr().out


def test_same_message_id_in_two_launches_gives_two_rows(tmp_path):
    write(tmp_path / "tr" / "a.jsonl", [user("ROLE=pm ISSUE=7"), asst("m1", [text("x")])])
    write(tmp_path / "tr" / "b.jsonl", [user("ROLE=pm ISSUE=7"), asst("m1", [text("x")])])
    collect(tmp_path / "tr", "--stage", "1")
    assert sorted(r["id"] for r in read_rows()) == ["o/r:a:m1", "o/r:b:m1"]


def test_cut_last_line_gives_rows_of_full_lines(tmp_path):
    cut = json.dumps(asst("m9", [tool("t9", "Bash", command="ls")]))[:40]
    write(tmp_path / "tr" / "a.jsonl", [user("ROLE=pm ISSUE=7"), asst("m1", [text("x")]),
                                        asst("m2", [text("y")], t="2026-11-04T10:00:20Z")], tail=cut)
    assert collect(tmp_path / "tr", "--stage", "1") == 0
    assert [r["id"] for r in read_rows()] == ["o/r:a:m1", "o/r:a:m2"]


def test_missing_folder_exits_0(tmp_path, capsys):
    assert collect(tmp_path / "nope", "--stage", "1") == 0
    assert "No transcript folder" in capsys.readouterr().out
    assert read_rows() == []


# --- no text is written -----------------------------------------------------------------------

def test_no_prompt_thinking_text_or_tool_output_is_written(tmp_path):
    write(tmp_path / "tr" / "a.jsonl", [
        user("ROLE=pm ISSUE=7 MARKER-PROMPT-1f3a"),
        asst("m1", [thinking("MARKER-THINK-9b2c"), text("MARKER-TEXT-77de"),
                    tool("t1", "Grep", pattern="MARKER-INPUT-5e5e")]),
        results(("t1", "MARKER-RESULT-c0de", None)),
        results(("t1", [text("MARKER-RESULT-LIST-aa11")], None)),
        user("MARKER-LATER-PROMPT-4242"),
        asst("m2", [text("ok")], t="2026-11-04T10:00:40Z"),
    ])
    collect(tmp_path / "tr", "--stage", "1")
    data = steps_file().read_text()
    assert len(read_rows()) == 2
    assert "MARKER" not in data


def test_fixture_transcript_has_no_text_in_output(tmp_path):
    """The synthetic fixture under tests/fakes/monitor/ (a split message with markers in each text)."""
    folder = tmp_path / "tr"
    folder.mkdir()
    (folder / "fixture-launch.jsonl").write_text((FIXTURES / "fixture-launch.jsonl").read_text())
    collect(folder, "--stage", "5")
    rows = read_rows()
    assert [r["tool"] for r in rows] == [["Read", "Bash"], []]
    assert rows[0]["input_tokens"] == 100 and rows[0]["result_chars"] == 11
    assert "SECRET" not in steps_file().read_text()


# --- file and paths ---------------------------------------------------------------------------

def test_file_mode_0600_new_and_existing(tmp_path):
    two_launches(tmp_path)
    collect(tmp_path / "tr", "--stage", "1")
    assert stat.S_IMODE(steps_file().stat().st_mode) == 0o600
    steps_file().chmod(0o644)
    write(tmp_path / "tr" / "c.jsonl", [user("ROLE=qa ISSUE=7"), asst("m3", [text("z")])])
    collect(tmp_path / "tr", "--stage", "1")
    assert stat.S_IMODE(steps_file().stat().st_mode) == 0o600
    assert len(read_rows()) == 3


def test_steps_path(tmp_path, monkeypatch):
    monkeypatch.setenv("STEPS_FILE", str(tmp_path / "x.jsonl"))
    assert st.steps_path() == tmp_path / "x.jsonl"
    monkeypatch.delenv("STEPS_FILE")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert st.steps_path() == tmp_path / "xdg" / "agent-graph-kit" / "steps.jsonl"
    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert st.steps_path() == tmp_path / "home" / ".local" / "state" / "agent-graph-kit" / "steps.jsonl"


def test_default_transcripts_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert st.default_transcripts("/home/u/my_proj.v2") == tmp_path / "home" / ".claude" / "projects" / "-home-u-my-proj-v2"
    monkeypatch.chdir(tmp_path)
    expected = re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd()))
    assert st.default_transcripts() == tmp_path / "home" / ".claude" / "projects" / expected


def test_default_folder_used_by_collect(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    folder = tmp_path / "home" / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd()))
    write(folder / "s" / "subagents" / "a.jsonl", [user("ROLE=pm ISSUE=7"), asst("m1", [text("x")])])
    assert st.main(["collect", "--project", "o/r", "--stage", "1"]) == 0
    assert [r["id"] for r in read_rows()] == ["o/r:a:m1"]


def test_conftest_keeps_steps_out_of_real_state_dir():
    real = Path.home() / ".local" / "state" / "agent-graph-kit" / "steps.jsonl"
    assert os.environ.get("STEPS_FILE") and Path(os.environ["STEPS_FILE"]) != real


def test_cli_runs_as_script(tmp_path):
    two_launches(tmp_path)
    res = subprocess.run([sys.executable, str(SRC), "collect", "--project", "o/r", "--transcripts",
                          str(tmp_path / "tr"), "--stage", "1"], capture_output=True, text=True, env=os.environ)
    assert res.returncode == 0, res.stderr
    assert "Wrote 2 step rows" in res.stdout


def test_standard_library_only():
    head = SRC.read_text().split("# ///", 2)[1]
    assert "dependencies" not in head
    assert "requires-python" in head


def test_skill_files_and_hand_skill():
    import build_plugin
    assert "monitor" in build_plugin.HAND_SKILLS
    skill = (ROOT / "plugin" / "skills" / "monitor" / "SKILL.md").read_text()
    assert skill.startswith("---\nname: monitor\n")
    desc = re.search(r"^description: (.*)$", skill, re.M).group(1)
    assert desc.startswith('"') and desc.endswith('"')
    assert "steps.py\" collect" in skill
    rr_skill = (ROOT / "plugin" / "skills" / "run-record" / "SKILL.md").read_text()
    assert "step rows" in rr_skill and "monitor" in rr_skill


# --- run_record.py write ----------------------------------------------------------------------

def stage_files(tmp_path):
    """Transcripts of a stage: launches of issue 5, one of issue 77 (not in --issues), and a main session."""
    tr = tmp_path / "tr"
    write(tr / "main-s.jsonl", [user(GOAL), asst("o1", [tool("x", "Agent", subagent_type="pm")])])
    write(tr / "main-s" / "subagents" / "agent-p.jsonl", [user("ROLE=pm ISSUE=5"), asst("p1", [text("x")]),
                                                          asst("p2", [text("y")], t="2026-11-04T10:00:20Z")])
    write(tr / "main-s" / "subagents" / "agent-q.jsonl", [user("ROLE=pm ISSUE=77"), asst("q1", [text("x")])])
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([{"number": 5, "comments": []}]))
    return tr, issues


def run_write(monkeypatch, tr, issues, record):
    monkeypatch.setenv("RUN_RECORD_FILE", str(record))
    return rr.main(["write", "--project", "o/r", "--stage", "9", "--issues", str(issues), "--transcripts", str(tr)])


def test_write_also_writes_step_rows(tmp_path, fake_gh, monkeypatch, capsys):
    calls, _ = fake_gh
    tr, issues = stage_files(tmp_path)
    assert run_write(monkeypatch, tr, issues, tmp_path / "rec.jsonl") == 0
    rows = read_rows()
    assert sorted(r["id"] for r in rows) == ["o/r:agent-p:p1", "o/r:agent-p:p2", "o/r:main-s:o1"]
    assert {r["stage"] for r in rows} == {9}
    assert {(r["launch"], r["role"], r["issue"]) for r in rows} == {("agent-p", "pm", 5), ("main-s", "orchestrator", None)}
    assert gh_calls(calls) == []
    assert "Wrote 3 step rows" in capsys.readouterr().out


def test_failing_step_write_changes_nothing_in_the_record(tmp_path, fake_gh, monkeypatch, capsys):
    tr, issues = stage_files(tmp_path)
    real_write_steps = rr.write_steps
    monkeypatch.setattr(rr, "write_steps", lambda *a, **k: 0)  # a run without the step write
    plain = tmp_path / "plain.jsonl"
    code_plain = run_write(monkeypatch, tr, issues, plain)
    monkeypatch.setattr(rr, "write_steps", real_write_steps)
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    monkeypatch.setenv("STEPS_FILE", str(blocker / "steps.jsonl"))  # its parent is a file: the step write raises
    capsys.readouterr()
    broken = tmp_path / "broken.jsonl"
    code_broken = run_write(monkeypatch, tr, issues, broken)
    out = capsys.readouterr().out
    assert code_broken == code_plain == 0
    assert broken.read_text() == plain.read_text() and plain.read_text()
    assert "Warning: no step rows written" in out


def test_failing_step_write_inside_extractor(tmp_path, fake_gh, monkeypatch, capsys):
    """The step write raises inside the extractor (its append), not only at the file path."""
    tr, issues = stage_files(tmp_path)
    real_load = importlib.util.spec_from_file_location

    def load_and_break(name, src, *a, **k):
        spec = real_load(name, src, *a, **k)
        if name == "agk_steps":
            orig = spec.loader.exec_module

            def exec_module(module):
                orig(module)
                module.append_rows = lambda rows: (_ for _ in ()).throw(RuntimeError("synthetic failure"))
            spec.loader.exec_module = exec_module
        return spec
    monkeypatch.setattr(importlib.util, "spec_from_file_location", load_and_break)
    assert run_write(monkeypatch, tr, issues, tmp_path / "rec.jsonl") == 0
    assert "Warning: no step rows written: RuntimeError: synthetic failure" in capsys.readouterr().out
    assert (tmp_path / "rec.jsonl").read_text()
