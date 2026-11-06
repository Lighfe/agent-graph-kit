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


def run(tmp_path, issues, monkeypatch, folder=None, codex=None, role=None, keep_orch=False):
    """Run `write`; return the record lines, without the issue lines unless role is "issue"."""
    rec = tmp_path / "state" / "run-record.jsonl"
    monkeypatch.setenv("RUN_RECORD_FILE", str(rec))
    argv = ["write", "--project", "o/r", "--stage", "9", "--issues", str(issues_file(tmp_path, issues)),
            "--transcripts", str(folder or tmp_path / "tr")]
    if codex is not None:
        argv += ["--codex-usage", str(codex)]
    assert rr.main(argv) == 0
    rows = [json.loads(x) for x in rec.read_text().splitlines()] if rec.exists() else []
    return [r for r in rows if (r["role"] == "issue") == (role == "issue") and (keep_orch or r["role"] != "orchestrator")]


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
    assert line["start"] == "2026-10-21T10:00:00.000Z" and line["end"] == "2026-10-21T11:00:00Z"
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


QA3 = [("qa", "2026-10-21T10:00:00Z"), ("qa", "2026-10-21T10:40:00Z"), ("qa", "2026-10-21T11:20:00Z")]


def qa_issue(receipts, closed="2026-10-21T12:00:00Z"):
    i = one_issue(5, receipts)
    i["closedAt"] = closed
    return i


def retries(lines):
    return [x["retry"] for x in sorted(lines, key=lambda x: x["start"])]


def test_codex_retry_counts_qa_receipts(tmp_path, monkeypatch):
    # usage lines written out of order; retry follows the receipts, not the file order
    f = codex_file(tmp_path, [crec(5, "2026-10-21T11:30:00Z"), crec(5, "2026-10-21T10:10:00Z"),
                              crec(5, "2026-10-21T10:50:00Z")])
    lines = run(tmp_path, [qa_issue(QA3)], monkeypatch, codex=f)
    assert retries(lines) == [0, 1, 2]
    assert len(run(tmp_path, [qa_issue(QA3)], monkeypatch, codex=f)) == 3


def test_codex_retry_one_receipt_one_line(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T10:30:00Z")])
    (line,) = run(tmp_path, [qa_issue(QA3[:1])], monkeypatch, codex=f)
    assert line["retry"] == 0


def test_codex_retry_counts_qa_launch_without_usage_line(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T10:10:00Z"), crec(5, "2026-10-21T11:30:00Z")])
    assert retries(run(tmp_path, [qa_issue(QA3)], monkeypatch, codex=f)) == [0, 2]


def test_codex_retry_no_qa_receipt_is_zero(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T10:30:00Z")])
    (line,) = run(tmp_path, [qa_issue([("pm", "2026-10-21T10:00:00Z")])], monkeypatch, codex=f)
    assert line["retry"] == 0


def starts(lines):
    return {x["end"]: x["start"] for x in lines}


def test_codex_start_is_newest_qa_receipt_at_or_before(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T11:00:00Z"), crec(5, "2026-10-21T10:30:00Z")])
    lines = run(tmp_path, [qa_issue(QA3[:2])], monkeypatch, codex=f)
    assert starts(lines) == {"2026-10-21T10:30:00Z": "2026-10-21T10:00:00.000Z",
                             "2026-10-21T11:00:00Z": "2026-10-21T10:40:00.000Z"}


def test_codex_start_receipt_at_exactly_usage_time_counts(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T10:40:00Z")])
    (line,) = run(tmp_path, [qa_issue(QA3[:2])], monkeypatch, codex=f)
    assert line["start"] == "2026-10-21T10:40:00.000Z" and line["end"] == "2026-10-21T10:40:00Z"


def test_codex_start_without_qa_receipt_equals_end(tmp_path, monkeypatch):
    f = codex_file(tmp_path, [crec(5, "2026-10-21T10:30:00Z")])
    (line,) = run(tmp_path, [qa_issue([("pm", "2026-10-21T10:00:00Z"), ("qa", "2026-10-21T11:00:00Z")])],
                  monkeypatch, codex=f)
    assert line["start"] == line["end"] == "2026-10-21T10:30:00Z"
    assert line["id"] == "o/r:codex:5:2026-10-21T10:30:00Z"


def test_issue_line(tmp_path, monkeypatch):
    issue = closed_issue(comments=["## PM: NEEDS OWNER\nwhy", "  ## QA: NEEDS OWNER  ", "no ## NEEDS OWNER"])
    (line,) = run(tmp_path, [issue], monkeypatch, role="issue")
    assert (line["role"], line["issue"], line["stage"], line["escalations"]) == ("issue", 5, 9, 2)
    assert line["start"] == "2026-10-21T10:00:00.000Z" and line["end"] == "2026-10-21T12:00:00.000Z"
    assert (line["input_tokens"], line["output_tokens"], line["cache_creation_tokens"], line["cache_read_tokens"]) == (0, 0, 0, 0)
    assert (line["source"], line["id"]) == ("issues", "o/r:issue:5")


def test_issue_line_open_with_needs_owner_label(tmp_path, monkeypatch):
    issue = one_issue(5)
    issue["labels"] = [{"name": "needs-owner"}]
    (line,) = run(tmp_path, [issue], monkeypatch, role="issue")
    assert line["escalations"] == 1 and line["start"] is None and line["end"] is None


def test_issue_line_repeated_run_adds_none(tmp_path, monkeypatch):
    assert len(run(tmp_path, [closed_issue()], monkeypatch, role="issue")) == 1
    assert len(run(tmp_path, [closed_issue()], monkeypatch, role="issue")) == 1


def test_issue_line_provider_null_source_issues(tmp_path, monkeypatch):
    (line,) = run(tmp_path, [closed_issue()], monkeypatch, role="issue")
    assert line["provider"] is None and line["source"] == "issues"


def test_no_issue_line_for_stage_issue(tmp_path, monkeypatch):
    stage = closed_issue(9, labels=("stage",))
    lines = run(tmp_path, [stage, closed_issue(5), closed_issue(6)], monkeypatch, role="issue")
    assert sorted(x["issue"] for x in lines) == [5, 6]


def test_no_issue_line_for_stage_label_alone(tmp_path, monkeypatch):
    other = closed_issue(12)
    other["labels"] = ["stage"]
    lines = run(tmp_path, [other, closed_issue(5)], monkeypatch, role="issue")
    assert [x["issue"] for x in lines] == [5]


def test_no_issue_line_for_stage_number_alone(tmp_path, monkeypatch):
    stage = one_issue(9)
    assert "labels" not in stage
    lines = run(tmp_path, [stage, closed_issue(5)], monkeypatch, role="issue")
    assert [x["issue"] for x in lines] == [5]


def test_stage_issue_keeps_launch_lines(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "a.jsonl", [
        user("ROLE=planner ISSUE=9"),
        asst("m1", "claude-x", (1, 2, 3, 4), "2026-10-21T10:01:00.000Z")])
    stage = closed_issue(9, labels=("stage",))
    lines = run(tmp_path, [stage], monkeypatch)
    assert [(x["role"], x["issue"]) for x in lines] == [("planner", 9)]


def test_start_end_are_first_and_last_message_not_min_max(tmp_path, monkeypatch):
    write(tmp_path / "tr" / "o.jsonl", [
        user("ROLE=pm ISSUE=5", "2026-10-21T11:00:00Z"),
        asst("m1", "claude-x", (1, 1, 1, 1), "2026-10-21T10:59:00Z"),
        asst("m2", "claude-x", (1, 1, 1, 1), "2026-10-21T11:02:00Z"),
        asst("m3", "claude-x", (1, 1, 1, 1), "2026-10-21T11:01:00Z")])
    (line,) = run(tmp_path, [one_issue()], monkeypatch)
    assert line["start"] == "2026-10-21T11:00:00.000Z" and line["end"] == "2026-10-21T11:01:00.000Z"


# --- orchestrator lines (issue #244) ---

def cost_state(**models):
    usage = {m: {"inputTokens": v[0], "outputTokens": v[1], "cacheCreationInputTokens": v[2],
                 "cacheReadInputTokens": v[3]} for m, v in models.items()}
    return {"type": "cost-state", "sessionId": "s1", "modelUsage": usage}


def main_session(tmp_path, rows, name="sess"):
    """A main-session transcript directly in the project folder `proj`; returns the subagent folder."""
    write(tmp_path / "proj" / f"{name}.jsonl", rows)
    return tmp_path / "proj" / name / "subagents"


def orch(lines):
    return {(x["model"], x["estimate"]): x for x in lines if x["role"] == "orchestrator"}


def sub_launch(folder):
    write(folder / "agent-a.jsonl", [user("ROLE=pm ISSUE=5", "2026-10-21T10:00:00Z"),
                                     asst("s1", "claude-x", (10, 20, 30, 40), "2026-10-21T10:01:00Z")])


MAIN = [{"type": "user", "timestamp": "2026-10-21T09:00:00Z", "message": {"content": "hello"}},
        asst("a1", "claude-x", (100, 200, 300, 400), "2026-10-21T09:05:00Z"),
        asst("a1", "claude-x", (100, 200, 300, 400), "2026-10-21T09:05:00Z"),
        asst("a2", "claude-x", (1, 2, 3, 4), "2026-10-21T09:10:00Z")]


def test_orchestrator_cost_state_minus_subagents(tmp_path, monkeypatch):
    folder = main_session(tmp_path, MAIN + [cost_state(**{"claude-x": (1000, 2000, 3000, 4000)})])
    sub_launch(folder)
    lines = run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True)
    o = orch(lines)
    m, e = o[("claude-x", False)], o[("claude-x", True)]
    assert (m["input_tokens"], m["output_tokens"], m["cache_creation_tokens"], m["cache_read_tokens"]) == (990, 1980, 2970, 3960)
    assert (m["role"], m["issue"], m["provider"], m["retry"], m["source"]) == ("orchestrator", None, "claude", 0, "session-total")
    assert (m["start"], m["end"]) == ("2026-10-21T09:00:00.000Z", "2026-10-21T09:10:00.000Z")
    assert e["input_tokens"] == round(990 * rr.ORCHESTRATOR_ESTIMATE_FACTOR) and e["source"] == "session-total"
    assert (m["id"], e["id"]) == ("o/r:sess:claude-x:measured", "o/r:sess:claude-x:estimate")
    assert len([x for x in lines if x["role"] == "pm"]) == 1


def test_orchestrator_cost_state_without_subagent_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "COST_STATE_INCLUDES_SUBAGENTS", False)
    folder = main_session(tmp_path, MAIN + [cost_state(**{"claude-x": (1000, 2000, 3000, 4000)})])
    sub_launch(folder)
    m = orch(run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True))[("claude-x", False)]
    assert (m["input_tokens"], m["output_tokens"], m["cache_creation_tokens"], m["cache_read_tokens"]) == (1000, 2000, 3000, 4000)


def test_orchestrator_without_cost_state_sums_messages(tmp_path, monkeypatch):
    folder = main_session(tmp_path, MAIN)
    o = orch(run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True))
    m = o[("claude-x", False)]
    assert (m["input_tokens"], m["output_tokens"], m["cache_creation_tokens"], m["cache_read_tokens"]) == (101, 202, 303, 404)
    assert m["source"] == "transcript" and o[("claude-x", True)]["source"] == "transcript"


def test_orchestrator_no_usable_usage_no_line(tmp_path, monkeypatch, capsys):
    folder = main_session(tmp_path, [{"type": "user", "timestamp": "2026-10-21T09:00:00Z", "message": {"content": "hi"}},
                                     {"type": "cost-state", "modelUsage": "broken"}])
    assert orch(run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True)) == {}
    assert "no orchestrator line" in capsys.readouterr().out


def test_orchestrator_no_main_transcript_says_so(tmp_path, monkeypatch, capsys):
    assert orch(run(tmp_path, [one_issue()], monkeypatch, keep_orch=True)) == {}
    assert "No main-session transcript found" in capsys.readouterr().out


def test_orchestrator_two_models(tmp_path, monkeypatch):
    folder = main_session(tmp_path, MAIN + [cost_state(**{"claude-x": (10, 20, 30, 40), "claude-y": (1, 2, 3, 4)})])
    o = orch(run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True))
    assert sorted(o) == [("claude-x", False), ("claude-x", True), ("claude-y", False), ("claude-y", True)]
    assert o[("claude-y", False)]["input_tokens"] == 1


def test_orchestrator_appends_again_and_prints_file(tmp_path, monkeypatch, capsys):
    folder = main_session(tmp_path, MAIN)
    run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True)
    run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True)
    out = capsys.readouterr().out
    assert out.count("Orchestrator transcript:") == 2 and "sess.jsonl" in out
    rec = (tmp_path / "state" / "run-record.jsonl").read_text().splitlines()
    assert [json.loads(x)["id"] for x in rec if json.loads(x)["role"] == "orchestrator"].count("o/r:sess:claude-x:measured") == 2


def test_orchestrator_transcript_option_and_newest_pick(tmp_path, monkeypatch):
    main_session(tmp_path, MAIN, "old")
    main_session(tmp_path, MAIN[:2], "new")
    import os
    os.utime(tmp_path / "proj" / "old.jsonl", (1, 1))
    assert orch(run(tmp_path, [one_issue()], monkeypatch, folder=tmp_path / "proj", keep_orch=True))[("claude-x", False)]["input_tokens"] == 100
    rec = tmp_path / "state" / "run-record.jsonl"
    rec.unlink()
    argv = ["write", "--project", "o/r", "--stage", "9", "--issues", str(issues_file(tmp_path, [one_issue()])),
            "--transcripts", str(tmp_path / "proj"), "--orchestrator-transcript", str(tmp_path / "proj" / "old.jsonl")]
    assert rr.main(argv) == 0
    ids = [json.loads(x)["id"] for x in rec.read_text().splitlines()]
    assert "o/r:old:claude-x:measured" in ids and "o/r:new:claude-x:measured" not in ids


def test_orchestrator_discovery_skips_subagents_folder(tmp_path):
    folder = main_session(tmp_path, MAIN)
    write(folder / "agent-1.jsonl", [user("no role prompt here")])
    assert rr.newest_main_transcript(folder) == tmp_path / "proj" / "sess.jsonl"


def test_orchestrator_empty_cost_state_falls_back_to_messages(tmp_path, monkeypatch):
    folder = main_session(tmp_path, MAIN + [cost_state(**{"claude-x": (0, 0, 0, 0)})])
    m = orch(run(tmp_path, [one_issue()], monkeypatch, folder=folder, keep_orch=True))[("claude-x", False)]
    assert (m["input_tokens"], m["source"]) == (101, "transcript")


# --- limit subcommand (issue #245) ---

def test_limit_appends_line(tmp_path, monkeypatch):
    rec = tmp_path / "state" / "run-record.jsonl"
    monkeypatch.setenv("RUN_RECORD_FILE", str(rec))
    monkeypatch.delenv("RUN_RECORD_LIMITS_FILE", raising=False)
    argv = ["limit", "--project", "o/r", "--stage", "9", "--point", "start", "--percent", "12.5", "--plan", "max"]
    assert rr.main(argv) == 0
    rows = [json.loads(x) for x in (tmp_path / "state" / "run-record-limits.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert (row["v"], row["project"], row["stage"], row["point"], row["percent"], row["plan"]) == (1, "o/r", 9, "start", 12.5, "max")
    assert row["time"].endswith("Z")


def test_limit_env_overrides_path(tmp_path, monkeypatch):
    target = tmp_path / "elsewhere" / "l.jsonl"
    monkeypatch.setenv("RUN_RECORD_LIMITS_FILE", str(target))
    assert rr.main(["limit", "--project", "p", "--stage", "1", "--point", "end", "--percent", "0", "--plan", "x"]) == 0
    assert target.is_file()


def test_limit_rejects_bad_input(tmp_path, monkeypatch):
    import pytest
    target = tmp_path / "l.jsonl"
    monkeypatch.setenv("RUN_RECORD_LIMITS_FILE", str(target))
    for pct in ("-1", "100.5"):
        assert rr.main(["limit", "--project", "p", "--stage", "1", "--point", "end", "--percent", pct, "--plan", "x"]) != 0
    with pytest.raises(SystemExit) as e:
        rr.main(["limit", "--project", "p", "--stage", "1", "--point", "middle", "--percent", "5", "--plan", "x"])
    assert e.value.code != 0
    assert not target.exists()


# --- Codex QA step rows from `write` (#272) ---------------------------------------------------

STREAM = [
    {"type": "thread.started", "thread_id": "t"},
    {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "ls",
                                        "aggregated_output": "a\n", "exit_code": 0, "status": "completed"}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2}},
]
QA_CODEX = "qa-" + "codex"


def step_rows():
    import os
    p = Path(os.environ["STEPS_FILE"])
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def codex_step_rows():
    return [r for r in step_rows() if r["role"] == QA_CODEX]


def write_with_runs(tmp_path, monkeypatch, runs=None, record="rec.jsonl"):
    rec = tmp_path / record
    monkeypatch.setenv("RUN_RECORD_FILE", str(rec))
    argv = ["write", "--project", "o/r", "--stage", "9",
            "--issues", str(issues_file(tmp_path, [one_issue(5)])), "--transcripts", str(tmp_path / "tr")]
    if runs is not None:
        argv += ["--codex-runs", str(runs)]
    assert rr.main(argv) == 0
    return rec


def test_write_codex_runs_gives_codex_step_rows(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    write(runs / "o__r-5-20261104T090807.jsonl", STREAM)
    write_with_runs(tmp_path, monkeypatch, runs)
    rows = codex_step_rows()
    assert len(rows) == 2
    assert {(r["role"], r["issue"], r["stage"]) for r in rows} == {(QA_CODEX, 5, 9)}
    assert {r["launch"] for r in rows} == {"o__r-5-20261104T090807"}


def test_write_codex_runs_skips_other_issue_and_other_project(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    write(runs / "o__r-77-20261104T090807.jsonl", STREAM)  # issue 77 is not in --issues
    write(runs / "x__y-5-20261104T090807.jsonl", STREAM)  # another project
    write_with_runs(tmp_path, monkeypatch, runs)
    assert step_rows() == []


def test_write_reads_codex_runs_dir_by_default(tmp_path, monkeypatch):
    runs = tmp_path / "env-runs"
    write(runs / "o__r-5-20261104T090807.jsonl", STREAM)
    monkeypatch.setenv("CODEX_RUNS_DIR", str(runs))
    write_with_runs(tmp_path, monkeypatch)
    rows = codex_step_rows()
    assert len(rows) == 2 and {r["issue"] for r in rows} == {5}


def test_write_missing_codex_runs_folder_same_record(tmp_path, monkeypatch, capsys):
    plain = write_with_runs(tmp_path, monkeypatch, record="plain.jsonl")
    missing = write_with_runs(tmp_path, monkeypatch, tmp_path / "no-such-folder", record="missing.jsonl")
    assert missing.read_text() == plain.read_text() and plain.read_text()
    assert codex_step_rows() == []
    assert "Warning" not in capsys.readouterr().out


def test_write_twice_adds_no_second_codex_step_row(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    write(runs / "o__r-5-20261104T090807.jsonl", STREAM)
    write_with_runs(tmp_path, monkeypatch, runs)
    first = sorted(r["id"] for r in codex_step_rows())
    write_with_runs(tmp_path, monkeypatch, runs)
    assert sorted(r["id"] for r in codex_step_rows()) == first and len(first) == 2
