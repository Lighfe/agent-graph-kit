"""Tests for .agents/skills/codex-review (review.py and review.schema.json).

Every call of `main` runs with a fake `run_codex` and a reviews folder in `tmp_path`. No test starts
the real `codex`, writes into the real `docs/reviews/` or uses the network. All data is synthetic.
"""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import codex_exec
from codex_exec import CodexRun

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "codex-review"
SCRIPT = SKILL_DIR / "review.py"
SCHEMA = SKILL_DIR / "review.schema.json"


def _load():
    spec = importlib.util.spec_from_file_location("codex_review", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


review = _load()

DATA = {"verdict": "needs-attention", "summary": "One gap.",
        "findings": [{"severity": "high", "title": "Missing deny", "body": "Crash allows call.",
                      "file": "guard.py", "line_start": 10, "line_end": 12, "confidence": 0.8,
                      "recommendation": "Catch BaseException."}],
        "next_steps": ["Add test"]}
EXPECTED = textwrap.dedent("""\
    # Codex review: demo

    - Date: 2026-01-01
    - Target: docs/x.md
    - Verdict: needs-attention

    ## Summary

    One gap.

    ## Findings

    ### 1. [high] Missing deny

    - File: guard.py:10-12
    - Confidence: 0.8

    Crash allows call.

    Recommendation: Catch BaseException.

    Decision: open

    ## Next steps

    - Add test
    """)

DATE = "2026-01-01"


def _finding(**kw):
    return {**DATA["findings"][0], **kw}


# --- rendering ---------------------------------------------------------------------------


def test_render_matches_expected():
    out = review.render_review(DATA, topic="demo", target="docs/x.md", date=DATE)
    assert out == EXPECTED
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_render_single_line():
    data = {**DATA, "findings": [_finding(line_start=10, line_end=10)]}
    out = review.render_review(data, topic="demo", target="docs/x.md", date=DATE)
    assert "- File: guard.py:10\n" in out
    assert "guard.py:10-10" not in out


def test_render_empty_findings_and_next_steps():
    data = {**DATA, "findings": [], "next_steps": []}
    out = review.render_review(data, topic="demo", target="docs/x.md", date=DATE)
    assert "## Findings\n\nNo findings.\n\n## Next steps\n\nNone.\n" in out
    assert out.endswith("None.\n")
    assert "Decision:" not in out


def test_render_several_findings_numbered_in_order():
    data = {**DATA, "findings": [_finding(title="First"), _finding(title="Second", severity="low"),
                                 _finding(title="Third", severity="critical")]}
    out = review.render_review(data, topic="demo", target="docs/x.md", date=DATE)
    heads = [line for line in out.splitlines() if line.startswith("### ")]
    assert heads == ["### 1. [high] First", "### 2. [low] Second", "### 3. [critical] Third"]
    assert out.count("Decision: open") == 3
    # each finding has its own decision line before the next heading
    for block in out.split("### ")[1:]:
        assert block.count("Decision: open") == 1


# --- schema ------------------------------------------------------------------------------


def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _objects(value)


def test_schema_shape():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["description"] == "Adapted from the review schema of the openai-codex plugin for Claude Code."
    objects = list(_objects(schema))
    assert len(objects) == 2  # top level and finding
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])
    props = schema["properties"]
    assert set(props) == {"verdict", "summary", "findings", "next_steps"}
    assert props["verdict"]["enum"] == ["approve", "needs-attention"]
    assert props["summary"]["type"] == "string"
    assert props["findings"]["type"] == "array"
    assert props["next_steps"] == {"type": "array", "items": {"type": "string"}}
    finding = props["findings"]["items"]
    assert finding["type"] == "object"
    fp = finding["properties"]
    assert set(fp) == {"severity", "title", "body", "file", "line_start", "line_end", "confidence",
                       "recommendation"}
    assert fp["severity"]["enum"] == ["critical", "high", "medium", "low"]
    for key in ("title", "body", "file", "recommendation"):
        assert fp[key]["type"] == "string"
    assert fp["line_start"]["type"] == "integer" and fp["line_end"]["type"] == "integer"
    assert fp["confidence"]["type"] == "number"


# --- main --------------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Reviews folder in tmp_path, and a run_codex that fails the test unless a test replaces it."""
    reviews = tmp_path / "reviews"
    monkeypatch.setattr(review, "REVIEWS_DIR", reviews)

    def forbidden(*a, **kw):
        raise AssertionError("run_codex must not be called")

    monkeypatch.setattr(review.codex_exec, "run_codex", forbidden)
    return reviews


def _fake(monkeypatch, result, calls=None):
    def fake(prompt, **kw):
        if calls is not None:
            calls.append((prompt, kw))
        return result

    monkeypatch.setattr(review.codex_exec, "run_codex", fake)


def _main(*argv):
    return review.main(list(argv), today=DATE)


def test_run_codex_arguments_and_prompt(env, monkeypatch, capsys):
    calls = []
    _fake(monkeypatch, CodexRun("ok", DATA, ""), calls)
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 0
    (prompt, kw), = calls
    assert kw == {"schema": SCHEMA, "sandbox_args": ["-s", "read-only"], "model": "gpt-6-astra",
                  "effort": "medium", "timeout_s": 1800, "cwd": ROOT}
    assert "Review AGENTS.md for correctness, gaps and risks." in prompt
    assert "git diff <range>" in prompt
    assert "Do not quote secrets (keys, tokens, passwords)" in prompt
    assert "adversarial" not in prompt.lower()


def test_model_matches_qa_codex():
    text = (ROOT / "scripts" / "qa-codex").read_text(encoding="utf-8")
    assert f'QA_MODEL = "{review.MODEL}"' in text


def test_success_writes_file_and_prints_path(env, monkeypatch, capsys):
    _fake(monkeypatch, CodexRun("ok", DATA, ""))
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 0
    path = env / f"{DATE}-demo-codex-review.md"
    out = capsys.readouterr().out
    assert out == f"{path}\n"
    assert path.read_text(encoding="utf-8") == review.render_review(
        DATA, topic="demo", target="AGENTS.md", date=DATE)


def test_default_reviews_dir_and_date():
    assert review.REVIEWS_DIR == ROOT / "docs" / "reviews"
    assert review.ROOT == ROOT


def test_date_defaults_to_local_today(env, monkeypatch, capsys):
    _fake(monkeypatch, CodexRun("ok", DATA, ""))
    import datetime
    assert review.main(["--target", "AGENTS.md", "--topic", "demo"]) == 0
    assert (env / f"{datetime.date.today().isoformat()}-demo-codex-review.md").exists()


def test_commit_range_target(env, monkeypatch, capsys):
    calls = []
    _fake(monkeypatch, CodexRun("ok", DATA, ""), calls)
    assert _main("--target", "HEAD..HEAD", "--topic", "demo") == 0
    assert "Review HEAD..HEAD for" in calls[0][0]


@pytest.mark.parametrize("status", ["transient", "timeout", "invalid_output", "unavailable", "unknown"])
def test_failure_writes_no_file(env, monkeypatch, capsys, status):
    _fake(monkeypatch, CodexRun(status, None, "no result after 30 min"))
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 1
    err = capsys.readouterr()
    assert err.err == f"codex-review: {status}: no result after 30 min\n"
    assert err.out == ""
    assert not env.exists() or not any(env.iterdir())


def test_timeout_message(env, monkeypatch, capsys):
    _fake(monkeypatch, CodexRun("timeout", None, "no result after 30 min"))
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 1
    assert "codex-review: timeout: no result after 30 min" in capsys.readouterr().err
    assert not (env / f"{DATE}-demo-codex-review.md").exists()


@pytest.mark.parametrize("output, needle", [
    ({k: v for k, v in DATA.items() if k != "summary"}, "summary"),
    ({**DATA, "findings": [_finding(severity="blocker")]}, "severity"),
    ({**DATA, "extra": 1}, "extra"),
    ({**DATA, "verdict": "maybe"}, "verdict"),
    ({**DATA, "findings": [_finding(line_start="10")]}, "line_start"),
    ({**DATA, "findings": [_finding(confidence=True)]}, "confidence"),
    ({**DATA, "next_steps": [1]}, "next_steps"),
    ({**DATA, "findings": ["x"]}, "findings"),
])
def test_invalid_shape_writes_no_file(env, monkeypatch, capsys, output, needle):
    _fake(monkeypatch, CodexRun("ok", output, ""))
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("codex-review: invalid_output: ")
    assert needle in captured.err
    assert not (env / f"{DATE}-demo-codex-review.md").exists()


def test_validate_accepts_data():
    assert review.validate(DATA) == []
    assert review.validate({**DATA, "findings": [_finding(confidence=1)]}) == []


@pytest.mark.parametrize("topic", ["../x", "My Topic", "", "a--b", "-a", "a-", "a/b", "A"])
def test_bad_topic_exits_2(env, capsys, topic):
    assert _main("--target", "AGENTS.md", "--topic", topic) == 2
    err = capsys.readouterr().err
    assert "usage:" in err
    assert not env.exists()


def test_good_topics():
    for topic in ("demo", "tasks-4-5-6", "a1"):
        assert review.TOPIC_RE.fullmatch(topic)


def test_missing_args_exit_2(env, capsys):
    assert _main("--topic", "demo") == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("target", ["no/such/file.md", "nosuchref..HEAD", "--all", ".."])
def test_bad_target_exits_2(env, capsys, target):
    assert _main(f"--target={target}", "--topic", "demo") == 2
    err = capsys.readouterr().err
    assert "codex-review:" in err and target in err
    assert not env.exists()


def test_existing_file_is_not_overwritten(env, capsys):
    env.mkdir()
    path = env / f"{DATE}-demo-codex-review.md"
    path.write_text("old review\n", encoding="utf-8")
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 1
    assert str(path) in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "old review\n"


def test_redaction(env, monkeypatch, capsys):
    token = "sk-" + "A1b2C3d4" * 4  # synthetic
    data = {**DATA, "findings": [_finding(body=f"The key {token} is in the file.")]}
    _fake(monkeypatch, CodexRun("ok", data, ""))
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 0
    text = (env / f"{DATE}-demo-codex-review.md").read_text(encoding="utf-8")
    assert token not in text
    assert "The key [redacted] is in the file." in text


# --- signals -----------------------------------------------------------------------------


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_signal_kills_child_and_writes_no_file(env, monkeypatch, capsys, sig):
    children = []

    def fake(prompt, **kw):
        p = codex_exec.start(["sleep", "30"])
        children.append(p)
        os.kill(os.getpid(), sig)
        time.sleep(5)  # the handler raises Interrupted before this ends
        raise AssertionError("not interrupted")

    monkeypatch.setattr(review.codex_exec, "run_codex", fake)
    before = {s: signal.getsignal(s) for s in codex_exec.INTERRUPT_SIGNALS}
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 128 + sig
    assert children and children[0].poll() is not None  # killed and reaped
    assert not (env / f"{DATE}-demo-codex-review.md").exists()
    assert {s: signal.getsignal(s) for s in codex_exec.INTERRUPT_SIGNALS} == before
    assert "stopped by" in capsys.readouterr().err


def test_signal_during_write_removes_file(env, monkeypatch, capsys):
    _fake(monkeypatch, CodexRun("ok", DATA, ""))
    import builtins
    opened = []

    def open_then_signal(*a, **kw):
        f = builtins.open(*a, **kw)
        opened.append(a[0])
        os.kill(os.getpid(), signal.SIGTERM)  # arrives during the write (inside deferred)
        return f

    monkeypatch.setattr(review, "open", open_then_signal, raising=False)
    assert _main("--target", "AGENTS.md", "--topic", "demo") == 128 + signal.SIGTERM
    assert opened  # the file was created, then removed
    assert not (env / f"{DATE}-demo-codex-review.md").exists()
    assert capsys.readouterr().out == ""


# --- as a script -------------------------------------------------------------------------


def test_script_bad_topic_from_other_cwd(tmp_path):
    p = subprocess.run([sys.executable, str(SCRIPT), "--target", "AGENTS.md", "--topic", "My Topic"],
                       cwd=tmp_path, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert p.returncode == 2
    assert "usage:" in p.stderr
    assert p.stdout == ""


def test_script_header():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env -S uv run --script\n# /// script\n")
    assert "# dependencies = []" in text


# --- prose -------------------------------------------------------------------------------


def test_skill_md():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    assert "\nname: codex-review\n" in front
    assert "/codex-review" in front
    for needle in ("review.py", "one target", "Decision: open", "Decision: taken - <reason>",
                   "Decision: partly taken - <reason>", "Decision: rejected - <reason>",
                   "/codex:adversarial-review", "commit"):
        assert needle in text, needle


def test_agents_md_line():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    section = text.split("## Skills and subagents")[1].split("\n## ")[0]
    assert "When the owner asks for a Codex review, use the `codex-review` skill." in section
