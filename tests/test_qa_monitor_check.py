"""Tests for the monitor smoke check of scripts/qa-codex (#319).

No Docker and no network beyond 127.0.0.1: a fake `docker` (tests/fakes/docker), a fake `board.py` in the
tested commit, and small HTTP servers that play the Collector, Loki and Grafana. All data is synthetic.
"""

import json
import shutil
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_qa_codex import FAKES, QaEnv, git, qa

PASSWORD = "PW-synthetic-hunter2"
TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"

FAKE_BOARD = '''
import json, os, pathlib, socket, sys, time
mode = os.environ.get("FAKE_BOARD_MODE", "ok")
state = pathlib.Path(os.environ["XDG_STATE_HOME"]) / "agent-graph-kit"
keys = ["XDG_STATE_HOME", "COMPOSE_PROJECT_NAME"] + sorted(k for k in os.environ if k.startswith("AGK_"))
with open(os.environ["FAKE_BOARD_LOG"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "env": {k: os.environ.get(k) for k in keys},
                        "projects": (state / "monitor-projects.json").read_text()}) + "\\n")
if sys.argv[1] == "up":
    (state / "grafana-admin").write_text("PASSWORD_VALUE\\n")
    if mode == "leak":
        print("password is PASSWORD_VALUE and token TOKEN_VALUE")
        sys.exit(1)
    if mode == "hang":
        time.sleep(30)
    if mode == "ports":
        for var in sorted(k for k in os.environ if k.startswith("AGK_") and k.endswith("_PORT")):
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", int(os.environ[var])))
            except OSError:
                print("Error response from daemon: Bind for 127.0.0.1:%s failed: port is already allocated" % os.environ[var])
                sys.exit(1)
            finally:
                s.close()
sys.exit(0)
'''.replace("PASSWORD_VALUE", PASSWORD).replace("TOKEN_VALUE", TOKEN)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeStack:
    """Three HTTP servers: the OTLP receiver of the Collector, Loki and Grafana."""

    def __init__(self, drop_untagged=True):
        self.stored = []
        stack = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body=b"{}"):
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                res = body["resourceLogs"][0]
                keys = {a["key"] for a in res["resource"]["attributes"]}
                line = res["scopeLogs"][0]["logRecords"][0]["body"]["stringValue"]
                if "agk.project" in keys or not drop_untagged:
                    stack.stored.append(line)
                self.reply(200)

            def do_GET(self):
                if self.path.startswith("/loki/api/v1/query_range"):
                    values = [["1", line] for line in stack.stored]
                    self.reply(200, json.dumps({"data": {"result": [{"values": values}]}}).encode())
                elif self.path == "/api/health":
                    self.reply(200)
                elif self.path == "/api/user":
                    ok = self.headers.get("Authorization", "").startswith("Basic ")
                    self.reply(200 if ok else 401)
                else:
                    self.reply(404)

        self.servers = [ThreadingHTTPServer(("127.0.0.1", 0), Handler) for _ in range(3)]
        for server in self.servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        http, loki, grafana = (s.server_address[1] for s in self.servers)
        self.ports = {"AGK_OTLP_GRPC_PORT": free_port(), "AGK_OTLP_HTTP_PORT": http,
                      "AGK_PROMETHEUS_PORT": free_port(), "AGK_LOKI_PORT": loki, "AGK_GRAFANA_PORT": grafana}

    def close(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    e = QaEnv(tmp_path, monkeypatch)
    (e.bin / "docker").symlink_to(FAKES / "docker")
    for key in ("FAKE_BOARD_MODE", "FAKE_DOCKER_INFO_FAIL", "FAKE_DOCKER_PS", "FAKE_DOCKER_VOLUMES",
                "FAKE_DOCKER_DOWN_FAIL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("FAKE_BOARD_LOG", str(tmp_path / "board.log"))
    monkeypatch.setattr(qa, "MONITOR_SETTLE_S", 0)
    monkeypatch.setattr(qa, "MONITOR_POLL_EVERY_S", 0.05)
    monkeypatch.setattr(qa, "MONITOR_POLL_S", 3)
    # settings of the owner's stack must not reach the check
    monkeypatch.setenv("AGK_GRAFANA_PORT", "3000")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "agk-monitor")
    return e


def commit_monitor(e, compose=True):
    skill = e.repo / "plugin" / "skills" / "monitor"
    skill.mkdir(parents=True)
    (skill / "board.py").write_text(FAKE_BOARD)
    if compose:
        (skill / "compose.yaml").write_text("name: agk-monitor\nservices: {}\n")
    git(e.repo, "add", ".")
    git(e.repo, "commit", "-q", "-m", "monitor files")


@pytest.fixture
def stack(monkeypatch):
    made = []

    def make(**kw):
        s = FakeStack(**kw)
        made.append(s)
        monkeypatch.setattr(qa, "_pick_ports", lambda: dict(s.ports))
        return s
    yield make
    for s in made:
        s.close()


def run_check(e, timeout_s=None):
    folder, state = e.tmp / "out" / "monitor", e.tmp / "out" / "state"
    qa.run_monitor_check(e.repo, folder, state, timeout_s)
    summary = json.loads((folder / "summary.json").read_text())
    cleanup = json.loads((folder / "cleanup.json").read_text())
    return {s["name"]: s for s in summary}, cleanup, folder


def docker_calls(e):
    log = e.tmp / "docker.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def cleaned_up(e):
    return any(c["argv"][:1] == ["compose"] and c["argv"][-2:] == ["down", "-v"] for c in docker_calls(e))


EMPTY = {"containers": [], "volumes": []}


def test_success(env, stack):
    commit_monitor(env)
    stack()
    steps, cleanup, folder = run_check(env)
    assert list(steps) == list(qa.MONITOR_STEPS)
    assert {s["result"] for s in steps.values()} == {"pass"}
    assert steps["board.py up"]["exit_code"] == 0 and steps["board.py down"]["exit_code"] == 0
    assert all(s["reason"] for s in steps.values())
    assert cleanup == EMPTY and cleaned_up(env)
    assert sorted(p.name for p in folder.iterdir()) == ["cleanup.json", "summary.json"]


def test_isolation_and_every_docker_call_carries_the_project(env, stack):
    commit_monitor(env)
    s = stack()
    run_check(env)
    board = [json.loads(line) for line in (env.tmp / "board.log").read_text().splitlines()]
    assert [b["argv"] for b in board] == [["up"], ["down"]]
    seen = board[0]["env"]
    name = seen["COMPOSE_PROJECT_NAME"]
    assert name.startswith("agk-qa-") and len(name) > len("agk-qa-")
    assert seen["XDG_STATE_HOME"].startswith(str(env.tmp / "out"))  # a temporary state folder
    ports = {k: int(v) for k, v in seen.items() if k.endswith("_PORT")}
    assert ports == s.ports and len(set(ports.values())) == 5
    assert not set(ports.values()) & {4317, 4318, 9090, 3100, 3000}  # the owner's AGK_GRAFANA_PORT=3000 is gone
    assert json.loads(board[0]["projects"])[0]["project"] == qa.MONITOR_PROJECT
    calls = docker_calls(env)
    assert calls and all(c["project"] == name for c in calls)
    assert not any("agk-monitor" in " ".join(c["argv"]) for c in calls)
    assert next(c for c in calls if c["argv"][:1] == ["compose"])["argv"][:3] == ["compose", "-p", name]
    assert not (env.tmp / "out" / "state").exists()  # the state folder with the password is removed


def test_failed_step_is_a_result_and_the_cleanup_runs(env, stack):
    commit_monitor(env)
    stack(drop_untagged=False)  # the Collector filter lets the untagged record pass
    steps, cleanup, _ = run_check(env)
    assert steps["only tagged record stored"]["result"] == "fail"
    assert "no agk.project" in steps["only tagged record stored"]["reason"]
    assert steps["grafana login with password"]["result"] == "pass"
    assert steps["board.py down"]["result"] == "pass"
    assert cleaned_up(env) and cleanup == EMPTY


def test_failed_up_skips_the_rest_and_cleans_up(env, stack, monkeypatch):
    commit_monitor(env)
    stack()
    monkeypatch.setenv("FAKE_BOARD_MODE", "leak")
    monkeypatch.setenv("FAKE_DOCKER_PS", "agk-qa-left-over-1")
    steps, cleanup, _ = run_check(env)
    assert steps["board.py up"]["result"] == "fail" and steps["board.py up"]["exit_code"] == 1
    assert steps["send tagged record"] == {"name": "send tagged record", "result": "skipped",
                                           "reason": "board.py up failed"}
    assert cleaned_up(env)
    assert cleanup == {"containers": ["agk-qa-left-over-1"], "volumes": []}


def test_occupied_port_fails_up_and_names_the_port(env, monkeypatch):
    commit_monitor(env)
    ports = {var: free_port() for var in qa.MONITOR_PORT_VARS}
    monkeypatch.setattr(qa, "_pick_ports", lambda: dict(ports))
    monkeypatch.setenv("FAKE_BOARD_MODE", "ports")
    held = socket.socket()
    held.bind(("127.0.0.1", ports["AGK_LOKI_PORT"]))
    try:
        steps, cleanup, _ = run_check(env)
    finally:
        held.close()
    up = steps["board.py up"]
    assert up["result"] == "fail"
    assert str(ports["AGK_LOKI_PORT"]) in up["reason"] and "AGK_LOKI_PORT" in up["reason"]
    assert cleaned_up(env) and cleanup == EMPTY


def test_timeout_stops_the_step_and_cleans_up(env, stack, monkeypatch):
    commit_monitor(env)
    stack()
    monkeypatch.setenv("FAKE_BOARD_MODE", "hang")
    steps, cleanup, _ = run_check(env, timeout_s=1)  # the fake board.py sleeps 30 s
    assert steps["board.py up"]["result"] == "fail" and steps["board.py up"]["reason"] == "timeout"
    assert all(s["result"] == "skipped" for n, s in steps.items() if n != "board.py up")
    assert steps["board.py down"]["reason"] == "timeout of an earlier step"
    assert cleaned_up(env) and cleanup == EMPTY


def test_the_time_limit_is_600_seconds():
    assert qa.MONITOR_TIMEOUT_S == 600


def test_error_of_the_launcher_still_cleans_up(env, stack, monkeypatch):
    commit_monitor(env)
    stack()

    def boom(self, *a, **k):
        raise RuntimeError("synthetic launcher error")
    monkeypatch.setattr(qa.MonitorCheck, "send", boom)
    steps, cleanup, _ = run_check(env)
    assert steps["send tagged record"]["result"] == "fail"
    assert "launcher error" in steps["send tagged record"]["reason"]
    assert cleaned_up(env) and cleanup == EMPTY


def test_error_before_the_first_step_still_cleans_up(env, monkeypatch):
    commit_monitor(env)

    def boom():
        raise RuntimeError("synthetic launcher error")
    monkeypatch.setattr(qa, "_pick_ports", boom)
    steps, cleanup, _ = run_check(env)
    assert steps["board.py up"]["result"] == "fail" and "launcher error" in steps["board.py up"]["reason"]
    assert cleanup == EMPTY


def test_no_docker_skips_every_step(env, monkeypatch):
    commit_monitor(env)
    (env.tmp / "empty").mkdir()
    monkeypatch.setenv("PATH", str(env.tmp / "empty"))  # no `docker` anywhere on PATH
    steps, cleanup, _ = run_check(env)
    assert list(steps) == list(qa.MONITOR_STEPS)
    assert {(s["result"], s["reason"]) for s in steps.values()} == {("skipped", "no docker")}
    assert cleanup == EMPTY


def test_failing_docker_info_skips_every_step(env, monkeypatch):
    commit_monitor(env)
    monkeypatch.setenv("FAKE_DOCKER_INFO_FAIL", "1")
    steps, _, _ = run_check(env)
    assert {s["reason"] for s in steps.values()} == {"no docker"}


def test_no_compose_file_skips_every_step_and_starts_no_docker(env):
    commit_monitor(env, compose=False)
    steps, _, _ = run_check(env)
    assert {(s["result"], s["reason"]) for s in steps.values()} == {("skipped", "no compose file")}
    assert docker_calls(env) == []


def test_no_secret_in_any_file(env, stack, monkeypatch):
    commit_monitor(env)
    stack()
    monkeypatch.setenv("FAKE_BOARD_MODE", "leak")  # board.py prints the password and a token
    monkeypatch.setenv("FAKE_DOCKER_PS", f"left-{PASSWORD}-{TOKEN}")
    steps, cleanup, folder = run_check(env)
    text = "".join(p.read_text() for p in folder.iterdir())
    assert "[redacted]" in text
    assert PASSWORD not in text and TOKEN not in text and "ghp_" not in text
    assert steps["board.py up"]["log"] and len(cleanup["containers"]) == 1


def test_log_is_cut_to_the_last_20_lines(env, stack, monkeypatch):
    commit_monitor(env)
    stack()
    monkeypatch.setattr(qa.MonitorCheck, "run_cmd",
                        lambda self, cmd: (1, "\n".join(f"line {i}" for i in range(100))))
    steps, _, _ = run_check(env)
    log = steps["board.py up"]["log"]
    assert len(log) == 20 and log[0] == "line 80" and log[-1] == "line 99"


def test_main_goes_on_after_a_failed_step_and_the_prompt_names_the_files(env, stack, monkeypatch):
    commit_monitor(env)
    stack()
    monkeypatch.setenv("FAKE_BOARD_MODE", "leak")
    kept, folders = env.tmp / "kept", []
    original = qa.run_monitor_check

    def wrapper(worktree, folder, state, timeout_s=None):
        original(worktree, folder, state, timeout_s)
        folders.append(str(folder))
        shutil.copytree(folder, kept)
    monkeypatch.setattr(qa, "run_monitor_check", wrapper)
    comment, _ = env.run(["ok"])
    assert comment.startswith("## QA: PASS")  # a failed step does not give UNAVAILABLE
    assert json.loads((kept / "summary.json").read_text())[0]["result"] == "fail"
    prompt = env.calls("codex")[0]["stdin"]
    assert folders[0] in prompt and "summary.json" in prompt and "cleanup.json" in prompt
    assert "do not mark a criterion `invalid`" in prompt


def test_main_with_no_compose_file_runs_no_docker(env):
    comment, _ = env.run(["ok"])
    assert comment.startswith("## QA: PASS")
    assert docker_calls(env) == []
    prompt = env.calls("codex")[0]["stdin"]
    assert "no compose file" in prompt and "do not mark a criterion `invalid`" in prompt
