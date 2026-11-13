#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Start and stop the optional monitoring stack of the monitor skill (issue #309).

  uv run --script board.py up      check Docker, start the stack in the background, print the URLs
  uv run --script board.py down    stop the stack; exit 0 also when it is not running

The stack (`compose.yaml` next to this file) is the OTel Collector, Prometheus, Loki and Grafana in Docker.
Every port is on 127.0.0.1 only. Docker is needed for this part only.
The Collector keeps only data of the projects in `<state dir>/monitor-projects.json`; `up` writes that
file once with the current project when it is missing. The admin password of Grafana is in
`<state dir>/grafana-admin` (mode 0600, made on the first `up`); this script prints the path, never the value.
Spec: docs/specs/2026-11-13-otel-monitoring-boards.md, Part B
"""

import argparse
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose.yaml"
DATA = HERE / "data.py"

# The ports of the stack: environment variable and default. `compose.yaml` has the same defaults.
PORTS = {
    "AGK_OTLP_GRPC_PORT": "4317",
    "AGK_OTLP_HTTP_PORT": "4318",
    "AGK_PROMETHEUS_PORT": "9090",
    "AGK_LOKI_PORT": "3100",
    "AGK_GRAFANA_PORT": "3000",
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

def password_path():
    return data.state_dir() / "grafana-admin"


def projects_path():
    return data.state_dir() / "monitor-projects.json"


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


def compose(env, *args):
    return subprocess.run(["docker", "compose", "-f", str(COMPOSE), *args], env=env).returncode


# --- up / down --------------------------------------------------------------------------------

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
    say(f"Grafana: http://127.0.0.1:{port('AGK_GRAFANA_PORT')}  (user admin, password in {password_file})")
    say(f"OTLP: gRPC 127.0.0.1:{port('AGK_OTLP_GRPC_PORT')}, HTTP http://127.0.0.1:{port('AGK_OTLP_HTTP_PORT')}")
    say(f"Prometheus: http://127.0.0.1:{port('AGK_PROMETHEUS_PORT')}  Loki: http://127.0.0.1:{port('AGK_LOKI_PORT')}")
    say("the stack runs in the background; `board.py down` stops it.")
    return 0


def down():
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
