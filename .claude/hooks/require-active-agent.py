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

THE SHELL CHECK is _shell.program_runs(), the parser every shell gate shares: the
claude CLI (or `npx @anthropic-ai/claude-code`) started through any launcher it
unwraps, `$out = claude -p`, `cmd /c "claude -p hi"`, `Start-Process -FilePath claude`,
`env` and `timeout` prefixes, `powershell -c claude ...`, `x=$(claude ...)`,
`(claude ...)`, an encoded PowerShell command, and a string piped into iex or bash.
It does not look inside the quoted arguments of an ordinary program, so a capture whose
text says "Claude -p rota" is not a dispatch.

team.py IS IMPORTED ONLY FOR A DISPATCH. Most shell commands are not one, and a
broken team.py must not refuse them all: that would refuse `python
scripts/ea_doctor.py`, the command every refusal tells Taylor to run.

FAILS CLOSED, all the way: an unreadable payload, an unreadable team file, and any
crash of this hook itself are refusals. Python's own exit code on a traceback is 1,
which Claude Code treats as a non-blocking error, so _failsafe.run_gate() turns every
crash, including a failed import, into a refusal.
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
        REPO_ROOT,
        PayloadUnreadable,
        block,
        deny_environment,
        read_payload,
        tool_input,
    )
    from _shell import program_runs  # noqa: E402
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
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

CLAUDE_PROGRAMS = frozenset({"claude", "claude-code"})  # claude-code: `npx @anthropic-ai/claude-code`
SESSION_FLAGS = frozenset({"--agents", "-p", "--print"})


def claude_cli_dispatch(command: str) -> tuple[str, str] | None:
    """("agent", NAME) or ("session", flag) when this command starts the claude CLI as a dispatch."""
    session = None
    for args in program_runs(command or "", CLAUDE_PROGRAMS):
        # Flattened, so flags passed inside one quoted argument (Start-Process claude
        # -ArgumentList '-p hi') are still seen.
        flat = " ".join(args).split()
        for j, arg in enumerate(flat):
            flag, _, inline = arg.partition("=")
            if flag == "--agent":
                return "agent", inline or (flat[j + 1] if j + 1 < len(flat) else "")
            if flag in SESSION_FLAGS and session is None:
                session = flag
    return ("session", session) if session else None


def _team_module():
    """scripts/team.py, imported only when a call turned out to be a dispatch."""
    import team  # noqa: PLC0415  -- from scripts/, put on sys.path above

    return team


def decide(tool: str, given: dict, team) -> tuple[bool, str, tuple[str, ...]]:
    """(allowed, rule_id, the lines a refusal prints). Pure, so the guardrail self-test drives it.

    `team` is a scripts/team.py Team, or None when the call turned out not to be a
    dispatch (then it is never consulted).
    """
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
        allowed, rule_id, lines = _team_module().dispatch_verdict(team, value)
        if not allowed:
            return False, rule_id, lines
        return False, "claude-cli:--agent", SESSION_LINES
    if tool in DISPATCH_TOOLS:
        return _team_module().dispatch_verdict(team, str(given.get("subagent_type") or ""))
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
        team_module = _team_module()
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


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
