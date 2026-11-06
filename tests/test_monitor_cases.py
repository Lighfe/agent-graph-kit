"""Tests for the retry case collector `plugin/skills/monitor/cases.py` (issue #264). All issues,
comments, run-record lines and step rows are synthetic."""

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugin" / "skills" / "monitor" / "cases.py"
FAKES = ROOT / "tests" / "fakes"
PROJECT = "acme/widgets"


def load():
    spec = importlib.util.spec_from_file_location("cases_under_test", SRC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cs = load()


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    """Cases, run record and step rows in a temp state dir."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("RUN_RECORD_FILE", str(tmp_path / "state" / "run-record.jsonl"))
    monkeypatch.setenv("STEPS_FILE", str(tmp_path / "state" / "steps.jsonl"))


def c(body, t, url=None, assoc="OWNER"):
    out = {"body": body, "createdAt": t}
    if url:
        out["url"] = url
    if assoc is not None:
        out["authorAssociation"] = assoc
    return out


def t(minute):
    return f"2026-11-04T10:{minute:02d}:00Z"


BODY = "Lane: default\n\n## Acceptance criteria\n\n- [ ] The log line   has one sentence\n- [ ] The script exits 0\n"


def qa_fail(minute, url=None):
    return c("## QA: FAIL\n\nVerified: abc\n\n- [x] The script exits 0 - PASS\n"
             "- [ ] The log line has one sentence - FAIL\n- [ ] A line that is not in the body - INVALID\n",
             t(minute), url=url)


def receipt(role, minute):
    return c(f"## Launch: {role} (attempt 1)\nAgent: {role}\nCall: abc", t(minute))


def done(minute, rng="aaa111..bbb222"):
    return c(f"## Engineer: DONE\n\nDid it.\n\nCommits: {rng}\n", t(minute))


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def cases_of(issue, number=7, stage=3, repo=None):
    return cs.issue_cases(PROJECT, stage, number, issue, repo,
                          cs.read_jsonl(cs.rr.record_path()), cs.read_jsonl(cs.st.steps_path()))


def standard_issue(**extra):
    issue = {"number": 7, "body": BODY, "comments": [
        receipt("pm", 0), c("## PM: GROOMED", t(1)), receipt("engineer", 2), done(3),
        receipt("qa-codex", 4), qa_fail(5, url="https://example.test/c/5"),
        receipt("engineer", 6), done(8, "bbb222..ccc333"), receipt("qa-codex", 9), c("## QA: PASS\n\nok", t(10)),
    ]}
    issue.update(extra)
    return issue


# --- fields ---------------------------------------------------------------------------------

def test_fields_are_exact_and_judge_nothing():
    [case] = cases_of(standard_issue())
    assert tuple(case) == cs.FIELDS
    assert set(case) == {"id", "project", "stage", "issue", "round", "marker", "comment_url", "failed_lines",
                         "criteria", "next_markers", "body_edited", "commit", "files_changed", "lines_added",
                         "lines_removed", "tokens", "seconds"}
    for judging in ("cause", "verdict", "category", "score"):
        assert judging not in case
    assert case["id"] == f"{PROJECT}:7:1"
    assert (case["project"], case["stage"], case["issue"], case["round"]) == (PROJECT, 3, 7, 1)
    assert case["marker"] == "## QA: FAIL"
    assert case["comment_url"] == "https://example.test/c/5"


def test_comment_url_null_without_url():
    issue = standard_issue()
    issue["comments"][5].pop("url")
    assert cases_of(issue)[0]["comment_url"] is None


# --- round rule -----------------------------------------------------------------------------

MARKERS = ["## QA: FAIL", "## QA: UNVERIFIABLE", "## QA: INVALID", "## QA: UNAVAILABLE", "## Engineer: BLOCKED",
           "## PM: NEEDS OWNER"]


@pytest.mark.parametrize("marker", MARKERS)
def test_each_marker_with_receipt_starts_a_round(marker):
    issue = {"body": BODY, "comments": [receipt("engineer", 0), c(marker + "\n\nwhy", t(1)), receipt("pm", 2),
                                        c("## PM: GROOMED", t(3))]}
    [case] = cases_of(issue)
    assert case["marker"] == marker
    assert case["next_markers"] == ["## PM: GROOMED"]


@pytest.mark.parametrize("marker", MARKERS)
def test_marker_without_receipt_gives_no_case(marker):
    issue = {"body": BODY, "comments": [receipt("engineer", 0), c(marker, t(1)), c("## Owner: RESUME", t(2))]}
    assert cases_of(issue) == []


def test_marker_followed_by_marker_before_receipt_gives_no_case_for_the_first():
    issue = {"body": BODY, "comments": [receipt("qa-codex", 0), c("## QA: UNAVAILABLE", t(1)),
                                        c("## PM: NEEDS OWNER", t(2)), receipt("pm", 3)]}
    [case] = cases_of(issue)
    assert case["marker"] == "## PM: NEEDS OWNER"


def test_relaunch_after_miss_without_marker_gives_no_case():
    issue = {"body": BODY, "comments": [receipt("engineer", 0), receipt("engineer", 1), done(2)]}
    assert cases_of(issue) == []


def test_round_lasts_until_next_starting_marker_and_groomed_starts_no_round():
    issue = {"body": BODY, "comments": [
        receipt("qa-codex", 0), qa_fail(1), receipt("pm", 2), c("## PM: GROOMED", t(3)), receipt("engineer", 4),
        c("## Engineer: BLOCKED\n\nquestion", t(5)),  # no receipt after it before the next marker
        c("## QA: INVALID", t(6)), receipt("pm", 7), c("## PM: GROOMED", t(8)),
    ]}
    cases = cases_of(issue)
    assert [x["marker"] for x in cases] == ["## QA: FAIL", "## QA: INVALID"]
    assert [x["round"] for x in cases] == [1, 2]
    assert cases[0]["next_markers"] == ["## PM: GROOMED", "## Engineer: BLOCKED"]
    assert cases[1]["next_markers"] == ["## PM: GROOMED"]


def test_comments_of_non_owners_are_ignored_and_missing_field_counts():
    issue = {"body": BODY, "comments": [
        receipt("qa-codex", 0), c("## QA: FAIL", t(1), assoc="NONE"), c("## Launch: pm (attempt 1)", t(2), assoc="NONE"),
        c("## QA: FAIL", t(3), assoc=None), receipt("engineer", 4),
    ]}
    [case] = cases_of(issue)
    assert case["marker"] == "## QA: FAIL"
    assert case["round"] == 1


# --- failed lines and criteria ----------------------------------------------------------------

def test_failed_lines_and_matching_criteria():
    [case] = cases_of(standard_issue())
    assert case["failed_lines"] == ["- [ ] The log line has one sentence - FAIL",
                                    "- [ ] A line that is not in the body - INVALID"]
    assert case["criteria"] == ["- [ ] The log line   has one sentence"]


def test_unverifiable_suffix_counts():
    body = "## QA: UNVERIFIABLE\n- [ ] The script exits 0 - UNVERIFIABLE\n- [ ] other - PASS\n"
    issue = {"body": BODY, "comments": [c(body, t(1)), receipt("pm", 2)]}
    [case] = cases_of(issue)
    assert case["failed_lines"] == ["- [ ] The script exits 0 - UNVERIFIABLE"]
    assert case["criteria"] == ["- [ ] The script exits 0"]


def test_indented_lines_are_not_failed_lines():
    body = ("## QA: FAIL\n- [ ] The script exits 0 - FAIL\n    - [ ] Indented example - FAIL\n"
            "  - [ ] The log line has one sentence - FAIL\n")
    issue = {"body": BODY + "\n  - [ ] Indented example\n", "comments": [c(body, t(1)), receipt("pm", 2)]}
    [case] = cases_of(issue)
    assert case["failed_lines"] == ["- [ ] The script exits 0 - FAIL"]
    assert case["criteria"] == ["- [ ] The script exits 0"]


def test_indented_body_line_is_not_a_criterion():
    body = "## QA: FAIL\n- [ ] Indented example - FAIL\n"
    issue = {"body": "## Acceptance criteria\n\n  - [ ] Indented example\n",
             "comments": [c(body, t(1)), receipt("pm", 2)]}
    [case] = cases_of(issue)
    assert case["failed_lines"] == ["- [ ] Indented example - FAIL"]
    assert case["criteria"] == []


def test_other_markers_give_empty_lists():
    body = "## Engineer: BLOCKED\n- [ ] The script exits 0 - FAIL\n"
    issue = {"body": BODY, "comments": [c(body, t(1)), receipt("pm", 2)]}
    [case] = cases_of(issue)
    assert case["failed_lines"] == [] and case["criteria"] == []


# --- body edits and commit ------------------------------------------------------------------

def test_body_edited_true_false_null():
    assert cases_of(standard_issue())[0]["body_edited"] is None
    inside = standard_issue(userContentEdits=[{"editedAt": "2026-11-04T10:07:00Z"}])
    assert cases_of(inside)[0]["body_edited"] is True
    outside = standard_issue(userContentEdits={"nodes": [{"editedAt": "2026-11-04T10:01:00Z"}]})
    assert cases_of(outside)[0]["body_edited"] is False
    assert cases_of(standard_issue(userContentEdits=[]))[0]["body_edited"] is False


def test_commit_is_first_done_of_the_round_without_repo_counts_null():
    issue = standard_issue()
    issue["comments"].insert(8, done(8, "ccc333..ddd444"))
    [case] = cases_of(issue)
    assert case["commit"] == "bbb222..ccc333"
    assert (case["files_changed"], case["lines_added"], case["lines_removed"]) == (None, None, None)


def test_blocked_round_with_body_edit_and_no_done():
    issue = {"body": BODY, "userContentEdits": [{"editedAt": t(3)}], "comments": [
        receipt("engineer", 0), c("## Engineer: BLOCKED\n\nwhich file?", t(1)), receipt("pm", 2),
        c("## PM: GROOMED", t(4))]}
    [case] = cases_of(issue)
    assert case["body_edited"] is True
    assert case["commit"] is None
    assert (case["files_changed"], case["lines_added"], case["lines_removed"]) == (None, None, None)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def test_numstat_from_git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.test")
    git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("one\ntwo\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("one\nTWO\nthree\n")
    (repo / "b.txt").write_text("new\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "work")
    head = git(repo, "rev-parse", "HEAD")
    issue = standard_issue()
    issue["comments"][7] = done(8, f"{base}..{head}")
    [case] = cases_of(issue, repo=repo)
    assert case["commit"] == f"{base}..{head}"
    assert (case["files_changed"], case["lines_added"], case["lines_removed"]) == (2, 3, 1)
    issue["comments"][7] = done(8, "deadbeef..cafebabe")
    [case] = cases_of(issue, repo=repo)
    assert (case["files_changed"], case["lines_added"], case["lines_removed"]) == (None, None, None)


# --- cost join ------------------------------------------------------------------------------

def rec(rid, provider, start, issue=7, project=PROJECT, i=1, o=2, cc=3, cr=4):
    return {"id": rid, "project": project, "issue": issue, "provider": provider, "start": start,
            "input_tokens": i, "output_tokens": o, "cache_creation_tokens": cc, "cache_read_tokens": cr}


def test_tokens_and_seconds_join_by_time_inside_the_round():
    write_jsonl(os.environ["RUN_RECORD_FILE"], [
        rec("a", "claude", t(2)),                       # before the round
        rec("b", "claude", t(6)),                       # engineer of the round: 10
        rec("b", "claude", t(6), i=100),                # last line per id wins: 109
        rec("c", "codex", t(9), i=1000, o=0, cc=0, cr=500),  # second QA run: 1500
        rec("d", None, t(7)),                           # issue line, no provider
        rec("e", "claude", t(7), issue=8),              # other issue
        rec("f", "claude", t(7), project="other/x"),    # other project
    ])
    write_jsonl(os.environ["STEPS_FILE"], [
        {"id": "s1", "project": PROJECT, "issue": 7, "time": t(4), "duration_s": 99},
        {"id": "s2", "project": PROJECT, "issue": 7, "time": t(6), "duration_s": 2.5},
        {"id": "s3", "project": PROJECT, "issue": 7, "time": t(9), "duration_s": None},
        {"id": "s4", "project": PROJECT, "issue": 7, "time": t(10), "duration_s": 3},
        {"id": "s5", "project": PROJECT, "issue": 8, "time": t(6), "duration_s": 40},
    ])
    [case] = cases_of(standard_issue())
    assert case["tokens"] == {"claude": 109, "codex": 1500}
    assert case["seconds"] == 5.5


def test_missing_files_give_null_cost():
    [case] = cases_of(standard_issue())
    assert case["tokens"] is None and case["seconds"] is None


def test_no_matching_row_gives_null_cost():
    write_jsonl(os.environ["RUN_RECORD_FILE"], [rec("a", "claude", t(1))])
    write_jsonl(os.environ["STEPS_FILE"], [{"id": "s", "project": PROJECT, "issue": 7, "time": t(1), "duration_s": 4}])
    [case] = cases_of(standard_issue())
    assert case["tokens"] is None and case["seconds"] is None


def test_round_bounds_split_cost_between_rounds():
    write_jsonl(os.environ["RUN_RECORD_FILE"], [rec("a", "claude", t(2), i=10), rec("b", "claude", t(6), i=20)])
    issue = {"body": BODY, "comments": [
        receipt("qa-codex", 0), qa_fail(1), receipt("engineer", 2), done(3),
        receipt("qa-codex", 4), qa_fail(5), receipt("engineer", 6), done(7)]}
    first, second = cases_of(issue)
    assert first["tokens"] == {"claude": 19} and second["tokens"] == {"claude": 29}
    assert (first["commit"], second["commit"]) == ("aaa111..bbb222", "aaa111..bbb222")


# --- command line ---------------------------------------------------------------------------

def run(args, env=None):
    return subprocess.run([sys.executable, str(SRC), *args], capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def test_collect_from_issues_file_writes_whole_file_mode_0600(tmp_path):
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([standard_issue(), dict(standard_issue(), number=9)]))
    out = Path(os.environ["XDG_STATE_HOME"]) / "agent-graph-kit" / "retry-cases.jsonl"
    out.parent.mkdir(parents=True)
    out.write_text('{"old": 1}\n{"old": 2}\n{"old": 3}\n')
    res = run(["collect", "--project", PROJECT, "--issues", str(issues), "--stage", "3"])
    assert res.returncode == 0, res.stderr
    assert "2 cases" in res.stdout
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert [r["id"] for r in rows] == [f"{PROJECT}:7:1", f"{PROJECT}:9:1"]
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    res = run(["collect", "--project", PROJECT, "--issues", str(issues), "--stage", "3"])
    assert len(out.read_text().splitlines()) == 2


def test_default_path_without_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cs.cases_path() == tmp_path / "home" / ".local" / "state" / "agent-graph-kit" / "retry-cases.jsonl"


def test_collect_from_repo_slug_makes_only_reads(tmp_path):
    calls = tmp_path / "calls.jsonl"
    api = tmp_path / "api.json"
    api.write_text(json.dumps({"sub_issues": [{"number": 7}],
                               "graphql": {"7": [{"editedAt": "2026-11-04T10:07:00Z"}]}}))
    issue = tmp_path / "issue.json"
    issue.write_text(json.dumps(standard_issue()))
    env = {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_CALLS": str(calls),
           "FAKE_GH_API": str(api), "FAKE_GH_ISSUE": str(issue)}
    res = run(["collect", "--project", PROJECT, "--repo-slug", "acme/widgets", "--stage", "3"], env)
    assert res.returncode == 0, res.stderr
    assert "1 cases" in res.stdout
    out = Path(os.environ["XDG_STATE_HOME"]) / "agent-graph-kit" / "retry-cases.jsonl"
    [row] = [json.loads(x) for x in out.read_text().splitlines()]
    assert row["stage"] == 3 and row["issue"] == 7 and row["body_edited"] is True
    logged = [json.loads(x) for x in calls.read_text().splitlines()]
    assert logged
    kinds = set()
    for argv in logged:
        assert argv[:2] == ["issue", "view"] or argv[0] == "api", argv
        if argv[0] == "api":
            for flag in ("-X", "--method"):
                if flag in argv:
                    assert argv[argv.index(flag) + 1].upper() == "GET", argv
            assert not any(a.startswith("--method=") and a.upper() != "--METHOD=GET" for a in argv)
            if argv[1] == "graphql":
                query = next(a for a in argv if a.startswith("query="))[len("query="):]
                assert query.lstrip().startswith("query") and "mutation" not in query
        kinds.add(argv[1] if argv[0] == "api" and argv[1] == "graphql" else argv[0] if argv[0] == "api" else "view")
    assert kinds == {"api", "graphql", "view"}


def test_repo_slug_reads_every_page_of_edit_times(tmp_path):
    calls = tmp_path / "calls.jsonl"
    api = tmp_path / "api.json"
    pages = [[{"editedAt": "2026-11-04T09:00:00Z"}], [{"editedAt": "2026-11-04T09:30:00Z"}],
             [{"editedAt": "2026-11-04T10:07:00Z"}]]
    api.write_text(json.dumps({"sub_issues": [{"number": 7}], "graphql": {"7": {"pages": pages}}}))
    issue = tmp_path / "issue.json"
    issue.write_text(json.dumps(standard_issue()))
    env = {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_CALLS": str(calls),
           "FAKE_GH_API": str(api), "FAKE_GH_ISSUE": str(issue)}
    res = run(["collect", "--project", PROJECT, "--repo-slug", "acme/widgets", "--stage", "3"], env)
    assert res.returncode == 0, res.stderr
    out = Path(os.environ["XDG_STATE_HOME"]) / "agent-graph-kit" / "retry-cases.jsonl"
    [row] = [json.loads(x) for x in out.read_text().splitlines()]
    # Only the edit on the last page falls inside the round.
    assert row["body_edited"] is True
    graphql = [argv for argv in map(json.loads, calls.read_text().splitlines()) if argv[:2] == ["api", "graphql"]]
    assert len(graphql) == 3
    afters = [next((a for a in argv if a.startswith("after=")), None) for argv in graphql]
    assert afters == [None, "after=1", "after=2"]
    for argv in graphql:
        query = next(a for a in argv if a.startswith("query="))[len("query="):]
        assert "pageInfo" in query and "hasNextPage" in query and "endCursor" in query


def test_repo_slug_needs_stage():
    res = run(["collect", "--project", PROJECT, "--repo-slug", "acme/widgets"])
    assert res.returncode == 2


def test_gh_failure_writes_nothing(tmp_path):
    env = {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_FAIL": "1"}
    res = run(["collect", "--project", PROJECT, "--repo-slug", "acme/widgets", "--stage", "3"], env)
    assert res.returncode == 1
    assert not (Path(os.environ["XDG_STATE_HOME"]) / "agent-graph-kit" / "retry-cases.jsonl").exists()


# --- merge with the rows of other runs (issue #273) ----------------------------------------

def out_path():
    return Path(os.environ["XDG_STATE_HOME"]) / "agent-graph-kit" / "retry-cases.jsonl"


def issues_file(tmp_path, numbers, name="issues.json"):
    path = tmp_path / name
    path.write_text(json.dumps([dict(standard_issue(), number=n) for n in numbers]))
    return path


def collect_file(path, stage=None, project=PROJECT):
    args = ["collect", "--project", project, "--issues", str(path)]
    if stage is not None:
        args += ["--stage", str(stage)]
    res = run(args)
    assert res.returncode == 0, res.stderr
    return res


def rows_of():
    return [json.loads(x) for x in out_path().read_text().splitlines()]


def row(rid, project, stage, **extra):
    return {"id": rid, "project": project, "stage": stage, **extra}


def test_two_stages_of_one_project_are_both_kept(tmp_path):
    collect_file(issues_file(tmp_path, [7], "a.json"), stage=1)
    res = collect_file(issues_file(tmp_path, [9], "b.json"), stage=2)
    assert "Wrote 1 cases to" in res.stdout
    assert [(r["id"], r["stage"]) for r in rows_of()] == [(f"{PROJECT}:7:1", 1), (f"{PROJECT}:9:1", 2)]


def test_second_run_replaces_only_its_project_and_stage(tmp_path):
    other = [row(f"{PROJECT}:20:1", PROJECT, 2, note="b"), row("other/q:7:1", "other/q", 1, note="q1"),
             row("other/q:8:1", "other/q", 2, note="q2")]
    gone = row(f"{PROJECT}:11:1", PROJECT, 1, note="gone")
    write_jsonl(out_path(), [other[0], gone, other[1], other[2]])
    res = collect_file(issues_file(tmp_path, [7]), stage=1)
    assert "Wrote 1 cases to" in res.stdout
    rows = rows_of()
    assert rows[:3] == other
    assert [r["id"] for r in rows] == [f"{PROJECT}:20:1", "other/q:7:1", "other/q:8:1", f"{PROJECT}:7:1"]


def test_run_without_cases_removes_only_its_rows(tmp_path):
    keep = [row(f"{PROJECT}:20:1", PROJECT, 2), row("other/q:7:1", "other/q", 1)]
    write_jsonl(out_path(), [row(f"{PROJECT}:7:1", PROJECT, 1), keep[0], keep[1]])
    path = tmp_path / "empty.json"
    path.write_text(json.dumps([{"number": 7, "body": BODY, "comments": []}]))
    res = collect_file(path, stage=1)
    assert "Wrote 0 cases to" in res.stdout
    assert rows_of() == keep


def test_issue_moved_to_another_stage_keeps_its_id_once(tmp_path):
    write_jsonl(out_path(), [row(f"{PROJECT}:7:1", PROJECT, 1, note="old"), row(f"{PROJECT}:8:1", PROJECT, 1)])
    collect_file(issues_file(tmp_path, [7]), stage=2)
    rows = rows_of()
    assert [r["id"] for r in rows] == [f"{PROJECT}:8:1", f"{PROJECT}:7:1"]
    assert rows[1]["stage"] == 2 and "note" not in rows[1]


def test_run_without_stage_replaces_only_rows_with_stage_null(tmp_path):
    staged = row(f"{PROJECT}:20:1", PROJECT, 3)
    write_jsonl(out_path(), [row(f"{PROJECT}:30:1", PROJECT, None), staged])
    collect_file(issues_file(tmp_path, [7]))
    rows = rows_of()
    assert rows[0] == staged
    assert [(r["id"], r["stage"]) for r in rows] == [(f"{PROJECT}:20:1", 3), (f"{PROJECT}:7:1", None)]


def test_stage_compare_is_on_the_json_value(tmp_path):
    keep = [row(f"{PROJECT}:20:1", PROJECT, "1"), row(f"{PROJECT}:21:1", PROJECT, None),
            row(f"{PROJECT}:22:1", PROJECT, True)]
    write_jsonl(out_path(), keep + [row(f"{PROJECT}:23:1", PROJECT, 1)])
    collect_file(issues_file(tmp_path, [7]), stage=1)
    assert rows_of()[:3] == keep and len(rows_of()) == 4


def test_old_rows_keep_the_order_of_their_last_line_and_the_last_line_counts(tmp_path):
    out = out_path()
    out.parent.mkdir(parents=True)
    a1, b, a2 = row("q:1:1", "q", 1, v=1), row("q:2:1", "q", 1), row("q:1:1", "q", 1, v=2)
    out.write_text("".join(json.dumps(r) + "\n" for r in (a1, b, a2))
                   + 'not json\n[1, 2]\n{"no_id": 1}\n{"id": null}\n')
    collect_file(issues_file(tmp_path, [7]), stage=5)
    assert [r for r in rows_of() if r["project"] == "q"] == [b, a2]
    assert len(rows_of()) == 3


def test_failed_run_leaves_old_file_byte_equal(tmp_path):
    out = out_path()
    out.parent.mkdir(parents=True)
    data = b'{"id":"q:1:1","project":"q","stage":3}\nnot json\n'
    out.write_bytes(data)
    env = {"PATH": f"{FAKES}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_FAIL": "1"}
    res = run(["collect", "--project", PROJECT, "--repo-slug", "acme/widgets", "--stage", "3"], env)
    assert res.returncode == 1
    assert out.read_bytes() == data


def test_merged_file_keeps_mode_0600_and_rename(tmp_path, monkeypatch):
    write_jsonl(out_path(), [row("q:1:1", "q", 1)])
    os.chmod(out_path(), 0o644)
    renames = []
    real = os.replace
    monkeypatch.setattr(cs.os, "replace", lambda a, b: (renames.append((Path(a), Path(b))), real(a, b))[1])
    cs.write_cases(PROJECT, 1, [])
    assert renames == [(out_path().with_name("retry-cases.jsonl.tmp"), out_path())]
    assert stat.S_IMODE(out_path().stat().st_mode) == 0o600
    assert rows_of() == [row("q:1:1", "q", 1)]
