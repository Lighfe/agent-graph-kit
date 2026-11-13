"""Tests for `board.py` of the monitor skill (issue #309): `up` and `down` of the monitoring stack.

No test needs a Docker daemon or the network: `board.py` runs with a fake `docker` and a fake `gh` on PATH,
in a temp HOME and state dir. All data is synthetic."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugin" / "skills" / "monitor"
BOARD = SKILL / "board.py"


RIGS = []


def free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _stop_facts_after_test():
    yield
    while RIGS:
        RIGS.pop().kill_facts()


FAKE_GH = """#!{python}
import sys
if "--fail" in open(__import__("os").environ["FAKE_GH_MODE"]).read():
    sys.stderr.write("fake gh: no network in tests\\n")
    sys.exit(1)
print("own/demo-project")
"""


FAKE_DOCKER = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a") as f:
    f.write(json.dumps({{"args": args, "env": {{k: v for k, v in os.environ.items() if k.startswith("AGK_")}}}}) + "\\n")
if args[:1] == ["info"]:
    sys.exit(int(os.environ.get("FAKE_DOCKER_INFO_EXIT", "0")))
if args[:2] == ["network", "inspect"]:
    print(os.environ.get("FAKE_DOCKER_NETWORK", '[{{"IPAM": {{"Config": [{{"Subnet": "127.0.0.0/8", "Gateway": "127.0.0.1"}}]}}}}]'))
    sys.exit(0)
if args[:1] == ["compose"] and "up" in args:
    sys.exit(int(os.environ.get("FAKE_DOCKER_UP_EXIT", "0")))
if args[:1] == ["compose"] and "down" in args and os.environ.get("FAKE_DOCKER_DOWN_SLEEP"):
    import time
    time.sleep(float(os.environ["FAKE_DOCKER_DOWN_SLEEP"]))
    open(os.path.join(os.path.dirname(os.environ["FAKE_DOCKER_LOG"]), "down.done"), "w").close()
sys.exit(0)
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
                     "AGK_GRAFANA_PORT", "FAKE_DOCKER_INFO_EXIT", "FAKE_DOCKER_UP_EXIT",
                     "FAKE_DOCKER_DOWN_SLEEP"):
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


class Rig:
    def __init__(self, tmp, docker=True, gh_fails=False):
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.home = tmp / "home"
        self.home.mkdir()
        self.state = tmp / "state" / "agent-graph-kit"
        self.cwd = tmp / "elsewhere"
        self.cwd.mkdir()
        self.log = tmp / "docker.log"
        self.gh_mode = tmp / "gh-mode"
        self.gh_mode.write_text("--fail" if gh_fails else "ok")
        self.write_fake("gh", FAKE_GH)
        if docker:
            self.write_fake("docker", FAKE_DOCKER)
        env = dict(os.environ)
        for name in ("AGK_OTLP_GRPC_PORT", "AGK_OTLP_HTTP_PORT", "AGK_PROMETHEUS_PORT", "AGK_LOKI_PORT",
                     "AGK_GRAFANA_PORT", "AGK_FACTS_PORT", "FAKE_DOCKER_INFO_EXIT", "FAKE_DOCKER_UP_EXIT",
                     "FAKE_DOCKER_NETWORK"):
            env.pop(name, None)
        env.update(PATH=str(self.bin), HOME=str(self.home), XDG_STATE_HOME=str(tmp / "state"),
                   FAKE_DOCKER_LOG=str(self.log), FAKE_GH_MODE=str(self.gh_mode),
                   AGK_FACTS_PORT=str(free_port()))
        self.env = env
        RIGS.append(self)

    @property
    def facts_pid_file(self):
        return self.state / "facts.pid"

    def kill_facts(self):
        """Test cleanup: stop a facts.py that `up` started."""
        try:
            os.kill(int(self.facts_pid_file.read_text().strip()), 9)
        except (OSError, ValueError):
            pass

    def write_fake(self, name, body):
        path = self.bin / name
        path.write_text(body.format(python=sys.executable))
        path.chmod(0o755)

    @property
    def password_file(self):
        return self.state / "grafana-admin"

    @property
    def projects_file(self):
        return self.state / "monitor-projects.json"

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def compose_calls(self):
        return [c["args"] for c in self.calls() if c["args"][:1] == ["compose"]]

    def run(self, *args, **env):
        return subprocess.run([sys.executable, str(BOARD), *args], capture_output=True, text=True,
                              timeout=60, cwd=self.cwd, env={**self.env, **env})


def output(res):
    return res.stdout + res.stderr


def up_call(rig):
    call = [c for c in rig.calls() if "up" in c["args"]][0]
    return call


def test_up_without_docker_names_docker_and_starts_nothing(tmp_path):
    rig = Rig(tmp_path, docker=False)
    res = rig.run("up")
    assert res.returncode != 0
    assert "Docker" in output(res)
    assert not rig.password_file.exists()
    assert not rig.projects_file.exists()


def test_up_when_docker_info_fails_starts_nothing(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up", FAKE_DOCKER_INFO_EXIT="1")
    assert res.returncode != 0
    assert "Docker" in output(res)
    assert [c["args"] for c in rig.calls()] == [["info"]]
    assert not rig.password_file.exists()


def test_up_starts_the_stack_in_the_background_and_exits_0(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up")
    assert res.returncode == 0, output(res)
    call = up_call(rig)
    assert call["args"] == ["compose", "-f", str(SKILL / "compose.yaml"), "up", "-d"]
    assert "http://127.0.0.1:3000" in res.stdout
    assert str(rig.password_file) in res.stdout
    assert "127.0.0.1:4317" in res.stdout and "http://127.0.0.1:4318" in res.stdout


def test_up_when_a_port_is_in_use_names_it_and_cleans_up(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up", FAKE_DOCKER_UP_EXIT="1", AGK_GRAFANA_PORT="3999")
    assert res.returncode == 1
    assert "docker compose up" in output(res) and "AGK_GRAFANA_PORT=3999" in output(res)
    assert rig.compose_calls()[-1][-1] == "down"


def test_up_writes_the_project_list_once_with_the_current_project(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up")
    assert res.returncode == 0, output(res)
    assert json.loads(rig.projects_file.read_text()) == [{"project": "own/demo-project", "repo": str(rig.cwd)}]
    assert stat.S_IMODE(rig.projects_file.stat().st_mode) == 0o600
    assert up_call(rig)["env"]["AGK_PROJECT_PATTERN"] == "^(own/demo-project)$"
    # a second run reads the file and does not ask gh again
    rig.gh_mode.write_text("--fail")
    rig.projects_file.write_text(json.dumps([{"project": "a/b.c", "repo": "/r"}, {"project": "d/e", "repo": "/s"}]))
    assert rig.run("up").returncode == 0
    assert rig.calls()[-1]["env"]["AGK_PROJECT_PATTERN"] == "^(a/b[.]c|d/e)$"


def test_up_without_a_project_list_and_without_gh_starts_nothing(tmp_path):
    rig = Rig(tmp_path, gh_fails=True)
    res = rig.run("up")
    assert res.returncode == 2
    assert "gh repo view" in output(res)
    assert not rig.compose_calls()
    assert not rig.projects_file.exists()


def test_up_with_an_empty_project_list_starts_nothing(tmp_path):
    rig = Rig(tmp_path)
    rig.state.mkdir(parents=True)
    rig.projects_file.write_text("[]")
    res = rig.run("up")
    assert res.returncode == 2
    assert "Nothing was started" in output(res)
    assert not rig.compose_calls()


def test_up_passes_the_ports_and_the_host_uid(tmp_path):
    rig = Rig(tmp_path)
    rig.run("up", AGK_LOKI_PORT="3101", AGK_OTLP_GRPC_PORT="14317")
    env = up_call(rig)["env"]
    assert env["AGK_LOKI_PORT"] == "3101" and env["AGK_OTLP_GRPC_PORT"] == "14317"
    assert env["AGK_GRAFANA_PORT"] == "3000" and env["AGK_PROMETHEUS_PORT"] == "9090"
    assert env["AGK_OTLP_HTTP_PORT"] == "4318"
    assert env["AGK_UID"] == str(os.getuid()) and env["AGK_GID"] == str(os.getgid())
    assert env["AGK_GRAFANA_ADMIN_FILE"] == str(rig.password_file.resolve())


def test_password_file_is_private_reused_and_never_printed(tmp_path):
    rig = Rig(tmp_path)
    first = rig.run("up")
    assert stat.S_IMODE(rig.password_file.stat().st_mode) == 0o600
    password = rig.password_file.read_text()
    assert len(password) >= 20
    rig.password_file.chmod(0o644)
    second = rig.run("up")
    assert rig.password_file.read_text() == password
    assert stat.S_IMODE(rig.password_file.stat().st_mode) == 0o600
    for res in (first, second):
        assert password not in output(res)


def test_board_py_has_no_loader_or_store_code():
    text = BOARD.read_text(encoding="utf-8")
    for word in ("store", "sqlite", "run_loader", "signal"):
        assert word not in text.lower(), word


def test_down_exits_0_when_the_stack_is_not_running(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("down")
    assert res.returncode == 0, output(res)
    assert rig.compose_calls() == [["compose", "-f", str(SKILL / "compose.yaml"), "down"]]
    assert not rig.projects_file.exists() and not rig.password_file.exists()


@pytest.mark.parametrize("docker", [False, True])
def test_down_exits_0_without_docker(tmp_path, docker):
    rig = Rig(tmp_path, docker=docker)
    res = rig.run("down", FAKE_DOCKER_INFO_EXIT="1")
    assert res.returncode == 0, output(res)
    assert not rig.compose_calls()


def test_up_starts_facts_after_the_containers_and_down_stops_it(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up")
    assert res.returncode == 0, output(res)
    pid = int(rig.facts_pid_file.read_text())
    assert (rig.state / "facts.log").exists()
    assert os.path.exists(f"/proc/{pid}")
    assert "/metrics" in res.stdout
    res = rig.run("down")
    assert res.returncode == 0, output(res)
    assert not rig.facts_pid_file.exists()
    for _ in range(50):
        if not os.path.exists(f"/proc/{pid}") or "facts.py" not in Path(f"/proc/{pid}/cmdline").read_text():
            break
        import time
        time.sleep(0.1)
    else:
        raise AssertionError("facts.py still runs after down")


def test_up_with_a_used_facts_port_starts_nothing(tmp_path):
    import socket
    rig = Rig(tmp_path)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        used = str(s.getsockname()[1])
        res = rig.run("up", AGK_FACTS_PORT=used)
    assert res.returncode != 0
    assert "AGK_FACTS_PORT" in output(res)
    assert not rig.compose_calls()
    assert not rig.facts_pid_file.exists()


def test_down_exits_0_when_facts_is_not_running(tmp_path):
    rig = Rig(tmp_path)
    assert rig.run("down").returncode == 0
    rig.state.mkdir(parents=True, exist_ok=True)
    rig.facts_pid_file.write_text("999999999\n")
    assert rig.run("down").returncode == 0
    assert not rig.facts_pid_file.exists()


# --- the listen address of facts.py (issue #321) ----------------------------------------------

def board_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("agk_board_under_test", BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_text(*gateways):
    return json.dumps([{"Name": "agk-monitor_default", "IPAM": {"Config": [
        {"Subnet": "x", "Gateway": g} if g is not None else {"Subnet": "x"} for g in gateways]}}])


def test_gateway_from_a_normal_output():
    board = board_module()
    assert board.gateway_from_inspect(inspect_text("172.19.0.1")) == "172.19.0.1"
    assert board.gateway_from_inspect(inspect_text("fd00::1", "172.19.0.1")) == "172.19.0.1"


@pytest.mark.parametrize("text", [
    "",
    "not json {",
    "[]",
    "null",
    inspect_text(None),
    inspect_text("fd00::1"),
    inspect_text("0.0.0.0"),
    inspect_text("8.8.8.8"),
    json.dumps([{"IPAM": {"Config": None}}]),
])
def test_gateway_not_found(text):
    assert board_module().gateway_from_inspect(text) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "", "8.8.8.8", "localhost"])
def test_facts_command_refuses_unsafe_hosts(host):
    with pytest.raises(ValueError):
        board_module().facts_command(host)


def test_facts_command_passes_the_host():
    cmd = board_module().facts_command("172.19.0.1")
    assert cmd[-2:] == ["--host", "172.19.0.1"]


def test_up_passes_the_gateway_to_prometheus_and_facts(tmp_path):
    rig = Rig(tmp_path)
    res = rig.run("up")
    assert res.returncode == 0, output(res)
    ups = [c for c in rig.calls() if "up" in c["args"]]
    assert ups[-1]["env"]["AGK_FACTS_HOST"] == "127.0.0.1"
    assert "AGK_FACTS_HOST" not in ups[0]["env"]
    cmdline = Path(f"/proc/{int(rig.facts_pid_file.read_text())}/cmdline").read_bytes().split(b"\0")
    assert b"--host" in cmdline and cmdline[cmdline.index(b"--host") + 1] == b"127.0.0.1"
    assert b"0.0.0.0" not in cmdline


@pytest.mark.parametrize("text", ["", "not json", inspect_text("fd00::1"), inspect_text("0.0.0.0")])
def test_up_without_an_address_starts_no_facts_and_goes_on(tmp_path, text):
    rig = Rig(tmp_path)
    res = rig.run("up", FAKE_DOCKER_NETWORK=text)
    assert res.returncode == 0, output(res)
    assert not rig.facts_pid_file.exists()
    lines = [l for l in output(res).splitlines() if "facts.py was not started" in l]
    assert len(lines) == 1 and "gateway" in lines[0]
    assert "Grafana:" in res.stdout
