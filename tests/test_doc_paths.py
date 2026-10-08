"""Fact test for repo paths in instruction files (issue #105).

The instruction files are kept up to date in the same commit as the change
that makes them false. This test checks one fact of them: every repo path an
instruction file names exists in a fresh checkout of the repo. It checks facts,
never meaning.

Files read (INSTRUCTION_FILES below): AGENTS.md, CLAUDE.md, docs/process.md,
docs/task-template.md, every .md file in docs/team/ and .claude/agents/, every
.md file under .agents/skills/, the living spec docs/specs/agent-graph-kit.md,
and of README.md only three sections (README_SECTIONS below: the new-project
section, the Lovable section and the v1 section), each from its heading to the
next "## " heading.

Candidates: the inline code spans with single backticks and the markdown link
targets `](...)`, both outside fenced code blocks (lines between ``` or ~~~
fences). A candidate is a path when it holds a `/` and no whitespace. Bare file
names without a `/` (for example guard.py or labels.json) are not paths for
this test. A `#anchor` at the end of a link target is cut off before the check.

Resolution: a path in an inline code span is resolved from the repo root; a
link target is resolved from the folder of the file that holds the link, as
GitHub does.

Existence: a path exists only when git tracks that file, or tracks at least one
file under that folder (from one `git ls-files` call in the repo root). So a
gitignored or untracked local file counts as missing. A path with a `*`
wildcard exists when it matches at least one tracked file.

Skip rule. A path candidate is skipped, and not checked, when it is:
- a placeholder: it holds `<` or `…`;
- a URL with a scheme: it starts with `https://`, `http://` or `mailto:`;
- a candidate that starts with `/` (slash commands like /goal, absolute paths
  like /tmp/x.md, the permission-rule paths of the Claude Code settings that
  start with `/`), `~`, `$`, `@` or `>`;
- a path that leaves the repo root through `..` (after resolution);
- a GitHub issue reference of the form <owner>/<repo>#<number>, e.g. octo/lib#12;
- an entry of SKIP_LIST below (an entry that ends with `/` also skips every
  path under it). The list holds only paths in a target project and not in
  this repo, and gitignored local-only paths, each with a one-line reason.
"""

import posixpath
import re
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INSTRUCTION_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "docs/process.md",
    "docs/task-template.md",
    "docs/team/*.md",
    ".claude/agents/*.md",
    ".agents/skills/**/*.md",
    "docs/specs/agent-graph-kit.md",
]
README = "README.md"
README_SECTIONS = [
    "## Start a new project",
    "## Lovable frontend lane (optional, v2)",
    "## Set up the kit in a project",
]

# Paths that are skipped, with the reason for each.
SKIP_LIST = {
    "frontend/": "the frontend submodule of a target project, not in this repo",
    "docs/references/local/": "gitignored: third-party articles stay local only",
    ".claude/settings.local.json": "gitignored: the local Claude Code settings file",
    "__pycache__/": "gitignored: Python byte-code cache",
}

MIN_CHECKED = 50

SCHEMES = ("https://", "http://", "mailto:")
SKIP_PREFIXES = ("/", "~", "$", "@", ">")
ISSUE_REF = re.compile(r"^[\w.-]+/[\w.-]+#\d+$")
CODE_SPAN = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)")
LINK_TARGET = re.compile(r"\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```|~~~)")


# --- helpers ---------------------------------------------------------------------


def tracked_files():
    """The repo-relative paths git tracks, from one `git ls-files` call."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return {p for p in out.split("\0") if p}


def outside_fences(text):
    """The lines of a markdown text that are not inside a fenced code block."""
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield line


def candidates(text):
    """(kind, text) for each inline code span ("code") and link target ("link")."""
    out = []
    for line in outside_fences(text):
        spans = list(CODE_SPAN.finditer(line))
        for m in spans:
            if len(m.group(1)) == 1:
                out.append(("code", m.group(2)))
        # Link targets outside code spans only.
        rest = CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)
        for m in LINK_TARGET.finditer(rest):
            out.append(("link", m.group(1)))
    return out


def is_path(candidate):
    return "/" in candidate and not re.search(r"\s", candidate)


def skip_list_match(path, skip_list):
    for entry in skip_list:
        if entry.endswith("/"):
            if path == entry.rstrip("/") or path.startswith(entry):
                return entry
        elif path == entry:
            return entry
    return None


def resolve(source, kind, candidate):
    """The repo-relative path a candidate names, or None when it is skipped."""
    if "<" in candidate or "…" in candidate:
        return None
    if candidate.startswith(SCHEMES) or candidate.startswith(SKIP_PREFIXES):
        return None
    if ISSUE_REF.match(candidate):
        return None
    if kind == "link":
        candidate = candidate.split("#", 1)[0]
        if not candidate:
            return None
        joined = posixpath.join(posixpath.dirname(source), candidate)
    else:
        joined = candidate
    path = posixpath.normpath(joined)
    if path == ".." or path.startswith("../"):
        return None
    return path


def exists(path, tracked):
    """True when git tracks the file, a file under the folder, or a wildcard match."""
    if "*" in path:
        return any(fnmatchcase(t, path) for t in tracked)
    if path in tracked:
        return True
    prefix = path.rstrip("/") + "/"
    return any(t.startswith(prefix) for t in tracked)


def check_texts(texts, tracked, skip_list=SKIP_LIST):
    """(checked paths, missing (file, path) pairs) over {file: text}."""
    checked = []
    missing = []
    for source, text in texts.items():
        for kind, candidate in candidates(text):
            if not is_path(candidate):
                continue
            path = resolve(source, kind, candidate)
            if path is None or skip_list_match(path, skip_list):
                continue
            checked.append((source, path))
            if not exists(path, tracked):
                missing.append((source, path))
    return checked, missing


def section(text, heading):
    """The lines from `heading` to the next `## ` heading (not included)."""
    lines = text.splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def instruction_texts():
    """{repo-relative path: text} of the instruction files."""
    texts = {}
    for entry in INSTRUCTION_FILES:
        for path in sorted(ROOT.glob(entry)):
            if path.is_file():
                texts[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    readme = (ROOT / README).read_text(encoding="utf-8")
    texts[README] = "\n".join(section(readme, h) for h in README_SECTIONS)
    return texts


# --- the repo ----------------------------------------------------------------------


def test_instruction_files_are_read():
    texts = instruction_texts()
    for name in ["AGENTS.md", "CLAUDE.md", "docs/process.md", "docs/task-template.md",
                 "docs/team/orchestrator.md", ".claude/agents/pm.md",
                 ".agents/skills/stage-start/SKILL.md", "docs/specs/agent-graph-kit.md", "README.md"]:
        assert name in texts
    headings = [line for line in texts["README.md"].splitlines() if line.startswith("## ")]
    assert headings == README_SECTIONS


def test_every_named_repo_path_exists():
    checked, missing = check_texts(instruction_texts(), tracked_files())
    assert missing == [], "missing paths:\n" + "\n".join(f"{f}: {p}" for f, p in missing)
    assert len(checked) >= MIN_CHECKED, f"only {len(checked)} paths checked"


# --- the helpers on synthetic text -----------------------------------------------

TRACKED = {"docs/process.md", "docs/archive/x.md", "scripts/qa-codex", ".claude/hooks/guard.py"}


def test_missing_path_is_reported_with_file_and_path():
    texts = {"docs/a.md": "See `docs/process.md` and `docs/no-such.md`.\n"}
    checked, missing = check_texts(texts, TRACKED, skip_list={})
    assert missing == [("docs/a.md", "docs/no-such.md")]
    assert len(checked) == 2


def test_folder_exists_when_a_file_under_it_is_tracked():
    texts = {"a.md": "`docs/archive/` and `scripts` and `.claude/hooks` and `docs/arch/`\n"}
    assert check_texts(texts, TRACKED, skip_list={})[1] == [("a.md", "docs/arch")]


def test_bare_file_name_is_not_a_path():
    texts = {"a.md": "`guard.py` and `labels.json`\n"}
    assert check_texts(texts, TRACKED, skip_list={}) == ([], [])


def test_code_span_with_whitespace_is_not_a_path():
    texts = {"a.md": "`gh issue view docs/x/y`\n"}
    assert check_texts(texts, TRACKED, skip_list={}) == ([], [])


def test_fenced_code_block_is_ignored():
    texts = {"a.md": "```\n`docs/no-such.md` [x](no/such.md)\n```\n~~~\n`no/such`\n~~~\n"}
    assert check_texts(texts, TRACKED, skip_list={}) == ([], [])


def test_double_backtick_span_is_not_a_candidate():
    assert candidates("``docs/no-such.md`` and `docs/process.md`") == [("code", "docs/process.md")]


def test_link_target_is_resolved_from_the_files_folder():
    texts = {"docs/specs/a.md": "See [x](../archive/x.md) and [y](../archive/y.md#part).\n"}
    checked, missing = check_texts(texts, TRACKED, skip_list={})
    assert [p for _, p in checked] == ["docs/archive/x.md", "docs/archive/y.md"]
    assert missing == [("docs/specs/a.md", "docs/archive/y.md")]


def test_anchor_is_cut_from_a_link_target():
    texts = {"docs/a.md": "[x](./process.md#rules) and [y](#local) and [z](../docs/process.md#a)\n"}
    checked, missing = check_texts(texts, TRACKED, skip_list={})
    assert checked == [("docs/a.md", "docs/process.md"), ("docs/a.md", "docs/process.md")]
    assert missing == []


def test_code_span_is_resolved_from_the_repo_root():
    texts = {"docs/specs/a.md": "`docs/process.md`\n"}
    assert check_texts(texts, TRACKED, skip_list={}) == ([("docs/specs/a.md", "docs/process.md")], [])


def test_wildcard_with_no_tracked_match_is_reported():
    texts = {"a.md": "`.claude/hooks/*.py` and `docs/*.txt`\n"}
    assert check_texts(texts, TRACKED, skip_list={})[1] == [("a.md", "docs/*.txt")]


def test_untracked_file_on_disk_is_reported():
    # This file exists on disk, but the tracked list given to the helper lacks it.
    assert (ROOT / "tests" / "test_doc_paths.py").is_file()
    texts = {"a.md": "`tests/test_doc_paths.py`\n"}
    assert check_texts(texts, TRACKED, skip_list={})[1] == [("a.md", "tests/test_doc_paths.py")]


SKIPPED_EXAMPLES = [
    "`docs/<name>.md`",  # placeholder with <
    "`docs/…/x.md`",  # placeholder with …
    "[a](https://example.com/x)",  # URL https
    "[a](http://example.com/x)",  # URL http
    "[a](mailto:someone@example.com/x)",  # URL mailto
    "`/goal`",  # slash command
    "`/tmp/x.md`",  # absolute path
    "`~/notes/x.md`",  # home path
    "`$TMPDIR/x.md`",  # variable path
    "`@scope/package`",  # npm package
    "`>docs/x.md`",  # starts with >
    "`../agent-graph-kit`",  # leaves the repo root (code span)
    "[a](../../outside.md)",  # leaves the repo root (link from docs/)
    "`octo/lib#12`",  # GitHub issue reference
    "`listed/thing.md`",  # explicit list, exact entry
    "`target/` and `target/app/x.ts`",  # explicit list, folder entry and a path under it
]


def test_each_skip_rule_skips_its_example():
    skip_list = {"listed/thing.md": "test", "target/": "test"}
    for example in SKIPPED_EXAMPLES:
        texts = {"docs/a.md": example + "\n"}
        assert check_texts(texts, TRACKED, skip_list=skip_list) == ([], []), example


def test_without_the_skip_list_entry_the_path_is_checked():
    texts = {"a.md": "`target/app/x.ts`\n"}
    assert check_texts(texts, TRACKED, skip_list={})[1] == [("a.md", "target/app/x.ts")]


def test_section_ends_at_the_next_level_two_heading():
    text = "# T\n## A\nx `a/b`\n### sub\ny\n## B\nz\n"
    assert section(text, "## A") == "## A\nx `a/b`\n### sub\ny"


def test_readme_route_anchor_links_point_to_headings():
    readme = (ROOT / README).read_text(encoding="utf-8")
    route = section(readme, "## Start a new project")
    slugs = set()
    for line in outside_fences(readme):
        m = re.match(r"^#+\s+(.*)$", line)
        if m:
            slugs.add(re.sub(r"[^\w\- ]", "", m.group(1).lower()).replace(" ", "-"))
    anchors = re.findall(r"\]\(#([^)\s]+)\)", "\n".join(outside_fences(route)))
    assert anchors
    assert [a for a in anchors if a not in slugs] == []
