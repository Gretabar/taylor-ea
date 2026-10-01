"""What a Bash or PowerShell command line runs: one parser for every gate that has to ask.

NEW in this repo. Four gates ask what a shell command starts: require-active-agent (the
claude CLI), require-delivery-agent (scripts/docs_edit.py), require-privacy-agent
(scripts/privacy_review.py) and confine-read-only-agent (everything LARK starts). The
first three each carried their own tokenizer, and a review found the copies had
drifted: the dispatch gate missed a dozen ways to start `claude -p`, and the privacy
gate refused HUGO for reading a table whose name merely contains the script's.

HOW A COMMAND IS READ, crude but in one place:

  1. Split into simple commands at separators outside quotes: ; && || | & newline
     ( ) { }. A lone & is PowerShell's call operator or bash's background operator;
     either way what follows is a command. `2>&1` and `&>` are redirections. $(...)
     is cut out and read as a command of its own wherever it appears, and so is
     `...` in bash.
  2. Split each simple command into words, removing quotes and escapes.
  3. Unwrap what only launches something else: assignments ($out = ..., X=1 ...),
     env, timeout, nohup, nice, xargs, npx, wsl, runas, uv/poetry/pipenv/conda run,
     cmd /c, powershell or pwsh -c / -Command / -EncodedCommand (decoded), bash -c,
     iex / Invoke-Expression, Start-Process / start, and ii / Invoke-Item, which
     executes the item it opens. A shell or iex handed no command reads one from the
     pipe, so the quoted strings on the line are read as commands too.

TWO DIALECTS, BOTH APPLIED. Bash escapes with a backslash, substitutes with backticks,
decodes $'\\x70' and has heredocs; PowerShell escapes with a backtick, keeps
backslashes, has here-strings (@"..."@), reads typographic quotes and dashes as plain
ones, and treats a quoted word at the head of a command as a string, not a program. A
command is read both ways and the deny-list gates take the union, so a trick aimed at
one shell (p`ython, p\\ython, \\"; python ..., a here-string hiding a separator) is read
the way that shell reads it. The allowlist gate (confine-read-only-agent) reads a
command the way the tool's own shell does, because what that shell runs is all that
matters there.

invocations(command) is the list of (program, arguments) that results. A program name
is case-folded and stripped of its directory and of .exe, .cmd, .bat or .com.

runs_script(command, stem) is the scripts/<stem>.py question. It matches the SCRIPT,
never a longer name that contains it (the privacy_reviews table is not
privacy_review.py), and it fails toward "runs it":

  the script executed directly, or by an interpreter (python, py, python3.14, a
  variable used as a program), including -m and a -c string that names or imports it
  a runner module given the script as an argument: python -m trace, -m cProfile, -m
  pdb, -m coverage run
  a program this file does not know that is handed the script, or a reader that can
  execute (git -c, sed, awk, find) on a line that also names an interpreter

Reading the script (cat, grep, git log, Get-Content) runs nothing and passes.

WHAT IT DOES NOT DO, stated: it does not look inside the quoted arguments of an
ordinary program for the claude CLI (a capture whose text says "Claude -p" is not a
dispatch); it does not expand bash brace lists or honour PowerShell's --% token; and a
script that starts something without naming it on the command line is invisible to any
hook, which is why scripts/ is not writable on Taylor's machine. Its known false
positive errs toward refusing: the PowerShell reading has no heredocs, so a bash
heredoc whose body names the script beside an unfamiliar word reads as running it.

Standard library only and pure. Each reading is one pass over the command, and nested
wrappers are memoised, so a long or hostile command cannot run a gate into Claude
Code's hook timeout, which would let the call through. The guardrail self-test drives
every form above, and tests/test_hardening.py feeds it noise.
"""

from __future__ import annotations

import base64
import functools
import re

MAX_DEPTH = 4
BASH = "bash"
POWERSHELL = "powershell"
DIALECTS = (BASH, POWERSHELL)
SUBSTITUTION = "__SUBSTITUTION__"

_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PS_ASSIGNMENT = re.compile(r"^\$[\w:{}]+=(.*)$", re.S)
_PS_VARIABLE = re.compile(r"^\$[\w:{}]+$")
_INTERPRETER = re.compile(r"^(?:python|pythonw|py|pypy)(?:\d+(?:\.\d+)*)?[tw]?$")
_INTERPRETER_WORD = re.compile(r"(?<![\w.-])(?:python|pythonw|py|pypy)(?:\d+(?:\.\d+)*)?[tw]?(?:\.exe)?(?![\w-])", re.I)
_REDIRECT = re.compile(r"^(?:\d|\*|&)?(>>?|<)(.*)$", re.S)
_QUOTED = re.compile(r'"((?:[^"\\`]|[\\`].)*)"|\'([^\']*)\'', re.S)

# Leading words that only change how the next program runs.
_PREFIXES = frozenset({"&", ".", "call", "exec", "time", "nohup", "command", "builtin", "sudo", "--", SUBSTITUTION.lower()})
_POWERSHELL = frozenset({"powershell", "pwsh", "powershell_ise"})
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_RUNNERS = frozenset({"uv", "poetry", "pipenv", "hatch", "pdm", "rye", "conda", "mamba", "micromamba"})
_PACKAGE_RUNNERS = frozenset({"npx", "bunx", "pnpx"})

# Programs that read or move the files they are given and execute nothing.
PURE_READERS = frozenset({
    "cat", "type", "gc", "get-content", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "findstr",
    "select-string", "sls", "diff", "fc", "cmp", "ls", "dir", "gci", "get-childitem", "get-item", "gi",
    "test-path", "get-filehash", "sha256sum", "md5sum", "certutil", "echo", "printf", "write-output",
    "write-host", "stat", "file", "more", "less", "code", "notepad", "sort", "uniq", "cut", "tr", "xxd",
    "od", "strings", "cp", "copy", "copy-item", "cpi", "mv", "move", "move-item", "mi", "rm", "del",
    "remove-item", "ri", "out-file", "set-content", "add-content", "tee", "tee-object", "ruff", "black",
    "flake8", "pyflakes", "pylint", "mypy", "isort", "#",
})
# Readers that can also run a command they are handed (git -c alias.x='!...', sed's e,
# awk's system(), find -exec): they count only on a line that also names an interpreter.
CONDITIONAL_READERS = frozenset({"git", "sed", "awk", "gawk", "find", "vim", "vi"})
# python -m <module> <script>: modules that inspect a file without running it.
STATIC_MODULES = frozenset({"py_compile", "compileall", "tabnanny", "pyflakes", "flake8", "pycodestyle",
                            "black", "isort", "ruff", "mypy", "pylint"})


# --------------------------------------------------------------------------
# 1. simple commands, in one pass
# --------------------------------------------------------------------------

def segments(command: str, dialect: str = BASH) -> list[str]:
    """The simple commands in `command`, substitutions included, as raw text."""
    return _scan(command, dialect)[0]


_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")


def _scan(command: str, dialect: str) -> tuple[list[str], list[str]]:
    """(simple commands, bash heredoc bodies). One pass, linear in the length of the command.

    A heredoc body is data for the command it is attached to, not a command, so it is
    set aside; invocations() reads it as commands only when a shell or an interpreter
    on the line reads its program from stdin. An unquoted delimiter still expands
    $(...) inside the body, so what it substitutes is read as commands.
    """
    text = _normalise(command or "", dialect)
    escape = "\\" if dialect == BASH else "`"
    out: list[str] = []
    bodies: list[str] = []
    pending: list[tuple[str, bool, bool]] = []  # heredocs opened on this line: (delimiter, strip tabs, quoted)
    # One frame per open substitution: [chars, opener, quote outside it, open plain parentheses].
    frames: list[list] = [[[], "", None, 0]]
    quote = None  # None, "'", '"', or a PowerShell here-string: "@'" (literal) or '@"' (expanding)
    i, n = 0, len(text)

    def flush(frame: list) -> None:
        piece = "".join(frame[0]).strip()
        if piece:
            out.append(piece)
        frame[0] = []

    while i < n:
        c = text[i]
        frame = frames[-1]
        if quote in ("'", "@'"):
            frame[0].append(c)
            if quote == "'" and c == "'":
                quote = None
            elif quote == "@'" and c == "\n":
                close = _here_string_end(text, i + 1, "'@")
                if close:
                    frame[0].append(text[i + 1:close])
                    quote, i = None, close
                    continue
            i += 1
            continue
        if c == escape and i + 1 < n:
            frame[0].append(text[i:i + 2])  # kept for words(), never a separator or a quote
            i += 2
            continue
        if c == "$" and text.startswith("$(", i):
            frame[0].append(f" {SUBSTITUTION} ")
            frames.append([[], "$(", quote, 0])
            quote = None
            i += 2
            continue
        if c == "`" and dialect == BASH:
            if frame[1] == "`":
                flush(frame)
                frames.pop()
                quote = frame[2]
            else:
                frame[0].append(f" {SUBSTITUTION} ")
                frames.append([[], "`", quote, 0])
                quote = None
            i += 1
            continue
        if quote in ('"', '@"'):
            frame[0].append(c)
            if quote == '"' and c == '"':
                quote = None
            elif quote == '@"' and c == "\n":
                close = _here_string_end(text, i + 1, '"@')
                if close:
                    frame[0].append(text[i + 1:close])
                    quote, i = None, close
                    continue
            i += 1
            continue
        if dialect == POWERSHELL and c == "@" and i + 1 < n and text[i + 1] in "'\"" \
                and _rest_of_line_blank(text, i + 2):
            quote = "@" + text[i + 1]  # a here-string: it runs to a line that starts with "@ or '@
            frame[0].append(text[i:i + 2])
            i += 2
            continue
        if c in "'\"":
            quote = c
            frame[0].append(c)
            i += 1
            continue
        if c == ")" and frame[3] == 0 and frame[1] == "$(":
            flush(frame)
            frames.pop()
            quote = frame[2]
            i += 1
            continue
        if c in "()":
            frame[3] = frame[3] + 1 if c == "(" else max(frame[3] - 1, 0)
            flush(frame)
            i += 1
            continue
        if c == "&":
            before = text[i - 1] if i else ""
            after = text[i + 1] if i + 1 < n else ""
            if before == ">" or after == ">":
                frame[0].append(c)  # 2>&1, &>file: a redirection, not a separator
                i += 1
                continue
            if dialect == POWERSHELL and after != "&" and not any(piece.strip() for piece in frame[0]):
                frame[0].append("& ")  # PowerShell's call operator, kept: it makes a quoted head a program
                i += 1
                continue
            flush(frame)
            i += 2 if after == "&" else 1
            continue
        if c == "<" and dialect == BASH and text.startswith("<<", i) and not text.startswith("<<<", i):
            match = _HEREDOC.match(text, i)
            if match:
                pending.append((match.group(3), bool(match.group(1)), bool(match.group(2))))
                frame[0].append(" ")
                i = match.end()
                continue
        if c == "\n" and pending:
            flush(frame)
            i += 1
            for delimiter, strip_tabs, quoted in pending:
                body: list[str] = []
                while i < n:
                    end = text.find("\n", i)
                    line = text[i:] if end < 0 else text[i:end]
                    i = n if end < 0 else end + 1
                    if (line.lstrip("\t") if strip_tabs else line).rstrip("\r") == delimiter:
                        break
                    body.append(line)
                bodies.append("\n".join(body))
                if not quoted:
                    # An unquoted body still runs its $(...) and `...`: read it as one double-quoted
                    # string (quotes inside it are literal there) and keep only what it substitutes.
                    wrapped = '"' + bodies[-1].replace('"', "'") + '"'
                    out.extend(_scan(wrapped, dialect)[0][:-1])
            pending = []
            continue
        if c in ";|\n\r{}":
            flush(frame)
            i += 1
            continue
        frame[0].append(c)
        i += 1
    while frames:
        flush(frames.pop())
    return out, bodies


# PowerShell reads typographic quotes and dashes as their ASCII forms: a curly-quoted word
# is quoted, and an en dash before Command is -Command.
_PS_EQUIVALENTS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
                                 "\u201c": '"', "\u201d": '"', "\u201e": '"',
                                 "\u2013": "-", "\u2014": "-", "\u2015": "-"})


def _normalise(text: str, dialect: str) -> str:
    return text.translate(_PS_EQUIVALENTS) if dialect == POWERSHELL else text


def _rest_of_line_blank(text: str, i: int) -> bool:
    end = text.find("\n", i)
    return end >= 0 and not text[i:end].strip()


def _here_string_end(text: str, i: int, marker: str) -> int:
    """The index just past `marker` when the line starting at i closes a here-string, else 0.

    Leading blanks are allowed before the marker. If PowerShell is stricter than that, a
    line this reads as the end it reads as content, and the rest is read as commands,
    which errs toward refusing.
    """
    j = i
    while j < len(text) and text[j] in " \t":
        j += 1
    return j + len(marker) if text.startswith(marker, j) else 0


_ANSI_C_LETTERS = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "f": "\f", "v": "\v",
                   "\\": "\\", "'": "'", '"': '"', "?": "?"}


def _ansi_c(body: str) -> str:
    """Bash's $'...' quoting decoded: hex, unicode and octal escapes, and the usual letters."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c != "\\" or i + 1 >= len(body):
            out.append(c)
            i += 1
            continue
        nxt = body[i + 1]
        width = {"x": 2, "u": 4, "U": 8}.get(nxt)
        if width:
            digits = re.match(r"[0-9a-fA-F]{1,%d}" % width, body[i + 2:i + 2 + width])
            if digits:
                out.append(chr(min(int(digits.group(0), 16), 0x10FFFF)))
                i += 2 + len(digits.group(0))
                continue
        digits = re.match(r"[0-7]{1,3}", body[i + 1:i + 4])
        if digits:
            out.append(chr(int(digits.group(0), 8)))
            i += 1 + len(digits.group(0))
            continue
        out.append(_ANSI_C_LETTERS.get(nxt, "\\" + nxt))
        i += 2
    return "".join(out)


class Literal(str):
    """A PowerShell word that opened with a quote. At the head of a command it is a string
    expression, not a program: `$x = "python scripts/x.py"` runs nothing, unlike in bash."""


def words(segment: str, dialect: str = BASH) -> list[str]:
    """Split one simple command into words, removing quotes and escapes the way `dialect` does."""
    segment = _normalise(segment, dialect)
    escape = "\\" if dialect == BASH else "`"
    out: list[str] = []
    current: list[str] = []
    quote, quoted = None, False
    i, n = 0, len(segment)

    def emit() -> None:
        text = "".join(current)
        literal = dialect == POWERSHELL and (segment[start:start + 1] in ("'", '"')
                                             or segment[start:start + 2] in ("@'", '@"'))
        out.append(Literal(text) if literal else text)

    start = 0
    while i < n:
        c = segment[i]
        if quote in ("'", "@'"):
            close = _here_string_end(segment, i + 1, "'@") if quote == "@'" and c == "\n" else 0
            if close:
                quote, i = None, close
                continue
            if quote == "'" and c == "'":
                quote = None
            else:
                current.append(c)
            i += 1
            continue
        if c == escape and i + 1 < n:
            nxt = segment[i + 1]
            if quote == '"' and dialect == BASH and nxt not in '"\\$`\n':
                current.append(c)  # inside bash double quotes a backslash escapes only these
                i += 1
                continue
            current.append(nxt)
            i += 2
            continue
        if quote in ('"', '@"'):
            close = _here_string_end(segment, i + 1, '"@') if quote == '@"' and c == "\n" else 0
            if close:
                quote, i = None, close
                continue
            if quote == '"' and c == '"':
                quote = None
            else:
                current.append(c)
            i += 1
            continue
        if dialect == BASH and c == "$" and segment.startswith("$'", i):
            end = i + 2
            while end < n and segment[end] != "'":
                end += 2 if segment[end] == "\\" else 1
            current.append(_ansi_c(segment[i + 2:min(end, n)]))
            quoted = True
            i = end + 1
            continue
        if dialect == POWERSHELL and c == "@" and i + 1 < n and segment[i + 1] in "'\"" \
                and _rest_of_line_blank(segment, i + 2):
            quote, quoted = "@" + segment[i + 1], True
            i = segment.find("\n", i) + 1
            continue
        if c in "'\"":
            quote, quoted = c, True
            i += 1
            continue
        if c.isspace():
            if current or quoted:
                emit()
            current, quoted = [], False
            i += 1
            start = i
            continue
        current.append(c)
        i += 1
    if current or quoted:
        emit()
    return out


# --------------------------------------------------------------------------
# 2. what each simple command really starts
# --------------------------------------------------------------------------

def program_name(word: str) -> str:
    """'C:\\Python311\\python.exe' -> 'python'; '@anthropic-ai/claude-code' -> 'claude-code'."""
    name = (word or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in _SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def is_python(name: str) -> bool:
    """python, python3, python3.14, pythonw, py, pypy: a Python interpreter named outright."""
    return bool(_INTERPRETER.match(name))


def is_interpreter(name: str) -> bool:
    """A Python interpreter, or a variable used as a program, which might be one: the "might run it" reading."""
    return is_python(name) or name.startswith(("$", "%"))


def _decode_powershell(encoded: str) -> str:
    try:
        return base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-16-le", errors="replace")
    except (ValueError, TypeError):
        return ""


def _flag(word: str) -> str:
    """PowerShell and cmd accept /x for -x."""
    low = word.lower()
    return "-" + low[1:] if low.startswith("/") and len(low) > 1 else low


def _powershell(args: list[str], depth: int) -> list[tuple[str, list[str]]] | None:
    """The commands inside `powershell ... -Command ...`, or None when it names none."""
    with_value = {"-executionpolicy", "-ep", "-ex", "-windowstyle", "-w", "-inputformat", "-outputformat", "-of",
                  "-if", "-version", "-v", "-configurationname", "-workingdirectory", "-wd", "-settingsfile",
                  "-psconsolefile"}
    i = 0
    while i < len(args):
        flag = _flag(args[i])
        if flag in ("-c", "-cmd") or (flag.startswith("-co") and "-command".startswith(flag)):
            rest = args[i + 1:]
            return invocations(" ".join(rest), depth + 1) if rest and rest != ["-"] else None
        if flag in ("-e", "-ec", "-en") or (flag.startswith("-enc") and "-encodedcommand".startswith(flag)):
            return invocations(_decode_powershell(args[i + 1]) if i + 1 < len(args) else "", depth + 1)
        if flag in ("-f", "-file"):
            return [(program_name(args[i + 1]), args[i + 2:])] if i + 1 < len(args) else []
        if flag in with_value:
            i += 2
            continue
        if flag.startswith("-"):
            i += 1
            continue
        return invocations(" ".join(args[i:]), depth + 1)  # Windows PowerShell's default is -Command
    return None


def _start_process(args: list[str], depth: int) -> list[tuple[str, list[str]]]:
    """Start-Process / saps / start: the program it starts and the arguments it passes."""
    with_value = {"-filepath", "-file", "-path", "-argumentlist", "-args", "-workingdirectory", "-verb",
                  "-windowstyle", "-redirectstandardinput", "-redirectstandardoutput", "-redirectstandarderror",
                  "-credential", "-d"}
    program, passed, positional = None, [], []
    i = 0
    while i < len(args):
        arg, flag = args[i], _flag(args[i])
        if flag in ("-filepath", "-file", "-path") and i + 1 < len(args):
            program = args[i + 1]
            i += 2
            continue
        if flag in ("-argumentlist", "-args") and i + 1 < len(args):
            passed.append(args[i + 1])
            i += 2
            continue
        if flag in with_value:
            i += 2
            continue
        if not arg or (arg.startswith("-") and program is None and not positional) or (
                arg.startswith("/") and len(arg) <= 6 and program is None and not positional):
            i += 1  # switches, and cmd's own start options (/b, /min, /wait), and a "" title
            continue
        positional.append(arg)
        i += 1
    if program is None and positional:
        program, positional = positional[0], positional[1:]
    if program is None:
        return []
    flat = [piece for item in passed + positional for piece in re.split(r"[\s,]+", item) if piece]
    return _unwrap([str(program), *flat], depth + 1)  # what Start-Process starts is a program, quoted or not


def _skip_options(ws: list[str], k: int, takes_value: tuple[str, ...]) -> int:
    """The index of the first word at or after k that is not an option or an option's value."""
    while k < len(ws) and ws[k].startswith("-") and ws[k] != "-":
        k += 2 if ws[k] in takes_value and k + 1 < len(ws) else 1
    return k


def _unwrap(ws: list[str], depth: int) -> list[tuple[str, list[str]]]:
    """(program, args) for what this simple command starts, through every launcher above.

    Walks an index rather than slicing, so a command of n words costs O(n) here.
    """
    if depth > MAX_DEPTH:
        return []
    ws = list(ws)
    k = 0
    called = False  # PowerShell's & or . in front: a quoted head is then a program after all
    while k < len(ws):
        head = ws[k]
        low = head.lower()
        if not head or low in _PREFIXES or _ASSIGNMENT.match(head):
            called = called or low in ("&", ".")
            k += 1  # a prefix, or bash's NAME=value before the command
            continue
        if isinstance(head, Literal) and not called:
            return []  # PowerShell: a string expression, which runs nothing
        head = str(head)
        if _PS_VARIABLE.match(head) and k + 1 < len(ws) and ws[k + 1] in ("=", "+=", "-="):
            k += 2  # PowerShell: $out = command
            continue
        assigned = _PS_ASSIGNMENT.match(head)
        if assigned:
            if assigned.group(1):
                ws[k] = assigned.group(1)  # PowerShell: $out=command
            else:
                k += 1
            continue
        name = program_name(head)
        r = k + 1  # the first argument
        if name == "env":
            while r < len(ws) and (ws[r].startswith("-") or _ASSIGNMENT.match(ws[r])):
                if ws[r] in ("-S", "--split-string") and r + 1 < len(ws):
                    return invocations(" ".join(ws[r + 1:]), depth + 1)
                r += 2 if ws[r] in ("-u", "-C", "--unset", "--chdir") and r + 1 < len(ws) else 1
            k = r
            continue
        if name == "timeout":
            k = _skip_options(ws, r, ("-s", "-k", "--signal", "--kill-after")) + 1  # the duration, then the command
            continue
        if name in ("nice", "ionice", "stdbuf"):
            k = _skip_options(ws, r, ("-n", "-c"))
            continue
        if name == "xargs":
            k = _skip_options(ws, r, ("-n", "-I", "-L", "-P", "-d", "-a", "-E", "-s"))
            continue
        if name in _PACKAGE_RUNNERS:
            k = _skip_options(ws, r, ("-p", "--package", "-c", "--call"))
            continue
        if name == "wsl":
            r = _skip_options(ws, r, ("-d", "--distribution", "-u", "--user", "--cd", "--shell-type"))
            k = r + 1 if r < len(ws) and ws[r] in ("-e", "--exec", "--") else r
            continue
        rest = ws[r:]
        if name == "runas":
            commands = [a for a in rest if not a.startswith("/")]
            return invocations(commands[-1], depth + 1) if commands else []
        if name in _RUNNERS and rest and rest[0].lower() == "run":
            j = 1
            while j < len(rest) and rest[j].startswith("-") and rest[j] not in ("-m", "--module"):
                takes = rest[j] in ("-n", "--name", "-p", "--prefix", "--python", "--with", "--project",
                                    "--directory", "--env-file", "--group", "--extra", "--package")
                j += 2 if takes and j + 1 < len(rest) else 1
            if j < len(rest) and rest[j] in ("-m", "--module"):
                return [("python", ["-m", *rest[j + 1:]])]
            k = r + j
            continue
        if name == "cmd":
            for j, arg in enumerate(rest):
                if _flag(arg)[:2] in ("-c", "-k"):
                    tail = arg[2:]
                    inner = " ".join(([tail] if tail else []) + rest[j + 1:])
                    return invocations(re.sub(r"\^(.)", r"\1", inner), depth + 1)
            return [(name, rest)]
        if name in _POWERSHELL:
            found = _powershell(rest, depth)
            return [(name, rest)] if found is None else found
        if name in _SHELLS:
            for j, arg in enumerate(rest):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg) and j + 1 < len(rest):
                    return invocations(rest[j + 1], depth + 1)
            return [(name, rest)]
        if name in ("iex", "invoke-expression"):
            pieces = [a for a in rest if _flag(a) not in ("-command", "-c")]
            return invocations(" ".join(pieces), depth + 1) if pieces else [(name, [])]
        if name in ("start-process", "saps", "start"):
            return _start_process(rest, depth)
        if name in ("ii", "invoke-item"):
            return [(program_name(t), []) for t in rest if not t.startswith("-")]
        return [(name, rest)]
    return []


def _reads_commands_from_stdin(program: str, args: list[str]) -> bool:
    """A shell, or iex, handed no command of its own: it runs what the pipe gives it."""
    if program in ("iex", "invoke-expression") and not args:
        return True
    if program in _SHELLS | _POWERSHELL | {"cmd"}:
        return not args or args[-1:] == ["-"] or all(a.startswith("-") for a in args)
    return False


def invocations(command: str, depth: int = 0) -> list[tuple[str, list[str]]]:
    """Every (program, args) this command line starts, read as bash and as PowerShell."""
    return [(program, list(args)) for program, args in _invocations(command or "", depth)]


@functools.lru_cache(maxsize=512)
def _invocations(command: str, depth: int) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """invocations(), memoised: both dialects unwrap `powershell -c X` to the same X, and a
    nested wrapper would otherwise be read 2**depth times."""
    if depth > MAX_DEPTH or not command:
        return ()
    found: list[tuple[str, list[str]]] = []
    bodies: list[str] = []
    for dialect in DIALECTS:
        simple, heredocs = _scan(command, dialect)
        bodies.extend(heredocs)
        for segment in simple:
            found.extend(_unwrap(words(segment, dialect), depth))
    if any(_reads_commands_from_stdin(program, args) for program, args in found):
        for body in bodies:
            found.extend(invocations(body, depth + 1))
        for match in _QUOTED.finditer(command):
            literal = match.group(1) if match.group(1) is not None else match.group(2)
            found.extend(invocations(literal, depth + 1))
    return tuple((program, tuple(args)) for program, args in found)


# --------------------------------------------------------------------------
# 3. the questions the gates ask
# --------------------------------------------------------------------------

def _mentions(text: str, stem: str) -> bool:
    """`text` names scripts/<stem>.py: the file, an import of the module, or -m of it."""
    s = re.escape(stem)
    return bool(re.search(
        rf"(?<![\w-]){s}\.py\b"
        rf"|\bimport\s+(?:[\w.]{{1,100}}\s*,\s*){{0,20}}(?:[\w.]{{1,100}}\.)?{s}\b(?!\.py)"
        rf"|\bfrom\s+(?:[\w.]{{1,100}}\.)?{s}\s+import\b"
        rf"|\bfrom\s+[\w.]{{1,100}}\s+import\s+[\w\s,()]{{0,300}}\b{s}\b"
        rf"|\b(?:import_module|__import__|run_module|run_path)\(\s*['\"][^'\"]*\b{s}(?:\.py)?['\"]"
        rf"|(?:^|\s)-m\s*(?:[\w.]+\.)?{s}\b",
        text or "", re.I))


def _without_redirections(args: list[str]) -> tuple[list[str], str | None]:
    """The arguments with every redirection removed, and the file an input redirection reads."""
    kept, stdin_from = [], None
    i = 0
    while i < len(args):
        match = _REDIRECT.match(args[i])
        if match:
            target = match.group(2)
            if not target and i + 1 < len(args):
                target = args[i + 1]
                i += 1
            if match.group(1) == "<":
                stdin_from = target
            i += 1
            continue
        kept.append(args[i])
        i += 1
    return kept, stdin_from


def _module_runs(module: str, rest: list[str], stem: str) -> bool:
    """python -m <module> <rest>: the module is the script, or a runner handed the script."""
    name = module.lower().rsplit(".", 1)[-1]
    if name == stem.lower():
        return True
    if name in STATIC_MODULES:
        return False
    return _mentions(" ".join(rest), stem)


def _python_runs(args: list[str], stem: str, mentioned: bool) -> bool:
    """Does `python <args>` run scripts/<stem>.py? `mentioned`: the whole line names it."""
    script = f"{stem}.py".lower()
    args, stdin_from = _without_redirections(args)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            target = args[i + 1] if i + 1 < len(args) else None
            return mentioned if target is None or target.startswith(("$", "%")) else program_name(target) == script
        if arg == "-":
            return mentioned  # the program arrives on stdin, from the pipeline
        if arg.startswith("--"):
            i += 1
            continue
        if arg.startswith("-") and len(arg) > 1:
            skip_next = False
            for j, ch in enumerate(arg[1:], 1):
                glued = arg[j + 1:]
                if ch in "cm":
                    value = glued or (args[i + 1] if i + 1 < len(args) else "")
                    rest = args[i + 1:] if glued else args[i + 2:]
                    if ch == "c":
                        return _mentions(" ".join([value, *rest]), stem)
                    return _module_runs(value, rest, stem)
                if ch in "WXQ":
                    skip_next = not glued
                    break
            i += 2 if skip_next else 1
            continue
        if arg.startswith(("$", "%")):
            return mentioned  # a variable as the script: whatever it holds, the line named the script
        return program_name(arg) == script  # the first positional is the script
    if stdin_from is not None:
        return program_name(stdin_from) == script
    return mentioned  # no script, no -c, no -m: python reads its program from stdin


def runs_script(command: str, stem: str) -> bool:
    """True when this command line would run scripts/<stem>.py in any form this parser knows."""
    script = f"{stem}.py".lower()
    mentioned = _mentions(command or "", stem)
    for program, args in invocations(command or ""):
        joined = " ".join(args)
        if program == script:
            return True  # executed directly: ./scripts/x.py, cmd /c x.py, ii x.py, uv run x.py
        if is_interpreter(program):
            if _python_runs(args, stem, mentioned):
                return True
            continue
        if program in PURE_READERS:
            continue
        if program in CONDITIONAL_READERS:
            if _mentions(joined, stem) and _INTERPRETER_WORD.search(joined):
                return True
            continue
        if _mentions(joined, stem):
            return True  # a program this file does not know, handed the script
    return False


def program_runs(command: str, names: set[str] | frozenset[str]) -> list[list[str]]:
    """The argument list of every invocation of a program in `names`."""
    return [args for program, args in invocations(command or "") if program in names]


_SINKS = frozenset({"/dev/null", "$null", "nul", "nul:", "&1", "&2"})


def writes_by_redirect(command: str) -> bool:
    """True when a > or >> sends output to a file (not to /dev/null, $null or nul), read either way."""
    for dialect in DIALECTS:
        for segment in segments(command or "", dialect):
            ws = words(segment, dialect)
            for i, word in enumerate(ws):
                match = _REDIRECT.match(word)
                if not match or match.group(1) == "<":
                    continue
                target = match.group(2) or (ws[i + 1] if i + 1 < len(ws) else "")
                if target.lower() not in _SINKS:
                    return True
    return False
