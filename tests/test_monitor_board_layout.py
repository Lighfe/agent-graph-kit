"""Tests for the boards of the monitor skill: the live board (issue #313, `grafana/boards/live.json`) and the
history board (issue #314, `grafana/boards/history.json`).

No test needs Grafana or Docker. The checks read the board JSON only."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
LIVE = SKILL / "grafana" / "boards" / "live.json"
HISTORY = SKILL / "grafana" / "boards" / "history.json"
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


def history():
    return json.loads(HISTORY.read_text(encoding="utf-8"))


BOARDS = pytest.mark.parametrize("load", [board, history], ids=["live", "history"])


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
        results = [m["options"]["result"]] if m["type"] == "regex" else list(m["options"].values())
        for res in results:
            role = res["text"].removeprefix("↺ ").split(" · ")[0]
            maps.setdefault(role, set()).add(res["color"])
            if res["text"].startswith("↺"):
                maps.setdefault("↺", set()).add(res["color"])
    for role, colour in ROLE_COLOURS.items():
        assert maps[role] == {colour}
    assert maps["↺"] == set(ROLE_COLOURS.values())
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
    # one row per launch of an issue: the queries join on a key of issue, role and launch (the launch name alone,
    # for example engineer-1, repeats on every issue), and only query A carries the label columns
    join = next(t for t in p["transformations"] if t["id"] == "joinByField")["options"]
    assert join == {"byField": "key", "mode": "outer"}
    for t in p["targets"]:
        assert '"key", "/", "issue", "role", "launch"' in t["expr"], t["refId"]
        if t["refId"] != "A":
            assert re.match(r"(sum|min|topk) by \(key\) \(", t["expr"]), t["refId"]
    keep = next(t for t in p["transformations"] if t["id"] == "filterFieldsByName")["options"]["include"]["names"]
    assert keep == order
    # no wrap; a fixed width of at most 60 px only on the two marker columns (Grafana cannot make a column
    # narrower than its share without one); no other column has a fixed width, no column has a minimum width
    assert p["fieldConfig"]["defaults"]["custom"]["wrapText"] is False
    for prop_id in ("width", "minWidth"):
        assert prop_id not in p["fieldConfig"]["defaults"]["custom"]
    widths = {}
    for o in p["fieldConfig"]["overrides"]:
        for prop in o["properties"]:
            assert prop["id"] != "custom.minWidth", o["matcher"]
            if prop["id"] == "custom.width":
                widths[o["matcher"]["options"]] = prop["value"]
    assert set(widths) == {"tokens above typical", "active time above typical"}
    # Grafana 13 draws a column at least 50 px wide but sizes the other columns with the set width,
    # so a smaller width pushes the last column out of the panel
    assert all(isinstance(w, int) and 50 <= w <= 60 for w in widths.values()), widths
    # the long header of a narrow marker column wraps instead of being cut
    for name in widths:
        ov = next(o for o in p["fieldConfig"]["overrides"] if o["matcher"]["options"] == name)
        assert {"id": "custom.wrapHeaderText", "value": True} in ov["properties"], name
    # the marker columns: "▲" in rose, from a p75 grouped and joined by role
    by_ref = {t["refId"]: t["expr"] for t in p["targets"]}
    for ref in ("B", "D"):
        assert re.search(r"quantile by \(role\) \(0\.75,", by_ref[ref]), ref
        assert "on (role)" in by_ref[ref], ref
    for name in ("Value #B", "Value #D", "tokens above typical", "active time above typical"):
        ov = next(o for o in p["fieldConfig"]["overrides"] if o["matcher"]["options"] == name)
        maps = next(pr["value"] for pr in ov["properties"] if pr["id"] == "mappings")
        assert maps[0]["options"]["1"] == {"text": "▲", "color": ROSE, "index": 0}
        # a table cell shows a mapping colour only as coloured text
        assert {"id": "custom.cellOptions", "value": {"type": "color-text"}} in ov["properties"]
        # the marker column is always there: the query gives 0 for a launch that is not above the p75
        assert maps[1]["options"]["0"]["text"].strip() == ""
    for ref in ("B", "D"):
        assert re.search(r"\* 0 \+ 1\) or \(sum by \(issue, role, launch\) .* \* 0\)", by_ref[ref]), ref
        # the p75 is over the launches of the other stages, one value per launch of an issue
        assert "sum by (stage, issue, role, launch)" in by_ref[ref], ref
    # the running launch: a teal dot before the role, by value mapping
    assert mapping_colours(p)["^● .*"] == TEAL
    assert "● $1" in by_ref["A"]
    assert "agk_marker" in by_ref["A"]


@BOARDS
def test_panel_data_source_fits_its_queries(load):
    """Grafana sends every query of a panel to the data source of the panel, unless that is "-- Mixed --".
    A Loki query in a Prometheus panel is a query error (the warning icon of the Now panel)."""
    for p in panels(load()):
        kinds = {t["datasource"]["type"] for t in p.get("targets", [])}
        if not kinds:
            continue
        if len(kinds) > 1:
            assert p["datasource"] == {"type": "datasource", "uid": "-- Mixed --"}, p["title"]
        else:
            assert p["datasource"]["type"] in kinds, p["title"]
            assert p["datasource"]["uid"] in ("agk-prometheus", "agk-loki"), p["title"]
    if load is board:
        assert top(board())["Now"]["datasource"]["uid"] == "-- Mixed --"


def test_not_started_issues_keep_their_slot():
    """An issue with no data has the series "pending" with value 0. The bar chart must draw that series (with no
    colour): a field that is hidden from the chart leaves "No numeric fields found" when no issue has data."""
    t = top(board())
    for title in ("Tokens per issue, by role", "Active time per issue, by role"):
        p = t[title]
        expr = p["targets"][0]["expr"]
        assert re.search(r'label_replace\(.*agk_issue_info.* \* 0, "role", "pending", "", ""\) unless on \(issue\)', expr)
        ov = next(o for o in p["fieldConfig"]["overrides"] if o["matcher"]["options"] == "pending")
        props = {x["id"]: x["value"] for x in ov["properties"]}
        assert props["custom.hideFrom"] == {"legend": True, "tooltip": True, "viz": False}
        assert props["color"] == {"mode": "fixed", "fixedColor": "transparent"}
        matrix = next(x for x in p["transformations"] if x["id"] == "groupingToMatrix")["options"]
        assert (matrix["rowField"], matrix["columnField"], matrix["valueField"]) == ("slot", "role", "Value")
    # the timeline has a row for each issue of the stage, also with no launch: value 0, no colour
    tl = t["Timeline"]
    assert re.search(r"or \(label_join\(.*agk_issue_info.*\) \* 0\)\)$", tl["targets"][1]["expr"])
    zero = [m["options"]["0"] for m in tl["fieldConfig"]["defaults"]["mappings"] if "0" in m["options"]]
    assert zero == [{"text": " ", "color": "transparent", "index": 0}]
    # the colour mode "thresholds" makes the state timeline show the threshold range, not the mapped role
    assert tl["fieldConfig"]["defaults"]["color"]["mode"] == "fixed"


def _timeline_text(maps, value):
    """The text and colour Grafana gives a state: the first mapping in index order that matches the text value
    (a regex mapping matches only text, see the convertFieldType step)."""
    s = str(value)
    for m in sorted(maps, key=lambda m: min(r["index"] for r in (
            [m["options"]["result"]] if m["type"] == "regex" else m["options"].values()))):
        if m["type"] == "value" and s in m["options"]:
            return m["options"][s]["text"], m["options"][s]["color"]
        if m["type"] == "regex":
            rx = re.compile(m["options"]["pattern"])
            if rx.fullmatch(s):
                res = m["options"]["result"]
                return rx.sub(re.sub(r"\$(\d)", r"\\\1", res["text"]), s), res["color"]
    return None


def test_hover_shows_total_and_launch_details():
    t = top(board())
    # panels 2 and 3: a series "total" per issue, in the hover only: its own scale (a max of its own), so it is
    # not stacked on the segments, and no fill
    for title, scale in (("Tokens per issue, by role", " / 1e6"), ("Active time per issue, by role", "")):
        p = t[title]
        expr = p["targets"][0]["expr"]
        assert re.search(r'or label_replace\(sum by \(issue\) \(sum_over_time\(agk:[a-z_]+:1m\{[^}]*\}\[\$__range\]\)\)'
                         + re.escape(scale) + r' \* on \(issue\) group_left \(slot\) .*, "role", "total", "", ""\)$',
                         expr), title
        ov = next(o for o in p["fieldConfig"]["overrides"] if o["matcher"]["options"] == "total")
        props = {x["id"]: x["value"] for x in ov["properties"]}
        assert props["custom.hideFrom"] == {"legend": True, "tooltip": False, "viz": False}
        assert props["custom.fillOpacity"] == 0
        assert props["max"] >= 1e12
        assert props["custom.axisPlacement"] == "hidden"
        assert "unit" not in props  # the same unit as the segments
        order = next(x for x in p["transformations"] if x["id"] == "organize")["options"]["indexByName"]
        assert max(order, key=order.get) == "total"  # the last line of the hover
    assert t["Tokens per issue, by role"]["fieldConfig"]["defaults"]["unit"] == "suffix: M"
    assert t["Active time per issue, by role"]["fieldConfig"]["defaults"]["unit"] == "s"
    # panel 4: the state is a number R N AAAA TTTTT (role, return, active minutes, tokens / 1e4), made text, and a
    # regex mapping per role gives the hover text
    tl = t["Timeline"]
    conv = next(x for x in tl["transformations"] if x["id"] == "convertFieldType")["options"]["conversions"]
    assert conv == [{"targetField": "Value", "destinationType": "string"}]
    expr = tl["targets"][1]["expr"]
    assert "* 1e10" in expr and "* 1e9" in expr and "* 1e5" in expr and "/ 1e4" in expr
    assert "agk:active_seconds:1m" in expr and "agk:tokens:1m" in expr
    maps = tl["fieldConfig"]["defaults"]["mappings"]
    for n, (role, colour) in enumerate(ROLE_COLOURS.items(), start=1):
        assert _timeline_text(maps, n * 10**10 + 9 * 10**5 + 99) == (
            f"{role} · return 0 · 9 min active · 0.99 M tokens", colour)
        assert _timeline_text(maps, n * 10**10 + 2 * 10**9 + 1234 * 10**5 + 12345) == (
            f"↺ {role} · return 2 · 1234 min active · 123.45 M tokens", colour)
        assert _timeline_text(maps, n * 10**10) == (f"{role} · return 0 · 0 min active · 0.00 M tokens", colour)
    assert _timeline_text(maps, 0) == (" ", "transparent")
    assert _timeline_text(maps, 1) == ("orchestrator", ROLE_COLOURS["orchestrator"])


def test_now_panel_fields():
    p = top(board())["Now"]
    assert p["options"]["orientation"] == "auto"
    assert p["options"]["colorMode"] == "value"  # with "none" the role tile has no role colour
    shown = p["options"]["reduceOptions"]["fields"]
    for name in ("role", "issue", "return", "active time", "tokens", "since last step", "tool_name", "facts age"):
        assert name in shown
    legends = {t.get("legendFormat") for t in p["targets"]}
    assert {"return", "active time", "tokens", "since last step", "facts age"} <= legends
    age = next(t for t in p["targets"] if t.get("legendFormat") == "facts age")
    assert age["expr"] == "(time() - agk_facts_last_success_seconds) > 120"


@BOARDS
def test_builtin_panels_only(load):
    b = load()
    for p in panels(b):
        assert p["type"] in ALLOWED_TYPES, p["title"]
        assert "pluginVersion" not in p
    for p in panels(b):
        if p["type"] != "row":
            assert p["datasource"]["uid"] in ("agk-prometheus", "agk-loki", "-- Mixed --"), p["title"]
    uids = {t["datasource"]["uid"] for _, t in queries(b)}
    assert uids <= {"agk-prometheus", "agk-loki"}
    assert {t["datasource"]["type"] for _, t in queries(b)} <= {"prometheus", "loki"}


@pytest.mark.parametrize("path, uid", [(LIVE, "agk-live"), (HISTORY, "agk-history")], ids=["live", "history"])
def test_board_has_no_instance_ids(path, uid):
    text = path.read_text(encoding="utf-8")
    b = json.loads(text)
    assert "id" not in b
    assert b["uid"] == uid
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
DERIVED = {"ord", "short", "slot", "attempt", "type", "key"}
# attributes of the Loki events (structured metadata)
LOKI_FIELDS = {"tool_name", "duration_ms"}
# Attributes the history board (#314) adds, read as Loki structured metadata. No real data confirmed them yet.
# The role of an event, as in the recording rules (agk.yml):
LOKI_ROLE_FIELDS = {"query_source", "agent_name"}
# The tool details (OTEL_LOG_TOOL_DETAILS=1): the JSON attribute and the keys the board reads from it:
LOKI_TOOL_FIELDS = {"tool_parameters", "file_path", "full_command"}
# The token counts and the model of a claude_code.api_request event:
LOKI_API_FIELDS = {"input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "model"}
# Labels the history board makes in its LogQL pipelines (label_format), and the parser error labels it drops:
LOKI_DERIVED = {"agk_role", "agk_in_launch", "agk_target", "agk_context", "agk_tool", "agk_tokens", "agk_doc",
                "__error__", "__error_details__"}
LOKI_ALL = LOKI_FIELDS | LOKI_ROLE_FIELDS | LOKI_TOOL_FIELDS | LOKI_API_FIELDS | LOKI_DERIVED
EVENTS = {"claude_code.tool_result", "claude_code.api_request", "claude_code.api_error", "codex.api_request"}


def _strings(expr):
    return re.findall(r'"((?:[^"\\]|\\.)*)"', expr)


def _strip_strings(expr):
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', expr)


def _strip_templates(expr):
    """LogQL text without its Go templates (backtick strings) and quoted strings."""
    return _strip_strings(re.sub(r"`[^`]*`", '""', expr))


@BOARDS
def test_queries_use_known_names(load):
    known = _header_series() | EXTRA_SERIES | RECORDED | FACTS
    assert "codex_turn_token_usage_sum" in known  # the header was read
    labels_ok = LABELS | DERIVED | LOKI_ALL
    for title, t in queries(load()):
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
            assert lab in LOKI_ALL, (title, lab)
        if t["datasource"]["type"] == "loki":
            lines = [s for s in _strings(expr) if re.match(r"(claude_code|codex)\.", s)]
            assert lines, title
            assert set(lines) <= EVENTS, (title, lines)
            plain = _strip_templates(expr)
            # label filters, parsers, label_format and drop name only known fields
            for lab in re.findall(r"\|\s*(\w+)\s*(?:=~|!~|!=|==|=|<=|>=|<|>)", plain):
                assert lab in LOKI_ALL, (title, lab)
            for m in re.finditer(r"\|\s*(?:json|label_format|drop)\s+([^|]*)", plain):
                for lab in re.findall(r"(\w+)\s*(?:=|,|$)", m.group(1)):
                    assert lab in LOKI_ALL, (title, lab)
            # the fields a template reads
            for tpl in re.findall(r"\{\{(.*?)\}\}", expr):
                for lab in re.findall(r"(?<![\w\\])\.(\w+)", _strip_strings(tpl)):
                    assert lab in LOKI_ALL, (title, lab)
    # the variables use known names too
    for v in load()["templating"]["list"]:
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


# --- the history board (issue #314) ---------------------------------------------------------------------
HISTORY_PANELS = [
    ("Tokens per stage, by role", "barchart"),
    ("Active time per stage, by role", "barchart"),
    ("Token kinds per stage", "barchart"),
    ("Selected stage: tokens per issue, by role", "barchart"),
    ("Most expensive issues of all stages", "barchart"),
    ("Steps of the launch", "timeseries"),
    ("Launches of the issue", "table"),
    ("Steps of the launch (table)", "table"),
    ("Kit document reads per role", "barchart"),
]
PALETTE = set(ROLE_COLOURS.values()) | set(KIND_COLOURS.values()) | {ROSE, TEAL, "transparent"}


def htop():
    return {p["title"]: p for p in history()["panels"]}


def test_history_board_header():
    b = history()
    assert b["title"] == "Stages"
    assert [v["name"] for v in b["templating"]["list"]] == ["project", "stage", "issue", "launch"]
    # the lists of earlier stages do not depend on the board range: an instant query over the stored year
    for v in b["templating"]["list"]:
        assert v["query"]["query"].startswith("query_result(")
        assert "[365d]" in v["query"]["query"]


def test_history_panel_types():
    b = history()
    assert [(p["title"], p["type"]) for p in b["panels"]] == HISTORY_PANELS
    assert {p["type"] for p in panels(b)} <= ALLOWED_TYPES
    assert [p["title"] for p in panels(b) if p["type"] == "table"] == ["Launches of the issue",
                                                                        "Steps of the launch (table)"]
    t = htop()
    for title in ("Tokens per stage, by role", "Active time per stage, by role", "Token kinds per stage",
                  "Selected stage: tokens per issue, by role", "Most expensive issues of all stages"):
        assert t[title]["options"]["stacking"] == "normal", title
    assert t["Most expensive issues of all stages"]["options"]["orientation"] == "horizontal"
    assert "topk(10," in t["Most expensive issues of all stages"]["targets"][0]["expr"]
    # panel 4 is the live panel 2 for the selected stage: the same query, with the issues of a closed stage too
    live2 = top(board())["Tokens per issue, by role"]["targets"][0]["expr"]
    info = 'agk_issue_info{agk_project="$project",stage="$stage"}'
    own = t["Selected stage: tokens per issue, by role"]["targets"][0]["expr"]
    assert own == live2.replace(info, f"topk by (issue) (1, last_over_time({info}[365d]))")
    # panel 6: bars for the tool calls (rose above 2 minutes), a line for the context size
    steps = t["Steps of the launch"]
    assert steps["fieldConfig"]["defaults"]["custom"]["drawStyle"] == "bars"
    by_ref = {x["refId"]: x["expr"] for x in steps["targets"]}
    assert "| duration_ms <= 120000" in by_ref["A"] and "| duration_ms > 120000" in by_ref["C"]
    assert "add (int .input_tokens) (int .cache_read_tokens) (int .cache_creation_tokens)" in by_ref["B"]
    line = next(o for o in steps["fieldConfig"]["overrides"] if o["matcher"] == {"id": "byFrameRefID", "options": "B"})
    assert {"id": "custom.drawStyle", "value": "line"} in line["properties"]
    assert steps["targets"][0]["legendFormat"] == "{{tool_name}} · {{agk_target}}"  # the hover: tool and target
    # panel 9: one bar per role, the documents only in the hover
    reads = t["Kit document reads per role"]
    assert reads["options"]["xField"] == "role" and reads["options"]["colorByField"] == "role"
    assert reads["fieldConfig"]["defaults"]["custom"]["hideFrom"] == {"legend": True, "tooltip": False, "viz": True}
    over = next(o for o in reads["fieldConfig"]["overrides"] if o["matcher"]["options"] == "reads")
    assert over["properties"] == [{"id": "custom.hideFrom", "value": {"legend": True, "tooltip": False, "viz": False}}]


def _link(panel):
    links = panel["fieldConfig"]["defaults"]["links"]
    assert len(links) == 1
    return links[0]["url"]


def test_history_drilldown_links():
    t = htop()
    for title in ("Tokens per stage, by role", "Active time per stage, by role", "Token kinds per stage"):
        url = _link(t[title])
        assert "var-stage=${__data.fields.stage}" in url, title
        assert "var-issue" not in url and "var-launch" not in url
    for title in ("Selected stage: tokens per issue, by role", "Most expensive issues of all stages"):
        assert "var-issue=${__data.fields.issue}" in _link(t[title]), title
    assert "var-stage=${__data.fields.stage}" in _link(t["Most expensive issues of all stages"])
    url = _link(t["Launches of the issue"])
    assert "var-launch=${__data.fields.launch}" in url
    # the time range of the launch, relative to now, so the fixed range of the other panels holds
    assert "&from=now-${__data.fields.from}s&to=now-${__data.fields.to}s" in url
    for p in history()["panels"]:
        if "links" in p["fieldConfig"]["defaults"]:
            url = _link(p)
            assert url.startswith("/d/agk-history/stages?var-project=${project:percentencode}"), p["title"]
            assert "${__from}" not in url and "${__to}" not in url  # an absolute range would end the fixed ranges
    # the fields the links read: the regexp that takes stage and issue from the bar label
    for title, sample, want in (
            ("Selected stage: tokens per issue, by role", "03 · 314 · History board: char", {"issue": "314"}),
            ("Most expensive issues of all stages", "308 · #313", {"stage": "308", "issue": "313"})):
        ext = next(x for x in t[title]["transformations"] if x["id"] == "extractFields")["options"]
        assert ext["format"] == "regexp"
        m = re.match(ext["regExp"].strip("/").replace("(?<", "(?P<"), sample)
        assert m and m.groupdict() == want, title
    # the link fields of the launches table: start and end of the launch in seconds before now
    by_ref = {x["refId"]: x["expr"] for x in t["Launches of the issue"]["targets"]}
    assert by_ref["F"].startswith("time() - min by (key)") and by_ref["F"].endswith("+ 60")
    assert by_ref["G"].startswith("time() - max by (key)")
    for ref in ("F", "G"):
        assert "timestamp(agk:active_seconds:1m{" in by_ref[ref]


def _visible_columns(panel):
    organize = next(x for x in panel["transformations"] if x["id"] == "organize")["options"]
    index, rename = organize["indexByName"], organize["renameByName"]
    hidden = {o["matcher"]["options"] for o in panel["fieldConfig"]["overrides"]
              if {"id": "custom.hidden", "value": True} in o["properties"]}
    names = [rename.get(n, n) for n in sorted(index, key=index.get)]
    keep = next(x for x in panel["transformations"] if x["id"] == "filterFieldsByName")["options"]["include"]["names"]
    assert keep == sorted(index, key=index.get)
    return [n for n in names if n not in hidden], [n for n in names if n in hidden]


def test_history_table_columns():
    t = htop()
    shown, hidden = _visible_columns(t["Launches of the issue"])
    assert shown == ["issue", "role", "tokens", "active time", "return", "model", "start"]
    assert hidden == ["launch", "from", "to"]
    shown, hidden = _visible_columns(t["Steps of the launch (table)"])
    assert shown == ["step", "tool", "target", "duration", "tokens", "time"]
    assert hidden == []
    for title in ("Launches of the issue", "Steps of the launch (table)"):
        p = t[title]
        assert p["fieldConfig"]["defaults"]["custom"]["wrapText"] is False
        assert "width" not in p["fieldConfig"]["defaults"]["custom"]
        assert "minWidth" not in p["fieldConfig"]["defaults"]["custom"]
        for o in p["fieldConfig"]["overrides"]:
            for prop in o["properties"]:
                assert prop["id"] not in ("custom.width", "custom.minWidth"), (title, o["matcher"])


def test_history_colours():
    t = htop()
    for title in ("Tokens per stage, by role", "Active time per stage, by role",
                  "Selected stage: tokens per issue, by role", "Most expensive issues of all stages"):
        got = colour_overrides(t[title])
        for role, colour in ROLE_COLOURS.items():
            assert got[role] == colour, (title, role)
    got = colour_overrides(t["Token kinds per stage"])
    for kind, colour in KIND_COLOURS.items():
        assert got[kind] == colour
    for title in ("Launches of the issue", "Kit document reads per role"):
        got = mapping_colours(t[title])
        for role, colour in ROLE_COLOURS.items():
            assert got[role] == colour, (title, role)
    # the long tool calls in rose: the bars of query C and the duration cell above 2 minutes
    steps = t["Steps of the launch"]
    c = next(o for o in steps["fieldConfig"]["overrides"] if o["matcher"] == {"id": "byFrameRefID", "options": "C"})
    assert c["properties"] == [{"id": "color", "value": {"mode": "fixed", "fixedColor": ROSE}}]
    dur = next(o for o in t["Steps of the launch (table)"]["fieldConfig"]["overrides"]
               if o["matcher"]["options"] == "duration")
    steps_of = next(p["value"]["steps"] for p in dur["properties"] if p["id"] == "thresholds")
    assert steps_of[-1] == {"color": ROSE, "value": 120000}
    # no colour outside the palette of the live board, anywhere in the board
    text = HISTORY.read_text(encoding="utf-8")
    used = set(re.findall(r'"(?:fixedColor|color)":\s*"([^"]+)"', text))
    assert used and used <= PALETTE, used - PALETTE


def test_history_typical_stage_needs_three_stages():
    t = htop()
    guard = re.compile(r"and on \(\) \(count\(count by \(stage\) \(last_over_time\([^)]*\[365d\]\)\)\) >= 3\)")
    for title in ("Tokens per stage, by role", "Active time per stage, by role"):
        typical = [x for x in t[title]["targets"] if x["refId"] == "B"][0]
        assert "quantile(0.5, sum by (stage) (" in typical["expr"]
        assert 'stage!="$stage"' in typical["expr"]
        assert guard.search(typical["expr"]), title
        assert typical.get("hide") is True
        assert "not drawn" in t[title]["description"]


def test_history_time_ranges():
    """Panels 1-5 and 7 keep one year, panel 9 30 days (Loki refuses longer queries); the steps follow the board."""
    t = htop()
    for title, _ in HISTORY_PANELS:
        want = {"Steps of the launch": None, "Steps of the launch (table)": None,
                "Kit document reads per role": "30d"}.get(title, "365d")
        assert t[title].get("timeFrom") == want, title
    assert history()["time"] == {"from": "now-24h", "to": "now"}


def test_history_steps_of_the_launch_only():
    t = htop()
    role = re.compile(r'label_format agk_role=`\{\{ if eq \.query_source "main" \}\}orchestrator')
    launch = '"$launch" }}1{{ end }}` | agk_in_launch="1"'
    for title in ("Steps of the launch", "Steps of the launch (table)"):
        p = t[title]
        for x in p["targets"]:
            assert role.search(x["expr"]) and launch in x["expr"], (title, x["refId"])
        assert "qa-codex" in p["description"] and "#322" in p["description"], title
    # the agent names map to the roles of the recording rules
    rules = RULES.read_text(encoding="utf-8")
    for name in ("software-engineer", "frontend-engineer", "qa-engineer", "planner"):
        assert name in rules and f'"{name}"' in t["Steps of the launch"]["targets"][0]["expr"]


def test_history_kit_documents():
    expr = htop()["Kit document reads per role"]["targets"][0]["expr"]
    assert '| tool_name="Read"' in expr
    rx = re.search(r'agk_doc=~"([^"]+)"', expr).group(1).replace("\\\\", "\\")
    cut = re.search(r'regexReplaceAll "([^"]+)" \.file_path', expr).group(1).replace("\\\\", "\\")
    for path, doc in (("/home/u/repo/docs/team/pm.md", "docs/team/pm.md"), ("/r/AGENTS.md", "AGENTS.md"),
                      ("/r/CLAUDE.md", "CLAUDE.md"), ("/r/.agents/skills/x/SKILL.md", ".agents/skills/x/SKILL.md"),
                      ("/r/plugin/skills/monitor/SKILL.md", "plugin/skills/monitor/SKILL.md"),
                      ("/r/src/app.py", None), ("/r/README.md", None), ("/r/MY_AGENTS.md", None)):
        got = re.sub(cut, r"\1", path)
        assert (got if re.fullmatch(rx, got) else None) == doc, path
