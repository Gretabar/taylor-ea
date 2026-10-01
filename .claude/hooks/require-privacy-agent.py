"""PreToolUse (Bash|PowerShell): scripts/privacy_review.py runs only inside SAGE.

NEW in this repo, the sibling of require-delivery-agent.py. privacy_review.py writes
the stamp that lets a flagged proposal (personal context headed for a manager's Doc,
blueprint s.2) through to WREN, or holds it back. If REED, PAGE, WREN or the
orchestrator could run it, the privacy review would be a step anyone can skip by
approving their own proposal.

WHO IS CALLING comes from Claude Code itself (agent_id and agent_type on the
payload, read by _gate.caller_agent), exactly as for WREN:

    agent_id present, agent_type == sage     ALLOW
    agent_id present, any other agent_type   DENY  (name the agent, point at SAGE)
    agent_id present, agent_type unreadable  DENY  (None is a refusal, never a pass)
    no agent_id                              DENY  (the main thread is the orchestrator)

WHAT COUNTS AS RUNNING IT is _gate.invokes_script(), shared with the WREN-only gate:
the script named with an interpreter anywhere in the command, executed directly, or
imported inline. Reading it (cat, grep, Get-Content) passes. Matched on PowerShell
as well as Bash, because on Windows PowerShell is the primary shell.

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

HOOK = "require-privacy-agent"

# HARDCODED. context/roster-agents.json marks the same agent `privacy: true`, and the
# guardrail self-test asserts the two agree. Reading the name from a file at runtime
# would make the width of this exemption a matter of file contents.
PRIVACY_AGENT = "SAGE"


def decide(command: str, caller: str | None) -> tuple[bool, str]:
    """(allowed, rule_id). Pure, so the guardrail self-test can drive it."""
    if not invokes_script(command, "privacy_review"):
        return True, "not-the-reviewer"
    if caller == PRIVACY_AGENT:
        return True, f"privacy-agent:{PRIVACY_AGENT}"
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
        "BLOCKED: only SAGE records a privacy review.",
        "",
        f"  caller:  {who}",
        f"  command: {command[:160]}",
        "",
        "scripts/privacy_review.py decides whether personal context may go into a Doc",
        "a manager reads (blueprint section 2). An agent that could stamp its own",
        "proposal would make the review a step anyone can skip.",
        "",
        "Dispatch SAGE with the proposal path. Rephrasing the command, or running the",
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
    if rule_id == "not-the-reviewer":
        return 0

    session = str(payload.get("session_id") or "")
    tool = str(payload.get("tool_name") or "")
    if allowed:
        _audit.record(hook=HOOK, tool=tool, agent=PRIVACY_AGENT, decision="allow",
                      rule_id=rule_id, target=command[:200], session_id=session)
        return 0

    _audit.record(hook=HOOK, tool=tool, agent=str(caller or ""), decision="deny",
                  rule_id=rule_id, target=command[:200], session_id=session)
    return deny(rule_id, caller, command)


if __name__ == "__main__":
    sys.exit(main())
