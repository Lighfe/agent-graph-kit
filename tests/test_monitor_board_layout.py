"""Tests for the live board of the monitor skill (issue #313): `grafana/boards/live.json`.

No test needs Grafana or Docker. The checks read the board JSON only. The helper `panels(board)` also
serves the history board test of issue #314."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
LIVE = SKILL / "grafana" / "boards" / "live.json"
RULES = SKILL / "otel" / "rules" / "agk.yml"

ROLE_COLOURS = {"orchestrator": "#332288", "pm": "#DDCC77", "engineer": "#117733", "qa-codex": "#88CCEE",
                "qa-claude": "#882255", "planner": "#999933", "other": "#DDDDDD"}
KIND_COLOURS = {"cache_read": "#44AA99", "cache_creation": "#999933", "output": "#AA4499", "input": "#DDDDDD"}
ROSE = "#CC6677"
TEAL = "#44AA99"
ALLOWED_TYPES = {"stat", "text", "barchart", "state-timeline", "bargauge", "table", "timeseries", "row"}

TOP_PANELS = [
    ("Now", "stat"),
    ("Tokens per issue, by role", "barchart"),
    ("Active time per issue, by role", "barchart"),
    ("Timeline", "state-timeline"),
    ("Plan usage limit", "bargauge"),
    ("Launches of this stage", "table"),
    ("Telemetry", "row"),
]
TELEMETRY = [
    "Token rate by kind",
    "Active time per hour, Claude and Codex",
    "API requests per minute, Claude and Codex",
    "API latency p50 and p95",
    "API errors",
    "Tool calls by tool and p95 tool duration",
    "Lines of code added and removed",
    "Commits and pull requests",
]
TABLE_COLUMNS = ["issue", "role", "tokens", "tokens above typical", "active time", "active time above typical",
                 "return", "model", "start"]


def board():
    return json.loads(LIVE.read_text(encoding="utf-8"))


def panels(board):
    """All panels of a board in order, with the panels inside rows after their row."""
    out = []
    for p in board["panels"]:
        out.append(p)
        out.extend(p.get("panels", []))
    return out


def top(board):
    return {p["title"]: p for p in board["panels"]}


def queries(board, source=None):
    for p in panels(board):
        for t in p.get("targets", []):
            if source is None or t["datasource"]["type"] == source:
                yield p["title"], t


def colour_overrides(panel):
    """name -> fixed colour of the byName overrides of a panel."""
    out = {}
    for o in panel["fieldConfig"]["overrides"]:
        if o["matcher"]["id"] != "byName":
            continue
        for prop in o["properties"]:
            if prop["id"] == "color" and prop["value"].get("mode") == "fixed":
                out[o["matcher"]["options"]] = prop["value"]["fixedColor"]
    return out


def mapping_colours(panel):
    """text/value -> colour of the value mappings of a panel (defaults and overrides)."""
    out = {}
    sets = [panel["fieldConfig"]["defaults"].get("mappings", [])]
    sets += [p["value"] for o in panel["fieldConfig"]["overrides"] for p in o["properties"] if p["id"] == "mappings"]
    for maps in sets:
        for m in maps:
            if m["type"] == "value":
                for key, res in m["options"].items():
                    if "color" in res:
                        out[res.get("text", key)] = res["color"]
            elif m["type"] == "regex" and "color" in m["options"]["result"]:
                out[m["options"]["pattern"]] = m["options"]["result"]["color"]
    return out


def test_live_board_header():
    b = board()
    assert "id" not in b
    assert b["refresh"] == "30s"
    names = [v["name"] for v in b["templating"]["list"]]
    assert names == ["project", "stage"]


def test_live_panel_types():
    b = board()
    assert [(p["title"], p["type"]) for p in b["panels"]] == TOP_PANELS
    all_panels = panels(b)
    assert {p["type"] for p in all_panels} <= ALLOWED_TYPES
    assert [p["title"] for p in all_panels if p["type"] == "table"] == ["Launches of this stage"]
    for p in all_panels:
        if p["title"] in ("Tokens per issue, by role", "Active time per issue, by role"):
            assert p["type"] == "barchart"
            assert p["options"]["stacking"] == "normal"


def test_role_colours():
    b = board()
    t = top(b)
    for title in ("Tokens per issue, by role", "Active time per issue, by role"):
        got = colour_overrides(t[title])
        for role, colour in ROLE_COLOURS.items():
            assert got[role] == colour, (title, role)
    # the timeline: every role as a block colour, and the return mark keeps it
    maps = {}
    for m in t["Timeline"]["fieldConfig"]["defaults"]["mappings"]:
        for key, res in m["options"].items():
            maps.setdefault(res["text"], set()).add(res["color"])
    for role, colour in ROLE_COLOURS.items():
        assert maps[role] == {colour}
    assert "↺" in maps
    # the table and the Now tile colour the role text
    for title in ("Launches of this stage", "Now"):
        got = mapping_colours(t[title])
        for role, colour in ROLE_COLOURS.items():
            assert got[role] == colour, (title, role)
    # the token kinds and the providers in the Telemetry row
    tel = {p["title"]: p for p in t["Telemetry"]["panels"]}
    got = colour_overrides(tel["Token rate by kind"])
    for kind, colour in KIND_COLOURS.items():
        assert got[kind] == colour
    got = colour_overrides(tel["Active time per hour, Claude and Codex"])
    assert got["Claude"] == "#332288" and got["Codex"] == "#88CCEE"
    assert set(colour_overrides(tel["API errors"]).values()) == {ROSE}


def test_launch_table_columns():
    b = board()
    p = top(b)["Launches of this stage"]
    organize = next(t for t in p["transformations"] if t["id"] == "organize")["options"]
    index = organize["indexByName"]
    rename = organize["renameByName"]
    order = sorted(index, key=index.get)
    assert [rename.get(n, n) for n in order] == TABLE_COLUMNS
    sort = next(t for t in p["transformations"] if t["id"] == "sortBy")["options"]["sort"]
    assert sort == [{"field": "Value #F", "desc": True}]
    # no fixed width, no wrap
    assert p["fieldConfig"]["defaults"]["custom"]["wrapText"] is False
    for o in p["fieldConfig"]["overrides"]:
        for prop in o["properties"]:
            assert prop["id"] not in ("custom.width", "custom.minWidth")
    # the marker columns: "▲" in rose, from a p75 grouped and joined by role
    by_ref = {t["refId"]: t["expr"] for t in p["targets"]}
    for ref in ("B", "D"):
        assert re.search(r"quantile by \(role\) \(0\.75,", by_ref[ref]), ref
        assert "on (role)" in by_ref[ref], ref
    for name in ("Value #B", "Value #D", "tokens above typical", "active time above typical"):
        ov = next(o for o in p["fieldConfig"]["overrides"] if o["matcher"]["options"] == name)
        maps = next(pr["value"] for pr in ov["properties"] if pr["id"] == "mappings")
        assert maps[0]["options"]["1"] == {"text": "▲", "color": ROSE, "index": 0}
    # the running launch: a teal dot before the role, by value mapping
    assert mapping_colours(p)["^● .*"] == TEAL
    assert "● $1" in by_ref["A"]
    assert "agk_marker" in by_ref["A"]


def test_builtin_panels_only():
    b = board()
    for p in panels(b):
        assert p["type"] in ALLOWED_TYPES, p["title"]
        assert "pluginVersion" not in p
    uids = {t["datasource"]["uid"] for _, t in queries(b)}
    assert uids <= {"agk-prometheus", "agk-loki"}
    assert {t["datasource"]["type"] for _, t in queries(b)} <= {"prometheus", "loki"}


def test_board_has_no_instance_ids():
    text = LIVE.read_text(encoding="utf-8")
    b = json.loads(text)
    assert "id" not in b
    assert b["uid"] == "agk-live"
    # data sources only by uid: no numeric datasource id anywhere
    assert not re.search(r'"datasource":\s*\{[^}]*"id"', text)
    assert not re.search(r'"datasource":\s*(\d+|"[^"]*")', text)


# --- the names of the data-names criterion ------------------------------------------------------------
def _header_series():
    names = set()
    for line in RULES.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            names.update(re.findall(r"\b(?:claude_code|codex)_[a-z0-9_]+\b", line))
    return names


# Claude Code counters of the Telemetry row that the header of agk.yml does not list. Their names follow the
# rule of the header (dots become underscores, a counter gets _total); no live data confirmed them yet.
EXTRA_SERIES = {"claude_code_lines_of_code_count_total", "claude_code_commit_count_total",
                "claude_code_pull_request_count_total"}
RECORDED = {"agk:tokens:1m", "agk:active_seconds:1m"}
FACTS = {"agk_issue_info", "agk_marker", "agk_usage_limit_percent", "agk_facts_last_success_seconds"}
LABELS = {"agk_project", "stage", "issue", "title", "order", "role", "launch", "kind", "model", "provider", "window"}
# labels that a query makes itself (label_replace, label_join) or that the Claude counters carry
DERIVED = {"ord", "short", "slot", "attempt", "type"}
# attributes of the Loki events (structured metadata)
LOKI_FIELDS = {"tool_name", "duration_ms"}
EVENTS = {"claude_code.tool_result", "claude_code.api_request", "claude_code.api_error", "codex.api_request"}


def _strings(expr):
    return re.findall(r'"((?:[^"\\]|\\.)*)"', expr)


def _strip_strings(expr):
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', expr)


def test_queries_use_known_names():
    known = _header_series() | EXTRA_SERIES | RECORDED | FACTS
    assert "codex_turn_token_usage_sum" in known  # the header was read
    labels_ok = LABELS | DERIVED | LOKI_FIELDS
    for title, t in queries(board()):
        expr = t["expr"]
        bare = _strip_strings(expr)
        if t["datasource"]["type"] == "prometheus":
            for name in re.findall(r"\b((?:agk|claude_code|codex)[A-Za-z0-9_:]*)", bare):
                if name not in LABELS:
                    assert name in known, (title, name)
        for m in re.finditer(r"\{([^{}]*)\}", expr):
            for lab in re.findall(r"(\w+)\s*(?:=~|!~|!=|=)", re.sub(r'"(?:[^"\\]|\\.)*"', '""', m.group(1))):
                assert lab in labels_ok, (title, lab)
        for m in re.finditer(r"\b(?:by|on|group_left|group_right|without)\s*\(([^)]*)\)", bare):
            for lab in [x.strip() for x in m.group(1).split(",") if x.strip()]:
                assert lab in labels_ok, (title, lab)
        for lab in re.findall(r"unwrap\s+(\w+)", bare):
            assert lab in LOKI_FIELDS, (title, lab)
        if t["datasource"]["type"] == "loki":
            lines = [s for s in _strings(expr) if re.match(r"(claude_code|codex)\.", s)]
            assert lines, title
            assert set(lines) <= EVENTS, (title, lines)
    # the variables use known names too
    for v in board()["templating"]["list"]:
        q = v["query"]["query"]
        for name in re.findall(r"\b(agk[A-Za-z0-9_:]*)", _strip_strings(q)):
            assert name in known or name in LABELS


def test_telemetry_row_collapsed():
    row = top(board())["Telemetry"]
    assert row["type"] == "row"
    assert row["collapsed"] is True
    assert [p["title"] for p in row["panels"]] == TELEMETRY
    assert {p["type"] for p in row["panels"]} == {"timeseries"}


def test_highlight_needs_three_stages():
    b = board()
    t = top(b)
    guard = re.compile(r"and on \(\) \(count\(count by \(stage\) \(last_over_time\([^)]*\[365d\]\)\)\) >= 3\)")
    for title in ("Tokens per issue, by role", "Active time per issue, by role"):
        typical = [x for x in t[title]["targets"] if x["refId"] == "B"][0]
        assert "quantile(0.5," in typical["expr"]
        assert guard.search(typical["expr"]), title
        assert typical.get("hide") is True
        assert "not drawn" in t[title]["description"]
    table = t["Launches of this stage"]
    for ref in ("B", "D"):
        expr = [x for x in table["targets"] if x["refId"] == ref][0]["expr"]
        assert guard.search(expr), ref
        assert 'stage!="$stage"' in expr
