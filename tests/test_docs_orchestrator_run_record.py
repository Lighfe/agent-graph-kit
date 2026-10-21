"""The orchestrator writes the run record at stage end (issue #246): after the release, before the planner."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs/team/orchestrator.md").read_text()
STAGE_END = DOC.split("### Stage end")[1].split("\n### ")[0].split("\n#### ")[0]
README = (ROOT / "README.md").read_text()
SPEC = (ROOT / "docs/specs/agent-graph-kit.md").read_text()


def test_step_order_release_then_record_then_planner():
    release = STAGE_END.index("Release the plugin")
    record = STAGE_END.index("run_record.py")
    planner = STAGE_END.index("Launch the agent `planner`")
    assert release < record < planner


def test_step_names_options_and_failure_rule():
    step = STAGE_END[STAGE_END.index("Write the run record"):STAGE_END.index("Launch the agent `planner`")]
    assert "run_record.py> write" in step or "run_record.py write" in step
    for opt in ["--project", "--stage", "--issues", "--transcripts", "--codex-usage", "--orchestrator-transcript"]:
        assert opt in step
    assert "--json number,comments,closedAt,labels" in step
    assert "go on" in step


def test_readme_section_and_entry():
    sec = README.split("## Run record")[1].split("\n## ")[0]
    for k in ["RUN_RECORD_FILE", "incomplete by design", "estimate", "run_record.py> limit", "--record", "/permissions", "$defaults"]:
        assert k in sec


def test_readme_entry_matches_orchestrator_command():
    sec = README.split("## Run record")[1].split("\n## ")[0]
    cmd = [l.strip() for l in DOC.splitlines() if l.strip().startswith("uv run --script <run_record.py> write")][0]
    assert cmd in sec


def test_spec_section():
    sec = SPEC.split("## Run record")[1].split("\n## ")[0]
    for k in ["`id`", "orchestrator", "estimate", "run-weights.json", "run-record-limits.jsonl"]:
        assert k in sec
