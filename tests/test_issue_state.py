"""Tests for .claude/hooks/issue_state.py.

All tests use synthetic Issue and Facts objects. No test runs gh, git or
another subprocess, and no test opens a socket (enforced by the autouse
fixture below).
"""

import socket
import subprocess

import pytest

from helpers import HEAD, OLD, cont, facts, issue, launch
from issue_state import (
    AGENT_LANE,
    MARKERS,
    RESUME,
    Call,
    attempt,
    check,
    commits_range,
    current_result,
    first_line,
    is_pending,
    lane,
    launch_comment,
    newest_done,
    parse_issue,
    returns_since_resume,
    verified_sha,
)

PM = Call(role="pm", agent="pm", issue=7)
ENG = Call(role="engineer", agent="software-engineer", issue=7)
FE_ENG = Call(role="engineer", agent="frontend-engineer", issue=7)
QA = Call(role="qa", agent="qa-codex", issue=7)
QA_FALLBACK = Call(role="qa", agent="qa-engineer", issue=7)
CLOSE = Call(role="close", agent="", issue=7)

DONE = "## Engineer: DONE\nCommits: x..y"


@pytest.fixture(autouse=True)
def no_network_no_subprocess(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests of issue_state must not run a subprocess or open a socket")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def groomed(*more):
    return issue(launch("pm"), "## PM: GROOMED", *more)


def done(*more):
    return groomed(launch("engineer"), DONE, *more)


# --- constants ---------------------------------------------------------------


def test_constants_match_spec():
    assert MARKERS == {
        "pm": ("## PM: GROOMED", "## PM: NEEDS OWNER"),
        "engineer": ("## Engineer: DONE", "## Engineer: BLOCKED"),
        "qa": ("## QA: PASS", "## QA: FAIL", "## QA: UNAVAILABLE", "## QA: INVALID"),
    }
    assert RESUME == "## Owner: RESUME"
    assert AGENT_LANE == {"default": "software-engineer", "frontend": "frontend-engineer"}


# --- parse_issue -------------------------------------------------------------


def gh_json(state="OPEN"):
    # Shape of `gh issue view N --json number,state,labels,body,comments`.
    # The timestamps are deliberately out of order: the array order counts.
    return {
        "number": 12,
        "state": state,
        "labels": [
            {"id": "LA_1", "name": "ready", "description": "", "color": "0e8a16"},
            {"id": "LA_2", "name": "bug", "description": "", "color": "d73a4a"},
        ],
        "body": "Lane: default\r\n\r\n## Goal\r\n",
        "comments": [
            {"id": "IC_1", "author": {"login": "someone"}, "authorAssociation": "OWNER",
             "body": "## Launch: pm (attempt 1)\nAgent: pm", "createdAt": "2026-09-26T12:00:00Z",
             "includesCreatedEdit": False, "isMinimized": False, "minimizedReason": "",
             "reactionGroups": [], "url": "https://github.com/o/r/issues/12#issuecomment-1", "viewerDidAuthor": True},
            {"id": "IC_2", "author": {"login": "someone"}, "authorAssociation": "OWNER",
             "body": "## PM: GROOMED\r\nok", "createdAt": "2026-09-26T11:00:00Z",
             "includesCreatedEdit": False, "isMinimized": False, "minimizedReason": "",
             "reactionGroups": [], "url": "https://github.com/o/r/issues/12#issuecomment-2", "viewerDidAuthor": True},
        ],
    }


def test_parse_issue_open():
    iss = parse_issue(gh_json())
    assert iss.number == 12
    assert iss.open is True
    assert iss.labels == frozenset({"ready", "bug"})
    assert iss.body == "Lane: default\r\n\r\n## Goal\r\n"
    assert iss.comments == ("## Launch: pm (attempt 1)\nAgent: pm", "## PM: GROOMED\r\nok")
    assert lane(iss) == "default"
    assert current_result(iss) == (1, "## PM: GROOMED")


def test_parse_issue_closed():
    assert parse_issue(gh_json("CLOSED")).open is False


def test_parse_issue_without_comments_or_labels():
    iss = parse_issue({"number": 3, "state": "OPEN", "labels": [], "body": "", "comments": []})
    assert iss.labels == frozenset() and iss.comments == ()


# --- first line, markers, CRLF -----------------------------------------------


def test_first_line_strips_cr_and_trailing_spaces():
    assert first_line("## QA: PASS\r\nVerified: x") == "## QA: PASS"
    assert first_line("## QA: PASS   \nx") == "## QA: PASS"
    assert first_line("## QA: PASS \r") == "## QA: PASS"


def test_crlf_first_line_matches_but_suffix_does_not():
    assert current_result(issue(launch("pm"), "## PM: GROOMED\r\nx"))[1] == "## PM: GROOMED"
    assert current_result(issue(launch("pm"), "## PM: GROOMED  \nx"))[1] == "## PM: GROOMED"
    assert current_result(issue(launch("qa"), "## QA: PASS (re-check)")) is None


def test_crlf_launch_comment_counts():
    iss = issue("## Launch: pm (attempt 1)\r\nAgent: pm")
    assert is_pending(iss)
    assert current_result(issue("## Launch: pm (attempt 1)  \r\nAgent: pm", "## PM: GROOMED")) == (1, "## PM: GROOMED")


def test_crlf_resume_matches():
    assert current_result(issue(launch("engineer"), "## Owner: RESUME\r\nplease groom again")) == (1, RESUME)
    assert current_result(issue(launch("engineer"), "## Owner: RESUME   ")) == (1, RESUME)
    assert not is_pending(issue(launch("engineer"), "## Owner: RESUME\r\n"))


def test_resume_with_suffix_does_not_match():
    iss = issue(launch("engineer"), "## Owner: RESUME later")
    assert current_result(iss) is None
    assert is_pending(iss)


# --- validity, pending, current result ---------------------------------------


def test_result_without_launch_is_not_valid():
    assert current_result(issue("## PM: GROOMED")) is None


def test_result_after_launch_of_other_role_is_not_valid():
    assert current_result(issue(launch("pm"), "## Engineer: DONE\nCommits: x..y")) is None


def test_result_before_newest_launch_of_its_role_is_not_valid():
    iss = done(launch("qa"), "## QA: FAIL", launch("engineer", 2))
    assert current_result(iss) == (5, "## QA: FAIL")
    assert newest_done(iss) is None


def test_late_result_of_earlier_attempt_is_ignored():
    # QA attempt 1 fails, engineer attempt 2 is done, QA attempt 2 launched;
    # the FAIL of attempt 1 is before the newest QA launch and is not valid.
    iss = done(launch("qa"), "## QA: FAIL", launch("engineer", 2), DONE, launch("qa", 2))
    assert is_pending(iss)
    assert current_result(iss) == (7, "## Engineer: DONE")


def test_newest_launch_without_result_is_pending():
    iss = issue(launch("engineer"), DONE, launch("qa"), "## QA: FAIL", launch("engineer", 2))
    assert is_pending(iss)
    assert check(ENG, facts(iss)).startswith("G1:")


def test_result_of_other_role_does_not_end_pending():
    assert is_pending(issue(launch("engineer"), "## QA: PASS\nVerified: " + HEAD))


def test_no_launch_is_not_pending():
    assert not is_pending(issue())
    assert not is_pending(issue("## PM: GROOMED"))


def test_resume_ends_pending_and_sends_issue_to_pm():
    iss = issue(launch("engineer"), "## Owner: RESUME")
    assert not is_pending(iss)
    assert check(ENG, facts(iss)).startswith("G3:")
    assert check(PM, facts(iss)) is None


def test_current_result_is_resume_when_newer():
    assert current_result(groomed("## Owner: RESUME")) == (2, RESUME)


def test_current_result_is_valid_result_when_newer_than_resume():
    iss = issue("## Owner: RESUME", launch("pm"), "## PM: GROOMED")
    assert current_result(iss) == (2, "## PM: GROOMED")


def test_current_result_is_newest_valid_result_of_any_role():
    assert current_result(done()) == (3, "## Engineer: DONE")


# --- values: Lane, Verified, Commits -----------------------------------------


def test_lane_values_with_crlf_and_trailing_spaces():
    assert lane(issue(body="Lane: default\r\n")) == "default"
    assert lane(issue(body="Lane: default   \n## Goal")) == "default"
    assert lane(issue(body="Lane: frontend")) == "frontend"
    assert lane(issue(body="## Goal\nno lane")) is None
    assert lane(issue(body="Lane: frontend\nLane: default")) == "frontend"


def test_verified_sha_with_crlf_and_trailing_spaces():
    assert verified_sha(f"## QA: PASS\nVerified: {HEAD}") == HEAD
    assert verified_sha(f"## QA: PASS\r\nVerified: {HEAD}\r\n") == HEAD
    assert verified_sha(f"## QA: PASS\nVerified: {HEAD}   \n") == HEAD
    assert verified_sha("## QA: PASS\nTests: none") is None


def test_commits_range_with_crlf_and_trailing_spaces():
    assert commits_range(f"## Engineer: DONE\nCommits: {OLD}..{HEAD}") == (OLD, HEAD)
    assert commits_range(f"## Engineer: DONE\r\nCommits: {OLD}..{HEAD}\r\n") == (OLD, HEAD)
    assert commits_range(f"## Engineer: DONE\nCommits: {OLD}..{HEAD}  \n") == (OLD, HEAD)
    assert commits_range("## Engineer: DONE\nno range") is None
    assert commits_range("## Engineer: DONE\nCommits: onlyone") is None


def test_newest_done_returns_body_of_newest_valid_done():
    iss = done()
    assert newest_done(iss) == DONE
    assert newest_done(issue(DONE)) is None


# --- G1 ----------------------------------------------------------------------


def test_g1_allows_first_pm_launch():
    assert check(PM, facts(issue())) is None


def test_g1_denies_dirty_tree():
    msg = check(PM, facts(issue(), clean=False))
    assert msg.startswith("G1:") and "clean" in msg


def test_g1_denies_closed_issue():
    msg = check(PM, facts(issue(open=False)))
    assert msg.startswith("G1:") and "closed" in msg


@pytest.mark.parametrize("labels", [("ready", "later"), ("ready", "needs-owner"), ()])
def test_g1_denies_labels(labels):
    assert check(PM, facts(issue(labels=labels))).startswith("G1:")


def test_g1_denies_pending_issue_for_every_role():
    iss = issue(launch("pm"))
    for call in (PM, ENG, QA, QA_FALLBACK, CLOSE):
        assert check(call, facts(iss)).startswith("G1:")


def test_g1_denies_close_on_dirty_tree():
    iss = done(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")
    assert check(CLOSE, facts(iss, clean=False)).startswith("G1:")


def test_g1_denies_facts_of_another_issue():
    assert check(Call(role="pm", agent="pm", issue=8), facts(issue())).startswith("G1:")


def test_g1_denies_unknown_role():
    assert check(Call(role="reviewer", agent="reviewer", issue=7), facts(issue())).startswith("G1:")


@pytest.mark.parametrize("agent", ["software-engineer", "", "codex"])
def test_g1_denies_new_qa_call_with_other_agent(agent):
    msg = check(Call(role="qa", agent=agent, issue=7), facts(done()))
    assert msg is not None and msg.startswith("G1:")


def test_g1_denies_new_pm_launch_with_other_agent():
    assert check(Call(role="pm", agent="software-engineer", issue=7), facts(issue())).startswith("G1:")


# --- G2 ----------------------------------------------------------------------


def test_g2_allows_first_launch():
    assert check(PM, facts(issue())) is None


def test_g2_allows_after_blocked():
    assert check(PM, facts(groomed(launch("engineer"), "## Engineer: BLOCKED\nwhy"))) is None


def test_g2_allows_after_resume():
    assert check(PM, facts(done("## Owner: RESUME"))) is None


def test_g2_denies_after_groomed():
    msg = check(PM, facts(groomed()))
    assert msg.startswith("G2:")
    assert "## PM: GROOMED" in msg and "expected" in msg


def test_g2_denies_after_done():
    # A launch comment exists and the current result is DONE.
    assert check(PM, facts(done())).startswith("G2:")


# --- G3 ----------------------------------------------------------------------


def test_g3_allows_after_groomed():
    assert check(ENG, facts(groomed())) is None


def test_g3_allows_after_fail():
    assert check(ENG, facts(done(launch("qa"), "## QA: FAIL"))) is None


def test_g3_denies_after_pass():
    msg = check(ENG, facts(done(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")))
    assert msg.startswith("G3:")
    assert "## QA: PASS" in msg and "expected ## PM: GROOMED or ## QA: FAIL" in msg


def test_g3_denies_without_result():
    assert check(ENG, facts(issue())).startswith("G3:")


def test_g3_denies_agent_not_matching_lane():
    assert check(FE_ENG, facts(groomed())).startswith("G3:")
    iss = issue(launch("pm"), "## PM: GROOMED", body="Lane: frontend\n")
    msg = check(ENG, facts(iss))
    assert msg.startswith("G3:") and "frontend-engineer" in msg


def test_g3_allows_frontend_agent_in_frontend_lane():
    iss = issue(launch("pm"), "## PM: GROOMED", body="Lane: frontend\r\n")
    assert check(FE_ENG, facts(iss)) is None


def test_g3_denies_missing_lane():
    iss = issue(launch("pm"), "## PM: GROOMED", body="## Goal\n")
    msg = check(ENG, facts(iss))
    assert msg.startswith("G3:") and "Lane" in msg


def test_g3_denies_unknown_lane():
    iss = issue(launch("pm"), "## PM: GROOMED", body="Lane: backend\n")
    assert check(ENG, facts(iss)).startswith("G3:")


# --- G4 ----------------------------------------------------------------------


def test_g4_allows_after_done():
    assert check(QA, facts(done())) is None


def test_g4_allows_recheck_after_pass_with_old_sha():
    assert check(QA, facts(done(launch("qa"), f"## QA: PASS\nVerified: {OLD}"))) is None


def test_g4_denies_pass_with_sha_equal_head():
    msg = check(QA, facts(done(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")))
    assert msg.startswith("G4:") and HEAD in msg


def test_g4_denies_done_without_commits_line():
    iss = groomed(launch("engineer"), "## Engineer: DONE\nno range")
    msg = check(QA, facts(iss))
    assert msg.startswith("G4:") and "Commits:" in msg


def test_g4_denies_after_fail():
    assert check(QA, facts(done(launch("qa"), "## QA: FAIL"))).startswith("G4:")


def test_g4_allows_pass_without_verified_as_recheck():
    assert check(QA, facts(done(launch("qa"), "## QA: PASS\nno sha"))) is None


def test_g4_reads_commits_with_crlf():
    iss = groomed(launch("engineer"), f"## Engineer: DONE\r\nCommits: {OLD}..{HEAD}\r\n")
    assert check(QA, facts(iss)) is None


# --- G5 ----------------------------------------------------------------------


def test_g5_allows_fallback_after_unavailable():
    assert check(QA_FALLBACK, facts(done(launch("qa"), "## QA: UNAVAILABLE\ncodex missing"))) is None


def test_g5_denies_fallback_after_done():
    msg = check(QA_FALLBACK, facts(done()))
    assert msg.startswith("G5:") and "## QA: UNAVAILABLE" in msg


def test_g5_denies_fallback_after_fail():
    assert check(QA_FALLBACK, facts(done(launch("qa"), "## QA: FAIL"))).startswith("G5:")


# --- G6 ----------------------------------------------------------------------


def test_g6_needs_full_verified_sha_equal_head():
    iss = issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD[:7]}")
    assert check(CLOSE, facts(iss)).startswith("G6:")
    iss = issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")
    assert check(CLOSE, facts(iss)) is None


def test_g6_denies_old_sha():
    msg = check(CLOSE, facts(done(launch("qa"), f"## QA: PASS\nVerified: {OLD}")))
    assert msg.startswith("G6:") and OLD in msg and HEAD in msg


def test_g6_denies_pass_without_verified():
    assert check(CLOSE, facts(done(launch("qa"), "## QA: PASS\nno sha"))).startswith("G6:")


def test_g6_denies_when_current_result_is_not_pass():
    assert check(CLOSE, facts(done(launch("qa"), f"## QA: FAIL\nVerified: {HEAD}"))).startswith("G6:")
    assert check(CLOSE, facts(done())).startswith("G6:")


def test_g6_reads_verified_with_crlf():
    iss = done(launch("qa"), f"## QA: PASS\r\nVerified: {HEAD}\r\n")
    assert check(CLOSE, facts(iss)) is None


# --- G7 ----------------------------------------------------------------------


def three_fails():
    return (launch("pm"), "## PM: GROOMED",
            launch("engineer"), DONE, launch("qa"), "## QA: FAIL",
            launch("engineer", 2), DONE, launch("qa", 2), "## QA: FAIL",
            launch("engineer", 3), DONE, launch("qa", 3), "## QA: FAIL")


def test_g7_denies_third_return():
    iss = issue(*three_fails())
    assert returns_since_resume(iss) == 3
    msg = check(ENG, facts(iss))
    assert msg.startswith("G7:") and "3" in msg


def test_g7_allows_second_return():
    iss = issue(*three_fails()[:10])
    assert returns_since_resume(iss) == 2
    assert check(ENG, facts(iss)) is None


def test_g7_denies_pm_after_third_return():
    iss = done(launch("qa"), "## QA: FAIL", launch("engineer", 2), "## Engineer: BLOCKED",
               launch("pm", 2), "## PM: GROOMED", launch("engineer", 3), "## Engineer: BLOCKED")
    assert returns_since_resume(iss) == 3
    assert check(PM, facts(iss)).startswith("G7:")


def test_g7_count_starts_after_newest_resume():
    iss = issue(*three_fails(), "## Owner: RESUME")
    assert returns_since_resume(iss) == 0
    assert check(PM, facts(iss)) is None


def test_g7_counts_two_fails_after_one_launch():
    iss = done(launch("qa"), "## QA: FAIL", "## QA: FAIL")
    assert returns_since_resume(iss) == 2


def test_g7_ignores_return_without_launch_of_its_role():
    assert returns_since_resume(issue("## QA: FAIL", launch("engineer"), "## Engineer: BLOCKED")) == 1
    assert returns_since_resume(issue(launch("pm"), "## QA: FAIL")) == 0


def test_g7_ignores_return_markers_with_suffix():
    assert returns_since_resume(done(launch("qa"), "## QA: FAIL (flaky)")) == 0


# --- continuation (spec 5.3) -------------------------------------------------


def test_continued_comment_makes_issue_pending():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1"))
    assert is_pending(iss)
    assert check(ENG, facts(iss)).startswith("G1:")


def test_result_after_continued_comment_is_valid():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1"), "## Engineer: DONE\nCommits: x..z")
    assert not is_pending(iss)
    assert current_result(iss) == (7, "## Engineer: DONE")
    assert newest_done(iss) == "## Engineer: DONE\nCommits: x..z"


def test_continued_comment_makes_older_result_invalid():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1"))
    assert newest_done(iss) is None


def test_continued_comment_counts_for_attempt():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1"), DONE)
    assert attempt(iss, "engineer") == 3
    assert attempt(iss, "qa") == 2
    assert attempt(iss, "pm") == 2
    assert attempt(issue(), "pm") == 1


def test_continued_comment_counts_for_g7():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1"), "## Engineer: BLOCKED")
    assert returns_since_resume(iss) == 2


def test_continued_engineer_call_after_fail_passes_g3_with_any_agent():
    iss = done(launch("qa"), "## QA: FAIL")
    assert check(Call(role="engineer", agent="eng-1", issue=7, continued=True), facts(iss)) is None


def test_continued_engineer_call_still_checks_result():
    iss = done()
    assert check(Call(role="engineer", agent="eng-1", issue=7, continued=True), facts(iss)).startswith("G3:")


def test_new_engineer_launch_with_other_agent_is_denied_by_g3():
    iss = done(launch("qa"), "## QA: FAIL")
    assert check(Call(role="engineer", agent="eng-1", issue=7), facts(iss)).startswith("G3:")


def test_continued_qa_call_runs_g5():
    after_done = done()
    after_unavailable = done(launch("qa"), "## QA: UNAVAILABLE")
    for agent in ("qa-1", "qa-engineer", "qa-codex"):
        call = Call(role="qa", agent=agent, issue=7, continued=True)
        assert check(call, facts(after_done)).startswith("G5:")
        assert check(call, facts(after_unavailable)) is None


def test_continued_calls_run_g7():
    iss = issue(*three_fails())
    assert check(Call(role="engineer", agent="eng-1", issue=7, continued=True), facts(iss)).startswith("G7:")


# --- stop results (spec 5.5) -------------------------------------------------


STOP_CALLS = (
    PM, ENG, FE_ENG, QA, QA_FALLBACK, CLOSE,
    Call(role="engineer", agent="eng-1", issue=7, continued=True),
    Call(role="qa", agent="qa-1", issue=7, continued=True),
)


@pytest.mark.parametrize("call", STOP_CALLS)
def test_needs_owner_denies_every_call(call):
    iss = issue(launch("pm"), "## PM: NEEDS OWNER\nquestion")
    assert current_result(iss) == (1, "## PM: NEEDS OWNER")
    msg = check(call, facts(iss))
    assert msg is not None and "## PM: NEEDS OWNER" in msg


@pytest.mark.parametrize("call", STOP_CALLS)
def test_invalid_denies_every_call(call):
    iss = done(launch("qa"), f"## QA: INVALID\nVerified: {HEAD}")
    assert current_result(iss) == (5, "## QA: INVALID")
    msg = check(call, facts(iss))
    assert msg is not None and "## QA: INVALID" in msg


# --- launch_comment round trip -----------------------------------------------


def test_launch_comment_text():
    assert launch_comment(ENG, 3) == "## Launch: engineer (attempt 3)\nAgent: software-engineer"
    call = Call(role="engineer", agent="eng-1", issue=7, continued=True)
    assert launch_comment(call, 2) == "## Launch: engineer (continued, round 2)\nAgent: eng-1"


@pytest.mark.parametrize("call", [PM, ENG, QA, QA_FALLBACK,
                                  Call(role="engineer", agent="eng-1", issue=7, continued=True)])
def test_launch_comment_round_trip(call):
    before = groomed()
    n = attempt(before, call.role)
    after = issue(*before.comments, launch_comment(call, n))
    assert is_pending(after)
    assert attempt(after, call.role) == n + 1


# --- deny messages -----------------------------------------------------------


def test_deny_messages_start_with_check_id_and_name_expectation():
    cases = [
        (PM, facts(issue(), clean=False), "G1:"),
        (PM, facts(groomed()), "G2:"),
        (ENG, facts(issue()), "G3:"),
        (QA, facts(groomed()), "G4:"),
        (QA_FALLBACK, facts(groomed()), "G5:"),
        (CLOSE, facts(groomed()), "G6:"),
        (ENG, facts(issue(*three_fails())), "G7:"),
    ]
    for call, f, gid in cases:
        msg = check(call, f)
        assert msg.startswith(gid), msg
        assert "expected" in msg, msg
