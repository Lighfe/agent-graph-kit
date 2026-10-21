#!/usr/bin/env python3
"""Read-only report of where a stage spends time and tokens (issue #193).

Input is local only: issue comments as JSON and a folder of Claude Code
subagent transcripts. The script calls no network and writes nothing but
Markdown on stdout. Spec: docs/specs/2026-10-19-run-report.md
"""

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The transcript reading lives once, in the run-record skill; the report loads it from there.
_spec = importlib.util.spec_from_file_location(
    "run_record", ROOT / "plugin" / "skills" / "run-record" / "run_record.py")
run_record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_record)
parse_time = run_record.parse_time
load_issues = run_record.load_issues
DEFAULT_WEIGHTS = ROOT / "docs" / "run-weights.json"

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
        launch = run_record.read_launch(path)
        if launch is None:
            continue
        slot = result.setdefault(launch["issue"], {}).setdefault(launch["role"], [0, 0, 0, 0])
        for sums in launch["models"].values():
            for k, (field, _src) in enumerate(run_record.USAGE_FIELDS):
                slot[k] += sums[field]
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


# --- Report from the run record (issue #245). Spec: docs/specs/2026-10-21-run-record.md ---

KINDS = (("input", "input_tokens"), ("output", "output_tokens"),
         ("cache_creation", "cache_creation_tokens"), ("cache_read", "cache_read_tokens"))
PROVIDERS = ("claude", "codex")
WEIGHTED_LABEL = "estimate from price ratios, not measured plan use"
ORCHESTRATOR_LABEL = "measured up to the report; not complete"


class ReportError(Exception):
    pass


def load_weights(path):
    """Read the weights file; a missing file, bad JSON or a missing factor is a ReportError naming the file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as e:
        raise ReportError(f"weights file {path}: cannot read ({e})")
    for provider in PROVIDERS:
        table = data.get(provider) if isinstance(data, dict) else None
        for kind, _field in KINDS:
            if not isinstance(table, dict) or isinstance(table.get(kind), bool) \
                    or not isinstance(table.get(kind), (int, float)):
                raise ReportError(f"weights file {path}: no factor for {provider}.{kind}")
    return data


def weighted(line, weights):
    """Weighted token total of one record line: the sum of the token counts times the factors of its provider."""
    table = weights.get(line.get("provider")) if isinstance(weights, dict) else None
    if not isinstance(table, dict):
        raise ReportError(f"weights: no factors for provider {line.get('provider')!r}")
    total = 0.0
    for kind, field in KINDS:
        if kind not in table:
            raise ReportError(f"weights: no factor for {line.get('provider')}.{kind}")
        total += float(line.get(field) or 0) * table[kind]
    return total


def read_jsonl(path):
    """Return (objects, number of skipped lines). A line that is not a JSON object is skipped."""
    rows, skipped = [], 0
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            skipped += 1
            continue
        if isinstance(d, dict):
            rows.append(d)
        else:
            skipped += 1
    return rows, skipped


def read_record(path, stage=None, project=None):
    """Return (lines, skipped). Only the last line of an id counts; stage and project filter."""
    rows, skipped = read_jsonl(path)
    last = {}
    for i, d in enumerate(rows):
        last[d.get("id") if d.get("id") is not None else ("noid", i)] = d
    lines = [d for d in last.values()
             if (stage is None or d.get("stage") == stage)
             and (project is None or d.get("project") == project)]
    return lines, skipped


def read_limits(path, project=None):
    """Return {(project, stage): {point: entry}}; for one point entered twice the later `time` counts."""
    rows, _skipped = read_jsonl(path)
    result = {}
    for d in rows:
        if d.get("point") not in ("start", "end") or (project is not None and d.get("project") != project):
            continue
        slot = result.setdefault((d.get("project"), d.get("stage")), {})
        old = slot.get(d["point"])
        if old is None or str(d.get("time") or "") >= str(old.get("time") or ""):
            slot[d["point"]] = d
    return result


def _num(x):
    return f"{x:,.1f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"


def _tokens_table(out, title, key_name, lines, key):
    groups = {}
    for ln in lines:
        k = "estimate" if ln.get("estimate") else key(ln)
        slot = groups.setdefault(k, [0, 0, 0, 0])
        for i, (_kind, field) in enumerate(KINDS):
            slot[i] += int(ln.get(field) or 0)
    out += [f"## {title}", "", f"| {key_name} | input | output | cache creation | cache read |", "|---|---|---|---|---|"]
    for k in sorted(groups, key=lambda x: (x == "estimate", str(x))):
        out.append(f"| {k} | " + " | ".join(_num(v) for v in groups[k]) + " |")
    if not groups:
        out.append("| none | 0 | 0 | 0 | 0 |")
    out.append("")


def build_record_report(lines, weights, limits=None, skipped=0, stage=None):
    out = ["# Run report (from the run record)", ""]
    if skipped:
        out += [f"Skipped {skipped} invalid line{'s' if skipped != 1 else ''} in the record.", ""]
    usage = [ln for ln in lines if ln.get("role") != "issue"]
    issue_lines = [ln for ln in lines if ln.get("role") == "issue"]

    def role_key(ln):
        role = ln.get("role")
        return f"orchestrator ({ORCHESTRATOR_LABEL})" if role == "orchestrator" else str(role)

    _tokens_table(out, "Tokens per role", "role", usage, role_key)
    _tokens_table(out, "Tokens per issue", "issue", usage,
                  lambda ln: f"#{ln['issue']}" if ln.get("issue") is not None else "none")
    _tokens_table(out, "Tokens per model", "model", usage, lambda ln: str(ln.get("model")))
    _tokens_table(out, "Tokens per project", "project", usage, lambda ln: str(ln.get("project")))

    out += ["## Weighted totals per provider", "", f"Label: {WEIGHTED_LABEL}. Claude and Codex are never added together.", "",
            "| provider | measured | estimate |", "|---|---|---|"]
    for provider in PROVIDERS:
        mine = [ln for ln in usage if ln.get("provider") == provider]
        measured = sum(weighted(ln, weights) for ln in mine if not ln.get("estimate"))
        est = sum(weighted(ln, weights) for ln in mine if ln.get("estimate"))
        out.append(f"| {provider} | {_num(measured)} | {_num(est)} |")
    out.append("")

    out += ["## Time and escalations per issue", "", "| issue | time | escalations |", "|---|---|---|"]
    by_issue = {}
    for ln in issue_lines:
        by_issue[ln.get("issue")] = ln
    for n in sorted(by_issue, key=lambda x: (x is None, x)):
        ln = by_issue[n]
        try:
            seconds = (parse_time(ln["end"]) - parse_time(ln["start"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            seconds = None
        out.append(f"| #{n} | {fmt_duration(seconds)} | {int(ln.get('escalations') or 0)} |")
    if not by_issue:
        out.append("| none | n/a | 0 |")
    out.append("")

    out += ["## Retries", "", "Highest retry value per role and issue (0 means no repeat).", "",
            "| role | issue | retry |", "|---|---|---|"]
    retries = {}
    for ln in usage:
        if ln.get("issue") is None or ln.get("estimate"):
            continue
        k = (str(ln.get("role")), ln["issue"])
        retries[k] = max(retries.get(k, 0), int(ln.get("retry") or 0))
    for (role, n), v in sorted(retries.items()):
        out.append(f"| {role} | #{n} | {v} |")
    if not retries:
        out.append("| none | none | 0 |")
    out.append("")

    if limits is not None:
        out += ["## Plan limit per stage", "",
                f"Percent of the session limit, entered by hand, next to the weighted total ({WEIGHTED_LABEL}).", ""]
        stages = sorted({(ln.get("project"), ln.get("stage")) for ln in usage}, key=lambda x: (str(x[0]), x[1] is None, x[1] or 0))
        for project, st in stages:
            entry = limits.get((project, st), {})
            totals = []
            for provider in PROVIDERS:
                mine = [ln for ln in usage if ln.get("provider") == provider and not ln.get("estimate")
                        and ln.get("project") == project and ln.get("stage") == st]
                if mine:
                    totals.append(f"{provider} {_num(sum(weighted(ln, weights) for ln in mine))}")
            def point(name):
                e = entry.get(name)
                return f"{name} {_num(e['percent'])}%" if e and "percent" in e else f"{name} not entered"
            plans = sorted({str(e.get("plan")) for e in entry.values() if e.get("plan")})
            plan = f" (plan {', '.join(plans)})" if plans else ""
            out.append(f"- {project} stage {st}: weighted {'; '.join(totals) or 'none'}; {point('start')}; {point('end')}{plan}")
        if not stages:
            out.append("- no stages in the record")
        out.append("")
    return "\n".join(out)


def main_record(args):
    try:
        weights = load_weights(args.weights or DEFAULT_WEIGHTS)
        lines, skipped = read_record(args.record, args.stage, args.project)
        limits = read_limits(args.limits, args.project) if args.limits else None
        sys.stdout.write(build_record_report(lines, weights, limits, skipped, args.stage))
    except (ReportError, OSError, UnicodeError) as e:
        print(f"run_report: {e}", file=sys.stderr)
        return 1
    sys.stdout.write("\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comments", help="JSON file: gh issue view --json number,comments,closedAt,labels")
    ap.add_argument("--stage", type=int, help="stage issue number; its subIssues list is read from the JSON")
    ap.add_argument("--issues", help="comma-separated issue numbers")
    ap.add_argument("--transcripts", help="folder of Claude Code subagent transcripts")
    ap.add_argument("--codex-usage", help="Codex QA token record (codex-qa-usage.jsonl)")
    ap.add_argument("--record", help="run record file (run-record.jsonl): print the report from it")
    ap.add_argument("--weights", help="weights file (default: docs/run-weights.json)")
    ap.add_argument("--limits", help="plan limit file (run-record-limits.jsonl)")
    ap.add_argument("--project", help="with --record: only this project")
    args = ap.parse_args(argv)
    if args.record:
        return main_record(args)
    if not args.comments:
        ap.error("--comments is required without --record")
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
