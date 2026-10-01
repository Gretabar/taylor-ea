"""PreToolUse: a read-only agent (LARK) runs only what is on its list, and changes nothing.

NEW in this repo. Deviation D-3 switches LARK on ahead of Phase 7 on the grounds that
prep writes nothing. LARK holds Bash, so until this gate "writes nothing" rested on the
prose in .claude/agents/lark.md. This is the mechanism.

WHO IS CONFINED. An agent the roster marks `read_only: true`, or one hardcoded here,
LARK. The union, on purpose: the roster can widen confinement, never narrow it, so the
width of this gate is not a matter of file contents. A subagent the payload does not
identify is confined too, because it might be LARK. The main thread and every other
agent pass through untouched.

WHAT A CONFINED AGENT MAY DO:

  Read, Grep, Glob   if this hook is ever wired to them; LARK's file holds only these
                     and Bash, and validate_agent_contracts.py fails if it holds more.
  Bash, PowerShell   only when EVERY simple command in it, read the way that tool's
                     own shell reads it (_shell.py), is one of

                       python scripts/prep.py ...
                       python scripts/register.py <a read subcommand> ...
                           owed, history, morning, resolve-date, resolve-person,
                           topics, show, needs-input list

                     run by a plain interpreter (python, py, python3.14, a full path to
                     one, with harmless options such as -X utf8), the script named by
                     its path in this repo, and nothing writing a file by redirect.

  Everything else is refused: other scripts, other programs, an environment prefix or
  a wrapper (env, cmd /c, powershell -c), inline code (-c, -m), and any tool this
  list does not name.

WHAT THE LIST'S COMMANDS WRITE, stated: no record. prep.py opens the register
read-only. register.py's read subcommands only read, but register.py opens the register
the way every caller does, so on a register whose schema is behind it applies the
pending migration; and SQLite keeps its WAL index files (-wal, -shm) beside the
database while it is open. Neither is a record LARK made.

FAILS CLOSED: an unreadable payload, and any crash of this hook, refuse
(_failsafe.run_gate).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _failsafe import run_gate  # noqa: E402  -- standard library only, so it loads when the rest cannot

# A failed import must end in a refusal, never in Python's own exit 1, which lets the call through.
try:
    import _audit  # noqa: E402
    from _gate import (  # noqa: E402
        REPO_ROOT,
        ROSTER_READ_ONLY,
        PayloadUnreadable,
        agent_name,
        block,
        deny_environment,
        read_payload,
        tool_input,
    )
    from _shell import (  # noqa: E402
        DIALECTS,
        is_python,
        program_name,
        segments,
        words,
        writes_by_redirect,
    )
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

HOOK = "confine-read-only-agent"

# HARDCODED, like WREN and SAGE in their gates. context/roster-agents.json marks the
# same agent `read_only: true`, and the guardrail self-test asserts the two agree.
READ_ONLY_AGENTS = frozenset({"LARK"})

READ_TOOLS = frozenset({"Read", "Grep", "Glob"})
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
SHELL_DIALECTS = {"Bash": ("bash",), "PowerShell": ("powershell",)}  # _shell.BASH, _shell.POWERSHELL

PREP = "scripts/prep.py"
REGISTER = "scripts/register.py"
REGISTER_READS = frozenset({"owed", "history", "morning", "resolve-date", "resolve-person", "topics", "show"})
# Interpreter options that change nothing about what runs. -X takes a value.
SAFE_OPTIONS = frozenset({"-B", "-E", "-I", "-P", "-q", "-s", "-S", "-u", "-O", "-OO"})
PY_LAUNCHER_VERSION = re.compile(r"-[23](?:\.\d+)?(?:-(?:32|64))?")


def confined(payload: dict, roster_read_only: frozenset[str]) -> tuple[bool, str]:
    """(this caller is confined, who it is)."""
    if not payload.get("agent_id"):
        return False, "MAIN"
    raw = str(payload.get("agent_type") or "").strip()
    if not raw:
        return True, "a subagent the payload does not identify"
    name = agent_name(raw)
    if name is None:
        return False, raw  # another plugin's agent: not one of ours, and the dispatch gate refuses those
    return name in READ_ONLY_AGENTS or name in roster_read_only, name


def _repo_path(word: str, cwd: str) -> str:
    """`word` as a repo-relative POSIX path, or "" when it is not inside the repo."""
    target = os.path.normcase(os.path.abspath(os.path.join(cwd, word)))
    root = os.path.normcase(os.path.abspath(str(REPO_ROOT)))
    if not target.startswith(root + os.sep):
        return ""
    return os.path.relpath(target, root).replace("\\", "/").lower()


def check_simple(ws: list[str], cwd: str) -> str:
    """"" when one simple command is on the list, else why it is not."""
    k = 1 if ws[:1] == ["&"] else 0  # PowerShell's call operator before a quoted interpreter path
    if k >= len(ws):
        return "an empty command"
    if not is_python(program_name(ws[k])):
        return f"{ws[k]!r} is not on the list"
    k += 1
    while k < len(ws) and ws[k].startswith("-"):
        option = ws[k]
        if option in SAFE_OPTIONS or PY_LAUNCHER_VERSION.fullmatch(option):
            k += 1
        elif option == "-X" and k + 1 < len(ws):
            k += 2
        elif option.startswith("-X") and len(option) > 2:
            k += 1
        else:
            return f"the interpreter option {option!r} is not on the list"
    if k >= len(ws):
        return "python with no script reads its program from stdin"
    script, args = _repo_path(ws[k], cwd), ws[k + 1:]
    if script == PREP:
        return ""
    if script != REGISTER:
        return f"{ws[k]!r} is not on the list"
    if "--self-test" in args:
        return "register.py --self-test is not on the list"
    plain = [a for a in args if not a.startswith("-")]
    if not plain:
        return "register.py with no read subcommand"
    if plain[0] == "needs-input":
        return "" if plain[1:2] == ["list"] else "register.py needs-input is on the list only as `needs-input list`"
    if plain[0] in REGISTER_READS:
        return ""
    return f"register.py {plain[0]} writes, or is not on the list"


def decide(tool: str, given: dict, cwd: str) -> tuple[bool, str]:
    """(allowed, why not) for a confined caller. Pure, so the guardrail self-test can drive it."""
    if tool in READ_TOOLS:
        return True, ""
    if tool not in SHELL_TOOLS:
        return False, f"the {tool or 'unnamed'} tool is not on the list"
    command = given.get("command")
    if not isinstance(command, str) or not command.strip():
        return False, "no command to check"
    if writes_by_redirect(command):
        return False, "it writes a file by redirect"
    # An allowlist reads the command the way the tool's own shell does: what bash runs is
    # what the bash reading lists. (The deny-list gates take both readings instead.)
    for dialect in SHELL_DIALECTS.get(tool, DIALECTS):
        simple = segments(command, dialect)
        if not simple:
            return False, "no command to check"
        for segment in simple:
            why = check_simple(words(segment, dialect), cwd)
            if why:
                return False, why
    return True, ""


def deny(who: str, why: str, tool: str, given: dict) -> int:
    shown = str(given.get("command") or tool)[:160]
    return block([
        f"BLOCKED: {who} is read only, and this is not on its list ({why}).",
        "",
        f"  call: {shown}",
        "",
        "A read-only agent runs python scripts/prep.py and the register's read",
        "subcommands (owed, history, morning, resolve-date, resolve-person, topics, show,",
        "needs-input list), as plain commands, and nothing else. It changes nothing, which",
        "is the condition deviation D-3 switched it on under.",
        "",
        "If the work needs a write, hand it back to the orchestrator, which dispatches the",
        "agent whose lane it is. Rephrasing the command will not change this outcome.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    is_confined, who = confined(payload, ROSTER_READ_ONLY)
    if not is_confined:
        return 0
    tool = str(payload.get("tool_name") or "")
    given = tool_input(payload)
    cwd = str(payload.get("cwd") or REPO_ROOT)
    allowed, why = decide(tool, given, cwd)
    target = str(given.get("command") or given.get("file_path") or tool)[:200]
    session = str(payload.get("session_id") or "")
    if allowed:
        _audit.record(hook=HOOK, tool=tool, agent=who, decision="allow", rule_id="read-only:listed",
                      target=target, session_id=session)
        return 0
    _audit.record(hook=HOOK, tool=tool, agent=who, decision="deny", rule_id="read-only:not-listed",
                  target=target, detail=why[:300], session_id=session)
    return deny(who, why, tool, given)


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
