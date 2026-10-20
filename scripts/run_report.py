#!/usr/bin/env python3
"""Read-only report of where a stage spends time and tokens (issue #193).

Input is local only: issue comments as JSON and a folder of Claude Code
subagent transcripts. The script calls no network and writes nothing but
Markdown on stdout. Spec: docs/specs/2026-10-19-run-report.md
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
TOKEN_LABELS = ("input", "output", "cache creation", "cache read")

LAUNCH_RE = re.compile(r"^## Launch: (\S+)")
MARKER_RE = re.compile(r"^## (Engineer|QA|PM|Planner): ([A-Z][A-Z ]*)")
PREFIX_OF_ROLE = {"pm": "PM", "engineer": "Engineer", "planner": "Planner"}
FAILURE_TYPES = (
    "Engineer: BLOCKED",
    "QA: FAIL",
    "QA: UNAVAILABLE",
    "QA: UNVERIFIABLE",
    "escalation",
)
PROMPT_RE = re.compile(r"ROLE=(\S+)\s+ISSUE=(\d+)")


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def first_line(body):
    lines = (body or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def prefix_for_role(role):
    if role in PREFIX_OF_ROLE:
        return PREFIX_OF_ROLE[role]
    if role.startswith("qa"):
        return "QA"
    return role


def analyse_issue(issue):
    """Return the comment-based numbers of one issue."""
    comments = sorted(issue.get("comments") or [], key=lambda c: c.get("createdAt", ""))
    launches = []  # (role, time, index)
    markers = []  # (prefix, word, time, index)
    for i, c in enumerate(comments):
        line = first_line(c.get("body"))
        t = c.get("createdAt")
        m = LAUNCH_RE.match(line)
        if m:
            launches.append((m.group(1), t, i))
            continue
        m = MARKER_RE.match(line)
        if m:
            markers.append((m.group(1), m.group(2).strip(), t, i))

    per_role = {}
    for role, _t, idx in launches:
        stat = per_role.setdefault(role, {"launches": 0, "no_result": 0})
        stat["launches"] += 1
        prefix = prefix_for_role(role)
        same = [x[2] for x in launches if prefix_for_role(x[0]) == prefix and x[2] > idx]
        end = min(same) if same else None
        found = any(
            p == prefix and i > idx and (end is None or i < end) for p, _w, _t2, i in markers
        )
        if not found:
            stat["no_result"] += 1

    labels = {
        (l if isinstance(l, str) else l.get("name", "")) for l in (issue.get("labels") or [])
    }
    failures = set()
    for prefix, word, _t, _i in markers:
        key = f"{prefix}: {word}"
        if key in FAILURE_TYPES:
            failures.add(key)
        if word.endswith("NEEDS OWNER"):
            failures.add("escalation")
    if "needs-owner" in labels:
        failures.add("escalation")

    duration = None
    if launches:
        start = parse_time(launches[0][1])
        end_time = issue.get("closedAt")
        if not end_time and markers:
            end_time = markers[-1][2]
        if end_time:
            duration = (parse_time(end_time) - start).total_seconds()
    return {"roles": per_role, "failures": failures, "seconds": duration}


def read_transcripts(folder):
    """Return {issue: {role: [in, out, cache_create, cache_read]}}, or None without a folder."""
    if folder is None or not Path(folder).is_dir():
        return None
    result = {}
    for path in sorted(Path(folder).rglob("*.jsonl")):
        role = issue = None
        seen = set()
        sums = [0, 0, 0, 0]
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            msg = d.get("message") or {}
            if role is None and d.get("type") == "user":
                content = msg.get("content")
                if isinstance(content, list):
                    content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                m = PROMPT_RE.search(content or "")
                if m:
                    role, issue = m.group(1), int(m.group(2))
                continue
            usage = msg.get("usage")
            if d.get("type") == "assistant" and isinstance(usage, dict):
                mid = msg.get("id")
                if mid:
                    if mid in seen:
                        continue
                    seen.add(mid)
                for k, field in enumerate(TOKEN_FIELDS):
                    sums[k] += int(usage.get(field) or 0)
        if role is None:
            continue
        slot = result.setdefault(issue, {}).setdefault(role, [0, 0, 0, 0])
        for k in range(4):
            slot[k] += sums[k]
    return result


def read_codex_usage(path):
    """Return {issue: total tokens (input + cached input + output)} from the Codex QA record
    (scripts/codex_exec.py record_usage), or None for no path, a missing or an empty file.
    A line that is not a JSON object with an integer issue is skipped."""
    if not path or not Path(path).is_file():
        return None
    result = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for raw in lines:
        try:
            d = json.loads(raw)
            n = d["issue"]
            total = sum(d[f] for f in ("input_tokens", "cached_input_tokens", "output_tokens"))
        except (ValueError, KeyError, TypeError):
            continue
        if isinstance(n, int) and isinstance(total, int):
            result[n] = result.get(n, 0) + total
    return result or None


def fmt_duration(seconds):
    if seconds is None:
        return "n/a"
    minutes = int(seconds // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def load_issues(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "comments" in data:
        data = [data]
    if isinstance(data, dict):
        data = [dict(v, number=int(k)) for k, v in data.items()]
    return {int(i["number"]): i for i in data}


def build_report(numbers, issues, transcripts, codex_usage=None):
    out = ["# Run report", ""]
    if not numbers:
        out += ["No issues given.", ""]
    stats = {}
    for n in numbers:
        stats[n] = analyse_issue(issues.get(n, {"comments": []}))
    tokens = {}
    if transcripts is not None:
        for n in numbers:
            tokens[n] = transcripts.get(n, {})

    for n in numbers:
        s = stats[n]
        out.append(f"## Issue #{n}")
        out.append(f"- Launch to close or last result: {fmt_duration(s['seconds'])}")
        if s["roles"]:
            for role, r in sorted(s["roles"].items()):
                out.append(
                    f"- {role}: {r['launches']} launches, {r['no_result']} without a result"
                )
        else:
            out.append("- No launches")
        if transcripts is None:
            out.append("- Tokens: no transcript")
        else:
            roles = tokens[n]
            if not roles:
                out.append("- Tokens: no transcript")
            for role, v in sorted(roles.items()):
                cols = ", ".join(f"{lab} {val}" for lab, val in zip(TOKEN_LABELS, v))
                out.append(f"- Tokens {role}: {cols}")
        if codex_usage is not None and n in codex_usage:
            out.append(f"- Codex QA tokens: {codex_usage[n]}")
        else:
            out.append("- Codex QA tokens: no record")
        out.append("")

    total = len(numbers)
    out.append("## Failure types")
    shares = {}
    for ft in FAILURE_TYPES:
        count = sum(1 for n in numbers if ft in stats[n]["failures"])
        shares[ft] = count
        pct = (100 * count / total) if total else 0
        out.append(f"- {ft}: {count} of {total} issues ({pct:.0f}%)")
    out.append("")

    out.append("## Most expensive")
    timed = sorted((n for n in numbers if stats[n]["seconds"] is not None),
                   key=lambda n: -stats[n]["seconds"])[:3]
    out.append("- Longest launch-to-close time: " + (", ".join(
        f"#{n} ({fmt_duration(stats[n]['seconds'])})" for n in timed) or "none"))
    issue_tokens = {n: sum(sum(v) for v in tokens.get(n, {}).values()) for n in numbers}
    if transcripts is None or not any(issue_tokens.values()):
        out.append("- Most tokens: no transcript data")
        out.append("- Role with the most tokens: no transcript data")
    else:
        top = sorted((n for n in numbers if issue_tokens[n]), key=lambda n: -issue_tokens[n])[:3]
        out.append("- Most tokens: " + ", ".join(f"#{n} ({issue_tokens[n]})" for n in top))
        by_role = {}
        for n in numbers:
            for role, v in tokens.get(n, {}).items():
                by_role[role] = by_role.get(role, 0) + sum(v)
        best = max(by_role, key=lambda r: by_role[r])
        out.append(f"- Role with the most tokens: {best} ({by_role[best]})")
    if total and max(shares.values()) > 0:
        ft = max(FAILURE_TYPES, key=lambda f: shares[f])
        out.append(f"- Failure type with the largest share: {ft} ({shares[ft]} of {total})")
    else:
        out.append("- Failure type with the largest share: none")
    out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comments", required=True, help="JSON file: gh issue view --json number,comments,closedAt,labels")
    ap.add_argument("--stage", type=int, help="stage issue number; its subIssues list is read from the JSON")
    ap.add_argument("--issues", help="comma-separated issue numbers")
    ap.add_argument("--transcripts", help="folder of Claude Code subagent transcripts")
    ap.add_argument("--codex-usage", help="Codex QA token record (codex-qa-usage.jsonl)")
    args = ap.parse_args(argv)
    issues = load_issues(args.comments)
    numbers = []
    if args.stage is not None:
        numbers = [int(x) for x in issues.get(args.stage, {}).get("subIssues", [])]
    if args.issues:
        numbers = [int(x) for x in args.issues.split(",") if x.strip()]
    sys.stdout.write(build_report(numbers, issues, read_transcripts(args.transcripts),
                                   read_codex_usage(args.codex_usage)))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
