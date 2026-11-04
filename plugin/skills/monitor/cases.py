#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Write the retry cases: one JSON line per return round of an issue (issue #264).

  uv run --script cases.py collect --project <name> (--issues <file> | --repo-slug <owner/repo> --stage <n>) [--repo <path>]

A round starts at a round marker (QA FAIL, UNVERIFIABLE, INVALID, UNAVAILABLE, Engineer BLOCKED, a
`## ... NEEDS OWNER` marker) that has a launch receipt after it before the next round marker. Each case
names the marker, the failed criterion lines, what came next and what the round cost. The collector
sorts and judges nothing. It writes no comment and changes no label: its only `gh` calls are reads.
Spec: docs/specs/2026-11-04-kit-monitoring.md, Part 2
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FIELDS = ("id", "project", "stage", "issue", "round", "marker", "comment_url", "failed_lines", "criteria",
          "next_markers", "body_edited", "commit", "files_changed", "lines_added", "lines_removed",
          "tokens", "seconds")
ROUND_MARKERS = ("## QA: FAIL", "## QA: UNVERIFIABLE", "## QA: INVALID", "## QA: UNAVAILABLE",
                 "## Engineer: BLOCKED")
RESULT_PREFIXES = ("## PM: ", "## Engineer: ", "## QA: ")
FAILED_SUFFIXES = (" - FAIL", " - INVALID", " - UNVERIFIABLE")
COMMITS_RE = re.compile(r"^Commits:\s*(\S+\.\.\S+)\s*$")
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens")
EDITS_QUERY = ("query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) "
               "{ issue(number: $number) { userContentEdits(first: 100) { nodes { editedAt } } } } }")


def _load(name, *parts):
    src = Path(__file__).resolve().parent.parent.joinpath(*parts)
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rr = _load("agk_run_record", "run-record", "run_record.py")
st = _load("agk_steps", "monitor", "steps.py")


def cases_path():
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return base / "agent-graph-kit" / "retry-cases.jsonl"


# --- comment kinds --------------------------------------------------------------------------

def first_line(comment):
    lines = (comment.get("body") or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def is_round_marker(line):
    return line in ROUND_MARKERS or (line.startswith("## ") and line.endswith("NEEDS OWNER"))


def is_receipt(line):
    return bool(rr.LAUNCH_RE.match(line))


def is_result(line):
    return line.startswith(RESULT_PREFIXES)


def counted(comment):
    """A comment counts when it has no `authorAssociation` field (saved fixtures) or it is `OWNER`."""
    return "authorAssociation" not in comment or comment.get("authorAssociation") == "OWNER"


def time_of(comment):
    try:
        return rr.parse_time(comment["createdAt"]) if comment.get("createdAt") else None
    except (ValueError, TypeError):
        return None


# --- rounds ---------------------------------------------------------------------------------

def rounds(comments):
    """Return a list of (start index, end index) into `comments`: the comments of each round, end exclusive."""
    markers = [i for i, c in enumerate(comments) if is_round_marker(first_line(c))]
    starting = []
    for k, i in enumerate(markers):
        stop = markers[k + 1] if k + 1 < len(markers) else len(comments)
        if any(is_receipt(first_line(c)) for c in comments[i + 1:stop]):
            starting.append(i)
    return [(i, starting[k + 1] if k + 1 < len(starting) else len(comments)) for k, i in enumerate(starting)]


def norm(text):
    return " ".join(text.split())


def failed_lines(body):
    out = []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line.startswith("- [ ]") and line.endswith(FAILED_SUFFIXES):
            out.append(line)
    return out


def criteria_of(lines, issue_body):
    """For each failed line, the first issue-body line `- [ ] <text>` whose text equals the QA text."""
    body = [raw.strip() for raw in (issue_body or "").splitlines()]
    body = [line for line in body if line.startswith("- [ ]")]
    out = []
    for line in lines:
        text = line[len("- [ ]"):]
        for suffix in FAILED_SUFFIXES:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
                break
        want = norm(text)
        match = next((b for b in body if norm(b[len("- [ ]"):]) == want), None)
        if match is not None:
            out.append(match)
    return out


def edit_times(issue):
    """The body edit times of an issue, or None when the issue has no edit data."""
    edits = issue.get("userContentEdits")
    if edits is None:
        return None
    if isinstance(edits, dict):
        edits = edits.get("nodes") or []
    times = []
    for e in edits if isinstance(edits, list) else []:
        when = e.get("editedAt") if isinstance(e, dict) else e
        try:
            times.append(rr.parse_time(when))
        except (ValueError, TypeError):
            continue
    return times


def inside(t, start, end, last):
    """True when t falls inside the round [start, end); the last round includes its end."""
    if t is None or start is None:
        return False
    if end is None:
        return t >= start
    return start <= t <= end if last else start <= t < end


def numstat(repo, commit):
    """(files, added, removed) from `git diff --numstat`, or (None, None, None) on any failure."""
    if not repo or not commit:
        return None, None, None
    try:
        res = subprocess.run(["git", "-C", str(repo), "diff", "--numstat", commit],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    if res.returncode != 0:
        return None, None, None
    files = added = removed = 0
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        files += 1
        added += int(parts[0]) if parts[0].isdigit() else 0
        removed += int(parts[1]) if parts[1].isdigit() else 0
    return files, added, removed


def read_jsonl(path):
    """The JSON object lines of a file, last line per `id` (lines without `id` all kept); [] when missing."""
    try:
        raws = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    by_id, rows = {}, []
    for raw in raws:
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("id") is None:
            rows.append(d)
        else:
            by_id[d["id"]] = d
    return rows + list(by_id.values())


def row_time(row, key):
    try:
        return rr.parse_time(row[key]) if row.get(key) else None
    except (ValueError, TypeError):
        return None


def same_issue(row, project, number):
    try:
        return row.get("project") == project and row.get("issue") is not None and int(row["issue"]) == number
    except (ValueError, TypeError):
        return False


def tokens_of(record, project, number, start, end, last):
    out = {}
    for row in record:
        if row.get("provider") is None or not same_issue(row, project, number):
            continue
        if not inside(row_time(row, "start"), start, end, last):
            continue
        total = sum(int(row.get(k) or 0) for k in TOKEN_FIELDS)
        out[row["provider"]] = out.get(row["provider"], 0) + total
    return out or None


def seconds_of(steps, project, number, start, end, last):
    matched, total = False, 0.0
    for row in steps:
        if not same_issue(row, project, number) or not inside(row_time(row, "time"), start, end, last):
            continue
        matched = True
        value = row.get("duration_s")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += value
    if not matched:
        return None
    return int(total) if total == int(total) else round(total, 3)


def issue_cases(project, stage, number, issue, repo=None, record=(), steps=()):
    comments = [c for c in issue.get("comments") or [] if isinstance(c, dict) and counted(c)]
    edits = edit_times(issue)
    spans = rounds(comments)
    cases = []
    for n, (i, j) in enumerate(spans, 1):
        marker = comments[i]
        start = time_of(marker)
        last = j >= len(comments)
        end = time_of(comments[j]) if not last else time_of(comments[-1])
        inner = comments[i + 1:j]
        failed = failed_lines(marker.get("body")) if first_line(marker).startswith("## QA: ") else []
        done = next((c for c in inner if first_line(c) == "## Engineer: DONE"), None)
        commit = None
        if done is not None:
            for raw in (done.get("body") or "").splitlines():
                m = COMMITS_RE.match(raw.strip())
                if m:
                    commit = m.group(1)
                    break
        if edits is None or start is None:
            edited = None
        else:
            edited = any(inside(t, start, end, last) for t in edits)
        files, added, removed = numstat(repo, commit)
        case = {"id": f"{project}:{number}:{n}", "project": project, "stage": stage, "issue": number,
                "round": n, "marker": first_line(marker), "comment_url": marker.get("url") or None,
                "failed_lines": failed, "criteria": criteria_of(failed, issue.get("body")),
                "next_markers": [first_line(c) for c in inner if is_result(first_line(c))],
                "body_edited": edited, "commit": commit, "files_changed": files, "lines_added": added,
                "lines_removed": removed,
                "tokens": tokens_of(record, project, number, start, end, last) if start else None,
                "seconds": seconds_of(steps, project, number, start, end, last) if start else None}
        cases.append({k: case[k] for k in FIELDS})
    return cases


def build_cases(project, stage, issues, repo=None):
    record = read_jsonl(rr.record_path())
    steps = read_jsonl(st.steps_path())
    out = []
    for number, issue in sorted(issues.items()):
        out.extend(issue_cases(project, stage, number, issue, repo, record, steps))
    return out


# --- gh reads (read only) -------------------------------------------------------------------

def gh(*args):
    res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {res.stderr.strip()}")
    return res.stdout


def json_values(text):
    """All JSON values of a text (`gh api --paginate` prints one array per page)."""
    dec, i, out = json.JSONDecoder(), 0, []
    text = text.strip()
    while i < len(text):
        value, i = dec.raw_decode(text, i)
        out.append(value)
        while i < len(text) and text[i].isspace():
            i += 1
    return out


def read_repo(slug, stage):
    owner, _, name = slug.partition("/")
    numbers = []
    for page in json_values(gh("api", f"repos/{slug}/issues/{stage}/sub_issues", "--paginate")):
        items = page if isinstance(page, list) else [page]
        numbers.extend(int(item["number"]) for item in items if isinstance(item, dict) and "number" in item)
    issues = {}
    for number in numbers:
        issue = json.loads(gh("issue", "view", str(number), "--repo", slug, "--json",
                              "number,body,comments,closedAt"))
        data = json.loads(gh("api", "graphql", "-f", f"query={EDITS_QUERY}", "-f", f"owner={owner}",
                             "-f", f"name={name}", "-F", f"number={number}"))
        edits = (((data.get("data") or {}).get("repository") or {}).get("issue") or {}).get("userContentEdits")
        if edits is not None:
            issue["userContentEdits"] = edits
        issue["number"] = number
        issues[number] = issue
    return issues


def write_cases(cases):
    path = cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, separators=(",", ":")) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def collect(args):
    if args.issues:
        issues = rr.load_issues(args.issues)
    else:
        if args.stage is None:
            print("cases: --repo-slug needs --stage", file=sys.stderr)
            return 2
        try:
            issues = read_repo(args.repo_slug, args.stage)
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as e:
            print(f"cases: {e}", file=sys.stderr)
            return 1
    cases = build_cases(args.project, args.stage, issues, args.repo)
    path = write_cases(cases)
    print(f"Wrote {len(cases)} cases to {path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="write one row per return round")
    c.add_argument("--project", required=True)
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--issues", help="JSON file in the form that run_record.py load_issues reads")
    src.add_argument("--repo-slug", help="owner/repo: read the stage's sub-issues with gh (read only)")
    c.add_argument("--stage", type=int)
    c.add_argument("--repo", help="the project repo on this machine, for git diff --numstat")
    args = ap.parse_args(argv)
    return collect(args)


if __name__ == "__main__":
    sys.exit(main())
