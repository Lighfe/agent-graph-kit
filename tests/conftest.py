import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".claude" / "hooks"), str(ROOT / "scripts"), str(ROOT / "tests")]


@pytest.fixture(autouse=True)
def _steps_file(tmp_path_factory, monkeypatch):
    """No test writes step rows to the real state dir (issue #263)."""
    monkeypatch.setenv("STEPS_FILE", str(tmp_path_factory.mktemp("steps") / "steps.jsonl"))
