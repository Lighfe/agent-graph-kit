#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Start and stop the optional monitoring stack of the monitor skill (issue #309).

  uv run --script board.py up      check Docker, start the stack in the background, start facts.py, print the URLs
  uv run --script board.py down    stop facts.py and the stack; exit 0 also when it is not running

The stack (`compose.yaml` next to this file) is the OTel Collector, Prometheus, Loki and Grafana in Docker.
Every port is on 127.0.0.1 only. Docker is needed for this part only.
The Collector keeps only data of the projects in `<state dir>/monitor-projects.json`; `up` writes that
file once with the current project when it is missing. The admin password of Grafana is in
`<state dir>/grafana-admin` (mode 0600, made on the first `up`); this script prints the path, never the value.
`facts.py` (issue #310) runs on the host and listens on the gateway address of the compose network (never on
0.0.0.0), the address Prometheus scrapes (issue #321). Its process id is in `<state dir>/facts.pid`, its log in `<state dir>/facts.log`.
Spec: docs/specs/2026-11-13-otel-monitoring-boards.md, Part B
"""

import argparse
import importlib.util
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose.yaml"
DATA = HERE / "data.py"
FACTS = HERE / "facts.py"
HEADERS_HELPER = HERE / "otel_headers.py"  # copied by `up` to <state dir>/otel-headers.py (issue #324)
NETWORK = "agk-monitor_default"  # the compose network of the project `agk-monitor` (compose.yaml `name`)

# The ports of the stack: environment variable and default. `compose.yaml` has the same defaults.
PORTS = {
    "AGK_OTLP_GRPC_PORT": "4317",
    "AGK_OTLP_HTTP_PORT": "4318",
    "AGK_PROMETHEUS_PORT": "9090",
    "AGK_LOKI_PORT": "3100",
    "AGK_GRAFANA_PORT": "3000",
    "AGK_FACTS_PORT": "9464",
}
SLUG = re.compile(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+")


def _load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


data = _load("agk_monitor_data", DATA)


def say(text, err=False):
    print(f"board: {text}", file=sys.stderr if err else sys.stdout, flush=True)


# --- paths and settings -----------------------------------------------------------------------

def facts_pid_path():
    return data.state_dir() / "facts.pid"


def facts_log_path():
    return data.state_dir() / "facts.log"


def password_path():
    return data.state_dir() / "grafana-admin"


def projects_path():
    return data.state_dir() / "monitor-projects.json"


def headers_helper_path():
    """The fixed place of the `otelHeadersHelper` of the user settings: it does not change with a plugin update."""
    return data.state_dir() / "otel-headers.py"


def port(name):
    return os.environ.get(name) or PORTS[name]


# --- projects ---------------------------------------------------------------------------------

def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)


def current_project():
    """`owner/name` of the repo in the current folder (`gh repo view`), or raise RuntimeError."""
    try:
        res = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"`gh repo view` did not run: {e}")
    slug = res.stdout.strip()
    if res.returncode != 0 or not slug:
        detail = (res.stderr or "").strip().splitlines()
        raise RuntimeError("`gh repo view` gave no owner/name" + (f" ({detail[-1]})" if detail else ""))
    return slug


def projects():
    """The projects of `monitor-projects.json`. When the file is missing, write it once with the
    current project (`owner/name` from `gh repo view`, the current folder as repo)."""
    path = projects_path()
    if not path.exists():
        entries = [{"project": current_project(), "repo": str(Path.cwd())}]
        write_private(path, json.dumps(entries, indent=2) + "\n")
        say(f"wrote {path} with {entries[0]['project']}")
        return entries
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{path}: not a list")
    return [e for e in entries
            if isinstance(e, dict) and isinstance(e.get("project"), str) and isinstance(e.get("repo"), str)]


def install_headers_helper():
    """Copy `otel_headers.py` to `headers_helper_path()` (mode 0700), next to the project list it reads.
    Each `up` writes it again, so a plugin update reaches it. The file is replaced in one step
    (rename), so a session that starts meanwhile never runs half a file."""
    path = headers_helper_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o700)
    try:
        os.fchmod(fd, 0o700)
        os.write(fd, HEADERS_HELPER.read_bytes())
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return path


def project_pattern(entries):
    """A regular expression that matches exactly the `owner/name` values of the entries. It holds
    no backslash and no quote, so the Collector config can use it inside a string. `.` is written
    `[.]`. An entry that is not `owner/name` is left out. Raise ValueError when none is left."""
    names = sorted({e["project"] for e in entries if SLUG.fullmatch(e["project"])})
    if not names:
        raise ValueError("no project of the form owner/name")
    return "^(" + "|".join(n.replace(".", "[.]") for n in names) + ")$"


# --- Docker -----------------------------------------------------------------------------------

def docker_problem():
    """A message when Docker cannot be used, else None."""
    if not shutil.which("docker"):
        return "Docker is not installed (no `docker` on PATH). The monitoring stack needs Docker."
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return f"`docker info` did not run: {e}. Is the Docker daemon running?"
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip().splitlines()
        return ("Docker does not answer (`docker info` failed: "
                f"{detail[-1] if detail else 'exit ' + str(res.returncode)}). "
                "Start the Docker daemon or check your access to it.")
    return None


def stack_env(password_file, pattern):
    env = dict(os.environ)
    env.update({
        "AGK_UID": str(os.getuid()),
        "AGK_GID": str(os.getgid()),
        "AGK_GRAFANA_ADMIN_FILE": str(password_file.resolve()),
        "AGK_PROJECT_PATTERN": pattern,
    })
    env.update({name: port(name) for name in PORTS})
    return env


# --- facts.py ---------------------------------------------------------------------------------

def port_in_use(number):
    """True when 127.0.0.1:<number> cannot be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", int(number)))
        except (OSError, ValueError):
            return True
    return False


def gateway_from_inspect(text):
    """The IPv4 gateway address of a network, from the text output of `docker network inspect`, or None
    ("not found"). None for empty text, invalid JSON, no gateway, an IPv6-only gateway, and for an address
    that is `0.0.0.0` or not a private or loopback address. Takes the text, not the docker call."""
    try:
        networks = json.loads(text)
    except (TypeError, ValueError):
        return None
    if isinstance(networks, dict):
        networks = [networks]
    if not isinstance(networks, list):
        return None
    for net in networks:
        ipam = net.get("IPAM") if isinstance(net, dict) else None
        configs = ipam.get("Config") if isinstance(ipam, dict) else None
        for cfg in configs if isinstance(configs, list) else []:
            gateway = cfg.get("Gateway") if isinstance(cfg, dict) else None
            try:
                addr = ipaddress.ip_address(gateway)
            except ValueError:
                continue
            if addr.version != 4 or addr.is_unspecified or addr.is_multicast:
                continue
            if addr.is_private or addr.is_loopback:
                return str(addr)
    return None


def network_gateway():
    """The gateway address of the compose network, or None when it cannot be found."""
    try:
        res = subprocess.run(["docker", "network", "inspect", NETWORK], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return gateway_from_inspect(res.stdout) if res.returncode == 0 else None


def facts_pid():
    """The process id of the running facts.py from the pid file, else None. A dead process, a pid that
    is not facts.py (pid reuse) and an unreadable file give None."""
    try:
        pid = int(facts_pid_path().read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        try:
            if "facts.py" not in cmdline.read_bytes().decode("utf-8", "replace"):
                return None
        except OSError:
            return None
    return pid


def stop_facts():
    """Stop facts.py when it runs and remove the pid file. Never raises."""
    try:
        pid = facts_pid()
        if pid is not None:
            os.kill(pid, 15)
            for _ in range(50):
                time.sleep(0.1)
                if facts_pid() is None:
                    break
            else:
                os.kill(pid, 9)
            say(f"stopped facts.py (pid {pid})")
        facts_pid_path().unlink(missing_ok=True)
    except OSError as e:
        say(f"could not stop facts.py: {e}", err=True)


def facts_command(host):
    """The command that starts facts.py. Raise ValueError for a host that must never be used."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(f"not an IP address: {host!r}") from None
    if addr.is_unspecified or addr.is_multicast or not (addr.is_private or addr.is_loopback):
        raise ValueError(f"refused listen address {host}")
    return [sys.executable, str(FACTS), "--host", str(addr)]


def start_facts(env, host):
    """Start facts.py on `host` in the background; its log goes to facts.log. A failure here is only a
    message: it never stops `up`."""
    try:
        cmd = facts_command(host)
    except ValueError as e:
        say(f"facts.py did not start: {e}", err=True)
        return False
    try:
        log_path = facts_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as log:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=log, start_new_session=True)
        write_private(facts_pid_path(), f"{proc.pid}\n")
    except OSError as e:
        say(f"facts.py did not start: {e}", err=True)
        return False
    say(f"facts.py: http://{host}:{port('AGK_FACTS_PORT')}/metrics  (pid file {facts_pid_path()}, log {facts_log_path()})")
    return True


def compose(env, *args):
    return subprocess.run(["docker", "compose", "-f", str(COMPOSE), *args], env=env).returncode


# --- up / down --------------------------------------------------------------------------------

def start_facts_for_prometheus(env):
    """Find the gateway of the compose network, point the Prometheus target at it and start facts.py on
    it. When the address cannot be found, print one line with the cause and start no facts.py."""
    host = network_gateway()
    if host is None:
        say(f"facts.py was not started: no IPv4 gateway address found for the Docker network {NETWORK} "
            "(`docker network inspect`). The boards miss the facts metrics; the rest runs.", err=True)
        return False
    try:
        facts_command(host)
    except ValueError as e:
        say(f"facts.py was not started: {e}. The boards miss the facts metrics; the rest runs.", err=True)
        return False
    # Prometheus gets the same address as its scrape target. Compose does not see the changed config
    # text, so Prometheus is recreated by force (its data is in a volume); no other service restarts.
    env["AGK_FACTS_HOST"] = host
    if compose(env, "up", "-d", "--force-recreate", "--no-deps", "prometheus") != 0:
        say("facts.py was not started: `docker compose up` could not set the scrape address "
            f"{host}. The boards miss the facts metrics; the rest runs.", err=True)
        return False
    return start_facts(env, host)


def ensure_password():
    """The password file: mode 0600, a random value on the first call, the same value after."""
    path = password_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        os.chmod(path, 0o600)
        if path.read_text(encoding="utf-8").strip():
            return path
        fd = os.open(path, os.O_WRONLY | os.O_TRUNC)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, secrets.token_urlsafe(24).encode("ascii"))
    finally:
        os.close(fd)
    return path


def up():
    problem = docker_problem()
    if problem:
        say(problem, err=True)
        say("nothing was started.", err=True)
        return 2
    try:
        pattern = project_pattern(projects())
    except (RuntimeError, ValueError, OSError) as e:
        say(f"no project list for the Collector: {e}. Nothing was started.", err=True)
        return 2
    try:
        say(f"otelHeadersHelper for the user settings: {install_headers_helper()}")
    except OSError as e:
        say(f"could not write the otelHeadersHelper ({e}); Claude Code data has no project tag.", err=True)
    stop_facts()  # a facts.py of an earlier `up` is replaced, so its port is free
    if port_in_use(port("AGK_FACTS_PORT")):
        say(f"the port {port('AGK_FACTS_PORT')} of facts.py is in use. Set AGK_FACTS_PORT to a free port "
            "and run `up` again. Nothing was started.", err=True)
        return 2
    password_file = ensure_password()
    env = stack_env(password_file, pattern)
    try:
        code = compose(env, "up", "-d")
    except KeyboardInterrupt:
        say("stopped while the stack started; stopping the stack.")
        compose(env, "down")
        return 130
    if code != 0:
        say(f"`docker compose up` failed (exit {code}), for example because a port is in use "
            f"(ports: {', '.join(f'{n}={port(n)}' for n in PORTS)}).", err=True)
        compose(env, "down")
        return 1
    start_facts_for_prometheus(env)
    say(f"Grafana: http://127.0.0.1:{port('AGK_GRAFANA_PORT')}  (user admin, password in {password_file})")
    say(f"OTLP: gRPC 127.0.0.1:{port('AGK_OTLP_GRPC_PORT')}, HTTP http://127.0.0.1:{port('AGK_OTLP_HTTP_PORT')}")
    say(f"Prometheus: http://127.0.0.1:{port('AGK_PROMETHEUS_PORT')}  Loki: http://127.0.0.1:{port('AGK_LOKI_PORT')}")
    say("the stack runs in the background; `board.py down` stops it.")
    return 0


def down():
    stop_facts()
    problem = docker_problem()
    if problem:
        say(f"{problem} Nothing to stop.")
        return 0
    # `down` never reads the project list: the variables only have to be set for compose.
    env = stack_env(password_path(), "^()$")
    code = compose(env, "down")
    if code != 0:
        say(f"`docker compose down` failed (exit {code}).", err=True)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up", help="start the stack in the background")
    sub.add_parser("down", help="stop the stack (exit 0 also when it is not running)")
    args = ap.parse_args(argv)
    return up() if args.cmd == "up" else down()


if __name__ == "__main__":
    sys.exit(main())
