"""Issue state and checks G1-G7 (docs/specs/agent-graph-kit.md#launch-comments, docs/specs/agent-graph-kit.md#checks,
docs/specs/agent-graph-kit.md#result-markers).

Roles: pm, engineer, qa, planner (the stage review, issue #99) and close. A planner launch
on a stage issue has its own path of G1 (`g1_planner`); G2 to G7 do not apply to it.

Pure functions over the facts of one issue. No I/O: the guard (Task 5)
reads the facts with `gh` and `git` and passes them in. Stdlib only.

Comment order is the order of the `gh` comments array (plan decision).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

# role -> result markers (docs/specs/agent-graph-kit.md#result-markers)
MARKERS: dict[str, tuple[str, ...]] = {
    "pm": ("## PM: GROOMED", "## PM: NEEDS OWNER", "## PM: WAITING"),
    "engineer": ("## Engineer: DONE", "## Engineer: BLOCKED"),
    "qa": ("## QA: PASS", "## QA: FAIL", "## QA: UNAVAILABLE", "## QA: INVALID", "## QA: UNVERIFIABLE"),
    "planner": ("## Planner: STAGE REVIEW",),  # issue #99: one comment, then the planner ends
}
RESUME = "## Owner: RESUME"
# The only authorAssociation whose comments count (issue #70). Organization-owned repos are not supported yet.
OWNER = "OWNER"
AGENT_LANE = {"default": "software-engineer", "frontend": "frontend-engineer"}

GROOMED, NEEDS_OWNER, WAITING = MARKERS["pm"]
DONE, BLOCKED = MARKERS["engineer"]
PASS, FAIL, UNAVAILABLE, INVALID, UNVERIFIABLE = MARKERS["qa"]
(STAGE_REVIEW,) = MARKERS["planner"]
# A return sends the issue back (G7): FAIL and BLOCKED, and UNVERIFIABLE (a limit of the
# checker's environment, back to the PM, docs/team/qa-engineer.md). INVALID is not a return: it escalates.
RETURNS = (FAIL, UNVERIFIABLE, BLOCKED)
STOP_RESULTS = (NEEDS_OWNER, INVALID)
MAX_RETURNS = 3

ROLES = "pm|engineer|qa|planner"  # the roles of a launch receipt (the planner: issue #99)
LAUNCH = re.compile(rf"^## Launch: ({ROLES}) \((?:attempt|continued, round) (\d+)\)$")
# A receipt that Claude Code denied before the launch ran (PermissionDenied hook,
# docs/specs/agent-graph-kit.md#not-started-and-stopped-by-an-outage)
NOT_STARTED = re.compile(rf"^## Launch not started: ((?:{ROLES}) \((?:attempt|continued, round) \d+\))$")
# A receipt whose agent started, was stopped by an auto mode outage and ended without a result
# (SubagentStop hook, docs/specs/agent-graph-kit.md#not-started-and-stopped-by-an-outage). It voids its receipt exactly like a not-started comment.
STOPPED = re.compile(rf"^## Launch stopped by outage: ((?:{ROLES}) \((?:attempt|continued, round) \d+\))$")
# First-line prefixes of a denial without a classifier verdict (Claude Code 2.1.284,
# docs/specs/agent-graph-kit.md#not-started-and-stopped-by-an-outage)
NO_VERDICT_REASONS = ("Classifier unavailable",
                      "Auto mode could not evaluate this action and is blocking it for safety",
                      "Auto mode unavailable")
_RECEIPT_KEY = re.compile(rf"^## Launch: ((?:{ROLES}) \((?:attempt|continued, round) \d+\))$")
_CALL = re.compile(r"^Call: (\S+)$")
CALL_HASH_LEN = 12
REASON_MAX = 200
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
class Blocker:
    """One native "blocked by" link of an issue (issue #64)."""
    repo: str  # owner/repo of the blocker, also another repo
    number: int
    state: str  # "open" or "closed"

    def name(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass(frozen=True)
class SubIssue:
    """One sub-issue of a stage issue (issue #97)."""
    repo: str  # owner/repo of the sub-issue, also another repo
    number: int
    state: str  # "open" or "closed" (any state reason, so "not planned" is closed)

    def name(self) -> str:
        return f"{self.repo}#{self.number}"


STAGE = "stage"  # the label of a stage issue (docs/specs/agent-graph-kit.md#stage-model)


@dataclass(frozen=True)
class Facts:
    issue: Issue
    head: str  # full SHA of HEAD
    clean: bool  # git status --porcelain is empty
    # The two blocker reads (issue #64), None when not read. The guard reads them for every role
    # launch except the planner, never for close: the blocker list (all pages, a set) and the open-blocker count.
    blockers: tuple[Blocker, ...] | None = None
    open_blockers: int | None = None
    # The two sub-issue reads (issue #97), None when not read. The guard reads them only for the
    # close of a stage issue: the sub-issue list (all pages, a set) and sub_issues_summary.total.
    sub_issues: tuple[SubIssue, ...] | None = None
    sub_issue_total: int | None = None


@dataclass(frozen=True)
class Call:
    role: str  # "pm" | "engineer" | "qa" | "planner" | "close"
    agent: str  # subagent type, "qa-codex", "" for close; the SendMessage target for a continuation
    issue: int
    continued: bool = False  # a SendMessage continuation (docs/specs/agent-graph-kit.md#continuation)


# --- parsing -------------------------------------------------------------------


def _comment_bodies(data: dict) -> tuple[str, ...]:
    """The bodies of the comments the repo owner wrote (authorAssociation exactly OWNER), oldest
    first, or ValueError when the comment data is missing or malformed. Every comment is checked,
    also the ones that are dropped: missing author data must not look like a stranger's comment."""
    comments = data.get("comments")
    if not isinstance(comments, list):
        raise ValueError(f"issue JSON has no comments list (got {type(comments).__name__})")
    bodies = []
    for n, c in enumerate(comments):
        if not isinstance(c, dict) or not isinstance(c.get("body"), str):
            raise ValueError(f"issue JSON comment {n} has no string body")
        association = c.get("authorAssociation")
        if not isinstance(association, str):
            raise ValueError(f"issue JSON comment {n} has no string authorAssociation "
                             f"(got {type(association).__name__})")
        if association == OWNER:
            bodies.append(c["body"])
    return tuple(bodies)


def parse_issue(data: dict) -> Issue:
    """Build an Issue from `gh issue view N --json number,state,labels,body,comments`.

    Only comments whose `authorAssociation` is exactly OWNER count (issue #70): in a public
    repo anyone can comment, and a stranger's marker must not resume, pass, block, void a
    receipt or close an issue. Other comments are left out of `Issue.comments`.

    Raises ValueError when `comments` is missing, not a list, or has an element
    without a string `body` or a string `authorAssociation`: missing comment data
    must not look like an issue without comments.
    """
    return Issue(
        number=int(data["number"]),
        open=data["state"] == "OPEN",
        labels=frozenset(label["name"] for label in data.get("labels") or ()),
        body=data.get("body") or "",
        comments=_comment_bodies(data),
    )


def first_line(body: str) -> str:
    return body.split("\n", 1)[0].rstrip()


def evidence_line(reason: str) -> str:
    """The first line of a reason as is (trailing whitespace kept), cut to REASON_MAX characters."""
    return reason.split("\n", 1)[0][:REASON_MAX]


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _unfenced_lines(text: str):
    """Lines of one text outside fenced code blocks (the fence lines count as inside).

    A fence opens on a line of 3+ backticks or 3+ tildes (at most 3 leading spaces,
    any info string after it) and closes on a line of the same character, at least
    as long, with only spaces or tabs after it. An unclosed fence runs to the end.
    """
    fence = None  # (character, length) of the open fence
    for line in text.split("\n"):
        bare = line.rstrip("\r")
        if fence is None:
            m = _FENCE_OPEN.match(bare)
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
            else:
                yield line
            continue
        char, length = fence
        close = re.match(r"^ {0,3}(" + re.escape(char) + r"{" + str(length) + r",})[ \t]*$", bare)
        if close:
            fence = None


def _value(text: str, pattern: re.Pattern) -> tuple[str, ...] | None:
    """The groups of the lines of `text` outside fences (CR and trailing spaces
    removed) that match `pattern`. None when no line matches or when matching
    lines disagree (an unknown value behaves like a missing one)."""
    found = {m.groups() for line in _unfenced_lines(text) if (m := pattern.match(line.rstrip()))}
    return found.pop() if len(found) == 1 else None


def lane(issue: Issue) -> str | None:
    m = _value(issue.body, _LANE)
    return m[0] if m else None


def verified_sha(body: str) -> str | None:
    m = _value(body, _VERIFIED)
    return m[0] if m else None


def commits_range(body: str) -> tuple[str, str] | None:
    m = _value(body, _COMMITS)
    return (m[0], m[1]) if m else None


def _decode_stream(text: str) -> list:
    """The JSON values of a text, one after the other (gh --jq prints one value per line)."""
    decoder, values, i = json.JSONDecoder(), [], 0
    while True:
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i == len(text):
            return values
        value, i = decoder.raw_decode(text, i)
        values.append(value)


def _parse_linked(text: str, what: str, kind):
    """The linked issues (`kind`: Blocker or SubIssue) from `gh api --paginate … --jq
    '.[] | {repo: .repository.full_name, number, state}'`: one object per item, all pages.
    Counted per item; the order means nothing. ValueError for output that cannot be read."""
    items = []
    for item in _decode_stream(text):
        if not isinstance(item, dict):
            raise ValueError(f"{what} item is not an object (got {type(item).__name__})")
        repo, number, state = item.get("repo"), item.get("number"), item.get("state")
        if not isinstance(repo, str) or not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
            raise ValueError(f"{what} item has no repo owner/name")
        if type(number) is not int or number < 1:
            raise ValueError(f"{what} item has no positive issue number")
        if state not in ("open", "closed"):
            raise ValueError(f"{what} item has no state open or closed")
        items.append(kind(repo=repo, number=number, state=state))
    return tuple(items)


def _parse_count(text: str, what: str) -> int:
    """One non-negative integer, as `gh api … --jq <field>` prints it, else ValueError."""
    values = _decode_stream(text)
    if len(values) != 1 or type(values[0]) is not int or values[0] < 0:
        raise ValueError(f"the {what} is not one non-negative integer")
    return values[0]


def parse_blockers(text: str) -> tuple[Blocker, ...]:
    """The blockers from the output of
    `gh api --paginate repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by
    --jq '.[] | {repo: .repository.full_name, number, state}'`: one object per blocker, all pages.
    Counted per item; the order means nothing. ValueError for output that cannot be read."""
    return _parse_linked(text, "blocker", Blocker)


def parse_open_blocker_count(text: str) -> int:
    """The open-blocker count from the output of
    `gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by`.
    ValueError for anything but one non-negative integer."""
    return _parse_count(text, "open-blocker count")


def parse_sub_issues(text: str) -> tuple[SubIssue, ...]:
    """The sub-issues from the output of
    `gh api --paginate repos/<owner>/<repo>/issues/<n>/sub_issues
    --jq '.[] | {repo: .repository.full_name, number, state}'` (issue #97, read form of the #95 report):
    one object per sub-issue, all pages. Counted per item; the order means nothing (#95).
    ValueError for output that cannot be read."""
    return _parse_linked(text, "sub-issue", SubIssue)


def parse_sub_issue_total(text: str) -> int:
    """The sub-issue count from the output of
    `gh api repos/<owner>/<repo>/issues/<n> --jq .sub_issues_summary.total`.
    ValueError for anything but one non-negative integer."""
    return _parse_count(text, "sub-issue total")


def is_stage(issue: Issue) -> bool:
    return STAGE in issue.labels


def open_blocker_problem(facts: Facts) -> str | None:
    """None when both blocker reads ran and show no open blocker, else the text for a deny:
    the reads are missing, the open blockers by name, or an open blocker the login cannot read
    (the count is greater than the open entries of the list; the list may be incomplete, #95)."""
    if facts.blockers is None or facts.open_blockers is None:
        return "the blockers were not read"
    names = sorted(b.name() for b in facts.blockers if b.state == "open")
    parts = []
    if names:
        parts.append(f"open blocker {', '.join(names)}")
    if facts.open_blockers > len(names):
        parts.append(f"the open-blocker count is {facts.open_blockers} but the blocker list holds "
                     f"{len(names)} open, so an open blocker the login cannot read")
    return "; ".join(parts) or None


# --- validity, pending, current result (docs/specs/agent-graph-kit.md#valid-result-pending-and-current-result) ---


def call_hash(tool_use_id: str) -> str:
    """The first 12 hex characters of the SHA-256 of a tool_use_id. The raw id is never posted."""
    return hashlib.sha256(tool_use_id.encode("utf-8")).hexdigest()[:CALL_HASH_LEN]


def _call_value(body: str) -> str | None:
    m = _value(body, _CALL)
    return m[0] if m else None


def is_no_verdict(reason) -> bool:
    """True when the first line of a denial reason starts with one of the no-verdict texts."""
    return isinstance(reason, str) and first_line(reason).startswith(NO_VERDICT_REASONS)


def _not_started(issue: Issue) -> set[int]:
    """Indexes of the voided receipts: a later not-started or stopped-by-outage comment has the
    same `<role> (…)` part and the same Call: value. A receipt without a Call: line is never voided."""
    marks = []  # (index, key, call) of the not-started and stop comments
    for j, body in enumerate(issue.comments):
        line = first_line(body)
        m = NOT_STARTED.match(line) or STOPPED.match(line)
        if m and (value := _call_value(body)):
            marks.append((j, m.group(1), value))
    voided = set()
    for i, body in enumerate(issue.comments):
        m = _RECEIPT_KEY.match(first_line(body))
        if m and (value := _call_value(body)) and any(
                j > i and key == m.group(1) and call == value for j, key, call in marks):
            voided.add(i)
    return voided


def _raw_lines(issue: Issue) -> list[str]:
    return [first_line(c) for c in issue.comments]


def _lines(issue: Issue) -> list[str]:
    """First lines of the comments. A receipt that is not started counts for nothing here:
    its line is blank. Only `attempt` reads the raw lines."""
    voided = _not_started(issue)
    return ["" if i in voided else line for i, line in enumerate(_raw_lines(issue))]


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
    """A receipt that is not started still counts here, so the next launch gets the next number."""
    return sum(1 for line in _raw_lines(issue) if _launch_role(line) == role) + 1


def launch_comment(call: Call, attempt: int, call_hash: str | None = None) -> str:
    kind = f"continued, round {attempt}" if call.continued else f"attempt {attempt}"
    text = f"## Launch: {call.role} ({kind})\nAgent: {call.agent}"
    return f"{text}\nCall: {call_hash}" if call_hash else text


def _void_comment(issue: Issue, head: str, role: str | None, reason: str,
                  call_hash: str | None = None, verbatim: bool = False) -> str | None:
    """`head` for the newest receipt, or None when the newest receipt has no Call: line (or not one
    equal to call_hash), has another role than `role`, has a result of its role or a RESUME after
    it, or is already voided."""
    raw = _raw_lines(issue)
    j = _newest_launch(raw)
    if j is None or j in _not_started(issue):
        return None
    value = _call_value(issue.comments[j])
    if value is None or (call_hash is not None and value != call_hash):
        return None
    receipt_role = _launch_role(raw[j])
    if role is not None and receipt_role != role:
        return None
    if any(line == RESUME or _result_role(line) == receipt_role for line in raw[j + 1:]):
        return None
    key = raw[j][len("## Launch: "):]
    text = evidence_line(reason) if verbatim else first_line(reason)[:REASON_MAX]
    return f"{head} {key}\nCall: {value}\nReason: {text}"


def not_started_comment(issue: Issue, call_hash: str, reason: str, role: str | None = None) -> str | None:
    """The not-started comment for the newest receipt, or None when it must not be posted:
    the newest receipt has no Call: line equal to call_hash (or another role than `role`),
    has a result of its role or a RESUME after it, or is already not started or stopped."""
    return _void_comment(issue, "## Launch not started:", role, reason, call_hash)


def outage_stop_comment(issue: Issue, role: str, reason: str) -> str | None:
    """The stop comment for the newest receipt of an agent that an auto mode outage stopped, or None:
    the newest receipt has no Call: line, has another role than `role`, has a result of its role or
    a RESUME after it, or is already not started or stopped. The reason (the evidence content)
    is posted as is: its first line, trailing whitespace kept, cut to REASON_MAX characters."""
    return _void_comment(issue, "## Launch stopped by outage:", role, reason, verbatim=True)


def _two_not_started(issue: Issue) -> bool:
    """The two newest receipts are both voided (not started or stopped by an outage, any mix),
    and no result and no RESUME follows the older one."""
    raw = _raw_lines(issue)
    receipts = [i for i, line in enumerate(raw) if _launch_role(line)]
    if len(receipts) < 2 or not set(receipts[-2:]) <= _not_started(issue):
        return False
    return not any(line == RESUME or _result_role(line) for line in raw[receipts[-2] + 1:])


# --- checks (docs/specs/agent-graph-kit.md#checks) ---------------------------------------


def _current(issue: Issue) -> tuple[int | None, str | None, str]:
    """(index, marker, text for messages) of the current result."""
    cur = current_result(issue)
    if cur is None:
        return None, None, "none"
    return cur[0], cur[1], cur[1]


def g1_open(call: Call, facts: Facts) -> str | None:
    """The part of G1 that also holds on the stage path of close: the facts are for this issue,
    and the issue is open."""
    iss = facts.issue
    if iss.number != call.issue:
        return f"G1: facts are for issue #{iss.number}, expected issue #{call.issue}"
    if not iss.open:
        return f"G1: issue #{iss.number} is closed, expected an open issue"
    return None


def g1(call: Call, facts: Facts) -> str | None:
    iss = facts.issue
    if problem := g1_open(call, facts):
        return problem
    if call.role != "close" and (problem := open_blocker_problem(facts)):  # close reads no blockers
        return (f"G1: issue #{iss.number}: {problem}, expected no open blocker "
                f"(the orchestrator picks the issue when its blockers are closed)")
    if "ready" not in iss.labels:
        return f"G1: issue #{iss.number} has no label ready, expected the label ready"
    return _g1_rest(call, facts)


def g1_planner(call: Call, facts: Facts) -> str | None:
    """G1 on the planner path (issue #99): the issue is open and has the label `stage` (the label
    ready is neither required nor denied), no label later or needs-owner, a clean tree, not voided
    twice, not pending. No blocker read: the blocked-by links between stage issues order the start
    of stages, and a stage review reviews a stage that has run."""
    iss = facts.issue
    if problem := g1_open(call, facts):
        return problem
    if not is_stage(iss):
        return f"G1: issue #{iss.number} has no label {STAGE}, expected the label {STAGE} for a planner launch"
    return _g1_rest(call, facts)


def _g1_rest(call: Call, facts: Facts) -> str | None:
    """The part of G1 after the label check: the labels later and needs-owner, the clean tree,
    two voided launches (not for close) and the pending check."""
    iss = facts.issue
    for label in ("later", "needs-owner"):
        if label in iss.labels:
            return f"G1: issue #{iss.number} has the label {label}, expected no label later or needs-owner"
    if not facts.clean:
        return "G1: working tree is not clean, expected a clean tree (git status --porcelain empty)"
    if call.role != "close" and _two_not_started(iss):
        return (f"G1: issue #{iss.number}: the last 2 launches did not start or were stopped by an auto mode "
                f"outage, expected a launch that runs; stop the loop, the owner posts {RESUME}")
    if is_pending(iss):
        lines = _lines(iss)
        j = _newest_launch(lines)
        return (f"G1: issue #{iss.number} is pending: {lines[j]} has no result, "
                f"expected a result of {_launch_role(lines[j])} or {RESUME}")
    return None


def g2(call: Call, facts: Facts) -> str | None:
    lines = _lines(facts.issue)
    _, marker, found = _current(facts.issue)
    if _newest_launch(lines) is None or marker in (BLOCKED, UNVERIFIABLE, RESUME):
        return None
    if marker == WAITING:
        if facts.blockers == ():
            return (f"G2: current result is {WAITING}, but issue #{facts.issue.number} has no blocker link, "
                    f"expected at least one native blocked-by link, all closed")
        if problem := open_blocker_problem(facts):
            return f"G2: current result is {WAITING}: {problem}, expected every blocker closed"
        return None
    return (f"G2: current result is {found}, expected no launch comment yet, "
            f"{BLOCKED}, {UNVERIFIABLE}, {RESUME} or {WAITING} with blockers that are all closed")


def g3(call: Call, facts: Facts) -> str | None:
    _, marker, found = _current(facts.issue)
    if marker not in (GROOMED, FAIL):
        return f"G3: current result is {found}, expected {GROOMED} or {FAIL}"
    if call.continued:
        return None  # the SendMessage target is a name, not a type (docs/specs/agent-graph-kit.md#continuation)
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


def g6_stage(call: Call, facts: Facts) -> str | None:
    """G6 on the stage path of close (issue #97): instead of a QA PASS, every sub-issue is closed.
    Denies when the reads are missing, when the list is empty, for every open sub-issue (by name,
    in any order) and when sub_issues_summary.total is greater than the listed entries (a sub-issue
    the login cannot see; the list may be incomplete, #95)."""
    n = facts.issue.number
    subs, total = facts.sub_issues, facts.sub_issue_total
    if subs is None or total is None:
        return f"G6: the sub-issues of stage issue #{n} were not read, expected both sub-issue reads"
    expected = "expected at least one sub-issue, every sub-issue closed"
    parts = []
    if not subs:
        parts.append(f"stage issue #{n} has no sub-issue")
    names = sorted(sub.name() for sub in subs if sub.state == "open")
    if names:
        parts.append(f"open sub-issue {', '.join(names)}")
    if total > len(subs):
        parts.append(f"the sub-issue count is {total} but the list holds {len(subs)}, so the count shows "
                     f"a sub-issue the list does not hold")
    return f"G6: stage issue #{n}: {'; '.join(parts)}, {expected}" if parts else None


def g7(call: Call, facts: Facts) -> str | None:
    n = returns_since_resume(facts.issue)
    if n < MAX_RETURNS:
        return None
    return (f"G7: {n} returns ({FAIL}, {UNVERIFIABLE} or {BLOCKED}) since the newest {RESUME}, "
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
            return (g5,)  # only the qa-engineer subagent can be continued (docs/specs/agent-graph-kit.md#guarded-calls, docs/specs/agent-graph-kit.md#continuation)
        if call.agent == "qa-codex":
            return (g4,)
        return f"G1: qa call with agent {call.agent or 'none'}, expected qa-codex or qa-engineer"
    if call.role == "close":
        return (g6,)
    return f"G1: unknown role {call.role or 'none'}, expected pm, engineer, qa, planner or close"


PLANNER = "planner"  # the role and the agent of the stage review (issue #99)


def _planner_check(call: Call, facts: Facts) -> str | None:
    """The planner path (issue #99): only a new launch of the agent planner, then G1 of the planner
    path. G2 to G7 do not apply: no current-result check, no return count."""
    if call.continued:
        return "G1: a planner cannot be continued, expected a new launch of the agent planner"
    if call.agent != PLANNER:
        return f"G1: planner call with agent {call.agent or 'none'}, expected agent planner"
    return g1_planner(call, facts)


def is_stage_close(call: Call, issue: Issue) -> bool:
    """The stage path (issue #97): a close of an issue with the label `stage`."""
    return call.role == "close" and is_stage(issue)


def check(call: Call, facts: Facts) -> str | None:
    """None = allow, else the deny message. Never allows a call it cannot place.

    The stage path (a close of an issue with the label `stage`, issue #97) checks only that the
    issue is open and that every sub-issue is closed. The label ready, the labels later and
    needs-owner, the clean tree, the pending check and the QA PASS with verified SHA (G6) do not
    apply: a stage issue never gets ready and never goes through PM, engineer and QA.

    The planner path (a launch of the agent planner, issue #99) checks G1 of the planner path only
    (see `g1_planner`)."""
    if is_stage_close(call, facts.issue):
        return g1_open(call, facts) or g6_stage(call, facts)
    if call.role == PLANNER:
        return _planner_check(call, facts)
    checks = _role_checks(call)
    if isinstance(checks, str):
        return checks
    for g in (g1, *checks):
        reason = g(call, facts)
        if reason is not None:
            return reason
    return None
