"""Fact tests for the QA role file: one test-run rule, qa-codex pre-step evidence, headless
browser check (issue #260).

They read the repo copy and the plugin copy of docs/team/qa-engineer.md. No subprocess runs.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATHS = [ROOT / "docs/team/qa-engineer.md", ROOT / "plugin/templates/docs/team/qa-engineer.md"]


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def section(text, start, end):
    assert start in text, start
    return text.split(start, 1)[1].split(end, 1)[0]


def test_copies_are_identical():
    assert QA_PATHS[0].read_text(encoding="utf-8") == QA_PATHS[1].read_text(encoding="utf-8")


def test_one_test_run_rule_with_memory_cap_pointer():
    for path in QA_PATHS:
        text = flat(path)
        assert text.count("Test run.") == 1, path
        rule = section(text, "Test run.", "Pre-step evidence.")
        assert "full test command of `AGENTS.md`" in rule
        assert "only under a memory cap" in rule
        assert '"Memory-heavy jobs" in `docs/team/software-engineer.md`' in rule
        assert "Without a cap tool" in rule and "no systemd bus" in rule
        assert "the fast subset that `AGENTS.md` names" in rule
        assert "when it names none, only the test files that cover the changed criteria" in rule
        assert "The `Tests:` line names what ran" in rule
        assert "Tests: not run (no test suite)" in rule


def test_old_test_run_wording_is_gone():
    for path in QA_PATHS:
        text = flat(path)
        assert "Run the test command in AGENTS.md as secondary evidence" not in text, path
        assert "run only small checks of your own" not in text, path
        assert "`<test command from AGENTS.md>`" not in text, path


def test_pre_step_evidence():
    for path in QA_PATHS:
        rule = section(flat(path), "Pre-step evidence.", "Do not install anything.")
        assert "only when `scripts/qa-codex` runs you and the project has a `frontend/` submodule" in rule
        assert "`git submodule update --init -- frontend`" in rule
        assert "`npm ci`" in rule and "`bun install --frozen-lockfile`" in rule
        assert "`npx --no playwright install chromium`" in rule
        assert "`bun x --no-install playwright install chromium`" in rule
        assert "`## QA: UNAVAILABLE`" in rule
        assert "each of these steps exited 0" in rule
        assert "do not run them again" in rule
        assert "do not mark the criterion invalid for them" in rule
        assert "The fallback `qa-engineer` gets no pre-step" in rule


def test_headless_browser_check():
    for path in QA_PATHS:
        rule = section(path.read_text(encoding="utf-8"), "Browser check.", "Your output is a verdict")
        f = re.sub(r"\s+", " ", rule)
        assert "If your tool list has a browser tool, start the app" in f
        assert "local binding on `localhost` and `127.0.0.1`" in f
        assert "in one command" in f
        assert "from `AGENTS.md`; when `AGENTS.md` names none, from the newest `## Engineer: DONE`" in f
        assert "`--host 127.0.0.1`" in f
        assert "default host `::`" in f and "exits 1" in f
        assert "Wait until each process answers" in f
        assert "imports Playwright from `frontend/node_modules`" in f
        assert "also when the script fails" in f
        assert "under `/tmp`" in f
        assert "UNVERIFIABLE" in f and "quote the error" in f
        # no project-specific command
        assert "quack-rl" not in f and "bun run dev" not in f
        # the old line contradicted the headless check
        assert "do not repeat a browser check" not in f.lower()
