"""Shared dispatch detection for STEVIE's hooks.

Three hooks need the same fact -- "which agents were dispatched since Mike last
spoke?" -- and the parse that answers it already existed once, inline, in
skill_proposer.py. Copying it a third and fourth time would guarantee the four
copies drift, and a dispatch gate that disagrees with the roll call reporting on
it is worse than either alone.

The load-bearing decision here is the exception. A caller must be able to tell
"no agents were dispatched" from "I could not look" -- collapsing those two into
an empty list is the short-circuit-to-pass that _lib.sh was written to stamp
out, and it would turn the enforcement gate into a pass-through the moment a
transcript path went stale. So an unreadable or unparseable transcript raises
TranscriptUnreadable; only a genuinely readable transcript returns a list.

Transcript shape (verified against ~/.claude/projects/<slug>/*.jsonl, v2.1.228):
  - one JSON object per line; `type` is user | assistant | attachment | system
  - a real user turn is type=user, isSidechain absent/false, no isMeta, and
    carries at least one `text` content block. The same type=user row shape also
    carries tool_result blocks, which are not turn boundaries
  - subagent conversations live in their OWN file under <session>/subagents/ and
    every row there has isSidechain: true
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Blocks the harness injects INTO a type=user row that Mike did not type. A row
# containing only these is not a turn boundary -- and treating one as a boundary
# is not a cosmetic error: a backgrounded agent's own completion notification
# arrives this way, so the notification would erase the dispatch that produced
# it and the roll call would report SOLO on a properly dispatched turn.
SYNTHETIC_BLOCK = re.compile(
    r"<(system-reminder|task-notification|ide_selection|command-name"
    r"|command-message|command-args|local-command-stdout)>.*?</\1>",
    re.S | re.I,
)


class TranscriptUnreadable(Exception):
    """The transcript could not be located, read, or parsed at all.

    Distinct from "parsed fine, found nothing". Callers that gate on dispatch
    must treat this as "cannot verify", never as "verified clean".
    """


@dataclass
class TurnContext:
    """What happened since Mike's most recent message."""

    dispatches: list[str] = field(default_factory=list)
    last_user_text: str = ""
    is_sidechain: bool = False
    found_turn_boundary: bool = False


def _read_lines(transcript_path: str | Path | None) -> list[str]:
    """Return the transcript's non-empty lines, or raise TranscriptUnreadable."""
    if not transcript_path:
        raise TranscriptUnreadable("no transcript_path in the hook payload")

    path = Path(str(transcript_path))
    if not path.exists():
        raise TranscriptUnreadable(f"transcript does not exist: {path}")

    try:
        # Decode UTF-8 explicitly: the default text mode uses the locale
        # encoding, cp1252 on this machine, and transcripts routinely carry em
        # dashes and accented paths. Same defect documented in _lib.sh:36-39.
        raw = path.read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        raise TranscriptUnreadable(f"cannot read transcript: {exc}") from exc

    return [line for line in raw.splitlines() if line.strip()]


def _text_of(message: dict) -> str:
    """Join the plain-text blocks of a message, ignoring tool_result blocks."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p)


def _human_text(message: dict) -> str:
    """Only the part of a user row Mike actually typed.

    Harness-injected blocks are stripped first. What remains is the human turn;
    if nothing remains, the row is synthetic and is not a boundary at all.
    """
    return SYNTHETIC_BLOCK.sub(" ", _text_of(message)).strip()


def _is_real_user_turn(event: dict) -> bool:
    """True only for a message Mike actually typed.

    Excludes sidechain rows (a subagent's own prompt), meta rows, the type=user
    rows that exist solely to carry a tool_result back to the model, and rows
    whose entire text is harness-injected (see SYNTHETIC_BLOCK).
    """
    if event.get("type") != "user":
        return False
    if event.get("isSidechain") is True:
        return False
    if event.get("isMeta"):
        return False
    return bool(_human_text(event.get("message") or {}))


def _agent_calls(event: dict) -> list[str]:
    """subagent_type of every Agent tool call in one assistant event."""
    if event.get("type") != "assistant" or event.get("isSidechain") is True:
        return []
    found = []
    for block in event.get("message", {}).get("content", []) or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") == "Agent":
            found.append(block.get("input", {}).get("subagent_type", ""))
    return found


def turn_context(transcript_path: str | Path | None) -> TurnContext:
    """Summarise the current turn in a single backwards pass.

    Walks from the end of the file and stops at the first real user message, so
    a 20 MB transcript costs only the lines belonging to this turn. Hooks fire
    on every Write, so a full-file parse would be felt.
    """
    lines = _read_lines(transcript_path)
    ctx = TurnContext()
    if not lines:
        return ctx

    parsed_any = False
    dispatches_reversed: list[str] = []

    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # One truncated line (a transcript mid-flush) is normal and is not
            # the same fact as a file that holds no JSON at all; the
            # parsed_any check below covers the latter.
            continue
        if not isinstance(event, dict):
            continue
        parsed_any = True

        if event.get("isSidechain") is True:
            ctx.is_sidechain = True

        if _is_real_user_turn(event):
            ctx.last_user_text = _human_text(event.get("message") or {})
            ctx.found_turn_boundary = True
            break

        dispatches_reversed.extend(reversed(_agent_calls(event)))

    if not parsed_any:
        raise TranscriptUnreadable(
            f"no line of {transcript_path} parsed as JSON ({len(lines)} tried)"
        )

    ctx.dispatches = [s for s in reversed(dispatches_reversed) if s]
    return ctx


def roster(dispatches: list[str]) -> list[str]:
    """Uppercase agent names in dispatch order, consecutive repeats collapsed.

    Repeats matter: three parallel MACs is one research step, not three, and
    "MAC -> MAC -> MAC" reads like a stutter. Non-adjacent repeats are kept
    because coming back to an agent later is a real second pass.

    Lives here rather than in team-rollcall.py because the status line reports
    the same fact and must render the same names -- a bar that disagrees with
    the roll call is worse than either alone.
    """
    names = []
    for raw in dispatches:
        name = (raw or "").split(":")[-1].strip().upper()
        if name and (not names or names[-1] != name):
            names.append(name)
    return names


def dispatches_this_turn(transcript_path: str | Path | None) -> list[str]:
    """subagent_type of every Agent call since Mike's most recent message.

    Raises TranscriptUnreadable rather than returning [] when it could not look.
    """
    return turn_context(transcript_path).dispatches


def is_subagent_transcript(transcript_path: str | Path | None, ctx: TurnContext) -> bool:
    """True when this transcript belongs to a dispatched agent, not the main thread.

    Two independent signals because the storage layout has already moved once:
    the file sits under <session>/subagents/, and/or it contains sidechain rows
    with no real user turn anywhere in it. Either way a dispatch demonstrably
    already happened, so the gate has nothing left to enforce.
    """
    parts = {p.lower() for p in Path(str(transcript_path or "")).parts}
    if "subagents" in parts:
        return True
    return ctx.is_sidechain and not ctx.found_turn_boundary
