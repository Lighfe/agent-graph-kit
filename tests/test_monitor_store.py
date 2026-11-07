"""Tests for the monitor store loader `plugin/skills/monitor/store.py` (issue #282).

All data is synthetic (`tests/fakes/monitor/`). `gh` and the collectors are stubbed; no test uses
the network."""

import ast
import importlib.util
import json
import os
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
FIXTURES = ROOT / "tests" / "fakes" / "monitor"
FAKES = ROOT / "tests" / "fakes"
PROJECT = "example/proj"
OTHER = "example/other"


def load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = load("monitor_store_under_test", SKILL / "store.py")
TABLES = ("launches", "steps", "issues", "cases", "limits", "files")


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Env:
    """The paths of one test: a state dir with the input files, a repo folder, stubs for gh and the
    collectors, and the db."""

    def __init__(self, tmp, monkeypatch):
        self.state = tmp / "state"
        self.home = self.state / "agent-graph-kit"
        self.home.mkdir(parents=True)
        self.repo = tmp / "repo"
        self.repo.mkdir()
        self.record = self.home / "run-record.jsonl"
        self.steps = self.home / "steps.jsonl"
        self.cases = self.home / "retry-cases.jsonl"
        self.tags = self.home / "retry-tags.jsonl"
        self.limits = self.home / "run-record-limits.jsonl"
        self.runs = self.home / "codex-runs"
        self.db = self.home / "monitor.sqlite"
        self.config = self.home / "monitor-projects.json"
        for name in ("XDG_STATE_HOME",):
            monkeypatch.setenv(name, str(self.state))
        monkeypatch.setenv("RUN_RECORD_FILE", str(self.record))
        monkeypatch.setenv("STEPS_FILE", str(self.steps))
        monkeypatch.setenv("CODEX_RUNS_DIR", str(self.runs))
        for name in ("MONITOR_DB_FILE", "RUN_RECORD_LIMITS_FILE", "RUN_WEIGHTS_FILE"):
            monkeypatch.delenv(name, raising=False)
        self.commands = []
        self.failing = set()  # projects whose collectors fail
        self.gh_calls = []
        self.stages = {PROJECT: [(9, "Stage nine")]}
        self.subs = {(PROJECT, 9): [{"number": 1, "title": "Issue one", "state": "closed"},
                                    {"number": 2, "title": "Issue two", "state": "open"}]}
        self.gh_fail = set()
        monkeypatch.setattr(store, "run_command", self.run_command)
        monkeypatch.setattr(store, "gh", self.gh)

    def projects(self, *entries):
        self.config.write_text(json.dumps([{"project": p, "repo": str(self.repo)} for p in entries]))
        os.chmod(self.config, 0o600)

    def run_command(self, cmd, cwd=None):
        self.commands.append((cmd, cwd))
        project = cmd[cmd.index("--project") + 1]
        if project in self.failing:
            return 1, "synthetic collector failure"
        return 0, ""

    def gh(self, *args, cwd=None):
        self.gh_calls.append(args)
        if args[:2] == ("repo", "view"):
            if "repo" in self.gh_fail:
                raise RuntimeError("gh repo view failed")
            return "example/current\n"
        if args[:2] == ("issue", "list"):
            project = args[args.index("--repo") + 1]
            if project in self.gh_fail:
                raise RuntimeError("gh issue list failed")
            return json.dumps([{"number": n, "title": t} for n, t in self.stages.get(project, [])])
        if args[0] == "api":
            parts = args[1].split("/")
            project, stage = f"{parts[1]}/{parts[2]}", int(parts[4])
            return json.dumps(self.subs.get((project, stage), []))
        raise AssertionError(f"unexpected gh call {args}")

    def fill(self):
        shutil.copy(FIXTURES / "record.jsonl", self.record)
        shutil.copy(FIXTURES / "steps.jsonl", self.steps)
        shutil.copy(FIXTURES / "retry-cases.jsonl", self.cases)
        shutil.copy(FIXTURES / "retry-tags.jsonl", self.tags)
        shutil.copy(FIXTURES / "run-record-limits.jsonl", self.limits)

    def connect(self):
        return store.connect(self.db)

    def load(self, now=None, force=False):
        con = self.connect()
        try:
            return store.load_once(con, now=now, force_stage_read=force)
        finally:
            con.close()

    def rows(self, table, order="1"):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        finally:
            con.close()

    def query(self, sql, *params):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    e = Env(tmp_path, monkeypatch)
    e.projects(PROJECT)
    monkeypatch.chdir(e.repo)
    return e


def append(path, *rows):
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write((row if isinstance(row, str) else json.dumps(row)) + "\n")


def step(launch, seq, when, role="engineer", issue=1, **kw):
    row = {"v": 1, "id": f"{PROJECT}:{launch}:{seq}", "project": PROJECT, "stage": 9, "issue": issue,
           "role": role, "launch": launch, "seq": seq, "time": iso(when), "duration_s": 1.0,
           "model": None if role == "qa-codex" else "claude-fixture", "input_tokens": 10, "output_tokens": 1,
           "cache_creation_tokens": 0, "cache_read_tokens": 0, "context_tokens": 10, "tool": ["Bash"],
           "target": "ls", "result_chars": 1, "is_error": False, "kit_doc": None}
    row.update(kw)
    return row


def counts(env):
    return {t: len(env.rows(t)) for t in TABLES}


# --- script form ------------------------------------------------------------------------------

def test_store_imports_only_the_standard_library():
    tree = ast.parse((SKILL / "store.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names and names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)
    head = (SKILL / "store.py").read_text(encoding="utf-8").splitlines()[:4]
    assert head[0] == "#!/usr/bin/env -S uv run --script" and "# /// script" in head


def test_store_reuses_the_readers_of_the_sibling_scripts():
    text = (SKILL / "store.py").read_text(encoding="utf-8")
    for name in ("data.weighted", "data.launch_of", "data.load_tags", "data.steps_path", "data.cases_path",
                 "data.tags_path", "rr.record_path", "rr.limits_path", "st.codex_runs_dir", "data.load_weights"):
        assert name in text, name
    assert "def weighted" not in text and "def launch_of" not in text and "def load_tags" not in text


# --- output file, journal, log ----------------------------------------------------------------

def test_db_and_log_paths_modes_and_journal(env):
    env.fill()
    assert env.load()[0] == "ok"
    assert store.db_path() == env.db
    assert stat.S_IMODE(os.stat(env.db).st_mode) == 0o600
    log = env.home / "monitor-load.log"
    assert log.is_file() and stat.S_IMODE(os.stat(log).st_mode) == 0o600
    con = sqlite3.connect(env.db)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    con.close()
    assert not (env.home / "monitor.sqlite-wal").exists()


def test_db_path_follows_the_env_var(env, monkeypatch, tmp_path):
    monkeypatch.setenv("MONITOR_DB_FILE", str(tmp_path / "other" / "m.sqlite"))
    assert store.db_path() == tmp_path / "other" / "m.sqlite"
    assert store.log_path() == tmp_path / "other" / "monitor-load.log"


def test_existing_db_with_another_mode_gets_0600(env):
    env.db.write_bytes(b"")
    os.chmod(env.db, 0o644)
    env.load()
    assert stat.S_IMODE(os.stat(env.db).st_mode) == 0o600


def test_a_load_is_one_transaction(env, monkeypatch):
    env.fill()
    seen = []
    real = store.load_files

    def spy(con, entries):
        seen.append(con.in_transaction)
        result = real(con, entries)
        seen.append(con.in_transaction)
        return result

    monkeypatch.setattr(store, "load_files", spy)
    env.load()
    assert seen == [True, True]


# --- tables and view --------------------------------------------------------------------------

def test_tables_and_view_exist(env):
    env.load()
    found = {(r["type"], r["name"]) for r in env.query("SELECT type, name FROM sqlite_master")}
    for t in ("launches", "steps", "issues", "cases", "limits", "loads"):
        assert ("table", t) in found
    assert ("view", "active_launches") in found


def test_cases_hold_the_current_tag_note_and_escalation(env):
    env.fill()
    append(env.cases, {"id": f"{PROJECT}:4:1", "project": PROJECT, "stage": 9, "issue": 4, "round": 1,
                       "marker": "## PM: NEEDS OWNER", "tokens": {"claude": 5}})
    env.load()
    cases = {r["id"]: r for r in env.query("SELECT * FROM cases")}
    assert set(cases) == {f"{PROJECT}:1:1", f"{PROJECT}:2:1", f"{PROJECT}:3:1", f"{PROJECT}:4:1"}
    one = cases[f"{PROJECT}:1:1"]
    assert (one["tag"], one["note"], one["escalation"]) == ("test gap", "synthetic note", 0)
    # the last line of the case wins (1100)
    assert one["role"] == "QA" and one["tokens_claude"] == 1100 and one["tokens_codex"] == 200
    assert cases[f"{PROJECT}:2:1"]["tag"] == "" and cases[f"{PROJECT}:2:1"]["escalation"] == 0
    assert cases[f"{PROJECT}:4:1"]["escalation"] == 1


def test_a_new_tag_line_changes_the_case_row(env):
    env.fill()
    env.load()
    append(env.tags, {"case_id": f"{PROJECT}:2:1", "tag": "later tag", "note": "n", "time": "2026-11-04T12:00:00Z"})
    env.load()
    assert env.query("SELECT tag FROM cases WHERE id = ?", f"{PROJECT}:2:1")[0]["tag"] == "later tag"


def test_limits_are_loaded_and_marked_as_entered_by_hand(env):
    env.fill()
    env.load()
    rows = env.query("SELECT point, percent, plan, entered_by_hand FROM limits ORDER BY line")
    assert rows == [{"point": "start", "percent": 12.5, "plan": "fixture plan", "entered_by_hand": 1},
                    {"point": "end", "percent": 40, "plan": "fixture plan", "entered_by_hand": 1}]


# --- active launches --------------------------------------------------------------------------

def test_claude_launch_is_active_while_its_newest_step_is_at_most_5_minutes_old(env):
    now = datetime.now(timezone.utc)
    append(env.steps, step("live-1", 1, now - timedelta(hours=1)), step("live-1", 2, now - timedelta(minutes=1)),
           step("old-1", 1, now - timedelta(minutes=10)))
    env.load()
    active = env.query("SELECT * FROM active_launches")
    assert [r["launch"] for r in active] == ["live-1"]
    row = active[0]
    assert row["role"] == "engineer" and row["last_seq"] == 2 and row["steps"] == 2
    assert row["input_tokens"] == 20 and row["provider"] == "claude"
    assert 3500 < row["run_time_s"] < 3700


def test_active_launches_compare_with_the_time_of_the_query(env):
    now = datetime.now(timezone.utc)
    append(env.steps, step("live-1", 1, now - timedelta(minutes=4)))
    env.load()
    assert len(env.query("SELECT * FROM active_launches")) == 1
    # two minutes pass without a load: the view must use the query time, not the load time
    con = sqlite3.connect(env.db)
    con.execute("UPDATE steps SET time_s = time_s - 120")
    con.commit()
    con.close()
    assert env.query("SELECT * FROM active_launches") == []


def codex_attempt(env, start, mtime):
    """A Codex QA stream file and its step row, with the file modification time `mtime`."""
    env.runs.mkdir(exist_ok=True)
    launch = f"example__proj-1-{start.strftime('%Y%m%dT%H%M%S')}"
    path = env.runs / f"{launch}.jsonl"
    path.write_text('{"type": "turn.completed"}\n')
    os.utime(path, (mtime.timestamp(), mtime.timestamp()))
    append(env.steps, step(launch, 1, start, role="qa-codex"))
    return launch


def test_codex_attempt_with_a_fresh_stream_file_is_active(env):
    now = datetime.now(timezone.utc)
    launch = codex_attempt(env, now - timedelta(hours=1), now - timedelta(minutes=1))
    env.load()
    active = env.query("SELECT * FROM active_launches")
    assert [(r["launch"], r["provider"], r["role"]) for r in active] == [(launch, "codex", "qa-codex")]


def test_codex_attempt_with_an_old_stream_file_is_not_active(env):
    now = datetime.now(timezone.utc)
    codex_attempt(env, now - timedelta(hours=1), now - timedelta(minutes=10))
    env.load()
    assert env.query("SELECT * FROM active_launches") == []


def test_stream_file_time_is_stored_again_when_the_file_changes(env):
    now = datetime.now(timezone.utc)
    launch = codex_attempt(env, now - timedelta(hours=1), now - timedelta(minutes=10))
    env.load()
    assert env.query("SELECT * FROM active_launches") == []
    path = env.runs / f"{launch}.jsonl"
    os.utime(path, (now.timestamp(), now.timestamp()))
    env.load()
    assert [r["launch"] for r in env.query("SELECT * FROM active_launches")] == [launch]


# --- weighted tokens --------------------------------------------------------------------------

def codex_line(**kw):
    line = {"v": 1, "id": f"{PROJECT}:codex:1:2026-11-04T09:22:00Z", "project": PROJECT, "stage": 9, "issue": 1,
            "role": "qa-codex", "provider": "codex", "model": "codex-fixture", "effort": None,
            "input_tokens": 100, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 80,
            "start": "2026-11-04T09:22:00Z", "end": "2026-11-04T09:22:00Z", "retry": 0, "estimate": False,
            "source": "codex-record"}
    line.update(kw)
    return line


def test_codex_line_weighted_with_the_skill_weights_is_28(env):
    append(env.record, codex_line())
    env.load()
    row = env.query("SELECT weighted, weighted_is_estimate, provider FROM launches")[0]
    assert row == {"weighted": 28, "weighted_is_estimate": 1, "provider": "codex"}


def test_weights_come_from_the_project_repo(env):
    (env.repo / "docs").mkdir()
    (env.repo / "docs" / "run-weights.json").write_text(json.dumps({"codex": {"input": 2, "cache_read": 1}}))
    append(env.record, codex_line())
    env.load()
    assert env.query("SELECT weighted FROM launches")[0]["weighted"] == 2 * 20 + 80


def test_no_provider_line_has_no_weighted_value_and_no_column_adds_providers(env):
    env.fill()
    env.load()
    rows = {r["id"]: r for r in env.query("SELECT * FROM launches")}
    issue = rows[f"{PROJECT}:issue:1"]
    assert issue["weighted"] is None and issue["weighted_is_estimate"] is None
    claude = rows[f"{PROJECT}:fixture-eng-1:claude-fixture"]
    # 1000*1 + 100*5 + 2000*1.25 + 10000*0.1 with the skill weights; nothing of Codex is in it
    assert claude["weighted"] == 1000 + 500 + 2500 + 1000
    codex = rows[f"{PROJECT}:codex:1:2026-11-04T09:22:00Z"]
    assert codex["weighted"] == 100 * 1 + 40 * 5 + 300 * 0.1
    for name in TABLES + ("loads", "active_launches"):
        cols = [r["name"] for r in env.query(f"PRAGMA table_info({name})")]
        assert not any("total" in c or ("claude" in c and "codex" in c) for c in cols), (name, cols)


def test_active_launches_never_mix_providers(env):
    now = datetime.now(timezone.utc)
    append(env.steps, step("shared", 1, now - timedelta(minutes=1)),
           step("shared", 2, now - timedelta(minutes=1), role="qa-codex"))
    (env.runs).mkdir(exist_ok=True)
    (env.runs / "shared.jsonl").write_text("{}\n")
    env.load()
    rows = env.query("SELECT provider, steps FROM active_launches ORDER BY provider")
    assert rows == [{"provider": "claude", "steps": 1}, {"provider": "codex", "steps": 1}]


def test_steps_carry_weighted_estimates(env):
    append(env.steps, step("w-1", 1, datetime(2026, 11, 4, tzinfo=timezone.utc), input_tokens=100,
                           cache_read_tokens=80, output_tokens=0, role="qa-codex"))
    env.load()
    assert env.query("SELECT weighted, weighted_is_estimate FROM steps")[0] == {"weighted": 28, "weighted_is_estimate": 1}


def test_codex_record_line_joins_its_stream_launch(env):
    env.fill()
    launch = "example__proj-1-20261104T092000"
    append(env.steps, step(launch, 1, datetime(2026, 11, 4, 9, 20, tzinfo=timezone.utc), role="qa-codex"))
    env.load()
    row = env.query("SELECT launch FROM launches WHERE provider = 'codex'")[0]
    assert row["launch"] == launch
    claude = env.query("SELECT launch FROM launches WHERE id = ?", f"{PROJECT}:fixture-eng-1:claude-fixture")[0]
    assert claude["launch"] == "fixture-eng-1"


# --- incremental loads ------------------------------------------------------------------------

def test_second_load_on_unchanged_files_adds_no_rows(env):
    env.fill()
    env.load()
    before = {t: env.rows(t) for t in TABLES}
    loads = len(env.rows("loads"))
    status, message = env.load()
    assert status == "ok" and message == "no change"
    assert {t: env.rows(t) for t in TABLES} == before
    assert len(env.rows("loads")) == loads + 1


def test_later_record_line_with_a_known_id_replaces_the_row(env):
    env.fill()
    env.load()
    n = len(env.rows("launches"))
    append(env.record, codex_line(input_tokens=1000, cache_read_tokens=0, output_tokens=0))
    env.load()
    rows = env.query("SELECT input_tokens, weighted FROM launches WHERE id = ?", codex_line()["id"])
    assert rows == [{"input_tokens": 1000, "weighted": 1000}]
    assert len(env.rows("launches")) == n


def test_only_new_bytes_are_read(env, monkeypatch):
    env.fill()
    env.load()
    offsets = []
    real = store.complete_lines
    monkeypatch.setattr(store, "complete_lines", lambda p, o: (offsets.append((Path(p).name, o)), real(p, o))[1])
    append(env.record, codex_line(id="x:new"))
    env.load()
    assert offsets == [("run-record.jsonl", os.path.getsize(env.record) - len(json.dumps(codex_line(id="x:new"))) - 1)]


def test_rewritten_case_file_gives_exactly_its_rows(env):
    env.fill()
    env.load()
    assert len(env.rows("cases")) == 3
    lines = [json.loads(line) for line in FIXTURES.joinpath("retry-cases.jsonl").read_text().splitlines()
             if line.startswith("{")]
    # shorter, other order (issue 3 first, then issue 2), written as cases.py does: temp file and rename
    assert [r["issue"] for r in lines[1:3]] == [2, 3]
    tmp = env.cases.with_name("tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in [lines[2], lines[1]]))
    os.replace(tmp, env.cases)
    env.load()
    assert sorted(r[0] for r in env.rows("cases")) == [f"{PROJECT}:2:1", f"{PROJECT}:3:1"]


def test_shorter_record_file_is_read_again_from_the_start(env):
    env.fill()
    env.load()
    env.record.write_text(json.dumps(codex_line()) + "\n")
    env.load()
    assert [r[0] for r in env.rows("launches")] == [codex_line()["id"]]


def test_cut_last_line_is_skipped_and_loaded_once_when_complete(env):
    full = json.dumps(codex_line())
    env.record.write_text(full[:40])
    env.load()
    assert env.rows("launches") == []
    with open(env.record, "a") as f:
        f.write(full[40:] + "\n")
    env.load()
    assert len(env.rows("launches")) == 1
    env.load()
    assert len(env.rows("launches")) == 1


def test_cut_last_step_line_is_skipped(env):
    row = json.dumps(step("cut", 1, datetime(2026, 11, 4, tzinfo=timezone.utc)))
    env.steps.write_text(row + "\n" + row.replace(":cut:1", ":cut:2")[:30])
    env.load()
    assert [r[0] for r in env.rows("steps")] == [f"{PROJECT}:cut:1"]


def test_cut_last_tag_line_is_skipped_and_loaded_once_when_complete(env):
    env.fill()
    env.load()
    line = json.dumps({"case_id": f"{PROJECT}:2:1", "tag": "cut tag", "note": "", "time": "2026-11-04T12:00:00Z"})
    before = env.rows("cases")
    with open(env.tags, "a") as f:
        f.write(line[:25])
    env.load()
    assert env.rows("cases") == before
    with open(env.tags, "a") as f:
        f.write(line[25:] + "\n")
    env.load()
    assert env.query("SELECT tag FROM cases WHERE id = ?", f"{PROJECT}:2:1")[0]["tag"] == "cut tag"


def test_tag_line_of_valid_json_without_a_newline_is_skipped(env):
    env.fill()
    line = json.dumps({"case_id": f"{PROJECT}:2:1", "tag": "no newline", "note": "", "time": "2026-11-04T12:00:00Z"})
    with open(env.tags, "a") as f:
        f.write(line)
    env.load()
    assert env.query("SELECT tag FROM cases WHERE id = ?", f"{PROJECT}:2:1")[0]["tag"] != "no newline"
    with open(env.tags, "a") as f:
        f.write("\n")
    env.load()
    assert env.query("SELECT tag FROM cases WHERE id = ?", f"{PROJECT}:2:1")[0]["tag"] == "no newline"


def case_lines():
    return [line for line in FIXTURES.joinpath("retry-cases.jsonl").read_text().splitlines() if line.startswith("{")]


def test_case_line_without_a_newline_is_skipped_and_loaded_once_when_complete(env):
    lines = case_lines()
    env.cases.write_text("\n".join(lines[:2]) + "\n" + lines[2])  # the last line is valid JSON, no newline
    env.load()
    assert sorted(r[0] for r in env.rows("cases")) == sorted(json.loads(x)["id"] for x in lines[:2])
    with open(env.cases, "a") as f:
        f.write("\n")
    env.load()
    assert sorted(r[0] for r in env.rows("cases")) == sorted(json.loads(x)["id"] for x in lines[:3])
    env.load()
    assert len(env.rows("cases")) == 3


def test_cut_case_line_is_skipped(env):
    lines = case_lines()
    env.cases.write_text(lines[0] + "\n" + lines[1][:30])
    env.load()
    assert [r[0] for r in env.rows("cases")] == [json.loads(lines[0])["id"]]


# --- rebuild ----------------------------------------------------------------------------------

def test_rebuild_after_delete_gives_the_same_rows_as_incremental_loads(env):
    now = datetime.now(timezone.utc)
    env.fill()
    codex_attempt(env, now - timedelta(hours=1), now - timedelta(minutes=1))
    env.load(force=True)
    append(env.record, codex_line(input_tokens=500))
    append(env.steps, step("later", 1, now))
    append(env.limits, {"project": PROJECT, "stage": 9, "time": iso(now), "point": "end", "percent": 50, "plan": "p"})
    append(env.tags, {"case_id": f"{PROJECT}:3:1", "tag": "t", "note": "", "time": iso(now)})
    env.load()
    order = {"issues": "project, issue", "limits": "line"}
    incremental = {t: env.rows(t, order.get(t, "1")) for t in TABLES}
    active = env.query("SELECT project, launch, provider FROM active_launches ORDER BY launch")
    env.db.unlink()
    assert store.main(["rebuild"]) == 0
    assert {t: env.rows(t, order.get(t, "1")) for t in TABLES} == incremental
    assert env.query("SELECT project, launch, provider FROM active_launches ORDER BY launch") == active
    assert all(incremental[t] for t in TABLES), "every table has rows in this test"


def test_rebuild_with_cut_last_lines_gives_the_same_rows_as_incremental_loads(env):
    env.fill()
    env.load(force=True)
    for path in (env.record, env.steps, env.limits, env.tags):
        with open(path, "a") as f:
            f.write('{"id": "cut", "case_id": "cut"')
    with open(env.cases, "a") as f:
        f.write(case_lines()[0].replace(":1:1", ":77:1"))  # valid JSON without a newline
    env.load()
    order = {"issues": "project, issue", "limits": "line"}
    incremental = {t: env.rows(t, order.get(t, "1")) for t in TABLES}
    assert len(incremental["cases"]) == 3 and all(incremental[t] for t in TABLES)
    env.db.unlink()
    assert store.main(["rebuild"]) == 0
    assert {t: env.rows(t, order.get(t, "1")) for t in TABLES} == incremental


def test_rebuild_replaces_an_existing_db(env):
    env.fill()
    env.load()
    con = sqlite3.connect(env.db)
    con.execute("DELETE FROM launches")
    con.commit()
    con.close()
    assert store.main(["rebuild"]) == 0
    assert len(env.rows("launches")) == 6
    assert len(env.rows("loads")) == 1


# --- missing files ----------------------------------------------------------------------------

def test_missing_input_files_give_empty_tables(env):
    status, _ = env.load()
    assert status == "ok"
    for t in ("launches", "steps", "cases", "limits"):
        assert env.rows(t) == [], t


def test_empty_input_files_give_empty_tables(env):
    for p in (env.record, env.steps, env.cases, env.tags, env.limits):
        p.write_text("")
    env.runs.mkdir()
    status, _ = env.load()
    assert status == "ok"
    for t in ("launches", "steps", "cases", "limits"):
        assert env.rows(t) == [], t


def test_a_deleted_input_file_empties_its_table(env):
    env.fill()
    env.load()
    env.steps.unlink()
    env.load()
    assert env.rows("steps") == [] and env.rows("launches")


# --- loads table and errors -------------------------------------------------------------------

def input_bytes(env):
    return {p.name: p.read_bytes() for p in env.home.rglob("*")
            if p.is_file() and not p.name.startswith("monitor")}


def test_each_load_writes_an_ok_row(env):
    env.fill()
    env.load()
    env.load()
    rows = env.query("SELECT time, status, message FROM loads ORDER BY id")
    assert [r["status"] for r in rows] == ["ok", "ok"]
    assert all(r["time"].endswith("Z") and r["message"] for r in rows)


def test_load_error_writes_a_failed_row_exits_non_zero_and_changes_no_input(env, monkeypatch):
    env.fill()
    store.main(["load", "--once"])
    before = input_bytes(env)
    rows_before = {t: env.rows(t) for t in TABLES}
    env.record.unlink()
    env.record.mkdir()  # a folder where the run record should be: reading it fails
    (env.record / "keep").write_text("x")
    before = input_bytes(env)
    assert store.main(["load", "--once"]) == 1
    last = env.query("SELECT status, message FROM loads ORDER BY id DESC LIMIT 1")[0]
    assert last["status"] == "failed" and "IsADirectoryError" in last["message"]
    assert input_bytes(env) == before
    assert {t: env.rows(t) for t in TABLES} == rows_before  # the failed load was rolled back
    assert "failed" in (env.home / "monitor-load.log").read_text()


@pytest.mark.parametrize("name", ["retry-cases.jsonl", "retry-tags.jsonl", "steps.jsonl", "run-record-limits.jsonl"])
def test_an_input_that_cannot_be_read_fails_the_load(env, name):
    env.fill()
    assert store.main(["load", "--once"]) == 0
    rows_before = {t: env.rows(t) for t in TABLES}
    path = env.home / name
    path.unlink()
    path.mkdir()  # a folder where the file should be: reading it fails
    before = input_bytes(env)
    assert store.main(["load", "--once"]) == 1
    last = env.query("SELECT status, message FROM loads ORDER BY id DESC LIMIT 1")[0]
    assert last["status"] == "failed" and "IsADirectoryError" in last["message"], last
    assert input_bytes(env) == before
    assert {t: env.rows(t) for t in TABLES} == rows_before


def test_failing_collector_of_one_project_does_not_stop_the_others(env):
    env.projects(OTHER, PROJECT)
    env.failing = {OTHER}
    env.stages[OTHER] = [(5, "Other stage")]
    env.subs[(OTHER, 5)] = [{"number": 7, "title": "Other issue", "state": "open"}]
    env.fill()
    status, message = env.load()
    assert status == "failed" and OTHER in message and PROJECT not in message.replace(OTHER, "")
    steps_runs = [c for c, _ in env.commands if "steps.py" in c[1]]
    assert [c[c.index("--project") + 1] for c in steps_runs] == [OTHER, PROJECT]
    assert len(env.rows("launches")) == 6
    assert {(r[0], r[2]) for r in env.rows("issues")} == {(PROJECT, 1), (PROJECT, 2), (OTHER, 7)}


def test_failing_stage_read_of_one_project_keeps_its_old_issues(env):
    env.projects(OTHER, PROJECT)
    env.stages[OTHER] = [(5, "Other stage")]
    env.subs[(OTHER, 5)] = [{"number": 7, "title": "Other issue", "state": "open"}]
    t0 = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    env.load(now=t0)
    env.gh_fail = {OTHER}
    env.subs[(PROJECT, 9)] = [{"number": 3, "title": "Issue three", "state": "open"}]
    status, message = env.load(now=t0 + timedelta(minutes=6))
    assert status == "failed" and OTHER in message
    assert {(r[0], r[2]) for r in env.rows("issues")} == {(PROJECT, 3), (OTHER, 7)}


# --- projects file ----------------------------------------------------------------------------

def test_missing_projects_file_is_written_with_the_current_project(env):
    env.config.unlink()
    env.load()
    assert json.loads(env.config.read_text()) == [{"project": "example/current", "repo": str(env.repo)}]
    assert stat.S_IMODE(os.stat(env.config).st_mode) == 0o600
    assert env.commands[0] == (store.data.collect_command("example/current"), str(env.repo))
    calls = len([c for c in env.gh_calls if c[:2] == ("repo", "view")])
    env.load()
    assert len([c for c in env.gh_calls if c[:2] == ("repo", "view")]) == calls == 1


def test_projects_file_that_exists_is_not_written(env):
    before = env.config.read_bytes()
    mtime = os.stat(env.config).st_mtime_ns
    env.load()
    assert env.config.read_bytes() == before and os.stat(env.config).st_mtime_ns == mtime
    assert not [c for c in env.gh_calls if c[:2] == ("repo", "view")]


def test_failing_repo_view_writes_no_projects_file(env):
    env.config.unlink()
    env.gh_fail = {"repo"}
    env.fill()
    status, message = env.load()
    assert status == "failed" and "no projects" in message
    assert not env.config.exists() and len(env.rows("launches")) == 6


# --- collectors and stage reads ---------------------------------------------------------------

def test_each_load_runs_the_step_collector_in_the_repo_folder(env):
    env.load()
    env.load()
    steps_runs = [(c, cwd) for c, cwd in env.commands if "steps.py" in c[1]]
    assert steps_runs == [(store.data.collect_command(PROJECT), str(env.repo))] * 2
    assert steps_runs[0][0][1:] == [str(SKILL / "steps.py"), "collect", "--project", PROJECT]


def test_cases_collect_and_issue_reads_run_at_most_every_5_minutes(env):
    t0 = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    env.load(now=t0)
    case_runs = [(c, cwd) for c, cwd in env.commands if "cases.py" in c[1]]
    assert case_runs == [(store.data.cases_collect_command(PROJECT, 9), str(env.repo))]
    assert case_runs[0][0][1:] == [str(SKILL / "cases.py"), "collect", "--project", PROJECT,
                                   "--repo-slug", PROJECT, "--stage", "9"]
    assert env.query("SELECT project, stage, issue, title, state FROM issues ORDER BY issue") == [
        {"project": PROJECT, "stage": 9, "issue": 1, "title": "Issue one", "state": "closed"},
        {"project": PROJECT, "stage": 9, "issue": 2, "title": "Issue two", "state": "open"}]
    env.subs[(PROJECT, 9)] = [{"number": 3, "title": "Issue three", "state": "open"}]
    env.load(now=t0 + timedelta(minutes=4))
    assert len([c for c, _ in env.commands if "cases.py" in c[1]]) == 1
    assert [r[2] for r in env.rows("issues", "issue")] == [1, 2]  # the last result is kept
    env.load(now=t0 + timedelta(minutes=5))
    assert len([c for c, _ in env.commands if "cases.py" in c[1]]) == 2
    assert [r[2] for r in env.rows("issues", "issue")] == [3]


def test_gh_calls_are_reads_only(env):
    env.config.unlink()
    env.load()
    for args in env.gh_calls:
        assert args[:2] in {("repo", "view"), ("issue", "list")} or (args[0] == "api" and "-X" not in args), args
    listing = [a for a in env.gh_calls if a[:2] == ("issue", "list")][0]
    assert "--label" in listing and listing[listing.index("--label") + 1] == "stage"
    assert listing[listing.index("--state") + 1] == "open"


def test_project_without_open_stage_gets_no_issue_rows_and_no_cases_collect(env):
    env.stages[PROJECT] = []
    env.load()
    assert env.rows("issues") == []
    assert not [c for c, _ in env.commands if "cases.py" in c[1]]


def test_loader_writes_only_its_own_files(env):
    env.fill()
    before = input_bytes(env)
    env.load()
    env.load()
    assert input_bytes(env) == before
    assert {p.name for p in env.home.iterdir() if p.name.startswith("monitor")} == {
        "monitor.sqlite", "monitor-load.log", "monitor-projects.json"}


# --- the loop as a process --------------------------------------------------------------------

def proc_env(tmp_path):
    state = tmp_path / "state"
    (state / "agent-graph-kit").mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    (state / "agent-graph-kit" / "monitor-projects.json").write_text(
        json.dumps([{"project": PROJECT, "repo": str(repo)}]))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MONITOR_", "RUN_RECORD", "RUN_WEIGHTS"))}
    env.update({"XDG_STATE_HOME": str(state), "HOME": str(tmp_path), "STEPS_FILE": str(state / "steps.jsonl"),
                "CODEX_RUNS_DIR": str(state / "runs"), "PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}",
                "FAKE_GH_FAIL": "1"})
    return env, repo, state / "agent-graph-kit" / "monitor.sqlite"


def wait_for_load(db, proc):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        assert proc.poll() is None, proc.communicate()
        if db.exists():
            try:
                con = sqlite3.connect(db)
                n = con.execute("SELECT COUNT(*) FROM loads").fetchone()[0]
                con.close()
                if n:
                    return
            except sqlite3.Error:
                pass
        time.sleep(0.2)
    raise AssertionError("no load row within 60 s")


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_load_loop_ends_with_exit_0_and_no_traceback_on_a_signal(tmp_path, sig):
    env, repo, db = proc_env(tmp_path)
    proc = subprocess.Popen([sys.executable, str(SKILL / "store.py"), "load"], cwd=repo, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for_load(db, proc)
        proc.send_signal(sig)
        out, err = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, (out, err)
    assert "Traceback" not in out + err
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM loads").fetchone()[0] == 1
    con.close()


def test_load_once_as_a_process(tmp_path):
    env, repo, db = proc_env(tmp_path)
    res = subprocess.run([sys.executable, str(SKILL / "store.py"), "load", "--once"], cwd=repo, env=env,
                         capture_output=True, text=True, timeout=120)
    # the fake gh fails every call, so the stage read fails and the load is marked failed
    assert res.returncode == 1, res.stdout + res.stderr
    assert "Traceback" not in res.stdout + res.stderr
    con = sqlite3.connect(db)
    status, message = con.execute("SELECT status, message FROM loads").fetchone()
    con.close()
    assert status == "failed" and "stage read" in message


# --- skill doc --------------------------------------------------------------------------------

def test_skill_has_a_store_section_with_commands_tables_rule_config_and_log():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "\n## Store\n" in text
    section = text.split("\n## Store\n", 1)[1].split("\n## ", 1)[0]
    for needed in ("store.py\" load ", "load --once", "rebuild", "monitor-projects.json", "monitor-load.log",
                   "MONITOR_DB_FILE", "0600", "at most 5 minutes old", "time of the query",
                   "`launches`", "`steps`", "`issues`", "`cases`", "`limits`", "`loads`", "`active_launches`",
                   "`escalation`", "`weighted_is_estimate`"):
        assert needed in section, needed
