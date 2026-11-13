"""Tests for the otelHeadersHelper of the monitor skill (issue #324): `otel_headers.py`.

The script finds the kit project of a Claude Code session from the session folder and
`monitor-projects.json` next to itself. No test needs Docker or the network. All data is synthetic."""

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "plugin" / "skills" / "monitor" / "otel_headers.py"


def module():
    spec = importlib.util.spec_from_file_location("agk_otel_headers", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def world(tmp_path):
    """A state folder with the helper copied in (as `board.py up` does), a project list with two kit
    projects, a repo that is not in the list and a plain folder."""
    state = tmp_path / "state" / "agent-graph-kit"
    state.mkdir(parents=True)
    helper = state / "otel-headers.py"
    shutil.copyfile(HELPER, helper)
    helper.chmod(0o700)
    kit = tmp_path / "work" / "kit"
    other_kit = tmp_path / "work" / "other-kit"
    foreign = tmp_path / "work" / "foreign-repo"
    plain = tmp_path / "plain"
    for p in (kit / "src" / "deep", other_kit, foreign, plain):
        p.mkdir(parents=True)
    for repo in (kit, other_kit, foreign):
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (state / "monitor-projects.json").write_text(json.dumps([
        {"project": "Synthetic/kit", "repo": str(kit)},
        {"project": "Synthetic/other-kit", "repo": str(other_kit)},
    ]))
    return {"state": state, "helper": helper, "kit": kit, "other_kit": other_kit,
            "foreign": foreign, "plain": plain}


def run_helper(helper, cwd, interpreter_args=()):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd)}
    start = time.monotonic()
    res = subprocess.run([sys.executable, *interpreter_args, str(helper)], cwd=cwd, capture_output=True,
                         text=True, timeout=10, env=env, stdin=subprocess.DEVNULL)
    return res, time.monotonic() - start


# --- the project of a session ------------------------------------------------------------------

@pytest.mark.parametrize("where, want", [
    ("kit", {"x-agk-project": "Synthetic/kit"}),
    ("kit/src", {"x-agk-project": "Synthetic/kit"}),
    ("kit/src/deep", {"x-agk-project": "Synthetic/kit"}),
    ("other_kit", {"x-agk-project": "Synthetic/other-kit"}),
    ("foreign", {}),   # a git repo that is not in the project list
    ("plain", {}),     # no git repo
])
def test_session_folder_gives_the_project_or_nothing(world, where, want):
    name, *sub = where.split("/")
    cwd = world[name].joinpath(*sub)
    res, seconds = run_helper(world["helper"], cwd)
    assert res.returncode == 0
    assert json.loads(res.stdout) == want
    assert res.stderr == ""  # no error or warning output
    assert seconds < 2


def test_a_folder_that_only_starts_with_the_repo_name_is_outside(world):
    twin = world["kit"].parent / "kit-copy"
    twin.mkdir()
    res, _ = run_helper(world["helper"], twin)
    assert json.loads(res.stdout) == {}


def test_the_deepest_repo_wins_and_symlinks_are_resolved(tmp_path):
    mod = module()
    outer = tmp_path / "outer"
    inner = outer / "inner"
    (inner / "x").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(inner)
    entries = [{"project": "a/outer", "repo": str(outer)}, {"project": "a/inner", "repo": str(link)}]
    assert mod.project_for(str(inner / "x"), entries) == "a/inner"
    assert mod.project_for(str(outer), entries) == "a/outer"
    assert mod.project_for(str(link / "x"), entries) == "a/inner"


def test_bad_entries_are_skipped():
    mod = module()
    entries = ["x", {"project": "not a slug", "repo": "/"}, {"project": "a/b"}, {"project": "a/b", "repo": ""},
               {"project": 3, "repo": "/"}]
    assert mod.project_for("/tmp", entries) is None


@pytest.mark.parametrize("content", [None, "", "not json", "{}", '{"project": "a/b"}', "[1, 2]"])
def test_a_missing_or_broken_list_gives_an_empty_object_and_exit_0(world, content):
    path = world["state"] / "monitor-projects.json"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    res, seconds = run_helper(world["helper"], world["kit"])
    assert res.returncode == 0 and res.stderr == ""
    assert json.loads(res.stdout) == {}
    assert seconds < 2


def test_the_list_next_to_the_helper_is_read_not_the_one_of_the_environment(world, tmp_path):
    # XDG_STATE_HOME of the session does not matter: the helper reads the list in its own folder.
    env_state = tmp_path / "other-state" / "agent-graph-kit"
    env_state.mkdir(parents=True)
    (env_state / "monitor-projects.json").write_text(json.dumps([{"project": "x/y", "repo": str(world["plain"])}]))
    res = subprocess.run([sys.executable, str(world["helper"])], cwd=world["plain"], capture_output=True,
                         text=True, timeout=10, env={**os.environ, "XDG_STATE_HOME": str(tmp_path / "other-state")})
    assert json.loads(res.stdout) == {}


def test_output_is_a_json_object_of_strings(world):
    # Claude Code refuses empty output, a non-object and a non-string value (otelHeadersHelper rules).
    for where in ("kit", "plain"):
        res, _ = run_helper(world["helper"], world[where])
        out = json.loads(res.stdout)
        assert isinstance(out, dict) and all(isinstance(v, str) for v in out.values())
        assert res.stdout.strip()


# --- no network call, no process ---------------------------------------------------------------

def test_the_helper_imports_nothing_that_reaches_the_network_or_starts_a_process():
    tree = ast.parse(HELPER.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= {"json", "os", "re", "sys", "pathlib"}, names
    text = HELPER.read_text()
    for word in ("subprocess", "socket", "urllib", "http", "system(", "popen", "exec"):
        assert word not in text.split('"""', 2)[2], word


def test_the_helper_runs_with_sockets_and_processes_blocked(world, tmp_path):
    # A sitecustomize that makes every socket and process start raise: the helper still prints its answer.
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import socket, subprocess, os\n"
        "def _no(*a, **k):\n    raise RuntimeError('network or process call')\n"
        "socket.socket = _no\nsocket.create_connection = _no\nsocket.getaddrinfo = _no\n"
        "subprocess.Popen = _no\nos.system = _no\nos.posix_spawn = _no\nos.fork = _no\n")
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(guard)}
    res = subprocess.run([sys.executable, str(world["helper"])], cwd=world["kit"], capture_output=True, text=True,
                         timeout=10, env=env)
    assert res.returncode == 0 and res.stderr == ""
    assert json.loads(res.stdout) == {"x-agk-project": "Synthetic/kit"}
