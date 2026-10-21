"""Tests for the run-record skill `plugin/skills/run-record/run_record.py` (issue #242). All data is synthetic."""

import ast
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugin" / "skills" / "run-record" / "run_record.py"
spec = importlib.util.spec_from_file_location("run_record", SRC)
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


def user(prompt, t="2026-10-21T10:00:00.000Z"):
    return {"type": "user", "timestamp": t, "message": {"content": prompt}}


def asst(mid, model, usage, t):
    u = {"input_tokens": usage[0], "output_tokens": usage[1],
         "cache_creation_input_tokens": usage[2], "cache_read_input_tokens": usage[3]}
    return {"type": "assistant", "timestamp": t, "message": {"id": mid, "model": model, "usage": u}}


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def issues_file(tmp_path, issues):
    p = tmp_path / "issues.json"
    p.write_text(json.dumps(issues))
    return p


def run(tmp_path, issues, monkeypatch, folder=None, codex=None, role=None):
    """Run `write`; return the record lines, without the issue lines unless role is "issue"."""
    rec = tmp_path / "state" / "run-record.jsonl"
    monkeypatch.setenv("RUN_RECORD_FILE", str(rec))
    argv = ["write", "--project", "o/r", "--stage", "9", "--issues", str(issues_file(tmp_path, issues)),
            "--transcripts", str(folder or tmp_path / "tr")]
    if codex is not None:
        argv += ["--codex-usage", str(codex)]
    assert rr.main(argv) == 0
    rows = [json.loads(x) for x in rec.read_text().splitlines()] if rec.exists() else []
    return [r for r in rows if (r["role"] == "issue") == (role == "issue")]


def one_issue(n=5, receipts=()):
    return {"number": n, "comments": [{"body": f"## Launch: {r} (attempt 1)\nx", "createdAt": t} for r, t in receipts]}


def test_one_launch(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "a.jsonl", [
        user("ROLE=pm ISSUE=5"),
        asst("m1", "claude-x", (10, 20, 30, 40), "2026-10-21T10:01:00.000Z"),
        asst("m1", "claude-x", (10, 20, 30, 40), "2026-10-21T10:01:00.000Z"),
        asst("m2", "claude-x", (1, 2, 3, 4), "2026-10-21T10:02:00.000Z"),
    ])
    lines = run(tmp_path, [one_issue()], monkeypatch)
    assert len(lines) == 1
    line = lines[0]
    assert list(line) == list(rr.FIELDS)
    assert (line["v"], line["id"], line["project"], line["stage"], line["issue"]) == (1, "o/r:a:claude-x", "o/r", 9, 5)
    assert (line["role"], line["provider"], line["model"], line["effort"]) == ("pm", "claude", "claude-x", None)
    assert (line["input_tokens"], line["output_tokens"], line["cache_creation_tokens"], line["cache_read_tokens"]) == (11, 22, 33, 44)
    assert line["start"] == "2026-10-21T10:00:00.000Z" and line["end"] == "2026-10-21T10:02:00.000Z"
    assert (line["retry"], line["estimate"], line["source"]) == (0, False, "transcript")


def test_two_models_two_lines(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "sub" / "b.jsonl", [
        user("ROLE=engineer ISSUE=5"),
        asst("m1", "claude-a", (1, 1, 1, 1), "2026-10-21T10:01:00Z"),
        asst("m2", "claude-b", (2, 2, 2, 2), "2026-10-21T10:02:00Z"),
    ])
    lines = run(tmp_path, [one_issue()], monkeypatch)
    assert sorted(x["id"] for x in lines) == ["o/r:b:claude-a", "o/r:b:claude-b"]
    assert {x["retry"] for x in lines} == {0}


def test_repeated_run_adds_nothing(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "a.jsonl", [user("ROLE=pm ISSUE=5"), asst("m1", "claude-x", (1, 1, 1, 1), "2026-10-21T10:01:00Z")])
    assert len(run(tmp_path, [one_issue()], monkeypatch)) == 1
    assert len(run(tmp_path, [one_issue()], monkeypatch)) == 1


def test_ignored_transcripts(tmp_path, monkeypatch):
    use = asst("m1", "claude-x", (1, 1, 1, 1), "2026-10-21T10:01:00Z")
    write(tmp_path / "tr" / "noprompt.jsonl", [user("hello"), use])
    write(tmp_path / "tr" / "other.jsonl", [user("ROLE=pm ISSUE=77"), use])
    write(tmp_path / "tr" / "nousage.jsonl", [user("ROLE=pm ISSUE=5")])
    assert run(tmp_path, [one_issue()], monkeypatch) == []


def test_second_qa_launch_has_retry_1(tmp_path, monkeypatch):
    receipts = [("qa", "2026-10-21T10:00:00Z"), ("qa", "2026-10-21T11:00:00Z")]
    write(tmp_path / "tr" / "q1.jsonl", [user("ROLE=qa ISSUE=5", "2026-10-21T10:00:05Z"),
                                          asst("m1", "claude-x", (1, 1, 1, 1), "2026-10-21T10:05:00Z")])
    write(tmp_path / "tr" / "q2.jsonl", [user("ROLE=qa ISSUE=5", "2026-10-21T11:00:05Z"),
                                          asst("m2", "claude-x", (1, 1, 1, 1), "2026-10-21T11:05:00Z")])
    lines = {x["id"]: x["retry"] for x in run(tmp_path, [one_issue(receipts=receipts)], monkeypatch)}
    assert lines == {"o/r:q1:claude-x": 0, "o/r:q2:claude-x": 1}


def test_missing_folder_writes_nothing(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, [one_issue()], monkeypatch, folder=tmp_path / "nope") == []
    assert "No transcript folder" in capsys.readouterr().out


def test_record_path(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_RECORD_FILE", str(tmp_path / "x.jsonl"))
    assert rr.record_path() == tmp_path / "x.jsonl"
    monkeypatch.delenv("RUN_RECORD_FILE")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert rr.record_path() == tmp_path / "xdg" / "agent-graph-kit" / "run-record.jsonl"
    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert rr.record_path() == tmp_path / "home" / ".local" / "state" / "agent-graph-kit" / "run-record.jsonl"


def test_append_lines_skips_known_id_except_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_RECORD_FILE", str(tmp_path / "d" / "r.jsonl"))
    assert rr.append_lines([{"id": "a", "role": "pm"}, {"id": "o", "role": "orchestrator"}]) == 2
    assert rr.append_lines([{"id": "a", "role": "pm"}, {"id": "o", "role": "orchestrator"}]) == 1


def test_no_network_imports():
    tree = ast.parse(SRC.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module.split(".")[0])
    assert not names & {"socket", "urllib", "http", "subprocess"}


def test_marker_only_in_first_user_prompt(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "late.jsonl", [user("ordinary first prompt"), user("ROLE=qa ISSUE=5"),
                                            asst("m1", "claude-x", (1, 1, 1, 1), "2026-10-21T10:05:00Z")])
    assert run(tmp_path, [one_issue()], monkeypatch) == []


def test_times_come_from_messages_only(tmp_path, monkeypatch):
    receipts = [("qa", "2026-10-21T10:00:00Z"), ("qa", "2026-10-21T11:00:00Z")]
    write(tmp_path / "tr" / "q2.jsonl", [
        {"type": "summary", "timestamp": "2026-10-21T09:00:00Z"},
        user("ROLE=qa ISSUE=5", "2026-10-21T11:00:05Z"),
        asst("m2", "claude-x", (1, 1, 1, 1), "2026-10-21T11:05:00Z"),
        {"type": "system", "timestamp": "2026-10-21T12:00:00Z"},
    ])
    (line,) = run(tmp_path, [one_issue(receipts=receipts)], monkeypatch)
    assert line["start"] == "2026-10-21T11:00:05.000Z" and line["end"] == "2026-10-21T11:05:00.000Z"
    assert line["retry"] == 1


def test_no_message_timestamp_gives_null(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "n.jsonl", [
        {"type": "summary", "timestamp": "2026-10-21T09:00:00Z"},
        {"type": "user", "message": {"content": "ROLE=pm ISSUE=5"}},
        {"type": "assistant", "message": {"id": "m", "model": "claude-x", "usage": {"input_tokens": 1}}}])
    (line,) = run(tmp_path, [one_issue()], monkeypatch)
    assert line["start"] is None and line["end"] is None


def test_skill_frontmatter_is_valid_yaml():
    import re
    text = (ROOT / "plugin" / "skills" / "run-record" / "SKILL.md").read_text()
    desc = re.search(r"^description: (.*)$", text, re.M).group(1)
    assert desc.startswith('"') and desc.endswith('"')


def codex_file(tmp_path, rows):
    p = tmp_path / "codex-qa-usage.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def crec(issue, t, **kw):
    return {"issue": issue, "time": t, "model": "gpt-x", "effort": "high", "input_tokens": 100,
            "cached_input_tokens": 60, "output_tokens": 7, **kw}


WIN = [("qa", "2026-10-21T10:00:00Z")]


def closed_issue(n=5, closed="2026-10-21T12:00:00Z", labels=(), comments=()):
    i = one_issue(n, WIN)
    i["closedAt"] = closed
    i["labels"] = [{"name": x} for x in labels]
    i["comments"] += [{"body": b, "createdAt": "2026-10-21T10:30:00Z"} for b in comments]
    return i


def test_codex_line_inside_window(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T11:00:00Z")])
    (line,) = run(tmp_path, [closed_issue()], monkeypatch, codex=f)
    assert list(line) == list(rr.FIELDS)
    assert (line["role"], line["provider"], line["model"], line["effort"]) == ("qa-codex", "codex", "gpt-x", "high")
    assert (line["input_tokens"], line["cache_read_tokens"], line["cache_creation_tokens"], line["output_tokens"]) == (100, 60, 0, 7)
    assert line["start"] == line["end"] == "2026-10-21T11:00:00Z"
    assert (line["retry"], line["source"], line["issue"], line["stage"]) == (0, "codex-record", 5, 9)
    assert line["id"] == "o/r:codex:5:2026-10-21T11:00:00Z"


def test_codex_skips_outside_window_and_unknown_issue(tmp_path, monkeypatch, capsys):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T09:00:00Z"), crec(5, "2026-10-21T13:00:00Z"),
                              crec(99, "2026-10-21T11:00:00Z"), {"issue": 5}, {"time": "2026-10-21T11:00:00Z"},
                              crec(5, "2026-10-21T11:00:00Z")])
    assert len(run(tmp_path, [closed_issue()], monkeypatch, codex=f)) == 1
    assert "skipped 5 Codex record lines" in capsys.readouterr().out


def test_codex_issue_without_receipt_has_no_window(tmp_path, monkeypatch, capsys):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T11:00:00Z")])
    assert run(tmp_path, [one_issue()], monkeypatch, codex=f) == []
    assert "skipped 1 Codex record lines" in capsys.readouterr().out


def test_codex_missing_or_empty_file(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, [closed_issue()], monkeypatch, codex=tmp_path / "nope.jsonl") == []
    (tmp_path / "e.jsonl").write_text("")
    assert run(tmp_path, [closed_issue()], monkeypatch, codex=tmp_path / "e.jsonl") == []
    assert "skipped" not in capsys.readouterr().out


def test_codex_open_issue_window_runs_to_now(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T15:00:00Z")])
    assert len(run(tmp_path, [one_issue(5, WIN)], monkeypatch, codex=f)) == 1


def test_two_codex_runs_two_lines_and_repeat_adds_none(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T11:00:00Z"), crec(5, "2026-10-21T11:30:00Z")])
    assert len(run(tmp_path, [closed_issue()], monkeypatch, codex=f)) == 2
    assert len(run(tmp_path, [closed_issue()], monkeypatch, codex=f)) == 2


def test_issue_line(tmp_path, monkeypatch):
    issue = closed_issue(comments=["## PM: NEEDS OWNER\nwhy", "  ## QA: NEEDS OWNER  ", "no ## NEEDS OWNER"])
    (line,) = run(tmp_path, [issue], monkeypatch, role="issue")
    assert (line["role"], line["issue"], line["stage"], line["escalations"]) == ("issue", 5, 9, 2)
    assert line["start"] == "2026-10-21T10:00:00.000Z" and line["end"] == "2026-10-21T12:00:00.000Z"
    assert (line["input_tokens"], line["output_tokens"], line["cache_creation_tokens"], line["cache_read_tokens"]) == (0, 0, 0, 0)
    assert (line["source"], line["id"]) == ("transcript", "o/r:issue:5")


def test_issue_line_open_with_needs_owner_label(tmp_path, monkeypatch):
    issue = one_issue(5)
    issue["labels"] = [{"name": "needs-owner"}]
    (line,) = run(tmp_path, [issue], monkeypatch, role="issue")
    assert line["escalations"] == 1 and line["start"] is None and line["end"] is None


def test_issue_line_repeated_run_adds_none(tmp_path, monkeypatch):
    assert len(run(tmp_path, [closed_issue()], monkeypatch, role="issue")) == 1
    assert len(run(tmp_path, [closed_issue()], monkeypatch, role="issue")) == 1


def test_start_end_are_first_and_last_message_not_min_max(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "o.jsonl", [
        user("ROLE=pm ISSUE=5", "2026-10-21T11:00:00Z"),
        asst("m1", "claude-x", (1, 1, 1, 1), "2026-10-21T10:59:00Z"),
        asst("m2", "claude-x", (1, 1, 1, 1), "2026-10-21T11:02:00Z"),
        asst("m3", "claude-x", (1, 1, 1, 1), "2026-10-21T11:01:00Z")])
    (line,) = run(tmp_path, [one_issue()], monkeypatch)
    assert line["start"] == "2026-10-21T11:00:00.000Z" and line["end"] == "2026-10-21T11:01:00.000Z"
