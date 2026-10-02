"""Fact tests for spec citations (issue #104).

Code and README cite the living spec docs/specs/agent-graph-kit.md by heading
anchor or by guarantee ID, never by the section numbers of the archived v1
spec. These tests read files only; no test runs gh, git or another subprocess.

Anchor rule (GitHub's heading slug): the heading text lowercased, every
character that is not a letter, digit, space, `-` or `_` removed, spaces
replaced by `-`; a repeated slug gets `-1`, `-2`, ... Headings are lines that
start with one to six `#` and a space, outside fenced code blocks (lines
between ``` fences).

This file is scanned too: its patterns and synthetic examples are built so that
they do not match the checks in its own source.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "docs" / "specs" / "agent-graph-kit.md"
SPEC_NAME = "agent-graph-kit" + ".md"

# The section-number pattern of the archived v1 spec (case-insensitive).
SECTION_NUMBER = re.compile(r"(spec|section)[^a-z0-9]{0,3}[0-9]+", re.IGNORECASE)
# A citation of the living spec by anchor, with any path before the file name. An anchor
# holds only letters, digits, `-` and `_` (the slug rule), so trailing punctuation ends it.
SPEC_CITATION = re.compile(re.escape(SPEC_NAME) + r"#([\w-]+)")
# A link to an anchor in the same file.
LOCAL_LINK = re.compile(r"\]\(#([\w-]+)\)")
# A guarantee ID: G followed by digits, as a whole word.
GUARANTEE_ID = re.compile(r"\bG(\d+)\b")
# A guarantee heading of the living spec.
GUARANTEE_HEADING = re.compile(r"^### G(\d+)\b")
# A deny message that starts with a guarantee ID, in a string literal.
DENY_PREFIX = re.compile(r"[\"']G(\d+):")
HEADING = re.compile(r"^(#{1,6}) +(.*?)\s*$")

SCANNED = [".claude/hooks", "scripts", "tests", ".agents/skills", "README.md"]
CITING = [
    "README.md",
    "AGENTS.md",
    "docs",
    ".claude/agents",
    ".claude/hooks",
    "scripts",
    "tests",
    ".agents/skills",
]
CITING_EXCLUDED = ["docs/archive", "docs/reviews", "docs/references"]
HOOKS_WITH_DENIES = [".claude/hooks/guard.py", ".claude/hooks/issue_state.py"]


# --- helpers ---------------------------------------------------------------------


def read_texts(entries, excluded=()):
    """{relative path: text} for every UTF-8 file under the entries.

    Skips files that do not decode, `__pycache__` folders and excluded folders.
    """
    out = {}
    excluded_paths = [ROOT / e for e in excluded]
    for entry in entries:
        base = ROOT / entry
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in files:
            if "__pycache__" in path.parts:
                continue
            if any(path == ex or ex in path.parents for ex in excluded_paths):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            out[str(path.relative_to(ROOT))] = text
    return out


def headings(text):
    """The heading texts of a markdown text, outside fenced code blocks."""
    out = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING.match(line)
        if m:
            out.append(m.group(2).rstrip("#").strip())
    return out


def slug(heading):
    """GitHub's slug of one heading text, without the duplicate suffix."""
    s = heading.lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def anchors(text):
    """The set of heading anchors of a markdown text, with duplicate suffixes."""
    seen = {}
    out = set()
    for h in headings(text):
        base = slug(h)
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return out


def citations(text, is_spec=False):
    """The anchors a text cites in the living spec."""
    found = SPEC_CITATION.findall(text)
    if is_spec:
        found += LOCAL_LINK.findall(text)
    return found


def missing_citations(texts, spec_text, spec_key):
    """(file, anchor) for every cited anchor that the living spec does not have."""
    have = anchors(spec_text)
    return [
        (name, anchor)
        for name, text in texts.items()
        for anchor in citations(text, is_spec=(name == spec_key))
        if anchor not in have
    ]


def spec_guarantee_ids(spec_text):
    """The IDs that have a `### G<n> ...` heading in the living spec."""
    return {
        "G" + m.group(1)
        for line in _outside_fences(spec_text)
        if (m := GUARANTEE_HEADING.match(line))
    }


def _outside_fences(text):
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield line


def guarantee_ids(text):
    return {"G" + n for n in GUARANTEE_ID.findall(text)}


def unknown_guarantee_ids(texts, spec_ids):
    """(file, ID) for every guarantee ID with no heading in the living spec."""
    return sorted(
        (name, gid) for name, text in texts.items() for gid in guarantee_ids(text) if gid not in spec_ids
    )


def deny_ids(text):
    """The IDs that start a deny message in a hook source."""
    return {"G" + n for n in DENY_PREFIX.findall(text)}


def id_set_difference(spec_ids, hook_ids):
    """(only in spec, only in hooks); both empty when the sets are equal."""
    return sorted(spec_ids - hook_ids), sorted(hook_ids - spec_ids)


def section_number_hits(texts):
    """(file, line number, line) for every line that cites a section number."""
    return [
        (name, i, line)
        for name, text in texts.items()
        for i, line in enumerate(text.splitlines(), 1)
        if SECTION_NUMBER.search(line)
    ]


def spec_text():
    return SPEC_PATH.read_text(encoding="utf-8")


# --- the repo ----------------------------------------------------------------------


def test_no_section_number_citations():
    hits = section_number_hits(read_texts(SCANNED))
    assert hits == [], "\n".join(f"{n}:{i}: {line}" for n, i, line in hits)


def test_every_spec_anchor_citation_has_a_heading():
    texts = read_texts(CITING, CITING_EXCLUDED)
    spec_key = str(SPEC_PATH.relative_to(ROOT))
    assert spec_key in texts
    assert missing_citations(texts, texts[spec_key], spec_key) == []


def test_spec_anchor_citations_are_found():
    """The scan sees the citations that exist, so the check above is not empty."""
    texts = read_texts(CITING, CITING_EXCLUDED)
    found = [a for name, text in texts.items() for a in citations(text, name.endswith(SPEC_NAME))]
    assert len(found) >= 3


def test_every_guarantee_id_has_a_spec_heading():
    ids = spec_guarantee_ids(spec_text())
    assert unknown_guarantee_ids(read_texts(SCANNED), ids) == []


def test_spec_and_hook_guarantee_ids_are_the_same():
    hook_ids = set()
    for name, text in read_texts(HOOKS_WITH_DENIES).items():
        hook_ids |= deny_ids(text)
    spec_ids = spec_guarantee_ids(spec_text())
    assert spec_ids == {f"G{n}" for n in range(1, 9)}
    assert id_set_difference(spec_ids, hook_ids) == ([], [])


# --- the helpers on synthetic text -----------------------------------------------

SYNTHETIC_SPEC = "\n".join(
    [
        "# Title",
        "## Launch contract",
        "### Bash rule of G1",
        "### qa-codex contract",
        "### " + "G" + "1 Launch preconditions",
        "### " + "G" + "2 PM launch",
        "## Notes",
        "## Notes",
        "```",
        "## Launch: engineer (attempt 3)",
        "```",
    ]
)


def test_slug_follows_the_github_rule():
    assert slug("Bash rule of G1") == "bash-rule-of-g1"
    assert slug("qa-codex contract") == "qa-codex-contract"
    assert slug("Valid result, pending and current result") == "valid-result-pending-and-current-result"
    assert slug("a_b (c)") == "a_b-c"


def test_repeated_heading_gets_a_suffix():
    assert {"notes", "notes-1"} <= anchors(SYNTHETIC_SPEC)


def test_heading_in_fenced_block_gives_no_anchor():
    have = anchors(SYNTHETIC_SPEC)
    assert "launch-engineer-attempt-3" not in have
    assert "Launch: engineer (attempt 3)" not in headings(SYNTHETIC_SPEC)


def test_missing_anchor_is_reported():
    bad = "docs/specs/" + SPEC_NAME + "#" + "no-such-heading"
    good = "docs/specs/" + SPEC_NAME + "#" + "bash-rule-of-g1"
    texts = {"a.py": f"# see {bad}\n# see {good}\n"}
    assert missing_citations(texts, SYNTHETIC_SPEC, "spec") == [("a.py", "no-such-heading")]


def test_trailing_punctuation_is_not_part_of_the_anchor():
    cite = "docs/specs/" + SPEC_NAME + "#"
    texts = {"a.py": f"# ({cite}bash-rule-of-g1, {cite}notes-1).\n# {cite}notes.\n"}
    assert citations(texts["a.py"]) == ["bash-rule-of-g1", "notes-1", "notes"]
    assert missing_citations(texts, SYNTHETIC_SPEC, "spec") == []


def test_local_link_in_spec_is_checked():
    spec = SYNTHETIC_SPEC + "\nSee [x](#" + "nowhere) and [y](#notes-1)."
    assert missing_citations({"spec": spec}, spec, "spec") == [("spec", "nowhere")]


def test_unknown_guarantee_id_is_reported():
    gid = "G" + "99"
    ids = spec_guarantee_ids(SYNTHETIC_SPEC)
    assert ids == {"G1", "G2"}
    texts = {"a.py": f"# checks G1 and {gid}\n# G12x is not an ID\n"}
    assert unknown_guarantee_ids(texts, ids) == [("a.py", gid)]


def test_deny_ids_are_read_from_string_literals():
    src = 'deny(f"' + "G" + '1: no") and ("' + "G" + "2: x" + '")\n# G3 mention\n'
    assert deny_ids(src) == {"G1", "G2"}


def test_id_set_difference_is_reported_both_ways():
    assert id_set_difference({"G1", "G2"}, {"G1"}) == (["G2"], [])
    assert id_set_difference({"G1"}, {"G1", "G2"}) == ([], ["G2"])
    assert id_set_difference({"G1"}, {"G1"}) == ([], [])


def test_section_number_is_reported():
    line = "# see " + "spec" + " 5.3 and " + "Section" + "-2"
    texts = {"a.py": line + "\n# see the launch contract\n"}
    assert section_number_hits(texts) == [("a.py", 1, line)]
