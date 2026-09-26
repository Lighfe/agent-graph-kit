"""Issue state and checks G1-G7 (spec 5.3-5.5).

Pure functions over the facts of one issue. No I/O: the guard (Task 5)
reads the facts with `gh` and `git` and passes them in. Stdlib only.

Comment order is the order of the `gh` comments array (plan decision).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# role -> result markers (spec 5.5)
MARKERS: dict[str, tuple[str, ...]] = {
    "pm": ("## PM: GROOMED", "## PM: NEEDS OWNER"),
    "engineer": ("## Engineer: DONE", "## Engineer: BLOCKED"),
    "qa": ("## QA: PASS", "## QA: FAIL", "## QA: UNAVAILABLE", "## QA: INVALID"),
}
RESUME = "## Owner: RESUME"
AGENT_LANE = {"default": "software-engineer", "frontend": "frontend-engineer"}

GROOMED, NEEDS_OWNER = MARKERS["pm"]
DONE, BLOCKED = MARKERS["engineer"]
PASS, FAIL, UNAVAILABLE, INVALID = MARKERS["qa"]
RETURNS = (FAIL, BLOCKED)
STOP_RESULTS = (NEEDS_OWNER, INVALID)
MAX_RETURNS = 3

LAUNCH = re.compile(r"^## Launch: (pm|engineer|qa) \((?:attempt|continued, round) (\d+)\)$")
_LANE = re.compile(r"^Lane: (\S+)$")
_VERIFIED = re.compile(r"^Verified: (\S+)$")
_COMMITS = re.compile(r"^Commits: (\S+?)\.\.(\S+)$")


@dataclass(frozen=True)
class Issue:
    number: int
    open: bool
    labels: frozenset[str]
    body: str
    comments: tuple[str, ...]  # comment bodies, oldest first


@dataclass(frozen=True)
class Facts:
    issue: Issue
    head: str  # full SHA of HEAD
    clean: bool  # git status --porcelain is empty


@dataclass(frozen=True)
class Call:
    role: str  # "pm" | "engineer" | "qa" | "close"
    agent: str  # subagent type, "qa-codex", "" for close; the SendMessage target for a continuation
    issue: int
    continued: bool = False  # a SendMessage continuation (spec 5.3)


# --- parsing -------------------------------------------------------------------


def parse_issue(data: dict) -> Issue:
    """Build an Issue from `gh issue view N --json number,state,labels,body,comments`."""
    return Issue(
        number=int(data["number"]),
        open=data["state"] == "OPEN",
        labels=frozenset(label["name"] for label in data.get("labels") or ()),
        body=data.get("body") or "",
        comments=tuple(c.get("body") or "" for c in data.get("comments") or ()),
    )


def first_line(body: str) -> str:
    return body.split("\n", 1)[0].rstrip()


def _value(body: str, pattern: re.Pattern) -> re.Match | None:
    """First line of `body` (CR and trailing spaces removed) that matches `pattern`."""
    for line in body.split("\n"):
        m = pattern.match(line.rstrip())
        if m:
            return m
    return None


def lane(issue: Issue) -> str | None:
    m = _value(issue.body, _LANE)
    return m.group(1) if m else None


def verified_sha(body: str) -> str | None:
    m = _value(body, _VERIFIED)
    return m.group(1) if m else None


def commits_range(body: str) -> tuple[str, str] | None:
    m = _value(body, _COMMITS)
    return (m.group(1), m.group(2)) if m else None


# --- validity, pending, current result (spec 5.3) --------------------------------


def _lines(issue: Issue) -> list[str]:
    return [first_line(c) for c in issue.comments]


def _result_role(line: str) -> str | None:
    return next((role for role, markers in MARKERS.items() if line in markers), None)


def _launch_role(line: str) -> str | None:
    m = LAUNCH.match(line)
    return m.group(1) if m else None


def _newest_launch(lines: list[str], role: str | None = None) -> int | None:
    idx = [i for i, line in enumerate(lines)
           if (r := _launch_role(line)) and (role is None or r == role)]
    return idx[-1] if idx else None


def _valid(lines: list[str], i: int) -> bool:
    role = _result_role(lines[i])
    j = _newest_launch(lines, role) if role else None
    return j is not None and i > j


def is_pending(issue: Issue) -> bool:
    lines = _lines(issue)
    j = _newest_launch(lines)
    if j is None:
        return False
    role = _launch_role(lines[j])
    return not any(line == RESUME or _result_role(line) == role for line in lines[j + 1:])


def current_result(issue: Issue) -> tuple[int, str] | None:
    lines = _lines(issue)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == RESUME or _valid(lines, i):
            return i, lines[i]
    return None


def returns_since_resume(issue: Issue) -> int:
    lines = _lines(issue)
    resumes = [i for i, line in enumerate(lines) if line == RESUME]
    start = resumes[-1] + 1 if resumes else 0
    count = 0
    for i in range(start, len(lines)):
        if lines[i] in RETURNS:
            role = _result_role(lines[i])
            if any(_launch_role(line) == role for line in lines[:i]):
                count += 1
    return count


def newest_done(issue: Issue) -> str | None:
    lines = _lines(issue)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == DONE and _valid(lines, i):
            return issue.comments[i]
    return None


def attempt(issue: Issue, role: str) -> int:
    return sum(1 for line in _lines(issue) if _launch_role(line) == role) + 1


def launch_comment(call: Call, attempt: int) -> str:
    kind = f"continued, round {attempt}" if call.continued else f"attempt {attempt}"
    return f"## Launch: {call.role} ({kind})\nAgent: {call.agent}"


# --- checks (spec 5.4) -----------------------------------------------------------


def _current(issue: Issue) -> tuple[int | None, str | None, str]:
    """(index, marker, text for messages) of the current result."""
    cur = current_result(issue)
    if cur is None:
        return None, None, "none"
    return cur[0], cur[1], cur[1]


def g1(call: Call, facts: Facts) -> str | None:
    iss = facts.issue
    if iss.number != call.issue:
        return f"G1: facts are for issue #{iss.number}, expected issue #{call.issue}"
    if not iss.open:
        return f"G1: issue #{iss.number} is closed, expected an open issue"
    if "ready" not in iss.labels:
        return f"G1: issue #{iss.number} has no label ready, expected the label ready"
    for label in ("later", "needs-owner"):
        if label in iss.labels:
            return f"G1: issue #{iss.number} has the label {label}, expected no label later or needs-owner"
    if not facts.clean:
        return "G1: working tree is not clean, expected a clean tree (git status --porcelain empty)"
    if is_pending(iss):
        lines = _lines(iss)
        j = _newest_launch(lines)
        return (f"G1: issue #{iss.number} is pending: {lines[j]} has no result, "
                f"expected a result of {_launch_role(lines[j])} or {RESUME}")
    return None


def g2(call: Call, facts: Facts) -> str | None:
    lines = _lines(facts.issue)
    _, marker, found = _current(facts.issue)
    if _newest_launch(lines) is None or marker in (BLOCKED, RESUME):
        return None
    return f"G2: current result is {found}, expected no launch comment yet, {BLOCKED} or {RESUME}"


def g3(call: Call, facts: Facts) -> str | None:
    _, marker, found = _current(facts.issue)
    if marker not in (GROOMED, FAIL):
        return f"G3: current result is {found}, expected {GROOMED} or {FAIL}"
    if call.continued:
        return None  # the SendMessage target is a name, not a type (spec 5.3)
    value = lane(facts.issue)
    if value is None:
        return f"G3: issue body has no Lane line, expected Lane: {' or Lane: '.join(AGENT_LANE)}"
    if value not in AGENT_LANE:
        return f"G3: lane is {value}, expected {' or '.join(AGENT_LANE)}"
    if call.agent != AGENT_LANE[value]:
        return f"G3: agent is {call.agent or 'none'}, expected {AGENT_LANE[value]} for lane {value}"
    return None


def g4(call: Call, facts: Facts) -> str | None:
    i, marker, found = _current(facts.issue)
    if marker == PASS:
        sha = verified_sha(facts.issue.comments[i])
        if sha == facts.head:
            return (f"G4: current result is {PASS} with verified SHA {sha} equal to HEAD, "
                    f"expected {DONE} or a {PASS} with a verified SHA not equal to HEAD")
    elif marker != DONE:
        return (f"G4: current result is {found}, "
                f"expected {DONE} or a {PASS} with a verified SHA not equal to HEAD")
    done = newest_done(facts.issue)
    if done is None:
        return f"G4: no valid {DONE} comment found, expected one with a Commits: line"
    if commits_range(done) is None:
        return f"G4: the newest {DONE} comment has no Commits: line, expected Commits: <base>..<head>"
    return None


def g5(call: Call, facts: Facts) -> str | None:
    _, marker, found = _current(facts.issue)
    if marker == UNAVAILABLE:
        return None
    return f"G5: current result is {found}, expected {UNAVAILABLE}"


def g6(call: Call, facts: Facts) -> str | None:
    i, marker, found = _current(facts.issue)
    if marker != PASS:
        return f"G6: current result is {found}, expected {PASS} with a verified SHA equal to HEAD"
    sha = verified_sha(facts.issue.comments[i])
    if sha != facts.head:
        return f"G6: verified SHA is {sha or 'missing'}, expected HEAD {facts.head}"
    return None


def g7(call: Call, facts: Facts) -> str | None:
    n = returns_since_resume(facts.issue)
    if n < MAX_RETURNS:
        return None
    return (f"G7: {n} returns ({FAIL} or {BLOCKED}) since the newest {RESUME}, "
            f"expected fewer than {MAX_RETURNS}")


def _role_checks(call: Call):
    """The role checks for a call, or a G1 deny message if the call cannot be placed."""
    if call.role == "pm":
        if not call.continued and call.agent != "pm":
            return f"G1: pm call with agent {call.agent or 'none'}, expected agent pm"
        return (g2, g7)
    if call.role == "engineer":
        return (g3, g7)
    if call.role == "qa":
        if call.continued or call.agent == "qa-engineer":
            return (g5,)  # only the qa-engineer subagent can be continued (spec 5.1, 5.3)
        if call.agent == "qa-codex":
            return (g4,)
        return f"G1: qa call with agent {call.agent or 'none'}, expected qa-codex or qa-engineer"
    if call.role == "close":
        return (g6,)
    return f"G1: unknown role {call.role or 'none'}, expected pm, engineer, qa or close"


def check(call: Call, facts: Facts) -> str | None:
    """None = allow, else the deny message. Never allows a call it cannot place."""
    checks = _role_checks(call)
    if isinstance(checks, str):
        return checks
    for g in (g1, *checks):
        reason = g(call, facts)
        if reason is not None:
            return reason
    return None
