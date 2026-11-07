"""Tests for the optional Grafana stack of the monitor skill (issue #283):
`plugin/skills/monitor/compose.yaml`, `grafana/` and `board.py`.

No test needs a Docker daemon or the network: `board.py` runs with a fake `docker` (and a fake
`gh`) on PATH, in a temp HOME and state dir. All data is synthetic."""

import importlib.util
import json
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
COMPOSE = SKILL / "compose.yaml"
GRAFANA = SKILL / "grafana"
BOARD = SKILL / "board.py"
DB_TARGET = "/var/lib/agk-monitor"


def load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = load("monitor_store_for_board_tests", SKILL / "store.py")
board = load("monitor_board_under_test", BOARD)


# --- a small YAML reader for the block style of these files (the test env has no PyYAML) -------

KEY = re.compile(r"^([A-Za-z0-9_.\-]+):(?:\s+(.*))?$")


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


def grafana_service():
    services = compose()["services"]
    assert list(services) == ["grafana"]
    return services["grafana"]


def mounts():
    return grafana_service()["volumes"]


# --- compose.yaml -----------------------------------------------------------------------------

def test_yaml_reader_agrees_with_pyyaml_when_present():
    yaml = pytest.importorskip("yaml")
    for path in [COMPOSE, *sorted((GRAFANA / "provisioning").rglob("*.yaml"))]:
        assert read_yaml(path) == yaml.safe_load(path.read_text(encoding="utf-8")), path


def test_one_grafana_service_with_pinned_image_and_plugin():
    svc = grafana_service()
    image = svc["image"]
    assert re.fullmatch(r"grafana/grafana:\d+\.\d+\.\d+", image), image
    plugins = svc["environment"]["GF_PLUGINS_PREINSTALL_SYNC"]
    assert re.fullmatch(r"frser-sqlite-datasource@\d+\.\d+\.\d+", plugins), plugins
    assert svc["environment"]["GF_PLUGINS_PREINSTALL_AUTO_UPDATE"] == "false"
    text = COMPOSE.read_text(encoding="utf-8").lower()
    assert "latest" not in text
    for ch in ("^", "~", ">", "<", "*"):
        assert ch not in image + plugins


def test_port_is_bound_to_localhost_only():
    ports = grafana_service()["ports"]
    assert ports
    for p in ports:
        assert isinstance(p, str) and p.startswith("127.0.0.1:"), p


def test_restart_is_no():
    assert grafana_service()["restart"] == "no"


def test_db_folder_is_mounted_read_only():
    db = [m for m in mounts() if m.get("target") == DB_TARGET]
    assert len(db) == 1
    assert db[0]["type"] == "bind"
    assert db[0]["read_only"] is True
    assert db[0]["source"].startswith("${AGK_MONITOR_DB_DIR")
    for m in mounts():
        if m["type"] == "bind":
            assert m["read_only"] is True, m


def test_grafana_runs_with_the_host_uid():
    assert grafana_service()["user"].startswith("${AGK_UID")


def test_no_credential_is_passed_to_the_container():
    text = COMPOSE.read_text(encoding="utf-8")
    upper = text.upper()
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC", "CLAUDE", "OPENAI", "CODEX"):
        assert name not in upper, name
    for path in ("~/.config/gh", "~/.claude", "~/.codex", ".config/gh", ".claude", ".codex", "$HOME", "${HOME"):
        assert path not in text, path
    svc = grafana_service()
    assert "env_file" not in svc
    # The only host paths: the db folder, the two folders of grafana/, and the password file.
    sources = sorted(m["source"] for m in mounts() if m["type"] == "bind")
    assert sources == sorted(["${AGK_MONITOR_DB_DIR:?run board.py up}", "./grafana/provisioning", "./grafana/boards"])
    named = [m for m in mounts() if m["type"] == "volume"]
    assert [m["target"] for m in named] == ["/var/lib/grafana/plugins"]
    assert compose()["secrets"] == {"grafana_admin": {"file": "${AGK_GRAFANA_ADMIN_FILE:?run board.py up}"}}


def test_login_is_needed_and_anonymous_access_is_off():
    env = grafana_service()["environment"]
    assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert env["GF_USERS_ALLOW_SIGN_UP"] == "false"
    assert env["GF_SECURITY_ADMIN_PASSWORD__FILE"] == "/run/secrets/grafana_admin"
    assert grafana_service()["secrets"] == ["grafana_admin"]
    assert "GF_SECURITY_ADMIN_PASSWORD" not in env


def test_no_phone_home_after_the_first_start():
    env = grafana_service()["environment"]
    for key in ("GF_ANALYTICS_REPORTING_ENABLED", "GF_ANALYTICS_CHECK_FOR_UPDATES",
                "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES", "GF_NEWS_NEWS_FEED_ENABLED"):
        assert env[key] == "false", key
    disabled = env["GF_PLUGINS_DISABLE_PLUGINS"].split(",")
    assert "grafana-advisor-app" in disabled and "frser-sqlite-datasource" not in disabled


@pytest.mark.skipif(not shutil.which("docker"), reason="docker CLI not installed")
def test_docker_compose_accepts_the_file(tmp_path):
    """`docker compose config` reads the file without a daemon."""
    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0:
        pytest.skip("docker compose not installed")
    pw = tmp_path / "pw"
    pw.write_text("x")
    env = dict(os.environ, AGK_UID="1000", AGK_GID="1000", AGK_MONITOR_DB_DIR=str(tmp_path),
               AGK_MONITOR_DB_NAME="monitor.sqlite", AGK_GRAFANA_ADMIN_FILE=str(pw))
    res = subprocess.run(["docker", "compose", "-f", str(COMPOSE), "config", "--format", "json"],
                         capture_output=True, text=True, env=env, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    cfg = json.loads(res.stdout)
    svc = cfg["services"]["grafana"]
    assert svc["ports"][0]["host_ip"] == "127.0.0.1"
    assert svc["environment"]["AGK_MONITOR_DB"] == f"{DB_TARGET}/monitor.sqlite"


# --- provisioning and boards ------------------------------------------------------------------

def test_data_source_is_provisioned_read_only_on_the_mounted_db():
    files = sorted((GRAFANA / "provisioning" / "datasources").glob("*.yaml"))
    assert files
    (ds,) = read_yaml(files[0])["datasources"]
    assert ds["type"] == "frser-sqlite-datasource"
    assert ds["uid"] == "agk-monitor"
    assert ds["jsonData"]["path"] == "$AGK_MONITOR_DB"
    assert "mode=ro" in ds["jsonData"]["pathOptions"]
    env = grafana_service()["environment"]
    assert env["AGK_MONITOR_DB"].startswith(DB_TARGET + "/")


def test_board_provider_reads_the_boards_folder():
    files = sorted((GRAFANA / "provisioning" / "dashboards").glob("*.yaml"))
    assert files
    (provider,) = read_yaml(files[0])["providers"]
    assert provider["type"] == "file"
    target = [m["target"] for m in mounts() if m.get("source") == "./grafana/boards"]
    assert target == [provider["options"]["path"]]
    provisioning = [m["target"] for m in mounts() if m.get("source") == "./grafana/provisioning"]
    assert provisioning == ["/etc/grafana/provisioning"]


def board_files():
    files = sorted((GRAFANA / "boards").glob("*.json"))
    assert files
    return files


def queries():
    for path in board_files():
        for panel in json.loads(path.read_text(encoding="utf-8"))["panels"]:
            for target in panel.get("targets", []):
                assert target["datasource"]["uid"] == "agk-monitor"
                for key in ("rawQueryText", "queryText"):
                    yield path.name, panel["title"], target[key]


def test_stub_board_shows_the_last_load_time():
    stub = json.loads((GRAFANA / "boards" / "monitor-stub.json").read_text(encoding="utf-8"))
    sqls = [t["rawQueryText"] for p in stub["panels"] for t in p.get("targets", [])]
    assert any(re.search(r"\btime\b.*\bFROM loads\b.*ORDER BY id DESC LIMIT 1", s) for s in sqls)


@pytest.mark.parametrize("rows", [0, 2])
def test_each_board_query_runs_on_a_db_made_by_store_connect(tmp_path, rows):
    con = store.connect(tmp_path / "monitor.sqlite")
    try:
        for n in range(rows):
            store.write_load_row(con, store.now_utc(), "ok", f"load {n}", False)
        for name, title, sql in queries():
            try:
                result = con.execute(sql).fetchall()
            except sqlite3.Error as e:
                pytest.fail(f"{name} / {title}: {e}")
            if rows and "loads" in sql:
                assert result, f"{name} / {title}: no row"
    finally:
        con.close()


# --- board.py with a fake docker --------------------------------------------------------------

FAKE_DOCKER = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a") as f:
    f.write(json.dumps({{"args": args, "env": {{k: v for k, v in os.environ.items() if k.startswith("AGK_")}}}}) + "\\n")
if args[:1] == ["info"]:
    sys.exit(int(os.environ.get("FAKE_DOCKER_INFO_EXIT", "0")))
if args[:1] == ["compose"] and "up" in args:
    sys.exit(int(os.environ.get("FAKE_DOCKER_UP_EXIT", "0")))
sys.exit(0)
"""

FAKE_GH = """#!{python}
import sys
sys.stderr.write("fake gh: no network in tests\\n")
sys.exit(1)
"""


class Rig:
    def __init__(self, tmp, docker=True):
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.home = tmp / "home"
        self.home.mkdir()
        self.state = tmp / "state" / "agent-graph-kit"
        self.cwd = tmp / "elsewhere"
        self.cwd.mkdir()
        self.log = tmp / "docker.log"
        self.write_fake("gh", FAKE_GH)
        if docker:
            self.write_fake("docker", FAKE_DOCKER)
        env = dict(os.environ)
        for name in ("MONITOR_DB_FILE", "RUN_RECORD_FILE", "RUN_RECORD_LIMITS_FILE", "RUN_WEIGHTS_FILE",
                     "AGK_GRAFANA_PORT", "FAKE_DOCKER_INFO_EXIT", "FAKE_DOCKER_UP_EXIT"):
            env.pop(name, None)
        env.update(PATH=str(self.bin), HOME=str(self.home), XDG_STATE_HOME=str(tmp / "state"),
                   FAKE_DOCKER_LOG=str(self.log))
        self.env = env

    def write_fake(self, name, body):
        path = self.bin / name
        path.write_text(body.format(python=sys.executable))
        path.chmod(0o755)

    @property
    def db(self):
        return self.state / "monitor.sqlite"

    @property
    def password_file(self):
        return self.state / "grafana-admin"

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def compose_calls(self):
        return [c["args"] for c in self.calls() if c["args"][:1] == ["compose"]]

    def run(self, *args, **env):
        return subprocess.run([sys.executable, str(BOARD), *args], capture_output=True, text=True,
                              timeout=60, cwd=self.cwd, env={**self.env, **env})

    def loader_started(self):
        log = self.state / "monitor-load.log"
        return log.exists() and "loader started" in log.read_text()


def output(res):
    return res.stdout + res.stderr


def test_up_without_docker_names_docker_and_starts_nothing(tmp_path):
    rig = Rig(tmp_path, docker=False)
    res = rig.run("up")
    assert res.returncode != 0
    assert "Docker" in output(res)
    assert not rig.db.exists()
    assert not rig.loader_started()
    assert not rig.password_file.exists()


def test_up_when_docker_info_fails_starts_nothing(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up", FAKE_DOCKER_INFO_EXIT="1")
    assert res.returncode != 0
    assert "Docker" in output(res)
    assert [c["args"] for c in rig.calls()] == [["info"]]
    assert not rig.db.exists()
    assert not rig.loader_started()


def test_up_when_compose_up_fails_does_not_start_the_loader(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up", FAKE_DOCKER_UP_EXIT="1")
    assert res.returncode != 0
    assert "docker compose up" in output(res)
    assert any("up" in c for c in rig.compose_calls())
    assert not rig.loader_started()


def test_up_creates_the_db_file_before_the_stack_starts(tmp_path):
    rig = Rig(tmp_path)
    rig.run("up", FAKE_DOCKER_UP_EXIT="1")
    assert rig.db.is_file()
    assert stat.S_IMODE(rig.db.stat().st_mode) == 0o600
    with sqlite3.connect(rig.db) as con:
        assert con.execute("SELECT COUNT(*) FROM loads").fetchone() == (0,)


def test_up_passes_the_db_folder_and_the_host_uid(tmp_path):
    rig = Rig(tmp_path)
    rig.run("up", FAKE_DOCKER_UP_EXIT="1")
    (call,) = [c for c in rig.calls() if "up" in c["args"]]
    assert call["args"][:3] == ["compose", "-f", str(SKILL / "compose.yaml")]
    env = call["env"]
    assert env["AGK_MONITOR_DB_DIR"] == str(rig.db.parent.resolve())
    assert env["AGK_MONITOR_DB_NAME"] == "monitor.sqlite"
    assert env["AGK_UID"] == str(os.getuid()) and env["AGK_GID"] == str(os.getgid())
    assert env["AGK_GRAFANA_ADMIN_FILE"] == str(rig.password_file.resolve())


def test_up_follows_monitor_db_file(tmp_path):
    rig = Rig(tmp_path)
    db = tmp_path / "own" / "board.sqlite"
    rig.run("up", FAKE_DOCKER_UP_EXIT="1", MONITOR_DB_FILE=str(db))
    assert db.is_file()
    (call,) = [c for c in rig.calls() if "up" in c["args"]]
    assert call["env"]["AGK_MONITOR_DB_DIR"] == str(db.parent.resolve())
    assert call["env"]["AGK_MONITOR_DB_NAME"] == "board.sqlite"


@pytest.mark.parametrize("where", ["home", "claude"])
def test_up_refuses_a_db_folder_with_credentials(tmp_path, where):
    rig = Rig(tmp_path)
    folder = rig.home if where == "home" else rig.home / ".claude"
    res = rig.run("up", MONITOR_DB_FILE=str(folder / "monitor.sqlite"))
    assert res.returncode != 0
    assert not rig.compose_calls()
    assert not (folder / "monitor.sqlite").exists()


def test_password_file_is_private_reused_and_never_printed(tmp_path):
    rig = Rig(tmp_path)
    first = rig.run("up", FAKE_DOCKER_UP_EXIT="1")
    assert stat.S_IMODE(rig.password_file.stat().st_mode) == 0o600
    password = rig.password_file.read_text()
    assert len(password) >= 20
    rig.password_file.chmod(0o644)
    second = rig.run("up", FAKE_DOCKER_UP_EXIT="1")
    assert rig.password_file.read_text() == password
    assert stat.S_IMODE(rig.password_file.stat().st_mode) == 0o600
    for res in (first, second):
        assert password not in output(res)


def wait_for(check, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.2)
    return False


def loads_in(db):
    try:
        with sqlite3.connect(db, timeout=5) as con:
            return con.execute("SELECT COUNT(*) FROM loads").fetchone()[0]
    except sqlite3.Error:
        return 0


def test_sigint_stops_the_loader_and_the_stack(tmp_path):
    rig = Rig(tmp_path)
    proc = subprocess.Popen([sys.executable, str(BOARD), "up"], cwd=rig.cwd, env=rig.env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert wait_for(lambda: loads_in(rig.db) > 0), "the loader made no load"
        assert rig.loader_started()
        assert not any("down" in c for c in rig.compose_calls())
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert proc.returncode == 0, err
    calls = rig.compose_calls()
    assert any("up" in c for c in calls)
    assert calls[-1][-1] == "down"
    assert "loader stopped" in (rig.state / "monitor-load.log").read_text()
    password = rig.password_file.read_text()
    assert password not in out + err
    assert str(rig.password_file) in out
    assert "http://127.0.0.1:3000" in out


def test_down_exits_0_when_the_stack_is_not_running(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("down")
    assert res.returncode == 0, output(res)
    assert rig.compose_calls() == [["compose", "-f", str(SKILL / "compose.yaml"), "down"]]


@pytest.mark.parametrize("docker", [False, True])
def test_down_exits_0_without_docker(tmp_path, docker):
    rig = Rig(tmp_path, docker=docker)
    res = rig.run("down", FAKE_DOCKER_INFO_EXIT="1")
    assert res.returncode == 0, output(res)
    assert not rig.compose_calls()


def test_unsafe_db_dir_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert board.unsafe_db_dir(tmp_path)
    assert board.unsafe_db_dir(Path("/"))
    assert board.unsafe_db_dir(tmp_path / ".codex" / "x")
    assert board.unsafe_db_dir(tmp_path / ".config")
    assert board.unsafe_db_dir(tmp_path / ".local" / "state" / "agent-graph-kit") is None
