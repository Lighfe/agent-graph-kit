"""Tests for scripts/run_report.py (issue #193). All data is synthetic."""

import json

import run_report


def c(body, t):
    return {"body": body, "createdAt": t}


def issue(n, comments, closed=None, labels=()):
    return {"number": n, "comments": comments, "closedAt": closed, "labels": [{"name": x} for x in labels]}


ISSUES = [
    issue(1, [
        c("## Launch: pm (attempt 1)\nAgent: pm", "2026-01-01T10:00:00Z"),
        c("## PM: GROOMED", "2026-01-01T10:10:00Z"),
        c("## Launch: engineer (attempt 1)\nx", "2026-01-01T10:20:00Z"),
        c("## Engineer: BLOCKED\nwhy", "2026-01-01T10:30:00Z"),
        c("## Launch: engineer (continued, round 1)\nx", "2026-01-01T10:40:00Z"),
        c("## Engineer: DONE", "2026-01-01T11:00:00Z"),
        c("## Launch: qa-codex (attempt 1)", "2026-01-01T11:05:00Z"),
        c("## QA: FAIL", "2026-01-01T11:20:00Z"),
        c("## Launch: qa-codex (attempt 2)", "2026-01-01T11:30:00Z"),
        # no result for the second qa launch
    ], closed="2026-01-01T12:00:00Z"),
    issue(2, [
        c("## Launch: engineer (attempt 1)", "2026-01-02T08:00:00Z"),
        c("## Engineer: DONE", "2026-01-02T08:30:00Z"),
        c("## QA: PASS", "2026-01-02T08:40:00Z"),
    ], closed="2026-01-02T09:00:00Z"),
    issue(3, [
        c("## Launch: engineer (attempt 1)", "2026-01-03T08:00:00Z"),
        c("## PM: NEEDS OWNER", "2026-01-03T08:30:00Z"),
    ], labels=["needs-owner"]),
]


def assistant(mid, i, o, cc, cr):
    return {"type": "assistant", "message": {"id": mid, "model": "m", "usage": {
        "input_tokens": i, "output_tokens": o,
        "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}}}


def write_transcript(path, role, n, msgs):
    path.parent.mkdir(parents=True, exist_ok=True)
    first = {"type": "user", "message": {"role": "user", "content": f"ROLE={role} ISSUE={n}\nrest"}}
    path.write_text("\n".join(json.dumps(x) for x in [first] + msgs) + "\n")


def run(tmp_path, issues=ISSUES, numbers="1,2,3", transcripts=None, capsys=None, stage=None):
    f = tmp_path / "issues.json"
    f.write_text(json.dumps(issues))
    argv = ["--comments", str(f)]
    argv += ["--issues", numbers] if numbers is not None else []
    if transcripts is not None:
        argv += ["--transcripts", str(transcripts)]
    if stage is not None:
        argv += ["--stage", str(stage)]
    assert run_report.main(argv) == 0
    return capsys.readouterr().out


def transcripts(tmp_path):
    d = tmp_path / "t"
    write_transcript(d / "s1" / "subagents" / "a.jsonl", "engineer", 1,
                     [assistant("m1", 1, 2, 3, 4), assistant("m1", 1, 2, 3, 4), assistant("m2", 10, 20, 30, 40)])
    write_transcript(d / "s1" / "subagents" / "b.jsonl", "engineer", 1, [assistant("m3", 5, 5, 5, 5)])
    write_transcript(d / "s1" / "subagents" / "c.jsonl", "pm", 2, [assistant("m4", 1, 1, 1, 1)])
    (d / "s1" / "subagents" / "junk.jsonl").write_text("not json\n")
    return d


def test_token_sums_and_dedupe(tmp_path, capsys):
    out = run(tmp_path, transcripts=transcripts(tmp_path), capsys=capsys)
    # engineer issue 1: (1+10+5, 2+20+5, 3+30+5, 4+40+5); the repeated message id counts once
    assert "- Tokens engineer: input 16, output 27, cache creation 38, cache read 49" in out
    assert "- Tokens pm: input 1, output 1, cache creation 1, cache read 1" in out
    assert "- Most tokens: #1 (130), #2 (4)" in out
    assert "- Role with the most tokens: engineer (130)" in out


def test_launches_continuation_and_no_result(tmp_path, capsys):
    out = run(tmp_path, capsys=capsys)
    assert "- engineer: 2 launches, 0 without a result" in out
    assert "- qa-codex: 2 launches, 1 without a result" in out
    assert "- pm: 1 launches, 0 without a result" in out
    assert "- Launch to close or last result: 2h 00m" in out


def test_failure_shares_and_zero_issue(tmp_path, capsys):
    out = run(tmp_path, capsys=capsys)
    assert "- Engineer: BLOCKED: 1 of 3 issues (33%)" in out
    assert "- QA: FAIL: 1 of 3 issues (33%)" in out
    assert "- QA: UNAVAILABLE: 0 of 3 issues (0%)" in out
    assert "- escalation: 1 of 3 issues (33%)" in out
    # issue 2 has no failure marker: it still counts in the total of 3
    only2 = run(tmp_path, numbers="2", capsys=capsys)
    assert "- QA: FAIL: 0 of 1 issues (0%)" in only2
    assert "largest share: none" in only2


def test_missing_transcript_folder(tmp_path, capsys):
    out = run(tmp_path, capsys=capsys, transcripts=tmp_path / "nope")
    assert "- Tokens: no transcript" in out
    assert "- Most tokens: no transcript data" in out
    assert "Longest launch-to-close time: #1 (2h 00m)" in out


def test_no_transcript_arg_still_prints_rest(tmp_path, capsys):
    out = run(tmp_path, capsys=capsys)
    assert "no transcript data" in out
    assert "## Failure types" in out


def test_empty_issue_list(tmp_path, capsys):
    out = run(tmp_path, numbers="", capsys=capsys)
    assert "No issues given." in out
    assert "(0%)" in out
    assert "Longest launch-to-close time: none" in out


def test_fewer_than_three_issues_and_stage(tmp_path, capsys):
    stage = {"number": 9, "comments": [], "subIssues": [2, 3]}
    out = run(tmp_path, issues=ISSUES + [stage], numbers=None, stage=9, capsys=capsys)
    assert "## Issue #2" in out and "## Issue #3" in out and "## Issue #1" not in out
    assert "#2 (1h 00m)" in out
