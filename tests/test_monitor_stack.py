"""Tests for the monitoring stack of the monitor skill (issue #309): `compose.yaml`, `otel/` and `grafana/`.

No test needs a Docker daemon or the network. All data is synthetic."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
COMPOSE = SKILL / "compose.yaml"
OTEL = SKILL / "otel"
GRAFANA = SKILL / "grafana"
SERVICES = ["collector", "prometheus", "loki", "grafana"]


# --- a small YAML reader for the block style of these files (the test env has no PyYAML) -------

KEY = re.compile(r"^([A-Za-z0-9_.\-/]+):(?:\s+(.*))?$")


def _strip_comment(line):
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return {"true": True, "false": False, "null": None, "~": None}.get(text, text)


def _block(lines, i, indent):
    if lines[i][1].startswith("-"):
        out = []
        while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("-"):
            rest = lines[i][1][1:].strip()
            if not rest:
                value, i = _block(lines, i + 1, lines[i + 1][0])
            elif KEY.match(rest):
                lines[i] = (indent + 2, rest)
                value, i = _block(lines, i, indent + 2)
            else:
                value, i = _scalar(rest), i + 1
            out.append(value)
        return out, i
    out = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("-"):
        m = KEY.match(lines[i][1])
        assert m, f"not a key line: {lines[i][1]!r}"
        key, rest = m.group(1), m.group(2)
        i += 1
        if rest:
            out[key] = _scalar(rest)
        elif i < len(lines) and (lines[i][0] > indent or lines[i][1].startswith("-") and lines[i][0] == indent):
            out[key], i = _block(lines, i, lines[i][0])
        else:
            out[key] = None
    return out, i


def read_yaml(path):
    lines = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw)
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    value, i = _block(lines, 0, lines[0][0])
    assert i == len(lines), f"{path}: lines left after line {i}"
    return value



def compose():
    return read_yaml(COMPOSE)


def service(name):
    return compose()["services"][name]


def collector():
    return read_yaml(OTEL / "collector.yaml")


def board_module():
    spec = importlib.util.spec_from_file_location("monitor_board_for_stack_tests", SKILL / "board.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- compose.yaml -----------------------------------------------------------------------------

def test_yaml_reader_agrees_with_pyyaml_when_present():
    yaml = pytest.importorskip("yaml")
    paths = [COMPOSE, *sorted(OTEL.glob("*.y*ml")), *sorted((GRAFANA / "provisioning").rglob("*.yaml"))]
    for path in paths:
        assert read_yaml(path) == yaml.safe_load(path.read_text(encoding="utf-8")), path


def test_four_services():
    assert list(compose()["services"]) == SERVICES


def test_images_pinned():
    images = {n: service(n)["image"] for n in SERVICES}
    assert images["collector"].startswith("otel/opentelemetry-collector-contrib:")
    assert images["prometheus"].startswith("prom/prometheus:")
    assert images["loki"].startswith("grafana/loki:")
    assert images["grafana"].startswith("grafana/grafana:")
    for name, image in images.items():
        assert re.fullmatch(r"[a-z/\-]+:v?\d+\.\d+\.\d+", image), f"{name}: {image} is not an exact version"
    assert "latest" not in COMPOSE.read_text(encoding="utf-8").lower()
    # Each tag has its push date in a comment. The newest date must be at least two weeks before
    # 2026-11-13 (the day of the task), so no tag is a fresh release.
    dates = re.findall(r"image: \S+\s+# pushed (\d{4}-\d{2}-\d{2})", COMPOSE.read_text(encoding="utf-8"))
    assert len(dates) == 4
    assert all(d <= "2026-10-30" for d in dates)


def test_all_ports_on_localhost():
    seen = {}
    for name in SERVICES:
        for p in service(name).get("ports", []):
            assert p.startswith("127.0.0.1:"), f"{name}: {p}"
            seen.setdefault(name, []).append(p)
    assert sorted(seen) == sorted(SERVICES)
    wanted = {
        "collector": [("AGK_OTLP_GRPC_PORT", "4317", "4317"), ("AGK_OTLP_HTTP_PORT", "4318", "4318")],
        "prometheus": [("AGK_PROMETHEUS_PORT", "9090", "9090")],
        "loki": [("AGK_LOKI_PORT", "3100", "3100")],
        "grafana": [("AGK_GRAFANA_PORT", "3000", "3000")],
    }
    for name, ports in wanted.items():
        assert seen[name] == [f"127.0.0.1:${{{var}:-{host}}}:{inner}" for var, host, inner in ports]


def test_restart_no():
    for name in SERVICES:
        assert service(name)["restart"] == "no", name


def test_retention_one_year():
    flags = service("prometheus")["command"]
    (retention,) = [f for f in flags if f.startswith("--storage.tsdb.retention.time=")]
    assert days(retention.split("=", 1)[1]) >= 365
    loki = read_yaml(OTEL / "loki.yaml")
    assert days(loki["limits_config"]["retention_period"]) >= 365
    assert loki["compactor"]["retention_enabled"] is True


def days(text):
    m = re.fullmatch(r"(\d+)([dwhy])", str(text))
    assert m, text
    return int(m.group(1)) * {"h": 1 / 24, "d": 1, "w": 7, "y": 365}[m.group(2)]


def test_no_credentials_in_compose():
    text = COMPOSE.read_text(encoding="utf-8")
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_", "OPENAI_", "CODEX_", "CLAUDE_CODE_OAUTH"):
        assert name not in text, name
    assert "/.claude" not in text and "/.codex" not in text and ".config/gh" not in text
    for name in SERVICES:
        for v in service(name).get("volumes", []):
            if v["type"] == "bind":
                assert v["source"].startswith("./"), f"{name}: {v['source']}"
                assert v["read_only"] is True


def test_prometheus_scrapes_facts_and_loads_rules():
    prom = read_yaml(OTEL / "prometheus.yml")
    assert prom["rule_files"] == ["/etc/prometheus/rules/*.yml"]
    (job,) = [j for j in prom["scrape_configs"] if j["job_name"] == "facts"]
    assert job["file_sd_configs"] == [{"files": ["/etc/prometheus/targets/facts.json"]}]
    targets = compose()["configs"]["facts_targets"]["content"]
    assert json.loads(targets.replace("${AGK_FACTS_PORT:-9464}", "9464")) == [
        {"targets": ["host.docker.internal:9464"]}]
    assert "host.docker.internal:host-gateway" in service("prometheus")["extra_hosts"]
    mounts = {v["target"]: v["source"] for v in service("prometheus")["volumes"]}
    assert mounts["/etc/prometheus/rules"] == "./otel/rules"
    assert (OTEL / "rules").is_dir()


def test_grafana_login_rules_and_provisioned_data_sources():
    env = service("grafana")["environment"]
    assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert env["GF_USERS_ALLOW_SIGN_UP"] == "false"
    assert env["GF_SECURITY_ADMIN_PASSWORD__FILE"] == "/run/secrets/grafana_admin"
    assert "GF_SECURITY_ADMIN_PASSWORD" not in env
    for key in ("GF_ANALYTICS_REPORTING_ENABLED", "GF_ANALYTICS_CHECK_FOR_UPDATES",
                "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES", "GF_NEWS_NEWS_FEED_ENABLED"):
        assert env[key] == "false", key
    assert "GF_PLUGINS_PREINSTALL_SYNC" not in env and "GF_PLUGINS_PREINSTALL" not in env
    disabled = env["GF_PLUGINS_DISABLE_PLUGINS"].split(",")
    assert "prometheus" not in disabled and "loki" not in disabled
    assert "frser-sqlite-datasource" not in COMPOSE.read_text(encoding="utf-8")
    files = sorted((GRAFANA / "provisioning" / "datasources").glob("*.yaml"))
    assert [f.name for f in files] == ["loki.yaml", "prometheus.yaml"]
    by_file = {f.name: read_yaml(f)["datasources"] for f in files}
    assert [(s["type"], s["uid"]) for s in by_file["prometheus.yaml"]] == [("prometheus", "agk-prometheus")]
    assert [(s["type"], s["uid"]) for s in by_file["loki.yaml"]] == [("loki", "agk-loki")]
    assert all("sqlite" not in f.read_text(encoding="utf-8").lower() for f in files)


def test_removed_files_are_gone():
    for rel in ("store.py", "grafana/boards/live.json", "grafana/boards/history.json",
                "grafana/boards/monitor-stub.json"):
        assert not (SKILL / rel).exists(), rel
    for rel in ("tests/test_monitor_store.py", "tests/test_monitor_boards.py"):
        assert not (ROOT / rel).exists(), rel


@pytest.mark.skipif(not shutil.which("docker"), reason="docker CLI not installed")
def test_docker_compose_accepts_the_file(tmp_path):
    """`docker compose config` reads the file without a daemon."""
    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0:
        pytest.skip("docker compose not installed")
    pw = tmp_path / "pw"
    pw.write_text("x")
    env = dict(os.environ, AGK_UID="1000", AGK_GID="1000", AGK_GRAFANA_ADMIN_FILE=str(pw),
               AGK_PROJECT_PATTERN="^(a/b)$", AGK_FACTS_PORT="9555")
    res = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "config", "--format", "json"],
                         capture_output=True, text=True, env=env, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    cfg = json.loads(res.stdout)
    assert sorted(cfg["services"]) == sorted(SERVICES)
    for svc in cfg["services"].values():
        assert svc["restart"] == "no"
        assert all(p["host_ip"] == "127.0.0.1" for p in svc["ports"])
    assert "host.docker.internal:9555" in cfg["configs"]["facts_targets"]["content"]


# --- the Collector ----------------------------------------------------------------------------

def test_collector_pipelines_go_to_prometheus_and_loki():
    pipes = collector()["service"]["pipelines"]
    assert sorted(pipes) == ["logs", "metrics"]
    assert pipes["metrics"]["exporters"] == ["prometheus_remote_write"]
    assert pipes["logs"]["exporters"] == ["otlp_http/loki"]
    assert pipes["metrics"]["receivers"] == pipes["logs"]["receivers"] == ["otlp"]
    otlp = collector()["receivers"]["otlp"]["protocols"]
    assert otlp["grpc"]["endpoint"] == "0.0.0.0:4317" and otlp["http"]["endpoint"] == "0.0.0.0:4318"


def test_collector_drops_untagged():
    cfg = collector()
    for signal, context in (("metrics", "metric"), ("logs", "log_record")):
        assert "filter/agk_projects" in cfg["service"]["pipelines"][signal]["processors"]
        conditions = cfg["processors"]["filter/agk_projects"][signal][context]
        (cond,) = conditions
        # A true condition drops the data: no agk.project, or one that is not in the list.
        assert 'resource.attributes["agk.project"] == nil' in cond
        assert 'not IsMatch(resource.attributes["agk.project"], "${env:AGK_PROJECT_PATTERN}")' in cond
    # the filter runs before every exporter and before any other processor that changes data
    for signal in ("metrics", "logs"):
        procs = cfg["service"]["pipelines"][signal]["processors"]
        assert procs.index("filter/agk_projects") < procs.index("batch")
    assert service("collector")["environment"]["AGK_PROJECT_PATTERN"].startswith("${AGK_PROJECT_PATTERN:?")


def test_project_pattern_matches_only_listed_projects():
    board = board_module()
    entries = [{"project": "own/agent-graph-kit", "repo": "/x"}, {"project": "o.w/n-2", "repo": "/y"},
               {"project": "not a slug", "repo": "/z"}]
    pattern = board.project_pattern(entries)
    assert "\\" not in pattern and '"' not in pattern
    rx = re.compile(pattern)
    assert rx.search("own/agent-graph-kit") and rx.search("o.w/n-2")
    for other in ("own/agent-graph-kit-2", "xown/agent-graph-kit", "oxw/n-2", "other/p", "", "not a slug"):
        assert not rx.search(other), other
    with pytest.raises(ValueError):
        board.project_pattern([{"project": "x", "repo": "/"}])


PROMPT_ATTRIBUTES = ["prompt", "user_prompt", "response", "response_text", "output_text",
                     "assistant_message", "last_assistant_message"]


def test_collector_no_prompt_attributes():
    cfg = collector()
    assert "transform/no_prompts" in cfg["service"]["pipelines"]["logs"]["processors"]
    (block,) = cfg["processors"]["transform/no_prompts"]["log_statements"]
    assert block["context"] == "log"
    for name in PROMPT_ATTRIBUTES:
        assert f'delete_key(attributes, "{name}")' in block["statements"], name
    assert len(block["statements"]) == len(PROMPT_ATTRIBUTES)
    # the guard runs before the export and after the project filter
    procs = cfg["service"]["pipelines"]["logs"]["processors"]
    assert procs.index("filter/agk_projects") < procs.index("transform/no_prompts") < procs.index("batch")
