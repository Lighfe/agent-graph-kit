#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Write the run record: one JSON line per Claude subagent launch and model (issue #242).

  uv run --script run_record.py write --project <name> --stage <n> --issues <issues.json> --transcripts <folder>

Reads local files only and calls no network. It appends to the record file and writes no prompt
text, comment text or output text. Spec: docs/specs/2026-10-21-run-record.md
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
FIELDS = ("v", "id", "project", "stage", "issue", "role", "provider", "model", "effort",
          "input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens",
          "start", "end", "retry", "estimate", "source")
USAGE_FIELDS = (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                ("cache_creation_tokens", "cache_creation_input_tokens"),
                ("cache_read_tokens", "cache_read_input_tokens"))
PROMPT_RE = re.compile(r"ROLE=(\S+)\s+ISSUE=(\d+)")
LAUNCH_RE = re.compile(r"^## Launch: (\S+)")
PREFIX_OF_ROLE = {"pm": "PM", "engineer": "Engineer", "planner": "Planner"}


def record_path():
    env = os.environ.get("RUN_RECORD_FILE")
    if env:
        return Path(env)
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return base / "agent-graph-kit" / "run-record.jsonl"


def role_group(role):
    if role in PREFIX_OF_ROLE:
        return PREFIX_OF_ROLE[role]
    if role.startswith("qa"):
        return "QA"
    return role


def parse_time(text):
    dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if dt else None


def load_issues(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "comments" in data:
        data = [data]
    if isinstance(data, dict):
        data = [dict(v, number=int(k)) for k, v in data.items()]
    return {int(i["number"]): i for i in data}


def receipts(issue):
    """Return {role group: sorted list of receipt times} from the launch comments of one issue."""
    out = {}
    for c in issue.get("comments") or []:
        lines = (c.get("body") or "").strip().splitlines()
        m = LAUNCH_RE.match(lines[0].strip()) if lines else None
        if not m or not c.get("createdAt"):
            continue
        try:
            out.setdefault(role_group(m.group(1)), []).append(parse_time(c["createdAt"]))
        except ValueError:
            continue
    return {k: sorted(v) for k, v in out.items()}


def read_launch(path):
    """Return a dict with role, issue, effort, start, end and per-model sums, or None."""
    role = issue = effort = None
    first_user_seen = False
    seen = set()
    models = {}
    times = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for raw in lines:
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if effort is None and isinstance(d.get("effort"), str):
            effort = d["effort"]
        msg = d.get("message") or {}
        if not isinstance(msg, dict) or not msg:
            continue
        ts = d.get("timestamp")
        if ts:
            try:
                times.append(parse_time(ts))
            except ValueError:
                pass
        if not first_user_seen and d.get("type") == "user":
            first_user_seen = True
            content = msg.get("content")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            m = PROMPT_RE.search(content if isinstance(content, str) else "")
            if m:
                role, issue = m.group(1), int(m.group(2))
            else:
                return None
            continue
        usage = msg.get("usage")
        if d.get("type") == "assistant" and isinstance(usage, dict):
            mid = msg.get("id")
            if mid:
                if mid in seen:
                    continue
                seen.add(mid)
            model = msg.get("model")
            if not isinstance(model, str) or not model:
                continue
            sums = models.setdefault(model, dict.fromkeys((f for f, _ in USAGE_FIELDS), 0))
            for out_field, in_field in USAGE_FIELDS:
                sums[out_field] += int(usage.get(in_field) or 0)
    if role is None:
        return None
    return {"role": role, "issue": issue, "effort": effort, "models": models,
            "start": times[0] if times else None, "end": times[-1] if times else None,
            "file_id": path.name[:-len(".jsonl")]}


def build_lines(project, stage, issues, folder):
    launches = []
    for path in sorted(Path(folder).rglob("*.jsonl")):
        launch = read_launch(path)
        if launch and launch["issue"] in issues and launch["models"]:
            launches.append(launch)
    # retry: launch receipts of the same role group before this launch
    groups = {}
    for launch in launches:
        groups.setdefault((launch["issue"], role_group(launch["role"])), []).append(launch)
    for (n, group), items in groups.items():
        items.sort(key=lambda x: (x["start"] is None, x["start"] or datetime.min.replace(tzinfo=timezone.utc)))
        times = receipts(issues[n]).get(group, [])
        for rank, launch in enumerate(items):
            if times and launch["start"] is not None:
                launch["retry"] = max(0, sum(1 for t in times if t <= launch["start"]) - 1)
            else:
                launch["retry"] = rank
    lines = []
    for launch in launches:
        for model, sums in sorted(launch["models"].items()):
            row = {"v": VERSION, "id": f"{project}:{launch['file_id']}:{model}", "project": project,
                   "stage": stage, "issue": launch["issue"], "role": launch["role"],
                   "provider": "claude", "model": model, "effort": launch["effort"], **sums,
                   "start": iso(launch["start"]), "end": iso(launch["end"]),
                   "retry": launch["retry"], "estimate": False, "source": "transcript"}
            lines.append({k: row[k] for k in FIELDS})
    return lines


def first_receipt(issue):
    """Return the time of the first `## Launch:` receipt of any role, or None."""
    times = [t for ts in receipts(issue).values() for t in ts]
    return min(times) if times else None


def close_time(issue):
    try:
        return parse_time(issue["closedAt"]) if issue.get("closedAt") else None
    except ValueError:
        return None


def window(issue, now=None):
    """Return (start, end) of the issue window, or None when the issue has no receipt."""
    start = first_receipt(issue)
    if start is None:
        return None
    return start, close_time(issue) or now or datetime.now(timezone.utc)


def codex_lines(usage_file, issues, project, stage):
    """Return (lines, skipped): one qa-codex line per Codex record line inside the window of its issue."""
    lines, skipped = [], 0
    try:
        raws = Path(usage_file).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return lines, skipped
    windows = {}
    for raw in raws:
        if not raw.strip():
            continue
        try:
            d = json.loads(raw)
            n, when = d.get("issue"), d.get("time")
            if n is None or not when:
                raise ValueError("incomplete")
            n = int(n)
            t = parse_time(when)
        except (ValueError, TypeError, AttributeError):
            skipped += 1
            continue
        if n not in issues:
            skipped += 1
            continue
        if n not in windows:
            windows[n] = window(issues[n])
        w = windows[n]
        if w is None or not w[0] <= t <= w[1]:
            skipped += 1
            continue
        row = {"v": VERSION, "id": f"{project}:codex:{n}:{when}", "project": project, "stage": stage,
               "issue": n, "role": "qa-codex", "provider": "codex", "model": d.get("model"),
               "effort": d.get("effort"), "input_tokens": int(d.get("input_tokens") or 0),
               "output_tokens": int(d.get("output_tokens") or 0), "cache_creation_tokens": 0,
               "cache_read_tokens": int(d.get("cached_input_tokens") or 0),
               "start": when, "end": when, "retry": 0, "estimate": False, "source": "codex-record"}
        lines.append({k: row[k] for k in FIELDS})
    return lines, skipped


def escalations(issue):
    count = 0
    for c in issue.get("comments") or []:
        body = (c.get("body") or "").strip().splitlines()
        first = body[0].strip() if body else ""
        if first.startswith("## ") and first.endswith("NEEDS OWNER"):
            count += 1
    if count == 0:
        names = [(x.get("name") if isinstance(x, dict) else x) for x in issue.get("labels") or []]
        if "needs-owner" in names:
            count = 1
    return count


def issue_lines(issues, project, stage):
    lines = []
    for n, issue in sorted(issues.items()):
        row = {"v": VERSION, "id": f"{project}:issue:{n}", "project": project, "stage": stage,
               "issue": n, "role": "issue", "provider": None, "model": None, "effort": None,
               "input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0,
               "start": iso(first_receipt(issue)), "end": iso(close_time(issue)), "retry": 0,
               "estimate": False, "source": "transcript", "escalations": escalations(issue)}
        lines.append(row)
    return lines


def append_lines(lines):
    """Append one JSON line per entry; skip an id that is in the file already (orchestrator excepted).
    Return the number of lines written."""
    path = record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    known = set()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                known.add(json.loads(raw).get("id"))
            except (ValueError, AttributeError):
                continue
    written = 0
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            if line.get("role") != "orchestrator":
                if line.get("id") in known:
                    continue
                known.add(line.get("id"))
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
            written += 1
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="append the Claude subagent lines of a stage")
    w.add_argument("--project", required=True)
    w.add_argument("--stage", type=int, required=True)
    w.add_argument("--issues", required=True, help="JSON file: gh issue view --json number,comments,closedAt,labels")
    w.add_argument("--transcripts", required=True, help="folder of Claude Code subagent transcripts")
    w.add_argument("--codex-usage", help="Codex QA token record codex-qa-usage.jsonl")
    args = ap.parse_args(argv)
    issues = load_issues(args.issues)
    lines = []
    if Path(args.transcripts).is_dir():
        lines = build_lines(args.project, args.stage, issues, args.transcripts)
    else:
        print(f"No transcript folder: {args.transcripts}; no Claude lines")
    if args.codex_usage:
        codex, skipped = codex_lines(args.codex_usage, issues, args.project, args.stage)
        lines += codex
        if skipped:
            print(f"skipped {skipped} Codex record lines")
    lines += issue_lines(issues, args.project, args.stage)
    written = append_lines(lines)
    print(f"Wrote {written} lines to {record_path()} ({len(lines) - written} already there)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
