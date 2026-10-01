"""Raise an alert for Taylor about the SYSTEM. Local only: there is no outbound channel in Phase 1.

PORTED FROM PIPER's notify_cass.py. An alert is written where the things Taylor
already looks at will find it:

    state/ALERTS.jsonl   the unread queue. /morning opens with it; ea_doctor.py
                         reports its depth.
    logs/alerts.log      the human-readable history, kept bounded.
    a Windows toast      the only channel that does not need a session open.

WHAT CHANGED FROM PIPER. The staleness check is about the system and nothing else:
the tick has never succeeded, or last succeeded too long ago, or a registered Doc
has not been read successfully in that window. PIPER also alarmed on work orders
piling up; there is no equivalent here, and there must not be one about open
employee actions either. Blueprint s.4 and s.6: no weekday chasers, no reminders to
Taylor merely because employee work is open. This toasts when the MACHINE is
unwell, never about the work.

WHAT --watch DOES NOT COVER: a scheduled task that was deleted or disabled. Nothing
inside a job can report that the job is not running. ea_doctor.py checks the task.

IT MUST NEVER THROW. Every caller is a wrapper reporting a failure, and a reporter
that dies while reporting produces exactly the silence it exists to prevent.

Usage:
    python scripts/notify_owner.py --level fail --text "ea tick exited 3"
    python scripts/notify_owner.py --watch [--stale-days 3] [--force]
    python scripts/notify_owner.py --list
    python scripts/notify_owner.py --ack-all
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
ALERTS = REPO_ROOT / "state" / "ALERTS.jsonl"
LOG = REPO_ROOT / "logs" / "alerts.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP_LINES = 2000

DEFAULT_STALE_DAYS = int(os.environ.get("EA_STALE_DAYS") or 3)
TOAST_COOLDOWN_HOURS = 24
WATCH_JOB = "watchdog"
TICK_JOB = "ea_tick"

TOAST_PS = """
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@"
<toast><visual><binding template="ToastGeneric">
<text>$env:EA_TOAST_TITLE</text><text>$env:EA_TOAST_TEXT</text>
</binding></visual></toast>
"@)
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show(
    [Windows.UI.Notifications.ToastNotification]::new($xml))
"""

BALLOON_PS = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Warning
$icon.BalloonTipTitle = $env:EA_TOAST_TITLE
$icon.BalloonTipText = $env:EA_TOAST_TEXT
$icon.Visible = $true
$icon.ShowBalloonTip(20000)
Start-Sleep -Seconds 6
$icon.Dispose()
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, text: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as handle:
            handle.write(text.encode("utf-8"))
        return ""
    except OSError as exc:
        return str(exc)


def _roll(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size <= LOG_MAX_BYTES:
            return
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
        path.write_text("\n".join(lines[-LOG_KEEP_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass  # swallow: an unrollable log is a disk problem, not a reason to lose the alert


def notify(level: str, text: str, source: str) -> int:
    """Write one alert to both sinks. Always returns 0."""
    stamp = _now()
    record = {"ts": stamp, "level": level, "source": source, "text": text}
    queue_error = _append(ALERTS, json.dumps(record, ensure_ascii=False) + "\n")
    log_error = _append(LOG, f"{stamp}  {level.upper():<5} {source}: {text}\n")
    _roll(LOG)
    print(f"[{level.upper()}] {source}: {text}")
    if queue_error and log_error:
        print(f"notify_owner: neither alert sink could be written ({queue_error} | {log_error}). "
              f"The line above is the only record.", file=sys.stderr)
    return 0


def toast(title: str, text: str) -> str:
    """Raise a desktop notification. Returns "" on success, else why not. NEVER RAISES.

    The message travels through the environment, never interpolated into the script
    text: building a command line from arbitrary text is how a quoting bug becomes
    an execution bug.
    """
    if os.name != "nt":
        return "not Windows"
    env = dict(os.environ, EA_TOAST_TITLE=title, EA_TOAST_TEXT=text)
    failures = []
    for label, script in (("toast", TOAST_PS), ("balloon", BALLOON_PS)):
        try:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
                env=env, capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            failures.append(f"{label}: {exc.__class__.__name__}")
            continue  # swallow: recorded and reported by the return value
        if done.returncode == 0:
            return ""
        failures.append(f"{label}: {(done.stderr or '').strip().splitlines()[:1]}")
    return "; ".join(failures) or "unknown"


def _staleness(stale_days: int) -> tuple[list[str], object]:
    """(reasons the system looks unwell, an open db connection or None)."""
    reasons: list[str] = []
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import ea_db  # noqa: PLC0415

        conn = ea_db.connect()
        ea_db.migrate(conn)
    except Exception as exc:  # noqa: BLE001
        # swallow: a watchdog that cannot open the database has found something worth
        # saying, so it says that instead of dying.
        return [f"the register database could not be opened ({exc.__class__.__name__})"], None

    try:
        row = conn.execute(
            "SELECT ts FROM job_ticks WHERE job=? AND status='ok' ORDER BY ts DESC LIMIT 1",
            (TICK_JOB,)).fetchone()
        if row is None:
            reasons.append("the background tick has never recorded a successful run")
        else:
            stamp = datetime.fromisoformat(str(row["ts"]))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0
            if age > stale_days * 24:
                reasons.append(f"the background tick last succeeded {age / 24:.1f} days ago")

        cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat(timespec="seconds")
        stale_docs = conn.execute(
            "SELECT COUNT(*) AS n FROM docs WHERE fixture = 0 AND (verified_at IS NULL OR verified_at < ?)",
            (cutoff,)).fetchone()
        live_docs = conn.execute("SELECT COUNT(*) AS n FROM docs WHERE fixture = 0").fetchone()
        if live_docs and int(live_docs["n"]) and stale_docs and int(stale_docs["n"]):
            reasons.append(f"{stale_docs['n']} of {live_docs['n']} running Doc(s) have not been read "
                           f"successfully in {stale_days} days")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"the register could not be read ({exc.__class__.__name__})")  # swallow: reported
    return reasons, conn


def _toasted_recently(conn, hours: int) -> bool:
    try:
        row = conn.execute(
            "SELECT ts FROM job_ticks WHERE job=? AND status='warn' ORDER BY ts DESC LIMIT 1",
            (WATCH_JOB,)).fetchone()
        if row is None:
            return False
        stamp = datetime.fromisoformat(str(row["ts"]))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - stamp).total_seconds() < hours * 3600
    except Exception:  # noqa: BLE001
        return False  # swallow: cannot prove we toasted recently, so toast


def _record(conn, status: str, detail: str) -> None:
    try:
        with conn:
            conn.execute("INSERT INTO job_ticks (job, ts, status, detail) VALUES (?,?,?,?)",
                         (WATCH_JOB, _now(), status, detail[:200]))
    except Exception:
        pass  # swallow: a missing heartbeat row is not worth failing a wrapper


def watch(stale_days: int, force: bool) -> int:
    """The liveness check. Always returns 0: a watchdog must not fail the wrapper."""
    reasons, conn = _staleness(stale_days)
    if not reasons:
        if conn is not None:
            _record(conn, "ok", f"nothing stale at {stale_days}d")
            conn.close()
        print(f"watchdog: nothing stale (threshold {stale_days} days)")
        return 0

    text = "; ".join(reasons)
    notify("fail", f"The assistant may not be running: {text}", "watchdog")
    if conn is not None and not force and _toasted_recently(conn, TOAST_COOLDOWN_HOURS):
        print(f"watchdog: {text}  (toast suppressed, one was raised within {TOAST_COOLDOWN_HOURS}h)")
        conn.close()
        return 0
    problem = toast("Your assistant needs Mike", text + ". Tell Mike.")
    if problem:
        print(f"watchdog: could not raise a desktop notification ({problem}). The alert is in {ALERTS}.",
              file=sys.stderr)
    if conn is not None:
        _record(conn, "warn", text)
        conn.close()
    print(f"watchdog: {text}")
    return 0


def unread() -> list[dict]:
    try:
        raw = ALERTS.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    alerts = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue  # swallow: one truncated line does not hide the rest
        if isinstance(record, dict) and not record.get("acked"):
            alerts.append(record)
    return alerts


def ack_all() -> int:
    try:
        raw = ALERTS.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        print("no alerts file")
        return 0
    stamp, out, count = _now(), [], 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        if isinstance(record, dict) and not record.get("acked"):
            record["acked"] = stamp
            count += 1
        out.append(json.dumps(record, ensure_ascii=False))
    try:
        ALERTS.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"could not rewrite {ALERTS}: {exc}", file=sys.stderr)
        return 1
    print(f"acknowledged {count} alert(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--level", choices=("info", "warn", "fail"), default="warn")
    parser.add_argument("--text")
    parser.add_argument("--source", default="ea")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--ack-all", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.watch:
        try:
            return watch(args.stale_days, args.force)
        except Exception as exc:  # noqa: BLE001
            # swallow: the last line of defence. Printed, never raised.
            print(f"watchdog: crashed ({exc.__class__.__name__}: {exc}). Nothing was checked.", file=sys.stderr)
            return 0
    if args.ack_all:
        return ack_all()
    if args.list:
        alerts = unread()
        if not alerts:
            print("no unread alerts")
            return 0
        for record in alerts:
            print(f"  {record['ts']}  {record['level'].upper():<5} {record.get('source', '?')}: {record.get('text', '')}")
        print(f"\n{len(alerts)} unread. Clear with --ack-all once they are dealt with.")
        return 1
    if not args.text:
        parser.error("--text is required unless you passed --list, --ack-all or --watch")
    return notify(args.level, args.text, args.source)


if __name__ == "__main__":
    sys.exit(main())
