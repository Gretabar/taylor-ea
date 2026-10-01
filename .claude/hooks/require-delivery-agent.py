"""PreToolUse (Bash|PowerShell): scripts/docs_edit.py runs only inside WREN.

NEW in this repo. docs_edit.py is the one script that changes a running 1:1 Doc
that Taylor and his managers read. Every other agent's terminal output is a
proposal; WREN carries a proposal into the Doc, reads it back, and refuses honestly
when the read-back does not match. If REED, PAGE or the orchestrator could run the
writer too, the read-back discipline would live in four places and drift in three.

WHO IS CALLING comes from Claude Code itself, not from inference. When a hook fires
inside a subagent the payload carries `agent_id` and `agent_type` (hooks reference,
"Common input fields"). So:

    agent_id present, agent_type == wren     ALLOW
    agent_id present, any other agent_type   DENY  (name the agent, point at WREN)
    agent_id present, agent_type unreadable  DENY  (None is a refusal, never a pass)
    no agent_id                              DENY  (the main thread is the
                                                    orchestrator, whoever it last
                                                    dispatched)

PIPER's transcript-based resolver is deliberately NOT used to grant this. On the
main thread it names the last agent DISPATCHED, so an orchestrator that dispatched
WREN and then ran docs_edit.py itself would be waved through as WREN. That is the
exact call this gate exists to refuse.

WHAT COUNTS AS RUNNING THE WRITER. A command that mentions docs_edit AND starts a
Python interpreter anywhere in it (`python scripts/docs_edit.py`, `py -3 ...`,
`powershell -Command "python ..."`, `python -c "import docs_edit"`, or piping the
source into `python -`), or that executes docs_edit.py directly. Reading the file
(cat, grep, git diff, Get-Content) does not start an interpreter and passes.
Crude on purpose: a precise parser of two shells' grammar would be a larger
attack surface than the gate. The cost of the crudeness is a rare false positive
(`grep py scripts/docs_edit.py`), which is a sentence of clarification. The rule
itself is _gate.invokes_script(), shared with require-privacy-agent.py.

ALSO MATCHED ON PowerShell. Claude Code on Windows enables a native PowerShell tool
by default for claude.ai accounts and treats it as the primary shell; a gate that
matched Bash alone would be a gate with a side door.

Fails CLOSED on an unreadable payload.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _audit  # noqa: E402
from _gate import (  # noqa: E402
    PayloadUnreadable,
    block,
    caller_agent,
    deny_environment,
    first_field,
    invokes_script,
    read_payload,
)

HOOK = "require-delivery-agent"

# HARDCODED. context/roster-agents.json marks the same agent `delivery: true`, and
# the guardrail self-test asserts the two agree. Reading the name from a file at
# runtime would make the width of this exemption a matter of file contents.
DELIVERY_AGENT = "WREN"


def invokes_writer(command: str) -> bool:
    """True when this shell command would run scripts/docs_edit.py."""
    return invokes_script(command, "docs_edit")


def decide(command: str, caller: str | None) -> tuple[bool, str]:
    """(allowed, rule_id). Pure, so the guardrail self-test can drive it."""
    if not invokes_writer(command):
        return True, "not-the-writer"
    if caller == DELIVERY_AGENT:
        return True, f"delivery-agent:{DELIVERY_AGENT}"
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
        "BLOCKED: only WREN writes to a running Doc.",
        "",
        f"  caller:  {who}",
        f"  command: {command[:160]}",
        "",
        "scripts/docs_edit.py changes a Doc that Taylor and his managers read. WREN",
        "is the one agent that runs it, because WREN reads every write back and",
        "refuses to call an unverified write done. Every other agent hands WREN a",
        "proposal (scripts/docs_propose.py writes it) and WREN carries it.",
        "",
        "Dispatch WREN with the proposal path. Rephrasing the command, or running the",
        "same script another way, will not change this outcome.",
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
    if rule_id == "not-the-writer":
        return 0

    session = str(payload.get("session_id") or "")
    tool = str(payload.get("tool_name") or "")
    if allowed:
        _audit.record(hook=HOOK, tool=tool, agent=DELIVERY_AGENT, decision="allow",
                      rule_id=rule_id, target=command[:200], session_id=session)
        return 0

    _audit.record(hook=HOOK, tool=tool, agent=str(caller or ""), decision="deny",
                  rule_id=rule_id, target=command[:200], session_id=session)
    return deny(rule_id, caller, command)


if __name__ == "__main__":
    sys.exit(main())
