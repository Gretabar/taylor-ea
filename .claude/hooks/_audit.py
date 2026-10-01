"""The audit writer every hook and delivery script calls, and the one thing here that may never block.

PORTED FROM PIPER. Env var EA_ROOT, database module ea_db, doctor ea_doctor.py.
scripts/docs_edit.py records one row per Doc write through this module, including
every refusal and failure: /morning lists yesterday's Doc writes from the table, and
G4 ("no false success") is observed here as decision="fail".

TWO SINKS, ON PURPOSE. The `audit` table in state/ea.db is the queryable
record; logs/audit-YYYY-MM.jsonl is the greppable one. A SQLite file is useless
at the moment somebody needs to answer "what left this machine last Tuesday"
with a text editor, and a corrupt database must not take the record of egress
with it. Either sink landing is enough to call the row recorded.

IT NEVER BLOCKS. A hook that deadlocks on its own bookkeeping is strictly worse
than one that does not log: the first stops Taylor working, the second loses a
line. So every failure path here returns rather than raises, and the callers
treat record() as fire-and-forget.

BUT IT IS NEVER SILENT ABOUT FAILING. A quiet audit failure is exactly GRIFFIN's
nine-day false-criticals cascade, where a broken job kept reporting and nobody
could tell. So a write that lands in neither sink touches state/AUDIT-DEGRADED
with the reason and the timestamp, and team-rollcall.py renders a full-width
banner on every turn until that file is deleted. Loud and non-blocking, which is
the pair that actually works.

THE DEGRADED MARKER IS CLEARED BY A HUMAN, NOT BY A LATER SUCCESS. A subsequent
successful write does not remove it. The fact worth surfacing is not "logging
works now", it is "there is a window in which decisions were made and not
recorded", and that fact survives the next success.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

_ENV_ROOT = os.environ.get("EA_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
REPO_ROOT = Path(_ENV_ROOT) if _ENV_ROOT else Path(__file__).resolve().parents[2]

DEGRADED_MARKER = REPO_ROOT / "state" / "AUDIT-DEGRADED"
LOG_DIR = REPO_ROOT / "logs"

FIELDS = (
    "ts", "session_id", "agent", "hook", "tool", "decision", "rule_id",
    "target", "payload_sha256", "record_count", "approval_id", "detail",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mirror(row: dict) -> str:
    """Append one JSON line to logs/audit-YYYY-MM.jsonl. Returns "" on success."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"audit-{row['ts'][:7]}.jsonl"
        line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        # Append mode on a single line under 4 KB is atomic enough on Windows
        # for concurrent hooks; this is a mirror, and the table is the record of
        # order.
        with open(path, "ab") as handle:
            handle.write(line.encode("utf-8"))
        return ""
    except (OSError, TypeError, ValueError) as exc:
        return f"jsonl: {exc}"


def _table(row: dict) -> str:
    """Insert one row into the audit table. Returns "" on success."""
    try:
        scripts = str(REPO_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import ea_db  # noqa: PLC0415  -- local by design: see the module header

        conn = ea_db.connect()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO audit (ts, session_id, agent, hook, tool, decision,"
                    " rule_id, target, payload_sha256, record_count, approval_id, detail)"
                    " VALUES (:ts, :session_id, :agent, :hook, :tool, :decision,"
                    " :rule_id, :target, :payload_sha256, :record_count, :approval_id, :detail)",
                    row,
                )
        finally:
            conn.close()
        return ""
    except Exception as exc:  # noqa: BLE001
        # swallow: the audit writer is not allowed to raise into a hook, and the
        # failure is not lost -- it is returned to record(), which marks the run
        # degraded if the mirror did not land either.
        return f"sqlite: {exc.__class__.__name__}: {exc}"


def _mark_degraded(reason: str) -> None:
    try:
        DEGRADED_MARKER.parent.mkdir(parents=True, exist_ok=True)
        with open(DEGRADED_MARKER, "a", encoding="utf-8") as handle:
            handle.write(f"{_now()}  {socket.gethostname()}  {reason}\n")
    except OSError:
        # swallow: if the marker itself cannot be written there is nowhere left
        # to put the fact, and raising here would block the tool -- which is the
        # one outcome this module exists to prevent.
        pass


def record(
    *,
    decision: str,
    hook: str = "",
    tool: str = "",
    agent: str = "",
    rule_id: str = "",
    target: str = "",
    payload_sha256: str = "",
    record_count: int | None = None,
    approval_id: int | None = None,
    detail: str = "",
    session_id: str = "",
) -> None:
    """Write one gated-decision row to both sinks. Never raises, never blocks."""
    row = {
        "ts": _now(),
        "session_id": session_id or os.environ.get("CLAUDE_SESSION_ID", ""),
        "agent": agent,
        "hook": hook,
        "tool": tool,
        "decision": decision,
        "rule_id": rule_id,
        "target": target,
        "payload_sha256": payload_sha256,
        "record_count": record_count,
        "approval_id": approval_id,
        "detail": detail,
    }

    mirror_error = _mirror(row)
    table_error = _table(row)

    if mirror_error and table_error:
        _mark_degraded(f"{hook or '?'}/{decision}: {table_error} | {mirror_error}")


def degraded_reason() -> str:
    """The newest line of state/AUDIT-DEGRADED, or "" when the marker is absent.

    Read by team-rollcall.py and ea_doctor.py. An unreadable marker that
    exists still counts as degraded: the file being there is the signal.
    """
    try:
        if not DEGRADED_MARKER.exists():
            return ""
        text = DEGRADED_MARKER.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return "AUDIT-DEGRADED exists but could not be read"
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "AUDIT-DEGRADED exists but is empty"
