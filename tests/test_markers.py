"""The pytest marker `integration` (issue #328).

Rule: a test that starts a subprocess during its run (directly, through a helper or through a fixture),
for example a hook, a skill script, git, a fake gh or docker, carries `@pytest.mark.integration`.
A test that runs fully in-process, or only reads a file, stays unmarked."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.integration


def test_integration_marker_is_registered_and_selects_tests():
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "integration",
         "-W", "error::pytest.PytestUnknownMarkWarning"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out[-2000:]
    assert "PytestUnknownMarkWarning" not in out
    m = re.search(r"^(\d+)(?:/\d+)? tests? (?:collected|selected)", res.stdout, flags=re.M)
    assert m, res.stdout[-2000:]
    assert int(m.group(1)) >= 20
