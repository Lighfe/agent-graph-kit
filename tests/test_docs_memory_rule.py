"""Fact tests for the memory rule of the engineer (issue #223).

They read the role files in docs/team/ and check the rule lines. No subprocess runs.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAM = ROOT / "docs" / "team"


def read(name):
    return (TEAM / name).read_text(encoding="utf-8")


def rule():
    text = read("software-engineer.md")
    assert "## Memory-heavy jobs" in text
    return text.split("## Memory-heavy jobs", 1)[1].split("\n## ", 1)[0]


def test_engineer_cap_rule():
    r = rule()
    assert "systemd-run --user --scope -p MemoryMax=<cap> -p MemorySwapMax=0 <command>" in r
    assert "more than one minute" in r
    assert "never run such a job uncapped" in r.lower()
    assert "just once" in r
    assert "do not raise the cap" in r.lower()
    assert "at most 4 workers" in r


def test_engineer_peak_measurement():
    r = rule()
    assert "/usr/bin/time -v" in r
    assert "Maximum resident set size" in r
    assert "command line, the exit code and the peak" in r


def test_engineer_fallback_without_tool():
    r = rule()
    assert "smaller version first" in r
    assert "Check the premise" in r


def test_engineer_owner_effort():
    assert "install nothing" in rule().lower()
    assert "systemd" in rule()


def test_qa_line():
    qa = read("qa-engineer.md")
    assert "no systemd bus" in qa
    assert "never a heavy job uncapped" in qa


def test_orchestrator_hint():
    o = read("orchestrator.md")
    assert "out of memory" in o
    assert "memory cap" in o.split("out of memory", 1)[1][:400]
