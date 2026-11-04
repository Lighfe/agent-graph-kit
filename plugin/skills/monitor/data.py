"""Loaders and joins for the monitor notebook `explore.py` (issue #265). Standard library only.

The notebook turns these lists of dicts into tables. Nothing here judges: the functions sum, group,
sort and join; they add no verdict, recommendation or cause group.
Spec: docs/specs/2026-11-04-kit-monitoring.md, Part 4
"""

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN_KINDS = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens")
WEIGHT_KIND = {"input_tokens": "input", "output_tokens": "output",
               "cache_creation_tokens": "cache_creation", "cache_read_tokens": "cache_read"}
WEIGHT_LABEL = "estimate from price ratios, not measured plan use"
GROUP_FIELDS = ("project", "stage", "issue", "role", "model", "retry")
SKILL_WEIGHTS = HERE / "run-weights.json"


def _load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The run-record script of the sibling skill: its record path, line reading and time parsing.
rr = _load("agk_run_record", HERE.parent / "run-record" / "run_record.py")


# --- files ------------------------------------------------------------------------------------

def steps_path():
    """`$STEPS_FILE`, else `$XDG_STATE_HOME/agent-graph-kit/steps.jsonl`, else the same under
    `~/.local/state` (the rule of `steps.py`)."""
    env = os.environ.get("STEPS_FILE")
    if env:
        return Path(env)
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return base / "agent-graph-kit" / "steps.jsonl"


def last_per_id(rows):
    """The last row per `id`, in the order of first appearance; rows without `id` are all kept."""
    by_id, order = {}, []
    for row in rows:
        key = row.get("id")
        if key is None:
            order.append(("row", len(order), row))
            continue
        if key not in by_id:
            order.append(("id", key, None))
        by_id[key] = row
    return [by_id[k] if kind == "id" else row for kind, k, row in order]


def read_jsonl(path):
    """The JSON object lines of a file (a line that is not JSON is skipped), last line per `id`;
    [] when the file is missing."""
    return last_per_id(rr.read_records(path) or [])


def load_record(path=None):
    return read_jsonl(path or rr.record_path())


def load_steps(path=None):
    return read_jsonl(path or steps_path())


def weights_path(project_root=None):
    """`$RUN_WEIGHTS_FILE`, else `docs/run-weights.json` of the project when it exists, else the skill copy."""
    env = os.environ.get("RUN_WEIGHTS_FILE")
    if env:
        return Path(env)
    own = Path(project_root or Path.cwd()) / "docs" / "run-weights.json"
    return own if own.is_file() else SKILL_WEIGHTS


def load_weights(path=None, project_root=None):
    """The weights as a dict; {} when the file cannot be read."""
    try:
        data = json.loads(Path(path or weights_path(project_root)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# --- helpers ----------------------------------------------------------------------------------

def parse_time(text):
    try:
        return rr.parse_time(text) if text else None
    except (ValueError, TypeError):
        return None


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def tidy(value):
    return int(value) if isinstance(value, float) and value == int(value) else value


def seconds(line):
    """`end` minus `start` in seconds, or None when one of them is missing."""
    start, end = parse_time(line.get("start")), parse_time(line.get("end"))
    return tidy((end - start).total_seconds()) if start and end else None


def weighted(line, weights):
    """The weighted tokens of one line, or None when its provider has no factors (also provider null)."""
    table = weights.get(line.get("provider")) if isinstance(weights, dict) and line.get("provider") else None
    if not isinstance(table, dict):
        return None
    return sum(number(line.get(k)) * number(table.get(WEIGHT_KIND[k])) for k in TOKEN_KINDS)


def select(rows, where):
    """The rows whose fields equal each value of `where`; a value None means no filter on that field."""
    return [r for r in rows if all(v is None or r.get(k) == v for k, v in where.items())]


def values(rows, field):
    """The distinct values of a field, sorted (None last)."""
    found = {r.get(field) for r in rows}
    return sorted((v for v in found if v is not None), key=lambda v: (str(type(v)), v)) + \
        ([None] if None in found else [])


# --- totals -----------------------------------------------------------------------------------

def totals(record, by, weights=None):
    """One row per group of `by` fields and `estimate` (estimate lines apart from measured lines):
    `lines`, the four token kinds, `seconds` (sum of `end` minus `start`) and `weighted`, a dict
    {provider: weighted tokens}. Providers are never added together; provider null adds nothing."""
    groups = {}
    for line in record:
        key = tuple(line.get(f) for f in by) + (bool(line.get("estimate")),)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {**dict(zip(by, key)), "estimate": key[-1], "lines": 0,
                               **{k: 0 for k in TOKEN_KINDS}, "seconds": 0, "weighted": {}}
        g["lines"] += 1
        for k in TOKEN_KINDS:
            g[k] += number(line.get(k))
        g["seconds"] = tidy(g["seconds"] + (seconds(line) or 0))
        w = weighted(line, weights or {})
        if w is not None:
            g["weighted"][line["provider"]] = g["weighted"].get(line["provider"], 0) + w
    return sorted(groups.values(), key=lambda g: tuple(str(g[f]) for f in by) + (g["estimate"],))


# --- drill-down -------------------------------------------------------------------------------

def launch_of(line):
    """The `launch` value of the step rows of a record line: for a Claude line the middle part of
    `<project>:<transcript name>:<model>`; for a Codex line the stream file name
    `<project with / as __>-<issue>-<start %Y%m%dT%H%M%S>`. None when it cannot be built."""
    ident, project = line.get("id"), line.get("project")
    if not isinstance(ident, str) or not isinstance(project, str) or not ident.startswith(project + ":"):
        return None
    rest = ident[len(project) + 1:]
    if line.get("provider") == "codex":
        start = parse_time(line.get("start"))
        if start is None or line.get("issue") is None:
            return None
        return f"{project.replace('/', '__')}-{line['issue']}-{start.strftime('%Y%m%dT%H%M%S')}"
    model = line.get("model")
    if isinstance(model, str) and rest.endswith(":" + model):
        return rest[:-len(model) - 1]
    return None


def launches(record, where, group=None):
    """The record lines of one total, each with `launch` and `seconds` added, sorted by start.
    `where`: the filters (None = any); `group`: the fields of the total row, matched exactly (None =
    the field is null), with `estimate` as a bool."""
    group = group or {}
    picked = [r for r in select(record, where)
              if all((bool(r.get(k)) if k == "estimate" else r.get(k)) == v for k, v in group.items())]
    rows = [{**r, "launch": launch_of(r), "seconds": seconds(r)} for r in picked]
    return sorted(rows, key=lambda r: str(r.get("start") or ""))


def launch_steps(steps, launch):
    """The step rows of one launch in `seq` order; [] when it has none."""
    rows = [r for r in steps if r.get("launch") == launch]
    return sorted(rows, key=lambda r: number(r.get("seq")))


def kit_doc_reads(steps, by):
    """The count of steps with a kit document (`kit_doc` not null) per `by` fields and document."""
    groups = {}
    for row in steps:
        if not row.get("kit_doc"):
            continue
        key = tuple(row.get(f) for f in by) + (row["kit_doc"],)
        g = groups.setdefault(key, {**dict(zip(by, key)), "kit_doc": row["kit_doc"], "reads": 0})
        g["reads"] += 1
    return sorted(groups.values(), key=lambda g: tuple(str(g[f]) for f in by) + (g["kit_doc"],))


# --- running stage ----------------------------------------------------------------------------

def running(steps, now, active_minutes=5, stage=None, project=None):
    """One row per launch of the steps (of `stage` and `project` when given): role, issue, start
    (first step time), run time (newest step time minus start), tokens so far, the last step
    (highest `seq`) and `active` (newest step time at most `active_minutes` before `now`)."""
    by_launch = {}
    for row in select(steps, {"stage": stage, "project": project}):
        if row.get("launch") is not None:
            by_launch.setdefault(row["launch"], []).append(row)
    out = []
    for launch, rows in by_launch.items():
        times = [t for t in (parse_time(r.get("time")) for r in rows) if t is not None]
        first, newest = (min(times), max(times)) if times else (None, None)
        last = max(rows, key=lambda r: number(r.get("seq")))
        out.append({
            "launch": launch, "role": last.get("role"), "issue": last.get("issue"),
            "stage": last.get("stage"), "project": last.get("project"),
            "start": rr.iso(first), "newest_step": rr.iso(newest),
            "run_time_s": tidy((newest - first).total_seconds()) if times else None,
            "tokens": sum(number(r.get(k)) for r in rows for k in TOKEN_KINDS),
            "steps": len(rows), "last_seq": last.get("seq"), "last_tool": last.get("tool"),
            "last_target": last.get("target"),
            "active": newest is not None and (now - newest).total_seconds() <= active_minutes * 60,
        })
    return sorted(out, key=lambda r: str(r["start"] or ""))


def now_utc():
    return datetime.now(timezone.utc)


# --- refresh ----------------------------------------------------------------------------------

def collect_command(project):
    """The command that writes the current step rows of a project (`steps.py collect`)."""
    return [sys.executable, str(HERE / "steps.py"), "collect", "--project", project]


def collect_steps(project, cwd=None):
    """Run `steps.py collect --project <project>` in `cwd` (default: the current dir, the project
    root). Return (exit code, output text)."""
    import subprocess
    try:
        res = subprocess.run(collect_command(project), cwd=cwd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return res.returncode, (res.stdout + res.stderr).strip()
