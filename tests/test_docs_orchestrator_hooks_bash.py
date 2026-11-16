"""The Hooks paragraph of the orchestrator doc names the Bash settings check (G8) in its first sentence (issue #338)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _first_sentence(path):
    text = path.read_text()
    section = text.split("\n## Hooks\n", 1)[1].lstrip()
    paragraph = next(p for p in section.split("\n\n") if p.startswith("A hook checks each launch"))
    return paragraph.split(". ", 1)[0]


def test_hooks_first_sentence_names_bash_and_g8():
    sentence = _first_sentence(ROOT / "docs/team/orchestrator.md")
    assert "Bash" in sentence
    assert "G8" in sentence


def test_hooks_first_sentence_in_plugin_copy():
    sentence = _first_sentence(ROOT / "plugin/templates/docs/team/orchestrator.md")
    assert "Bash" in sentence
    assert "G8" in sentence
