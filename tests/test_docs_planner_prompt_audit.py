"""Fact tests for the prompt audit in the planner file (issue #205).

Both copies of the planner file must carry the output-file and "known" rules.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "docs" / "team" / "planner.md",
    ROOT / "plugin" / "templates" / "docs" / "team" / "planner.md",
]


def audit(path):
    text = path.read_text(encoding="utf-8")
    return text.split("Prompt audit:\n", 1)[1].split("Denied calls:", 1)[0]


def test_audit_output_goes_to_a_file_and_is_read_whole():
    for path in COPIES:
        text = audit(path)
        assert "Write the output of each run to its own file" in text, path
        assert "`/tmp`" in text and "stage number" in text, path
        assert "read the whole file before the review lists findings" in text, path


def test_audit_marks_known_findings():
    for path in COPIES:
        text = audit(path)
        assert 'listed as "known"' in text, path
        assert "earlier stage review or an open issue" in text, path
        assert "named, not as new" in text, path
