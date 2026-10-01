"""What this turn did, for the roll call and the status line: dispatched, wrote, read only, or unknown.

NEW in this repo. PIPER's roll call has two outcomes, the team line or the solo block,
and the solo block fires on every turn without a dispatch. Here /owe and /morning are
dispatch-free by design, because they only read, so Taylor would see the eight-line
alarm every morning, learn to skim past it, and miss the one time it means something:
a capture the orchestrator did alone. The block's own text already says what it is
for ("if this turn captured, changed or wrote a record"). This module answers that
question, so the block fires only when the answer is yes.

FOUR OUTCOMES, decided in this order:

    DISPATCHED   the roster is not empty                          the TEAM line
    WROTE        no dispatch, and a tool use wrote or changed     the SOLO block
                 something
    UNVERIFIED   no dispatch and no write found, but part of the  the UNVERIFIED block
                 turn could not be read
    READ_ONLY    no dispatch, every tool use read, and all of the one quiet line
                 turn was read

WROTE outranks UNVERIFIED: one unreadable line next to an add-action is a solo write,
and the more specific alarm wins. UNVERIFIED outranks READ_ONLY because the quiet line
is a claim, "nothing written", and a turn that could not be read in full has not
earned it.

ONE PARSE. Everything comes from the same _transcript.turn_context() that names the
roster, so the turn the roll call reports on and the turn whose writes it counts are
the same turn by construction. require-dispatch.py reads the same boundary.

WHAT COUNTS AS WRITING.

  Any Write, Edit, MultiEdit or NotebookEdit tool use, whatever the path.

  A Bash or PowerShell command that runs:
    scripts/docs_edit.py      any invocation (it can only write)
    scripts/docs_propose.py   any invocation (it writes a proposal)
    scripts/register.py       any subcommand EXCEPT the readers listed in
                              REGISTER_READS. The list is of readers, not writers, so a
                              subcommand nobody has classified counts as a write: a new
                              reader costs one false alarm, a new writer missing from a
                              list of writers would cost a quiet line on a solo capture.
    scripts/link_docs.py      any flag outside LINK_DOCS_READS (--add, --set-map, and
                              --confirm, which unlocks live writes to that Doc)
    scripts/calendar_next.py  any flag outside CALENDAR_READS (--link-series)
  or that imports one of those modules inline, or runs a SQL write statement against
  the register database (there is no delete subcommand, so a delete would go that way).

  Not writes: docs_reconcile.py, ea_tick.py and calendar_next.py --refresh. They pull
  what somebody else wrote into the register, exactly as the scheduled tick does, and
  /owe and /morning run the reconcile every time.

COUNTS ATTEMPTS, NOT OUTCOMES. A Write that a gate blocked still counts, and so does
docs_edit.py refused by require-delivery-agent.py. The transcript cannot prove a
failed command wrote nothing, and an orchestrator that tried to write alone is the
failure pattern even when a gate caught it.

WHAT IT DOES NOT SEE, stated. A shell redirect or Set-Content into a record directory
(require-dispatch.py does not see those either), a script's source piped into an
interpreter, and MCP tools (Phase 1 configures none). Crude on purpose, like
require-delivery-agent.py: every rule errs toward the alarm, and the cost of the
crudeness is a rare false SOLO, which is the behaviour this replaced.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _transcript import TranscriptUnreadable, TurnContext, roster, turn_context  # noqa: E402

DISPATCHED = "dispatched"
WROTE = "wrote"
UNVERIFIED = "unverified"
READ_ONLY = "read_only"

WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

ALWAYS_WRITES = frozenset({"docs_edit", "docs_propose"})
REGISTER_READS = frozenset({"owed", "history", "morning", "resolve-date", "resolve-person", "topics", "show"})
NEEDS_INPUT_READS = frozenset({"list"})
LINK_DOCS_READS = frozenset({"--status", "--verify", "--detect", "--person", "--doc", "--map-file"})
CALENDAR_READS = frozenset({"--status", "--refresh", "--discover", "--person", "--days", "--calendar"})
WATCHED = ALWAYS_WRITES | {"register", "link_docs", "calendar_next"}

# Programs that read a file named on their command line without running it, so a
# watched script named after one is an argument: `grep -n add-action scripts/register.py`.
# Anything else leading a command, an interpreter, a wrapper or a program this list has
# never heard of, is taken to run the watched script that follows it.
READERS = frozenset({
    "cat", "type", "gc", "get-content", "more", "less", "head", "tail", "grep", "egrep", "fgrep",
    "rg", "findstr", "select-string", "sls", "sed", "awk", "wc", "diff", "fc", "git", "ls", "dir",
    "get-childitem", "gci", "get-item", "gi", "test-path", "get-filehash", "sha256sum", "certutil",
    "echo", "printf", "write-output", "write-host", "code", "notepad", "file", "stat", "#",
})
PREFIXES = frozenset({"&", ".", "call", "start", "exec", "do", "then", "else", "time", "nohup"})

SEPARATORS = re.compile(r"\|\||&&|[;|\r\n]")
QUOTES = str.maketrans({'"': " ", "'": " ", "`": " "})
WRAPPING = "()[]{}$@,"
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
INLINE_IMPORT = re.compile(
    r"\b(?:import|from)\s+(?:scripts\.)?(?:docs_edit|docs_propose|register|link_docs|calendar_next)\b")
REGISTER_DB = re.compile(r"\b(?:ea|fixtures)\.db\b|\bea_db\b", re.I)
SQL_WRITE = re.compile(
    r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM"
    r"|DROP\s+(?:TABLE|INDEX|VIEW|TRIGGER)|ALTER\s+TABLE|CREATE\s+(?:TABLE|INDEX|VIEW|TRIGGER))\b",
    re.I)


@dataclass(frozen=True)
class Verdict:
    """One turn, classified. `why` names the write found or what could not be read."""

    kind: str
    names: tuple[str, ...] = ()
    why: str = ""


def _basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _watched_stem(token: str, previous: str) -> str | None:
    """The watched script this token names, as `scripts/register.py` or `-m scripts.register`."""
    name = _basename(token)
    if name.endswith(".py") and name[:-3] in WATCHED:
        return name[:-3]
    if previous == "-m" and name.rsplit(".", 1)[-1] in WATCHED:
        return name.rsplit(".", 1)[-1]
    return None


def _program(tokens: list[str]) -> tuple[str | None, int]:
    """(the program leading this fragment, the index of its token), past call operators and assignments."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token or token.lower() in PREFIXES or ENV_ASSIGNMENT.match(token) or token.startswith("env:"):
            i += 1
            continue
        if i + 1 < len(tokens) and tokens[i + 1] == "=":  # PowerShell: $out = python ...
            i += 2
            continue
        name = _basename(token)
        return (name[:-4] if name.endswith(".exe") else name), i
    return None, len(tokens)


def _run_writes(stem: str, args: list[str]) -> bool:
    """Whether running this watched script with these arguments writes a record."""
    if stem in ALWAYS_WRITES:
        return True
    if any(a.lower() in ("-h", "--help") for a in args):
        return False
    if stem == "register":
        if "--self-test" in args:
            return False  # its own temporary database
        words = [a.lower() for a in args if a and not a.startswith("-")]
        if not words:
            return False  # argparse refuses before anything opens
        if words[0] == "needs-input":
            return len(words) > 1 and words[1] not in NEEDS_INPUT_READS
        return words[0] not in REGISTER_READS
    flags = {a.split("=", 1)[0].lower() for a in args if a.startswith("--")}
    return bool(flags - (LINK_DOCS_READS if stem == "link_docs" else CALENDAR_READS))


def shell_writes(command: str) -> bool:
    """True when this Bash or PowerShell command runs something that writes a record."""
    runs_anything = False
    for fragment in SEPARATORS.split(command.translate(QUOTES)):
        tokens = [t.strip(WRAPPING) for t in fragment.split()]
        program, start = _program(tokens)
        if program is None or program in READERS:
            continue
        runs_anything = True
        for i in range(start, len(tokens)):
            stem = _watched_stem(tokens[i], tokens[i - 1] if i else "")
            if stem:
                if _run_writes(stem, tokens[i + 1:]):
                    return True
                break  # the first script a fragment names is the one it runs
    if not runs_anything:
        return False
    # Whole-command checks: inline code is split apart by its own semicolons above.
    if INLINE_IMPORT.search(command):
        return True
    return bool(REGISTER_DB.search(command) and SQL_WRITE.search(command))


def tool_use_writes(use: dict) -> bool | None:
    """True if this tool use wrote or changed something, False if it read, None if it cannot be read."""
    name = use.get("name")
    if not isinstance(name, str) or not name:
        return None
    if name in WRITE_TOOLS:
        return True
    if name in SHELL_TOOLS:
        tool_input = use.get("input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return shell_writes(command) if isinstance(command, str) else None
    if name in ("Agent", "Task"):
        # Reached only when the roster could not name the agent (Task is the tool's
        # older name), so whatever that agent did is not visible from here.
        return None
    return False


def _describe(use: dict) -> str:
    tool_input = use.get("input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return f"{use.get('name')}: {command[:80]}" if isinstance(command, str) else str(use.get("name"))


def classify(ctx: TurnContext) -> Verdict:
    """The verdict for one turn, from the TurnContext that also names its roster."""
    names = roster(ctx.dispatches)
    if names:
        return Verdict(DISPATCHED, tuple(names))
    unreadable = []
    for use in ctx.tool_uses:
        wrote = tool_use_writes(use)
        if wrote:
            return Verdict(WROTE, why=_describe(use))
        if wrote is None:
            unreadable.append(_describe(use))
    if ctx.unparsed_lines:
        unreadable.append(f"{ctx.unparsed_lines} line(s) that did not parse")
    if unreadable:
        return Verdict(UNVERIFIED, why="could not read: " + "; ".join(unreadable))
    return Verdict(READ_ONLY)


def verdict_for(transcript_path: str | Path | None) -> Verdict:
    """Classify the current turn of this transcript. An unreadable transcript is UNVERIFIED, never clean."""
    try:
        ctx = turn_context(transcript_path)
    except TranscriptUnreadable as exc:
        return Verdict(UNVERIFIED, why=str(exc))
    return classify(ctx)
