#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Start and stop the optional Grafana stack of the monitor skill (issue #283).

  uv run --script board.py up      check Docker, start Grafana, then run the loader in the foreground;
                                   Ctrl-C stops the loader and the stack
  uv run --script board.py down    stop the stack; exit 0 also when it is not running

Grafana runs in Docker (`compose.yaml` next to this file) and reads `monitor.sqlite` read-only.
The loader (`store.py load`) runs on the host. Docker is needed for this part only.
The admin password is in `<state dir>/grafana-admin` (mode 0600, made on the first `up`);
this script prints the path of the file, never the value.
Spec: docs/specs/2026-11-06-visual-monitoring.md, Part C
"""

import argparse
import importlib.util
import os
import secrets
import shutil
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose.yaml"
STORE = HERE / "store.py"
DEFAULT_PORT = "3000"


def _load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = _load("agk_monitor_store", STORE)


def say(text, err=False):
    print(f"board: {text}", file=sys.stderr if err else sys.stdout, flush=True)


# --- paths ------------------------------------------------------------------------------------

def password_path():
    return store.data.state_dir() / "grafana-admin"


def port():
    return os.environ.get("AGK_GRAFANA_PORT") or DEFAULT_PORT


def private_dirs():
    """Folders with credentials that must never be inside the mounted db folder."""
    home = Path.home()
    return [home / ".claude", home / ".codex", home / ".config" / "gh", home / ".ssh"]


def unsafe_db_dir(folder):
    """A reason when the db folder must not be mounted into the container, else None."""
    folder = folder.resolve()
    home = Path.home().resolve()
    if folder == Path("/") or folder == home:
        return f"the db folder {folder} is the root or the home folder"
    for private in private_dirs():
        private = private.resolve()
        if private == folder or private.is_relative_to(folder) or folder.is_relative_to(private):
            return f"the db folder {folder} holds or is inside {private}"
    return None


# --- Docker -----------------------------------------------------------------------------------

def docker_problem():
    """A message when Docker cannot be used, else None."""
    if not shutil.which("docker"):
        return "Docker is not installed (no `docker` on PATH). The Grafana board needs Docker."
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


def stack_env(db, password_file):
    env = dict(os.environ)
    env.update({
        "AGK_UID": str(os.getuid()),
        "AGK_GID": str(os.getgid()),
        "AGK_MONITOR_DB_DIR": str(db.parent.resolve()),
        "AGK_MONITOR_DB_NAME": db.name,
        "AGK_GRAFANA_ADMIN_FILE": str(password_file.resolve()),
        "AGK_GRAFANA_PORT": port(),
    })
    return env


def compose(env, *args):
    return subprocess.run(["docker", "compose", "-f", str(COMPOSE), *args], env=env).returncode


# --- up / down --------------------------------------------------------------------------------

def ensure_db():
    """Create the db when it is missing, so Docker never makes a folder in its place."""
    db = store.db_path()
    store.connect(db).close()
    return db


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


class Loader:
    """The loader `store.py load` as a child process; SIGINT and SIGTERM are passed on to it."""

    def __init__(self):
        self.proc = None
        self.stopped = False

    def on_signal(self, signum, _frame):
        self.stopped = True
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.send_signal(signal.SIGINT if signum == signal.SIGINT else signal.SIGTERM)
            except ProcessLookupError:
                pass

    def run(self):
        signal.signal(signal.SIGINT, self.on_signal)
        signal.signal(signal.SIGTERM, self.on_signal)
        self.proc = subprocess.Popen([sys.executable, str(STORE), "load"])
        if self.stopped:  # a signal came before the child existed
            self.proc.send_signal(signal.SIGINT)
        return self.proc.wait()


def up():
    problem = docker_problem()
    if problem:
        say(problem, err=True)
        say("nothing was started.", err=True)
        return 2
    db = store.db_path()
    reason = unsafe_db_dir(db.parent)
    if reason:
        say(f"{reason}; set MONITOR_DB_FILE to a file in a folder of its own. Nothing was started.",
            err=True)
        return 2
    db = ensure_db()
    password_file = ensure_password()
    env = stack_env(db, password_file)
    try:
        code = compose(env, "up", "-d")
    except KeyboardInterrupt:
        say("stopped while the stack started; stopping the stack.")
        compose(env, "down")
        return 130
    if code != 0:
        say(f"`docker compose up` failed (exit {code}), for example because port {port()} is in use. "
            "The loader was not started.", err=True)
        compose(env, "down")
        return 1
    say(f"Grafana: http://127.0.0.1:{port()}  (user admin, password in {password_file})")
    say(f"db: {db}")
    say("the loader runs now; Ctrl-C stops the loader and the stack.")
    loader = Loader()
    try:
        status = loader.run()
    finally:
        say("stopping the stack.")
        down_code = compose(env, "down")
    if down_code != 0:
        say(f"`docker compose down` failed (exit {down_code}).", err=True)
        return 1
    if loader.stopped:
        return 0
    say(f"the loader ended with exit {status}; the stack is stopped.", err=True)
    return status or 1


def down():
    problem = docker_problem()
    if problem:
        say(f"{problem} Nothing to stop.")
        return 0
    db = store.db_path()
    env = stack_env(db, password_path())
    code = compose(env, "down")
    if code != 0:
        say(f"`docker compose down` failed (exit {code}).", err=True)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up", help="start Grafana, then run the loader until Ctrl-C")
    sub.add_parser("down", help="stop the stack (exit 0 also when it is not running)")
    args = ap.parse_args(argv)
    return up() if args.cmd == "up" else down()


if __name__ == "__main__":
    sys.exit(main())
