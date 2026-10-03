#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse guard hook (docs/specs/agent-graph-kit.md#launch-contract, G1 to G8).

Reads one hook event on stdin. A guarded call (a role launch of pm, engineer,
qa or planner, a SendMessage continuation, `qa-codex`, `gh issue close`) is
checked against the issue state with `issue_state`. The planner (issue #99) is
launched only as a new subagent launch on an open issue with the label `stage`:
a SendMessage with ROLE=planner is denied, and the guard reads no blockers for
a planner launch. An allowed launch gets its launch comment before the guard
exits. A deny is printed as the PreToolUse deny JSON with exit code 0. An
allowed call prints nothing, so the normal permission check stays on.

Any error denies: a failing `gh` or `git`, broken input, a crash, and the
overall deadline (GUARD_DEADLINE seconds, default 60). Stdlib only.

Bash commands (docs/specs/agent-graph-kit.md#bash-rule-of-g1, issue #107): the guard reads the command with the
shell tokenizer below (the one G8 uses) and looks at every simple command in
it, also inside $(…), backticks, <(…), >(…) and the substitutions of an
unquoted here-document body. The command word is the first word after
assignments, redirections with their target and the reserved words. A close
run is `gh` (or a path ending in /gh) with the words `issue` and then `close`
after it; a launcher run is `qa-codex` (or a path ending in /qa-codex). A
runner (RUNNER_COMMANDS: bash -c, eval, xargs, env, python3 …) counts as a
run when the old word rule triggers on the text (the words `gh` and `close`,
or the text `qa-codex`); these false denies are accepted. A command with a
run is a guarded call only if its whole text is one of two exact forms
(CLOSE_FORM, QA_FORM); otherwise it is denied. A command without a run
passes, also when it holds the words in a comment, an array assignment or
an argument (`cat scripts/qa-codex`, a here-document body, a commit
message). An array assignment NAME=(…) is read as one word, as bash reads
it, and `case` is read both ways (reserved anywhere, and only where bash
reads it); a run found in either reading counts. A command the tokenizer
cannot read is denied if the old word rule triggers, and passes otherwise.

Known limits by design (P1, hooks are not a security boundary): variables
and other expansions in the command word (`$GH issue close 5`,
`"$x"gh issue close 5`), brace expansion, globs, other letter case, runners
not in the list, a script file that holds a close run, and calls outside the
prescribed ones (`gh api`, `gh issue edit --state closed`) are not recognized.
"""

from __future__ import annotations

import contextlib
import dataclasses
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
AGENT_ROLE = {"pm": "pm", "software-engineer": "engineer", "frontend-engineer": "engineer", "qa-engineer": "qa",
              "planner": "planner"}  # the planner: issue #99
LAUNCH_LINE = re.compile(r"ROLE=(pm|engineer|qa|planner) ISSUE=([0-9]+)")
LAUNCH_HINT = "exactly one line ROLE=<pm|engineer|qa|planner> ISSUE=<number>"
PLANNER_CONTINUED = ("G1: SendMessage with ROLE=planner: a planner cannot be continued (it posts one comment "
                     "and ends), expected a new launch of the agent planner")

DEFAULT_DEADLINE_S = 60  # docs/specs/agent-graph-kit.md#failure-behavior
CALL_TIMEOUT_S = 20  # per gh/git call
STDERR_MAX = 200  # P5: first stderr line, cut to 200 characters
LOCK_NAME = "agent-graph-kit-guard.lock"

# The two blocker reads (issue #64, read form from the #95 report). {owner}/{repo} is filled in by gh.
BLOCKERS_JQ = ".[] | {repo: .repository.full_name, number, state}"
OPEN_BLOCKERS_JQ = ".issue_dependencies_summary.blocked_by"
# The two sub-issue reads of a stage close (issue #97, read form from the #95 report, "Consequences").
SUB_ISSUES_JQ = ".[] | {repo: .repository.full_name, number, state}"
SUB_ISSUE_TOTAL_JQ = ".sub_issues_summary.total"

# Bash rule of G1 (docs/specs/agent-graph-kit.md#bash-rule-of-g1): what a real run is, the old word rule, and the only two forms a run may have.
CLI_NAME = "gh"
LAUNCHER_NAME = "qa-codex"
GH_WORD = re.compile(r"\bgh\b", re.ASCII)
CLOSE_WORD = re.compile(r"\bclose\b", re.ASCII)
CLOSE_FORM = re.compile(
    r"""gh issue close ([1-9][0-9]*)(?:(?: --reason | --reason=| -r )(?:completed|'not planned'|"not planned"))?[ \t]*\n?""")
QA_FORM = re.compile(r"scripts/qa-codex ROLE=qa ISSUE=([1-9][0-9]*)[ \t]*\n?")
# Commands that can run another command from their arguments, from stdin or from a here-document.
RUNNER_COMMANDS = frozenset({
    "command", "builtin", "exec", "env", "time", "coproc", "nohup", "sudo", "doas", "nice", "timeout", "xargs",
    "setsid", "stdbuf", "watch", "find", "parallel", "flock", "eval", "source", ".", "function",
    "bash", "sh", "zsh", "dash", "ksh", "fish", "python", "python3", "uv", "uvx", "perl", "ruby", "node", "npx",
    "bunx", "make", "script", "ssh",
    # more of the same kind
    "ionice", "chrt", "taskset", "unbuffer", "strace", "ltrace", "chroot", "nsenter", "unshare", "su", "runuser",
    "pkexec", "busybox", "ash", "mksh", "csh", "tcsh", "pwsh", "awk", "gawk", "mawk", "php", "lua", "deno", "bun",
    "npm", "pnpm", "yarn", "pipx", "poetry", "just", "trap",
})
_RESERVED_WORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until"}
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=")  # NAME=value, a[i]=value, NAME+=value
TRIGGER_DENY = (
    "G1: the command runs gh issue close or qa-codex (or may run it through a runner such as bash -c, eval, "
    "xargs or env) but is not one of the two exact forms: gh issue close <n> (optionally --reason completed "
    "or --reason 'not planned'), or scripts/qa-codex ROLE=qa ISSUE=<n>. The run must be the whole command: "
    "no operators, redirections, wrappers or substitutions. Run qa-codex with the Bash tool's "
    "run_in_background option instead of &. Text that only mentions these words passes, for example a body "
    "written to a file with a quoted here-document (cat > /tmp/body.md <<'EOF' … EOF)")

# G8 (docs/specs/agent-graph-kit.md#g8-settings-protection)
SETTINGS_NAME = re.compile(r"settings[^/\s]*\.json", re.IGNORECASE)
CLAUDE_GLOB = re.compile(r"\.claude/[^\s'\"]*[*?\[]")
READ_ONLY = {"cat", "jq", "head", "tail", "grep", "wc", "ls"}
_NO_BRACES = str.maketrans("", "", "{},")
_PART_SEPARATORS = {";", "&&", "||", "&", "\n", ";;", ";&", ";;&"}
_PIPES = {"|", "|&"}
# First words of a group or a compound command: data can flow from a part before a separator into a pipe after it.
_COMPOUND = {"{", "}", "if", "then", "else", "elif", "fi", "case", "esac", "for", "select", "while", "until", "do",
             "done", "function", "coproc"}
# Words that end a group or a compound command. A redirection after them takes the output of the whole group.
_CLOSERS = {"}", "fi", "done", "esac"}
G8_DENY = (
    "G8: the command may write to .claude/settings*.json. A command that names these files passes only when every "
    f"simple command that names them is one {', '.join(sorted(READ_ONLY))} command without redirections or "
    "substitutions, a pipe in the same part has only such commands, and no runner (bash, xargs, eval …) and no $_ "
    "is used. Way around: split the command so the parts that name the protected files are read-only commands, "
    "or use the Read or Grep tool. A here-document body only mentions the files unless a pipe or a runner reads it")


class Deny(Exception):
    """The call is denied. The message is the deny reason."""


# --- shell tokenizer ------------------------------------------------------------------
#
# A small bash-like tokenizer for G8 and for the Bash rule of G1 (docs/specs/agent-graph-kit.md#bash-rule-of-g1), which
# finds the simple commands that really run. It knows quotes ('…', "…", $'…', $"…"), backslashes,
# line continuations, $name, ${…}, $(…), <(…), >(…), backticks, arithmetic ((…)),
# $((…)), $[…] and subscripts a[…], operators, redirections (also with {fd}),
# here-documents, comments and the patterns of `case`. As in bash, `#` starts a
# comment only at the start of a word, so `echo x#; ls` has two commands.
#
# Tokens: ("w", value, subs) a word, quotes removed, `subs` the texts inside $(…),
# <(…), >(…), backticks, arithmetic and subscripts (unquoted or in double quotes);
# ("op", op) a command separator, also "((" before an arithmetic command; ("redir", op)
# a redirection; ("body", text, subs) a here-document body, one per `<<` or `<<-` in the order of
# these redirections, with its text and (only in an unquoted body) the substitutions in it.
# G8 uses it as it is. G1 sets `arrays` (NAME=(…) is one word) and reads once with `case_anywhere`
# and once without it (`case` is a reserved word only where bash reads one).

_OPS = (";;&", "&>>", "<<<", "<<-", "&&", "||", "|&", ";;", ";&", ">>", ">|", "<>", "<&", ">&",
        "&>", "<<", ";", "&", "|", "(", ")", "<", ">")
_REDIRECTS = {"<", ">", ">>", ">|", "<>", "<&", ">&", "&>", "&>>", "<<", "<<-", "<<<"}
_CASE_NEXT = {";;", ";&", ";;&"}  # end a case branch; a pattern follows
_COMMAND_FOLLOWS = {"{", "!", "if", "then", "else", "elif", "do", "while", "until", "time"}
_JOINABLE = (*_OPS, "<(", ">(", "((", "))", "$'", '$"', "${", "$(", "$((", "$[", "$$")  # tokens of more than one character
_MAX_NESTING = 100  # deeper $…, <(…) and >(…) nesting cannot be parsed
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ARRAY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")  # NAME= or NAME+= before the `(` of an array
_PARAMETER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9!@#?$*-]")  # $name, $1, $!, $$ …
_NAMED_FD = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")  # {fd}>file: bash puts the new fd number in $fd
_ANSI = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
         "\\": "\\", "'": "'", '"': '"', "?": "?"}
_ANSI_NUMBER = {"x": (16, 2), "u": (16, 4), "U": (16, 8)}


class _Lexer:
    # The text self.t can get shorter while the lexer runs: `join` removes line continuations
    # ahead of the current position. So every loop reads self.t and self.n again, and a
    # position returned by a nested call is a position in the new text.

    def __init__(self, text: str, case_anywhere: bool = True, arrays: bool = False):
        self.t = text
        self.n = len(text)
        self.level = 0  # nesting of $…, <(…) and >(…)
        self.case_anywhere = case_anywhere
        self.arrays = arrays
        self.underscore = False  # bash expands $_, ${_} or ${_…} somewhere in the text it read

    def join(self, i: int) -> None:
        """Remove the line continuations (backslash-newline) inside the token that starts at i.
        Bash removes them before it reads a token, so `$\\<newline>'` is `$'` and `<\\<newline><` is `<<`.
        It stops after the token, so a `#` after it and the comment behind it stay as they are."""
        j = i + 1
        while j <= self.n:
            while self.t.startswith("\\\n", j):
                self.t = self.t[:j] + self.t[j + 2:]
                self.n -= 2
            head = self.t[i:j + 1]
            if j < self.n and any(len(tok) > len(head) and tok.startswith(head) for tok in _JOINABLE):
                j += 1
            else:
                return

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
        # only keeps more text inside a $(, and G8 denies a settings name with a substitution.
        cases: list[list] = []
        # case_anywhere=False: `case` is a reserved word only where bash reads one, at the start of a
        # command (`start`) or after the words that bash allows before it (`ext`): `time`, `time -p`,
        # `time --`, `coproc`, `coproc NAME`, `function NAME`. `lead` is the last of these words.
        ext, lead = False, None

        def end():
            nonlocal buf, subs, word, quoted, start, ext, lead
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
                elif plain and value == "case" and (self.case_anywhere or start or ext):
                    cases.append(["word", False])
                at_command = start or ext
                if at_command and plain and value in ("coproc", "function", "time"):
                    lead, ext = value, True
                elif lead in ("coproc", "function"):
                    lead, ext = None, True
                elif lead == "time" and plain and value == "-p":
                    lead, ext = "time -p", True
                elif lead in ("time", "time -p") and plain and value == "--":
                    lead, ext = None, True
                else:
                    lead, ext = None, False
                start = plain and value in _COMMAND_FOLLOWS
            buf, subs, word, quoted = [], [], False, False

        while i < self.n:
            t, n = self.t, self.n
            c = t[i]
            if c in "$<>&|;(":
                self.join(i)
                t, n = self.t, self.n
            state = cases[-1][0] if cases else None
            if (self.arrays and c == "(" and word and not quoted and not subs and state != "pattern"
                    and _ARRAY_NAME.fullmatch("".join(buf))):
                i = self.array(i, buf, subs)  # NAME=(…) is one word, so `x=(a)#` has no comment
                continue
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
                    body_subs: list[str] = []
                    if not q:
                        body_lexer = _Lexer(body, self.case_anywhere, self.arrays)
                        body_lexer.double(0, [], body_subs, None)
                        self.underscore = self.underscore or body_lexer.underscore
                    toks.append(("body", body, tuple(body_subs)))
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
            elif c == "$":
                i, is_quoted = self.dollar(i, buf, subs)
                word = True
                quoted = quoted or is_quoted
            elif c in "<>" and t.startswith(("<(", ">("), i):  # process substitution, a word part like $(…)
                i = self.procsub(i, buf, subs)
                word = True
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
                if op == "(":
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
                    sub_end := self.arith(i + 1, "]")):
                # A subscript, as in `a[1<<2]=x`, `a[1<<2]` as the first word or `a=( [1<<2]=x )`, is one unit:
                # `<<` in it is no here-document. Bash reads an argument `a[…]` as a unit only in some
                # places. Reading it as a unit everywhere is safe for G8: the text inside counts as a
                # substitution, so a settings name next to it is denied. It is kept with a letter before
                # it: in bash, a `#` after the `[` is inside a word and starts no comment.
                j, inner, inner_subs = sub_end
                buf.append(self.t[i:j])
                subs.extend((*inner_subs, "x" + inner))
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
        """What starts with `$` at i: the quotes $'…' and $"…", or an expansion $name, $1, $$, ${…},
        $(…), $((…)), $[…], or a plain `$`.
        Returns (index after it, whether it is a quote)."""
        self.level += 1
        try:
            return self._dollar(i, buf, subs, dq)
        finally:
            self.level -= 1

    def _dollar(self, i: int, buf: list[str], subs: list[str], dq: bool) -> tuple[int, bool]:
        if self.level > _MAX_NESTING:
            raise ValueError("the command is nested too deeply")
        self.join(i)
        t = self.t
        if t.startswith("$'", i) and not dq:
            return self.ansi(i + 2, buf), True
        if t.startswith('$"', i) and not dq:
            return self.double(i + 2, buf, subs, '"'), True
        part: list[str] = []
        if t.startswith("${", i):
            j = self.brace(i, part, subs, dq)
            self.underscore = self.underscore or t.startswith("${_", i)
        elif m := _PARAMETER.match(t, i + 1):  # $$ is the process id, so a quote after it is a plain quote
            j = m.end()
            part.append(t[i:j])
            self.underscore = self.underscore or m.group() == "_"
        else:
            j = self.expression(i, part, subs)
        if not part:
            buf.append("$")
            return i + 1, False
        buf.append("".join(part))
        return j, False

    def expression(self, i: int, buf: list[str], subs: list[str]) -> int:
        """$(…), $((…)) or $[…] at i, else nothing. Returns the index after it."""
        t = self.t
        if t.startswith("$[", i):
            arith = self.arith(i + 2, "]")
            if not arith:
                raise ValueError("unterminated $[")
        elif t.startswith("$((", i):
            arith = self.arith(i + 3, "))")
        elif t.startswith("$(", i):
            arith = None
        else:
            return i
        if arith:  # the text inside is also kept as a substitution: $((…) ) may be a $( (…) )
            j, inner, inner_subs = arith
            subs.extend((*inner_subs, inner))
        else:
            _, j = self.script(i + 2, sub=True)
            subs.append(self.t[i + 2:j - 1])
        buf.append(self.t[i:j])
        return j

    def procsub(self, i: int, buf: list[str], subs: list[str]) -> int:
        if self.level >= _MAX_NESTING:
            raise ValueError("the command is nested too deeply")
        self.level += 1
        try:
            _, j = self.script(i + 2, sub=True)
        finally:
            self.level -= 1
        subs.append(self.t[i + 2:j - 1])
        buf.append(self.t[i:j])
        return j

    def array(self, i: int, buf: list[str], subs: list[str]) -> int:
        """A compound array assignment NAME=(…) from its `(` at i, as part of the word (arrays=True).
        The substitutions in its elements are kept. An operator other than a newline in it is a syntax
        error in bash, after which bash may go on with the next line: the text cannot be read."""
        if self.level >= _MAX_NESTING:
            raise ValueError("the command is nested too deeply")
        self.level += 1
        try:
            toks, j = self.script(i + 1, sub=True)
        finally:
            self.level -= 1
        if any(tok[0] == "redir" or (tok[0] == "op" and tok[1] != "\n") for tok in toks):
            raise ValueError("an operator inside an array assignment")
        for tok in toks:
            if tok[0] in ("w", "body"):
                subs.extend(tok[2])
        buf.append(self.t[i:j])
        return j

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
                self.join(j)
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
            elif c in "<>" and not dq:
                self.join(j)
                if self.t.startswith(("<(", ">("), j):
                    j = self.procsub(j, [], subs)
                else:
                    j += 1
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


def _lex(command: str, case_anywhere: bool = True, arrays: bool = False) -> list[tuple]:
    """Tokens of the command. Raises ValueError if it cannot be parsed.
    G8 uses the defaults. G1 reads array assignments NAME=(…) as one word (arrays=True), and reads the
    command twice: with `case` as a reserved word anywhere, and only where bash reads one."""
    try:
        return _Lexer(command, case_anywhere, arrays).script(0, sub=False)[0]
    except RecursionError:
        raise ValueError("the command is nested too deeply") from None


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
    if role == issue_state.PLANNER:
        raise Deny(PLANNER_CONTINUED)
    return Call(role=role, agent=to, issue=number, continued=True)


def _triggered(text: str) -> bool:
    """The old word rule: the words gh and close, or the text qa-codex."""
    return bool(GH_WORD.search(text) and CLOSE_WORD.search(text)) or LAUNCHER_NAME in text


def _check_simple_command(cmd: list[tuple], found: set[str]) -> None:
    """Add "run" to `found` for a close run or a launcher run, "runner" for a runner."""
    words, target = [], False
    for tok in cmd:
        if tok[0] == "redir":
            target = True  # the next word is the target of the redirection
        elif tok[0] == "w":
            if not target:
                words.append(tok)
            target = False
    k = 0
    while k < len(words) and (words[k][1] in _RESERVED_WORDS or _ASSIGNMENT.match(words[k][1])):
        k += 1
    if k == len(words):
        return
    word = words[k][1]
    name = word.rsplit("/", 1)[-1]
    rest = [tok[1] for tok in words[k + 1:]]
    if name in RUNNER_COMMANDS:
        found.add("runner")
    if name == LAUNCHER_NAME or (name == CLI_NAME and "issue" in rest and "close" in rest[rest.index("issue") + 1:]):
        found.add("run")


def _scan(text: str, found: set[str], case_anywhere: bool, depth: int = 0) -> None:
    """Look at every simple command of `text`, also inside substitutions (recursively), and add to
    `found` what they do (see _check_simple_command). Raises ValueError when the text cannot be read."""
    if depth > _MAX_NESTING:
        raise ValueError("the command is nested too deeply")
    toks = _lex(text, case_anywhere=case_anywhere, arrays=True)
    cmd: list[tuple] = []
    arith = False  # the simple command after `((` is an arithmetic command, not a command word
    for tok in (*toks, ("op", "")):
        if tok[0] in ("w", "body"):
            for sub in tok[2]:
                _scan(sub, found, case_anywhere, depth + 1)
        if tok[0] != "op":
            cmd.append(tok)
            continue
        if not arith:
            _check_simple_command(cmd, found)
        arith = tok[1] == "(("
        cmd = []


def _runs_guarded(command: str) -> bool:
    """True when the command runs a close run or the launcher, or may run one
    (docs/specs/agent-graph-kit.md#bash-rule-of-g1).
    The tokenizer reads the command twice, with `case` as a reserved word anywhere and only where
    bash reads one, and a simple command found in either reading counts."""
    triggered = _triggered(command) or _triggered(command.replace("\\\n", ""))
    found: set[str] = set()
    try:
        for case_anywhere in (True, False):
            _scan(command, found, case_anywhere)
    except (ValueError, RecursionError):
        return triggered  # a command the tokenizer cannot read
    return "run" in found or (triggered and "runner" in found)


def _raw_mentions(text: str) -> bool:
    return bool(SETTINGS_NAME.search(text) or CLAUDE_GLOB.search(text))


def _value_mentions(value: str) -> bool:
    """A word after quote removal names a protected file, also with braces removed
    (settings.{json,bak} names settings.json)."""
    return any(SETTINGS_NAME.search(v) or (".claude/" in v and any(ch in v for ch in "*?["))
               for v in (value, value.translate(_NO_BRACES)))


def _text_mentions(text: str, depth: int = 0) -> bool:
    """The text of a substitution names a protected file: in its raw text, or in a word inside it
    (read with the tokenizer, recursively). Here-document bodies inside a substitution count too."""
    if _raw_mentions(text):
        return True
    if depth > _MAX_NESTING:
        return True
    try:
        toks = _lex(text)
    except ValueError:
        return False  # the raw text has no mention
    return any(_token_mentions(tok, depth + 1) for tok in toks)


def _token_mentions(tok: tuple, depth: int = 0) -> bool:
    if tok[0] == "w":
        return _value_mentions(tok[1]) or any(_text_mentions(s, depth) for s in tok[2])
    if tok[0] == "body":
        return _raw_mentions(tok[1]) or any(_text_mentions(s, depth) for s in tok[2])
    return False


def _command(cmd: list[tuple]) -> list[tuple]:
    """The simple command without the reserved words before it ({ ! if then else elif do while until),
    so `then cat x` is the command `cat x`."""
    k = 0
    while k < len(cmd) and cmd[k][0] == "w" and cmd[k][1] in _RESERVED_WORDS - {"}"}:
        k += 1
    return cmd[k:]


def _read_only(cmd: list[tuple]) -> bool:
    """One cat, grep, head, jq, ls, tail or wc command without redirections or substitutions."""
    cmd = _command(cmd)
    return bool(cmd) and all(tok[0] == "w" and not tok[2] for tok in cmd) and cmd[0][1] in READ_ONLY


def _closer(cmd: list[tuple]) -> bool:
    """The end of a group or a compound command (`}`, `fi`, `done`, `esac`, or what follows a `)`),
    with its redirections. False for a simple command."""
    cmd = _command(cmd)
    return bool(cmd) and (cmd[0][0] == "redir" or (cmd[0][0] == "w" and cmd[0][1] in _CLOSERS))


def _expands_underscore(text: str, depth: int = 0) -> bool:
    """Bash expands $_, ${_} or ${_…} (the last argument of the command before) somewhere in the text:
    not in single quotes, $'…', a quoted here-document or after a backslash. Substitutions count,
    also backticks. True when the text cannot be read."""
    if depth > _MAX_NESTING:
        return True
    lexer = _Lexer(text)
    try:
        toks = lexer.script(0, sub=False)[0]
    except (ValueError, RecursionError):
        return True
    return lexer.underscore or any(_expands_underscore(s, depth + 1)
                                   for tok in toks if tok[0] in ("w", "body") for s in tok[2])


def _has_runner(command: str) -> bool:
    """A simple command, also inside a substitution, runs a runner (RUNNER_COMMANDS). True when the
    command cannot be read this way."""
    found: set[str] = set()
    try:
        for case_anywhere in (True, False):
            _scan(command, found, case_anywhere)
    except (ValueError, RecursionError):
        return True
    return "runner" in found


def g8(command: str) -> str | None:
    """Deny reason if the command may write to .claude/settings*.json (G8, issue #86).

    A command that mentions a protected file (a settings*.json name or a .claude/ path with a glob
    character) passes only when (a) every simple command whose words, redirection targets or
    substitutions mention one is a read-only command (_read_only), (b) every part between the
    separators ; && || & and newline that holds a mention and a pipe has only read-only commands,
    (c) no simple command is a runner, and (d) bash expands no $_. Reserved words before a simple
    command (`then cat x`) are not part of it. A redirection after the end of a group or a compound
    command (`} > x`, `fi > x`, `) > x`) denies a command with a mention. The text of a here-document body is a
    mention only when the command has a pipe or a runner; the substitutions of an unquoted body always
    count, for the command that reads the body. A command the tokenizer cannot read is denied when its
    text mentions a protected file."""
    try:
        toks = _lex(command)
    except ValueError:
        return G8_DENY if _raw_mentions(command) else None
    cmds: list[list[tuple]] = [[]]
    part_of = [0]  # the part of each simple command
    own = [False]  # its words, redirection targets or substitutions (also of its bodies) mention a file
    body = [False]  # the text of one of its here-document bodies mentions a file
    readers: list[int] = []  # the simple command of each here-document, in order
    pipe_parts: set[int] = set()
    grouped = orphan = False
    part, prev = 0, None
    for tok in toks:
        if tok[0] == "op":
            if tok[1] in _PART_SEPARATORS:
                part += 1
            elif tok[1] in _PIPES:
                pipe_parts.add(part)
            else:
                grouped = True  # ( ) (( or a case pattern
            cmds.append([])
            part_of.append(part)
            own.append(False)
            body.append(False)
        elif tok[0] == "body":
            subs_mention = any(_text_mentions(s) for s in tok[2])
            if not readers:
                orphan = orphan or subs_mention or _raw_mentions(tok[1])
                continue
            k = readers.pop(0)
            own[k] = own[k] or subs_mention
            body[k] = body[k] or _raw_mentions(tok[1])
        else:
            if tok[0] == "w":
                if prev in (("redir", "<<"), ("redir", "<<-")):
                    readers.append(len(cmds) - 1)
                own[-1] = own[-1] or _token_mentions(tok)
                if not cmds[-1] and tok[1] in _COMPOUND:
                    grouped = True
            cmds[-1].append(tok)
        prev = tok
    piped = bool(pipe_parts)
    body_counts = any(body) and (piped or _has_runner(command))
    mentioned = [o or (b and body_counts) for o, b in zip(own, body)]
    if not (any(mentioned) or orphan):
        return None
    if orphan or _expands_underscore(command) or _has_runner(command):
        return G8_DENY
    if any(o and not _read_only(c) for o, c in zip(own, cmds)):
        return G8_DENY
    if any(_closer(c) and any(t[0] == "redir" for t in c) for c in cmds):
        return G8_DENY  # the output of a group with a mention goes to a file
    if grouped:  # a group or a subshell can pass data on across a separator: read it as one part
        part_of = [0] * len(cmds)
        pipe_parts = {0} if piped else set()
    for p in pipe_parts:
        members = [i for i in range(len(cmds)) if part_of[i] == p]
        rest = [c for i in members if (c := _command(cmds[i])) and not (len(c) == 1 and c[0][1] in _CLOSERS)]
        if any(mentioned[i] for i in members) and not all(_read_only(c) for c in rest):
            return G8_DENY
    return None


def _classify_bash(tool_input: dict) -> Call | None:
    command = tool_input.get("command")
    if not isinstance(command, str):
        raise Deny("G1: Bash input has no string command, expected a command string")
    reason = g8(command)  # G8 first, without any gh call
    if reason:
        raise Deny(reason)
    if not _runs_guarded(command):
        return None
    if m := CLOSE_FORM.fullmatch(command):  # always the original text, never the copy
        return Call(role="close", agent="", issue=int(m.group(1)))
    if m := QA_FORM.fullmatch(command):
        return Call(role="qa", agent="qa-codex", issue=int(m.group(1)))
    raise Deny(TRIGGER_DENY)


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


def event_call_hash(event: dict) -> str | None:
    """The call hash of the event's tool_use_id, or None when it has no string tool_use_id."""
    tool_use_id = event.get("tool_use_id") if isinstance(event, dict) else None
    return issue_state.call_hash(tool_use_id) if isinstance(tool_use_id, str) else None


def _no_blocker_reader(number: int):
    raise Deny(f"guard error: no reader for the blockers of issue #{number}")


def _no_sub_issue_reader(number: int):
    raise Deny(f"guard error: no reader for the sub-issues of issue #{number}")


def decide(event: dict, read_facts, post_comment, lock=contextlib.nullcontext,
           read_blockers=_no_blocker_reader, read_sub_issues=_no_sub_issue_reader) -> str | None:
    """Deny reason, or None to let the call through. `lock()` is held from reading
    the facts until the launch comment is posted (docs/specs/agent-graph-kit.md#failure-behavior). The launch comment has a
    `Call:` line when the event has a string tool_use_id (docs/specs/agent-graph-kit.md#launch-comments). For every role launch
    (not for close and not for the planner, issue #99), `read_blockers(n)` gives (blocker list,
    open-blocker count) inside the lock.
    Only for the close of a stage issue (issue #97) and a planner launch on an open stage issue
    (issue #119), `read_sub_issues(n)` gives (sub-issue list, sub_issues_summary.total) inside the lock."""
    try:
        call = classify(event)
    except Deny as e:
        return str(e)
    if call is None:
        return None
    with lock():
        facts = read_facts(call.issue)
        if call.role not in ("close", issue_state.PLANNER):
            blockers, count = read_blockers(call.issue)
            facts = dataclasses.replace(facts, blockers=blockers, open_blockers=count)
        elif issue_state.needs_sub_issues(call, facts.issue):
            subs, total = read_sub_issues(call.issue)
            facts = dataclasses.replace(facts, sub_issues=subs, sub_issue_total=total)
        reason = issue_state.check(call, facts)
        if reason:
            return reason
        if call.role != "close":
            post_comment(call.issue, issue_state.launch_comment(
                call, issue_state.attempt(facts.issue, call.role), event_call_hash(event)))
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
        return _Deadline(f"guard error: deadline of {self.seconds:g} s reached before the checks finished, call denied")

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

    def read_issue(self, number: int) -> issue_state.Issue:
        data = json.loads(self.run(["gh", "issue", "view", str(number), "--json",
                                    "number,state,labels,body,comments"]))
        return issue_state.parse_issue(data)

    def read_blockers(self, number: int) -> tuple[tuple[issue_state.Blocker, ...], int]:
        """(blocker list of all pages, open-blocker count) of issue `number`; output that cannot be read denies."""
        path = f"repos/{{owner}}/{{repo}}/issues/{number}"
        listed = self.run(["gh", "api", "--paginate", f"{path}/dependencies/blocked_by", "--jq", BLOCKERS_JQ])
        try:
            blockers = issue_state.parse_blockers(listed)
        except ValueError as e:
            raise Deny(f"guard error: the blocker list of #{number} cannot be read: {_first_line(str(e))}") from None
        counted = self.run(["gh", "api", path, "--jq", OPEN_BLOCKERS_JQ])
        try:
            count = issue_state.parse_open_blocker_count(counted)
        except ValueError as e:
            raise Deny(f"guard error: the open-blocker count of #{number} cannot be read: "
                       f"{_first_line(str(e))}") from None
        return blockers, count

    def read_sub_issues(self, number: int) -> tuple[tuple[issue_state.SubIssue, ...], int]:
        """(sub-issue list of all pages, sub_issues_summary.total) of stage issue `number` (issue #97);
        output that cannot be read denies."""
        path = f"repos/{{owner}}/{{repo}}/issues/{number}"
        listed = self.run(["gh", "api", "--paginate", f"{path}/sub_issues", "--jq", SUB_ISSUES_JQ])
        try:
            subs = issue_state.parse_sub_issues(listed)
        except ValueError as e:
            raise Deny(f"guard error: the sub-issue list of #{number} cannot be read: {_first_line(str(e))}") from None
        counted = self.run(["gh", "api", path, "--jq", SUB_ISSUE_TOTAL_JQ])
        try:
            total = issue_state.parse_sub_issue_total(counted)
        except ValueError as e:
            raise Deny(f"guard error: the sub-issue total of #{number} cannot be read: "
                       f"{_first_line(str(e))}") from None
        return subs, total

    def read_facts(self, number: int) -> issue_state.Facts:
        iss = self.read_issue(number)
        head = self.run(["git", "rev-parse", "HEAD"]).strip()
        clean = self.run(["git", "status", "--porcelain"]).strip() == ""
        return issue_state.Facts(issue=iss, head=head, clean=clean)

    def post_comment(self, number: int, body: str) -> None:
        self.run(["gh", "issue", "comment", str(number), "--body-file", "-"], stdin=body)

    def git_dir(self) -> Path:
        git_dir = self.run(["git", "rev-parse", "--git-dir"]).strip()
        if not git_dir:
            raise Deny("guard error: git rev-parse --git-dir printed nothing")
        return Path(git_dir)

    @contextlib.contextmanager
    def lock(self):
        fd = os.open(self.git_dir() / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
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
            reason = decide(event, io.read_facts, io.post_comment, lock=io.lock,
                            read_blockers=io.read_blockers, read_sub_issues=io.read_sub_issues)
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
