"""Tests for the release channels (issue #326): `scripts/release_channels.py` and the workflows
`release-dev` and `release-stable`.

No test needs the network or GitHub. The workflow steps run in a temp repo with a bare remote and
a fake `gh`. All data is synthetic."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import release_channels

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_channels.py"
WORKFLOWS = ROOT / ".github" / "workflows"
DEV = WORKFLOWS / "release-dev.yml"
STABLE = WORKFLOWS / "release-stable.yml"
MARKETPLACE = ".claude-plugin/marketplace.json"
MANIFEST = "plugin/.claude-plugin/plugin.json"
ON_RELEASE = "startsWith(steps.check.outputs.result, 'release ')"

MARKET_TEXT = (ROOT / MARKETPLACE).read_text(encoding="utf-8")


# --- the script: functions --------------------------------------------------------------------

def _manifest(tmp_path, version):
    path = tmp_path / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "agk", "version": version}, indent=2) + "\n", encoding="utf-8")
    return tmp_path


def test_plugin_version_reads_the_manifest(tmp_path):
    assert release_channels.plugin_version(_manifest(tmp_path, "1.2.3")) == "1.2.3"


def test_plugin_version_of_this_repo_is_a_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", release_channels.plugin_version(ROOT))


@pytest.mark.parametrize("bad", ["0.2", "0.2.0-rc1", "v0.2.0", "0.2.0.1", ""])
def test_not_a_version_exits_1(tmp_path, capsys, bad):
    with pytest.raises(SystemExit) as stop:
        release_channels.plugin_version(_manifest(tmp_path, bad))
    assert stop.value.code == 1
    assert f"not a version: {bad}" in capsys.readouterr().err


def test_new_version_needs_a_release():
    assert release_channels.needs_release("0.2.1", ["v0.1.9", "v0.2.0"]) is True
    assert release_channels.needs_release("0.2.0", []) is True


def test_existing_tag_needs_no_release():
    assert release_channels.needs_release("0.2.0", ["v0.1.9", "v0.2.0"]) is False


def test_tag_match_is_exact():
    assert release_channels.needs_release("0.2.0", ["v0.2.00", "v0.2.0-rc1", "0.2.0", "v10.2.0"]) is True


def test_dev_and_stable_names():
    assert json.loads(release_channels.channel_marketplace(MARKET_TEXT, "dev"))["name"] == "agent-graph-kit-dev"
    assert json.loads(release_channels.channel_marketplace(MARKET_TEXT, "stable"))["name"] == "agent-graph-kit"


def test_marketplace_on_main_is_unchanged():
    assert json.loads(MARKET_TEXT)["name"] == "agent-graph-kit"
    assert release_channels.channel_marketplace(MARKET_TEXT, "stable") == MARKET_TEXT


def test_dev_changes_only_the_name_line():
    before, after = MARKET_TEXT.splitlines(), release_channels.channel_marketplace(MARKET_TEXT, "dev").splitlines()
    assert len(before) == len(after)
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert changed == [('  "name": "agent-graph-kit",', '  "name": "agent-graph-kit-dev",')]


def test_plugins_and_other_keys_unchanged():
    before = json.loads(MARKET_TEXT)
    after = json.loads(release_channels.channel_marketplace(MARKET_TEXT, "dev"))
    assert after["plugins"] == before["plugins"]
    assert after["plugins"][0]["name"] == "agk"
    assert {k: v for k, v in after.items() if k != "name"} == {k: v for k, v in before.items() if k != "name"}


def test_name_is_set_when_it_is_not_the_first_key():
    text = json.dumps({"plugins": [{"name": "agk", "source": "./plugin"}], "name": "agent-graph-kit"}, indent=2)
    after = json.loads(release_channels.channel_marketplace(text, "dev"))
    assert after == {"plugins": [{"name": "agk", "source": "./plugin"}], "name": "agent-graph-kit-dev"}


def test_dev_then_stable_gives_the_text_of_main():
    dev = release_channels.channel_marketplace(MARKET_TEXT, "dev")
    assert release_channels.channel_marketplace(dev, "stable") == MARKET_TEXT


@pytest.mark.parametrize("channel", ["main", "", "Dev", "prod"])
def test_other_channel_raises(channel):
    with pytest.raises(ValueError):
        release_channels.channel_marketplace(MARKET_TEXT, channel)


# --- a temp repo with a bare remote and a fake gh ---------------------------------------------

def _git(cwd, *args):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


def _commit(repo, message):
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _set_version(repo, version):
    path = repo / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "agk", "version": version}, indent=2) + "\n", encoding="utf-8")


FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_LOG"
case "$1 $2" in
  "run list") echo "${FAKE_CI_RUNS:-0}" ;;
  "release view") [ "${FAKE_RELEASE_EXISTS:-0}" = 1 ] || exit 1 ;;
esac
"""


class World:
    """A work clone with a bare remote `origin`, like the checkout of a workflow run."""

    def __init__(self, tmp_path, with_script=True):
        self.tmp = tmp_path
        self.remote = tmp_path / "origin.git"
        self.repo = tmp_path / "repo"
        self.bin = tmp_path / "bin"
        self.gh_log = tmp_path / "gh.log"
        self.runner_temp = tmp_path / "runner-temp"
        for folder in (self.repo, self.bin, self.runner_temp):
            folder.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH, encoding="utf-8")
        gh.chmod(0o755)
        _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.remote))
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / ".claude-plugin").mkdir()
        (self.repo / MARKETPLACE).write_text(MARKET_TEXT, encoding="utf-8")
        _set_version(self.repo, "0.2.0")
        if with_script:
            self.add_script()
        self.first = _commit(self.repo, "first")
        _git(self.repo, "push", "-q", "origin", "main")

    def add_script(self):
        (self.repo / "scripts").mkdir(exist_ok=True)
        shutil.copy2(SCRIPT, self.repo / "scripts" / "release_channels.py")

    def push(self, message):
        sha = _commit(self.repo, message)
        _git(self.repo, "push", "-q", "origin", "main")
        return sha

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
            GH_LOG=str(self.gh_log),
            GITHUB_OUTPUT=str(self.tmp / "github-output"),
            RUNNER_TEMP=str(self.runner_temp),
            # no user identity from the machine: the workflow step has to set its own
            HOME=str(self.tmp / "home"),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
        )
        env.update(extra)
        return env

    def run_step(self, step, **extra):
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", step["run"]], cwd=self.repo, env=self.env(**extra),
            capture_output=True, text=True,
        )

    def outputs(self):
        path = self.tmp / "github-output"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        path.unlink(missing_ok=True)
        return dict(line.split("=", 1) for line in lines)

    def remote_ref(self, ref):
        done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=self.remote, capture_output=True, text=True)
        return done.stdout.strip() or None

    def remote_tags(self):
        return _git(self.remote, "tag", "--list").split()

    def remote_file(self, ref, path):
        return _git(self.remote, "show", f"{ref}:{path}")

    def gh_calls(self):
        return self.gh_log.read_text(encoding="utf-8").splitlines() if self.gh_log.exists() else []


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# --- the script: CLI --------------------------------------------------------------------------

def _cli(world, *args, cwd=None):
    return subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), *args], cwd=cwd or world.repo, env=world.env(),
        capture_output=True, text=True,
    )


def test_cli_check_prints_release_for_a_version_without_tag(world):
    done = _cli(world, "--root", str(world.repo), "check")
    assert (done.returncode, done.stdout) == (0, "release v0.2.0\n")


def test_cli_check_prints_no_release_when_the_tag_exists(world):
    _git(world.repo, "tag", "v0.2.0")
    done = _cli(world, "--root", str(world.repo), "check")
    assert (done.returncode, done.stdout) == (0, "no release\n")


def test_cli_check_exits_1_on_a_bad_version(world):
    _set_version(world.repo, "0.2")
    done = _cli(world, "--root", str(world.repo), "check")
    assert done.returncode == 1
    assert done.stdout == ""
    assert "not a version: 0.2" in done.stderr


def test_cli_marketplace_rewrites_the_file_in_place(world):
    done = _cli(world, "--root", str(world.repo), "marketplace", "dev")
    assert done.returncode == 0, done.stderr
    assert json.loads((world.repo / MARKETPLACE).read_text())["name"] == "agent-graph-kit-dev"
    assert _git(world.repo, "status", "--porcelain").split() == ["M", MARKETPLACE]


def test_cli_marketplace_refuses_another_channel(world):
    done = _cli(world, "--root", str(world.repo), "marketplace", "main")
    assert done.returncode != 0
    assert (world.repo / MARKETPLACE).read_text(encoding="utf-8") == MARKET_TEXT


def test_cli_default_root_is_the_repo_of_the_script(world):
    done = subprocess.run(["uv", "run", "--script", "scripts/release_channels.py", "check"], cwd=world.repo,
                          env=world.env(), capture_output=True, text=True)
    assert (done.returncode, done.stdout) == (0, "release v0.2.0\n")


# --- a small YAML reader for the workflow files (the test env has no PyYAML) -------------------

KEY = re.compile(r"^([A-Za-z0-9_.\-/]+):(?:\s+(.*))?$")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _skip(lines, i):
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    return i


def _scalar(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(part) for part in text[1:-1].split(",") if part.strip()]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return {"true": True, "false": False, "null": None, "~": None}.get(text, text)


def _value(rest, lines, i, indent):
    if rest == "|":
        block = []
        while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) > indent):
            block.append(lines[i])
            i += 1
        while block and not block[-1].strip():
            block.pop()
        cut = min(_indent(line) for line in block if line.strip())
        return "\n".join(line[cut:] for line in block) + "\n", i
    if rest:
        return _scalar(rest), i
    j = _skip(lines, i)
    if j < len(lines) and (_indent(lines[j]) > indent or _indent(lines[j]) == indent and lines[j].lstrip().startswith("- ")):
        return _node(lines, j, _indent(lines[j]))
    return None, i


def _node(lines, i, indent):
    if lines[i].lstrip().startswith("- "):
        out = []
        while True:
            i = _skip(lines, i)
            if i >= len(lines) or _indent(lines[i]) != indent or not lines[i].lstrip().startswith("- "):
                return out, i
            lines[i] = " " * (indent + 2) + lines[i].lstrip()[2:]
            if KEY.match(lines[i].strip()):
                value, i = _node(lines, i, indent + 2)
            else:
                value, i = _scalar(lines[i]), i + 1
            out.append(value)
    out = {}
    while True:
        i = _skip(lines, i)
        if i >= len(lines) or _indent(lines[i]) != indent:
            return out, i
        m = KEY.match(lines[i].strip())
        assert m, f"not a key line: {lines[i]!r}"
        out[m.group(1)], i = _value(m.group(2) or "", lines, i + 1, indent)


def read_yaml(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    value, i = _node(lines, _skip(lines, 0), 0)
    assert _skip(lines, i) == len(lines), f"{path}: lines left after line {i}"
    return value


def triggers(doc):
    """The `on` block. Some YAML readers read the bare key `on` as the boolean True."""
    assert ("on" in doc) != (True in doc), "expected exactly one of the keys `on` and True"
    return doc["on"] if "on" in doc else doc[True]


def steps(path):
    jobs = read_yaml(path)["jobs"]
    assert len(jobs) == 1
    (job,) = jobs.values()
    return job["steps"]


def step(path, name):
    found = [s for s in steps(path) if s.get("name") == name]
    assert len(found) == 1, f"{path.name}: expected one step named {name!r}"
    return found[0]


def index(path, name):
    return steps(path).index(step(path, name))


def test_reader_reads_the_forms_the_workflows_use(tmp_path):
    path = tmp_path / "w.yml"
    path.write_text(
        "# comment\nname: w\non:\n  push:\n    branches: [main, 'x']\n\njobs:\n  a:\n    steps:\n"
        "      - uses: actions/checkout@v7\n        with:\n          fetch-depth: 0\n"
        "      - name: Two lines\n        if: startsWith(a.b, 'release ')\n        run: |\n"
        "          echo one\n\n          # kept\n          echo \"two: $X\"\n      - run: echo x\n",
        encoding="utf-8",
    )
    assert read_yaml(path) == {
        "name": "w",
        "on": {"push": {"branches": ["main", "x"]}},
        "jobs": {"a": {"steps": [
            {"uses": "actions/checkout@v7", "with": {"fetch-depth": 0}},
            {"name": "Two lines", "if": "startsWith(a.b, 'release ')", "run": 'echo one\n\n# kept\necho "two: $X"\n'},
            {"run": "echo x"},
        ]}},
    }


def test_reader_agrees_with_pyyaml_when_present():
    yaml = pytest.importorskip("yaml")
    for path in (DEV, STABLE):
        theirs = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert read_yaml(path) == {("on" if k is True else k): v for k, v in theirs.items()}, path


def test_triggers_are_found_under_on_or_true():
    assert triggers({"on": {"push": None}}) == {"push": None}
    assert triggers({True: {"push": None}}) == {"push": None}


# --- both workflow files ----------------------------------------------------------------------

@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_workflow_parses_and_is_named_after_its_file(path):
    assert read_yaml(path)["name"] == path.stem


@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_workflow_may_write_contents(path):
    assert read_yaml(path)["permissions"]["contents"] == "write"


@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_workflow_checks_out_with_all_tags(path):
    checkout = [s for s in steps(path) if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkout) == 1
    assert checkout[0]["with"]["fetch-depth"] == 0
    assert steps(path).index(checkout[0]) == 0


@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_workflow_calls_the_script(path):
    assert any("release_channels.py" in s.get("run", "") for s in steps(path))


@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_workflow_uses_only_the_default_token(path):
    text = path.read_text(encoding="utf-8")
    assert "secrets." not in text
    for found in re.findall(r"\$\{\{(.*?)\}\}", text):
        assert found.strip() in {"github.token", "inputs.tag", "steps.check.outputs.tag"}, found


@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_no_expression_inside_a_run_script(path):
    for s in steps(path):
        assert "${{" not in s.get("run", ""), s.get("name")


@pytest.mark.parametrize("path", [DEV, STABLE], ids=lambda p: p.name)
def test_one_run_at_a_time(path):
    doc = read_yaml(path)
    assert doc["concurrency"] == {"group": path.stem, "cancel-in-progress": False}


def _writes(s):
    """True when the step sets a tag, moves a branch or writes a release."""
    return bool(re.search(r"\bgit (tag|push|commit)\b|\bgh release (create|edit)\b", s.get("run", "")))


# --- release-dev.yml --------------------------------------------------------------------------

def test_dev_runs_on_a_push_to_main_only():
    assert triggers(read_yaml(DEV)) == {"push": {"branches": ["main"]}}


def test_dev_check_step_calls_check():
    check = step(DEV, "Check for a new plugin version")
    assert check["id"] == "check"
    assert "release_channels.py check" in check["run"]
    assert "if" not in check


def test_dev_test_step_runs_the_test_command():
    assert step(DEV, "Run the tests")["run"].strip() == "uv run --with pytest pytest"


def test_dev_test_step_is_before_any_tag_or_branch_step():
    all_steps = steps(DEV)
    writing = [i for i, s in enumerate(all_steps) if _writes(s)]
    assert [all_steps[i]["name"] for i in writing] == ["Create the tag", "Create the pre-release", "Move the branch dev"]
    assert index(DEV, "Check for a new plugin version") < index(DEV, "Run the tests") < min(writing)


def test_dev_steps_after_the_check_run_only_on_a_release():
    all_steps = steps(DEV)
    after = all_steps[index(DEV, "Check for a new plugin version") + 1:]
    assert len(after) == 4
    for s in after:
        assert s["if"] == ON_RELEASE, s["name"]
        assert "continue-on-error" not in s


def test_dev_steps_take_the_tag_from_the_check():
    for name in ("Create the tag", "Create the pre-release", "Move the branch dev"):
        assert step(DEV, name)["env"]["TAG"] == "${{ steps.check.outputs.tag }}"


def _dev_run(world):
    """Run the steps of release-dev as GitHub would. Returns the names of the steps that ran."""
    ran = []
    _git(world.repo, "fetch", "-q", "--tags", "origin")
    _git(world.repo, "checkout", "-q", "--detach", "origin/main")
    check = step(DEV, "Check for a new plugin version")
    done = world.run_step(check)
    assert done.returncode == 0, done.stderr
    ran.append(check["name"])
    out = world.outputs()
    for s in steps(DEV)[index(DEV, check["name"]) + 1:]:
        assert s["if"] == ON_RELEASE
        if not out["result"].startswith("release "):
            continue
        ran.append(s["name"])
        if s["name"] == "Run the tests":
            continue  # the suite does not run itself
        done = world.run_step(s, TAG=out["tag"])
        assert done.returncode == 0, f"{s['name']}: {done.stderr}"
    return ran, out


def test_dev_run_with_a_new_version_tags_and_moves_dev(world):
    ran, out = _dev_run(world)
    assert out == {"result": "release v0.2.0", "tag": "v0.2.0"}
    assert ran == ["Check for a new plugin version", "Run the tests", "Create the tag", "Create the pre-release",
                   "Move the branch dev"]
    assert world.remote_tags() == ["v0.2.0"]
    assert world.remote_ref("refs/tags/v0.2.0^{commit}") == world.first
    assert world.remote_ref("refs/heads/dev^") == world.first
    assert _git(world.remote, "diff", "--name-only", "dev^", "dev").split() == [MARKETPLACE]
    assert json.loads(world.remote_file("dev", MARKETPLACE))["name"] == "agent-graph-kit-dev"
    assert world.remote_ref("refs/heads/main") == world.first
    assert json.loads(world.remote_file("main", MARKETPLACE))["name"] == "agent-graph-kit"


def test_dev_run_creates_a_pre_release_for_the_tag(world):
    _dev_run(world)
    calls = world.gh_calls()
    assert len(calls) == 1
    assert calls[0].startswith("release create v0.2.0 ")
    assert "--prerelease" in calls[0].split()
    assert "--verify-tag" in calls[0].split()


def test_dev_run_without_a_new_version_does_nothing_more(world):
    _dev_run(world)
    dev = world.remote_ref("refs/heads/dev")
    _git(world.repo, "checkout", "-q", "main")
    (world.repo / "note.txt").write_text("a push without a version change\n", encoding="utf-8")
    world.push("no bump")
    world.gh_log.unlink()
    ran, out = _dev_run(world)
    assert out == {"result": "no release", "tag": ""}
    assert ran == ["Check for a new plugin version"]
    assert world.remote_tags() == ["v0.2.0"]
    assert world.remote_ref("refs/tags/v0.2.0^{commit}") == world.first
    assert world.remote_ref("refs/heads/dev") == dev
    assert world.gh_calls() == []


def test_dev_run_with_the_next_version_force_moves_dev(world):
    _dev_run(world)
    _git(world.repo, "checkout", "-q", "main")
    _set_version(world.repo, "0.2.1")
    second = world.push("bump")
    ran, out = _dev_run(world)
    assert out["tag"] == "v0.2.1"
    assert world.remote_tags() == ["v0.2.0", "v0.2.1"]
    assert world.remote_ref("refs/tags/v0.2.1^{commit}") == second
    assert world.remote_ref("refs/heads/dev^") == second
    assert json.loads(world.remote_file("dev", MARKETPLACE))["name"] == "agent-graph-kit-dev"
    assert json.loads(world.remote_file("dev", MANIFEST))["version"] == "0.2.1"


def test_dev_run_stops_on_a_bad_version(world):
    _set_version(world.repo, "0.2")
    world.push("bad version")
    done = world.run_step(step(DEV, "Check for a new plugin version"))
    assert done.returncode != 0
    assert "not a version: 0.2" in done.stderr
    assert world.remote_tags() == []


# --- release-stable.yml -----------------------------------------------------------------------

GATE = "Check the tag and its ci run"
CHECKOUT = "Check out the tag"
TESTS = "Run the tests"
MOVE = "Move the branch stable"
RELEASE = "Make the release the latest release"


def test_stable_runs_by_hand_with_the_input_tag():
    on = triggers(read_yaml(STABLE))
    assert list(on) == ["workflow_dispatch"]
    assert list(on["workflow_dispatch"]["inputs"]) == ["tag"]
    assert on["workflow_dispatch"]["inputs"]["tag"]["required"] is True


def test_stable_may_read_the_ci_runs():
    assert read_yaml(STABLE)["permissions"] == {"contents": "write", "actions": "read"}


def test_stable_gate_is_before_any_branch_or_release_step():
    all_steps = steps(STABLE)
    writing = [i for i, s in enumerate(all_steps) if _writes(s)]
    assert [all_steps[i]["name"] for i in writing] == [MOVE, RELEASE]
    assert index(STABLE, GATE) < min(writing)
    for s in all_steps:
        assert "if" not in s and "continue-on-error" not in s, s.get("name")


def test_stable_test_step_runs_the_test_command():
    assert step(STABLE, TESTS)["run"].strip() == "uv run --with pytest pytest"


def test_stable_test_step_is_before_any_tag_or_branch_step():
    all_steps = steps(STABLE)
    writing = [i for i, s in enumerate(all_steps) if _writes(s)]
    assert index(STABLE, GATE) < index(STABLE, CHECKOUT) < index(STABLE, TESTS) < min(writing)


def test_stable_steps_take_the_tag_from_the_input():
    for name in (GATE, CHECKOUT, MOVE, RELEASE):
        assert step(STABLE, name)["env"]["TAG"] == "${{ inputs.tag }}"


def test_stable_gate_asks_for_a_successful_run_of_ci():
    words = step(STABLE, GATE)["run"].split()
    for flag, value in (("--workflow", "ci.yml"), ("--status", "success"), ("--commit", '"$sha"')):
        assert words[words.index(flag) + 1] == value
    assert (WORKFLOWS / "ci.yml").is_file()
    assert read_yaml(WORKFLOWS / "ci.yml")["name"] == "ci"


def _stable_run(world, tag, ci_runs, release_exists=False):
    """Run the steps of release-stable as GitHub would: stop at the first step that fails.

    The test step does not run the suite; it records the commit it would test in `world.tested`."""
    _git(world.repo, "fetch", "-q", "--tags", "origin")
    _git(world.repo, "checkout", "-q", "--detach", "origin/main")
    world.tested = None
    for s in steps(STABLE):
        if "run" not in s:
            continue
        if s["name"] == TESTS:
            world.tested = _git(world.repo, "rev-parse", "HEAD")
            continue  # the suite does not run itself
        done = world.run_step(s, TAG=tag, FAKE_CI_RUNS=str(ci_runs), FAKE_RELEASE_EXISTS="1" if release_exists else "0")
        if done.returncode != 0:
            return s["name"], done
    return None, None


@pytest.fixture
def tagged(tmp_path):
    """v0.2.0 is on a commit without the script (like the hand-set first tag), v0.2.1 on a later one."""
    world = World(tmp_path, with_script=False)
    _git(world.repo, "tag", "v0.2.0", world.first)
    world.add_script()
    _set_version(world.repo, "0.2.1")
    world.second = world.push("bump")
    _git(world.repo, "tag", "v0.2.1", world.second)
    (world.repo / "later.txt").write_text("main goes on\n", encoding="utf-8")
    world.third = world.push("later")
    _git(world.repo, "push", "-q", "origin", "v0.2.0", "v0.2.1")
    return world


def test_stable_stops_when_the_tag_does_not_exist(tagged):
    failed, done = _stable_run(tagged, "v9.9.9", ci_runs=1)
    assert failed == GATE
    assert "tag v9.9.9 does not exist" in done.stdout + done.stderr
    assert tagged.remote_ref("refs/heads/stable") is None
    assert tagged.gh_calls() == []


def test_stable_stops_when_the_input_is_a_branch_name(tagged):
    failed, _ = _stable_run(tagged, "main", ci_runs=1)
    assert failed == GATE
    assert tagged.remote_ref("refs/heads/stable") is None


def test_stable_stops_when_the_commit_has_no_successful_ci_run(tagged):
    failed, done = _stable_run(tagged, "v0.2.0", ci_runs=0)
    assert failed == GATE
    assert tagged.tested is None
    assert f"no successful run of the workflow ci for {tagged.first}" in done.stdout + done.stderr
    assert tagged.remote_ref("refs/heads/stable") is None
    assert [c.split()[:2] for c in tagged.gh_calls()] == [["run", "list"]]


def test_stable_moves_the_branch_to_the_hand_set_tag_and_creates_its_release(tagged):
    failed, done = _stable_run(tagged, "v0.2.0", ci_runs=1)
    assert failed is None, done and done.stderr
    assert tagged.tested == tagged.first  # the tests run on the commit of the tag, not on main
    assert tagged.remote_ref("refs/heads/stable") == tagged.first
    assert json.loads(tagged.remote_file("stable", MARKETPLACE))["name"] == "agent-graph-kit"
    assert json.loads(tagged.remote_file("stable", MANIFEST))["version"] == "0.2.0"
    run_list, view, create = tagged.gh_calls()
    assert f"--commit {tagged.first}" in run_list
    assert view.startswith("release view v0.2.0")
    assert create.startswith("release create v0.2.0 ")
    assert "--latest" in create.split() and "--verify-tag" in create.split()
    assert "--prerelease" not in create


def test_stable_makes_an_existing_pre_release_a_full_latest_release(tagged):
    failed, done = _stable_run(tagged, "v0.2.1", ci_runs=1, release_exists=True)
    assert failed is None, done and done.stderr
    assert tagged.remote_ref("refs/heads/stable") == tagged.second
    edit = tagged.gh_calls()[-1].split()
    assert edit[:3] == ["release", "edit", "v0.2.1"]
    assert "--prerelease=false" in edit and "--draft=false" in edit and "--latest" in edit
    assert not any(c.startswith("release create") for c in tagged.gh_calls())


def test_stable_rollback_moves_the_branch_back_to_the_older_tag(tagged):
    assert _stable_run(tagged, "v0.2.1", ci_runs=1, release_exists=True)[0] is None
    assert tagged.remote_ref("refs/heads/stable") == tagged.second
    assert _stable_run(tagged, "v0.2.0", ci_runs=1, release_exists=True)[0] is None
    assert tagged.remote_ref("refs/heads/stable") == tagged.first
    assert tagged.remote_ref("refs/heads/main") == tagged.third
    assert tagged.remote_tags() == ["v0.2.0", "v0.2.1"]


def test_stable_puts_the_stable_name_on_a_commit_with_another_name(tagged):
    _git(tagged.repo, "checkout", "-q", "main")
    path = tagged.repo / MARKETPLACE
    path.write_text(release_channels.channel_marketplace(MARKET_TEXT, "dev"), encoding="utf-8")
    _set_version(tagged.repo, "0.2.2")
    fourth = tagged.push("another name")
    _git(tagged.repo, "tag", "v0.2.2", fourth)
    _git(tagged.repo, "push", "-q", "origin", "v0.2.2")
    failed, done = _stable_run(tagged, "v0.2.2", ci_runs=1, release_exists=True)
    assert failed is None, done and done.stderr
    assert tagged.remote_ref("refs/heads/stable^") == fourth
    assert _git(tagged.remote, "diff", "--name-only", "stable^", "stable").split() == [MARKETPLACE]
    assert json.loads(tagged.remote_file("stable", MARKETPLACE))["name"] == "agent-graph-kit"


# --- the owner's checklist --------------------------------------------------------------------

CHECKLIST = ROOT / "docs" / "checks" / "release-channels.md"


def _checklist_steps():
    text = CHECKLIST.read_text(encoding="utf-8")
    parts = re.split(r"^## Step (\d+): .*$", text, flags=re.M)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def test_checklist_has_seven_numbered_steps_in_order():
    numbers = re.findall(r"^## Step (\d+): ", CHECKLIST.read_text(encoding="utf-8"), flags=re.M)
    assert numbers == [str(n) for n in range(1, 8)]


def test_each_checklist_action_has_a_should_see_and_an_if_not():
    for number, body in _checklist_steps().items():
        sees, nots = body.count("You should see:"), body.count("If not:")
        assert sees >= 1 and sees == nots, f"step {number}: {sees} 'You should see:' and {nots} 'If not:'"


def test_checklist_steps_name_the_commands_of_the_issue():
    s = _checklist_steps()
    assert "git tag v0.2.0 e2295d7" in s[1] and "git push origin v0.2.0" in s[1]
    assert "git push origin main" in s[2]
    assert "release-stable" in s[3] and "`v0.2.0`" in s[3]
    assert "claude plugin marketplace add Lighfe/agent-graph-kit#stable" in s[4]
    assert "claude plugin install agk@agent-graph-kit " in s[4] and "0.2.0" in s[4]
    assert "release-dev" in s[5] and "git ls-remote" in s[5]
    assert "claude plugin marketplace add Lighfe/agent-graph-kit#dev" in s[6]
    assert "agk@agent-graph-kit-dev" in s[6]
    assert s[7].count("release-stable") >= 2 and "`v0.2.0`" in s[7]


def _checklist_actions():
    """(step, letter, text) for each action **a.**, **b.**, ... of the checklist."""
    found = []
    for number, body in _checklist_steps().items():
        parts = re.split(r"^\*\*([a-z])\.\*\* ", body, flags=re.M)
        found += [(number, parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
    return found


def test_each_checklist_action_has_one_should_see_and_one_if_not():
    for number, letter, text in _checklist_actions():
        assert text.count("You should see:") == 1 and text.count("If not:") == 1, f"{number}{letter}"


ACTION_FORMS = (
    "Copy this command",
    "Wait two minutes. Then copy this command",
    "Open this page in the browser:",
    "Click ",
    "Type ",
)


def test_each_checklist_action_is_a_command_a_page_a_click_or_a_value():
    for number, letter, text in _checklist_actions():
        assert text.startswith(ACTION_FORMS), f"{number}{letter}: {text.splitlines()[0]!r}"


def test_rollback_ends_with_the_written_down_version():
    rollback = _checklist_steps()[7]
    letters = [l for n, l, _ in _checklist_actions() if n == 7]
    assert letters == list("abcdef")
    assert "Write down which one you got." in rollback


def test_each_click_action_is_one_named_click():
    clicks = [(n, l, t) for n, l, t in _checklist_actions() if t.startswith("Click")]
    assert clicks, "the checklist has click actions (step 3)"
    for number, letter, text in clicks:
        action = text.split("You should see:")[0]
        assert len(re.findall(r"\*\*[^*]+\*\*", action)) == 1, f"{number}{letter}: {action!r}"


def test_each_command_action_is_one_command_block():
    for number, letter, text in _checklist_actions():
        if text.startswith("Copy this command"):
            action = text.split("You should see:")[0]
            assert action.count("```") == 2, f"{number}{letter}"


def test_claude_actions_name_the_exact_output():
    s = _checklist_steps()
    for line in (
        "✔ Successfully removed marketplace: agent-graph-kit",
        "(ref: stable)",
        "✔ Successfully added marketplace: agent-graph-kit (declared in user settings)",
        'Installing plugin "agk@agent-graph-kit"...✔ Successfully installed plugin: agk@agent-graph-kit (scope: project)',
        "    Version: 0.2.0",
    ):
        assert line in s[4], line
    for line in (
        "(ref: dev)",
        "✔ Successfully added marketplace: agent-graph-kit-dev (declared in user settings)",
        'Installing plugin "agk@agent-graph-kit-dev"...✔ Successfully installed plugin: agk@agent-graph-kit-dev (scope: project)',
    ):
        assert line in s[6], line
    assert '✔ Plugin "agk" updated from 0.2.0 to ' in s[7]
    assert "✓ Created workflow_dispatch event for release-stable.yml at main" in s[7]


def test_checklist_names_no_output_in_vague_words():
    text = CHECKLIST.read_text(encoding="utf-8")
    for vague in ("a line that says", "a last line that says", "one line that says"):
        assert vague not in text, vague


def test_checklist_tags_before_it_pushes_main():
    text = CHECKLIST.read_text(encoding="utf-8")
    assert text.index("git push origin v0.2.0") < text.index("git push origin main")


# --- the checklist is for the kit repo only: the plugin does not ship it ------------------------

SHIPPED = "templates/docs/checks/release-channels.md"


def test_checklist_is_not_a_plugin_template():
    import build_plugin

    assert CHECKLIST.is_file()
    assert not (ROOT / "plugin" / SHIPPED).exists()
    assert build_plugin.differences() == []


def test_build_does_not_copy_the_checklist(monkeypatch, tmp_path):
    import build_plugin

    copy = tmp_path / "plugin"
    shutil.copytree(ROOT / "plugin", copy)
    monkeypatch.setattr(build_plugin, "PLUGIN", copy)
    build_plugin.build()
    assert not (copy / SHIPPED).exists()
    assert (copy / "templates/docs/checks/hook-activation.md").is_file()
    assert build_plugin.differences() == []


def test_a_copy_of_the_checklist_in_the_plugin_is_reported(monkeypatch, tmp_path):
    import build_plugin

    copy = tmp_path / "plugin"
    shutil.copytree(ROOT / "plugin", copy)
    monkeypatch.setattr(build_plugin, "PLUGIN", copy)
    (copy / SHIPPED).write_text("x\n", encoding="utf-8")
    assert build_plugin.differences() == [f"extra: plugin/{SHIPPED}"]
