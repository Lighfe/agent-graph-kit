"""Tests for the two Grafana alert rules of the monitor skill (issue #327): `Runaway issue` and `Stuck launch`.

No test starts Grafana or uses the network: the tests read the provisioning file, `compose.yaml` and the
part of `board.py` that writes the two limits into the file. All data is synthetic."""

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from test_monitor_stack import read_yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
ALERTS = SKILL / "grafana" / "provisioning" / "alerting" / "agk-alerts.yaml"
COMPOSE = SKILL / "compose.yaml"
BOARD = SKILL / "board.py"
DEFAULTS = {"AGK_ALERT_ISSUE_TOKENS": "23000000", "AGK_ALERT_STUCK_MINUTES": "45"}
# The fields of an alert file in which Grafana expands environment variables (found on Grafana 13.2.4).
EXPANDED_FIELDS = ("uid", "title", "for", "condition", "noDataState", "execErrState")


def board_module():
    spec = importlib.util.spec_from_file_location("monitor_board_for_alert_tests", BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rules(doc=None):
    doc = read_yaml(ALERTS) if doc is None else doc
    return {r["title"]: {**r, "group": g} for g in doc["groups"] for r in g["rules"]}


def query(rule):
    (q,) = [d for d in rule["data"] if d["datasourceUid"] != "__expr__"]
    return q


def rendered(tmp_path, limits=DEFAULTS):
    """The alert file as `board.py up` writes it for Grafana, read back."""
    path = tmp_path / "rendered.yaml"
    path.write_text(board_module().render_alerts(ALERTS.read_text(encoding="utf-8"), limits), encoding="utf-8")
    return read_yaml(path)


# --- the file ---------------------------------------------------------------------------------

def test_the_file_parses_and_has_the_two_rules_in_folder_agk():
    doc = read_yaml(ALERTS)
    assert doc["apiVersion"] == 1
    assert sorted(rules(doc)) == ["Runaway issue", "Stuck launch"]
    for group in doc["groups"]:
        assert group["folder"] == "agk"
        assert group["orgId"] == 1
        assert re.fullmatch(r"\d+[sm]", group["interval"])
    assert len({r["uid"] for r in rules(doc).values()}) == 2


def test_the_file_agrees_with_pyyaml_when_present():
    yaml = pytest.importorskip("yaml")
    assert read_yaml(ALERTS) == yaml.safe_load(ALERTS.read_text(encoding="utf-8"))


def test_data_source_no_data_state_and_no_contact_point():
    doc = read_yaml(ALERTS)
    # only rule groups: no contact point, no notification policy, no template, so nothing needs a secret
    assert sorted(doc) == ["apiVersion", "groups"]
    for title, rule in rules(doc).items():
        assert query(rule)["datasourceUid"] == "agk-prometheus", title
        assert sorted(d["datasourceUid"] for d in rule["data"]) == ["__expr__", "agk-prometheus"], title
        assert rule["noDataState"] == "OK", title
        assert "notification_settings" not in rule and "receiver" not in json.dumps(rule), title
    text = ALERTS.read_text(encoding="utf-8").lower()
    for word in ("contactpoint", "webhook", "smtp", "slack", "password", "token:", "url:"):
        assert word not in text, word


def test_each_rule_fires_on_any_series_of_its_query():
    """The limit is part of the query, so the condition is: the query gives a series (value above 0)."""
    for title, rule in rules().items():
        (expr,) = [d for d in rule["data"] if d["datasourceUid"] == "__expr__"]
        assert rule["condition"] == expr["refId"], title
        model = expr["model"]
        assert model["type"] == "threshold" and model["expression"] == query(rule)["refId"], title
        assert model["conditions"] == [{"evaluator": {"type": "gt", "params": [0]}}], title
        assert query(rule)["model"]["instant"] is True, title


# --- Runaway issue ----------------------------------------------------------------------------

def test_runaway_issue_query():
    rule = rules()["Runaway issue"]
    expr = query(rule)["model"]["expr"]
    assert expr == ('sum by (agk_project, issue) (sum_over_time(agk:tokens:1m{issue!=""}[365d]))'
                    ' > ${AGK_ALERT_ISSUE_TOKENS}')
    # all token kinds, Claude and Codex together: no filter but the non-empty issue
    assert re.findall(r"\{([^}]*)\}", expr.replace("${AGK_ALERT_ISSUE_TOKENS}", "")) == ['issue!=""']
    assert rule["for"] == "0s"


def test_runaway_window_is_the_prometheus_retention():
    command = read_yaml(COMPOSE)["services"]["prometheus"]["command"]
    assert "--storage.tsdb.retention.time=365d" in command
    assert "[365d]" in query(rules()["Runaway issue"])["model"]["expr"]


def test_runaway_issue_with_the_default_limit(tmp_path):
    rule = rules(rendered(tmp_path))["Runaway issue"]
    assert query(rule)["model"]["expr"].endswith("[365d])) > 23000000")
    assert "23000000 tokens" in rule["annotations"]["summary"]


# --- Stuck launch -----------------------------------------------------------------------------

def test_stuck_launch_query():
    rule = rules()["Stuck launch"]
    expr = query(rule)["model"]["expr"]
    assert expr == ("agk_launch_open unless on (agk_project, issue)"
                    " ((max_over_time(agk:tokens:1m[2m]) != 0) or (min_over_time(agk:tokens:1m[2m]) != 0))")
    # samples of agk:tokens:1m can be below 0, so the query never adds them up: +100 and -100 give 0
    assert "sum" not in expr
    assert rule["for"] == "${AGK_ALERT_STUCK_MINUTES}m"
    # the look-back of the query covers at least one run of the rule, so no counted minute is missed
    assert rule["group"]["interval"] == "1m"


def test_stuck_launch_with_the_default_limit(tmp_path):
    rule = rules(rendered(tmp_path))["Stuck launch"]
    assert rule["for"] == "45m"
    assert "45 minutes" in rule["annotations"]["summary"]
    other = rules(rendered(tmp_path, {**DEFAULTS, "AGK_ALERT_STUCK_MINUTES": "90"}))["Stuck launch"]
    assert other["for"] == "90m"


# The behaviour of the `Stuck launch` query over time, run by `promtool test rules` in the Prometheus image of
# compose.yaml: the query of the alert file as a Prometheus alert rule with `for: 45m`, on synthetic series.
# Each case: (name, series of agk:tokens:1m as (labels, one value for each minute), minutes at which the
# alert fires, minutes at which it does not fire). The launch is open for the whole time.
PROMETHEUS_IMAGE = read_yaml(COMPOSE)["services"]["prometheus"]["image"]
TOKENS = 'agk_project="p", stage="s1", issue="10", role="engineer", launch="engineer-1", model="m"'
STUCK_CASES = [
    ("no_token_series", [], [46, 90], [44]),
    ("only_zero_samples", [(TOKENS + ', kind="output"', [0] * 91)], [46, 90], [44]),
    # the case of the QA return: +100 and -100 in turn add up to 0 in every window of two minutes
    ("plus_and_minus_in_turn", [(TOKENS + ', kind="output"', [100, -100] * 45 + [100])], [], [44, 46, 60, 90]),
    # two token kinds that add up to 0 in each minute
    ("two_kinds_cancel", [(TOKENS + ', kind="output"', [100] * 91), (TOKENS + ', kind="cache_read"', [-100] * 91)],
     [], [46, 90]),
    # one counted token at minute 30 starts the time again: the windows of 30m and 31m hold it
    ("one_token_starts_the_time_again", [(TOKENS + ', kind="output"', [0] * 30 + [1] + [0] * 60)], [78, 90], [46, 76]),
    ("one_minute_below_zero_starts_the_time_again", [(TOKENS + ', kind="output"', [0] * 30 + [-5] + [0] * 60)],
     [78, 90], [46, 76]),
    # tokens of another issue of the project are not tokens of this launch
    ("tokens_of_another_issue", [(TOKENS.replace('issue="10"', 'issue="11"') + ', kind="output"', [100] * 91)],
     [46, 90], [44]),
]


def promtool_available():
    probe = subprocess.run(["docker", "image", "inspect", PROMETHEUS_IMAGE], capture_output=True)
    return probe.returncode == 0


def stuck_promtool_files(expr, cases):
    """The rule file and the test file for `promtool test rules`, as text."""
    rule = ("groups:\n  - name: stuck\n    interval: 1m\n    rules:\n      - alert: StuckLaunch\n"
            f"        expr: '{expr}'\n        for: 45m\n")
    fired = ('              - exp_labels:\n                  agk_project: p\n                  stage: s1\n'
             '                  issue: "10"\n                  role: engineer\n                  launch: engineer-1\n')
    out = ["rule_files:\n  - rule.yml\nevaluation_interval: 1m\ntests:\n"]
    for name, series, firing, quiet in cases:
        out.append(f"  - name: {name}\n    interval: 1m\n    input_series:\n")
        out.append("      - series: 'agk_launch_open{agk_project=\"p\", stage=\"s1\", issue=\"10\", role=\"engineer\","
                   " launch=\"engineer-1\"}'\n        values: '1x90'\n")
        for labels, values in series:
            out.append(f"      - series: 'agk:tokens:1m{{{labels}}}'\n        values: '{' '.join(map(str, values))}'\n")
        out.append("    alert_rule_test:\n")
        for minute in sorted(firing + quiet):
            out.append(f"      - eval_time: {minute}m\n        alertname: StuckLaunch\n")
            out.append("        exp_alerts:\n" + fired if minute in firing else "        exp_alerts: []\n")
    return rule, "".join(out)


def run_promtool(tmp_path, expr, cases):
    rule, test = stuck_promtool_files(expr, cases)
    (tmp_path / "rule.yml").write_text(rule, encoding="utf-8")
    (tmp_path / "test.yaml").write_text(test, encoding="utf-8")
    return subprocess.run(["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                           "-v", f"{tmp_path}:/r:ro", "--entrypoint", "promtool", PROMETHEUS_IMAGE,
                           "test", "rules", "/r/test.yaml"], capture_output=True, text=True, timeout=120)


def test_stuck_cases_are_valid_yaml_for_promtool(tmp_path):
    expr = query(rules(rendered(tmp_path))["Stuck launch"])["model"]["expr"]
    rule, test = stuck_promtool_files(expr, STUCK_CASES)
    (tmp_path / "rule.yml").write_text(rule, encoding="utf-8")
    (tmp_path / "test.yaml").write_text(test, encoding="utf-8")
    assert read_yaml(tmp_path / "rule.yml")["groups"][0]["rules"][0]["expr"] == expr
    assert [t["name"] for t in read_yaml(tmp_path / "test.yaml")["tests"]] == [c[0] for c in STUCK_CASES]


@pytest.mark.skipif(not promtool_available(), reason="needs Docker and the local Prometheus image of compose.yaml")
def test_stuck_launch_over_time(tmp_path):
    expr = query(rules(rendered(tmp_path))["Stuck launch"])["model"]["expr"]
    res = run_promtool(tmp_path, expr, STUCK_CASES)
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.skipif(not promtool_available(), reason="needs Docker and the local Prometheus image of compose.yaml")
def test_a_query_that_adds_the_samples_up_fails_the_cases(tmp_path):
    # the query of the first version: the cases catch it, so they do check the cancellation
    old = ("agk_launch_open unless on (agk_project, issue)"
           " (sum by (agk_project, issue) (sum_over_time(agk:tokens:1m[2m])) != 0)")
    res = run_promtool(tmp_path, old, STUCK_CASES)
    assert res.returncode != 0
    assert "plus_and_minus_in_turn" in res.stdout + res.stderr


# --- the two variables ------------------------------------------------------------------------

def test_the_file_names_only_the_two_variables():
    text = "\n".join(line for line in ALERTS.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    assert set(re.findall(r"\$\{([A-Z_]+)\}", text)) == set(DEFAULTS)


def test_no_dollar_sign_is_left_where_grafana_expands_variables(tmp_path):
    """Grafana expands `$NAME` in these fields, so after `board.py` wrote the limits none may hold a `$`.
    A query model and an annotation are not expanded: `$labels` there has one dollar sign."""
    doc = rendered(tmp_path)
    assert "${" not in json.dumps(doc)
    for title, rule in rules(doc).items():
        for field in EXPANDED_FIELDS:
            assert "$" not in str(rule[field]), (title, field)
        for d in rule["data"]:
            assert "$" not in d["refId"] + d["datasourceUid"], title
        assert "$" not in rule["group"]["name"] + rule["group"]["folder"] + rule["group"]["interval"], title
        assert "$$" not in json.dumps(rule), title
        assert "{{ $labels.agk_project }}" in rule["annotations"]["summary"], title


def test_compose_sets_both_variables_for_grafana_with_the_defaults():
    compose = read_yaml(COMPOSE)
    env = compose["services"]["grafana"]["environment"]
    assert env["AGK_ALERT_ISSUE_TOKENS"] == "${AGK_ALERT_ISSUE_TOKENS:-23000000}"
    assert env["AGK_ALERT_STUCK_MINUTES"] == "${AGK_ALERT_STUCK_MINUTES:-45}"
    assert board_module().ALERT_LIMITS == DEFAULTS
    for name, svc in compose["services"].items():
        for p in svc["ports"]:
            assert p.startswith("127.0.0.1:"), f"{name}: {p}"


def test_compose_puts_the_written_file_over_the_file_of_the_skill():
    compose = read_yaml(COMPOSE)
    assert {"source": "agk_alerts", "target": "/etc/grafana/provisioning/alerting/agk-alerts.yaml"} in \
        compose["services"]["grafana"]["configs"]
    assert compose["configs"]["agk_alerts"]["file"] == \
        "${AGK_ALERTS_FILE:-./grafana/provisioning/alerting/agk-alerts.yaml}"
    assert (SKILL / "grafana/provisioning/alerting/agk-alerts.yaml").is_file()
    mounts = {v["target"]: v["source"] for v in compose["services"]["grafana"]["volumes"]}
    assert mounts["/etc/grafana/provisioning"] == "./grafana/provisioning"


# --- board.py writes the limits ---------------------------------------------------------------

def test_alert_limits_defaults_and_environment(monkeypatch):
    board = board_module()
    for name in DEFAULTS:
        monkeypatch.delenv(name, raising=False)
    assert board.alert_limits() == DEFAULTS
    monkeypatch.setenv("AGK_ALERT_ISSUE_TOKENS", "5000000")
    monkeypatch.setenv("AGK_ALERT_STUCK_MINUTES", "")
    assert board.alert_limits() == {"AGK_ALERT_ISSUE_TOKENS": "5000000", "AGK_ALERT_STUCK_MINUTES": "45"}


@pytest.mark.parametrize("value", ["0", "-5", "1.5", "45m", "ten", "1) or vector(1", "1e6", "$X"])
def test_alert_limits_refuses_what_is_not_a_whole_number(monkeypatch, value):
    monkeypatch.setenv("AGK_ALERT_STUCK_MINUTES", value)
    with pytest.raises(ValueError, match="AGK_ALERT_STUCK_MINUTES"):
        board_module().alert_limits()


FAKE_DOCKER = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a") as f:
    f.write(json.dumps({{"args": args, "env": {{k: v for k, v in os.environ.items() if k.startswith("AGK_")}}}}) + "\\n")
if args[:2] == ["network", "inspect"]:
    print("[]")
sys.exit(0)
"""


def free_port():
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Rig:
    """`board.py` with a fake `docker` and a project list, in a temp state dir. No facts.py starts:
    the fake `docker network inspect` gives no gateway address."""

    def __init__(self, tmp):
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.state = tmp / "state" / "agent-graph-kit"
        self.state.mkdir(parents=True)
        (self.state / "monitor-projects.json").write_text(json.dumps([{"project": "own/demo", "repo": str(tmp)}]))
        self.log = tmp / "docker.log"
        docker = self.bin / "docker"
        docker.write_text(FAKE_DOCKER.format(python=sys.executable))
        docker.chmod(0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGK_")}
        env.update(PATH=str(self.bin), HOME=str(tmp), XDG_STATE_HOME=str(tmp / "state"),
                   FAKE_DOCKER_LOG=str(self.log), AGK_FACTS_PORT=str(free_port()))
        self.env = env
        self.cwd = tmp

    @property
    def alerts_file(self):
        return self.state / "monitor-alerts.yaml"

    def run(self, *args, **env):
        return subprocess.run([sys.executable, str(BOARD), *args], capture_output=True, text=True,
                              timeout=60, cwd=self.cwd, env={**self.env, **env})

    def up_env(self):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        ups = [c["env"] for c in calls if c["args"][:1] == ["compose"] and "up" in c["args"]]
        return ups[0] if ups else None


def test_up_writes_the_alert_file_with_the_default_limits(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up")
    assert res.returncode == 0, res.stdout + res.stderr
    assert stat.S_IMODE(rig.alerts_file.stat().st_mode) == 0o600
    written = rules(read_yaml(rig.alerts_file))
    assert query(written["Runaway issue"])["model"]["expr"].endswith(" > 23000000")
    assert written["Stuck launch"]["for"] == "45m"
    env = rig.up_env()
    assert env["AGK_ALERTS_FILE"] == str(rig.alerts_file.resolve())
    assert env["AGK_ALERT_ISSUE_TOKENS"] == "23000000" and env["AGK_ALERT_STUCK_MINUTES"] == "45"
    assert re.fullmatch(r"[0-9a-f]{16}", env["AGK_ALERTS_VERSION"])
    # the file of the skill is not changed
    assert "${AGK_ALERT_ISSUE_TOKENS}" in ALERTS.read_text(encoding="utf-8")


def test_up_with_other_limits_writes_them_and_changes_the_version(tmp_path):
    rig = Rig(tmp_path)
    rig.run("up")
    first = rig.up_env()["AGK_ALERTS_VERSION"]
    rig.log.unlink()
    res = rig.run("up", AGK_ALERT_ISSUE_TOKENS="7000000", AGK_ALERT_STUCK_MINUTES="20")
    assert res.returncode == 0, res.stdout + res.stderr
    written = rules(read_yaml(rig.alerts_file))
    assert query(written["Runaway issue"])["model"]["expr"].endswith(" > 7000000")
    assert written["Stuck launch"]["for"] == "20m"
    env = rig.up_env()
    assert (env["AGK_ALERT_ISSUE_TOKENS"], env["AGK_ALERT_STUCK_MINUTES"]) == ("7000000", "20")
    assert env["AGK_ALERTS_VERSION"] != first
    # the same limits again give the same version, so Grafana is not started again for nothing
    rig.log.unlink()
    rig.run("up", AGK_ALERT_ISSUE_TOKENS="7000000", AGK_ALERT_STUCK_MINUTES="20")
    assert rig.up_env()["AGK_ALERTS_VERSION"] == env["AGK_ALERTS_VERSION"]


def test_up_with_a_bad_limit_starts_nothing(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up", AGK_ALERT_ISSUE_TOKENS="lots")
    assert res.returncode == 2
    assert "AGK_ALERT_ISSUE_TOKENS" in res.stderr and "Nothing was started" in res.stderr
    assert rig.up_env() is None
    assert not rig.alerts_file.exists()


def test_down_needs_no_alert_file_and_no_limit(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("down", AGK_ALERT_ISSUE_TOKENS="lots")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not rig.alerts_file.exists()


@pytest.mark.skipif(subprocess.run(["sh", "-c", "docker compose version"], capture_output=True).returncode != 0,
                    reason="docker compose not installed")
def test_docker_compose_reads_the_alert_settings(tmp_path):
    """`docker compose config` (no daemon): the defaults, and the values and the file of `board.py up`."""
    pw = tmp_path / "pw"
    pw.write_text("x")
    alerts = tmp_path / "alerts.yaml"
    alerts.write_text("apiVersion: 1\n")
    base = dict(os.environ, AGK_UID="1000", AGK_GID="1000", AGK_GRAFANA_ADMIN_FILE=str(pw),
                AGK_PROJECT_PATTERN="^(a/b)$")
    for name in (*DEFAULTS, "AGK_ALERTS_FILE", "AGK_ALERTS_VERSION"):
        base.pop(name, None)

    def config(**extra):
        res = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "config", "--format", "json"],
                             capture_output=True, text=True, env={**base, **extra}, cwd=tmp_path)
        assert res.returncode == 0, res.stderr
        return json.loads(res.stdout)

    cfg = config()
    env = cfg["services"]["grafana"]["environment"]
    assert (env["AGK_ALERT_ISSUE_TOKENS"], env["AGK_ALERT_STUCK_MINUTES"]) == ("23000000", "45")
    assert cfg["configs"]["agk_alerts"]["file"] == str(ALERTS)
    cfg = config(AGK_ALERT_ISSUE_TOKENS="7000000", AGK_ALERT_STUCK_MINUTES="20", AGK_ALERTS_FILE=str(alerts),
                 AGK_ALERTS_VERSION="abc")
    env = cfg["services"]["grafana"]["environment"]
    assert (env["AGK_ALERT_ISSUE_TOKENS"], env["AGK_ALERT_STUCK_MINUTES"]) == ("7000000", "20")
    assert env["AGK_ALERTS_VERSION"] == "abc"
    assert cfg["configs"]["agk_alerts"]["file"] == str(alerts)
    for svc in cfg["services"].values():
        assert all(p["host_ip"] == "127.0.0.1" for p in svc["ports"])
