"""Fact tests for the README overview picture (issue #331). They read files only: no render, no network."""

import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = ROOT / "docs" / "assets" / "overview"
PNG = ROOT / "docs" / "assets" / "agk-overview.png"
SOURCES = [OVERVIEW / "overview.svg", OVERVIEW / "overview.html"]

# The quoted label strings of the content list in the issue.
LABELS = [
    "You",
    "one stage",
    "/stage-start",
    "Planner",
    "stage ready, /goal",
    "Orchestrator",
    "stage review",
    "one issue",
    "GitHub Issues: every handoff is a comment",
    "PM",
    "Software engineer",
    "QA engineer",
    "FAIL",
    "PASS",
    "launch",
    "hooks check every handoff",
    "Monitoring",
    "Release",
]

# Every tool of the content list shows as a logo file or as a text badge.
TOOLS = ["Claude", "OpenAI", "Lovable", "GitHub", "GitHub Actions", "OpenTelemetry",
         "Prometheus", "Grafana", "Loki", "Docker", "superpowers"]


def source_path():
    found = [p for p in SOURCES if p.is_file()]
    assert len(found) == 1, f"expected exactly one source file, found {found}"
    return found[0]


def source_text():
    return source_path().read_text(encoding="utf-8")


def licenses_text():
    return (OVERVIEW / "LICENSES.md").read_text(encoding="utf-8")


def text_badges():
    part = licenses_text().split("\n## Text badges\n")[1].split("\n## ")[0]
    return [l[2:].split(":")[0].strip() for l in part.splitlines() if l.startswith("- ")]


def png_size():
    head = PNG.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR"
    return struct.unpack(">II", head[16:24])


def test_the_source_exists_and_starts_with_the_render_command():
    first_lines = "\n".join(source_text().splitlines()[:12])
    assert "<!--" in first_lines
    assert "docs/assets/agk-overview.png" in first_lines
    assert f"docs/assets/overview/{source_path().name}" in first_lines


@pytest.mark.parametrize("label", LABELS)
def test_the_source_holds_each_label_as_one_string(label):
    assert label in source_text()


def test_the_font_comes_from_the_font_file_and_not_from_the_web():
    text = source_text()
    assert "fonts/Kalam-Regular.ttf" in text
    assert (OVERVIEW / "fonts" / "Kalam-Regular.ttf").is_file()
    for remote in ["http://", "https://"]:
        assert remote not in text.replace("http://www.w3.org/", ""), remote


def test_the_source_uses_only_logo_files_from_the_logos_folder():
    text = source_text()
    names = sorted(p.name for p in (OVERVIEW / "logos").iterdir())
    assert names
    for name in names:
        assert f"logos/{name}" in text, f"{name} is not used in the picture"


def test_licenses_names_every_logo_and_font_file():
    text = licenses_text()
    files = [p for d in ("logos", "fonts") for p in sorted((OVERVIEW / d).iterdir())]
    assert len(files) >= 2
    for p in files:
        entries = [l for l in text.splitlines() if l.startswith("|") and f"`{p.parent.name}/{p.name}`" in l]
        assert len(entries) == 1, f"{p.name}: {len(entries)} entries"
        assert "https://" in entries[0], f"{p.name}: no source URL"


def test_each_tool_has_a_logo_entry_or_a_text_badge():
    text = licenses_text()
    logo_rows = [l for l in text.splitlines() if l.startswith("|") and "`logos/" in l]
    badges = text_badges()
    assert badges
    for tool in TOOLS:
        in_logos = any(l.split("|")[2].strip() == tool for l in logo_rows)
        assert in_logos != (tool in badges), f"{tool}: logo entry {in_logos}, text badge {tool in badges}"
    for badge in badges:
        assert badge in source_text(), badge


def test_the_png_is_in_the_bounds_and_is_not_the_old_picture():
    width, height = png_size()
    assert 1600 <= width <= 3200
    assert PNG.stat().st_size <= 2 * 1024 * 1024
    # The old picture was 1600 x 900 and 73376 bytes.
    assert (width, height, PNG.stat().st_size) != (1600, 900, 73376)


def test_the_readme_alt_text_names_both_loops():
    line = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[2]
    assert line.startswith("![") and line.endswith("](docs/assets/agk-overview.png)")
    alt = line[2:line.index("](")]
    assert "one stage" in alt and "one issue" in alt
