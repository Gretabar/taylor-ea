"""PreToolUse (Agent|Task|Workflow|Bash|PowerShell): only a switched-on agent is ever dispatched.

NEW in this repo. Taylor has thirteen specialists and his own phase gate (blueprint
s.11): an agent runs only when Taylor approved its phase AND Mike built and accepted
it. scripts/team.py decides which; this hook refuses everything else before the
subagent starts, so asking for a switched-off agent costs no model time at all.

A REFUSAL PRINTS EXACTLY TWO LINES, the ones docs/FOR-TAYLOR.md quotes:

    NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.
    To switch it on: say "architecture change ok: switch on Phase 2", and Mike builds it.

and the APPROVED, NOT BUILT YET, PENN and TALLY variants from team.py. Nothing is
added around them, because the orchestrator relays them to Taylor as they are.

WHAT COUNTS AS A DISPATCH, each refused the same way:

  Agent, and Task      the tool that starts a subagent (Task is its older name);
                       the target is tool_input.subagent_type, plugin prefix ignored.
  Workflow             a workflow script starts agents (agent(..., {agentType})) that
                       the roll call and the status line never see, and a named or
                       resumed workflow does not show this hook which agents it will
                       start. No phase of Taylor's blueprint uses one, so every
                       Workflow call is refused rather than half-inspected.
  Bash, PowerShell     the claude CLI started from a shell with --agent, --agents, -p
                       or --print: a second session the roll call cannot see. Matched
                       on both shells, because on Windows PowerShell is the primary one.
                       `claude --version` and reading a file that mentions claude pass.

NON-ROSTER AGENT TYPES ARE REFUSED, NOT PASSED THROUGH. A dispatch to Explore,
general-purpose, a fork or a plugin agent would read in the roll call as a properly
dispatched turn ("TEAM | EXPLORE (1 dispatched)") while bypassing every lane CLAUDE.md
defines, and a built-in agent holds Bash: the WREN-only and SAGE-only gates would still
stop a Doc write or a privacy stamp, but nothing stops it running register.py. The
thirteen are the closed set of who works on Taylor's records.

WHY NOT A SETTINGS DENY RULE. `permissions.deny: ["Agent(milo)"]` would block the
call, but with a generic message and from a static list: it cannot say APPROVED, NOT
BUILT YET the day Taylor approves a phase, because that depends on
context/architecture/phases.json.

THE SHELL CHECK IS CRUDE AND SAYS SO. It reads each command fragment's program, past
call operators and env assignments, and looks one level into a quoted argument (so
`powershell -Command "claude -p ..."` is seen). A separator inside a quoted wrapper
can still split it where the shell would not; erring there costs a missed refusal of
a dispatch that no prose in this system ever asks for.

FAILS CLOSED, all the way: an unreadable payload, an unreadable team file, and any
crash of this hook itself are refusals. Python's own exit code on a traceback is 1,
which Claude Code treats as a non-blocking error, so an uncaught exception here would
be a dispatch waved through. main() catches everything and refuses instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Even a failed import must end in a refusal, never in Python's own exit 1 (non-blocking).
try:
    import _audit  # noqa: E402
    from _gate import (  # noqa: E402
        REPO_ROOT,
        PayloadUnreadable,
        block,
        deny_environment,
        read_payload,
        tool_input,
    )
except Exception as _exc:  # noqa: BLE001
    _IMPORT_ERROR: Exception | None = _exc  # swallow: main() refuses every call, naming this error
    REPO_ROOT = HERE.parents[1]
else:
    _IMPORT_ERROR = None

SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

HOOK = "require-active-agent"
DISPATCH_TOOLS = frozenset({"Agent", "Task"})
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

WORKFLOW_LINES = (
    "NOT USED HERE: a workflow starts agents that the roll call cannot name or check.",
    "Send the work to the agent whose lane it is with the Agent tool instead.",
)
SESSION_LINES = (
    "NOT USED HERE: a second Claude session started from the shell is a dispatch the roll call cannot see.",
    "Send the work to the agent whose lane it is with the Agent tool instead.",
)

# Programs that only read the file or text they are given. A fragment led by one of
# these mentions claude; it does not start it.
READERS = frozenset({
    "cat", "type", "gc", "get-content", "more", "less", "head", "tail", "grep", "egrep", "fgrep", "rg",
    "findstr", "select-string", "sls", "sed", "awk", "wc", "diff", "fc", "git", "ls", "dir",
    "get-childitem", "gci", "echo", "printf", "write-output", "write-host", "code", "notepad", "#",
})
PREFIXES = frozenset({"&", ".", "call", "start", "exec", "time", "nohup", "npx", "bunx", "cmd", "/c"})
SEPARATORS = re.compile(r"\|\||&&|[;|\r\n]")
TOKEN = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


def _name(token: str) -> str:
    stem = token.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".ps1", ".bat"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


CLAUDE_PROGRAMS = frozenset({"claude", "claude-code"})  # claude-code: `npx @anthropic-ai/claude-code`


def claude_cli_dispatch(command: str, depth: int = 0) -> tuple[str, str] | None:
    """("agent", NAME) or ("session", flag) when this command starts the claude CLI as a dispatch."""
    if "claude" not in (command or "").lower():
        return None  # the common case, decided before any parsing, so a parser fault cannot touch it
    for fragment in SEPARATORS.split(command or ""):
        raw = TOKEN.findall(fragment)
        tokens = [t.strip("'\"") for t in raw]
        i = 0
        while i < len(tokens) and (tokens[i].lower() in PREFIXES or ENV_ASSIGNMENT.match(tokens[i])):
            i += 1
        if i >= len(tokens) or _name(tokens[i]) in READERS:
            continue
        if _name(tokens[i]) in CLAUDE_PROGRAMS:
            args = tokens[i + 1:]
            session = None
            for j, arg in enumerate(args):
                flag, _, inline = arg.partition("=")
                if flag == "--agent":
                    return "agent", inline or (args[j + 1] if j + 1 < len(args) else "")
                if flag in ("--agents", "-p", "--print") and session is None:
                    session = flag
            if session:
                return "session", session
            continue
        if depth < 2:
            # A wrapper (powershell -Command "...", bash -c '...'): look inside its quoted argument.
            for token in raw[i + 1:]:
                if token[:1] in "'\"" and " " in token:
                    found = claude_cli_dispatch(token.strip("'\""), depth + 1)
                    if found:
                        return found
    return None


def decide(tool: str, given: dict, team) -> tuple[bool, str, tuple[str, ...]]:
    """(allowed, rule_id, the lines a refusal prints). Pure, so the guardrail self-test drives it.

    `team` is a scripts/team.py Team, or None when the call turned out not to be a
    dispatch (then it is never consulted).
    """
    import team as team_module  # noqa: PLC0415  -- from scripts/, put on sys.path above

    if tool == "Workflow":
        return False, "workflow", WORKFLOW_LINES
    if tool in SHELL_TOOLS:
        found = claude_cli_dispatch(str(given.get("command") or ""))
        if found is None:
            return True, "not-a-dispatch", ()
        kind, value = found
        if kind == "session":
            return False, f"claude-cli:{value}", SESSION_LINES
        # A named agent that is switched off gets its own two lines, which tell Taylor
        # more. One that is on is refused all the same: a second session started from
        # the shell is invisible to the roll call whoever it runs as.
        allowed, rule_id, lines = team_module.dispatch_verdict(team, value)
        if not allowed:
            return False, rule_id, lines
        return False, "claude-cli:--agent", SESSION_LINES
    if tool in DISPATCH_TOOLS:
        return team_module.dispatch_verdict(team, str(given.get("subagent_type") or ""))
    return True, "not-a-dispatch", ()


def needs_team(tool: str, given: dict) -> bool:
    """Whether deciding this call needs the team files at all. Most shell commands do not."""
    if tool in DISPATCH_TOOLS:
        return True
    if tool in SHELL_TOOLS:
        found = claude_cli_dispatch(str(given.get("command") or ""))
        return found is not None and found[0] == "agent"
    return False


def run() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    tool = str(payload.get("tool_name") or "")
    given = tool_input(payload)
    team = None
    if needs_team(tool, given):
        import team as team_module  # noqa: PLC0415

        try:
            team = team_module.load(REPO_ROOT)
        except team_module.TeamUnreadable as exc:
            _audit.record(hook=HOOK, tool=tool, decision="deny_unverifiable", detail=str(exc)[:300],
                          session_id=str(payload.get("session_id") or ""))
            return deny_environment(HOOK, "team roster or phase gate", str(exc))

    allowed, rule_id, lines = decide(tool, given, team)
    if rule_id == "not-a-dispatch":
        return 0
    target = str(given.get("subagent_type") or given.get("command") or tool)[:200]
    session = str(payload.get("session_id") or "")
    if allowed:
        _audit.record(hook=HOOK, tool=tool, agent=rule_id.split(":", 1)[-1], decision="allow",
                      rule_id=rule_id, target=target, session_id=session)
        return 0
    _audit.record(hook=HOOK, tool=tool, decision="deny", rule_id=rule_id, target=target, session_id=session)
    return block(list(lines))


def refuse_crash(exc: Exception) -> int:
    """The refusal for a crash, written without anything this hook imports, since that may be what broke."""
    message = "\n".join([
        f"BLOCKED: {HOOK} crashed ({exc.__class__.__name__}: {str(exc)[:160]}) before it could",
        "check this call, so it is refusing rather than letting an unchecked agent start.",
        "This is an ENVIRONMENT fault. Run `python scripts/ea_doctor.py` and send Mike the output.",
    ]) + "\n"
    try:
        sys.stderr.buffer.write(message.encode("utf-8"))
    except Exception:  # noqa: BLE001
        pass  # swallow: nowhere left to write; the exit code below still refuses
    return 2


def main() -> int:
    try:
        if _IMPORT_ERROR is not None:
            raise _IMPORT_ERROR
        return run()
    except Exception as exc:  # noqa: BLE001
        # swallow: converted into a refusal. An uncaught traceback exits 1, which Claude
        # Code treats as non-blocking, so letting it escape would wave the dispatch through.
        return refuse_crash(exc)


if __name__ == "__main__":
    sys.exit(main())
