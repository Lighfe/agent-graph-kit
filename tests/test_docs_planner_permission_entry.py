from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ROOT / "docs/team/planner.md",
    ROOT / "plugin/templates/docs/team/planner.md",
]
PHRASES = [
    "Is this entry added?",
    "Auto mode",
    "/permissions",
    "$defaults",
    "Auto mode allow entries",
    "temporary",
]


def test_planner_permission_entry_phrases():
    for f in FILES:
        text = f.read_text()
        for p in PHRASES:
            assert p in text, f"{p!r} missing in {f}"


def test_planner_has_no_set_on_stage_confirmation():
    old = "only when the owner says in the session that it is set"
    for f in FILES:
        assert old not in f.read_text()


def test_planner_copy_identical():
    assert FILES[0].read_text() == FILES[1].read_text()
