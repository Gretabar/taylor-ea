"""Stop hook: close every turn with who worked, whether the tick is alive, and anything degraded.

PORTED FROM PIPER. The banner from announce-dispatch.py scrolls away mid-turn. This
is the summary Taylor reads last, and its real job is the negative case: "TEAM:
NONE" makes a solo turn impossible to miss. After a capture it should read
REED -> PAGE -> WREN; docs/FOR-TAYLOR.md tells him so.

THE TWO CASES ARE DELIBERATELY ASYMMETRIC and that asymmetry is the whole design. A
dispatched turn gets one compact line meant to be skimmed past. A solo turn gets a
full-width block. STEVIE tried one short line for each and the honest report back
was "it was so small I almost missed it".

WHAT IS ADDED HERE.

  The tick-health line. Whether the VS Code extension renders a custom statusLine
  is unverified, and a liveness signal that silently does not render is the
  eleven-week QueueSweep failure again. So the roll call carries the same fact the
  status line does: one short line when healthy, a framed block when the tick is
  stale or has never run.

  The change-log banner. protect-architecture.py lets a rules-text edit through
  when Taylor typed `architecture change ok`, and CLAUDE.md obliges the
  orchestrator to append a CHANGE-LOG bullet in the same turn. If the audit shows
  an allowed rules edit newer than the log's last write, this says so, every turn,
  until the log catches up. Skipped on the build machine, where edits are build
  work rather than Taylor's architecture changes.

ASCII rules only, and this banner never contains the literal override phrases: the
gates look for them in the user's text, and banner text can be quoted back.

ALWAYS EXITS 0. A non-zero exit on a Stop hook re-engages the model and risks a loop.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _audit  # noqa: E402
import _health  # noqa: E402
from _gate import REPO_ROOT, is_build_machine  # noqa: E402
from _transcript import TranscriptUnreadable, roster, turn_context  # noqa: E402

RULE = "=" * 60
CHANGE_LOG = REPO_ROOT / "context" / "architecture" / "CHANGE-LOG.md"

SOLO = "\n".join([
    RULE,
    "TEAM: NONE - THIS TURN RAN SOLO",
    RULE,
    "No specialist was dispatched. If this turn captured,",
    "changed or wrote a record, the orchestrator did it alone,",
    "and that is the documented failure pattern rather than",
    "a shortcut. Tell Mike if this follows a capture.",
    RULE,
])

UNVERIFIED = "\n".join([
    RULE,
    "TEAM: UNVERIFIED - the session transcript could not be read.",
    "Whether a specialist ran this turn is unknown, not clean.",
    RULE,
])


def audit_banner() -> str:
    reason = _audit.degraded_reason()
    if not reason:
        return ""
    return "\n".join([
        RULE,
        "AUDIT DEGRADED - DECISIONS ARE NOT BEING RECORDED",
        RULE,
        "At least one gated decision or Doc write could not be",
        "written to the audit log or its mirror. The gates still",
        "ran. What is missing is the record of what happened.",
        "",
        f"last: {reason[:200]}",
        "",
        "Run: python scripts/ea_doctor.py and send Mike the output.",
        "This banner stays until a human deletes state/AUDIT-DEGRADED.",
        RULE,
    ])


def tick_line() -> str:
    """The fallback liveness signal, in case the status line does not render."""
    hours = _health.tick_age_hours()
    label = _health.system_label()
    text = f"{label}  {_health.render_age(hours)}"
    if _health.healthy(hours):
        return text
    return "\n".join([
        RULE,
        text,
        "The background tick that reconciles the Docs and the register",
        "has not run recently. Tell Mike. Nothing was written wrongly;",
        "what is stale is the picture /owe and /morning are reading.",
        RULE,
    ])


def change_log_banner() -> str:
    """Loud when an allowed rules-text edit is newer than the CHANGE-LOG's last write."""
    if is_build_machine():
        return ""
    try:
        logged = datetime.fromtimestamp(CHANGE_LOG.stat().st_mtime, tz=timezone.utc)
    except OSError:
        logged = datetime.min.replace(tzinfo=timezone.utc)
    db = _health.db_path()
    if not os.path.exists(db):
        return ""
    try:
        conn = sqlite3.connect(f"file:{db.replace(os.sep, '/')}?mode=ro", uri=True, timeout=1.0)
        try:
            row = conn.execute(
                "SELECT ts, target FROM audit WHERE hook = 'protect-architecture'"
                " AND decision = 'allow' AND rule_id = 'rules-text:override'"
                " AND target NOT LIKE '%CHANGE-LOG.md' ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return ""  # swallow: the AUDIT-DEGRADED banner owns audit failures
    if not row:
        return ""
    try:
        edited = datetime.fromisoformat(str(row[0]))
    except ValueError:
        return ""  # swallow: an unreadable stamp proves nothing either way
    if edited.tzinfo is None:
        edited = edited.replace(tzinfo=timezone.utc)
    if edited <= logged:
        return ""
    return "\n".join([
        RULE,
        "ARCHITECTURE CHANGED WITHOUT A CHANGE-LOG ENTRY",
        RULE,
        f"edited: {str(row[1])[:80]} at {row[0]}",
        "Append one bullet to context/architecture/CHANGE-LOG.md",
        "in its stated format, describing what Taylor asked for.",
        RULE,
    ])


def rollcall(payload: dict) -> str:
    try:
        ctx = turn_context(payload.get("transcript_path"))
    except TranscriptUnreadable:
        team = UNVERIFIED
    else:
        names = roster(ctx.dispatches)
        team = SOLO if not names else f"TEAM  |  {' -> '.join(names)}  ({len(names)} dispatched)"

    blocks = [b for b in (audit_banner(), change_log_banner(), tick_line(), team) if b]
    return "\n".join(blocks)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
    except Exception:
        payload = {}  # swallow: a Stop hook that cannot read its payload still must not block

    try:
        message = rollcall(payload)
    except Exception as exc:  # noqa: BLE001
        # swallow: degraded to a one-line notice rather than a crash, because exit 2
        # here re-engages the model. The notice itself says the roll call failed.
        message = f"TEAM: roll call failed ({exc.__class__.__name__}); dispatch state unknown"

    try:
        line = json.dumps({"systemMessage": message}) + "\n"
        sys.stdout.buffer.write(line.encode("utf-8"))
        sys.stdout.flush()
    except Exception:
        return 0  # swallow: exit 2 on a Stop hook re-engages the model and can loop
    return 0


if __name__ == "__main__":
    sys.exit(main())
