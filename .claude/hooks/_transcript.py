"""Shared dispatch detection for this repo's hooks.

PORTED FROM PIPER. Five changes made here, recorded in VENDORED-FROM.md:

  1. A SLASH COMMAND IS A TURN BOUNDARY. Claude Code records `/add Kaed ...` as a user
     row holding only <command-message>, <command-name> and <command-args> blocks,
     followed by an isMeta row with the expanded prompt (checked against real
     transcripts, 2026-10-01). Stripping those blocks leaves the row empty, so without
     this rule it is not a boundary, and for a user who works entirely in slash
     commands the "turn" runs back to his last plain-text message: the roll call after
     /morning would report the previous /add's dispatches, and require-dispatch would
     let a solo write through because an EARLIER command had dispatched. A row with a
     <command-name> block is a boundary, and the command and its arguments count as
     typed text. Skill invocations never produce such a row (they arrive as a
     tool_result), and harness-injected rows (system-reminder, task-notification,
     local-command-stdout) are still never boundaries.

  2. THE TURN'S TOOL USES ARE COLLECTED IN THE SAME PASS. TurnContext also carries
     every main-thread tool_use of the turn (name and input) and how many lines in
     the turn failed to parse. The roll call decides "did this turn write?" from the
     same walk that finds its dispatches, so the two can never disagree about where
     the turn began.

  3. A COMPACTION SUMMARY IS NOT A TURN BOUNDARY. Compaction appends a compact_boundary
     system row and a type=user summary row (isCompactSummary) to the same file. When
     it fires mid-turn, ending the walk there would hide the turn's earlier dispatches
     (a false SOLO) and its earlier writes (a false "nothing written").

  4. A REFUSED CALL IS NOT A DISPATCH. require-active-agent.py refuses a switched-off
     agent before it starts, but the Agent tool_use is still in the transcript.
     Counted, the roll call would print "TEAM | MILO (1 dispatched)" for an agent that
     never ran, and require-dispatch.py would let a later solo write through because
     "a dispatch happened". So the walk reads the refusals too: a tool_result row
     with is_error and either Claude Code's own toolDenialKind field or a
     "PreToolUse:" hook message (both observed on a live VS Code session, v2.1.222,
     2026-10-01). A refused dispatch goes to TurnContext.refused, and each tool use
     carries `refused`.

  5. A DISPATCH COUNTS ONLY ON POSITIVE EVIDENCE THAT THE AGENT RAN: its Agent
     tool_use has a result in this turn, and the result is not a refusal. "No refusal
     found" is not evidence, because a refusal can fail to be found: its row truncated
     mid-flush, its text wrapped in a <tool_use_error> tag, or not written yet. So a
     call with no result yet goes to TurnContext.pending, and a call whose result is an
     error that is not a recognised refusal goes to TurnContext.unclear. Neither is a
     dispatch. Every Agent error Claude Code wrote in this machine's transcripts
     carried toolDenialKind (checked 2026-10-01); an agent that ran and failed comes
     back as an ordinary result describing the failure, which is positive evidence.
     doubts() names what makes the rest of the turn untrustworthy: a line that did not
     parse (it may have been the turn's start, or a refusal) and a turn whose start was
     never found. Callers decide what a doubt costs; none of them reads it as clean.

Several hooks need the same fact -- "which agents were dispatched since the user
last spoke?" -- and a copy of the parse in each would guarantee the copies drift,
and a dispatch gate that disagrees with the roll call reporting on it is worse than
either alone.

The load-bearing decision here is the exception. A caller must be able to tell
"no agents were dispatched" from "I could not look" -- collapsing those two into
an empty list is the short-circuit-to-pass that _lib.sh was written to stamp
out, and it would turn the enforcement gate into a pass-through the moment a
transcript path went stale. So an unreadable or unparseable transcript raises
TranscriptUnreadable; only a genuinely readable transcript returns a list.

Transcript shape (verified against ~/.claude/projects/<slug>/*.jsonl, v2.1.228):
  - one JSON object per line; `type` is user | assistant | attachment | system
  - a real user turn is type=user, isSidechain absent/false, no isMeta, and
    carries at least one `text` content block, or is a slash command row. The same
    type=user row shape also carries tool_result blocks, which are not turn boundaries
  - subagent conversations live in their OWN file under <session>/subagents/ and
    every row there has isSidechain: true
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Blocks the harness injects INTO a type=user row that the user did not type. A row
# containing only these is not a turn boundary -- and treating one as a boundary
# is not a cosmetic error: a backgrounded agent's own completion notification
# arrives this way, so the notification would erase the dispatch that produced
# it and the roll call would report SOLO on a properly dispatched turn.
HARNESS_BLOCK = re.compile(
    r"<(system-reminder|task-notification|ide_selection|local-command-stdout)>.*?</\1>",
    re.S | re.I,
)

# A slash command the user typed. The name and the arguments are what he typed;
# <command-message> is the harness's own "x is running" text and is not.
COMMAND_BLOCK = re.compile(r"<(command-name|command-message|command-args)>(.*?)</\1>", re.S | re.I)


class TranscriptUnreadable(Exception):
    """The transcript could not be located, read, or parsed at all.

    Distinct from "parsed fine, found nothing". Callers that gate on dispatch
    must treat this as "cannot verify", never as "verified clean".
    """


# What became of one Agent call, from its tool_result in the same turn.
RAN = "ran"            # a result that is not a refusal: the agent started
DENIED = "denied"      # refused before it started: a hook, a permission rule, or the user
UNCLEAR = "unclear"    # an error result that is not a recognised refusal: cannot tell
PENDING = "pending"    # no result in this turn yet: still running, or not written


@dataclass
class TurnContext:
    """What happened since the user's most recent message.

    `dispatches` holds only agents with positive evidence that they ran. `refused`,
    `pending` and `unclear` hold the other Agent calls; none of them is a dispatch.
    """

    dispatches: list[str] = field(default_factory=list)
    last_user_text: str = ""
    is_sidechain: bool = False
    found_turn_boundary: bool = False
    tool_uses: list[dict] = field(default_factory=list)
    unparsed_lines: int = 0
    refused: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    unclear: list[str] = field(default_factory=list)

    def doubts(self) -> list[str]:
        """Why this turn's record cannot be taken at its word. Empty when it can."""
        reasons = []
        if self.unparsed_lines:
            reasons.append(f"{self.unparsed_lines} line(s) of this turn did not parse")
        if not self.found_turn_boundary:
            reasons.append("the start of this turn was not found")
        return reasons


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
    """Join the plain-text blocks of a message, ignoring tool_result blocks. Never raises on odd shapes."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in parts if isinstance(p, str) and p)


def _typed(message: dict) -> tuple[bool, str]:
    """(is this a turn the user started, what he typed including a command and its arguments)."""
    text = HARNESS_BLOCK.sub(" ", _text_of(message))
    commands = COMMAND_BLOCK.findall(text)
    plain = COMMAND_BLOCK.sub(" ", text).strip()
    is_command = any(tag.lower() == "command-name" for tag, _ in commands)
    typed_parts = [value for tag, value in commands if tag.lower() in ("command-name", "command-args")]
    typed = " ".join(" ".join([plain, *typed_parts]).split())
    return bool(plain) or is_command, typed


def _human_text(message: dict) -> str:
    """Only the part of a user row the user actually typed, command arguments included."""
    return _typed(message)[1]


def _is_real_user_turn(event: dict) -> bool:
    """True only for a message the user actually typed, a slash command included.

    Excludes sidechain rows (a subagent's own prompt), meta rows (a command's
    expanded prompt among them), the type=user rows that exist solely to carry a
    tool_result back to the model, rows whose entire text is harness-injected, and
    the summary a compaction writes (isCompactSummary): an auto-compaction can land
    mid-turn, and treating its summary as a turn start would hide everything the
    turn did before it.
    """
    if event.get("type") != "user":
        return False
    if event.get("isSidechain") is True:
        return False
    if event.get("isMeta") or event.get("isCompactSummary"):
        return False
    message = event.get("message")
    return isinstance(message, dict) and _typed(message)[0]


def _tool_uses(event: dict) -> list[dict]:
    """{"name", "input", "id"} of every tool_use block in one main-thread assistant event."""
    if event.get("type") != "assistant" or event.get("isSidechain") is True:
        return []
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [{"name": block.get("name"), "input": block.get("input"), "id": block.get("id")}
            for block in (content if isinstance(content, list) else [])
            if isinstance(block, dict) and block.get("type") == "tool_use"]


def _agent_calls(event: dict) -> list[tuple[str, str]]:
    """(subagent_type, tool_use id) of every Agent call in one assistant event. Task is its older name."""
    if event.get("type") != "assistant" or event.get("isSidechain") is True:
        return []
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    found = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") in ("Agent", "Task"):
            given = block.get("input")
            kind = given.get("subagent_type") if isinstance(given, dict) else None
            found.append((kind if isinstance(kind, str) else ("" if kind is None else str(kind)),
                          str(block.get("id") or "")))
    return found


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text") for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def _result_kind(event: dict, block: dict) -> str:
    """RAN, DENIED or UNCLEAR for one tool_result block.

    A refusal is an error result carrying Claude Code's own toolDenialKind, or a hook's
    message starting "PreToolUse:". An error that is neither might be a refusal in
    another wrapper or a call that failed after starting, so it is UNCLEAR. A result
    that is not an error is RAN, unless it reads like a refusal anyway.
    """
    text = _result_text(block).lstrip()
    if block.get("is_error") is True:
        return DENIED if event.get("toolDenialKind") or text.startswith("PreToolUse:") else UNCLEAR
    if event.get("toolDenialKind") or text.startswith(("PreToolUse:", "<tool_use_error>")):
        return UNCLEAR
    return RAN


def _results(event: dict) -> dict[str, str]:
    """tool_use id -> RAN, DENIED or UNCLEAR for every tool_result in one main-thread user row."""
    if event.get("type") != "user" or event.get("isSidechain") is True:
        return {}
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return {}
    found = {}
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id"):
            found[str(block["tool_use_id"])] = _result_kind(event, block)
    return found


def _call_state(results: dict[str, str], use_id: str) -> str:
    """What became of one call: its result's kind, or PENDING when this turn holds no result for it."""
    return results.get(use_id, PENDING) if use_id else PENDING


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
    by_state: dict[str, list[str]] = {RAN: [], DENIED: [], UNCLEAR: [], PENDING: []}  # each reversed
    tool_uses_reversed: list[dict] = []
    # Walking backwards, a call's result row is met before the call itself.
    results: dict[str, str] = {}

    for line in reversed(lines):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            # One truncated line (a transcript mid-flush) is normal and is not
            # the same fact as a file that holds no JSON at all; the
            # parsed_any check below covers the latter. It IS counted, because a
            # line nobody could read may have been a tool call, a refusal or the
            # start of this turn. RecursionError: a line nested thousands deep.
            ctx.unparsed_lines += 1
            continue
        if not isinstance(event, dict):
            ctx.unparsed_lines += 1
            continue
        parsed_any = True

        if event.get("isSidechain") is True:
            ctx.is_sidechain = True

        if _is_real_user_turn(event):
            ctx.last_user_text = _human_text(event.get("message") or {})
            ctx.found_turn_boundary = True
            break

        for use_id, kind in _results(event).items():
            # Two results for one call that disagree prove nothing either way.
            results[use_id] = kind if results.get(use_id, kind) == kind else UNCLEAR
        for subagent_type, use_id in reversed(_agent_calls(event)):
            by_state[_call_state(results, use_id)].append(subagent_type or "general-purpose")
        for use in reversed(_tool_uses(event)):
            state = _call_state(results, str(use.get("id") or ""))
            use["result"] = state
            use["refused"] = state == DENIED
            tool_uses_reversed.append(use)

    if not parsed_any:
        raise TranscriptUnreadable(
            f"no line of {transcript_path} parsed as JSON ({len(lines)} tried)"
        )

    ctx.dispatches = list(reversed(by_state[RAN]))
    ctx.refused = list(reversed(by_state[DENIED]))
    ctx.unclear = list(reversed(by_state[UNCLEAR]))
    ctx.pending = list(reversed(by_state[PENDING]))
    ctx.tool_uses = list(reversed(tool_uses_reversed))
    return ctx


def roster(dispatches: list[str]) -> list[str]:
    """Uppercase agent names in dispatch order, consecutive repeats collapsed.

    Repeats matter: three parallel PAGEs (one proposal per person) is one step, not three,
    and "PAGE -> PAGE -> PAGE" reads like a stutter. Non-adjacent repeats are kept
    because coming back to an agent later is a real second pass.

    Lives here rather than in team-rollcall.py because the status line reports
    the same fact and must render the same names -- a bar that disagrees with
    the roll call is worse than either alone.

    Only this repo's own `ea:` prefix is dropped. Another plugin's `x:sage` is shown
    as X:SAGE, never as SAGE: it is not the SAGE on this team.
    """
    names = []
    for raw in dispatches:
        name = display_name(raw)
        if name and (not names or names[-1] != name):
            names.append(name)
    return names


def display_name(raw: str) -> str:
    """'reed' and 'ea:reed' -> 'REED'; 'otherplugin:sage' -> 'OTHERPLUGIN:SAGE'."""
    text = str(raw or "").strip()
    prefix, sep, name = text.partition(":")
    if sep and prefix.strip().lower() == "ea" and ":" not in name:
        text = name
    return text.strip().upper()


def dispatches_this_turn(transcript_path: str | Path | None) -> list[str]:
    """subagent_type of every Agent call since the user's most recent message that demonstrably ran.

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
