"""The last line of every gate: a failed import, a crash or an odd exit code becomes a refusal.

NEW in this repo. Claude Code blocks a PreToolUse call only on exit code 2. Every
other non-zero exit is a "non-blocking error": the tool call runs. Python's own exit
code on an uncaught exception is 1, so a gate that crashes, or that cannot even import
its helpers, waves through exactly the call it exists to stop. A review reproduced it:
a lone UTF-16 surrogate in a command made two gates crash while printing their
refusal, and the command they were refusing ran.

So every gate's __main__ is

    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))

and run_gate returns 0 or 2, nothing else: 0 only when the gate itself said 0.

STANDARD LIBRARY ONLY, on purpose. This module has to import when the modules it
protects (_gate, _audit, _transcript, scripts/) do not. If even this file fails to
import, the gate exits 1, and the command wrapper in .claude/settings.json turns that
into a block too. That wrapper is the backstop for the backstop; this is the gate's own.
"""

from __future__ import annotations

import sys


def refuse(hook: str, reason: str) -> int:
    """Print why the call is blocked, never failing to, and return the blocking exit code."""
    message = (
        f"BLOCKED: {hook} could not finish checking this call ({reason}).\n"
        "It is blocking rather than letting through something it never finished looking at.\n"
        "This is an ENVIRONMENT fault, not a problem with the request: do not retry or rephrase it.\n"
        "Run `python scripts/ea_doctor.py` and send Mike the output.\n"
    )
    try:
        sys.stderr.buffer.write(message.encode("utf-8", errors="replace"))
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass  # swallow: nowhere left to write; the exit code below still refuses
    return 2


def describe(exc: BaseException) -> str:
    """One line naming an exception, safe to print whatever it carries."""
    try:
        text = str(exc).replace("\r", " ").replace("\n", " ")
    except Exception:  # noqa: BLE001
        text = "(its message could not be read)"  # swallow: the type name below still says what broke
    return f"{type(exc).__name__}: {text[:160]}"


def run_gate(hook: str, main, import_error: BaseException | None = None) -> int:
    """Run a gate's main(). Its own 0 or 2 stands; anything else is a refusal.

    A sys.exit() inside main() is the gate's own answer and is held to the same rule,
    so argparse's exit 2 still blocks and a stray exit 1 does not let the call through.
    """
    if import_error is not None:
        return refuse(hook, f"it could not load its own code, {describe(import_error)}")
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code
    except BaseException as exc:  # noqa: BLE001
        # swallow: converted into a refusal, which is the whole point of this module.
        # RecursionError, MemoryError and KeyboardInterrupt included.
        return refuse(hook, f"it crashed, {describe(exc)}")
    # type() and not isinstance(): a bool is an int, and False == 0 would read as "allow".
    if type(code) is int and code in (0, 2):
        return code
    return refuse(hook, f"it ended with exit code {code!r}, which Claude Code would not treat as a block")
