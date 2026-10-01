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

A DISPATCH IS PROVED, NOT ASSUMED. The write passes when an agent of this turn
demonstrably ran: its Agent call came back with a result that is not a refusal
(_transcript.py, change 5). "No refusal found" is not proof. So the write is refused,
as UNVERIFIABLE rather than as solo, when the only dispatch has no result yet, when its
result is an error that is not a recognised refusal (a refusal wrapped in a
<tool_use_error> tag), when a line of the turn did not parse (it may have been the
turn's start, so an earlier turn's dispatch would read as this one's), or when the
turn's start was not found at all. The user's "solo ok" still opens it, read only from
a turn whose every line parsed: a truncated row must not let an earlier turn's
"solo ok" stand in for this one's.

Fails CLOSED on an unreadable transcript, same reasoning as _lib.sh's
hook_die_unparseable: a gate that cannot see its input has not checked anything. Any
crash of this hook is a refusal too (_failsafe.run_gate).
"""

from __future__ import annotations

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
        roster,
        turn_context,
    )
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

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


def deny_unverifiable(rel: str, why: str) -> int:
    return block([
        "BLOCKED: this turn does not prove an agent ran, so this is treated as a solo write.",
        "",
        f"  file:   {rel}",
        f"  reason: {why}",
        f"  owner:  {owner_for(rel)}",
        "",
        "A write here passes when an agent of this turn demonstrably ran: its Agent",
        "call came back with a result that is not a refusal. Dispatch the owner and",
        "let it write the file; an agent's own write always passes.",
        "",
        f'If this genuinely is a one-off that needs no agent, the user says "{OVERRIDE}"',
        "and the write goes through. Do not add that phrase yourself.",
    ])


def decide(ctx, transcript_path) -> tuple[bool, str, str]:
    """(allowed, rule_id, why). Pure, so the guardrail self-test can drive it."""
    if is_subagent_transcript(transcript_path, ctx):
        return True, "subagent-transcript", ""
    doubts = ctx.doubts()
    if ctx.dispatches and not doubts:
        return True, "dispatched", ""
    if not ctx.unparsed_lines and OVERRIDE in SYSTEM_REMINDER.sub(" ", ctx.last_user_text).lower():
        return True, "override", ""
    reasons = list(doubts)
    if ctx.pending:
        reasons.append("no result yet for " + ", ".join(roster(ctx.pending)))
    if ctx.unclear:
        reasons.append("an error that is not a recognised refusal for " + ", ".join(roster(ctx.unclear)))
    if ctx.dispatches and doubts:
        reasons.append("so the dispatch of " + ", ".join(roster(ctx.dispatches)) + " cannot be placed in this turn")
    if reasons:
        return False, "dispatch-unverifiable", "; ".join(reasons)
    return False, "solo-write", ""


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
    session = str(payload.get("session_id") or "")
    try:
        ctx = turn_context(transcript_path)
    except TranscriptUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", target=rel, detail=str(exc), session_id=session)
        return deny_environment(HOOK, "session transcript", str(exc))

    allowed, rule_id, why = decide(ctx, transcript_path)
    if allowed:
        if rule_id == "override":
            _audit.record(hook=HOOK, decision="allow", rule_id="override", target=rel, session_id=session)
        return 0
    _audit.record(hook=HOOK, tool=str(payload.get("tool_name") or ""), decision="deny", rule_id=rule_id,
                  target=rel, detail=why[:300], session_id=session)
    return deny_solo(rel) if rule_id == "solo-write" else deny_unverifiable(rel, why)


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
