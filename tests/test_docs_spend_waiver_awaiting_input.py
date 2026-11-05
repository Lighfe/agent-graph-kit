"""Fact tests for the project spend waiver and the Lovable awaiting_input pause (issue #262).
Read-only, no subprocess."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAM = ROOT / "docs" / "team"
BUILT = ROOT / "plugin" / "templates" / "docs" / "team"


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def frontend_lane():
    t = (TEAM / "software-engineer.md").read_text(encoding="utf-8")
    return t.split("## Lane `frontend`")[1]


def step3():
    lane = frontend_lane()
    return lane.split("\n3. ")[1].split("\n4. ")[0]


WAIVER = "A spend that the project's `AGENTS.md` names as needing no owner approval"


def test_pm_followup_rule_has_waiver_and_keeps_other_reasons():
    t = flat(TEAM / "pm.md")
    para = [p for p in t.split("If something does not belong in this task")][1].split("## ")[0]
    assert WAIVER in para
    assert "is no reason for `needs-owner`" in para
    assert ("the hooks, the project settings files in `.claude/` and the QA sandbox arguments "
            "still give `needs-owner`") in para


def test_planner_followup_rule_has_waiver_and_keeps_other_reasons():
    lines = (TEAM / "planner.md").read_text(encoding="utf-8").splitlines()
    hits = [l for l in lines if WAIVER in l]
    assert len(hits) == 1
    rule = hits[0]
    assert "is no reason for `needs-owner`" in rule
    assert "still give `needs-owner`" in rule
    for case in ("hooks", "the project settings files in `.claude/`", "the QA sandbox arguments"):
        assert case in rule, case
    # The waiver sits right after the needs-owner bullet of the stage set-up follow-up rule.
    i = lines.index(rule)
    assert "gets the label `needs-owner` in addition to `later`" in lines[i - 1]


def test_frontend_lane_spend_waiver_and_credit_pause():
    lane = re.sub(r"\s+", " ", frontend_lane())
    assert ("When the project's `AGENTS.md` names this spend as needing no owner approval, "
            "a Lovable message needs no owner approval.") in lane
    assert ("A credit or spend-limit pause still needs the owner: post `## Engineer: BLOCKED`, "
            "also when `AGENTS.md` waives that spend.") in lane


def test_step3_answers_awaiting_input_with_respond_to_approval():
    s = re.sub(r"\s+", " ", step3())
    for k in ("`awaiting_input` with an `awaiting_input` object", "`awaiting_input.tool_id`",
              "`awaiting_input.params`", "`respond_to_approval`", "`event_id`",
              "the user `message_id` the pause was reported on",
              "Never answer the pause with `send_message`: that rejects the pending tool",
              "Approve when the tool and its params fit the goal, the criteria and the constraints of the issue",
              "otherwise reject it and correct Lovable with a follow-up message"):
        assert k in s, k


def test_step3_blocked_cases_without_respond_to_approval():
    s = re.sub(r"\s+", " ", step3())
    bullet = s.split("no `respond_to_approval` call, post `## Engineer: BLOCKED` instead")[1]
    for k in ("`awaiting_input.requires_secure_form` is true", "`awaiting_input.editor_url`",
              "never enter a secret", "credits, a spend limit or a payment",
              "you cannot tell from `tool_id` and `params` what the tool does"):
        assert k in bullet, k


def test_no_supersede_rule_and_plan_in_finished_reply_uses_send_message():
    for p in (TEAM / "software-engineer.md", ROOT / "README.md"):
        t = flat(p)
        assert "supersedes the pause" not in t
        assert "supersedes an `awaiting_input`" not in t
    s = re.sub(r"\s+", " ", step3())
    assert "A plan or a question in a finished reply" in s
    assert "answer it with a new `send_message`" in s


def test_frontend_engineer_agent_has_respond_to_approval():
    for p in (ROOT / ".claude" / "agents" / "frontend-engineer.md",
              ROOT / "plugin" / "agents" / "frontend-engineer.md"):
        tools = [l for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("tools:")][0]
        assert "mcp__plugin_lovable_lovable__respond_to_approval" in tools


def test_readme_pause_paragraph_matches_rule_and_allow_entry_note():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    para = [p for p in readme.split("\n\n") if p.startswith("Lovable can pause a message")]
    assert len(para) == 1
    p = para[0]
    for k in ("`respond_to_approval`", "never with a new message", "secure form",
              "credits, a spend limit or a payment", "## Engineer: BLOCKED",
              "Auto mode allow entry that lists the `frontend-engineer` Lovable tools",
              "must also list `respond_to_approval`"):
        assert k in p, k


def test_built_copies_equal_sources():
    for name in ("pm.md", "planner.md", "software-engineer.md"):
        assert (TEAM / name).read_bytes() == (BUILT / name).read_bytes(), name
