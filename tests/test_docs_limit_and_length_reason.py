import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH = ["docs/team/orchestrator.md", "plugin/templates/docs/team/orchestrator.md"]
PROC = ["docs/process.md", "plugin/templates/docs/process.md"]
REASON = "`--jq` runs once for each page, so the count would be one number for each page"


def test_orchestrator_stage_list_calls_pass_limit():
    for rel in ORCH:
        text = (ROOT / rel).read_text()
        calls = [l for l in text.splitlines() if l.startswith("gh issue list --state open --label stage")]
        assert len(calls) == 2, rel
        for call in calls:
            assert "--limit 500" in call, (rel, call)


def test_length_rule_gives_reason():
    for rel in ORCH + PROC:
        text = (ROOT / rel).read_text()
        assert re.search(r"never count them with `--jq 'length'` on a paginated call\. " + re.escape(REASON), text), rel
