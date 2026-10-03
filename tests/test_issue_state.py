"""Tests for .claude/hooks/issue_state.py.

All tests use synthetic Issue and Facts objects. No test runs gh, git or
another subprocess, and no test opens a socket (enforced by the autouse
fixture below).
"""

import re
import socket
import subprocess

import pytest

from helpers import HEAD, OLD, cont, facts, issue, launch
from issue_state import (
    AGENT_LANE,
    Blocker,
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
    parse_blockers,
    parse_issue,
    parse_open_blocker_count,
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
        "pm": ("## PM: GROOMED", "## PM: NEEDS OWNER", "## PM: WAITING"),
        "engineer": ("## Engineer: DONE", "## Engineer: BLOCKED"),
        "qa": ("## QA: PASS", "## QA: FAIL", "## QA: UNAVAILABLE", "## QA: INVALID",
               "## QA: UNVERIFIABLE"),
        "planner": ("## Planner: STAGE REVIEW",),
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


def _without(key):
    data = gh_json()
    del data[key]
    return data


def _with(key, value):
    return {**gh_json(), key: value}


@pytest.mark.parametrize("data", [
    _without("comments"),
    _with("comments", None),
    _with("comments", {"body": "## PM: GROOMED"}),
    _with("comments", "## PM: GROOMED"),
    _with("comments", 3),
], ids=["missing", "null", "object", "string", "number"])
def test_parse_issue_rejects_missing_or_non_list_comments(data):
    with pytest.raises(ValueError):
        parse_issue(data)


@pytest.mark.parametrize("comment", [
    "## PM: GROOMED", None, 5, ["## PM: GROOMED"],
    {"id": "IC_1"}, {"body": None}, {"body": 5}, {"body": ["x"]},
], ids=["string", "null", "number", "list", "no-body", "body-null", "body-number", "body-list"])
def test_parse_issue_rejects_bad_comment_elements(comment):
    data = gh_json()
    data["comments"] = [data["comments"][0], comment]
    with pytest.raises(ValueError):
        parse_issue(data)


def test_parse_issue_with_empty_comment_list():
    iss = parse_issue(_with("comments", []))
    assert iss.comments == () and iss.number == 12


# --- only the repo owner's comments count (#70) ------------------------------


def gh_issue(*comments, number=7, labels=("ready",), body="Lane: default\n"):
    """A `gh issue view --json` dict. A comment is a body (written by the owner) or a
    (body, authorAssociation) pair."""
    items = [{"body": c, "authorAssociation": "OWNER"} if isinstance(c, str)
             else {"body": c[0], "authorAssociation": c[1]} for c in comments]
    return {"number": number, "state": "OPEN", "labels": [{"name": n} for n in labels],
            "body": body, "comments": items}


def stranger(body, association="NONE"):
    return (body, association)


def test_parse_issue_keeps_only_owner_comments_in_order():
    data = gh_issue("owner 1", stranger("none"), "owner 2", stranger("contributor", "CONTRIBUTOR"),
                    stranger("collaborator", "COLLABORATOR"), "owner 3", stranger("member", "MEMBER"))
    assert parse_issue(data).comments == ("owner 1", "owner 2", "owner 3")


@pytest.mark.parametrize("association", ["owner", "Owner", " OWNER", ""])
def test_parse_issue_association_must_be_exactly_owner(association):
    assert parse_issue(gh_issue("kept", stranger("dropped", association))).comments == ("kept",)


@pytest.mark.parametrize("comment", [
    {"body": "## PM: GROOMED"}, {"body": "## PM: GROOMED", "authorAssociation": None},
    {"body": "## PM: GROOMED", "authorAssociation": 1},
    {"body": "## PM: GROOMED", "authorAssociation": ["OWNER"]},
], ids=["missing", "null", "number", "list"])
def test_parse_issue_rejects_missing_or_non_string_author_association(comment):
    data = gh_issue("## Launch: pm (attempt 1)\nAgent: pm")
    data["comments"].append(comment)
    with pytest.raises(ValueError) as e:
        parse_issue(data)
    assert "authorAssociation" in str(e.value) and "comment 1" in str(e.value)


def test_parse_issue_rejects_bad_author_data_of_a_later_comment_too():
    data = gh_issue("x", "y")
    del data["comments"][1]["authorAssociation"]
    with pytest.raises(ValueError, match=r"comment 1 .*authorAssociation"):
        parse_issue(data)


def _three_owner_returns():
    return (launch("pm", 1), "## PM: GROOMED", launch("engineer", 1), "## Engineer: BLOCKED",
            launch("pm", 2), "## PM: GROOMED", launch("engineer", 2), "## Engineer: BLOCKED",
            launch("pm", 3), "## PM: GROOMED", launch("engineer", 3), "## Engineer: BLOCKED")


def test_stranger_resume_does_not_resume_needs_owner():
    base = (launch("pm"), "## PM: NEEDS OWNER")
    assert check(PM, facts(parse_issue(gh_issue(*base, stranger(RESUME))))).startswith("G2:")
    assert check(PM, facts(parse_issue(gh_issue(*base, RESUME)))) is None  # control: the owner's RESUME


def test_stranger_resume_does_not_reset_the_return_count():
    iss = parse_issue(gh_issue(*_three_owner_returns(), stranger(RESUME, "COLLABORATOR")))
    assert check(PM, facts(iss)).startswith("G7:")
    assert check(PM, facts(parse_issue(gh_issue(*_three_owner_returns(), RESUME)))) is None  # control


@pytest.mark.parametrize("stranger_comments", [
    [f"## QA: PASS\nVerified: {HEAD}"],
    [launch("qa"), f"## QA: PASS\nVerified: {HEAD}"],
], ids=["pass", "receipt-and-pass"])
def test_stranger_pass_does_not_allow_close(stranger_comments):
    owner = (launch("pm"), "## PM: GROOMED", launch("engineer"), DONE)
    iss = parse_issue(gh_issue(*owner, *(stranger(c) for c in stranger_comments)))
    assert check(CLOSE, facts(iss)).startswith("G6:")
    if len(stranger_comments) == 2:  # control: the same comments by the owner allow the close
        assert check(CLOSE, facts(parse_issue(gh_issue(*owner, *stranger_comments)))) is None


def test_stranger_receipt_does_not_count_as_a_launch():
    iss = parse_issue(gh_issue(stranger(launch("pm"))))
    assert check(PM, facts(iss)) is None
    assert attempt(iss, "pm") == 1
    assert launch_comment(PM, attempt(iss, "pm")).startswith("## Launch: pm (attempt 1)")


def test_stranger_not_started_does_not_void_owner_receipt():
    x = "0123456789ab"
    not_started = f"## Launch not started: pm (attempt 1)\nCall: {x}\nReason: Classifier unavailable"
    iss = parse_issue(gh_issue(launch("pm", call=x), stranger(not_started, "CONTRIBUTOR")))
    assert is_pending(iss)
    assert check(PM, facts(iss)).startswith("G1:")
    assert not is_pending(parse_issue(gh_issue(launch("pm", call=x), not_started)))  # control


def test_stranger_done_does_not_end_the_pending_engineer_launch():
    iss = parse_issue(gh_issue(launch("pm"), "## PM: GROOMED", launch("engineer"),
                               stranger(DONE), "note"))
    assert is_pending(iss)
    assert check(PM, facts(iss)).startswith("G1:")
    assert newest_done(iss) is None


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
    assert lane(issue(body="Lane: frontend\nLane: frontend")) == "frontend"


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


# Fenced examples and conflicting lines. Each value function gets the same text shape.

VALUE_CASES = [
    # (function, line with value A, line with value B, value A, value B)
    (lambda t: lane(issue(body=t)), "Lane: default", "Lane: frontend", "default", "frontend"),
    (verified_sha, f"Verified: {OLD}", f"Verified: {HEAD}", OLD, HEAD),
    (commits_range, f"Commits: {OLD}..{HEAD}", f"Commits: {HEAD}..{OLD}", (OLD, HEAD), (HEAD, OLD)),
]
VALUE_IDS = ["lane", "verified", "commits"]


def cases(test):
    return pytest.mark.parametrize("value, a_line, b_line, a, b", VALUE_CASES, ids=VALUE_IDS)(test)


@cases
def test_value_in_backtick_fence_is_ignored(value, a_line, b_line, a, b):
    assert value(f"## X\n```\n{b_line}\n```\n{a_line}\n") == a
    assert value(f"## X\n{a_line}\n```\n{b_line}\n```\n") == a


@cases
def test_value_in_tilde_fence_is_ignored(value, a_line, b_line, a, b):
    assert value(f"## X\n~~~\n{b_line}\n~~~\n{a_line}\n") == a
    assert value(f"## X\n~~~~\n{b_line}\n~~~~~\n{a_line}\n") == a


@cases
def test_fence_closes_only_on_same_char_and_at_least_same_length(value, a_line, b_line, a, b):
    # 4 backticks are not closed by 3; the value line after ``` is still inside.
    assert value(f"````\n```\n{b_line}\n````\n{a_line}") == a
    # ~~~ does not close a backtick fence, ``` does not close a tilde fence.
    assert value(f"```\n~~~\n{b_line}\n```\n{a_line}") == a
    assert value(f"~~~\n```\n{b_line}\n~~~\n{a_line}") == a
    # a closing line with text after the run does not close.
    assert value(f"```\n```x\n{b_line}\n```\n{a_line}") == a


@cases
def test_fence_with_info_string_or_indent_is_recognized(value, a_line, b_line, a, b):
    assert value(f"```markdown\n{b_line}\n```\n{a_line}") == a
    assert value(f"~~~ text\n{b_line}\n~~~\n{a_line}") == a
    for indent in (" ", "  ", "   "):
        assert value(f"{indent}```\n{b_line}\n{indent}```\n{a_line}") == a


@cases
def test_four_space_indent_is_not_a_fence(value, a_line, b_line, a, b):
    # An indented code block, not a fence; the values stay readable and the same.
    assert value(f"    ```\n{a_line}\n    ```\n{a_line}") == a


@cases
def test_fence_lines_with_crlf_are_recognized(value, a_line, b_line, a, b):
    assert value(f"## X\r\n```\r\n{b_line}\r\n```\r\n{a_line}\r\n") == a
    assert value(f"## X\r\n```markdown\r\n{b_line}\r\n``` \t\r\n{a_line}\r\n") == a


@cases
def test_unclosed_fence_hides_everything_after_it(value, a_line, b_line, a, b):
    assert value(f"{a_line}\n```\n{b_line}\n") == a
    assert value(f"{a_line}\n```\n{b_line}\n{b_line}\n") == a
    assert value(f"## X\n```\n{a_line}\n") is None


@cases
def test_only_fenced_value_gives_none(value, a_line, b_line, a, b):
    assert value(f"## X\n```\n{a_line}\n```\n") is None
    assert value(f"## X\n~~~\n{a_line}\n~~~\nmore text\n") is None


@cases
def test_same_value_twice_gives_that_value(value, a_line, b_line, a, b):
    assert value(f"{a_line}\n## X\n{a_line}\n") == a
    assert value(f"{a_line}\r\n{a_line}   \r\n") == a


@cases
def test_different_values_give_none(value, a_line, b_line, a, b):
    assert value(f"{a_line}\n{b_line}\n") is None
    assert value(f"{b_line}\n## X\n{a_line}\n") is None


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


def test_g3_denies_conflicting_lanes_as_missing():
    iss = issue(launch("pm"), "## PM: GROOMED", body="Lane: default\n## Goal\nLane: frontend\n")
    msg = check(ENG, facts(iss))
    assert msg.startswith("G3: issue body has no Lane line")


def test_g3_denies_lane_only_inside_fence():
    iss = issue(launch("pm"), "## PM: GROOMED", body="## Goal\n```markdown\nLane: default\n```\n")
    msg = check(ENG, facts(iss))
    assert msg.startswith("G3: issue body has no Lane line")


def test_g3_allows_lane_outside_fence_with_other_lane_in_fence():
    iss = issue(launch("pm"), "## PM: GROOMED", body="Lane: default\n```\nLane: frontend\n```\n")
    assert check(ENG, facts(iss)) is None


def test_g3_allows_lane_with_permissions_line():
    body = (
        "Lane: default\n"
        "<!-- default, or frontend -->\n"
        "Source: https://example.com/issue/1\n"
        "Permissions: create issues - set; close issues\n"
        "<!-- list each permission beyond the defaults -->\n\n"
        "## Goal\n"
    )
    iss = issue(launch("pm"), "## PM: GROOMED", body=body)
    assert lane(iss) == "default"
    assert check(ENG, facts(iss)) is None
    iss = issue(launch("pm"), "## PM: GROOMED", body=body.replace("default\n", "frontend\n", 1))
    assert check(FE_ENG, facts(iss)) is None


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


def test_g4_denies_done_with_conflicting_commits_lines():
    iss = groomed(launch("engineer"), f"## Engineer: DONE\nCommits: {OLD}..{HEAD}\nCommits: {HEAD}..{OLD}")
    msg = check(QA, facts(iss))
    assert msg.startswith("G4: the newest ## Engineer: DONE comment has no Commits: line")


def test_g4_ignores_fenced_commits_line():
    iss = groomed(launch("engineer"), f"## Engineer: DONE\n```\nCommits: {OLD}..{HEAD}\n```\n")
    assert check(QA, facts(iss)).startswith("G4: the newest ## Engineer: DONE comment has no Commits: line")


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


def test_g6_denies_fenced_head_before_old_footer():
    body = f"## QA: PASS\nExample:\n```\nVerified: {HEAD}\n```\nVerified: {OLD}\n"
    msg = check(CLOSE, facts(done(launch("qa"), body)))
    assert msg.startswith("G6:") and f"verified SHA is {OLD}" in msg


def test_g6_denies_two_unfenced_verified_lines():
    for body in (f"## QA: PASS\nVerified: {HEAD}\nVerified: {OLD}",
                 f"## QA: PASS\nVerified: {OLD}\nVerified: {HEAD}"):
        msg = check(CLOSE, facts(done(launch("qa"), body)))
        assert msg.startswith("G6: verified SHA is missing")


def test_g6_allows_verified_repeated_with_same_sha():
    body = f"## QA: PASS\nVerified: {HEAD}\nfooter\nVerified: {HEAD}"
    assert check(CLOSE, facts(done(launch("qa"), body))) is None


def test_unclosed_fence_in_one_comment_does_not_hide_the_next_comment():
    iss = done(launch("qa"), "## QA: FAIL\n```\nunclosed", launch("engineer", 2),
               f"## Engineer: DONE\nCommits: {OLD}..{HEAD}", launch("qa", 2), f"## QA: PASS\nVerified: {HEAD}")
    assert check(CLOSE, facts(iss)) is None


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


# --- continuation (docs/specs/agent-graph-kit.md#continuation) ---------------------


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


# --- stop results (docs/specs/agent-graph-kit.md#result-markers) -----------------


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


# --- not-started receipts (issue #48) ------------------------------------------

from helpers import not_started  # noqa: E402
from issue_state import call_hash, not_started_comment  # noqa: E402

X = "0123456789ab"
Y = "ba9876543210"


def test_call_hash_is_first_12_hex_of_sha256():
    import hashlib
    assert call_hash("toolu_synthetic_1") == hashlib.sha256(b"toolu_synthetic_1").hexdigest()[:12]
    assert len(call_hash("toolu_synthetic_1")) == 12


def test_launch_comment_with_call_line():
    assert launch_comment(PM, 1, X) == f"## Launch: pm (attempt 1)\nAgent: pm\nCall: {X}"
    call = Call(role="engineer", agent="eng-1", issue=7, continued=True)
    assert launch_comment(call, 2, X) == f"## Launch: engineer (continued, round 2)\nAgent: eng-1\nCall: {X}"
    assert launch_comment(PM, 1, None) == "## Launch: pm (attempt 1)\nAgent: pm"


def test_43_case_not_started_receipt_is_not_pending():
    iss = issue(launch("pm", call=X), not_started("pm", 1, X))
    assert not is_pending(iss)
    assert check(PM, facts(iss)) is None
    assert attempt(iss, "pm") == 2


@pytest.mark.parametrize("comments", [
    (launch("pm", call=X),),  # no not-started comment
    (launch("pm", call=X), "## PM: working, then stopped"),  # #39 case: started, ended without a result
])
def test_started_receipt_without_result_is_still_pending(comments):
    iss = issue(*comments)
    assert is_pending(iss)
    assert check(PM, facts(iss)).startswith("G1: issue #7 is pending")


def test_not_started_pm_after_blocked_keeps_blocked_as_current():
    iss = issue(launch("pm"), "## PM: GROOMED", launch("engineer"), "## Engineer: BLOCKED\nwhy",
                launch("pm", 2, call=X), not_started("pm", 2, X))
    assert current_result(iss) == (3, "## Engineer: BLOCKED")
    assert check(PM, facts(iss)) is None
    assert returns_since_resume(iss) == 1


def test_not_started_engineer_after_fail_adds_no_return():
    iss = done(launch("qa"), "## QA: FAIL", launch("engineer", 2, call=X), not_started("engineer", 2, X))
    assert check(ENG, facts(iss)) is None
    assert returns_since_resume(iss) == 1
    assert attempt(iss, "engineer") == 3


def test_not_started_comment_is_not_a_result_receipt_or_resume():
    line = not_started("pm", 1, X)
    iss = issue(line)
    assert not is_pending(iss) and current_result(iss) is None
    assert attempt(iss, "pm") == 1
    assert check(PM, facts(iss)) is None  # G2: no launch comment yet


@pytest.mark.parametrize("marker", [
    not_started("pm", 1, Y),  # other Call value
    not_started("engineer", 1, X),  # other role
    not_started("pm", 2, X),  # other attempt number
    not_started("pm", 1, X, continued=True),  # continuation instead of attempt
])
def test_not_started_comment_that_matches_no_receipt_has_no_effect(marker):
    iss = issue(launch("pm", call=X), marker)
    assert is_pending(iss)


def test_not_started_comment_before_the_receipt_has_no_effect():
    iss = issue(not_started("pm", 1, X), launch("pm", call=X))
    assert is_pending(iss)


def test_receipt_without_call_line_cannot_be_not_started():
    iss = issue(launch("pm"), not_started("pm", 1, X))
    assert is_pending(iss)


def test_not_started_continuation():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1", call=X),
               not_started("engineer", 2, X, continued=True))
    assert not is_pending(iss)
    assert current_result(iss)[1] == "## QA: FAIL"


# criterion 7: two not-started launches in a row


def two_not_started(*between):
    return issue(launch("pm", 1, call=X), not_started("pm", 1, X), *between,
                 launch("pm", 2, call=Y), not_started("pm", 2, Y))


def test_g1_denies_after_two_not_started_launches():
    msg = check(PM, facts(two_not_started()))
    assert msg.startswith("G1: issue #7: the last 2 launches did not start")
    assert RESUME in msg


@pytest.mark.parametrize("call", [PM, ENG, QA, QA_FALLBACK, Call(role="engineer", agent="e", issue=7, continued=True)])
def test_g1_two_not_started_denies_every_launch(call):
    assert check(call, facts(two_not_started())).startswith("G1: issue #7: the last 2 launches did not start")


def test_g1_two_not_started_does_not_deny_close():
    msg = check(CLOSE, facts(two_not_started()))
    assert not msg.startswith("G1:")


def test_g1_allows_after_one_not_started_launch():
    assert check(PM, facts(issue(launch("pm", 1, call=X), not_started("pm", 1, X)))) is None


def test_g1_allows_two_not_started_with_a_result_between():
    iss = issue(launch("pm", 1, call=X), not_started("pm", 1, X), "## Engineer: BLOCKED",
                launch("pm", 2, call=Y), not_started("pm", 2, Y))
    assert check(PM, facts(iss)) is None


def test_g1_allows_two_not_started_followed_by_resume():
    iss = issue(*two_not_started().comments, RESUME)
    assert check(PM, facts(iss)) is None


def test_g1_two_newest_receipts_must_both_be_not_started():
    iss = issue(launch("pm", 1, call=X), not_started("pm", 1, X), "## PM: GROOMED",
                launch("engineer", 1, call=Y), "## Engineer: BLOCKED",
                launch("pm", 2, call="c0ffee000000"), not_started("pm", 2, "c0ffee000000"))
    assert check(PM, facts(iss)) is None


# not_started_comment (the pure decision of not_started.py)


def test_not_started_comment_for_matching_receipt():
    iss = issue(launch("pm", call=X))
    assert not_started_comment(iss, X, "Auto mode could not evaluate this action and is blocking it for safety\nmore") == (
        f"## Launch not started: pm (attempt 1)\nCall: {X}\n"
        "Reason: Auto mode could not evaluate this action and is blocking it for safety")


def test_not_started_comment_for_continuation():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1", call=X))
    assert not_started_comment(iss, X, "Classifier unavailable").startswith(
        f"## Launch not started: engineer (continued, round 2)\nCall: {X}\n")


def test_not_started_comment_cuts_reason_to_200():
    iss = issue(launch("pm", call=X))
    assert not_started_comment(iss, X, "r" * 300).endswith("Reason: " + "r" * 200)


@pytest.mark.parametrize("comments", [
    (launch("pm", call=Y),),  # other Call
    (launch("pm"),),  # no Call line
    (launch("pm", call=X), launch("engineer", call=Y)),  # not the newest receipt
    (launch("pm", call=X), "## PM: GROOMED"),  # valid result
    (launch("pm", call=X), RESUME),  # resume after it
    (launch("pm", call=X), not_started("pm", 1, X)),  # already marked
    (),  # no receipt
])
def test_not_started_comment_none(comments):
    assert not_started_comment(issue(*comments), X, "Classifier unavailable") is None


# --- QA: UNVERIFIABLE (issue #55) ----------------------------------------------

UNVERIFIABLE = "## QA: UNVERIFIABLE"
INVALID = "## QA: INVALID"


def unverifiable(*more):
    return done(launch("qa"), f"{UNVERIFIABLE}\nReason: criterion 2 could not be verified", *more)


def test_unverifiable_is_a_qa_result_marker_that_ends_pending():
    before = done(launch("qa"))
    assert is_pending(before)
    iss = unverifiable()
    assert not is_pending(iss)
    assert current_result(iss) == (5, UNVERIFIABLE)


def test_not_started_comment_none_after_unverifiable():
    iss = done(launch("qa", call=X), f"{UNVERIFIABLE}\nReason: x")
    assert not_started_comment(iss, X, "Classifier unavailable") is None


def test_g2_allows_pm_after_unverifiable():
    assert check(PM, facts(unverifiable())) is None


@pytest.mark.parametrize("call, gid", [
    (ENG, "G3:"),
    (QA, "G4:"),
    (QA_FALLBACK, "G5:"),
    (CLOSE, "G6:"),
])
def test_unverifiable_denies_engineer_qa_fallback_and_close(call, gid):
    msg = check(call, facts(unverifiable()))
    assert msg is not None and msg.startswith(gid), msg
    assert f"current result is {UNVERIFIABLE}" in msg, msg


def test_g2_deny_message_names_unverifiable_as_allowed():
    msg = check(PM, facts(groomed()))
    assert msg.startswith("G2:") and UNVERIFIABLE in msg


def three_unverifiable():
    return (launch("pm"), "## PM: GROOMED",
            launch("engineer"), DONE, launch("qa"), UNVERIFIABLE,
            launch("pm", 2), "## PM: GROOMED", launch("engineer", 2), DONE, launch("qa", 2), UNVERIFIABLE,
            launch("pm", 3), "## PM: GROOMED", launch("engineer", 3), DONE, launch("qa", 3), UNVERIFIABLE)


def test_g7_three_unverifiable_deny_pm_and_engineer():
    iss = issue(*three_unverifiable())
    assert returns_since_resume(iss) == 3
    msg = check(PM, facts(iss))
    assert msg.startswith("G7:") and UNVERIFIABLE in msg, msg
    # the engineer is denied too; G3 comes first while UNVERIFIABLE is the current result
    assert check(ENG, facts(iss)) is not None
    # after a later GROOMED only G7 stops the engineer
    regroomed = issue(*three_unverifiable(), launch("pm", 4), "## PM: GROOMED")
    msg = check(ENG, facts(regroomed))
    assert msg.startswith("G7:") and UNVERIFIABLE in msg, msg


def test_g7_two_unverifiable_allow_pm():
    iss = issue(*three_unverifiable()[:12])
    assert returns_since_resume(iss) == 2
    assert check(PM, facts(iss)) is None


def test_g7_unverifiable_count_starts_after_newest_resume():
    iss = issue(*three_unverifiable(), RESUME)
    assert returns_since_resume(iss) == 0
    assert check(PM, facts(iss)) is None


def test_g7_mix_of_fail_unverifiable_and_blocked_is_three_returns():
    iss = done(launch("qa"), "## QA: FAIL",
               launch("engineer", 2), DONE, launch("qa", 2), UNVERIFIABLE,
               launch("pm", 2), "## PM: GROOMED", launch("engineer", 3), "## Engineer: BLOCKED")
    assert returns_since_resume(iss) == 3
    assert check(PM, facts(iss)).startswith("G7:")


def test_g7_ignores_unverifiable_without_qa_launch():
    assert returns_since_resume(issue(launch("pm"), UNVERIFIABLE)) == 0


@pytest.mark.parametrize("call, gid", [
    (PM, "G2:"),
    (ENG, "G3:"),
    (QA, "G4:"),
    (QA_FALLBACK, "G5:"),
])
def test_invalid_still_escalates(call, gid):
    iss = done(launch("qa"), f"{INVALID}\nReason: retries used up")
    msg = check(call, facts(iss))
    assert msg is not None and msg.startswith(gid), msg
    assert INVALID in msg


def test_invalid_is_not_a_return():
    iss = done(launch("qa"), INVALID, launch("qa", 2), INVALID, launch("qa", 3), INVALID)
    assert returns_since_resume(iss) == 0


# --- PM: WAITING and native blockers (issues #56, #64) ------------------------------


WAITING = "## PM: WAITING"
REPO = "octo/kit"


def b(number, state="closed", repo=REPO):
    return Blocker(repo=repo, number=number, state=state)


def waiting(*lines):
    """Issue #7: groomed, engineer BLOCKED, then a PM launch with a WAITING result."""
    body = "\n".join((WAITING, "The criterion needs octo/kit#3 first.", *lines))
    return groomed(launch("engineer"), "## Engineer: BLOCKED\nwhy", launch("pm", 2), body)


def test_waiting_is_a_pm_result_and_not_pending():
    iss = issue(launch("pm"), WAITING)
    assert current_result(iss) == (1, WAITING)
    assert not is_pending(iss)


# the blocker reads, parsed (the guard runs gh, issue_state only reads the text)


def test_parse_blockers_reads_one_object_per_line():
    text = ('{"number":3,"repo":"octo/kit","state":"open"}\n'
            '{"number":12,"repo":"other/lib","state":"closed"}\n')
    assert parse_blockers(text) == (b(3, "open"), b(12, "closed", "other/lib"))


def test_parse_blockers_of_no_blocker_is_empty():
    assert parse_blockers("") == ()
    assert parse_blockers("\n") == ()


def test_parse_blockers_counts_every_item_of_every_page():
    # gh --paginate --jq prints the items of all pages, one per line; 31 items are more than one page (30)
    text = "".join(f'{{"number":{n},"repo":"octo/kit","state":"closed"}}\n' for n in range(1, 32))
    assert len(parse_blockers(text)) == 31


@pytest.mark.parametrize("text", [
    "not json", "[]", '{"number":3,"repo":"octo/kit"}', '{"number":"3","repo":"octo/kit","state":"open"}',
    '{"number":3,"repo":"octo/kit","state":"OPEN"}', '{"number":3,"repo":5,"state":"open"}',
    '{"number":true,"repo":"octo/kit","state":"open"}', '{"number":0,"repo":"octo/kit","state":"open"}',
    '{"number":3,"repo":"","state":"open"}', '5',
])
def test_parse_blockers_rejects_output_it_cannot_read(text):
    with pytest.raises(ValueError):
        parse_blockers(text)


def test_parse_open_blocker_count():
    assert parse_open_blocker_count("0\n") == 0
    assert parse_open_blocker_count("2") == 2


@pytest.mark.parametrize("text", ["", "null", "-1", "x", "1.5", "true", '"2"', "1\n2"])
def test_parse_open_blocker_count_rejects_output_it_cannot_read(text):
    with pytest.raises(ValueError):
        parse_open_blocker_count(text)


# G1: an open blocker denies every role launch


ROLE_CALLS = [PM, ENG, FE_ENG, QA, QA_FALLBACK, Call(role="engineer", agent="a1", issue=7, continued=True)]


@pytest.mark.parametrize("call", ROLE_CALLS)
def test_g1_allows_no_blocker(call):
    msg = check(call, facts(issue(), blockers=(), open_blockers=0))
    assert msg is None or not msg.startswith("G1:"), msg


def test_g1_allows_a_pm_launch_with_only_closed_blockers():
    assert check(PM, facts(issue(), blockers=(b(3), b(4)), open_blockers=0)) is None


@pytest.mark.parametrize("call", ROLE_CALLS)
def test_g1_denies_one_open_blocker_and_names_it(call):
    msg = check(call, facts(issue(), blockers=(b(3, "open"),), open_blockers=1))
    assert msg.startswith("G1:") and "octo/kit#3" in msg and "open blocker" in msg, msg


def test_g1_denies_several_blockers_one_open_and_names_only_the_open_one():
    blockers = (b(3), b(5, "open"), b(9, "closed", "other/lib"))
    msg = check(PM, facts(issue(), blockers=blockers, open_blockers=1))
    assert msg.startswith("G1:") and "octo/kit#5" in msg, msg
    assert "octo/kit#3" not in msg and "other/lib#9" not in msg, msg


def test_g1_names_several_open_blockers_in_any_order():
    for blockers in ((b(5, "open"), b(2, "open", "other/lib")), (b(2, "open", "other/lib"), b(5, "open"))):
        msg = check(PM, facts(issue(), blockers=blockers, open_blockers=2))
        assert msg.startswith("G1:") and "octo/kit#5" in msg and "other/lib#2" in msg, msg


def test_g1_allows_a_closed_blocker_in_another_repo():
    assert check(PM, facts(issue(), blockers=(b(8, "closed", "other/lib"),), open_blockers=0)) is None


def test_g1_denies_an_open_blocker_in_another_repo():
    msg = check(PM, facts(issue(), blockers=(b(8, "open", "other/lib"),), open_blockers=1))
    assert msg.startswith("G1:") and "other/lib#8" in msg, msg


def test_g1_denies_an_open_blocker_on_the_second_page():
    blockers = tuple(b(n) for n in range(1, 31)) + (b(31, "open"),)
    msg = check(PM, facts(issue(), blockers=blockers, open_blockers=1))
    assert msg.startswith("G1:") and "octo/kit#31" in msg, msg


@pytest.mark.parametrize("blockers", [(), (b(3),), (b(3, "open"),)])
def test_g1_denies_a_count_greater_than_the_open_entries(blockers):
    """The #95 report: a hidden blocker is not observed, so the list may be incomplete."""
    count = sum(x.state == "open" for x in blockers) + 1
    msg = check(PM, facts(issue(), blockers=blockers, open_blockers=count))
    assert msg.startswith("G1:") and "count" in msg and "cannot read" in msg, msg


def test_g1_count_lower_than_the_open_entries_still_names_the_open_entry():
    # a count below the open entries is no hidden blocker; the open entry itself denies
    msg = check(PM, facts(issue(), blockers=(b(3, "open"),), open_blockers=0))
    assert msg.startswith("G1:") and "octo/kit#3" in msg and "cannot read" not in msg, msg


@pytest.mark.parametrize("missing", [{"blockers": None}, {"open_blockers": None}])
def test_g1_denies_role_launch_when_a_blocker_read_is_missing(missing):
    kw = {"blockers": (), "open_blockers": 0, **missing}
    msg = check(PM, facts(issue(), **kw))
    assert msg.startswith("G1:") and "not read" in msg, msg


def test_close_does_not_read_blockers():
    passed = issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")
    assert check(CLOSE, facts(passed, blockers=None, open_blockers=None)) is None
    assert check(CLOSE, facts(passed, blockers=(b(3, "open"),), open_blockers=1)) is None


@pytest.mark.parametrize("call", [PM, ENG, QA, QA_FALLBACK, CLOSE])
def test_label_waiting_is_no_longer_checked(call):
    iss = issue(labels=("ready", "waiting"))
    msg = check(call, facts(iss))
    assert msg is None or "waiting" not in msg, msg


def test_g1_does_not_mention_the_label_waiting_or_the_waiting_on_line():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "issue_state.py").read_text()
    assert '"waiting"' not in text and "Waiting on:" not in text


# G2 after ## PM: WAITING


def test_g2_allows_pm_after_waiting_with_closed_blockers():
    for blockers in ((b(3),), (b(3), b(4, "closed", "other/lib"))):
        assert check(PM, facts(waiting(), blockers=blockers, open_blockers=0)) is None
    cont_pm = Call(role="pm", agent="a1", issue=7, continued=True)
    assert check(cont_pm, facts(waiting(), blockers=(b(3),), open_blockers=0)) is None


def test_g2_denies_waiting_with_an_empty_blocker_list():
    msg = check(PM, facts(waiting(), blockers=(), open_blockers=0))
    assert msg.startswith("G2:") and WAITING in msg and "no blocker" in msg, msg


def test_g2_ignores_a_waiting_on_line():
    msg = check(PM, facts(waiting("Waiting on: #3"), blockers=(), open_blockers=0))
    assert msg.startswith("G2:") and "no blocker" in msg, msg


def test_g2_denies_waiting_with_an_open_blocker_by_name():
    from issue_state import g2
    msg = g2(PM, facts(waiting(), blockers=(b(3), b(4, "open")), open_blockers=1))
    assert msg.startswith("G2:") and "octo/kit#4" in msg and "open" in msg, msg


def test_g2_denies_waiting_with_a_hidden_open_blocker():
    from issue_state import g2
    msg = g2(PM, facts(waiting(), blockers=(b(3),), open_blockers=1))
    assert msg.startswith("G2:") and "cannot read" in msg, msg


def test_g2_denies_waiting_when_the_blockers_were_not_read():
    from issue_state import g2
    assert g2(PM, facts(waiting(), blockers=None, open_blockers=None)).startswith("G2:")


def test_waiting_is_not_a_return_and_does_not_reset_the_count():
    seq = done(launch("qa"), "## QA: FAIL",
               launch("pm", 2), WAITING,
               launch("engineer", 2), "## Engineer: BLOCKED")
    assert returns_since_resume(seq) == 2
    assert check(PM, facts(seq)) is None
    third = issue(*seq.comments, launch("pm", 3), "## PM: GROOMED", launch("engineer", 3), "## Engineer: BLOCKED")
    assert returns_since_resume(third) == 3
    assert check(PM, facts(third)).startswith("G7:")


def test_waiting_denies_engineer_and_qa():
    iss = waiting()
    assert check(ENG, facts(iss, blockers=(b(3),))).startswith("G3:")
    assert check(QA, facts(iss, blockers=(b(3),))).startswith("G4:")


def test_issue_state_has_no_io_imports():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "issue_state.py").read_text()
    assert not re.search(r"^import (subprocess|os)|^from (subprocess|os) ", text, re.MULTILINE)


# --- launches stopped by an auto mode outage (issue #52) ------------------------

from helpers import stopped  # noqa: E402
from issue_state import NO_VERDICT_REASONS, is_no_verdict, outage_stop_comment  # noqa: E402


def test_6a_39_case_stopped_receipt_is_not_pending():
    iss = issue(launch("pm", call=X), stopped("pm", 1, X))
    assert not is_pending(iss)
    assert check(PM, facts(iss)) is None
    assert attempt(iss, "pm") == 2


def test_6b_stopped_engineer_after_fail_adds_no_return():
    iss = done(launch("qa"), "## QA: FAIL", launch("engineer", 2, call=X), stopped("engineer", 2, X))
    assert check(ENG, facts(iss)) is None
    assert returns_since_resume(iss) == 1
    assert attempt(iss, "engineer") == 3


@pytest.mark.parametrize("marker", [
    stopped("pm", 1, Y),  # other Call value
    stopped("engineer", 1, X),  # other role
    stopped("pm", 2, X),  # other attempt number
    stopped("pm", 1, X, continued=True),  # continuation instead of attempt
])
def test_6c_stop_comment_that_matches_no_receipt_has_no_effect(marker):
    assert is_pending(issue(launch("pm", call=X), marker))


def test_stop_comment_before_the_receipt_or_without_call_line_has_no_effect():
    assert is_pending(issue(stopped("pm", 1, X), launch("pm", call=X)))
    assert is_pending(issue(launch("pm"), stopped("pm", 1, X)))


def test_stop_comment_is_not_a_result_receipt_or_resume():
    iss = issue(stopped("pm", 1, X))
    assert not is_pending(iss) and current_result(iss) is None
    assert attempt(iss, "pm") == 1
    assert returns_since_resume(iss) == 0
    assert check(PM, facts(iss)) is None


def test_stopped_continuation_keeps_fail_as_current():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1", call=X),
               stopped("engineer", 2, X, continued=True))
    assert not is_pending(iss)
    assert current_result(iss)[1] == "## QA: FAIL"


# criterion 7: two voided launches in a row, any mix


def two_voided(first, second):
    return issue(launch("pm", 1, call=X), first("pm", 1, X), launch("pm", 2, call=Y), second("pm", 2, Y))


@pytest.mark.parametrize("first, second", [(stopped, stopped), (not_started, stopped), (stopped, not_started)])
def test_7_g1_denies_after_two_voided_launches(first, second):
    msg = check(PM, facts(two_voided(first, second)))
    assert msg.startswith("G1: issue #7: the last 2 launches")
    assert RESUME in msg


def test_7_g1_allows_after_one_stopped_launch():
    assert check(PM, facts(issue(launch("pm", 1, call=X), stopped("pm", 1, X)))) is None


def test_7_g1_allows_two_stopped_followed_by_resume():
    iss = issue(*two_voided(stopped, stopped).comments, RESUME)
    assert check(PM, facts(iss)) is None


def test_7_g1_two_stopped_does_not_deny_close():
    assert not check(CLOSE, facts(two_voided(stopped, stopped))).startswith("G1:")


# the no-verdict reasons (evidence rule)


@pytest.mark.parametrize("reason", [
    "Classifier unavailable",
    "Classifier unavailable: synthetic detail\nsecond line",
    "Auto mode could not evaluate this action and is blocking it for safety",
    "Auto mode unavailable (synthetic)",
])
def test_no_verdict_reasons(reason):
    assert is_no_verdict(reason)


@pytest.mark.parametrize("reason", [
    None, 5, "", "Permission denied", "[Auto-Mode Bypass] synthetic judgment",
    "second line\nClassifier unavailable", " Classifier unavailable",
])
def test_other_reasons_are_no_evidence(reason):
    assert not is_no_verdict(reason)


def test_no_verdict_reasons_are_the_three_texts():
    assert NO_VERDICT_REASONS == ("Classifier unavailable",
                                  "Auto mode could not evaluate this action and is blocking it for safety",
                                  "Auto mode unavailable")


# outage_stop_comment (the pure decision of outage_stop.py)


def test_outage_stop_comment_for_pending_receipt():
    assert outage_stop_comment(issue(launch("pm", call=X)), "pm", "Classifier unavailable") == (
        f"## Launch stopped by outage: pm (attempt 1)\nCall: {X}\nReason: Classifier unavailable")


def test_outage_stop_comment_for_continuation_and_reason_cut():
    iss = done(launch("qa"), "## QA: FAIL", cont("engineer", 2, "eng-1", call=X))
    assert outage_stop_comment(iss, "engineer", "r" * 300 + "\nx") == (
        f"## Launch stopped by outage: engineer (continued, round 2)\nCall: {X}\nReason: " + "r" * 200)


def test_outage_stop_comment_keeps_trailing_whitespace_of_the_reason():
    reason = ("Classifier unavailable" + " " * 200)[:200]
    assert outage_stop_comment(issue(launch("pm", call=X)), "pm", reason) == (
        f"## Launch stopped by outage: pm (attempt 1)\nCall: {X}\nReason: {reason}")


@pytest.mark.parametrize("comments, role", [
    ((launch("pm"),), "pm"),  # no Call line
    ((launch("pm", call=X),), "engineer"),  # other role
    ((launch("pm", call=X), "## PM: GROOMED"), "pm"),  # valid result
    ((launch("pm", call=X), RESUME), "pm"),  # resume after it
    ((launch("pm", call=X), not_started("pm", 1, X)), "pm"),  # already not started
    ((launch("pm", call=X), stopped("pm", 1, X)), "pm"),  # already stopped
    ((), "pm"),  # no receipt
])
def test_outage_stop_comment_none(comments, role):
    assert outage_stop_comment(issue(*comments), role, "Classifier unavailable") is None


# --- close of a stage issue (issue #97) -------------------------------------------------


from issue_state import SubIssue, parse_sub_issue_total, parse_sub_issues  # noqa: E402


def s(number, state="closed", repo=REPO):
    return SubIssue(repo=repo, number=number, state=state)


def stage(*comments, labels=("stage",), open=True):
    return issue(*comments, labels=labels, open=open)


def stage_facts(iss=None, subs=(), total=None, **kw):
    """Facts of a stage issue with the two sub-issue reads; `total` defaults to the listed entries."""
    iss = iss if iss is not None else stage()
    total = len(subs) if total is None and subs is not None else total
    return facts(iss, blockers=None, open_blockers=None, sub_issues=subs, sub_issue_total=total, **kw)


def test_parse_sub_issues_reads_one_object_per_line_in_any_order():
    text = ('{"number":12,"repo":"other/lib","state":"closed"}\n'
            '{"number":3,"repo":"octo/kit","state":"open"}\n')
    assert parse_sub_issues(text) == (s(12, "closed", "other/lib"), s(3, "open"))
    assert parse_sub_issues("") == ()


@pytest.mark.parametrize("text", [
    "not json", "[]", '{"number":3,"repo":"octo/kit"}', '{"number":"3","repo":"octo/kit","state":"open"}',
    '{"number":3,"repo":"octo/kit","state":"OPEN"}', '{"number":3,"repo":5,"state":"open"}',
    '{"number":3,"repo":null,"state":"closed"}', '{"number":3.0,"repo":"octo/kit","state":"open"}', '5',
])
def test_parse_sub_issues_rejects_output_it_cannot_read(text):
    with pytest.raises(ValueError):
        parse_sub_issues(text)


def test_parse_sub_issue_total():
    assert parse_sub_issue_total("0\n") == 0
    assert parse_sub_issue_total("5") == 5


@pytest.mark.parametrize("text", ["", "null", "-1", "x", "1.5", "true", '"2"', "1\n2"])
def test_parse_sub_issue_total_rejects_output_it_cannot_read(text):
    with pytest.raises(ValueError):
        parse_sub_issue_total(text)


def test_stage_close_allows_all_sub_issues_closed_without_ready_and_without_qa():
    assert check(CLOSE, stage_facts(subs=(s(3), s(4)))) is None


@pytest.mark.parametrize("kw", [{"clean": False}, {"head": OLD}])
def test_stage_close_ignores_clean_tree_and_head(kw):
    assert check(CLOSE, stage_facts(subs=(s(3),), **kw)) is None


@pytest.mark.parametrize("labels", [("stage", "later"), ("stage", "needs-owner"), ("stage", "ready")])
def test_stage_close_ignores_the_labels_of_the_loop(labels):
    assert check(CLOSE, stage_facts(stage(labels=labels), subs=(s(3),))) is None


def test_stage_close_ignores_a_pending_launch_and_a_qa_fail():
    iss = stage(launch("pm"), "## PM: GROOMED", launch("qa"), "## QA: FAIL", launch("pm", 2))
    assert check(CLOSE, stage_facts(iss, subs=(s(3),))) is None


def test_stage_close_denies_an_open_sub_issue_and_names_it():
    msg = check(CLOSE, stage_facts(subs=(s(3), s(4, "open"))))
    assert msg.startswith("G6:") and "octo/kit#4" in msg and "octo/kit#3" not in msg, msg


def test_stage_close_names_every_open_sub_issue_in_any_order():
    for subs in ((s(5, "open"), s(2, "open", "other/lib")), (s(2, "open", "other/lib"), s(5, "open"))):
        msg = check(CLOSE, stage_facts(subs=subs))
        assert msg.startswith("G6:") and "octo/kit#5" in msg and "other/lib#2" in msg, msg


def test_stage_close_counts_a_sub_issue_closed_as_not_planned():
    # the read holds only the state; "not planned" is a state reason of the state closed
    assert check(CLOSE, stage_facts(subs=(s(3, "closed"),))) is None


def test_stage_close_reads_a_sub_issue_in_another_repo_the_same_way():
    assert check(CLOSE, stage_facts(subs=(s(8, "closed", "other/lib"),))) is None
    msg = check(CLOSE, stage_facts(subs=(s(8, "open", "other/lib"),)))
    assert msg.startswith("G6:") and "other/lib#8" in msg, msg


def test_stage_close_denies_no_sub_issue():
    msg = check(CLOSE, stage_facts(subs=(), total=0))
    assert msg.startswith("G6:") and "no sub-issue" in msg, msg


@pytest.mark.parametrize("subs", [(), (s(3),), (s(3), s(4, "open"))])
def test_stage_close_denies_a_total_greater_than_the_listed_entries(subs):
    msg = check(CLOSE, stage_facts(subs=subs, total=len(subs) + 1))
    assert msg.startswith("G6:") and "count" in msg and "does not hold" in msg, msg


def test_stage_close_allows_a_total_lower_than_the_listed_entries():
    assert check(CLOSE, stage_facts(subs=(s(3), s(4)), total=1)) is None


def test_stage_close_sees_an_open_sub_issue_on_the_second_page():
    subs = tuple(s(n) for n in range(1, 31)) + (s(31, "open"),)
    msg = check(CLOSE, stage_facts(subs=subs))
    assert msg.startswith("G6:") and "octo/kit#31" in msg, msg


def test_stage_close_denies_a_closed_stage_issue_as_today():
    msg = check(CLOSE, stage_facts(stage(open=False), subs=(s(3),)))
    assert msg == "G1: issue #7 is closed, expected an open issue", msg


def test_stage_close_denies_facts_of_another_issue():
    msg = check(Call(role="close", agent="", issue=8), stage_facts(subs=(s(3),)))
    assert msg.startswith("G1:") and "#8" in msg, msg


@pytest.mark.parametrize("missing", [{"subs": None, "total": 0}, {"subs": (s(3),), "total": None}])
def test_stage_close_denies_when_a_sub_issue_read_is_missing(missing):
    iss = stage()
    msg = check(CLOSE, facts(iss, blockers=None, open_blockers=None, sub_issues=missing["subs"],
                             sub_issue_total=missing["total"]))
    assert msg.startswith("G6:") and "not read" in msg, msg


def test_non_stage_close_is_checked_as_today_and_ignores_sub_issues():
    passed = issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD}")
    assert check(CLOSE, facts(passed, sub_issues=(s(3, "open"),), sub_issue_total=1)) is None
    msg = check(CLOSE, facts(issue(launch("qa"), f"## QA: PASS\nVerified: {HEAD}", labels=()),
                             sub_issues=(s(3),), sub_issue_total=1))
    assert msg.startswith("G1:") and "ready" in msg, msg
    msg = check(CLOSE, facts(issue(), sub_issues=(s(3),), sub_issue_total=1))
    assert msg.startswith("G6:") and "QA: PASS" in msg, msg


@pytest.mark.parametrize("call", [PM, ENG, QA, QA_FALLBACK])
def test_role_launches_on_a_stage_issue_are_not_on_the_stage_path(call):
    # a stage issue never gets ready: every role launch is denied by G1 as today
    msg = check(call, facts(stage()))
    assert msg.startswith("G1:") and "ready" in msg, msg


# --- planner launch on a stage issue (issue #99) -------------------------------------------

PLANNER = Call(role="planner", agent="planner", issue=7)
STAGE_REVIEW = "## Planner: STAGE REVIEW"
LATER_LABEL_MSG = "G1: issue #7 has the label {}, expected no label later or needs-owner"


def planner_receipt(n=1, call=None):
    return launch("planner", n, agent="planner", call=call)


def planner_facts(iss=None, **kw):
    """Facts of a planner launch: the guard runs no blocker read for it (issue #99)."""
    return facts(iss if iss is not None else stage(), blockers=None, open_blockers=None, **kw)


def test_planner_marker_is_a_result_marker_of_the_role_planner():
    assert MARKERS["planner"] == (STAGE_REVIEW,)


def test_planner_allowed_on_an_open_stage_issue_without_ready():
    assert check(PLANNER, planner_facts()) is None


def test_planner_allowed_on_a_stage_issue_with_ready():
    assert check(PLANNER, planner_facts(stage(labels=("stage", "ready")))) is None


@pytest.mark.parametrize("labels", [(), ("ready",), ("ready", "later")])
def test_planner_denied_on_an_issue_without_the_label_stage(labels):
    msg = check(PLANNER, planner_facts(issue(labels=labels)))
    assert msg == "G1: issue #7 has no label stage, expected the label stage for a planner launch", msg


def test_planner_denied_on_a_closed_stage_issue():
    assert check(PLANNER, planner_facts(stage(open=False))) == "G1: issue #7 is closed, expected an open issue"


@pytest.mark.parametrize("label", ["later", "needs-owner"])
def test_planner_denied_on_a_stage_issue_with_later_or_needs_owner(label):
    assert check(PLANNER, planner_facts(stage(labels=("stage", label)))) == LATER_LABEL_MSG.format(label)


def test_planner_denied_on_a_dirty_tree():
    msg = check(PLANNER, planner_facts(clean=False))
    assert msg == "G1: working tree is not clean, expected a clean tree (git status --porcelain empty)"


def test_planner_denied_while_pending():
    msg = check(PLANNER, planner_facts(stage(planner_receipt())))
    assert msg == ("G1: issue #7 is pending: ## Launch: planner (attempt 1) has no result, "
                   "expected a result of planner or ## Owner: RESUME"), msg


@pytest.mark.parametrize("after", [STAGE_REVIEW, STAGE_REVIEW + "\nsynthetic review", RESUME])
def test_planner_allowed_after_a_valid_stage_review_or_resume(after):
    iss = stage(planner_receipt(), after)
    assert not is_pending(iss)
    assert check(PLANNER, planner_facts(iss)) is None
    assert launch_comment(PLANNER, attempt(iss, "planner")) == "## Launch: planner (attempt 2)\nAgent: planner"


@pytest.mark.parametrize("first, second", [(not_started, not_started), (stopped, stopped),
                                           (not_started, stopped), (stopped, not_started)])
def test_planner_denied_after_two_voided_planner_launches(first, second):
    iss = stage(planner_receipt(1, X), first("planner", 1, X), planner_receipt(2, Y), second("planner", 2, Y))
    assert check(PLANNER, planner_facts(iss)).startswith("G1: issue #7: the last 2 launches")


def test_planner_allowed_after_two_voided_launches_and_a_resume():
    iss = stage(planner_receipt(1, X), not_started("planner", 1, X), planner_receipt(2, Y),
                stopped("planner", 2, Y), RESUME)
    assert check(PLANNER, planner_facts(iss)) is None


def test_planner_allowed_after_one_voided_launch():
    iss = stage(planner_receipt(1, X), not_started("planner", 1, X))
    assert not is_pending(iss)
    assert check(PLANNER, planner_facts(iss)) is None


@pytest.mark.parametrize("blockers, count", [(None, None), ((b(3, "open"),), 1), ((), 2)])
def test_planner_path_does_not_look_at_blockers(blockers, count):
    assert check(PLANNER, facts(stage(), blockers=blockers, open_blockers=count)) is None


def test_planner_path_runs_no_g2_to_g7():
    # three returns (G7), a current result that G2-G6 would deny, and a Lane-less body (G3)
    iss = issue(*three_fails(), labels=("stage",), body="Stage issue\n")
    assert returns_since_resume(iss) == 3
    assert check(PLANNER, planner_facts(iss)) is None
    assert check(PLANNER, planner_facts(stage(launch("pm"), "## PM: GROOMED"))) is None
    assert check(PLANNER, planner_facts(stage(launch("qa"), f"## QA: PASS\nVerified: {HEAD}"))) is None


@pytest.mark.parametrize("call", [Call(role="planner", agent="pm", issue=7),
                                  Call(role="planner", agent="", issue=7),
                                  Call(role="planner", agent="planner", issue=7, continued=True)])
def test_planner_role_with_another_agent_or_as_continuation_is_denied(call):
    msg = check(call, planner_facts())
    assert msg.startswith("G1:") and "planner" in msg, msg


def test_planner_denies_facts_of_another_issue():
    assert check(Call(role="planner", agent="planner", issue=8), planner_facts()).startswith("G1:")


def test_stage_review_after_the_planner_receipt_is_the_current_result():
    iss = stage(planner_receipt(), STAGE_REVIEW)
    assert current_result(iss) == (1, STAGE_REVIEW)


def test_stage_review_before_any_planner_receipt_is_not_valid():
    assert current_result(stage(STAGE_REVIEW)) is None
    iss = stage(STAGE_REVIEW, planner_receipt())
    assert is_pending(iss)
    assert current_result(iss) is None


def test_stage_review_after_another_role_receipt_is_not_valid():
    iss = stage(launch("pm"), STAGE_REVIEW)
    assert is_pending(iss) and current_result(iss) is None


def test_stage_review_is_not_a_return():
    iss = stage(planner_receipt(1), STAGE_REVIEW, planner_receipt(2), STAGE_REVIEW,
                planner_receipt(3), STAGE_REVIEW)
    assert returns_since_resume(iss) == 0


def test_planner_receipts_are_voided_by_not_started_and_stop_comments():
    assert not_started_comment(stage(planner_receipt(1, X)), X, "Classifier unavailable", role="planner") == (
        f"## Launch not started: planner (attempt 1)\nCall: {X}\nReason: Classifier unavailable")
    assert outage_stop_comment(stage(planner_receipt(1, X)), "planner", "Classifier unavailable") == (
        f"## Launch stopped by outage: planner (attempt 1)\nCall: {X}\nReason: Classifier unavailable")
    for void in (not_started, stopped):
        iss = stage(planner_receipt(1, X), void("planner", 1, X))
        assert not is_pending(iss) and attempt(iss, "planner") == 2


def test_role_launches_and_stage_close_are_unchanged_by_a_planner_result():
    iss = stage(planner_receipt(), STAGE_REVIEW)
    for call in (PM, ENG, QA, QA_FALLBACK):
        msg = check(call, facts(iss))
        assert msg.startswith("G1:") and "ready" in msg, msg
    assert check(CLOSE, stage_facts(iss, subs=(s(3),))) is None


# --- the resume match (issue #131) -------------------------------------------
# A first line is the owner's resume marker when " ".join(line.split()).casefold() == "## owner: resume".

from issue_state import is_resume  # noqa: E402

RESUME_COUNTS = [
    "## Owner: RESUME",  # exact line
    "## OWNER: RESUME",  # upper case
    "## OWNER: Resume", "## owner: resume",  # mixed and lower case
    "##  Owner:  RESUME ", "   ## Owner: RESUME", "##\tOwner: RESUME\r",  # spaces, leading, tab, CRLF
]
RESUME_DOES_NOT_COUNT = [
    "## Owner: RESUME later",  # trailing text
    "Owner: RESUME", "# Owner: RESUME",  # missing or short ##
    "##Owner: RESUME", "## Owner:RESUME",  # a missing space is not extra whitespace
]


def _needs_owner_then(line):
    return issue(launch("pm"), "## PM: NEEDS OWNER", line + "\nplease go on")


@pytest.mark.parametrize("line", RESUME_COUNTS)
def test_resume_variant_counts(line):
    assert is_resume(line)
    pending = issue(launch("engineer"), line + "\nnote")
    assert not is_pending(pending)
    assert current_result(pending) == (1, RESUME)
    assert check(PM, facts(_needs_owner_then(line))) is None  # G2 passes
    after = issue(*_three_owner_returns(), line)
    assert returns_since_resume(after) == 0
    assert check(PM, facts(after)) is None  # G7 count reset


@pytest.mark.parametrize("line", RESUME_DOES_NOT_COUNT)
def test_resume_non_match_does_not_count(line):
    assert not is_resume(line)
    pending = issue(launch("engineer"), line + "\nnote")
    assert is_pending(pending)
    assert current_result(pending) is None
    assert check(PM, facts(_needs_owner_then(line))).startswith("G2:")
    after = issue(*_three_owner_returns(), line)
    assert returns_since_resume(after) == 3
    assert check(PM, facts(after)).startswith("G7:")


def test_resume_variant_by_a_stranger_is_ignored():
    base = (launch("pm"), "## PM: NEEDS OWNER")
    assert check(PM, facts(parse_issue(gh_issue(*base, stranger("## OWNER: Resume", "CONTRIBUTOR"))))).startswith("G2:")
    iss = parse_issue(gh_issue(*_three_owner_returns(), stranger("## OWNER: Resume", "CONTRIBUTOR")))
    assert returns_since_resume(iss) == 3
    assert check(PM, facts(iss)).startswith("G7:")


@pytest.mark.parametrize("line", RESUME_COUNTS)
def test_resume_variant_stops_not_started_and_outage_stop_comments(line):
    iss = issue(launch("pm", call=X), line)
    assert not_started_comment(iss, X, "Classifier unavailable") is None
    assert outage_stop_comment(iss, "pm", "Classifier unavailable") is None
    control = issue(launch("pm", call=X), "note")
    assert not_started_comment(control, X, "Classifier unavailable") is not None
    assert outage_stop_comment(control, "pm", "Classifier unavailable") is not None


@pytest.mark.parametrize("line", RESUME_COUNTS)
def test_resume_variant_after_two_voided_receipts_lets_g1_pass(line):
    assert check(PM, facts(issue(*two_not_started().comments, line))) is None


@pytest.mark.parametrize("line", RESUME_DOES_NOT_COUNT)
def test_non_match_after_two_voided_receipts_keeps_g1_deny(line):
    msg = check(PM, facts(issue(*two_not_started().comments, line)))
    assert msg.startswith("G1: issue #7: the last 2 launches")


def test_deny_messages_name_the_exact_resume_line():
    assert RESUME == "## Owner: RESUME"
    assert RESUME in check(PM, facts(two_not_started()))
    assert RESUME in check(PM, facts(issue(launch("engineer"))))  # G1 pending
    assert RESUME in check(PM, facts(issue(launch("pm"), "## PM: NEEDS OWNER")))  # G2
    assert RESUME in check(PM, facts(issue(*_three_owner_returns())))  # G7


def test_other_markers_keep_their_exact_match():
    assert current_result(issue(launch("pm"), "## pm: groomed")) is None
    assert current_result(issue(launch("qa"), "##  QA:  PASS")) is None
    assert is_pending(issue("## launch: pm (attempt 1)\nAgent: pm")) is False
