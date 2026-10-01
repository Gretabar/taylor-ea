"""Plumbing every gate in this repo needs, written once.

Ported from PIPER. Several gates read a PreToolUse payload, decide, and either exit
0 or exit 2 with a message. Written once per gate that is several chances to get the
fail-closed branch subtly different, and the failure mode of getting it wrong is a
gate that waves through a call it never looked at. _lib.sh describes the classic
case: a bare `jq -r` on a machine without jq yields an empty string, every
subsequent grep misses, and a blocking gate ALLOWS the thing it was written to
block.

So the rules live here:

  read_payload()      raises PayloadUnreadable. It never returns {} for an
                      unreadable payload, because "nothing in it" and "could not
                      read it" are different facts.

  deny_environment()  the one message shape for every cannot-verify branch. It
                      says this is an environment fault and that rephrasing will
                      not change the outcome.

  load_context()      a missing or malformed context/*.json is also a
                      cannot-verify state. A gate whose rules failed to load has
                      no rules, and a gate with no rules must not pass traffic.

  caller_agent()      WHO is making this call. Claude Code itself stamps
                      `agent_id` and `agent_type` on the payload when a hook fires
                      inside a subagent (hooks reference, "Common input fields").
                      That is the authoritative signal and it is read first. A
                      payload with no agent_id is the MAIN THREAD, i.e. the
                      orchestrator, never "whichever agent was dispatched last".

  resolve_agent()     best-effort attribution for audit rows only. Never use it to
                      grant anything: on the main thread its transcript fallback
                      names the last agent DISPATCHED, which is not the caller.

  agent_name()        the namespace rule: a bare roster name or this repo's `ea:`
                      prefix names one of ours; any other prefix names nobody here.

  block()             never fails to refuse: the message is encoded with
                      errors="replace", because a refusal that raises while
                      printing exits 1, and exit 1 lets the call through. Every gate
                      also ends in _failsafe.run_gate(), which turns any crash into
                      a refusal.

WHAT CHANGED FROM PIPER. Env vars are EA_*; the roster is read from
context/roster-agents.json so this file, the roll call and the contract validator
cannot disagree about who exists; caller_agent() is new, because transcript
inference attributes an orchestrator call to the last agent it dispatched, which
is exactly the hole a delivery-agent gate cannot have.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

_ENV_ROOT = os.environ.get("EA_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
REPO_ROOT = Path(_ENV_ROOT) if _ENV_ROOT else HERE.parents[1]


def _load_roster() -> tuple[tuple[str, ...], frozenset[str]]:
    """(agent names, the agents marked read_only) from context/roster-agents.json, or empty when unreadable.

    An empty roster is the fail-closed answer: every gate that asks "is this caller
    one of ours" then answers no. RecursionError is caught with the rest: json.loads
    raises it, not ValueError, on a file nested a few thousand levels deep.
    """
    try:
        data = json.loads((REPO_ROOT / "context" / "roster-agents.json")
                          .read_bytes().decode("utf-8", errors="replace"))
        agents = [a for a in data.get("agents") or [] if a.get("name")]
        return (tuple(str(a["name"]).upper() for a in agents),
                frozenset(str(a["name"]).upper() for a in agents if a.get("read_only") is True))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return (), frozenset()  # swallow: an unreadable roster resolves every caller to None, which every gate denies


ROSTER, ROSTER_READ_ONLY = _load_roster()


class PayloadUnreadable(Exception):
    """stdin held no JSON object this hook could inspect."""


class ContextUnreadable(Exception):
    """A context/*.json rule file could not be read or parsed."""


def read_payload() -> dict:
    """The PreToolUse payload as a dict, or raise.

    Bytes then explicit UTF-8: sys.stdin decodes with the locale codec, cp1252 on a
    Canadian corporate Windows build, and an accented name in a path would arrive as
    mojibake and be matched against wrong.
    """
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise PayloadUnreadable(f"cannot read stdin: {exc}") from exc
    if not raw.strip():
        raise PayloadUnreadable("stdin was empty")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise PayloadUnreadable(f"stdin was not JSON this hook can read ({exc.__class__.__name__}: {exc})") from exc
    if not isinstance(payload, dict):
        raise PayloadUnreadable(f"payload was {type(payload).__name__}, not an object")
    return payload


def block(lines: list[str]) -> int:
    """Write a deny message to stderr and return the blocking exit code.

    errors="replace": a refusal quotes the command it refuses, and a command can carry
    a lone UTF-16 surrogate (a JSON "\\ud83d" escape). Encoded strictly, that raised on
    the DENY path, the hook exited 1, and Claude Code ran the command it was refusing.
    """
    sys.stderr.buffer.write(("\n".join(lines) + "\n").encode("utf-8", errors="replace"))
    sys.stderr.flush()
    return 2


def deny_environment(hook: str, subject: str, reason: str) -> int:
    """The single cannot-verify refusal, identical across every gate."""
    return block([
        f"BLOCKED: {hook} could not read the {subject}, so it has not inspected",
        "this call. It is blocking rather than waving through something it never",
        "looked at. A safety check that cannot see its input has checked nothing.",
        "",
        f"  reason: {reason}",
        "",
        "This is an ENVIRONMENT fault, not a problem with the request. Do not",
        "retry it and do not rephrase it. Neither will change the outcome.",
        "Run `python scripts/ea_doctor.py` and send Mike the output.",
    ])


def load_context(name: str) -> dict:
    """Parse context/<name>.json, or raise ContextUnreadable."""
    path = REPO_ROOT / "context" / f"{name}.json"
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        raise ContextUnreadable(f"{path}: {exc}") from exc
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContextUnreadable(f"{path}: {exc.__class__.__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContextUnreadable(f"{path}: top level is not an object")
    return data


def tool_input(payload: dict) -> dict:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def first_field(payload: dict, *names: str) -> str:
    """First non-empty tool_input field among `names`, coerced to text."""
    data = tool_input(payload)
    for name in names:
        value = data.get(name)
        if value in (None, ""):
            continue
        return value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return ""


def norm_path(raw: str) -> str:
    """Absolute, normalised, case-folded. Windows paths arrive both ways."""
    if not raw:
        return ""
    return os.path.normcase(os.path.abspath(os.path.normpath(raw)))


def under(path: str, root: Path | str) -> bool:
    """True when `path` is `root` or lives inside it."""
    target, base = norm_path(path), norm_path(str(root))
    if not target or not base:
        return False
    return target == base or target.startswith(base + os.sep)


def repo_relative(path: str) -> str:
    """Repo-relative POSIX path, or "" when the target is outside the repo."""
    if not under(path, REPO_ROOT):
        return ""
    rel = os.path.relpath(os.path.abspath(path), str(REPO_ROOT))
    return rel.replace("\\", "/")


BUILD_MARKER = REPO_ROOT / "state" / "BUILD_MACHINE"


def is_build_machine() -> bool:
    """True only on the machine this repo is built on (Mike's), never on Taylor's.

    The marker is state/BUILD_MACHINE, created by hand outside Claude Code, holding
    the build machine's hostname on its first line. Both halves are required: the
    file must exist AND name THIS host. A marker that travelled on a USB copy of the
    whole folder therefore opens nothing on Taylor's laptop. state/ is gitignored and
    never in the kit, and protect-architecture.py refuses any tool call that writes
    the marker, so a session cannot mint one.
    """
    import socket  # noqa: PLC0415

    try:
        first = BUILD_MARKER.read_bytes().decode("utf-8", errors="replace").strip().splitlines()
    except OSError:
        return False
    if not first:
        return False
    return first[0].strip().lower() == socket.gethostname().strip().lower()


def invokes_script(command: str, stem: str) -> bool:
    """True when this shell command would run scripts/<stem>.py.

    Shared by the WREN-only and SAGE-only gates; the rule itself is
    _shell.runs_script(), the one parser every shell gate uses. It matches the script
    (privacy_review.py, `import privacy_review`, `-m privacy_review`), never a longer
    name that contains it (the privacy_reviews table), through every launcher _shell
    unwraps. Imported when first asked, so a broken parser refuses only the gates that
    need it, and a gate that never asks does not load it.
    """
    from _shell import runs_script  # noqa: PLC0415

    return runs_script(command, stem)


PLUGIN = "ea"


def agent_name(raw: str) -> str | None:
    """'wren' or 'ea:wren' -> 'WREN'. Any other prefix -> None: it names somebody else's agent.

    Keeping only the last ':' segment let `otherplugin:sage` stand for SAGE and an
    `x:wren` subagent pass the WREN-only gate. Only a bare name or this repo's own
    `ea:` prefix can name one of ours; scripts/team.py applies the same rule.
    """
    text = str(raw or "").strip()
    prefix, sep, name = text.partition(":")
    if sep:
        if prefix.strip().lower() != PLUGIN or ":" in name:
            return None
        text = name
    return text.strip().upper() or None


def caller_agent(payload: dict) -> str | None:
    """The roster agent making THIS call, from Claude Code's own payload fields.

    Returns the agent name, "MAIN" for the main thread (the orchestrator), or None
    when the payload says it came from a subagent but not which one. Callers that
    grant something must treat None as DENY and "MAIN" as "not a specialist".

    No environment pin is honoured here. An environment variable is something a
    process inherits rather than something a person decides, and this function is
    the entire width of the delivery-agent exemption.
    """
    agent_id = payload.get("agent_id")
    agent_type = payload.get("agent_type")
    if agent_id:
        name = agent_name(str(agent_type or ""))
        return name if name in ROSTER else None
    # No agent_id: the hook fired on the main thread. agent_type alone can be
    # present when the whole session runs as an agent (`--agent`); that is not a
    # dispatched specialist either.
    return "MAIN"


_SUBAGENT_TYPE = re.compile(r'"subagent_type"\s*:\s*"([^"]+)"')


def resolve_agent(payload: dict) -> str | None:
    """Best-effort attribution for audit rows. NEVER use this to grant anything.

    Signals, strongest first:
      1. The payload's own agent_type, when agent_id says this is a subagent call.
      2. EA_AGENT in the environment, so a test can pin attribution.
      3. The last Agent dispatch in this turn, via the shared transcript parser.
      4. The last subagent_type written anywhere in the transcript file.
    3 and 4 name the last agent DISPATCHED, which on the main thread is not the
    caller. That is acceptable for an audit label and fatal for a permission.
    """
    caller = caller_agent(payload)
    if caller not in (None, "MAIN"):
        return caller

    pinned = agent_name(os.environ.get("EA_AGENT") or "")
    if pinned in ROSTER:
        return pinned

    transcript_path = payload.get("transcript_path")
    try:
        from _transcript import TranscriptUnreadable, roster, turn_context

        names = roster(turn_context(transcript_path).dispatches)
        for name in reversed(names):
            if name in ROSTER:
                return name
    except (ImportError, TranscriptUnreadable):
        pass  # swallow: fall through to the raw scan, and to None if that fails too
    except Exception:
        pass  # swallow: attribution is best effort by contract; None is safe

    try:
        raw = Path(str(transcript_path)).read_bytes().decode("utf-8", errors="replace")
    except (OSError, TypeError, ValueError):
        return None
    for match in reversed(_SUBAGENT_TYPE.findall(raw)):
        name = agent_name(match)
        if name in ROSTER:
            return name
    return None
