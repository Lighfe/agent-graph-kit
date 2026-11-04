"""Tests for the notebook data layer `plugin/skills/monitor/data.py` and the notebook file
`explore.py` (issue #265). All rows are synthetic (`tests/fakes/monitor/`)."""

import ast
import importlib.util
import json
import py_compile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
FIXTURES = ROOT / "tests" / "fakes" / "monitor"
RECORD = FIXTURES / "record.jsonl"
STEPS = FIXTURES / "steps.jsonl"


def load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


data = load("monitor_data_under_test", SKILL / "data.py")


def by_key(rows, *keys):
    return {tuple(r[k] for k in keys): r for r in rows}


# --- standard library only --------------------------------------------------------------------

def test_data_imports_only_the_standard_library():
    import sys
    tree = ast.parse((SKILL / "data.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names, "no imports found"
    assert names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


def test_notebook_compiles():
    py_compile.compile(str(SKILL / "explore.py"), doraise=True, cfile=None)


# --- loaders ----------------------------------------------------------------------------------

def test_record_last_line_per_id():
    record = data.load_record(RECORD)
    ids = [r["id"] for r in record]
    assert len(ids) == len(set(ids))
    eng = [r for r in record if r["id"] == "example/proj:fixture-eng-1:claude-fixture"]
    assert len(eng) == 1 and eng[0]["input_tokens"] == 1000 and eng[0]["end"].startswith("2026-11-04T09:10")


def test_line_that_is_not_json_is_skipped():
    assert len(data.load_record(RECORD)) == 6
    assert len(data.load_steps(STEPS)) == 5


def test_missing_files_give_empty_results(tmp_path, monkeypatch):
    monkeypatch.setenv("STEPS_FILE", str(tmp_path / "no-steps.jsonl"))
    monkeypatch.setenv("RUN_RECORD_FILE", str(tmp_path / "no-record.jsonl"))
    steps, record = data.load_steps(), data.load_record()
    assert steps == [] and record == []
    assert data.totals(record, ["role"]) == []
    assert data.launch_steps(steps, "fixture-eng-1") == []
    assert data.kit_doc_reads(steps, ["role"]) == []
    assert data.running(steps, datetime.now(timezone.utc)) == []


def test_loaders_follow_the_env_vars(monkeypatch):
    monkeypatch.setenv("STEPS_FILE", str(STEPS))
    monkeypatch.setenv("RUN_RECORD_FILE", str(RECORD))
    assert len(data.load_steps()) == 5 and len(data.load_record()) == 6


# --- totals -----------------------------------------------------------------------------------

def test_totals_by_role():
    rows = by_key(data.totals(data.load_record(RECORD), ["role"]), "role", "estimate")
    eng = rows[("engineer", False)]
    assert eng["lines"] == 2
    assert eng["input_tokens"] == 1500 and eng["output_tokens"] == 150
    assert eng["cache_creation_tokens"] == 2000 and eng["cache_read_tokens"] == 10000
    assert eng["seconds"] == 600 + 120  # end minus start, per line
    assert rows[("pm", False)]["seconds"] == 300
    assert rows[("qa-codex", False)]["input_tokens"] == 400


def test_estimate_lines_are_shown_apart():
    rows = data.totals(data.load_record(RECORD), ["project"])
    assert {r["estimate"] for r in rows} == {False, True}
    est = [r for r in rows if r["estimate"]][0]
    assert est["lines"] == 1 and est["input_tokens"] == 50


def test_weighted_totals_per_provider():
    weights = {"claude": {"input": 1, "output": 5, "cache_creation": 1.25, "cache_read": 0.1},
               "codex": {"input": 2, "output": 10, "cache_creation": 1, "cache_read": 0.5}}
    record = [r for r in data.load_record(RECORD) if not r["estimate"]]
    rows = data.totals(record, ["issue"], weights)
    one = by_key(rows, "issue")[(1,)]
    # issue 1: engineer + pm (claude), qa-codex (codex), the issue line (provider null)
    claude = (1000 + 100) * 1 + (100 + 10) * 5 + (2000 + 200) * 1.25 + (10000 + 1000) * 0.1
    codex = 400 * 2 + 40 * 10 + 300 * 0.5
    assert one["weighted"] == {"claude": claude, "codex": codex}
    assert data.WEIGHT_LABEL == "estimate from price ratios, not measured plan use"


def test_provider_null_lines_get_no_weighted_total():
    weights = data.load_weights(path=SKILL / "run-weights.json")
    issue_line = [r for r in data.load_record(RECORD) if r["role"] == "issue"]
    rows = data.totals(issue_line, ["role"], weights)
    assert rows[0]["weighted"] == {} and rows[0]["seconds"] == 40 * 60


def test_totals_filter():
    record = data.load_record(RECORD)
    picked = data.select(record, {"role": "engineer", "issue": 2})
    assert [r["id"] for r in picked] == ["example/proj:fixture-eng-2:claude-fixture"]
    assert len(data.select(record, {"role": None, "issue": 1})) == 4


# --- weights ----------------------------------------------------------------------------------

def test_skill_weights_copy_matches_docs():
    skill = json.loads((SKILL / "run-weights.json").read_text(encoding="utf-8"))
    docs = json.loads((ROOT / "docs" / "run-weights.json").read_text(encoding="utf-8"))
    assert skill == docs


def test_weights_order(tmp_path, monkeypatch):
    own = tmp_path / "own.json"
    own.write_text(json.dumps({"claude": {"input": 9}}), encoding="utf-8")
    project = tmp_path / "proj"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "run-weights.json").write_text(json.dumps({"claude": {"input": 7}}), encoding="utf-8")
    monkeypatch.setenv("RUN_WEIGHTS_FILE", str(own))
    assert data.weights_path(project) == own
    monkeypatch.delenv("RUN_WEIGHTS_FILE")
    assert data.weights_path(project) == project / "docs" / "run-weights.json"
    assert data.weights_path(tmp_path / "empty") == SKILL / "run-weights.json"
    assert data.load_weights(project_root=project) == {"claude": {"input": 7}}


# --- drill-down -------------------------------------------------------------------------------

def test_launch_of_record_line():
    record = {r["id"]: r for r in data.load_record(RECORD)}
    assert data.launch_of(record["example/proj:fixture-eng-1:claude-fixture"]) == "fixture-eng-1"
    assert data.launch_of(record["example/proj:codex:1:2026-11-04T09:20:00Z"]) == "example__proj-1-20261104T092000"


def test_launches_of_a_total():
    rows = data.launches(data.load_record(RECORD), {"role": "engineer"})
    assert [r["launch"] for r in rows] == ["fixture-eng-1", "fixture-eng-2"]
    assert rows[0]["seconds"] == 600


def test_launch_steps_in_seq_order():
    rows = data.launch_steps(data.load_steps(STEPS), "fixture-eng-1")
    assert [r["seq"] for r in rows] == [1, 2, 3]
    assert [r["context_tokens"] for r in rows] == [110, 165, 170]


def test_launch_without_steps_gives_empty_table():
    assert data.launch_steps(data.load_steps(STEPS), "fixture-eng-2") == []


def test_kit_doc_reads_per_launch_and_role():
    steps = data.load_steps(STEPS)
    per_role = by_key(data.kit_doc_reads(steps, ["role"]), "role", "kit_doc")
    assert per_role[("engineer", "/example/repo/docs/process.md")]["reads"] == 1
    assert per_role[("pm", "/example/repo/docs/process.md")]["reads"] == 1
    assert len(per_role) == 3
    per_launch = data.kit_doc_reads(steps, ["launch"])
    assert sum(r["reads"] for r in per_launch if r["launch"] == "fixture-eng-1") == 2


# --- running stage ----------------------------------------------------------------------------

def step(launch, seq, t, **extra):
    row = {"id": f"p:{launch}:{seq}", "project": "p", "stage": 5, "issue": 3, "role": "engineer",
           "launch": launch, "seq": seq, "time": t.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
           "duration_s": 1.0, "input_tokens": 1, "output_tokens": 2, "cache_creation_tokens": 3,
           "cache_read_tokens": 4, "context_tokens": 10, "tool": ["Read"], "target": f"f{seq}",
           "kit_doc": None}
    row.update(extra)
    return row


def test_running_marks_recent_launch_active():
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    steps = [step("recent", 1, now - timedelta(minutes=30)), step("recent", 2, now - timedelta(minutes=2)),
             step("old", 1, now - timedelta(minutes=40)), step("old", 2, now - timedelta(minutes=20)),
             step("other-stage", 1, now - timedelta(minutes=1), stage=6)]
    rows = {r["launch"]: r for r in data.running(steps, now, stage=5)}
    assert set(rows) == {"recent", "old"}
    assert rows["recent"]["active"] is True and rows["old"]["active"] is False
    recent = rows["recent"]
    assert recent["start"] == "2026-11-04T11:30:00.000Z"
    assert recent["run_time_s"] == 28 * 60
    assert recent["tokens"] == 2 * (1 + 2 + 3 + 4)
    assert recent["last_seq"] == 2 and recent["last_target"] == "f2"
    assert recent["role"] == "engineer" and recent["issue"] == 3


def test_running_last_step_is_highest_seq():
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    t = now - timedelta(minutes=1)
    steps = [step("a", 3, t, target="third"), step("a", 1, t, target="first")]
    assert data.running(steps, now)[0]["last_target"] == "third"


def test_running_on_fixtures():
    now = datetime(2026, 11, 4, 9, 22, tzinfo=timezone.utc)
    rows = {r["launch"]: r for r in data.running(data.load_steps(STEPS), now, stage=9)}
    assert rows["example__proj-1-20261104T092000"]["active"] is True
    assert rows["fixture-eng-1"]["active"] is False


# --- refresh ----------------------------------------------------------------------------------

def test_collect_command():
    cmd = data.collect_command("example/proj")
    assert cmd[-4:] == [str(SKILL / "steps.py"), "collect", "--project", "example/proj"]


# --- no verdict -------------------------------------------------------------------------------

def test_notebook_has_no_verdict_words():
    text = (SKILL / "explore.py").read_text(encoding="utf-8").lower()
    for word in ("recommend", "verdict", "should ", "too many", "too much", "waste", "inefficient"):
        assert word not in text, word


def test_launches_of_a_group_with_null_issue():
    record = data.load_record(RECORD)
    rows = data.launches(record, {}, {"issue": None, "estimate": True})
    assert [r["role"] for r in rows] == ["orchestrator"]
    assert data.launches(record, {}, {"issue": None, "estimate": False}) == []
