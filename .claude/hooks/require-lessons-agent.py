"""PreToolUse (Bash|PowerShell): scripts/lessons.py records, answers and forgets only inside REED.

NEW in this repo, the sibling of require-privacy-agent.py. lessons.py is how the system
learns from Taylor (blueprint s.1, "Learning and corrections"), and what it records is loaded
into every later session. If any agent, or the orchestrator, could write a lesson, a one-off
remark could become standing behaviour without the screen that holds back prices, packages,
policies and sending permissions until Taylor says yes, and the roll call would show nobody
doing it. REED records lessons; everyone may read them.

WHO IS CALLING comes from Claude Code itself (agent_id and agent_type on the payload, read by
_gate.caller_agent), exactly as for WREN and SAGE:

    agent_id present, agent_type == reed     ALLOW
    agent_id present, any other agent_type   DENY
    agent_id present, agent_type unreadable  DENY  (None is a refusal, never a pass)
    no agent_id                              DENY  (the main thread is the orchestrator)

WHAT IS A WRITE. Everything except `list` and `context`, the two reads ("show me what you've
learned" is the orchestrator's to answer). The subcommand is read with _shell.script_args();
a form that hides it (inline code, a runner module, a variable as the program) is treated as
a write. Reading the script's source passes. Matched on PowerShell as well as Bash.

FAILS CLOSED, all the way: an unreadable payload is a refusal, and so is any crash of this
hook, including an import that fails (_failsafe.run_gate).
"""

from __future__ import annotations

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
        PayloadUnreadable,
        block,
        caller_agent,
        deny_environment,
        first_field,
        read_payload,
    )
    from _shell import script_args  # noqa: E402
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

HOOK = "require-lessons-agent"

# HARDCODED. context/roster-agents.json marks the same agent `lessons: true`, and the guardrail
# self-test asserts the two agree. Reading the name from a file at runtime would make the
# width of this exemption a matter of file contents.
LESSONS_AGENT = "REED"
READS = frozenset({"list", "context"})


def writes_lessons(command: str) -> bool | None:
    """True when the command writes through lessons.py, False when it only reads, None when it does not run it."""
    runs = script_args(command, "lessons")
    if not runs:
        return None
    for args in runs:
        if args is None:
            return True
        words = [a for a in args if not a.startswith("-")]
        if not words or words[0].lower() not in READS:
            return True
    return False


def decide(command: str, caller: str | None) -> tuple[bool, str]:
    """(allowed, rule_id). Pure, so the guardrail self-test can drive it."""
    writes = writes_lessons(command)
    if writes is None:
        return True, "not-the-lessons-store"
    if not writes:
        return True, "lessons-read"
    if caller == LESSONS_AGENT:
        return True, f"lessons-agent:{LESSONS_AGENT}"
    if caller == "MAIN":
        return False, "orchestrator"
    if caller is None:
        return False, "caller-unknown"
    return False, f"wrong-agent:{caller}"


def deny(rule_id: str, caller: str | None, command: str) -> int:
    who = {
        "orchestrator": "the orchestrator (main thread)",
        "caller-unknown": "a subagent this hook could not identify",
    }.get(rule_id, caller or "unknown")
    return block([
        "BLOCKED: only REED records, answers or forgets a lesson.",
        "",
        f"  caller:  {who}",
        f"  command: {command[:160]}",
        "",
        "scripts/lessons.py decides what every later session is told about Taylor's",
        "preferences, and holds back anything that would be a rule until he says yes.",
        "Dispatch REED with Taylor's words. `lessons.py list` and `lessons.py context`",
        "are reads anyone may run. Rephrasing the command will not change this outcome.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    command = first_field(payload, "command")
    caller = caller_agent(payload)
    allowed, rule_id = decide(command, caller)
    if rule_id in ("not-the-lessons-store", "lessons-read"):
        return 0

    session = str(payload.get("session_id") or "")
    tool = str(payload.get("tool_name") or "")
    if allowed:
        _audit.record(hook=HOOK, tool=tool, agent=LESSONS_AGENT, decision="allow",
                      rule_id=rule_id, target=command[:200], session_id=session)
        return 0
    _audit.record(hook=HOOK, tool=tool, agent=str(caller or ""), decision="deny",
                  rule_id=rule_id, target=command[:200], session_id=session)
    return deny(rule_id, caller, command)


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
