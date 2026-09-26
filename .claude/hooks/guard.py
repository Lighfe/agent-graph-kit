#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse guard hook (spec 5.1-5.7, 5.9).

Reads one hook event on stdin. A guarded call (a role launch, a SendMessage
continuation, `qa-codex`, `gh issue close`) is checked against the issue state
with `issue_state`. An allowed launch gets its launch comment before the guard
exits. A deny is printed as the PreToolUse deny JSON with exit code 0. An
allowed call prints nothing, so the normal permission check stays on.

Any error denies: a failing `gh` or `git`, broken input, a crash, and the
overall deadline (GUARD_DEADLINE seconds, default 60). Stdlib only.

Known limits by design (P1, hooks are not a security boundary): a command
run from a string or a variable (`bash -c`, `eval`, `xargs`, `sudo`,
`$GH issue close 5`, aliases, functions) is not recognized.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import issue_state
from issue_state import Call

SUBAGENT_TOOLS = {"Agent", "Task"}  # S1 Q1: the tool is "Agent"; "Task" is the old name
AGENT_ROLE = {"pm": "pm", "software-engineer": "engineer", "frontend-engineer": "engineer", "qa-engineer": "qa"}
LAUNCH_LINE = re.compile(r"ROLE=(pm|engineer|qa) ISSUE=([0-9]+)")
LAUNCH_HINT = "exactly one line ROLE=<pm|engineer|qa> ISSUE=<number>"

DEFAULT_DEADLINE_S = 60  # spec 5.6
CALL_TIMEOUT_S = 20  # per gh/git call
STDERR_MAX = 200  # P5: first stderr line, cut to 200 characters
LOCK_NAME = "agent-graph-kit-guard.lock"

CLOSE_REASONS = {"completed", "not planned"}
# Shell words that may stand before a command. A guarded call behind one of them is denied.
# Commands that run the command after them. With an option argument (`timeout 5 gh …`),
# the guarded call is searched in the rest of the words.
WRAPPERS = {"exec", "command", "env", "builtin", "nohup", "coproc", "nice", "timeout", "stdbuf", "setsid"}
PREFIX_WORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "time"} | WRAPPERS
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
RUNNERS = re.compile(r"uv|python(3(\.[0-9]+)?)?")

# G8 (spec 5.9)
SETTINGS_NAME = re.compile(r"settings[^/\s]*\.json", re.IGNORECASE)
CLAUDE_GLOB = re.compile(r"\.claude/[^\s'\"]*[*?\[]")
READ_ONLY = {"cat", "jq", "head", "tail", "grep", "wc", "ls"}
_NO_BRACES = str.maketrans("", "", "{},")


class Deny(Exception):
    """The call is denied. The message is the deny reason."""


# --- shell tokenizer ------------------------------------------------------------------
#
# A small bash-like tokenizer. It knows quotes ('…', "…", $'…', $"…"), backslashes,
# line continuations, ${…}, $(…), backticks, arithmetic ((…)), $((…)) and $[…],
# operators, redirections (also with {fd}), here-documents, comments and the
# patterns of `case`. As in bash, `#` starts a comment only at the start of a
# word, so `echo x#; gh issue close 5` has two commands.
#
# Tokens: ("w", value, subs) a word, quotes removed, `subs` the texts inside
# $(…), backticks and arithmetic (unquoted or in double quotes); ("op", op) a
# command separator, also "((" before an arithmetic command; ("redir", op) a
# redirection; ("body", "", subs) the substitutions in an unquoted here-document body.

_OPS = (";;&", "&>>", "<<<", "<<-", "&&", "||", "|&", ";;", ";&", "<(", ">(", ">>", ">|", "<>", "<&", ">&",
        "&>", "<<", ";", "&", "|", "(", ")", "<", ">")
_REDIRECTS = {"<", ">", ">>", ">|", "<>", "<&", ">&", "&>", "&>>", "<<", "<<-", "<<<"}
_OPEN = {"(", "<(", ">("}
_CASE_NEXT = {";;", ";&", ";;&"}  # end a case branch; a pattern follows
_COMMAND_FOLLOWS = {"{", "!", "if", "then", "else", "elif", "do", "while", "until", "time"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NAMED_FD = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")  # {fd}>file: bash puts the new fd number in $fd
_ANSI = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
         "\\": "\\", "'": "'", '"': '"', "?": "?"}
_ANSI_NUMBER = {"x": (16, 2), "u": (16, 4), "U": (16, 8)}


class _Lexer:
    # The text self.t can get shorter while the lexer runs: `join` removes line continuations
    # ahead of the current position. So every loop reads self.t and self.n again, and a
    # position returned by a nested call is a position in the new text.

    def __init__(self, text: str):
        self.t = text
        self.n = len(text)

    def join(self, i: int, k: int = 2) -> None:
        """Remove the line continuations (backslash-newline) in the k characters after i.
        Bash removes them before it reads a token, so `$\\<newline>'` is `$'` and `<\\<newline><` is `<<`."""
        j = i + 1
        while j < min(self.n, i + 1 + k):
            if self.t.startswith("\\\n", j):
                self.t = self.t[:j] + self.t[j + 2:]
                self.n -= 2
            elif self.t[j] == "\\":
                break
            else:
                j += 1

    def script(self, i: int, sub: bool) -> tuple[list[tuple], int]:
        """Tokens from i to the end, or (sub=True) to the `)` that closes a $(."""
        toks: list[tuple] = []
        heredocs: list[tuple[str, bool, bool]] = []
        depth = 0
        buf: list[str] = []
        subs: list[str] = []
        word = quoted = False
        start = True  # at the start of a command, where `esac` is a reserved word
        # Open `case` commands: [state, at the first word of a pattern]. A plain word `case`
        # followed by a word and a plain `in` starts one wherever it stands. Seeing too many
        # is safe: the `)` of a pattern then does not end a $(, and the text stays inside it.
        cases: list[list] = []

        def end():
            nonlocal buf, subs, word, quoted, start
            if word:
                value = "".join(buf)
                if toks and toks[-1] in (("redir", "<<"), ("redir", "<<-")):
                    heredocs.append((value, toks[-1][1] == "<<-", quoted))
                toks.append(("w", value, tuple(subs)))
                plain = not quoted and not subs
                state = cases[-1][0] if cases else None
                if state == "word":  # case WORD
                    cases[-1][0] = "in"
                elif state == "in":  # case WORD in
                    if plain and value == "in":
                        cases[-1] = ["pattern", True]
                    else:
                        cases.pop()
                elif state == "pattern":
                    if cases[-1][1] and plain and value == "esac":
                        cases.pop()
                    else:
                        cases[-1][1] = False
                elif state == "body" and start and plain and value == "esac":
                    cases.pop()
                elif plain and value == "case":
                    cases.append(["word", False])
                start = plain and value in _COMMAND_FOLLOWS
            buf, subs, word, quoted = [], [], False, False

        while i < self.n:
            t, n = self.t, self.n
            c = t[i]
            if c in "$<>&|;(":
                self.join(i)
                t, n = self.t, self.n
            state = cases[-1][0] if cases else None
            if c in "()" and state != "pattern":
                # `((` at the start of a word is an arithmetic command, as in `(( x = 1 << 2 ))`
                arith = self.arith(i + 2, "))") if t.startswith("((", i) and not word else None
                if arith:
                    j, inner, inner_subs = arith
                    end()
                    toks.append(("op", "(("))
                    toks.append(("w", self.t[i:j], (*inner_subs, inner)))
                    start = False
                    i = j
                    continue
            if c in "()":
                end()  # the word before may be `esac`
                state = cases[-1][0] if cases else None
            if c in " \t":
                end()
                i += 1
            elif c == "#" and not word:  # a comment, up to the end of the line
                j = t.find("\n", i)
                i = n if j < 0 else j
            elif c == "\n":
                end()
                toks.append(("op", "\n"))
                start = True
                i += 1
                for delim, strip, q in heredocs:
                    i, body = self.heredoc(i, delim, strip, joined=not q)
                    if not q:
                        body_subs: list[str] = []
                        _Lexer(body).double(0, [], body_subs, None)
                        toks.append(("body", "", tuple(body_subs)))
                heredocs = []
            elif c == "\\":
                if i + 1 >= n:
                    raise ValueError("backslash at the end of the command")
                if t[i + 1] != "\n":  # backslash-newline is a line continuation
                    buf.append(t[i + 1])
                    word = quoted = True
                i += 2
            elif c == "'":
                j = t.find("'", i + 1)
                if j < 0:
                    raise ValueError("unterminated single quote")
                buf.append(t[i + 1:j])
                word = quoted = True
                i = j + 1
            elif c == '"':
                i = self.double(i + 1, buf, subs, '"')
                word = quoted = True
            elif c == "`":
                i = self.backtick(i, buf, subs)
                word = True
            elif c == "$" and t.startswith(("$'", '$"', "${", "$(", "$[", "$$"), i):
                i, is_quoted = self.dollar(i, buf, subs)
                word = True
                quoted = quoted or is_quoted
            elif c in "()" and state == "pattern":  # `(` before and `)` after a case pattern
                toks.append(("op", c))
                if c == ")":
                    cases[-1][0] = "body"
                    start = True
                i += 1
            elif c in "<>&|;()":
                if sub and c == ")" and depth == 0:
                    end()
                    return toks, i + 1
                op = next(o for o in _OPS if t.startswith(o, i))
                if op in _REDIRECTS and word and not quoted and not subs:
                    text = "".join(buf)
                    if (text.isascii() and text.isdigit()) or _NAMED_FD.fullmatch(text):
                        buf, word = [], False  # a file descriptor, as in 2>&1 or {fd}>file
                end()
                if op in _OPEN:
                    depth += 1
                elif op == ")":
                    depth -= 1
                if op in _CASE_NEXT and state == "body":
                    cases[-1] = ["pattern", True]
                if op not in _REDIRECTS:
                    start = True
                toks.append(("redir" if op in _REDIRECTS else "op", op))
                i += len(op)
            elif c == "[" and not quoted and not subs and (not word or _NAME.fullmatch("".join(buf))) and (
                    sub_end := self.subscript(i)):
                # the subscript of an array assignment, `a[1<<2]=x` or `a=( [1<<2]=x )`, is arithmetic
                j, inner, inner_subs = sub_end
                buf.append(self.t[i:j])
                subs.extend((*inner_subs, inner))
                word = True
                i = j
            else:
                buf.append(c)
                word = True
                i += 1
        if sub:
            raise ValueError("unterminated $(")
        end()
        return toks, i

    def dollar(self, i: int, buf: list[str], subs: list[str], dq: bool = False) -> tuple[int, bool]:
        """An expansion or quote that starts with `$` at i: $'…', $"…", ${…}, $(…), $((…)), $[…], $$.
        Returns (index after it, whether it is a quote)."""
        self.join(i)
        t = self.t
        if t.startswith("$$", i):  # the process id, so a quote after it is a plain quote
            buf.append("$$")
            return i + 2, False
        if t.startswith("$'", i) and not dq:
            return self.ansi(i + 2, buf), True
        if t.startswith('$"', i) and not dq:
            return self.double(i + 2, buf, subs, '"'), True
        if t.startswith("${", i):
            return self.brace(i, buf, subs, dq), False
        if t.startswith("$[", i):
            arith = self.arith(i + 2, "]")
            if not arith:
                raise ValueError("unterminated $[")
        elif t.startswith("$((", i):
            arith = self.arith(i + 3, "))")
        elif t.startswith("$(", i):
            arith = None
        else:
            buf.append("$")
            return i + 1, False
        if arith:  # the text inside is also checked as a command: $((…) ) may be a $( (…) )
            j, inner, inner_subs = arith
            subs.extend((*inner_subs, inner))
        else:
            _, j = self.script(i + 2, sub=True)
            subs.append(self.t[i + 2:j - 1])
        buf.append(self.t[i:j])
        return j, False

    def subscript(self, i: int) -> tuple[int, str, list[str]] | None:
        """`[…]` at i if `=` or `+=` follows it, as in an array assignment, else None."""
        arith = self.arith(i + 1, "]")
        if arith and self.t.startswith(("=", "+="), arith[0]):
            return arith
        return None

    def arith(self, i: int, close: str) -> tuple[int, str, list[str]] | None:
        """Arithmetic from i to `close` ("))" or "]"): (index after it, the text inside, the
        substitutions in it). None if there is no matching close."""
        depth, j, subs = 0, i, []
        opening = "(" if close == "))" else "["
        while j < self.n:
            t = self.t
            c = t[j]
            if c == "\\":
                j += 2
            elif c == "'":
                k = t.find("'", j + 1)
                if k < 0:
                    return None
                j = k + 1
            elif c == '"':
                j = self.double(j + 1, [], subs, '"')
            elif c == "`":
                j = self.backtick(j, [], subs)
            elif c == "$":
                j, _ = self.dollar(j, [], subs)
            elif c == opening:
                depth += 1
                j += 1
            elif c == close[0]:
                self.join(j, 1)
                if depth:
                    depth -= 1
                    j += 1
                elif self.t.startswith(close, j):
                    return j + len(close), self.t[i:j], subs
                else:
                    return None
            else:
                j += 1
        return None

    def double(self, i: int, buf: list[str], subs: list[str], stop: str | None) -> int:
        """Text in double quotes from i (stop='"'), or a here-document body (stop=None)."""
        while i < self.n:
            t, n = self.t, self.n
            c = t[i]
            if stop is not None and c == stop:
                return i + 1
            if c == "\\" and i + 1 < n:
                nxt = t[i + 1]
                if nxt != "\n":
                    buf.append(nxt if nxt in '$`"\\' else c + nxt)
                i += 2
            elif c == "`":
                i = self.backtick(i, buf, subs)
            elif c == "$":
                i, _ = self.dollar(i, buf, subs, dq=True)
            else:
                buf.append(c)
                i += 1
        if stop is not None:
            raise ValueError("unterminated double quote")
        return i

    def ansi(self, i: int, buf: list[str]) -> int:
        """Text in $'…' from i (after the quote), with its backslash escapes decoded.
        As in bash, a backslash always takes the next character, so `$'\\c'` ends at its second quote."""
        t, j = self.t, i
        while j < self.n and t[j] != "'":
            j += 2 if t[j] == "\\" else 1
        if j >= self.n:
            raise ValueError("unterminated $' quote")
        text, k = t[i:j], 0
        while k < len(text):
            c = text[k]
            nxt = text[k + 1] if k + 1 < len(text) else ""
            if c != "\\" or not nxt:
                buf.append(c)
                k += 1
            elif nxt in _ANSI:
                buf.append(_ANSI[nxt])
                k += 2
            elif nxt in "01234567":
                digits = re.match(r"[0-7]{1,3}", text[k + 1:]).group()
                buf.append(chr(int(digits, 8) & 0xFF))
                k += 1 + len(digits)
            elif nxt in _ANSI_NUMBER:
                base, most = _ANSI_NUMBER[nxt]
                m = re.match(r"[0-9A-Fa-f]{1,%d}" % most, text[k + 2:])
                if m:
                    buf.append(chr(int(m.group(), base)))
                    k += 2 + len(m.group())
                else:
                    buf.append(c + nxt)
                    k += 2
            elif nxt == "c" and k + 2 < len(text):
                ctrl = text[k + 2]
                buf.append(chr(ord(ctrl) & 0x1F))
                k += 4 if text.startswith("\\\\", k + 2) else 3  # $'\c\\' is one control character
            else:
                buf.append(c + nxt)
                k += 2
        return j + 1

    def brace(self, i: int, buf: list[str], subs: list[str], dq: bool) -> int:
        """${…} from i. Spaces and `#` inside belong to it. Returns the index after the `}`."""
        j = i + 2
        while j < self.n:
            t = self.t
            c = t[j]
            if c == "}":
                buf.append(t[i:j + 1])
                return j + 1
            if c == "\\":
                j += 2
            elif c == "'" and not dq:
                k = t.find("'", j + 1)
                if k < 0:
                    raise ValueError("unterminated single quote")
                j = k + 1
            elif c == '"':
                j = self.double(j + 1, [], subs, '"')
            elif c == "`":
                j = self.backtick(j, [], subs)
            elif c == "$":
                j, _ = self.dollar(j, [], subs, dq=dq)
            else:
                j += 1
        raise ValueError("unterminated ${")

    def backtick(self, i: int, buf: list[str], subs: list[str]) -> int:
        t, j = self.t, i + 1
        while j < self.n and t[j] != "`":
            j += 2 if t[j] == "\\" else 1
        if j >= self.n:
            raise ValueError("unterminated backtick")
        # bash removes the backslash before ` $ \ inside backticks before it runs the text
        subs.append(re.sub(r"\\([`$\\])", r"\1", t[i + 1:j]))
        buf.append(t[i:j + 1])
        return j + 1

    def heredoc(self, i: int, delim: str, strip: bool, joined: bool) -> tuple[int, str]:
        """Skip a here-document body. Returns (index after the delimiter line, body).
        In an unquoted body (joined=True), a backslash-newline joins two lines, also for the delimiter."""
        t, n, start = self.t, self.n, i
        while i < n:
            j, parts = i, []
            while True:
                k = t.find("\n", j)
                k = n if k < 0 else k
                part = t[j:k]
                trailing = len(part) - len(part.rstrip("\\"))
                if joined and trailing % 2 and k < n:
                    parts.append(part[:-1])
                    j = k + 1
                    continue
                parts.append(part)
                break
            line = "".join(parts)
            if (line.lstrip("\t") if strip else line) == delim:
                return min(k + 1, n), t[start:i]
            i = k + 1
        return n, t[start:]


def _lex(command: str) -> list[tuple]:
    return _Lexer(command).script(0, sub=False)[0]


def _simple_commands(toks: list[tuple]) -> tuple[list[list[tuple]], int]:
    cmds: list[list[tuple]] = []
    cur: list[tuple] = []
    ops = 0
    for tok in toks:
        if tok[0] == "op":
            ops += 1
            cmds.append(cur)
            cur = []
        else:
            cur.append(tok)
    cmds.append(cur)
    return [c for c in cmds if c], ops


def split_command(command: str) -> tuple[list[list[str]], int]:
    """(simple commands, number of operators). A simple command lists its words
    (quotes removed) and its redirection operators. Raises ValueError."""
    cmds, ops = _simple_commands(_lex(command))
    out = [[tok[1] for tok in cmd if tok[0] != "body"] for cmd in cmds]
    return [c for c in out if c], ops


def substitutions(token: str) -> list[str]:
    """Texts inside $(…) and backticks in `token`. Raises ValueError if unbalanced."""
    return [s for tok in _lex(token) if tok[0] in ("w", "body") for s in tok[2]]


# --- classification -------------------------------------------------------------------


def _launch(text: str, what: str) -> tuple[str, int]:
    """(role, issue) of the one launch line in `text`, else Deny."""
    found = [m for line in text.split("\n") if (m := LAUNCH_LINE.fullmatch(line.rstrip(" \r")))]
    if not found:
        raise Deny(f"G1: {what} has no launch line, expected {LAUNCH_HINT}")
    if len(found) > 1:
        raise Deny(f"G1: {what} has {len(found)} launch lines, expected {LAUNCH_HINT}")
    return found[0].group(1), int(found[0].group(2))


def _classify_agent(tool_input: dict) -> Call | None:
    agent = tool_input.get("subagent_type")
    if agent is None:
        return None  # a general-purpose launch (S1 Q1)
    if not isinstance(agent, str):
        raise Deny("G1: subagent_type is not a string, expected a subagent name")
    if agent not in AGENT_ROLE:
        return None
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str):
        raise Deny(f"G1: launch of {agent} has no string prompt, expected a prompt with {LAUNCH_HINT}")
    role, number = _launch(prompt, f"launch of {agent}")
    if role != AGENT_ROLE[agent]:
        raise Deny(f"G1: launch line role is {role}, expected {AGENT_ROLE[agent]} for agent {agent}")
    return Call(role=role, agent=agent, issue=number)


def _classify_send(tool_input: dict) -> Call:
    to, message = tool_input.get("to"), tool_input.get("message")
    if not isinstance(to, str) or not to or not isinstance(message, str):
        raise Deny("G1: SendMessage input has no string to or no string message, "
                   f"expected both, with {LAUNCH_HINT} in the message")
    role, number = _launch(message, "SendMessage")
    return Call(role=role, agent=to, issue=number, continued=True)


def _words(cmd: list[tuple]) -> list[str]:
    """The words of a simple command, without its redirections and their targets."""
    words, target = [], False
    for tok in cmd:
        if tok[0] == "redir":
            target = True
        elif tok[0] == "w":
            if not target:
                words.append(tok[1])
            target = False
    return words


def _gh_close(words: list[str], k: int) -> int | None:
    """Index of `close` if words[k:] is `gh … issue … close` with only options between, else None."""
    seen_issue = False
    for m in range(k + 1, len(words)):
        w = words[m]
        if w == "close" and seen_issue:
            return m
        if w == "issue" and not seen_issue:
            seen_issue = True
        elif not (w.startswith("-") or (m - 1 > k and words[m - 1].startswith("-"))):
            return None
    return None


def _call_at(words: list[str], k: int) -> tuple[str, int] | None:
    """("close" | "qa-codex", index of the last command word) if a guarded call starts at words[k]."""
    name = words[k].rsplit("/", 1)[-1]
    if name == "gh":
        m = _gh_close(words, k)
        return ("close", m) if m is not None else None
    if words[k].endswith("qa-codex"):
        return "qa-codex", k
    if RUNNERS.fullmatch(name):
        for m in range(k + 1, len(words)):
            if words[m].endswith("qa-codex"):
                return "qa-codex", m
    return None


def _find_guarded(cmd: list[tuple]) -> tuple[list[str], int, str, int] | None:
    """(words, index of the first command word, "close" | "qa-codex", index of the last command word) or None.
    Redirections do not count as words, wherever they stand."""
    words = _words(cmd)
    i, after_prefix = 0, False
    while i < len(words):
        value = words[i]
        if value in PREFIX_WORDS:
            after_prefix = True
        elif value == "function":  # `function NAME { …; }`: the name is no command
            after_prefix = True
            i += 1
        elif not ASSIGNMENT.match(value) and not (after_prefix and value.startswith("-")):
            break
        i += 1
    if i >= len(words):
        return None
    found = _call_at(words, i)
    if found:
        return words, i, *found
    # A command may run the words after it: `timeout 5 gh …`, `ionice -c 3 gh …`, `find -exec gh …`.
    # So a `gh … issue close` later in the words counts too. A qa-codex word later counts after a
    # known wrapper, or when its launch arguments follow, so `cat scripts/qa-codex` still passes.
    wrapped = any(w in WRAPPERS for w in words[:i])
    for k in range(i + 1, len(words)):
        found = _call_at(words, k)
        if not found:
            continue
        after = words[found[1] + 1] if found[1] + 1 < len(words) else ""
        if wrapped or found[0] == "close" or after.startswith(("ROLE=", "ISSUE=")):
            return words, k, *found
    return None


def _close_number(args: list[str]) -> int:
    number = None
    reason = False
    j = 0
    while j < len(args):
        value = args[j]
        if value in ("--reason", "-r") or value.startswith("--reason="):
            if value.startswith("--reason="):
                given, j = value.split("=", 1)[1], j + 1
            else:
                given = args[j + 1] if j + 1 < len(args) else None
                j += 2
            if reason or given not in CLOSE_REASONS:
                raise Deny(f"G1: gh issue close reason is {given or 'missing'}, "
                           "expected one --reason completed or --reason 'not planned'")
            reason = True
            continue
        if not (value.isascii() and value.isdigit()):
            raise Deny(f"G1: gh issue close has the argument {value}, "
                       "expected one issue number made of digits and optionally --reason")
        if number is not None:
            raise Deny("G1: gh issue close has two issue numbers, expected exactly one")
        number = int(value)
        j += 1
    if number is None:
        raise Deny("G1: gh issue close has no issue number, expected exactly one")
    return number


def _qa_codex_issue(args: list[str]) -> int:
    m = re.fullmatch(r"ISSUE=([0-9]+)", args[1]) if len(args) == 2 else None
    if args[:1] != ["ROLE=qa"] or not m:
        raise Deny("G1: qa-codex arguments are not ROLE=qa ISSUE=<number>, "
                   "expected exactly these two arguments in this order")
    return int(m.group(1))


def _mentions_guarded(text: str) -> bool:
    return "gh" in text or "qa-codex" in text


def _classify_text(text: str) -> Call | None:
    """Classify one shell text (a command, or the text inside a substitution)."""
    try:
        toks = _lex(text)
    except ValueError as e:
        if _mentions_guarded(text):
            raise Deny(f"G1: the command cannot be parsed ({e}) and mentions gh or qa-codex, "
                       "expected a command that parses") from None
        return None
    cmds, ops = _simple_commands(toks)
    for cmd in cmds:
        for tok in cmd:
            for inner in (tok[2] if tok[0] in ("w", "body") else ()):
                try:
                    inside = _classify_text(inner) is not None
                except Deny:
                    inside = True
                if inside:
                    raise Deny("G1: a guarded call (gh issue close or qa-codex) is inside $(…) or backticks, "
                               "expected it as a simple command of its own")
    guarded = [(cmd, g) for cmd in cmds if (g := _find_guarded(cmd))]
    if not guarded:
        return None
    if ops or len(cmds) != 1:
        raise Deny("G1: a guarded call (gh issue close or qa-codex) is part of a command with shell operators, "
                   "expected one simple command without ; && || | & newline ( )")
    cmd, (words, first, kind, last) = guarded[0]
    if first:
        raise Deny(f"G1: a guarded call ({kind}) has {words[0]} before it, "
                   "expected the call at the start of the command")
    redirection = next((tok[1] or "<<" for tok in cmd if tok[0] in ("redir", "body")), None)
    if redirection:
        raise Deny(f"G1: a guarded call ({kind}) has the redirection {redirection}, expected no redirection")
    args = words[last + 1:]
    if kind == "close":
        if words[1:last] != ["issue"]:
            raise Deny(f"G1: gh issue close has {' '.join(words[1:last])} between gh and close, "
                       "expected gh issue close <number>")
        return Call(role="close", agent="", issue=_close_number(args))
    return Call(role="qa", agent="qa-codex", issue=_qa_codex_issue(args))


def g8(command: str) -> str | None:
    """Deny reason if the command may write to .claude/settings*.json (spec 5.9)."""
    reason = ("G8: the command may write to .claude/settings*.json, expected only one simple "
              f"{', '.join(sorted(READ_ONLY))} command without operators or redirections")
    try:
        toks = _lex(command)
    except ValueError:
        toks = None
    values = [tok[1] for tok in toks or () if tok[0] == "w"]  # quotes removed
    values += [v.translate(_NO_BRACES) for v in values if "{" in v]  # settings.{json,bak} names settings.json
    mentions = SETTINGS_NAME.search(command) or CLAUDE_GLOB.search(command) or any(
        SETTINGS_NAME.search(v) or (".claude/" in v and any(ch in v for ch in "*?[")) for v in values)
    if not mentions:
        return None
    if toks is None:
        return reason
    cmds, ops = _simple_commands(toks)
    if ops or len(cmds) != 1:
        return reason
    cmd = cmds[0]
    if any(tok[0] != "w" or tok[2] for tok in cmd) or cmd[0][1] not in READ_ONLY:
        return reason
    return None


def _classify_bash(tool_input: dict) -> Call | None:
    command = tool_input.get("command")
    if not isinstance(command, str):
        raise Deny("G1: Bash input has no string command, expected a command string")
    reason = g8(command)  # first, and without any gh call
    if reason:
        raise Deny(reason)
    return _classify_text(command)


def classify(event: dict) -> Call | None:
    """The guarded call of a PreToolUse event, or None if the call is not guarded. Raises Deny."""
    if not isinstance(event, dict):
        raise Deny("guard error: the hook input is not a JSON object")
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool, str):
        raise Deny("guard error: the hook input has no tool_name")
    if tool not in SUBAGENT_TOOLS | {"SendMessage", "Bash"}:
        return None
    if not isinstance(tool_input, dict):
        raise Deny(f"G1: {tool} input is not an object, expected a tool_input object")
    if tool in SUBAGENT_TOOLS:
        return _classify_agent(tool_input)
    if tool == "SendMessage":
        return _classify_send(tool_input)
    return _classify_bash(tool_input)


def decide(event: dict, read_facts, post_comment, lock=contextlib.nullcontext) -> str | None:
    """Deny reason, or None to let the call through. `lock()` is held from reading
    the facts until the launch comment is posted (spec 5.7)."""
    try:
        call = classify(event)
    except Deny as e:
        return str(e)
    if call is None:
        return None
    with lock():
        facts = read_facts(call.issue)
        reason = issue_state.check(call, facts)
        if reason:
            return reason
        if call.role != "close":
            post_comment(call.issue, issue_state.launch_comment(call, issue_state.attempt(facts.issue, call.role)))
    return None


# --- I/O --------------------------------------------------------------------------------


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0].rstrip()[:STDERR_MAX]


class _Deadline(Deny):
    pass


class _IO:
    """`gh` and `git` calls within one overall deadline."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self.end = time.monotonic() + seconds

    def deadline(self) -> _Deadline:
        return _Deadline(f"guard: deadline of {self.seconds:g} s reached before the checks finished, call denied")

    def remaining(self) -> float:
        return self.end - time.monotonic()

    def run(self, args: list[str], stdin: str | None = None) -> str:
        name = " ".join(args[:3])
        left = self.remaining()
        if left <= 0:
            raise self.deadline()
        timeout = min(CALL_TIMEOUT_S, left)
        try:
            p = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise Deny(f"guard error: {args[0]} not found on PATH") from None
        except subprocess.TimeoutExpired:
            if timeout < CALL_TIMEOUT_S:
                raise self.deadline() from None
            raise Deny(f"guard error: {name} timed out after {CALL_TIMEOUT_S} s") from None
        if p.returncode != 0:
            raise Deny(f"guard error: {name} failed with exit code {p.returncode}: {_first_line(p.stderr)}")
        return p.stdout

    def read_facts(self, number: int) -> issue_state.Facts:
        data = json.loads(self.run(["gh", "issue", "view", str(number), "--json",
                                    "number,state,labels,body,comments"]))
        head = self.run(["git", "rev-parse", "HEAD"]).strip()
        clean = self.run(["git", "status", "--porcelain"]).strip() == ""
        return issue_state.Facts(issue=issue_state.parse_issue(data), head=head, clean=clean)

    def post_comment(self, number: int, body: str) -> None:
        self.run(["gh", "issue", "comment", str(number), "--body-file", "-"], stdin=body)

    @contextlib.contextmanager
    def lock(self):
        git_dir = self.run(["git", "rev-parse", "--git-dir"]).strip()
        if not git_dir:
            raise Deny("guard error: git rev-parse --git-dir printed nothing")
        fd = os.open(Path(git_dir) / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if self.remaining() <= 0:
                        raise self.deadline() from None
                    time.sleep(0.05)
            yield
        finally:
            os.close(fd)  # releases the lock


def _deadline_seconds() -> float:
    raw = os.environ.get("GUARD_DEADLINE", str(DEFAULT_DEADLINE_S))
    value = float(raw)
    if not value > 0 or value == float("inf"):
        raise ValueError(f"GUARD_DEADLINE must be a positive number of seconds, got {raw[:20]}")
    return value


@contextlib.contextmanager
def _alarm(io: _IO):
    """Backstop: raise the deadline deny wherever the guard hangs (for example on stdin)."""
    usable = hasattr(signal, "setitimer") and os.name == "posix"
    if usable:
        try:
            def fire(signum, frame):
                raise io.deadline()
            old = signal.signal(signal.SIGALRM, fire)
        except ValueError:  # not the main thread
            usable = False
    if usable:
        signal.setitimer(signal.ITIMER_REAL, max(io.remaining(), 0.01))
    try:
        yield
    finally:
        if usable:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)


def main(stdin=sys.stdin, stdout=sys.stdout) -> int:
    """Always returns 0. Prints the deny JSON, or nothing when the call may run."""
    try:
        io = _IO(_deadline_seconds())
        with _alarm(io):
            try:
                event = json.load(stdin)
            except ValueError as e:
                raise Deny(f"guard error: the hook input is not valid JSON ({_first_line(str(e))})") from None
            reason = decide(event, io.read_facts, io.post_comment, lock=io.lock)
    except Deny as e:
        reason = str(e)
    except BaseException as e:  # a crash must never let the call through
        reason = f"guard error: {type(e).__name__}: {_first_line(str(e))}"
    if reason:
        stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                        "permissionDecision": "deny",
                                                        "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
