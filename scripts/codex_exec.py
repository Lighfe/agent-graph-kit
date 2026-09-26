"""Shared runner for `codex exec` (used by qa-codex, Task 6, and the review skill, Task 8).

Flags, error texts and regexes come from spike S2 (docs/research/spike-codex-cli.md:
error table and "Consequences for the plan", #6). Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodexRun:
    status: str  # "ok" | "transient" | "timeout" | "invalid_output" | "unavailable" | "unknown"
    output: dict | None
    reason: str


# Keep the user config, AGENTS.md, skills, hooks and apps out of the run, report errors as
# JSON events on stdout, and end a network outage after a few minutes (S2 Q5, Q8).
BASE_FLAGS: list[str] = [
    "--json", "--ephemeral", "--ignore-user-config",
    "--disable", "hooks", "--disable", "apps", "--disable", "unbounded_connection_retries",
    "-c", "project_doc_max_bytes=0", "-c", "skills.include_instructions=false",
]

# S2 error table, rows E1-E9 in order; the first match wins, no match is "unknown" (E10).
FAILURE_PATTERNS: list[tuple[str, re.Pattern]] = [(status, re.compile(rx, re.MULTILINE)) for status, rx in [
    ("unavailable", r"codex'?: (?:(?:command )?not found|No such file or directory)|No such file or directory: 'codex'"),
    ("unavailable", r"^(?:ERROR: )?(?:unexpected status 401 Unauthorized|Not logged in$)"),
    ("unavailable", r"^(?:ERROR: )?(?:You've hit your usage limit|You hit your spend cap|Your workspace is out of credits"
                    r"|Quota exceeded\. Check your plan|To use Codex with your ChatGPT plan)"),
    ("transient", r"^(?:ERROR: )?exceeded retry limit, last status: 429"),
    ("transient", r"^(?:ERROR: )?rate limit exceeded: "),
    ("transient", r"^(?:ERROR: )?We're currently experiencing high demand"),
    ("transient", r"^(?:ERROR: )?Selected model is at capacity"),
    ("transient", r"^(?:ERROR: )?(?:unexpected status 5\d\d|exceeded retry limit, last status: 5\d\d)"),
    ("transient", r"^(?:ERROR: )?(?:Connection failed: |stream disconnected before completion: )"),
]]

REASON_MAX = 500


def _turn_failed(stdout: str) -> str | None:
    """Message of the last `turn.failed` event on stdout (`--json`), or None."""
    message = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.failed":
            error = event.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                message = error["message"]
    return message


def failure_text(stdout: str, stderr: str) -> str:
    """Message of the last turn.failed event, else stderr."""
    message = _turn_failed(stdout)
    return message if message is not None else stderr


def classify_failure(returncode: int, text: str) -> str:
    """"transient" | "unavailable" | "unknown", by the S2 error table."""
    for status, pattern in FAILURE_PATTERNS:
        if pattern.search(text):
            return status
    return "unknown"


def _one_line(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= REASON_MAX else line[:REASON_MAX - 3] + "..."


def failure_reason(stdout: str, stderr: str) -> str:
    """One line for the comment. Never the banner or the prompt: the turn.failed message
    (the prompt is not echoed with --json), else the matching or last line of stderr."""
    message = _turn_failed(stdout)
    if message is not None:
        return _one_line(message) or "codex failed without a message"
    lines = [line for line in stderr.splitlines() if line.strip()]
    for line in lines:
        if any(p.search(line) for _, p in FAILURE_PATTERNS):
            return _one_line(line)
    return _one_line(lines[-1]) if lines else "codex failed without a message"


def _duration(seconds: int) -> str:
    return f"{seconds // 60} min" if seconds >= 60 and seconds % 60 == 0 else f"{seconds} s"


def run_codex(prompt: str, *, schema: Path, sandbox_args: list[str], model: str, effort: str,
              timeout_s: int, cwd: Path) -> CodexRun:
    tmp = Path(tempfile.mkdtemp(prefix="codex-"))
    out = tmp / "last.json"  # fresh path per run: failed runs leave an old file in place (S2 Q1)
    cmd = ["codex", "exec", *BASE_FLAGS, "-m", model, "-c", f'model_reasoning_effort="{effort}"',
           *sandbox_args, "-C", str(cwd), "--output-schema", str(schema), "-o", str(out), "-"]
    try:
        try:
            p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, start_new_session=True)
        except FileNotFoundError:
            return CodexRun("unavailable", None, "codex is not installed")
        try:
            stdout, stderr = p.communicate(prompt, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(p)
            return CodexRun("timeout", None, f"no result after {_duration(timeout_s)}")
        if p.returncode != 0:
            text = failure_text(stdout, stderr)
            return CodexRun(classify_failure(p.returncode, text), None, failure_reason(stdout, stderr))
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return CodexRun("invalid_output", None, f"output is not JSON: {_one_line(str(e))}")
        if not isinstance(data, dict):
            return CodexRun("invalid_output", None, "output is not a JSON object")
        return CodexRun("ok", data, "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _kill_group(p: subprocess.Popen) -> None:
    """SIGKILL the whole process group of `p` (it was started in a new session), then reap it."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait()
    for stream in (p.stdin, p.stdout, p.stderr):
        if stream:
            try:
                stream.close()
            except OSError:
                pass
