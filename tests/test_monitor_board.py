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
                     "AGK_GRAFANA_PORT", "FAKE_DOCKER_INFO_EXIT", "FAKE_DOCKER_UP_EXIT"):
            env.pop(name, None)
        env.update(PATH=str(self.bin), HOME=str(self.home), XDG_STATE_HOME=str(tmp / "state"),
                   FAKE_DOCKER_LOG=str(self.log), FAKE_GH_MODE=str(self.gh_mode))
        self.env = env

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
    (call,) = [c for c in rig.calls() if "up" in c["args"]]
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
