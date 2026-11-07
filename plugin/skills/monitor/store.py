#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Copy the monitoring files into one SQLite file, `monitor.sqlite`, for Grafana (issue #282).

  uv run --script store.py load            load now, then every 30 s; Ctrl-C or SIGTERM ends it
  uv run --script store.py load --once     load once; exit 1 when the load failed
  uv run --script store.py rebuild         delete the db file and load everything again

Each load first runs `steps.py collect` for every project of `monitor-projects.json`, and at most
every 5 minutes `cases.py collect` for the open stage issue of each project (with `gh`, read only).
Then it reads only the new lines of the input files into the db, in one transaction. The db is a
derived copy: deleting it and running `rebuild` gives the same rows. The loader writes only the db,
its log and (once, when missing) the project file. Nothing here judges or decides anything.
Spec: docs/specs/2026-11-06-visual-monitoring.md, Part B
"""

import argparse
import importlib.util
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTERVAL_S = 30
STAGE_READ_S = 5 * 60
ACTIVE_S = 5 * 60
STREAM_KIND = "codex-stream:"


def _load(name, src):
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The readers of the sibling scripts: paths, weights, launch join and tags (reused, not copied).
data = _load("agk_monitor_data", HERE / "data.py")
rr = data.rr
st = _load("agk_monitor_steps", HERE / "steps.py")
cs = _load("agk_monitor_cases", HERE / "cases.py")
run_command = data.run_command  # tests replace it to stub the collectors


# --- paths ------------------------------------------------------------------------------------

def db_path():
    """`$MONITOR_DB_FILE`, else `<state dir>/agent-graph-kit/monitor.sqlite`."""
    env = os.environ.get("MONITOR_DB_FILE")
    return Path(env) if env else data.state_dir() / "monitor.sqlite"


def log_path():
    return db_path().with_name("monitor-load.log")


def projects_path():
    return data.state_dir() / "monitor-projects.json"


def now_utc():
    return datetime.now(timezone.utc)


def epoch(dt):
    return dt.timestamp() if dt else None


def write_private(path, text, append=False):
    """Write (or append) text to a file with mode 0600, also when it existed with another mode."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)


def log(text):
    try:
        write_private(log_path(), f"{rr.iso(now_utc())} {text}\n", append=True)
    except OSError:
        pass  # a log that cannot be written never stops the loader (O2)


# --- gh (read only) ---------------------------------------------------------------------------

def gh(*args, cwd=None):
    """Run a read-only `gh` call; return stdout, raise RuntimeError on a non-zero exit."""
    try:
        res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120, cwd=cwd)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"gh {' '.join(args[:2])}: {e}") from e
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {res.stderr.strip()}")
    return res.stdout


def open_stages(project):
    """[(number, title)] of the open issues with the label `stage` of a project."""
    out = gh("issue", "list", "--repo", project, "--label", "stage", "--state", "open",
             "--json", "number,title", "--limit", "100")
    return [(int(i["number"]), i.get("title")) for i in json.loads(out or "[]") if isinstance(i, dict)]


def sub_issues(project, stage):
    """[(number, title, state)] of the sub-issues of a stage issue."""
    rows = []
    for page in cs.json_values(gh("api", f"repos/{project}/issues/{stage}/sub_issues", "--paginate")):
        for item in page if isinstance(page, list) else [page]:
            if isinstance(item, dict) and "number" in item:
                rows.append((int(item["number"]), item.get("title"), item.get("state")))
    return rows


# --- projects ---------------------------------------------------------------------------------

def projects():
    """The projects of `monitor-projects.json`. When the file is missing, write it once with the
    current project (`owner/name` from `gh repo view`, the current folder as repo)."""
    path = projects_path()
    if not path.exists():
        slug = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
        if not slug:
            raise RuntimeError("gh repo view gave no owner/name")
        entries = [{"project": slug, "repo": str(Path.cwd())}]
        write_private(path, json.dumps(entries, indent=2) + "\n")
        log(f"wrote {path} with {slug}")
        return entries
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{path}: not a list")
    return [e for e in entries
            if isinstance(e, dict) and isinstance(e.get("project"), str) and isinstance(e.get("repo"), str)]


# --- schema -----------------------------------------------------------------------------------

TOKENS = "input_tokens INTEGER, output_tokens INTEGER, cache_creation_tokens INTEGER, cache_read_tokens INTEGER"
NOW_S = "((julianday('now') - 2440587.5) * 86400.0)"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS launches (
  id TEXT PRIMARY KEY, project TEXT, stage INTEGER, issue INTEGER, role TEXT, provider TEXT, model TEXT,
  effort TEXT, {TOKENS}, start_time TEXT, end_time TEXT, start_s REAL, end_s REAL, seconds REAL,
  retry INTEGER, estimate INTEGER, source TEXT, escalations INTEGER, launch TEXT,
  weighted REAL, weighted_is_estimate INTEGER);
CREATE TABLE IF NOT EXISTS steps (
  id TEXT PRIMARY KEY, project TEXT, stage INTEGER, issue INTEGER, role TEXT, provider TEXT, launch TEXT,
  seq INTEGER, time TEXT, time_s REAL, duration_s REAL, model TEXT, {TOKENS}, context_tokens INTEGER,
  tool TEXT, target TEXT, result_chars INTEGER, is_error INTEGER, kit_doc TEXT,
  weighted REAL, weighted_is_estimate INTEGER);
CREATE INDEX IF NOT EXISTS steps_launch ON steps (project, launch, seq);
CREATE TABLE IF NOT EXISTS issues (
  project TEXT, stage INTEGER, issue INTEGER, title TEXT, state TEXT, PRIMARY KEY (project, issue));
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, project TEXT, stage INTEGER, issue INTEGER, round INTEGER, marker TEXT, role TEXT,
  escalation INTEGER, tag TEXT, note TEXT, criteria TEXT, failed_lines TEXT, next_markers TEXT,
  commit_range TEXT, files_changed INTEGER, lines_added INTEGER, lines_removed INTEGER, body_edited INTEGER,
  tokens TEXT, tokens_claude INTEGER, tokens_codex INTEGER, seconds REAL, comment_url TEXT);
CREATE TABLE IF NOT EXISTS limits (
  line INTEGER PRIMARY KEY, project TEXT, stage INTEGER, time TEXT, time_s REAL, point TEXT,
  percent REAL, plan TEXT, entered_by_hand INTEGER);
CREATE TABLE IF NOT EXISTS loads (
  id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, time_s REAL, status TEXT, message TEXT,
  stage_read INTEGER);
CREATE TABLE IF NOT EXISTS files (
  kind TEXT PRIMARY KEY, path TEXT, inode INTEGER, size INTEGER, mtime_ns INTEGER, mtime_s REAL,
  offset INTEGER);
CREATE VIEW IF NOT EXISTS active_launches AS
WITH per AS (
  SELECT project, launch, provider, MIN(time_s) AS start_s, MAX(time_s) AS newest_step_s, MAX(seq) AS last_seq,
         COUNT(*) AS steps, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
         SUM(cache_creation_tokens) AS cache_creation_tokens, SUM(cache_read_tokens) AS cache_read_tokens,
         SUM(weighted) AS weighted, MAX(weighted_is_estimate) AS weighted_is_estimate
  FROM steps WHERE launch IS NOT NULL GROUP BY project, launch, provider
), live AS (
  SELECT per.*, CASE WHEN per.provider = 'codex' THEN f.mtime_s ELSE per.newest_step_s END AS live_s
  FROM per LEFT JOIN files f ON f.kind = '{STREAM_KIND}' || per.launch
)
SELECT live.project, live.launch, live.provider, last.role, last.model, last.issue, last.stage,
       live.start_s, datetime(live.start_s, 'unixepoch') AS start_time,
       live.newest_step_s, live.live_s, datetime(live.live_s, 'unixepoch') AS live_time,
       live.live_s - live.start_s AS run_time_s, {NOW_S} - live.live_s AS idle_s,
       live.steps, live.input_tokens, live.output_tokens, live.cache_creation_tokens, live.cache_read_tokens,
       live.weighted, live.weighted_is_estimate, last.seq AS last_seq, last.tool AS last_tool,
       last.target AS last_target
FROM live JOIN steps last ON last.project = live.project AND last.launch = live.launch AND last.seq = live.last_seq
WHERE live.live_s IS NOT NULL AND {NOW_S} - live.live_s <= {ACTIVE_S};
"""


def connect(path=None):
    """Open the db (created with mode 0600) in autocommit mode, with the default rollback journal."""
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    con = sqlite3.connect(path, isolation_level=None, timeout=30)
    con.execute("PRAGMA journal_mode=DELETE")
    con.executescript(SCHEMA)
    return con


# --- reading the input files ------------------------------------------------------------------

def complete_lines(path, offset):
    """[(byte offset, JSON object)] of the full lines after `offset`, and the offset after the last
    newline. A last line without a newline is left for the next load; a line that is not a JSON
    object is skipped (the rule of `rr.read_records`)."""
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read()
    end = chunk.rfind(b"\n") + 1
    out, pos = [], 0
    for raw in chunk[:end].split(b"\n")[:-1]:
        try:
            d = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            d = None
        if isinstance(d, dict):
            out.append((offset + pos, d))
        pos += len(raw) + 1
    return out, offset + end


def file_state(con, kind):
    row = con.execute("SELECT path, inode, size, mtime_ns, offset FROM files WHERE kind = ?", (kind,)).fetchone()
    return dict(zip(("path", "inode", "size", "mtime_ns", "offset"), row)) if row else None


def save_state(con, kind, path, stat, offset):
    con.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_mtime_ns / 1e9, offset))


def stat_or_none(path):
    try:
        return os.stat(path)
    except FileNotFoundError:
        return None


def same(prev, path, stat):
    return (prev is not None and prev["path"] == str(path)
            and (prev["inode"], prev["size"], prev["mtime_ns"]) == (stat.st_ino, stat.st_size, stat.st_mtime_ns))


def load_appended(con, kind, path, table, put):
    """Load the new full lines of an appended file into `table` with `put(con, offset, row)`.
    A missing file empties the table; a shorter or other file is read again from the start.
    Return True when something was read or removed."""
    stat, prev = stat_or_none(path), file_state(con, kind)
    if stat is None:
        if prev is None:
            return False
        con.execute(f"DELETE FROM {table}")
        con.execute("DELETE FROM files WHERE kind = ?", (kind,))
        return True
    if same(prev, path, stat):
        return False
    start = 0
    if prev is not None and prev["path"] == str(path) and prev["inode"] == stat.st_ino and stat.st_size >= prev["offset"]:
        start = prev["offset"]
    elif prev is not None:
        con.execute(f"DELETE FROM {table}")
    rows, end = complete_lines(path, start)
    for offset, row in rows:
        put(con, offset, row)
    save_state(con, kind, path, stat, end)
    return True


def put_row(con, table, values):
    con.execute(f"INSERT OR REPLACE INTO {table} VALUES ({', '.join('?' * len(values))})", values)


def flag(value):
    return None if value is None else int(bool(value))


def as_text(value):
    return value if value is None or isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class Loader:
    """One load: the weights of each project, and the puts of each table."""

    def __init__(self, entries):
        self.repos = {e["project"]: e["repo"] for e in entries}
        self.weights = {}

    def weights_of(self, project):
        if project not in self.weights:
            self.weights[project] = data.load_weights(project_root=self.repos.get(project))
        return self.weights[project]

    def weigh(self, row, provider):
        w = data.weighted({**row, "provider": provider}, self.weights_of(row.get("project")))
        return w, (1 if w is not None else None)

    def put_launch(self, con, _offset, line):
        if not isinstance(line.get("id"), str):
            return
        start, end = data.parse_time(line.get("start")), data.parse_time(line.get("end"))
        weighted, est = self.weigh(line, line.get("provider"))
        launch = None if line.get("provider") == "codex" else data.launch_of(line)
        put_row(con, "launches", (
                        line["id"], line.get("project"), num(line.get("stage")), num(line.get("issue")),
                        line.get("role"), line.get("provider"), line.get("model"), as_text(line.get("effort")),
                        *(num(line.get(k)) for k in data.TOKEN_KINDS), line.get("start"), line.get("end"),
                        epoch(start), epoch(end), data.seconds(line), num(line.get("retry")),
                        flag(line.get("estimate")), line.get("source"), num(line.get("escalations")), launch,
                        weighted, est))

    def put_step(self, con, _offset, row):
        if not isinstance(row.get("id"), str):
            return
        provider = "codex" if row.get("role") == data.CODEX_ROLE else "claude"
        weighted, est = self.weigh(row, provider)
        put_row(con, "steps", (
                        row["id"], row.get("project"), num(row.get("stage")), num(row.get("issue")),
                        row.get("role"), provider, row.get("launch"), num(row.get("seq")), row.get("time"),
                        epoch(data.parse_time(row.get("time"))), num(row.get("duration_s")), row.get("model"),
                        *(num(row.get(k)) for k in data.TOKEN_KINDS), num(row.get("context_tokens")),
                        as_text(row.get("tool")), as_text(row.get("target")), num(row.get("result_chars")),
                        flag(row.get("is_error")), row.get("kit_doc"), weighted, est))

    @staticmethod
    def put_limit(con, offset, row):
        put_row(con, "limits", (
            offset, row.get("project"), num(row.get("stage")), row.get("time"),
            epoch(data.parse_time(row.get("time"))), row.get("point"), num(row.get("percent")), row.get("plan"), 1))


def link_codex(con):
    """Set `launch` of the Codex record lines from the Codex QA step rows (`data.launch_of`)."""
    rows = con.execute("SELECT project, issue, launch, role, time FROM steps WHERE role = ?", (data.CODEX_ROLE,))
    starts = data.codex_launch_starts([dict(zip(("project", "issue", "launch", "role", "time"), r)) for r in rows])
    lines = con.execute("SELECT id, project, issue, provider, model, start_time FROM launches WHERE provider = 'codex'")
    for ident, project, issue, provider, model, start in lines.fetchall():
        line = {"id": ident, "project": project, "issue": issue, "provider": provider, "model": model, "start": start}
        con.execute("UPDATE launches SET launch = ? WHERE id = ?", (data.launch_of(line, codex_starts=starts), ident))


def full_lines_of(path, reader):
    """Return `reader(p)` for a path reader of `data.py` (`load_cases`, `load_tags`), where `p` shows
    only the full lines of `path`: a last line without a newline is left out until it is complete.
    The full lines go to the reader through a pipe, so nothing is written to disk. A file that
    cannot be read raises the error (it is not taken as a missing file)."""
    with open(path, "rb") as f:
        raw = f.read()
    body = raw[:raw.rfind(b"\n") + 1]
    r, w = os.pipe()

    def feed():
        try:
            with os.fdopen(w, "wb") as out:
                out.write(body)
        except OSError:
            pass  # the reader stopped early; it has the error

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    try:
        result = reader(f"/dev/fd/{r}")
        os.set_blocking(r, False)
        try:
            left = os.read(r, 1)  # b"" (end of file): the reader got every byte
        except BlockingIOError:
            left = b"?"
        if left:
            raise OSError(f"{path}: the reader did not read the full lines")
        return result
    finally:
        os.close(r)
        writer.join()


def load_cases(con):
    """Read the case file and the tag file again when one of them changed (the case file is
    rewritten as a whole). Only full lines are read, so a cut last line waits for the next load."""
    cpath, tpath = data.cases_path(), data.tags_path()
    cstat, tstat = stat_or_none(cpath), stat_or_none(tpath)
    cprev, tprev = file_state(con, "cases"), file_state(con, "tags")
    unchanged = ((cstat is None and cprev is None) or (cstat is not None and same(cprev, cpath, cstat))) and \
                ((tstat is None and tprev is None) or (tstat is not None and same(tprev, tpath, tstat)))
    if unchanged:
        return False
    raw = full_lines_of(cpath, data.load_cases) if cstat is not None else []
    tags = full_lines_of(tpath, data.load_tags) if tstat is not None else {}
    table = data.case_table(raw, tags)
    con.execute("DELETE FROM cases")
    for case, row in zip(raw, table):
        tokens = case.get("tokens") if isinstance(case.get("tokens"), dict) else {}
        marker = row.get("marker")
        put_row(con, "cases", (
            row["id"], row.get("project"), num(row.get("stage")), num(row.get("issue")), num(row.get("round")),
            marker, row.get("role"), int(isinstance(marker, str) and marker.strip().endswith("NEEDS OWNER")),
            row.get("tag"), row.get("note"), as_text(row.get("criteria")), as_text(row.get("failed_lines")),
            as_text(row.get("next_markers")), row.get("commit"), num(row.get("files_changed")),
            num(row.get("lines_added")), num(row.get("lines_removed")), flag(row.get("body_edited")),
            row.get("tokens"), num(tokens.get("claude")), num(tokens.get("codex")), num(row.get("seconds")),
            row.get("comment_url")))
    for kind, path, stat in (("cases", cpath, cstat), ("tags", tpath, tstat)):
        if stat is None:
            con.execute("DELETE FROM files WHERE kind = ?", (kind,))
        else:
            save_state(con, kind, path, stat, stat.st_size)
    return True


def load_streams(con):
    """Store the modification time of each Codex stream file (the liveness of a Codex QA attempt)."""
    folder = st.codex_runs_dir()
    found = {}
    if folder.is_dir():
        for path in folder.glob("*.jsonl"):
            stat = stat_or_none(path)
            if stat is not None and path.is_file():
                found[STREAM_KIND + path.name[:-len(".jsonl")]] = (path, stat)
    changed = False
    for (kind,) in con.execute("SELECT kind FROM files WHERE kind LIKE ?", (STREAM_KIND + "%",)).fetchall():
        if kind not in found:
            con.execute("DELETE FROM files WHERE kind = ?", (kind,))
            changed = True
    for kind, (path, stat) in found.items():
        if not same(file_state(con, kind), path, stat):
            save_state(con, kind, path, stat, stat.st_size)
            changed = True
    return changed


def load_files(con, entries):
    """Read the new lines of every input file into the db. Return True when anything changed."""
    loader = Loader(entries)
    record = load_appended(con, "record", rr.record_path(), "launches", loader.put_launch)
    steps = load_appended(con, "steps", data.steps_path(), "steps", loader.put_step)
    limits = load_appended(con, "limits", rr.limits_path(), "limits", loader.put_limit)
    if record or steps:
        link_codex(con)
    cases = load_cases(con)
    streams = load_streams(con)
    return record or steps or limits or cases or streams


# --- one load ---------------------------------------------------------------------------------

def stage_read_due(con, now):
    last = con.execute("SELECT MAX(time_s) FROM loads WHERE stage_read = 1").fetchone()[0]
    return last is None or epoch(now) - last >= STAGE_READ_S


def collect(entries, stage_read):
    """Run the collectors of each project. Return ({project: issue rows} of the stage reads that
    worked, [problems]). A failing project never stops the others."""
    problems, issues = [], {}
    for e in entries:
        project, repo = e["project"], e["repo"]
        code, out = run_command(data.collect_command(project), cwd=repo)
        if code != 0:
            problems.append(f"steps collect of {project} failed (exit {code}): {out[-300:]}")
    if not stage_read:
        return issues, problems
    for e in entries:
        project, repo = e["project"], e["repo"]
        try:
            rows = []
            for stage, _title in open_stages(project):
                rows += [(project, stage, n, title, state) for n, title, state in sub_issues(project, stage)]
                code, out = run_command(data.cases_collect_command(project, stage), cwd=repo)
                if code != 0:
                    problems.append(f"cases collect of {project} stage {stage} failed (exit {code}): {out[-300:]}")
            issues[project] = rows
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as e:
            problems.append(f"stage read of {project} failed: {e}")
    return issues, problems


def write_load_row(con, now, status, message, stage_read):
    con.execute("INSERT INTO loads (time, time_s, status, message, stage_read) VALUES (?, ?, ?, ?, ?)",
                (rr.iso(now), epoch(now), status, message, int(stage_read)))


def load_once(con, now=None, force_stage_read=False):
    """One load. Return (status, message); status is `ok` or `failed`."""
    now = now or now_utc()
    problems = []
    try:
        entries = projects()
    except (RuntimeError, OSError, ValueError) as e:
        entries = []
        problems.append(f"no projects: {e}")
    stage_read = force_stage_read or stage_read_due(con, now)
    issues, more = collect(entries, stage_read)
    problems += more
    try:
        con.execute("BEGIN IMMEDIATE")
        changed = load_files(con, entries)
        for project, rows in issues.items():
            con.execute("DELETE FROM issues WHERE project = ?", (project,))
            con.executemany("INSERT OR REPLACE INTO issues VALUES (?, ?, ?, ?, ?)", rows)
        status = "failed" if problems else "ok"
        message = "; ".join(problems) or ("loaded new lines" if changed or issues else "no change")
        write_load_row(con, now, status, message, stage_read)
        con.execute("COMMIT")
    except Exception as e:  # O2: a load error goes to the log and the loads table, never further
        if con.in_transaction:
            con.execute("ROLLBACK")
        status, message = "failed", "; ".join(problems + [f"{type(e).__name__}: {e}"])
        log(traceback.format_exc().rstrip())
        try:
            write_load_row(con, now, status, message, stage_read)
        except sqlite3.Error as e2:
            message += f"; the failed row could not be written: {e2}"
    log(f"{status}: {message}")
    return status, message


# --- commands ---------------------------------------------------------------------------------

class Stop(BaseException):
    """SIGINT or SIGTERM: end the loop."""


def _stop(_sig, _frame):
    raise Stop()


def rebuild():
    path = db_path()
    for p in (path, path.with_name(path.name + "-journal")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    con = connect(path)
    try:
        return load_once(con, force_stage_read=True)[0]
    finally:
        con.close()


def loop():
    con = None
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        con = connect()
        log("loader started")
        while True:
            started = time.monotonic()
            load_once(con)
            while time.monotonic() - started < INTERVAL_S:
                time.sleep(0.5)
    except Stop:
        log("loader stopped")
        return 0
    finally:
        if con is not None:
            con.close()  # an open transaction is rolled back


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ld = sub.add_parser("load", help="load now and every 30 s; SIGINT or SIGTERM ends it")
    ld.add_argument("--once", action="store_true", help="load once, exit 1 when the load failed")
    sub.add_parser("rebuild", help="delete the db file and load everything again")
    args = ap.parse_args(argv)
    if args.cmd == "rebuild":
        status = rebuild()
    elif args.once:
        con = connect()
        try:
            status = load_once(con)[0]
        finally:
            con.close()
    else:
        return loop()
    print(f"store: load {status}; db {db_path()}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
