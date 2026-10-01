"""PreToolUse (Agent): print who just got the work, in chat.

PORTED FROM PIPER. Agent files live under .claude/agents/ here (so the VS Code
extension finds them by opening the folder), env var EA_ROOT, and the H1
separator class is written with escapes so this file carries no literal dash glyphs.

Taylor has no way to confirm a dispatch actually happened. The Agent tool call is
collapsed in the UI, so "I sent this to WREN" and "I quietly did it myself" look
identical from his side, and he is by design not able to audit the difference.
This prints one line per dispatch so the claim is visible rather than asserted.

The specialty is read out of .claude/agents/<name>.md at runtime instead of a table in
here, because a table in a hook is a second source of truth for the roster and
would be wrong within a month of the next agent being added.

This hook MUST NOT BLOCK. It is cosmetic; a banner that deadlocks a dispatch is
strictly worse than no banner, so every failure path exits 0 in silence. Note the
asymmetry with the gates in this directory: they fail closed because their job is
to refuse, this one fails open because its job is to narrate.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_ENV_ROOT = os.environ.get("EA_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
REPO_ROOT = Path(_ENV_ROOT) if _ENV_ROOT else Path(__file__).resolve().parents[2]

OBJECTIVE_LIMIT = 100

# "# WREN - Delivery". Accept an em dash, an en dash, a
# double hyphen or a single one: eight agent files written by different hands
# will not agree on the separator, and the banner is not worth failing over it.
H1 = re.compile(r"^#\s+(?P<name>[^\n]+?)\s+(?:\u2014|\u2013|--|-)\s+(?P<specialty>[^\n]+?)\s*$")


def agent_specialty(name: str) -> str:
    """Specialty from the H1 of agents/<name>.md, or "" if there is no such agent."""
    md = REPO_ROOT / ".claude" / "agents" / f"{name}.md"
    if not md.is_file():
        return ""
    try:
        text = md.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""  # swallow: an unreadable agent file only costs the bracket suffix
    for line in text.splitlines():
        if not line.startswith("# "):
            continue
        match = H1.match(line)
        return match.group("specialty") if match else ""
    return ""


def objective_of(tool_input: dict) -> str:
    """The dispatch's one-line objective, from `description` or an OBJECTIVE: line."""
    text = (tool_input.get("description") or "").strip()
    if not text:
        prompt = tool_input.get("prompt") or ""
        match = re.search(r"^\s*OBJECTIVE:\s*(.+)$", prompt, re.M)
        text = match.group(1).strip() if match else ""
    text = " ".join(text.split())
    if len(text) > OBJECTIVE_LIMIT:
        text = text[: OBJECTIVE_LIMIT - 3].rstrip() + "..."
    return text


def banner(tool_input: dict) -> str:
    raw_type = (tool_input.get("subagent_type") or "").strip()
    if not raw_type:
        return ""

    # Plugin-qualified names arrive as "ea:wren"; only the bare name maps to a
    # file in agents/.
    bare = raw_type.split(":")[-1].strip()
    specialty = agent_specialty(bare)

    if specialty:
        head = f">> {bare.upper()} dispatched  [{specialty}]"
    else:
        head = f">> {raw_type} dispatched"

    objective = objective_of(tool_input)
    return f"{head}\n   {objective}" if objective else head


def main() -> int:
    try:
        # Bytes, then explicit UTF-8: sys.stdin decodes with the locale codec,
        # cp1252 here, which mangles any accented name in the prompt.
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
        message = banner(payload.get("tool_input") or {})
    except Exception:
        return 0  # swallow: a cosmetic banner must never block a dispatch, whatever broke

    if not message:
        return 0

    try:
        # json.dumps keeps this on one line and escapes the newline, which is
        # what makes a two-line banner legal inside a single systemMessage string.
        line = json.dumps({"systemMessage": message}) + "\n"
        sys.stdout.buffer.write(line.encode("utf-8"))
        sys.stdout.flush()
    except Exception:
        return 0  # swallow: a closed or non-UTF-8 stdout is not worth failing a dispatch over

    return 0


if __name__ == "__main__":
    sys.exit(main())
