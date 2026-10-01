"""The scheduled tick. Deterministic: no model, no prose, and it never writes to a Doc.

PORTED FROM PIPER's cadence_tick.py: the frame is kept (lock held across the whole
run, a heartbeat row only on success, fixed exit codes watched from outside by the
.ps1 wrapper, --dry-run on an in-memory copy, --date). The body is new:

  1. PREFLIGHT. identity.json readable; the Google token refreshes with the scopes
     the work needs (documents always, calendar.readonly only if a Calendar series
     is linked). A failure here exits 2 with the reason and writes nothing.
  2. EVERY REGISTERED DOC, READ ONLY: docs_reconcile.reconcile_doc. A Status cell
     reading Done completes the register action (completed_via=doc); an unchanged
     revision is skipped; nothing is ever written back to the Doc.
  3. EVERY LINKED CALENDAR SERIES, READ ONLY: next_at and cadence_observed.
  4. A HEARTBEAT ROW, status ok only when every Doc and series was read.

WHY NOT `claude -p`. STEVIE's sweep did that, produced "Unknown skill", and rotted
for eleven weeks because the process died before its own error handling ran. A
dead tick here costs staleness that the status line and /morning show in red; it
can never cost a wrong write, because this file has no write path to a Doc at all.

FIXTURES ARE SEPARATE. --fixtures (or EA_FIXTURE_MODE=1) reconciles the fixture
Docs in state/fixtures.db under its own lock and its own job name, so a test run
can neither block the live tick nor be mistaken for its heartbeat.

Exit codes, watched by run_ea_tick.ps1:
    0  ticked (or another run holds the lock, or there is nothing registered yet)
    2  preflight failed: identity unreadable, token missing, expired or short a scope
    3  the register could not be written
    4  partial: some Doc or Calendar series could not be read; the rest was done
    9  unhandled crash
"""

from __future__ import annotations

import os
import sys

if "--fixtures" in sys.argv:
    os.environ["EA_FIXTURE_MODE"] = "1"

import argparse  # noqa: E402
import socket  # noqa: E402
import sqlite3  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ea_db  # noqa: E402
import job_lock  # noqa: E402

FIXTURES = ea_db.fixture_mode()
JOB = "ea_tick_fixtures" if FIXTURES else "ea_tick"
LOCK_PATH = ea_db.REPO_ROOT / "state" / ("ea_tick_fixtures.lock" if FIXTURES else "ea_tick.lock")
KEEP_TICK_DAYS = 120


class PreflightError(RuntimeError):
    """The tick cannot start: nothing was read and nothing was written."""


def record_tick(conn, status: str, detail: str) -> None:
    """Append one liveness row. statusline-ea.py reads the newest ok row."""
    with conn:
        conn.execute("INSERT INTO job_ticks (job, ts, status, detail, host, pid) VALUES (?,?,?,?,?,?)",
                     (JOB, ea_db.now_iso(), status, detail[:500], socket.gethostname(), os.getpid()))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_TICK_DAYS)).isoformat(timespec="seconds")
        conn.execute("DELETE FROM job_ticks WHERE ts < ?", (cutoff,))


def preflight(conn) -> dict:
    """What the run needs, or PreflightError naming the first thing missing."""
    import docs_reconcile  # noqa: PLC0415
    import google_creds  # noqa: PLC0415
    import register  # noqa: PLC0415

    try:
        register.identity()
    except register.RegisterError as exc:
        raise PreflightError(str(exc)) from exc
    docs = docs_reconcile.docs_for_tick(conn, FIXTURES)
    series = conn.execute("SELECT COUNT(*) FROM meetings WHERE source = 'calendar' AND series_event_id IS NOT NULL"
                          ).fetchone()[0] if not FIXTURES else 0
    needs = {"docs": docs, "series": int(series), "docs_service": None, "calendar_ok": True, "calendar_error": ""}
    if docs:
        try:
            import docs_read  # noqa: PLC0415

            needs["docs_service"] = docs_read.docs_service()
        except google_creds.CredentialsError as exc:
            raise PreflightError(f"Google token: {exc}") from exc
    if series:
        try:
            google_creds.load_credentials([google_creds.CALENDAR_READONLY])
        except google_creds.CredentialsError as exc:
            needs["calendar_ok"], needs["calendar_error"] = False, str(exc)
    return needs


def run(conn, needs: dict, today: date) -> dict:
    import calendar_next  # noqa: PLC0415
    import docs_reconcile  # noqa: PLC0415

    report = {"docs": [], "calendar": [], "partial": []}
    for row in needs["docs"]:
        result = docs_reconcile.safe_reconcile(conn, needs["docs_service"], row, actor="tick")
        report["docs"].append(result)
        if result["status"] == "unreadable":
            report["partial"].append(f"{row['title']}: {result.get('error')}")
    if needs["series"]:
        if not needs["calendar_ok"]:
            report["partial"].append(f"Calendar: {needs['calendar_error']}")
        else:
            try:
                report["calendar"] = calendar_next.refresh(conn)
            except calendar_next.CalendarError as exc:
                report["partial"].append(f"Calendar: {exc}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fixtures", action="store_true", help="reconcile the fixture Docs instead of the live ones")
    parser.add_argument("--date", help="report as of this date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="read everything, write nothing")
    args = parser.parse_args()
    ea_db.console_utf8()
    today = date.fromisoformat(args.date) if args.date else date.today()

    try:
        with job_lock.hold(LOCK_PATH, label=JOB):
            live = ea_db.connect()
            ea_db.migrate(live)
            conn = live
            if args.dry_run:
                # A copy, not a rolled-back transaction: every helper commits through
                # `with conn:`, so a rollback would have nothing left to undo.
                conn = sqlite3.connect(":memory:")
                conn.row_factory = sqlite3.Row
                live.backup(conn)
                live.close()
            try:
                needs = preflight(conn)
                if not needs["docs"] and not needs["series"]:
                    if not args.dry_run:
                        record_tick(conn, "ok", "nothing registered yet: 0 Docs, 0 Calendar series")
                    print(f"tick {today.isoformat()}  nothing registered yet (link Docs with scripts/link_docs.py)")
                    return 0
                report = run(conn, needs, today)
                completed = sum(len(d["completed"]) for d in report["docs"])
                detail = (f"{len(report['docs'])} Doc(s), {completed} completed from a Doc, "
                          f"{len(report['calendar'])} series refreshed"
                          + (f"; PARTIAL: {'; '.join(report['partial'])}" if report["partial"] else ""))
                if not args.dry_run:
                    record_tick(conn, "warn" if report["partial"] else "ok", detail)
            finally:
                conn.close()
    except job_lock.AlreadyRunning as exc:
        print(f"{exc}")
        return 0
    except PreflightError as exc:
        print(f"PREFLIGHT FAILED: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"REGISTER WRITE FAILED: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 3

    import docs_reconcile  # noqa: PLC0415

    print(f"tick {today.isoformat()} [{JOB}]" + ("  [DRY RUN, nothing written]" if args.dry_run else ""))
    for result in report["docs"]:
        print(docs_reconcile.render(result))
    for result in report["calendar"]:
        print(f"  calendar   {result['person']}: next {result['next_at'] or 'none'} ({result['cadence_observed']})")
    if report["partial"]:
        print("PARTIAL: " + "; ".join(report["partial"]), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # swallow: converted into exit 9 with the reason on stderr, so the wrapper's
        # outside-the-process watch alarms on a code rather than a traceback.
        print(f"TICK CRASHED: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        sys.exit(9)
