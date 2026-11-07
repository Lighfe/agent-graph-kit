"""Tests for the Grafana board files of the monitor skill (issues #284 and #285): every query of
every board in `plugin/skills/monitor/grafana/boards/` runs on the dbs that `store.py rebuild` made
from synthetic fixtures, the live board `live.json` has the panels of the spec (Part D, "Live
board"), and the history board `history.json` those of Part D, "History board".

No test needs Grafana, Docker or the network: `gh` and the collectors are stubbed. All data is
synthetic (`tests/fakes/monitor/live/` and `tests/fakes/monitor/history/`). The live times are
written relative to the time of the test, since the view `active_launches` only lists launches
with a step at most 5 minutes old."""

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
HISTORY = BOARDS / "history.json"
FIXTURES = ROOT / "tests" / "fakes" / "monitor" / "live"
HISTORY_FIXTURES = ROOT / "tests" / "fakes" / "monitor" / "history"
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


@pytest.mark.parametrize("path", [LIVE, HISTORY], ids=lambda p: p.name)
def test_board_shows_no_verdict(path):
    """Numbers and text only: no threshold step beyond the base step, no colored value mapping."""
    for panel in read_board(path)["panels"]:
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


def board_values(db, board):
    """The values of a board's own variables on a db, as Grafana picks them by default: the first
    row of each variable query, in board order (a later query uses the earlier values). A query
    with no row gives the empty text."""
    values = {}
    for var in board_variables(board):
        rows = db.rows(substitute(variable_sql(var), values))
        values[var["name"]] = next(iter(rows[0].values())) if rows else ""
    return values


def run_every_query(db, must_give_rows=()):
    for path in board_files():
        board = read_board(path)
        try:
            values = board_values(db, board)
        except sqlite3.Error as e:
            pytest.fail(f"{path.name} / variables: {e}")
        for title, sql in panel_queries(board):
            try:
                rows = db.rows(substitute(sql, values))
            except sqlite3.Error as e:
                pytest.fail(f"{path.name} / {title}: {e}")
            if path in must_give_rows:
                assert rows, f"{path.name} / {title}: no row"


def test_every_query_of_every_board_runs_and_each_live_panel_gives_a_row(live_db):
    assert fixture_values(live_db) == {"project": PROJECT, "stage": 9}
    assert board_values(live_db, live_board()) == {"project": PROJECT, "stage": 9}
    run_every_query(live_db, must_give_rows=(LIVE,))


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


# --- the history board ------------------------------------------------------------------------

HISTORY_STAGE = 7
HISTORY_TITLES = {1: "History issue one"}  # issue 2 and the stage issue have no stored title
TOKEN_KINDS = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens")


class HistoryDb(LiveDb):
    """A state dir with the history fixtures (fixed times: no panel of the history board depends
    on the time of the query), stubs for `gh` and the collectors, and the db of `store.rebuild()`."""

    def __init__(self, tmp, monkeypatch):  # noqa: super().__init__ is not called on purpose
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
        for name, target in (("record.jsonl", "run-record.jsonl"), ("steps.jsonl", "steps.jsonl"),
                             ("retry-cases.jsonl", "retry-cases.jsonl")):
            (home / target).write_text((HISTORY_FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
        repo = tmp / "repo"
        repo.mkdir()
        (home / "monitor-projects.json").write_text(json.dumps([{"project": PROJECT, "repo": str(repo)}]))
        monkeypatch.setattr(store, "run_command", lambda cmd, cwd=None: (0, ""))
        monkeypatch.setattr(store, "gh", self.gh)
        self.status = store.rebuild()

    @staticmethod
    def gh(*args, cwd=None):
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": HISTORY_STAGE, "title": "Stage seven"}])
        if args[0] == "api":
            return json.dumps([{"number": n, "title": t, "state": "closed"} for n, t in HISTORY_TITLES.items()])
        raise AssertionError(f"unexpected gh call {args}")


@pytest.fixture
def history_db(tmp_path, monkeypatch):
    return HistoryDb(tmp_path, monkeypatch)


def history_board():
    return read_board(HISTORY)


def history_panel(title):
    (panel,) = [p for p in history_board()["panels"] if p["title"] == title]
    return panel


def history_values(db, **chosen):
    """The history variables as Grafana picks them; `chosen` sets a variable as a data link does,
    and the variables after it are picked again from their first row."""
    values = {}
    for var in board_variables(history_board()):
        name = var["name"]
        if name in chosen:
            values[name] = chosen[name]
            continue
        rows = db.rows(substitute(variable_sql(var), values))
        values[name] = next(iter(rows[0].values())) if rows else ""
    return values


def history_rows(db, title, **chosen):
    return db.rows(substitute(panel_sql(history_panel(title)), history_values(db, **chosen)))


def all_history_rows(db):
    values = history_values(db)
    return {p["title"]: db.rows(substitute(panel_sql(p), values)) for p in history_board()["panels"]}


def sql_round(value):
    """ROUND() of SQLite, the rounding of the panels."""
    con = sqlite3.connect(":memory:")
    try:
        return con.execute("SELECT ROUND(?)", (value,)).fetchone()[0]
    finally:
        con.close()


def fixture_record():
    return [json.loads(line) for line in (HISTORY_FIXTURES / "record.jsonl").read_text().splitlines() if line]


def counted_lines():
    """The fixture lines a history total counts, by the rules of #285: a provider, not the planner
    /stage-start session. Each with its label (`measured` or `orchestrator estimate`), weighted value
    and seconds, computed here from the line itself."""
    weights = store.data.load_weights(path=SKILL / "run-weights.json")
    out = []
    for line in fixture_record():
        if line["provider"] not in ("claude", "codex"):
            continue
        if line["role"] == "planner" and line["issue"] is None:
            continue
        out.append({**line, "lines": "orchestrator estimate" if line["estimate"] else "measured",
                    "weighted": store.data.weighted(line, weights), "seconds": store.data.seconds(line)})
    return out


def expected_totals(lines, key):
    groups = {}
    for line in lines:
        groups.setdefault(key(line), []).append(line)
    return {k: {"weighted_tokens_estimate": sql_round(sum(l["weighted"] for l in g)),
                **{kind: sum(l[kind] for l in g) for kind in TOKEN_KINDS},
                "seconds": sql_round(sum(l["seconds"] for l in g)), "launches": len(g)}
            for k, g in groups.items()}


def test_history_board_form():
    board = history_board()
    uids = [read_board(p)["uid"] for p in board_files()]
    assert board["uid"] == "agk-monitor-history" and uids.count(board["uid"]) == 1
    variables = board_variables(board)
    names = [v["name"] for v in variables]
    assert names[:2] == ["project", "stage"]
    for var in variables:
        assert var["type"] == "query" and var["datasource"]["uid"] == "agk-monitor"
        assert var["multi"] is False and var["includeAll"] is False and var["sort"] == 0
        assert isinstance(var["query"], str) and var["query"] == var["definition"]
    sqls = [sql for _title, sql in panel_queries(board)] + [variable_sql(v) for v in variables]
    for sql in sqls:
        assert "$__" not in sql and "[[" not in sql, sql
        assert set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", sql)) <= set(names), sql
    for panel in board["panels"]:
        for target in panel["targets"]:
            assert target["rawQueryText"] == target["queryText"]
            assert target["datasource"]["uid"] == "agk-monitor"


def test_rebuild_of_the_history_fixtures(history_db):
    assert history_db.status == "ok"
    assert history_db.rows("SELECT COUNT(*) AS n FROM cases")[0]["n"] == 2
    assert history_values(history_db)["project"] == PROJECT
    assert history_values(history_db)["stage"] == HISTORY_STAGE


def test_every_query_of_every_board_runs_on_the_history_db_and_each_history_panel_gives_a_row(history_db):
    run_every_query(history_db, must_give_rows=(HISTORY,))


def test_history_queries_run_on_the_live_db_too(live_db):
    board = history_board()
    values = board_values(live_db, board)
    for title, sql in panel_queries(board):
        live_db.rows(substitute(sql, values))


def test_stage_panel_per_provider(history_db):
    rows = history_rows(history_db, "Stages")
    columns = history_db.columns(substitute(panel_sql(history_panel("Stages")), history_values(history_db)))
    for name in ("stage", "provider", "lines", *TOKEN_KINDS, "seconds", "launches", "retries", "escalations"):
        assert name in columns, name
    assert [c for c in columns if "weight" in c] == ["weighted_tokens_estimate"]
    expected = expected_totals(counted_lines(), lambda l: (l["stage"], l["provider"], l["lines"]))
    got = {(r["stage"], r["provider"], r["lines"]): r for r in rows}
    assert set(got) == set(expected) == {
        (7, "claude", "measured"), (7, "claude", "orchestrator estimate"), (7, "codex", "measured"),
        (6, "claude", "measured")}
    for key, want in expected.items():
        assert {k: got[key][k] for k in want} == want, key
    for provider in ("claude", "codex"):
        row = got[(HISTORY_STAGE, provider, "measured")]
        assert (row["retries"], row["escalations"]) == (2, 1)
    assert got[(6, "claude", "measured")]["retries"] == 0
    assert got[(HISTORY_STAGE, "claude", "orchestrator estimate")]["launches"] == 1
    assert [r["stage"] for r in rows] == sorted((r["stage"] for r in rows), reverse=True)


def cells(rows):
    for row in rows:
        yield from row.values()


def test_no_panel_adds_claude_and_codex_together(history_db):
    lines = [l for l in counted_lines() if l["stage"] == HISTORY_STAGE and l["lines"] == "measured"]
    both = sql_round(sum(l["weighted"] for l in lines))
    with_estimate = sql_round(sum(l["weighted"] for l in counted_lines() if l["stage"] == HISTORY_STAGE))
    for title, rows in all_history_rows(history_db).items():
        for value in cells(rows):
            assert value not in (both, with_estimate), (title, value)
    # The panels show each provider's own sum, so the check above is not empty.
    claude = sql_round(sum(l["weighted"] for l in lines if l["provider"] == "claude"))
    assert claude in set(cells(history_rows(history_db, "Stages")))


def test_breakdowns_by_issue_role_and_model(history_db):
    stage_lines = [l for l in counted_lines() if l["stage"] == HISTORY_STAGE]
    label = lambda l: "orchestrator" if l["issue"] is None else str(l["issue"])  # noqa: E731
    for title, key in (("Issues of the stage", lambda l: (label(l), l["provider"], l["lines"])),
                       ("Roles of the stage", lambda l: (l["role"], l["provider"], l["lines"])),
                       ("Models of the stage", lambda l: (l["model"], l["provider"], l["lines"]))):
        rows = history_rows(history_db, title)
        first = next(iter(rows[0]))
        got = {(r[first], r["provider"], r["lines"]): r for r in rows}
        expected = expected_totals(stage_lines, key)
        assert set(got) == set(expected), title
        for k, want in expected.items():
            assert {c: got[k][c] for c in want} == want, (title, k)
    issues = {(r["issue"], r["provider"], r["lines"]): r for r in history_rows(history_db, "Issues of the stage")}
    assert ("orchestrator", "claude", "measured") in issues
    assert ("orchestrator", "claude", "orchestrator estimate") in issues
    assert all(i not in (None, "") for i, _p, _l in issues)
    assert issues[("1", "claude", "measured")]["title"] == HISTORY_TITLES[1]
    assert issues[("2", "claude", "measured")]["title"] == ""  # no stored title: empty, not an error
    assert (issues[("1", "claude", "measured")]["retries"], issues[("2", "codex", "measured")]["escalations"]) == (1, 1)
    assert ("7", "claude", "measured") in issues  # the stage-review planner is shown


def test_drill_down_links_stage_issue_launch_steps(history_db):
    board = history_board()
    names = [v["name"] for v in board_variables(board)]
    chain = (("Stages", "stage", "Issues of the stage"), ("Issues of the stage", "issue", "Launches of the issue"),
             ("Launches of the issue", "launch", "Steps of the launch"))
    for title, column, target in chain:
        assert column in names
        (link,) = history_panel(title)["fieldConfig"]["defaults"]["links"]
        assert link["url"].startswith(f"/d/{board['uid']}/") or link["url"].startswith(f"/d/{board['uid']}?")
        assert f"var-{column}=${{__data.fields.{column}}}" in link["url"]
        assert column in history_db.columns(substitute(panel_sql(history_panel(title)), history_values(history_db)))
        assert re.search(r"\$\{?" + column + r"\b", panel_sql(history_panel(target))), target
    # Follow the links: the clicked row's value picks the rows of the next panel.
    (stage_row,) = [r for r in history_rows(history_db, "Stages") if r["stage"] == 6]
    (issue_row,) = history_rows(history_db, "Issues of the stage", stage=stage_row["stage"])
    assert issue_row["issue"] == "3"
    orch = history_rows(history_db, "Launches of the issue", issue="orchestrator")
    assert {r["lines"] for r in orch} == {"measured", "orchestrator estimate"}
    assert {r["launch"] for r in orch} == {"hist-orch"} and {r["steps"] for r in orch} == {2}
    launches = history_rows(history_db, "Launches of the issue", issue="1")
    assert [r["role"] for r in launches] == ["pm", "engineer", "qa-" + "codex", "engineer"]
    codex = launches[2]
    assert codex["launch"] == "example__proj-1-20261001T083000" and codex["steps"] == 2
    steps = history_rows(history_db, "Steps of the launch", launch=launches[0]["launch"])
    for name in ("tool", "target", *TOKEN_KINDS, "duration_s", "context_tokens"):
        assert name in steps[0], name
    assert [r["seq"] for r in steps] == [1, 2, 3]
    assert steps[0]["tool"] == '["Read"]' and steps[0]["context_tokens"] == 1230


def test_kit_document_reads_per_role_and_document(history_db):
    rows = history_rows(history_db, "Kit document reads")
    doc = "/example/repo/docs/"
    assert {(r["role"], r["kit_doc"]): r["reads"] for r in rows} == {
        ("engineer", doc + "process.md"): 2, ("engineer", doc + "team/software-engineer.md"): 1,
        ("orchestrator", doc + "process.md"): 1, ("pm", doc + "process.md"): 1, ("pm", doc + "team/pm.md"): 1,
        ("planner", doc + "team/planner.md"): 1}  # the stage review only; /stage-start read it twice


def test_planner_stage_start_session_is_in_no_panel(history_db):
    planner = [l for l in fixture_record() if l["role"] == "planner" and l["issue"] is None]
    assert planner
    # The planner counts are larger than any other line's, so a cell that holds one of them, alone
    # or inside a sum, is at least that large.
    smallest = min(l[k] for l in planner for k in TOKEN_KINDS)
    others = [l for l in fixture_record() if l not in planner]
    assert smallest > sum(l[k] for l in others for k in TOKEN_KINDS)
    token_columns = (*TOKEN_KINDS, "weighted_tokens_estimate")
    for title, rows in all_history_rows(history_db).items():
        for row in rows:
            if "role" in row and "issue" in row:  # the role panel has no issue: its planner row is the review
                assert not (row["role"] == "planner" and row["issue"] in (None, "orchestrator")), (title, row)
            assert "hist-plan" not in row.values(), (title, row)
            for column in token_columns:
                assert (row.get(column) or 0) < smallest, (title, column, row)
    assert history_rows(history_db, "Steps of the launch", launch="hist-plan") == []
    (var,) = [v for v in board_variables(history_board()) if v["name"] == "issue"]
    labels = [next(iter(r.values())) for r in history_db.rows(substitute(variable_sql(var), history_values(history_db)))]
    assert labels == ["1", "2", "7", "orchestrator"]
