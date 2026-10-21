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
# The first value is a guess: the writer runs before the orchestrator writes its report and final
# answer, so the number it sees is too low, and nobody has measured by how much. 1.1 means "about
# ten percent more is spent after the writer runs". Change it when real stage data shows better.
ORCHESTRATOR_ESTIMATE_FACTOR = 1.1
# Checked on real main-session transcripts (issue #244): the input and cache token totals of the
# `cost-state` record equal the sum of the main transcript and the subagent transcripts, so the
# totals include the subagents and the orchestrator line is the totals minus the subagent lines.
COST_STATE_INCLUDES_SUBAGENTS = True
COST_STATE_FIELDS = (("input_tokens", "inputTokens"), ("output_tokens", "outputTokens"),
                     ("cache_creation_tokens", "cacheCreationInputTokens"),
                     ("cache_read_tokens", "cacheReadInputTokens"))
PREFIX_OF_ROLE = {"pm": "PM", "engineer": "Engineer", "planner": "Planner"}


def record_path():
    env = os.environ.get("RUN_RECORD_FILE")
    if env:
        return Path(env)
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return base / "agent-graph-kit" / "run-record.jsonl"


def limits_path():
    env = os.environ.get("RUN_RECORD_LIMITS_FILE")
    return Path(env) if env else record_path().parent / "run-record-limits.jsonl"


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


def read_main(path):
    """Return {session, times, cost (last usable cost-state per model or None), sums (assistant sums)}."""
    session = path.name[:-len(".jsonl")]
    times, cost, seen, sums = [], None, set(), {}
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
        if d.get("type") == "cost-state":
            usage = d.get("modelUsage")
            try:
                parsed = {m: {out: int(u.get(src) or 0) for out, src in COST_STATE_FIELDS}
                          for m, u in usage.items()}
            except (AttributeError, TypeError, ValueError):
                continue
            if any(v for u in parsed.values() for v in u.values()):
                cost = parsed
            continue
        msg = d.get("message")
        if not isinstance(msg, dict) or not msg:
            continue
        if d.get("timestamp"):
            try:
                times.append(parse_time(d["timestamp"]))
            except ValueError:
                pass
        usage = msg.get("usage")
        if d.get("type") == "assistant" and isinstance(usage, dict):
            mid, model = msg.get("id"), msg.get("model")
            if mid:
                if mid in seen:
                    continue
                seen.add(mid)
            if not isinstance(model, str) or not model:
                continue
            row = sums.setdefault(model, dict.fromkeys((f for f, _ in USAGE_FIELDS), 0))
            for out_field, in_field in USAGE_FIELDS:
                row[out_field] += int(usage.get(in_field) or 0)
    return {"session": session, "times": times, "cost": cost, "sums": sums}


def orchestrator_lines(path, project, stage, subtract=()):
    """Return the measured and the estimate line of each model of the main session at `path`.

    Source is `cost-state` (minus the Claude subagent lines in `subtract`, when the totals include
    them) or, when it is missing or unusable, the sum of the assistant messages of the transcript."""
    main = read_main(Path(path))
    if main is None:
        return []
    if main["cost"]:
        source, totals = "session-total", {m: dict(v) for m, v in main["cost"].items()}
        if COST_STATE_INCLUDES_SUBAGENTS:
            for line in subtract:
                if line.get("model") in totals:
                    for f, _ in USAGE_FIELDS:
                        totals[line["model"]][f] = max(0, totals[line["model"]][f] - line[f])
    else:
        source, totals = "transcript", main["sums"]
    times = main["times"]
    lines = []
    for model, sums in sorted(totals.items()):
        if not any(sums.values()):
            continue
        for kind, factor in (("measured", 1), ("estimate", ORCHESTRATOR_ESTIMATE_FACTOR)):
            row = {"v": VERSION, "id": f"{project}:{main['session']}:{model}:{kind}", "project": project,
                   "stage": stage, "issue": None, "role": "orchestrator", "provider": "claude",
                   "model": model, "effort": None,
                   **{f: round(sums[f] * factor) for f, _ in USAGE_FIELDS},
                   "start": iso(times[0]) if times else None, "end": iso(times[-1]) if times else None,
                   "retry": 0, "estimate": kind == "estimate", "source": source}
            lines.append({k: row[k] for k in FIELDS})
    return lines


def is_subagent_transcript(path):
    """True when the file is under a `subagents` folder, or its first user message has a `ROLE=... ISSUE=...` prompt."""
    if path.parent.name == "subagents":
        return True
    try:
        with path.open(encoding="utf-8") as f:
            for raw in f:
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("type") == "user":
                    content = (d.get("message") or {}).get("content")
                    if isinstance(content, list):
                        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                    return bool(PROMPT_RE.search(content if isinstance(content, str) else ""))
    except (OSError, UnicodeError):
        pass
    return False


def project_folder(folder):
    """The folder itself when it directly holds a main-session transcript, else the nearest ancestor that does."""
    start = Path(folder).resolve()
    for d in (start, *start.parents):
        if any(not is_subagent_transcript(p) for p in d.glob("*.jsonl")):
            return d
    return None


def newest_main_transcript(folder):
    top = project_folder(folder)
    if top is None:
        return None
    files = [p for p in top.glob("*.jsonl") if not is_subagent_transcript(p)]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


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


def write_limit(args):
    """Append one hand-entered plan limit line; a percent outside 0 to 100 writes nothing."""
    if not 0 <= args.percent <= 100:
        print(f"run_record: percent must be between 0 and 100, got {args.percent}", file=sys.stderr)
        return 2
    row = {"v": VERSION, "project": args.project, "stage": args.stage, "time": iso(datetime.now(timezone.utc)),
           "point": args.point, "percent": args.percent, "plan": args.plan}
    path = limits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    print(f"Wrote the {args.point} limit of stage {args.stage} to {path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="append the Claude subagent lines of a stage")
    w.add_argument("--project", required=True)
    w.add_argument("--stage", type=int, required=True)
    w.add_argument("--issues", required=True, help="JSON file: gh issue view --json number,comments,closedAt,labels")
    w.add_argument("--transcripts", required=True, help="folder of Claude Code subagent transcripts")
    w.add_argument("--orchestrator-transcript", help="main-session transcript; default: the newest one of the project folder")
    w.add_argument("--codex-usage", help="Codex QA token record codex-qa-usage.jsonl")
    lim = sub.add_parser("limit", help="enter the percent of the session limit used at the start or end of a stage")
    lim.add_argument("--project", required=True)
    lim.add_argument("--stage", type=int, required=True)
    lim.add_argument("--point", required=True, choices=("start", "end"))
    lim.add_argument("--percent", required=True, type=float)
    lim.add_argument("--plan", required=True, help="plan name, free text")
    args = ap.parse_args(argv)
    if args.cmd == "limit":
        return write_limit(args)
    issues = load_issues(args.issues)
    lines = []
    if Path(args.transcripts).is_dir():
        lines = build_lines(args.project, args.stage, issues, args.transcripts)
    else:
        print(f"No transcript folder: {args.transcripts}; no Claude lines")
    orch = Path(args.orchestrator_transcript) if args.orchestrator_transcript else newest_main_transcript(args.transcripts)
    if orch is None:
        print("No main-session transcript found; no orchestrator line")
    else:
        if not args.orchestrator_transcript:
            print(f"Orchestrator transcript: {orch}")
        mine = {p.stem for p in (orch.parent / orch.stem / "subagents").rglob("*.jsonl")}
        sub = [x for x in lines if x["provider"] == "claude" and x["id"].split(":")[-2] in mine]
        orchestrator = orchestrator_lines(orch, args.project, args.stage, sub)
        if not orchestrator:
            print("No usable usage in the orchestrator transcript; no orchestrator line")
        lines += orchestrator
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
