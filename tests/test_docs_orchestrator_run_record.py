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


# Issue #258: the run-record step and the SendMessage rule are true in a plugin project too.
COPIES = [ROOT / "docs/team/orchestrator.md", ROOT / "plugin/templates/docs/team/orchestrator.md"]


def _record_step(text):
    stage_end = text.split("### Stage end")[1].split("\n### ")[0].split("\n#### ")[0]
    return stage_end[stage_end.index("Write the run record"):stage_end.index("Launch the agent `planner`")]


def _send_message_paragraph(text):
    return [p for p in text.split("\n\n") if "SendMessage" in p and "QA: FAIL" in p][0]


def test_record_step_names_both_sources_of_the_auto_mode_entry():
    for path in COPIES:
        step = _record_step(path.read_text())
        assert "the Auto mode entry in the README allows" not in step, path
        assert "/agk:setup" in step and "README" in step and "kit repo" in step, path


def test_record_step_names_the_skill_folder_not_a_kit_path_as_this_repo():
    for path in COPIES:
        text = path.read_text()
        step = _record_step(text)
        assert "in this repo `plugin/skills/run-record/run_record.py`" not in text, path
        assert "`run-record` skill folder of the plugin" in step, path
        for i in [m for m in range(len(text)) if text.startswith("plugin/skills/run-record/run_record.py", m)]:
            assert "kit repo" in text[max(0, i - 80):i], path


def test_send_message_paragraph_has_no_fixed_cache_lifetime():
    for path in COPIES:
        para = _send_message_paragraph(path.read_text())
        assert "5 min" not in para and "1 h" not in para, path
        assert "launch a fresh engineer" in para, path
        assert "usually outlasts the prompt cache" in para, path
        assert "writes its whole old context again" in para, path
