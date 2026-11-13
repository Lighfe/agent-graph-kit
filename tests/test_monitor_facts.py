"""Tests for `facts.py` of the monitor skill (issue #310): stage issues, the attribution marker and usage
limits as Prometheus metrics.

No test uses the network: `gh` is the fake in `tests/fakes/monitor/facts/` that answers from a JSON file.
All data is synthetic."""

import importlib.util
import json
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKES = ROOT / "tests" / "fakes" / "monitor" / "facts"
FACTS_PY = ROOT / "plugin" / "skills" / "monitor" / "facts.py"

spec = importlib.util.spec_from_file_location("agk_monitor_facts", FACTS_PY)
facts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(facts)


def comment(body, at, assoc="OWNER"):
    return {"body": body, "createdAt": at, "authorAssociation": assoc}


def receipt(role, n, at, agent=None, kind="attempt"):
    agent = agent or {"engineer": "software-engineer", "qa": "qa-engineer"}.get(role, role)
    return comment(f"## Launch: {role} ({kind} {n})\nAgent: {agent}\nCall: abc", at)


class Rig:
    """A temp state dir, a fake `gh` on PATH and a fixture file the fake reads."""

    def __init__(self, tmp, monkeypatch):
        self.state = tmp / "state"
        self.state.mkdir()
        self.repo = tmp / "repo"
        self.repo.mkdir()
        self.fixture = tmp / "fixture.json"
        self.log = tmp / "gh.log"
        self.fail = tmp / "gh.fail"
        self.fx = json.loads((FAKES / "stage.json").read_text())
        monkeypatch.setenv("PATH", f"{FAKES}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_GH_FIXTURE", str(self.fixture))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))
        monkeypatch.setenv("FAKE_GH_FAIL", str(self.fail))
        (self.state / "monitor-projects.json").write_text(
            json.dumps([{"project": "own/demo", "repo": str(self.repo)}]))
        self.comments({})

    def comments(self, by_issue):
        self.fx["comments"] = dict(by_issue)
        self.fixture.write_text(json.dumps(self.fx))

    def read(self):
        return facts.read_facts(self.state)

    def marker(self):
        (m,) = self.read()["markers"]
        return m

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


def parse(text):
    """A strict mini parser of the Prometheus text format: {(name, labels tuple): value}."""
    out = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r'([a-z_]+)(?:\{((?:[a-z_]+="(?:[^"\\\n]|\\.)*",?)*)\})? (\S+)', line)
        assert m, f"invalid line: {line!r}"
        labels = tuple(re.findall(r'([a-z_]+)="((?:[^"\\\n]|\\.)*)"', m.group(2) or ""))
        float(m.group(3))
        out[(m.group(1), labels)] = m.group(3)
    return out


def test_marker_is_newest_receipt(rig):
    rig.comments({"10": [receipt("pm", 1, "2026-01-01T10:00:00Z"), receipt("engineer", 1, "2026-01-01T11:00:00Z")]})
    assert rig.marker() == {"agk_project": "own/demo", "stage": "5", "issue": "10", "role": "engineer",
                            "launch": "engineer-1"}


def test_marker_return_attempt(rig):
    rig.comments({"10": [receipt("engineer", 1, "2026-01-01T11:00:00Z"),
                         receipt("engineer", 2, "2026-01-01T12:00:00Z")]})
    m = rig.marker()
    assert (m["issue"], m["role"], m["launch"]) == ("10", "engineer", "engineer-2")


def test_marker_continued_round_counts(rig):
    rig.comments({"10": [receipt("engineer", 3, "2026-01-01T11:00:00Z", kind="continued, round")]})
    assert rig.marker()["launch"] == "engineer-3"


def test_marker_stage_level_after_close(rig):
    rig.comments({"12": [receipt("qa", 1, "2026-01-01T11:00:00Z")]})
    m = rig.marker()
    assert (m["stage"], m["issue"], m["role"], m["launch"]) == ("5", "", "orchestrator", "")
    # a newer receipt on an open issue wins again
    rig.comments({"12": [receipt("qa", 1, "2026-01-01T11:00:00Z")], "11": [receipt("pm", 1, "2026-01-01T12:00:00Z")]})
    assert (rig.marker()["issue"], rig.marker()["role"]) == ("11", "pm")


def test_marker_planner_on_stage_issue(rig):
    rig.comments({"10": [receipt("engineer", 1, "2026-01-01T11:00:00Z")],
                  "5": [receipt("planner", 1, "2026-01-01T12:00:00Z")]})
    m = rig.marker()
    assert (m["stage"], m["issue"], m["role"], m["launch"]) == ("5", "", "planner", "planner-1")


def test_marker_qa_roles(rig):
    rig.comments({"10": [receipt("qa", 1, "2026-01-01T11:00:00Z", agent="qa-engineer")]})
    assert rig.marker()["role"] == "qa-claude"
    rig.comments({"10": [receipt("qa", 1, "2026-01-01T11:00:00Z", agent="qa-codex")]})
    assert rig.marker()["role"] == "qa-codex"
    assert rig.marker()["launch"] == "qa-1"


def test_marker_skips_not_started(rig):
    rig.comments({"10": [receipt("pm", 1, "2026-01-01T10:00:00Z"),
                         receipt("engineer", 1, "2026-01-01T11:00:00Z"),
                         comment("## Launch not started: engineer (attempt 1)\nreason", "2026-01-01T11:01:00Z")]})
    assert (rig.marker()["role"], rig.marker()["launch"]) == ("pm", "pm-1")
    # a not-started comment of another attempt does not skip it
    rig.comments({"10": [receipt("engineer", 2, "2026-01-01T11:00:00Z"),
                         comment("## Launch not started: engineer (attempt 1)", "2026-01-01T11:01:00Z")]})
    assert rig.marker()["launch"] == "engineer-2"


def test_marker_no_receipt(rig):
    m = rig.marker()
    assert (m["stage"], m["issue"], m["role"], m["launch"]) == ("5", "", "orchestrator", "")


def test_marker_ignores_comments_of_others(rig):
    rig.comments({"10": [comment("## Launch: engineer (attempt 1)\nAgent: x", "2026-01-01T11:00:00Z", "NONE")]})
    assert rig.marker()["role"] == "orchestrator"


def test_no_open_stage_gives_no_marker(rig):
    rig.fx["stages"] = []
    rig.comments({})
    assert rig.read() == {"issues": [], "markers": [], "limits": {}}


def test_issue_info_order(rig):
    issues = rig.read()["issues"]
    assert [(i["order"], i["issue"], i["title"], i["stage"]) for i in issues] == [
        ("1", "10", "First task", "5"), ("2", "11", "Second task", "5"), ("3", "12", "Third task", "5")]
    series = parse(facts.render(rig.read(), 1.0))
    assert ("agk_issue_info", (("agk_project", "own/demo"), ("stage", "5"), ("issue", "11"),
                               ("title", "Second task"), ("order", "2"))) in series


def test_gh_failure_keeps_last_facts(rig, capsys):
    f = facts.Facts(rig.state)
    assert f.refresh() is True
    before = f.body()
    assert "First task" in before
    rig.fail.write_text("x")
    assert f.refresh() is False
    assert f.body() == before
    err = capsys.readouterr().err
    assert "read failed" in err and "gh" in err
    rig.fail.unlink()
    assert f.refresh() is True


def test_gh_calls_read_only(rig):
    rig.comments({"10": [receipt("engineer", 1, "2026-01-01T11:00:00Z")]})
    rig.read()
    calls = rig.calls()
    assert calls
    for call in calls:
        args = call["args"]
        assert args[:2] in (["issue", "list"], ["issue", "view"]) or args[:1] == ["api"], args
        assert not {"-X", "--method", "-f", "-F"} & set(args), args
        assert call["cwd"] == str(rig.repo)


def test_usage_limits_bad_lines_skipped(tmp_path):
    (tmp_path / "usage-limits-claude.jsonl").write_text("\n".join([
        json.dumps({"v": 1, "provider": "claude", "window": "5h", "used_percent": 10}),
        json.dumps({"v": 1, "provider": "claude", "window": "5h", "used_percent": 42.5}),
        json.dumps({"v": 2, "provider": "claude", "window": "7d", "used_percent": 1}),
        json.dumps({"v": 1, "provider": "claude", "window": "7d", "used_percent": "50"}),
        json.dumps({"v": 1, "provider": "", "window": "7d", "used_percent": 5}),
        json.dumps({"v": 1, "provider": "claude", "window": "", "used_percent": 5}),
        json.dumps({"v": 1, "provider": "claude", "window": "7d", "used_percent": True}),
        "not json", "[1]",
    ]) + "\n")
    (tmp_path / "usage-limits-codex.jsonl").write_text(
        json.dumps({"v": 1, "provider": "codex", "window": "weekly", "used_percent": 7}) + "\n")
    assert facts.read_usage_limits(tmp_path) == {("claude", "5h"): 42.5, ("codex", "weekly"): 7.0}
    assert facts.read_usage_limits(tmp_path / "missing") == {}


def test_render_escapes_labels():
    data = {"issues": [{"agk_project": "o/p", "stage": "1", "issue": "2", "title": 'say "hi" \\ now\nnext',
                        "order": "1"}], "markers": [], "limits": {("claude", "5h"): 3.0}}
    text = facts.render(data, 1700000000.5)
    assert 'title="say \\"hi\\" \\\\ now\\nnext"' in text
    series = parse(text)
    assert ("agk_usage_limit_percent", (("provider", "claude"), ("window", "5h"))) in series
    assert series[("agk_facts_last_success_seconds", ())] == "1700000000.5"


def test_listens_on_localhost_only(rig):
    f = facts.Facts(rig.state)
    f.refresh()
    server = facts.make_server(f, 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=10) as resp:
            body = resp.read().decode()
            assert resp.headers["Content-Type"].startswith("text/plain")
        assert "agk_issue_info{" in body and "agk_facts_last_success_seconds" in body
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other", timeout=10)
    finally:
        server.shutdown()
        server.server_close()


def test_a_bad_projects_file_keeps_the_server_alive(rig, capsys):
    (rig.state / "monitor-projects.json").write_text("{not json")
    f = facts.Facts(rig.state)
    assert f.refresh() is False
    assert "read failed" in capsys.readouterr().err


def test_facts_py_does_not_write():
    text = FACTS_PY.read_text(encoding="utf-8")
    for word in ("write_text", "write_bytes", "os.remove", "unlink", '"-X"', "--method"):
        assert word not in text, word
    assert "open(" not in text
