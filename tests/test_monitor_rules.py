"""Tests for the recording rules of the monitor skill (issue #312): `otel/rules/agk.yml` and `agk_test.yaml`.

No test needs Docker. The rules are checked by `promtool test rules` in the pinned Prometheus image
(see the header of `agk_test.yaml`); these tests only read the two files as text."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "plugin" / "skills" / "monitor" / "otel" / "rules"
NAMES = ["agk:tokens:1m", "agk:active_seconds:1m"]


def _record_names():
    return re.findall(r"^\s*-\s*record:\s*(\S+)\s*$", (RULES / "agk.yml").read_text(), flags=re.M)


def test_rule_names():
    assert _record_names() == NAMES


def test_rule_group_interval():
    assert re.search(r"^\s*interval:\s*60s\s*$", (RULES / "agk.yml").read_text(), flags=re.M)


def test_rules_have_promtool_tests():
    text = (RULES / "agk_test.yaml").read_text()
    # the expected output of a case: an exp_samples entry whose labels start with the rule name
    for name in NAMES:
        assert re.search(r"^\s*(?:-\s*)?labels:\s*'" + re.escape(name) + r"\{", text, flags=re.M), name


def test_test_file_is_not_a_rule_file():
    assert not list(RULES.glob("*_test.yml"))
    assert (RULES / "agk_test.yaml").is_file()
