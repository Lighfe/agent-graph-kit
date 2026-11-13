#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Facts for the monitoring boards (issue #310): stage issues, the attribution marker and usage limits
as Prometheus metrics on 127.0.0.1.

  uv run --script facts.py [--port N] [--interval SECONDS]

Every 30 s it reads GitHub with `gh` (read only: `issue list`, `issue view`, `api` GET) for each project of
`<state dir>/monitor-projects.json`, and the usage-limit files `usage-limits-claude.jsonl` and
`usage-limits-codex.jsonl` in the same folder. It serves the result at
`http://127.0.0.1:<AGK_FACTS_PORT, default 9464>/metrics`. `board.py up` starts it and `board.py down` stops it.
An error in a read never stops the server: the previous metrics stay and the error goes to stderr (the log).
It writes no comment, no label and no file of a repo.
Spec: docs/specs/2026-11-13-otel-monitoring-boards.md, "Attribution to project, stage and issue"
"""

import argparse
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PORT = 9464
DEFAULT_INTERVAL = 30.0
HOST = "127.0.0.1"
GH_TIMEOUT = 120

# The pattern LAUNCH of `.claude/hooks/issue_state.py`: a launch receipt.
ROLES = "pm|engineer|qa|planner"
LAUNCH = re.compile(rf"^## Launch: ((?:{ROLES}) \((?:attempt|continued, round) (\d+)\))$")
RECEIPT_ROLE = re.compile(rf"^({ROLES}) ")
NOT_STARTED = "## Launch not started: "


class ReadError(Exception):
    """A read of GitHub or of a state file failed; the previous facts stay."""


def log(text):
    print(f"facts: {time.strftime('%Y-%m-%dT%H:%M:%S')} {text}", file=sys.stderr, flush=True)


def _load_data():
    spec = importlib.util.spec_from_file_location("agk_monitor_data", HERE / "data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state_dir():
    """`data.state_dir()` of this skill: `$XDG_STATE_HOME/agent-graph-kit`, else under `~/.local/state`."""
    return _load_data().state_dir()


# --- reading GitHub (read only) ---------------------------------------------------------------

def run_gh(args, cwd):
    """Run `gh <args>` in `cwd` and return stdout. Only read calls are made by the callers."""
    try:
        res = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise ReadError(f"`gh {' '.join(args[:2])}` did not run in {cwd}: {e}")
    if res.returncode != 0:
        lines = (res.stderr or "").strip().splitlines()
        raise ReadError(f"`gh {' '.join(args[:2])}` failed in {cwd} (exit {res.returncode})"
                        + (f": {lines[-1]}" if lines else ""))
    return res.stdout


def gh_json(args, cwd):
    try:
        return json.loads(run_gh(args, cwd))
    except ValueError as e:
        raise ReadError(f"`gh {' '.join(args[:2])}` gave no JSON: {e}")


def gh_json_stream(args, cwd):
    """The objects of a stream of JSON values (what `gh api --paginate --jq '.[] | {...}'` prints)."""
    text = run_gh(args, cwd)
    dec, pos, out = json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return out
        try:
            obj, pos = dec.raw_decode(text, pos)
        except ValueError as e:
            raise ReadError(f"`gh {' '.join(args[:2])}` gave no JSON: {e}")
        out.append(obj)


def _num(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def stage_issues(cwd):
    """The open stage issues: [{"number", "title"}], newest number first."""
    rows = gh_json(["issue", "list", "--label", "stage", "--state", "open", "--json", "number,title",
                    "--limit", "100"], cwd)
    if not isinstance(rows, list):
        raise ReadError("`gh issue list` gave no list")
    stages = [r for r in rows if isinstance(r, dict) and _num(r.get("number")) is not None]
    return sorted(stages, key=lambda r: -r["number"])


def sub_issues(cwd, stage):
    """The sub-issues of a stage in the list order of GitHub: [{"number", "title", "state"}]."""
    rows = gh_json_stream(["api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{stage}/sub_issues",
                           "--jq", ".[] | {number, title, state}"], cwd)
    return [r for r in rows if isinstance(r, dict) and _num(r.get("number")) is not None]


def comments_of(cwd, number):
    data = gh_json(["issue", "view", str(number), "--json", "comments"], cwd)
    comments = data.get("comments") if isinstance(data, dict) else None
    if not isinstance(comments, list):
        raise ReadError(f"`gh issue view {number}` gave no comments")
    return [c for c in comments if isinstance(c, dict)]


# --- the marker -------------------------------------------------------------------------------

def _first_line(body):
    return body.strip().splitlines()[0].strip() if isinstance(body, str) and body.strip() else ""


def receipts(comments):
    """The launch receipts of one issue that count: from the owner, and not followed by a comment
    `## Launch not started: <same role and attempt>`. Each is {"createdAt", "role", "n", "agent"}."""
    owner = [c for c in comments if c.get("authorAssociation") == "OWNER" and isinstance(c.get("createdAt"), str)]
    owner.sort(key=lambda c: c["createdAt"])
    out = []
    for i, c in enumerate(owner):
        m = LAUNCH.match(_first_line(c.get("body")))
        if not m:
            continue
        label = m.group(1)
        if any(_first_line(later.get("body")) == NOT_STARTED + label for later in owner[i + 1:]):
            continue
        agent = ""
        for line in c["body"].strip().splitlines()[1:]:
            if line.startswith("Agent:"):
                agent = line[len("Agent:"):].strip()
                break
        out.append({"createdAt": c["createdAt"], "role": RECEIPT_ROLE.match(label).group(1),
                    "n": m.group(2), "agent": agent})
    return out


def marker_role(receipt):
    if receipt["role"] == "qa":
        return "qa-codex" if receipt["agent"] == "qa-codex" else "qa-claude"
    return receipt["role"]


def pick_marker(stages):
    """The marker of one project. `stages` is a list of {"number", "receipts_stage", "subs"} where `subs`
    holds {"number", "state", "receipts"}. Receipts: planner on the stage issue, the others on the
    sub-issues. The newest receipt by `createdAt` wins; its issue closed and no newer receipt, or no
    receipt at all, gives the stage-level orchestrator marker. None when the project has no open stage."""
    if not stages:
        return None
    best = None  # (createdAt, stage number, issue number or None, receipt, issue closed)
    for st in stages:
        for r in st["receipts_stage"]:
            if r["role"] == "planner" and (best is None or r["createdAt"] > best[0]):
                best = (r["createdAt"], st["number"], None, r, False)
        for sub in st["subs"]:
            for r in sub["receipts"]:
                if r["role"] != "planner" and (best is None or r["createdAt"] > best[0]):
                    best = (r["createdAt"], st["number"], sub["number"], r, sub["state"] == "closed")
    if best is None:
        return {"stage": str(stages[0]["number"]), "issue": "", "role": "orchestrator", "launch": ""}
    _, stage, issue, r, closed = best
    if closed:
        return {"stage": str(stage), "issue": "", "role": "orchestrator", "launch": ""}
    return {"stage": str(stage), "issue": "" if issue is None else str(issue), "role": marker_role(r),
            "launch": f"{r['role']}-{r['n']}"}


def read_project(entry):
    """Facts of one project: {"issues": [labels], "marker": labels or None}."""
    project, cwd = entry["project"], entry["repo"]
    stages = []
    issues = []
    for st in stage_issues(cwd):
        subs = []
        for order, sub in enumerate(sub_issues(cwd, st["number"]), start=1):
            title = sub.get("title") if isinstance(sub.get("title"), str) else ""
            issues.append({"agk_project": project, "stage": str(st["number"]), "issue": str(sub["number"]),
                           "title": title, "order": str(order)})
            subs.append({"number": sub["number"], "state": str(sub.get("state", "")).lower(),
                         "receipts": receipts(comments_of(cwd, sub["number"]))})
        stages.append({"number": st["number"], "receipts_stage": receipts(comments_of(cwd, st["number"])),
                       "subs": subs})
    marker = pick_marker(stages)
    if marker is not None:
        marker = {"agk_project": project, **marker}
    return {"issues": issues, "marker": marker}


# --- usage limits -----------------------------------------------------------------------------

def read_usage_limits(directory):
    """{(provider, window): percent} from the two usage-limit files; the last valid line wins. A line is
    valid when `v` is 1, `used_percent` is a finite number and `provider` and `window` are non-empty text.
    A missing file gives nothing; a bad line is skipped."""
    limits = {}
    for name in ("usage-limits-claude.jsonl", "usage-limits-codex.jsonl"):
        path = Path(directory) / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            continue
        except OSError as e:
            log(f"cannot read {path}: {e}")
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                log(f"{path}:{lineno}: not JSON, skipped")
                continue
            if not isinstance(row, dict):
                continue
            v, pct, prov, win = row.get("v"), row.get("used_percent"), row.get("provider"), row.get("window")
            if (isinstance(v, int) and not isinstance(v, bool) and v == 1
                    and isinstance(pct, (int, float)) and not isinstance(pct, bool) and math.isfinite(pct)
                    and isinstance(prov, str) and prov.strip() and isinstance(win, str) and win.strip()):
                limits[(prov, win)] = float(pct)
            else:
                log(f"{path}:{lineno}: not a valid usage line, skipped")
    return limits


# --- the full read and the text format --------------------------------------------------------

def read_projects_file(directory):
    path = Path(directory) / "monitor-projects.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        raise ReadError(f"cannot read {path}: {e}")
    if not isinstance(entries, list):
        raise ReadError(f"{path}: not a list")
    return [e for e in entries
            if isinstance(e, dict) and isinstance(e.get("project"), str) and isinstance(e.get("repo"), str)]


def read_facts(directory):
    """One full read: {"issues", "markers", "limits"}. Raises ReadError when a GitHub read fails."""
    issues, markers = [], []
    for entry in read_projects_file(directory):
        facts = read_project(entry)
        issues += facts["issues"]
        if facts["marker"]:
            markers.append(facts["marker"])
    return {"issues": issues, "markers": markers, "limits": read_usage_limits(directory)}


def escape(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _series(name, labels, value):
    inner = ",".join(f'{k}="{escape(v)}"' for k, v in labels.items())
    return f"{name}{{{inner}}} {value}" if inner else f"{name} {value}"


def render(facts, success_time):
    """The Prometheus text format of one full read."""
    lines = []

    def block(name, help_text, rows):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.extend(rows)

    block("agk_issue_info", "Sub-issues of the open stage issues, 1 each.",
          [_series("agk_issue_info", {k: i[k] for k in ("agk_project", "stage", "issue", "title", "order")}, 1)
           for i in facts["issues"]])
    block("agk_marker", "The issue and role in work now, 1 for each project.",
          [_series("agk_marker", {k: m[k] for k in ("agk_project", "stage", "issue", "role", "launch")}, 1)
           for m in facts["markers"]])
    block("agk_usage_limit_percent", "Used share of a plan usage limit window, in percent.",
          [_series("agk_usage_limit_percent", {"provider": p, "window": w}, repr(v))
           for (p, w), v in sorted(facts["limits"].items())])
    block("agk_facts_last_success_seconds", "Unix time of the last full read.",
          [_series("agk_facts_last_success_seconds", {}, repr(float(success_time)))])
    return "\n".join(lines) + "\n"


# --- the server -------------------------------------------------------------------------------

class Facts:
    """The newest metrics text, refreshed by `refresh`. A failing read keeps the previous text."""

    def __init__(self, directory=None):
        self.directory = directory
        self.text = ""
        self.lock = threading.Lock()

    def refresh(self):
        try:
            directory = self.directory or state_dir()
            text = render(read_facts(directory), time.time())
        except Exception as e:  # any error: keep the previous facts, log it, go on
            log(f"read failed, previous facts kept: {e}")
            return False
        with self.lock:
            self.text = text
        return True

    def body(self):
        with self.lock:
            return self.text


def make_server(facts, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] != "/metrics":
                self.send_error(404)
                return
            body = facts.body().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True
    return server


def refresh_loop(facts, interval, stop):
    while not stop.is_set():
        facts.refresh()
        stop.wait(interval)


def serve(port, interval, directory=None):
    facts = Facts(directory)
    server = make_server(facts, port)
    stop = threading.Event()
    threading.Thread(target=refresh_loop, args=(facts, interval, stop), daemon=True).start()
    log(f"serving http://{HOST}:{server.server_address[1]}/metrics every {interval:g} s")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.environ.get("AGK_FACTS_PORT") or DEFAULT_PORT))
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = ap.parse_args(argv)
    return serve(args.port, args.interval)


if __name__ == "__main__":
    sys.exit(main())
