"""Tests for the Grafana board files of the monitor skill (issue #284): every query of every board
in `plugin/skills/monitor/grafana/boards/` runs on a db that `store.py rebuild` made from synthetic
fixtures, and the live board `live.json` has the panels of the spec (Part D, "Live board").

No test needs Grafana, Docker or the network: `gh` and the collectors are stubbed. All data is
synthetic (`tests/fakes/monitor/live/`); its times are written relative to the time of the test,
since the view `active_launches` only lists launches with a step at most 5 minutes old."""

import importlib.util
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
BOARDS = SKILL / "grafana" / "boards"
LIVE = BOARDS / "live.json"
FIXTURES = ROOT / "tests" / "fakes" / "monitor" / "live"
PROJECT = "example/proj"
OTHER = "example/other"
CODEX_ROLE = "qa-" + "codex"
STAGE_TITLES = {1: "Fixture issue one", 2: "Fixture issue two"}


def load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = load("monitor_store_for_boards_tests", SKILL / "store.py")


# --- board files ------------------------------------------------------------------------------

def board_files():
    files = sorted(BOARDS.glob("*.json"))
    assert files
    return files


def read_board(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def board_variables(board):
    return (board.get("templating") or {}).get("list") or []


def variable_sql(var):
    query = var.get("query")
    return query["rawQueryText"] if isinstance(query, dict) else query


def substitute(sql, values):
    """Replace `${name}` and `$name` of each board variable with its value (the Grafana form)."""
    for name, value in values.items():
        sql = sql.replace("${" + name + "}", str(value))
        sql = re.sub(r"\$" + re.escape(name) + r"\b", lambda _m: str(value), sql)
    return sql


def panel_queries(board):
    """(panel title, query text) of every panel target, both text fields."""
    for panel in board["panels"]:
        for target in panel.get("targets", []):
            for key in ("rawQueryText", "queryText"):
                yield panel["title"], target[key]


def live_board():
    return read_board(LIVE)


def live_panel(title):
    (panel,) = [p for p in live_board()["panels"] if p["title"] == title]
    return panel


def panel_sql(panel):
    (target,) = panel["targets"]
    return target["rawQueryText"]


# --- the db made by store.py rebuild ----------------------------------------------------------

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def relative(text, now):
    """Fill the `{now-<seconds>}` fields of a fixture line with a time before `now`."""
    return re.sub(r"\{now-(\d+)\}", lambda m: iso(now - timedelta(seconds=int(m.group(1)))), text)


class LiveDb:
    """A state dir with the live fixtures (times relative to now), stubs for `gh` and the
    collectors, and the db that `store.rebuild()` makes from them. The collector of a second
    project fails, so the load row is a failed one."""

    def __init__(self, tmp, monkeypatch):
        self.now = datetime.now(timezone.utc)
        state = tmp / "state"
        home = state / "agent-graph-kit"
        runs = home / "codex-runs"
        runs.mkdir(parents=True)
        self.db = home / "monitor.sqlite"
        monkeypatch.setenv("XDG_STATE_HOME", str(state))
        monkeypatch.setenv("MONITOR_DB_FILE", str(self.db))
        monkeypatch.setenv("CODEX_RUNS_DIR", str(runs))
        for name in ("RUN_RECORD_FILE", "RUN_RECORD_LIMITS_FILE", "RUN_WEIGHTS_FILE", "STEPS_FILE"):
            monkeypatch.delenv(name, raising=False)
        for name in ("steps.jsonl", "record.jsonl", "run-record-limits.jsonl"):
            target = home / ("run-record.jsonl" if name == "record.jsonl" else name)
            target.write_text(relative((FIXTURES / name).read_text(encoding="utf-8"), self.now), encoding="utf-8")
        # Codex stream files: the attempt of issue 2 still writes (30 s ago), the one of issue 1 ended long ago.
        for launch, age in (("example__proj-2-20261104T110000", 30), ("example__proj-1-20261104T092000", 6300)):
            path = runs / f"{launch}.jsonl"
            path.write_text("{}\n")
            when = (self.now - timedelta(seconds=age)).timestamp()
            os.utime(path, (when, when))
        repo = tmp / "repo"
        repo.mkdir()
        (home / "monitor-projects.json").write_text(json.dumps(
            [{"project": PROJECT, "repo": str(repo)}, {"project": OTHER, "repo": str(repo)}]))
        monkeypatch.setattr(store, "run_command", self.run_command)
        monkeypatch.setattr(store, "gh", self.gh)
        self.status = store.rebuild()

    @staticmethod
    def run_command(cmd, cwd=None):
        project = cmd[cmd.index("--project") + 1]
        return (1, "synthetic collector failure") if project == OTHER else (0, "")

    @staticmethod
    def gh(*args, cwd=None):
        if args[:2] == ("issue", "list"):
            project = args[args.index("--repo") + 1]
            return json.dumps([{"number": 9, "title": "Stage nine"}] if project == PROJECT else [])
        if args[0] == "api":
            return json.dumps([{"number": n, "title": t, "state": "open"} for n, t in STAGE_TITLES.items()])
        raise AssertionError(f"unexpected gh call {args}")

    def rows(self, sql):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql).fetchall()]
        finally:
            con.close()

    def columns(self, sql):
        con = sqlite3.connect(self.db)
        try:
            return [d[0] for d in con.execute(sql).description]
        finally:
            con.close()


@pytest.fixture
def live_db(tmp_path, monkeypatch):
    return LiveDb(tmp_path, monkeypatch)


def fixture_values(db):
    """The values of the live board variables, as Grafana picks them by default: the first row
    of each variable query (the stage query with the chosen project)."""
    values = {}
    for var in board_variables(live_board()):
        rows = db.rows(substitute(variable_sql(var), values))
        assert rows, f"variable {var['name']}: no value"
        values[var["name"]] = next(iter(rows[0].values()))
    return values


def live_rows(db, title):
    return db.rows(substitute(panel_sql(live_panel(title)), fixture_values(db)))


# --- the board form ---------------------------------------------------------------------------

def test_live_board_refreshes_every_30_s_and_has_two_single_value_variables():
    board = live_board()
    assert board["refresh"] == "30s"
    variables = board_variables(board)
    assert [v["name"] for v in variables] == ["project", "stage"]
    for var in variables:
        assert var["type"] == "query"
        assert var["datasource"]["uid"] == "agk-monitor"
        assert var["multi"] is False and var["includeAll"] is False
        assert var["sort"] == 0  # the query order counts: the newest stage first
        # The plugin's metricFindQuery takes the variable query as the SQL text itself.
        assert isinstance(var["query"], str) and var["query"] == var["definition"]
    assert "${project}" in variable_sql(variables[1]) or "$project" in variable_sql(variables[1])


def test_live_panel_queries_use_only_the_board_variables_and_no_time_macro():
    board = live_board()
    names = {v["name"] for v in board_variables(board)}
    sqls = [sql for _title, sql in panel_queries(board)] + [variable_sql(v) for v in board_variables(board)]
    assert sqls
    for sql in sqls:
        assert "$__" not in sql, sql
        used = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", sql))
        assert used <= names, (used, sql)
        assert "[[" not in sql
    for panel in board["panels"]:
        for target in panel.get("targets", []):
            assert target["rawQueryText"] == target["queryText"]
            assert target["datasource"]["uid"] == "agk-monitor"


def test_stub_board_stays_without_variables():
    stub = read_board(BOARDS / "monitor-stub.json")
    assert stub["uid"] == "agk-monitor-stub"
    assert not board_variables(stub)


def walk(node):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_live_board_shows_no_verdict():
    """Numbers and text only: no threshold step beyond the base step, no colored value mapping."""
    for panel in live_board()["panels"]:
        for node in walk(panel):
            if not isinstance(node, dict):
                continue
            if "thresholds" in node:
                steps = node["thresholds"].get("steps") or []
                assert len(steps) <= 1, (panel["title"], steps)
                assert all(s.get("value") is None for s in steps), (panel["title"], steps)
            for mapping in node.get("mappings") or []:
                for item in walk(mapping):
                    assert not (isinstance(item, dict) and "color" in item), (panel["title"], mapping)


# --- every query of every board on the rebuilt db ---------------------------------------------

def test_rebuild_of_the_fixtures_gives_a_failed_load_and_the_rows(live_db):
    assert live_db.status == "failed"
    assert live_db.rows("SELECT status FROM loads") == [{"status": "failed"}]
    assert live_db.rows("SELECT COUNT(*) AS n FROM limits")[0]["n"] == 1
    assert live_db.rows("SELECT COUNT(*) AS n FROM launches WHERE provider = 'codex'")[0]["n"] == 1


def test_every_query_of_every_board_runs_and_each_live_panel_gives_a_row(live_db):
    values = fixture_values(live_db)
    assert values == {"project": PROJECT, "stage": 9}
    for path in board_files():
        board = read_board(path)
        for var in board_variables(board):
            try:
                live_db.rows(substitute(variable_sql(var), values))
            except sqlite3.Error as e:
                pytest.fail(f"{path.name} / variable {var['name']}: {e}")
        for title, sql in panel_queries(board):
            try:
                rows = live_db.rows(substitute(sql, values))
            except sqlite3.Error as e:
                pytest.fail(f"{path.name} / {title}: {e}")
            if path == LIVE:
                assert rows, f"{path.name} / {title}: no row"


def test_stage_variable_lists_the_newest_stage_first(live_db):
    (var,) = [v for v in board_variables(live_board()) if v["name"] == "stage"]
    rows = live_db.rows(substitute(variable_sql(var), {"project": PROJECT}))
    assert [next(iter(r.values())) for r in rows] == [9, 8]


def test_active_launches_panel(live_db):
    sql = substitute(panel_sql(live_panel("Active launches")), fixture_values(live_db))
    columns = live_db.columns(sql)
    for name in ("role", "model", "issue", "title", "stage", "start", "run_time_s", "input_tokens",
                 "output_tokens", "cache_creation_tokens", "cache_read_tokens", "last_tool", "last_target",
                 "last_step_time"):
        assert name in columns, name
    weighted = [c for c in columns if "weight" in c]
    assert weighted and all("estimate" in c for c in weighted)
    rows = live_db.rows(sql)
    by_role = {(r["role"], r["issue"]): r for r in rows}
    assert set(by_role) == {("orchestrator", None), ("engineer", 1), (CODEX_ROLE, 2)}
    eng = by_role[("engineer", 1)]
    assert eng["title"] == STAGE_TITLES[1]
    assert eng["model"] == "claude-fixture" and eng["stage"] == 9
    assert eng["last_tool"] == '["Edit"]' and eng["last_target"] == "/example/repo/src/game.py"
    assert eng["input_tokens"] == 20 and eng["run_time_s"] == 140
    assert eng["weighted_tokens_estimate"] is not None
    assert by_role[("orchestrator", None)]["title"] is None


def test_current_stage_panel_counts_attempts_per_issue_and_role(live_db):
    rows = live_rows(live_db, "Current stage: launches")
    assert [(r["role"], r["issue"], r["attempt"]) for r in rows] == [
        ("orchestrator", None, 1), ("pm", 1, 1), ("engineer", 1, 1), (CODEX_ROLE, 1, 1),
        ("engineer", 1, 2), (CODEX_ROLE, 2, 1)]
    assert [r["start"] for r in rows] == sorted(r["start"] for r in rows)
    assert all(r["launch"] != "live-eng-5" for r in rows)  # stage 8
    assert rows[1]["title"] == STAGE_TITLES[1]


def test_codex_panel_says_active_or_done_with_the_retry(live_db):
    rows = live_rows(live_db, "Codex QA attempts of the stage")
    assert [(r["status"], r["issue"], r["retry"]) for r in rows] == [("done", 1, 1), ("active", 2, None)]
    assert rows[0]["launch"] == "example__proj-1-20261104T092000"
    assert any("estimate" in c for c in rows[0])


def test_usage_limit_panels(live_db):
    panel = live_panel("Usage limit in percent (entered by hand)")
    assert "entered by hand" in panel["title"]
    rows = live_rows(live_db, panel["title"])
    assert [(r["point"], r["percent"], r["plan"], r["entered_by_hand"]) for r in rows] == [
        ("start", 12.5, "fixture plan", 1)]
    texts = [p for p in live_board()["panels"] if p["type"] == "text"]
    assert [p["options"]["content"] for p in texts] == ["no live source; weighted tokens are an estimate"]


def test_loads_panel_shows_the_last_and_the_last_failed_load(live_db):
    (row,) = live_rows(live_db, "Loads")
    assert row["last_load"] and row["last_failed_load"] == row["last_load"]
    assert "synthetic collector failure" in row["last_failed_message"]


def test_loads_panel_gives_one_row_without_a_failed_load(tmp_path):
    con = store.connect(tmp_path / "monitor.sqlite")
    try:
        store.write_load_row(con, store.now_utc(), "ok", "fine", False)
        cur = con.execute(panel_sql(live_panel("Loads")))
        names = [d[0] for d in cur.description]
        (row,) = [dict(zip(names, r)) for r in cur.fetchall()]
    finally:
        con.close()
    assert row["last_load"] and row["last_failed_load"] is None
