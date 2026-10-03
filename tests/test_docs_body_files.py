"""Fact tests for per-launch body files and the read-back before posting (issue #130).

They read the role files in docs/team/ and docs/process.md and check the
facts the issue asks for. No test runs gh, git or another subprocess.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEAM = ROOT / "docs" / "team"
PROCESS = (ROOT / "docs" / "process.md").read_text(encoding="utf-8")


def read(name):
    return (TEAM / name).read_text(encoding="utf-8")


def section(text, heading):
    """The text from a heading line to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    start = lines.index(heading)
    out = []
    for line in lines[start + 1:]:
        m = re.match(r"^(#+) ", line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return "\n".join(out)


def body_files(name):
    return section(read(name), "## Body files")


# file -> receipt role of the launched agent
LAUNCHED = {
    "pm.md": "pm",
    "software-engineer.md": "engineer",
    "qa-engineer.md": "qa",
    "planner.md": "planner",
}
# file -> role in the path of a session without a receipt
RECEIPTLESS = {
    "orchestrator.md": "orchestrator",
    "planner.md": "planner",
}
FIVE = ["pm.md", "software-engineer.md", "qa-engineer.md", "planner.md", "orchestrator.md"]
# files that tell their agent to file or edit an issue
FILES_ISSUES = ["pm.md", "planner.md", "orchestrator.md"]


@pytest.mark.parametrize("name,role", LAUNCHED.items())
def test_launched_role_gives_attempt_path_form(name, role):
    text = body_files(name)
    assert "`/tmp/<role>-<issue>-attempt<n>.md`" in text
    assert re.search(rf"`/tmp/{role}-\d+-attempt\d+\.md`", text), f"concrete example for {role}"
    assert f"`## Launch: {role} (attempt <n>)`" in text
    assert f"`## Launch: {role} (continued, round <n>)`" in text
    assert "newest" in text


@pytest.mark.parametrize("name,role", RECEIPTLESS.items())
def test_receiptless_session_gives_utc_path_form(name, role):
    text = body_files(name)
    assert "no launch receipt" in text
    assert "`/tmp/<role>-<issue>-<UTC time>.md`" in text
    assert "`date -u +%Y%m%dT%H%M%S`" in text
    assert "right before the body is written" in text
    assert re.search(rf"`/tmp/{role}-\d+-\d{{8}}T\d{{6}}\.md`", text), f"concrete example for {role}"


def test_planner_names_which_jobs_use_which_form():
    text = body_files("planner.md")
    assert "Stage review" in text and "Intake and stage set-up" in text


def test_qa_rule_is_for_the_fallback_only_and_codex_posts_nothing():
    text = body_files("qa-engineer.md")
    assert "fallback `qa-engineer`" in text
    assert "`scripts/qa-codex`" in text
    assert "Do not post a comment." in read("qa-engineer.md")


@pytest.mark.parametrize("name", FIVE)
def test_second_body_gets_suffixed_path(name):
    text = body_files(name)
    assert "second body" in text
    assert "suffix" in text
    assert re.search(r"`/tmp/[a-z]+-\d+-(attempt\d+|\d{8}T\d{6})-[a-z]+\d+\.md`", text)


@pytest.mark.parametrize("name", FIVE)
def test_write_fresh_and_read_back_before_posting(name):
    text = body_files(name)
    assert "overwrite" in text and "never append" in text
    assert "denied or fails, do not post" in text
    assert "Read the body file back" in text
    assert "`cat <path>` as its own call" in text
    assert "intended first line" in text
    assert "placeholder text" in text
    assert "`TESTS_LINE`" in text
    assert "`<SHA>`" in text
    assert "Never join it to the post with `&&`, `;` or `|`" in text


@pytest.mark.parametrize("name,markers", [
    ("pm.md", ["`## PM: GROOMED`"]),
    ("software-engineer.md", ["`## Engineer: DONE`"]),
    ("qa-engineer.md", ["`## QA: PASS`"]),
    ("planner.md", ["`## Planner: STAGE REVIEW`", "`Lane:`", "`## Purpose`"]),
    ("orchestrator.md", ["`Lane:`"]),
])
def test_intended_first_line_examples(name, markers):
    text = body_files(name)
    for marker in markers:
        assert marker in text, marker


@pytest.mark.parametrize("name", FILES_ISSUES)
def test_rule_covers_issue_create_and_edit(name):
    text = body_files(name)
    assert "`gh issue create`" in text
    assert "`gh issue edit`" in text
    assert "`--body-file`" in text


def test_pm_names_follow_ups_and_resume_edits():
    text = body_files("pm.md")
    assert "follow-up" in text and "fix issue" in text
    assert "`## Owner: RESUME`" in text


ATTEMPT_PATH = re.compile(r"^/tmp/(<role>|[a-z]+)-(<issue>|<stage>|\d+)-(attempt(<n>|\d+))(-[a-z]+\d+)?\.md$")
UTC_PATH = re.compile(r"^/tmp/(<role>|[a-z]+)-(<issue>|<stage>|\d+)-(<UTC time>|\d{8}T\d{6})(-[a-z]+\d+)?\.md$")


def tmp_paths():
    files = sorted(TEAM.glob("*.md")) + [ROOT / "docs" / "process.md"]
    for path in files:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"/tmp/(?:<UTC time>|[^`\s)])*", line):
                yield f"{path.name}:{no}", m.group(0)


def test_every_tmp_path_follows_the_new_forms():
    found = list(tmp_paths())
    assert len(found) >= 10
    for where, path in found:
        assert "engineer-comment-72" not in path, where
        assert "planner-review-93" not in path, where
        assert ATTEMPT_PATH.match(path) or UTC_PATH.match(path), f"{where}: {path}"


def test_process_rule_names_per_launch_path_and_read_back():
    bullets = [l for l in PROCESS.splitlines() if l.startswith("- Agents post issue comments only with")]
    assert len(bullets) == 1
    rule = bullets[0]
    assert "`gh issue comment <n> --body-file <literal path>` as the whole command" in rule
    assert "attempt<n>" in rule
    assert "UTC time" in rule
    assert "read" in rule and "back" in rule
    assert "own path" in rule


POST_FORM = re.compile(r"^gh issue comment (<[^>]+>|\d+) --body-file (<[^>]+>|/tmp/\S+)$")


def test_posting_form_stays_the_whole_command():
    files = sorted(TEAM.glob("*.md")) + [ROOT / "docs" / "process.md"]
    seen = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for span in re.findall(r"`([^`]*gh issue comment[^`]*)`", text):
            seen += 1
            assert POST_FORM.match(span), f"{path.name}: {span}"
        assert not re.search(r"(&&|;|\|)\s*gh issue comment", text), path.name
        assert not re.search(r"gh issue comment[^`\n]*(&&|;|\|)", text), path.name
    assert seen >= 8
