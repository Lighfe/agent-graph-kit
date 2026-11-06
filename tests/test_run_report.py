"""Tests for scripts/run_report.py (issue #193). All data is synthetic."""

import json

import pytest

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


def test_codex_usage_record(tmp_path, capsys):
    rec = tmp_path / "codex-qa-usage.jsonl"
    rec.write_text("".join(json.dumps(d) + "\n" for d in (
        {"issue": 1, "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 5},
        {"issue": 1, "input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 1},
        {"issue": 2, "input_tokens": 7, "cached_input_tokens": 1, "output_tokens": 2},
    )) + "not json\n")
    f = tmp_path / "issues.json"
    f.write_text(json.dumps(ISSUES))
    assert run_report.main(["--comments", str(f), "--issues", "1,2,3", "--codex-usage", str(rec)]) == 0
    out = capsys.readouterr().out
    assert out.count("- Codex QA tokens: 136") == 1
    assert out.count("- Codex QA tokens: 10\n") == 1
    assert out.count("- Codex QA tokens: no record") == 1  # issue 3


def test_codex_usage_no_record_leaves_rest_unchanged(tmp_path, capsys):
    base = run(tmp_path, capsys=capsys)
    assert base.count("- Codex QA tokens: no record") == 3
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    f = tmp_path / "issues.json"
    for argv in (["--codex-usage", str(tmp_path / "missing.jsonl")], ["--codex-usage", str(empty)]):
        assert run_report.main(["--comments", str(f), "--issues", "1,2,3", *argv]) == 0
        assert capsys.readouterr().out == base


# --- report from the run record (issue #245) ---

def rline(id_, project="o/a", stage=9, issue=1, role="engineer", provider="claude", model="m1",
          tok=(100, 10, 40, 1000), retry=0, estimate=False, **extra):
    d = {"v": 1, "id": id_, "project": project, "stage": stage, "issue": issue, "role": role,
         "provider": provider, "model": model, "input_tokens": tok[0], "output_tokens": tok[1],
         "cache_creation_tokens": tok[2], "cache_read_tokens": tok[3], "start": "2026-10-21T10:00:00.000Z",
         "end": "2026-10-21T10:30:00.000Z", "retry": retry, "estimate": estimate}
    d.update(extra)
    return d


WEIGHTS = {"note": "x", "claude": {"input": 1, "output": 5, "cache_creation": 1.25, "cache_read": 0.1},
           "codex": {"input": 1, "output": 5, "cache_creation": 1, "cache_read": 0.1}}


def write_record(path, rows, raw_extra=()):
    path.write_text("\n".join([json.dumps(r) for r in rows] + list(raw_extra)) + "\n")


def record_rows():
    return [
        rline("a1"),
        rline("a2", role="qa", retry=2, issue=1),
        rline("c1", role="qa-codex", provider="codex", model="gpt", tok=(10, 2, 0, 50)),
        rline("o1", role="orchestrator", issue=None, tok=(1000, 100, 0, 0)),
        rline("o2", role="orchestrator", issue=None, tok=(1100, 110, 0, 0), estimate=True),
        rline("b1", project="o/b", stage=3, issue=7, tok=(5, 5, 5, 5)),
        {"v": 1, "id": "i1", "project": "o/a", "stage": 9, "issue": 1, "role": "issue", "escalations": 2,
         "start": "2026-10-21T10:00:00.000Z", "end": "2026-10-21T12:05:00.000Z"},
    ]


def run_record_report(tmp_path, rows, capsys, extra=(), raw_extra=(), weights=None):
    rec = tmp_path / "rec.jsonl"
    write_record(rec, rows, raw_extra)
    w = tmp_path / "w.json"
    w.write_text(json.dumps(weights or WEIGHTS))
    code = run_report.main(["--record", str(rec), "--weights", str(w), *extra])
    return code, capsys.readouterr()


def test_weighted_applies_factors():
    assert run_report.weighted(rline("x"), WEIGHTS) == 100 + 50 + 50 + 100.0
    assert run_report.weighted(rline("x", provider="codex", tok=(0, 0, 10, 0)), WEIGHTS) == 10.0


def test_codex_weighted_counts_cached_input_once():
    weights = run_report.load_weights(run_report.DEFAULT_WEIGHTS)
    line = rline("x", provider="codex", tok=(100, 0, 0, 80))
    assert run_report.weighted(line, weights) == pytest.approx(28)


def test_codex_weighted_cached_larger_than_input_is_not_negative():
    weights = run_report.load_weights(run_report.DEFAULT_WEIGHTS)
    line = rline("x", provider="codex", tok=(10, 2, 0, 50))
    assert run_report.weighted(line, weights) == pytest.approx(15)


def test_record_report_sections(tmp_path, capsys):
    code, cap = run_record_report(tmp_path, record_rows(), capsys)
    assert code == 0
    out = cap.out
    assert "| engineer | 105 | 15 | 45 | 1,005 |" in out
    assert "orchestrator (measured up to the run of the record writer; not complete)" in out
    assert "| orchestrator estimate (model m1) | 1,100 | 110 | 0 | 0 |" in out
    assert "| o/b (claude) |" in out and "| gpt |" in out
    assert "estimate from price ratios, not measured plan use" in out
    assert "| o/a | 9 | codex | 15 | 0 |" in out
    assert "| #1 | 2h 05m | 2 |" in out
    assert "| qa | #1 | 2 |" in out


def test_stage_and_project_filter(tmp_path, capsys):
    _c, cap = run_record_report(tmp_path, record_rows(), capsys, extra=["--stage", "3"])
    assert "| o/b (claude) |" in cap.out and "| o/a (claude) |" not in cap.out
    _c, cap = run_record_report(tmp_path, record_rows(), capsys, extra=["--project", "o/a"])
    assert "| o/b (claude) |" not in cap.out


def test_changed_weights_change_total_not_record(tmp_path, capsys):
    rec = tmp_path / "rec.jsonl"
    write_record(rec, record_rows())
    before = rec.read_bytes()
    w = tmp_path / "w.json"
    outs = []
    for out_factor in (5, 50):
        weights = json.loads(json.dumps(WEIGHTS))
        weights["claude"]["output"] = out_factor
        w.write_text(json.dumps(weights))
        assert run_report.main(["--record", str(rec), "--weights", str(w)]) == 0
        outs.append(capsys.readouterr().out)
    assert outs[0] != outs[1]
    assert rec.read_bytes() == before


def test_bad_json_line_skipped(tmp_path, capsys):
    code, cap = run_record_report(tmp_path, record_rows(), capsys, raw_extra=["{not json"])
    assert code == 0 and "skipped 1 invalid line" in cap.out.lower()


def test_missing_and_incomplete_weights(tmp_path, capsys):
    rec = tmp_path / "rec.jsonl"
    write_record(rec, record_rows())
    missing = tmp_path / "nope.json"
    assert run_report.main(["--record", str(rec), "--weights", str(missing)]) != 0
    assert str(missing) in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"claude": {"input": 1}, "codex": WEIGHTS["codex"]}))
    assert run_report.main(["--record", str(rec), "--weights", str(bad)]) != 0
    assert str(bad) in capsys.readouterr().err


def test_id_twice_last_counts(tmp_path, capsys):
    rows = [rline("same", tok=(1, 1, 1, 1)), rline("same", tok=(7, 1, 1, 1))]
    _c, cap = run_record_report(tmp_path, rows, capsys)
    assert "| engineer | 7 | 1 | 1 | 1 |" in cap.out


def test_limits_next_to_weighted_total(tmp_path, capsys):
    lim = tmp_path / "lim.jsonl"
    rows = [
        {"v": 1, "project": "o/a", "stage": 9, "time": "2026-10-21T09:05:00.000Z", "point": "start", "percent": 12, "plan": "max"},
        {"v": 1, "project": "o/a", "stage": 9, "time": "2026-10-21T09:00:00.000Z", "point": "start", "percent": 10, "plan": "max"},
    ]
    lim.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    _c, cap = run_record_report(tmp_path, record_rows(), capsys, extra=["--limits", str(lim)])
    assert "o/a stage 9: weighted claude" in cap.out
    assert "start 12%" in cap.out and "start 10%" not in cap.out
    assert "end not entered" in cap.out
    assert "o/b stage 3" in cap.out and "start not entered" in cap.out


def table_rows(out, title):
    """Return the body rows of the Markdown table under `## <title>` as lists of cells."""
    part = out.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in part.splitlines() if ln.startswith("|")][2:]
    return [[cell.strip() for cell in ln.strip("|").split("|")] for ln in rows]


TOKEN_TABLES = ("Tokens per role", "Tokens per issue", "Tokens per model", "Tokens per project")
WEIGHTED_TITLE = "Weighted totals per stage and provider"


def two_model_rows():
    """One stage: orchestrator measured and estimate lines for models m1 and m2, one Claude and one Codex
    line on issue 4."""
    return [
        rline("e1", issue=4, tok=(100, 10, 40, 1000)),
        rline("q1", role="qa-codex", issue=4, provider="codex", model="gpt", tok=(30, 3, 0, 20)),
        rline("o1", role="orchestrator", issue=None, model="m1", tok=(1000, 100, 0, 0)),
        rline("o2", role="orchestrator", issue=None, model="m1", tok=(1100, 110, 0, 0), estimate=True),
        rline("o3", role="orchestrator", issue=None, model="m2", tok=(2000, 200, 0, 0)),
        rline("o4", role="orchestrator", issue=None, model="m2", tok=(2200, 220, 0, 0), estimate=True),
    ]


def label_words(label):
    for ch in "(),:;":
        label = label.replace(ch, " ")
    return label.split()


def test_orchestrator_estimate_rows_name_model(tmp_path, capsys):
    _c, cap = run_record_report(tmp_path, two_model_rows(), capsys)
    for title in TOKEN_TABLES:
        rows = table_rows(cap.out, title)
        assert "estimate" not in [r[0] for r in rows], title
        for model, nums in (("m1", ["1,100", "110", "0", "0"]), ("m2", ["2,200", "220", "0", "0"])):
            hits = [r for r in rows if r[1:] == nums]
            assert len(hits) == 1, (title, model, rows)
            words = label_words(hits[0][0])
            assert "orchestrator" in words and "estimate" in words and model in words, (title, hits)


def test_issue_table_orchestrator_row_and_role_label(tmp_path, capsys):
    _c, cap = run_record_report(tmp_path, two_model_rows(), capsys)
    rows = table_rows(cap.out, "Tokens per issue")
    assert "none" not in [r[0] for r in rows]
    measured = [r for r in rows if r[1:] == ["3,000", "300", "0", "0"]]
    assert len(measured) == 1, rows
    assert "orchestrator" in label_words(measured[0][0]) and "estimate" not in label_words(measured[0][0])
    assert "orchestrator (measured up to the run of the record writer; not complete)" in cap.out
    assert "up to the report" not in cap.out


def test_issue_and_project_rows_split_by_provider(tmp_path, capsys):
    _c, cap = run_record_report(tmp_path, two_model_rows(), capsys)
    issue = {r[0]: r[1:] for r in table_rows(cap.out, "Tokens per issue")}
    assert issue["#4 (claude)"] == ["100", "10", "40", "1,000"]
    assert issue["#4 (codex)"] == ["30", "3", "0", "20"]
    project = {r[0]: r[1:] for r in table_rows(cap.out, "Tokens per project")}
    assert project["o/a (claude)"] == ["3,100", "310", "40", "1,000"]
    assert project["o/a (codex)"] == ["30", "3", "0", "20"]


def test_weighted_table_says_estimate_not_added(tmp_path, capsys):
    _c, cap = run_record_report(tmp_path, two_model_rows(), capsys)
    part = " ".join(cap.out.split(f"## {WEIGHTED_TITLE}\n", 1)[1].split("\n## ", 1)[0].split())
    assert "estimate column is the orchestrator estimate line" in part
    assert "not added to the measured column" in part


def two_stage_rows():
    """Stages 3 and 9 of o/a (Claude lines in both, a Codex line in 9) and stage 3 of o/b."""
    return [
        rline("s3a", stage=3, issue=11, tok=(7, 3, 2, 90)),
        rline("s3b", stage=3, issue=12, role="qa", tok=(11, 1, 0, 30)),
        rline("s9a", stage=9, issue=21, tok=(13, 4, 8, 70)),
        rline("s9c", stage=9, issue=21, role="qa-codex", provider="codex", model="gpt", tok=(437, 9, 0, 301)),
        rline("s9o", stage=9, issue=None, role="orchestrator", tok=(50, 5, 0, 0)),
        rline("s9e", stage=9, issue=None, role="orchestrator", tok=(55, 6, 0, 0), estimate=True),
        rline("p3", project="o/b", stage=3, issue=31, tok=(17, 2, 0, 10)),
    ]


def test_weighted_total_per_stage_and_provider(tmp_path, capsys):
    rows = two_stage_rows()
    _c, cap = run_record_report(tmp_path, rows, capsys)
    got = {(r[0], r[1], r[2]): r[3:] for r in table_rows(cap.out, WEIGHTED_TITLE)}

    def total(project, stage, provider, estimate):
        return run_report._num(sum(run_report.weighted(ln, WEIGHTS) for ln in rows
                                   if ln["project"] == project and ln["stage"] == stage
                                   and ln["provider"] == provider and ln["estimate"] == estimate))

    keys = (("o/a", 3, "claude"), ("o/a", 9, "claude"), ("o/a", 9, "codex"), ("o/b", 3, "claude"))
    expected = {(p, str(s), pr): [total(p, s, pr, False), total(p, s, pr, True)] for p, s, pr in keys}
    assert got == expected
    # the same stage number in two projects gives two rows
    assert ("o/a", "3", "claude") in got and ("o/b", "3", "claude") in got
    assert got[("o/a", "3", "claude")] != got[("o/b", "3", "claude")]


def test_claude_and_codex_weighted_never_summed(tmp_path, capsys):
    rows = two_stage_rows()
    _c, cap = run_record_report(tmp_path, rows, capsys)
    claude = sum(run_report.weighted(ln, WEIGHTS) for ln in rows
                 if ln["stage"] == 9 and ln["provider"] == "claude" and not ln["estimate"])
    codex = sum(run_report.weighted(ln, WEIGHTS) for ln in rows if ln["stage"] == 9 and ln["provider"] == "codex")
    summed = run_report._num(claude + codex)
    cells = {c for r in table_rows(cap.out, WEIGHTED_TITLE) for c in r[3:]}
    assert run_report._num(claude) in cells and run_report._num(codex) in cells
    assert summed not in cap.out


def test_stage_help_names_both_modes(capsys):
    with pytest.raises(SystemExit):
        run_report.main(["--help"])
    text = " ".join(capsys.readouterr().out.split())
    stage_help = text.split("--stage STAGE")[-1].split("--issues", 1)[0]  # the options part, not the usage line
    assert "comments mode" in stage_help and "stage issue" in stage_help and "--record" in stage_help


def test_repo_weights_file_is_valid():
    w = run_report.load_weights(run_report.DEFAULT_WEIGHTS)
    assert w["claude"] == {"input": 1, "output": 5, "cache_creation": 1.25, "cache_read": 0.1}
    assert w["codex"]["cache_creation"] == 1 and "assumption" in w["note"]
