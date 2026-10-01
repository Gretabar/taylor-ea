"""PreToolUse (Write|Edit): no solo writes into the record directories.

Ported from PIPER. "Dispatch the work, do not do it yourself", written only as prose
in a file that loads when somebody types a slash command, is a rule that gets broken
however often it is repeated. This is the mechanism.

WHAT IS GATED HERE. output/, plus the three state/ directories that hold records:
state/proposals/ (Doc edit proposals, PAGE's), state/records/ (parsed Doc snapshots
and other named-manager records) and state/private/ (Taylor's private material).
The orchestrator writing one of those by hand is the documented failure pattern
with worse content. Repo code, scripts, hooks, context and logs stay writable so
maintenance still flows, and a dispatched agent's own write passes for free because
the dispatch it would be proving already happened.

Fails CLOSED on an unreadable transcript, same reasoning as _lib.sh's
hook_die_unparseable: a gate that cannot see its input has not checked anything.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _audit  # noqa: E402
from _gate import (  # noqa: E402
    PayloadUnreadable,
    block,
    deny_environment,
    first_field,
    read_payload,
    repo_relative,
)
from _transcript import (  # noqa: E402
    TranscriptUnreadable,
    is_subagent_transcript,
    turn_context,
)

HOOK = "require-dispatch"
OVERRIDE = "solo ok"

# Injected context rides inside the user message as a system-reminder block and must
# be stripped before the override is looked for. CLAUDE.md documents the phrase, so
# leaving it in would hold this gate permanently open on any turn that carries it.
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S | re.I)

OWNERS = {
    "state/proposals": "PAGE (Running Docs), which writes Doc edit proposals through scripts/docs_propose.py",
    "state/records": "PAGE for Doc snapshots, REED for register records",
    "state/private": "REED, and only when Taylor asked for something to be kept private",
    "output/drafts": "no Phase 1 agent writes drafts; Phase 3 and later",
}
DEFAULT_OWNER = "the specialist who owns that record"

GATED_ROOTS = ("output/", "state/proposals/", "state/records/", "state/private/")


def gated(rel: str) -> str | None:
    """The gated root this write falls under, or None."""
    for root in GATED_ROOTS:
        if rel.startswith(root):
            return root.rstrip("/")
    return None


def owner_for(rel: str) -> str:
    for prefix, owner in OWNERS.items():
        if rel.startswith(prefix + "/") or rel == prefix:
            return owner
    return DEFAULT_OWNER


def deny_solo(rel: str) -> int:
    return block([
        "BLOCKED: solo write.",
        "",
        f"  file:  {rel}",
        "  turn:  zero agents dispatched",
        f"  owner: {owner_for(rel)}",
        "",
        "Records are produced by the specialist who owns them, not by the",
        "orchestrator. Dispatch that agent with the Agent tool and let it write the",
        "file.",
        "",
        f'If this genuinely is a one-off that needs no agent, the user says "{OVERRIDE}"',
        "and the write goes through. Do not add that phrase yourself.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    file_path = first_field(payload, "file_path")
    rel = repo_relative(file_path)
    if not rel or gated(rel) is None:
        return 0

    # Claude Code's own subagent marker is the cheapest proof a dispatch happened.
    if payload.get("agent_id"):
        return 0

    transcript_path = payload.get("transcript_path")
    try:
        ctx = turn_context(transcript_path)
    except TranscriptUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", target=rel, detail=str(exc))
        return deny_environment(HOOK, "session transcript", str(exc))

    if is_subagent_transcript(transcript_path, ctx):
        return 0
    if ctx.dispatches:
        return 0

    typed = SYSTEM_REMINDER.sub(" ", ctx.last_user_text).lower()
    if OVERRIDE in typed:
        _audit.record(hook=HOOK, decision="allow", rule_id="override", target=rel,
                      session_id=str(payload.get("session_id") or ""))
        return 0

    _audit.record(hook=HOOK, tool=str(payload.get("tool_name") or ""), decision="deny",
                  rule_id="solo-write", target=rel,
                  session_id=str(payload.get("session_id") or ""))
    return deny_solo(rel)


if __name__ == "__main__":
    sys.exit(main())
