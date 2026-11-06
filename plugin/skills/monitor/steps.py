#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Write step rows: one JSON line per assistant message of each Claude Code launch (issue #263),
and one per command and per turn of each Codex QA attempt (issue #268).

  uv run --script steps.py collect --project <owner/name> [--transcripts <folder>] [--codex-runs <folder>] [--stage <n>]

Reads the transcripts as they are, also while a launch still writes to them. Writes no prompt,
thinking or tool output text: only sizes, names, paths and the cut Bash command. The only network
call is the read-only `gh` parent read for the stage, at most once per issue per run, and only when
neither `--stage` nor a run-record line gives the stage. Spec: docs/specs/2026-11-04-kit-monitoring.md, Part 1
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
FIELDS = ("v", "id", "project", "stage", "issue", "role", "launch", "seq", "time", "duration_s", "model",
          "input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens", "context_tokens",
          "tool", "target", "result_chars", "is_error", "kit_doc")
FILE_TOOLS = {"Read": "file_path", "Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}
COMMAND_CUT = 300
COMMAND_RE = re.compile(r"<command-name>\s*(/[^<\s]+)\s*</command-name>")  # matched at the start of a line
ROLE_OF_COMMAND = {"/goal": "orchestrator", "/stage-start": "planner", "/agk:stage-start": "planner"}
KIT_DOC_FILES = ("AGENTS.md", "docs/process.md", "docs/task-template.md")
CODEX_ROLE = "qa-codex"
STREAM_NAME_RE = re.compile(r"-(\d+)-(\d{8}T\d{6})(?:-\d+)?\.jsonl")


def command_names(content):
    """The command names of the lines of a user message that start with a `<command-name>` tag.

    Each text line counts on its own (a string content, or each text part of a list), so a real
    slash command line counts also after a `<command-message>` line, and a tag inside a sentence
    does not count."""
    parts = [content] if isinstance(content, str) else [
        p.get("text") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str)
    ] if isinstance(content, list) else []
    for part in parts:
        for line in part.splitlines():
            m = COMMAND_RE.match(line)
            if m:
                yield m.group(1)


def _load_run_record():
    """The run-record script of the sibling skill folder: the shared transcript reading (issue #263)."""
    src = Path(__file__).resolve().parent.parent / "run-record" / "run_record.py"
    spec = importlib.util.spec_from_file_location("agk_run_record", src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rr = _load_run_record()


def steps_path():
    env = os.environ.get("STEPS_FILE")
    if env:
        return Path(env)
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return base / "agent-graph-kit" / "steps.jsonl"


def codex_runs_dir():
    """The folder of the Codex event streams that the QA launcher saves (the same rule as
    `codex_runs_dir()` in `codex_exec.py`)."""
    env = os.environ.get("CODEX_RUNS_DIR")
    if env:
        return Path(env)
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return base / "agent-graph-kit" / "codex-runs"


def default_transcripts(cwd=None):
    """`~/.claude/projects/<current dir with each character that is not a letter or digit replaced by ->`."""
    name = re.sub(r"[^A-Za-z0-9]", "-", str(cwd or Path.cwd()))
    return Path.home() / ".claude" / "projects" / name


def kit_doc(path):
    """The path when it names a kit document, else None."""
    if not isinstance(path, str) or not path:
        return None
    p = path.replace("\\", "/")
    for name in KIT_DOC_FILES:
        if p == name or p.endswith("/" + name):
            return path
    if (p.startswith("docs/team/") or "/docs/team/" in p) and not p.endswith("/"):
        return path
    return None


def target_of(name, tool_input):
    if not isinstance(tool_input, dict):
        return None
    if name in FILE_TOOLS:
        value = tool_input.get(FILE_TOOLS[name])
    elif name == "Bash":
        value = tool_input.get("command")
        value = value[:COMMAND_CUT] if isinstance(value, str) else None
    elif name == "Agent":
        value = tool_input.get("subagent_type")
    else:
        value = None
    return value if isinstance(value, str) else None


def result_size(content):
    """Characters of the text of one tool result: a string, or the text parts of a list."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(p["text"]) for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return 0


def read_steps(path):
    """Return (role, issue, steps) of one transcript. Each step is a dict with the message fields."""
    records = rr.read_records(path) or []
    role = issue = None
    command_role = None
    first_user_seen = False
    steps = {}  # message id -> step, in the order of the first line
    results = {}  # tool_use_id -> (chars, is_error)
    for index, d in enumerate(records):
        msg = d.get("message")
        if not isinstance(msg, dict) or not msg:
            continue
        content = msg.get("content")
        if d.get("type") == "user":
            blocks = content if isinstance(content, list) else []
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id"):
                    results[b["tool_use_id"]] = (result_size(b.get("content")), b.get("is_error") is True)
            text = rr.prompt_text(content)
            if not first_user_seen:
                first_user_seen = True
                m = rr.PROMPT_RE.search(text)
                if m:
                    role, issue = m.group(1), int(m.group(2))
            if command_role is None:
                for name in command_names(content):
                    if name in ROLE_OF_COMMAND:
                        command_role = ROLE_OF_COMMAND[name]
                        break
            continue
        if d.get("type") != "assistant":
            continue
        mid = msg.get("id") or d.get("uuid") or f"line-{index}"
        step = steps.get(mid)
        if step is None:
            usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
            sums = {out: int(usage.get(src) or 0) for out, src in rr.USAGE_FIELDS}
            step = steps[mid] = {"message_id": mid, "time": None, "model": msg.get("model"), **sums,
                                 "calls": [], "call_ids": set()}
            try:
                step["time"] = rr.parse_time(d["timestamp"]) if d.get("timestamp") else None
            except ValueError:
                pass
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            key = b.get("id") or (b.get("name"), json.dumps(b.get("input"), sort_keys=True, default=str))
            if key in step["call_ids"]:
                continue
            step["call_ids"].add(key)
            step["calls"].append(b)
    if role is None:
        role = command_role or "main"
    out = []
    for step in steps.values():
        calls = step.pop("calls")
        step.pop("call_ids")
        names = [c.get("name") if isinstance(c.get("name"), str) else None for c in calls]
        found = [results.get(c.get("id")) for c in calls if c.get("id") in results]
        docs = [kit_doc((c.get("input") or {}).get("file_path")) for c in calls
                if c.get("name") == "Read" and isinstance(c.get("input"), dict)]
        step.update(tool=names, target=[target_of(n, c.get("input")) for n, c in zip(names, calls)],
                    result_chars=sum(r[0] for r in found), is_error=any(r[1] for r in found),
                    kit_doc=next((x for x in docs if x), None))
        out.append(step)
    return role, issue, out


def launch_rows(path, project, stage_of):
    """Rows of one transcript. `stage_of(issue)` gives the stage of an issue (issue may be None)."""
    path = Path(path)
    launch = path.name[:-len(".jsonl")] if path.name.endswith(".jsonl") else path.stem
    role, issue, steps = read_steps(path)
    stage = stage_of(issue)
    rows = []
    for seq, step in enumerate(steps, 1):
        nxt = steps[seq] if seq < len(steps) else None
        duration = None
        if nxt is not None and step["time"] is not None and nxt["time"] is not None:
            duration = round((nxt["time"] - step["time"]).total_seconds(), 3)
        row = {"v": VERSION, "id": f"{project}:{launch}:{step['message_id']}", "project": project,
               "stage": stage, "issue": issue, "role": role, "launch": launch, "seq": seq,
               "time": rr.iso(step["time"]), "duration_s": duration, "model": step["model"],
               **{f: step[f] for f, _ in rr.USAGE_FIELDS},
               "context_tokens": step["input_tokens"] + step["cache_creation_tokens"] + step["cache_read_tokens"],
               "tool": step["tool"], "target": step["target"], "result_chars": step["result_chars"],
               "is_error": step["is_error"], "kit_doc": step["kit_doc"]}
        rows.append({k: row[k] for k in FIELDS})
    return rows


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def stream_files(folder, project):
    """[(path, issue, attempt start)] of the stream files of one project, read from the file names."""
    prefix = project.replace("/", "__")
    out = []
    for path in sorted(Path(folder).glob("*.jsonl")):
        name = path.name
        if not name.startswith(prefix) or not path.is_file():
            continue
        m = STREAM_NAME_RE.fullmatch(name[len(prefix):])
        if not m:
            continue
        try:
            start = datetime.strptime(m.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append((path, int(m.group(1)), start))
    return out


def stream_events(path):
    """The JSON object events of one stream file; a line that is not JSON (also a cut last line) is skipped."""
    try:
        raw = Path(path).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    events = []
    for line in raw.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            events.append(d)
    return events


def codex_rows(path, issue, start, project, stage_of):
    """Rows of one Codex stream: one per `command_execution` item id (the newest event of the id wins),
    one per `turn.completed`. No row holds command output or message text."""
    launch = Path(path).name[:-len(".jsonl")]
    stage = stage_of(issue)
    steps = {}  # key -> step, in the order of the first event of the key
    turns = 0
    for event in stream_events(path):
        kind = event.get("type")
        item = event.get("item")
        if (isinstance(kind, str) and kind.startswith("item.") and isinstance(item, dict)
                and item.get("type") == "command_execution" and isinstance(item.get("id"), str)):
            command = item.get("command")
            output = item.get("aggregated_output")
            code = item.get("exit_code")
            steps["cmd:" + item["id"]] = {
                "key": item["id"], "tool": ["command_execution"],
                "target": [command[:COMMAND_CUT] if isinstance(command, str) else None],
                "result_chars": len(output) if isinstance(output, str) else 0,
                "is_error": isinstance(code, int) and not isinstance(code, bool) and code != 0,
                "input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0,
                "context_tokens": 0}
        elif kind == "turn.completed":
            turns += 1
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            # the run-record mapping (`codex_lines`): Codex input_tokens includes the cached tokens
            steps[f"turn:{turns}"] = {
                "key": f"turn-{turns}", "tool": [], "target": [], "result_chars": 0, "is_error": False,
                "input_tokens": _int(usage.get("input_tokens")), "output_tokens": _int(usage.get("output_tokens")),
                "cache_creation_tokens": _int(usage.get("cache_write_input_tokens")),
                "cache_read_tokens": _int(usage.get("cached_input_tokens")),
                "context_tokens": _int(usage.get("input_tokens"))}
    rows = []
    for seq, step in enumerate(steps.values(), 1):
        row = {"v": VERSION, "id": f"{project}:{launch}:{step['key']}", "project": project, "stage": stage,
               "issue": issue, "role": CODEX_ROLE, "launch": launch, "seq": seq, "time": rr.iso(start),
               "duration_s": None, "model": None, "kit_doc": None, **step}
        rows.append({k: row[k] for k in FIELDS})
    return rows


def append_rows(rows):
    """Append each row whose id is not in the file yet. The file has mode 0600. Return the count written."""
    path = steps_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    known = set()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                known.add(json.loads(raw).get("id"))
            except (ValueError, AttributeError):
                continue
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    written = 0
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        for row in rows:
            if row["id"] in known:
                continue
            known.add(row["id"])
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
            written += 1
    return written


def write_steps(paths, project, stage, codex_runs=None, issues=None):
    """Write the step rows of the given transcripts with a fixed stage (no `gh` call). Return the count.

    With `issues` (a set of issue numbers), also write the Codex QA step rows of the stream files of
    these issues in `codex_runs` (default: `codex_runs_dir()`); a missing folder gives no Codex rows
    (issue #272)."""
    stage_of = lambda _issue: stage  # noqa: E731
    rows = []
    for p in paths:
        rows += launch_rows(p, project, stage_of)
    if issues is not None:
        runs = Path(codex_runs) if codex_runs else codex_runs_dir()
        if runs.is_dir():
            for path, issue, start in stream_files(runs, project):
                if issue in issues:
                    rows += codex_rows(path, issue, start, project, stage_of)
    return append_rows(rows)


def record_stages(project):
    """{issue: stage} from the run-record lines of the project."""
    out = {}
    records = rr.read_records(rr.record_path()) or []
    for d in records:
        if d.get("project") == project and isinstance(d.get("issue"), int) and isinstance(d.get("stage"), int):
            out.setdefault(d["issue"], d["stage"])
    return out


def gh_parent(issue):
    """The parent issue number from `gh` (read only), or None on any failure."""
    import subprocess
    try:
        res = subprocess.run(["gh", "api", f"repos/{{owner}}/{{repo}}/issues/{issue}/parent"],
                             capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            return None
        number = json.loads(res.stdout).get("number")
        return number if isinstance(number, int) else None
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return None


def stage_lookup(project, stage):
    """A function issue -> stage: `--stage`, else the run record, else the `gh` parent (one call per issue)."""
    if stage is not None:
        return lambda _issue: stage
    known = record_stages(project)
    cache = {}

    def lookup(issue):
        if issue is None:
            return None
        if issue in known:
            return known[issue]
        if issue not in cache:
            cache[issue] = gh_parent(issue)
        return cache[issue]
    return lookup


def collect(args):
    folder = Path(args.transcripts) if args.transcripts else default_transcripts()
    runs = Path(args.codex_runs) if args.codex_runs else codex_runs_dir()
    stage_of = stage_lookup(args.project, args.stage)
    rows = []
    if folder.is_dir():
        for path in sorted(folder.rglob("*.jsonl")):
            rows += launch_rows(path, args.project, stage_of)
    else:
        print(f"No transcript folder: {folder}; no transcript step rows")
    if runs.is_dir():  # a missing stream folder gives no Codex rows and no error
        for path, issue, start in stream_files(runs, args.project):
            rows += codex_rows(path, issue, start, args.project, stage_of)
    if not rows and not folder.is_dir():
        return 0
    written = append_rows(rows)
    print(f"Wrote {written} step rows to {steps_path()} ({len(rows) - written} already there)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="append the step rows of every transcript of a folder")
    c.add_argument("--project", required=True)
    c.add_argument("--transcripts", help="transcript folder; default: the Claude Code folder of the current dir")
    c.add_argument("--codex-runs", help="folder of the Codex QA event streams; default: $CODEX_RUNS_DIR, "
                   "else $XDG_STATE_HOME/agent-graph-kit/codex-runs, else ~/.local/state/agent-graph-kit/codex-runs")
    c.add_argument("--stage", type=int)
    args = ap.parse_args(argv)
    return collect(args)


if __name__ == "__main__":
    sys.exit(main())
