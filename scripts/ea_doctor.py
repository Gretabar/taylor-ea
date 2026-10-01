"""One command that describes this machine's whole state, to paste to Mike when something is wrong.

PORTED FROM PIPER's piper_doctor.py. Two machines and no CI: the first breakage becomes a site
visit unless the system can describe itself in one screen. Every line is a fact with a verdict, and
a check that could not run says so rather than passing: a doctor that reports healthy because it
could not take a pulse is the failure this system exists to prevent.

It never fixes anything, and touches the network only for the checks that are about the network
(a token refresh, one read of each registered Doc, one Calendar read).

WHAT CHANGED FROM PIPER. Google instead of PIPER's own systems: client and token present, refresh with
the Phase 1 scopes, every registered Doc readable and editable, the Calendar reachable. The repo
location is checked against context/identity.json. The scheduled task is EA-Tick and its battery
flags are read back. The build-machine marker is reported, because on Taylor's machine it must not
exist. Deviation D-1's status is shown, because it decides whether any live Doc can be written.

Usage:
    python scripts/ea_doctor.py
    python scripts/ea_doctor.py --offline        skip every network check (says so)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
HOOKS = REPO_ROOT / ".claude" / "hooks"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str]] = []

    def add(self, verdict: str, name: str, detail: str = "") -> None:
        self.lines.append((verdict, name, detail))

    def worst(self) -> str:
        verdicts = {v for v, _, _ in self.lines}
        return FAIL if FAIL in verdicts else (WARN if WARN in verdicts else OK)

    def render(self) -> str:
        width = max((len(n) for _, n, _ in self.lines), default=10)
        return "\n".join(f"  [{v:<4}] {n:<{width}}  {d}".rstrip() for v, n, d in self.lines)


def load_hook(filename: str):
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_")[:-3], HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(argv: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 99, f"{exc.__class__.__name__}: {exc}"
    return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()


def check_prerequisites(report: Report) -> None:
    report.add(OK if sys.version_info >= (3, 11) else FAIL, "python",
               f"{platform.python_version()} at {sys.executable}" + ("" if sys.version_info >= (3, 11) else ": needs 3.11+"))
    for module, why in (("yaml", "agent contract validation"), ("googleapiclient", "Docs and Calendar"),
                        ("google_auth_oauthlib", "the one consent"), ("tzdata", "Taylor's timezone on Windows")):
        found = importlib.util.find_spec(module) is not None
        report.add(OK if found else FAIL, f"module {module}", why if found else f"missing: {why}. pip install -r requirements.txt")
    try:
        import register  # noqa: PLC0415

        tz = register.identity().get("timezone")
        register.zone(tz)
        report.add(OK, "timezone", f"{tz} ({register.identity().get('timezone_status', '')})")
    except Exception as exc:  # noqa: BLE001
        report.add(FAIL, "timezone", f"{exc}")  # swallow: reported


def check_location(report: Report) -> None:
    try:
        identity = json.loads((REPO_ROOT / "context" / "identity.json").read_bytes().decode("utf-8"))
        expected = Path(identity.get("repo_root") or "")
        same = os.path.normcase(str(expected.resolve())) == os.path.normcase(str(REPO_ROOT.resolve()))
        report.add(OK if same else WARN, "repo path",
                   f"{REPO_ROOT}" + ("" if same else f" but identity.json says {expected}: update repo_root"))
    except (OSError, ValueError) as exc:
        report.add(FAIL, "repo path", f"context/identity.json unreadable: {exc}")
    try:
        hook = load_hook("no-cloud.py")
        reason = hook.classify_path(str(REPO_ROOT / "state" / "ea.db"))
        report.add(FAIL if reason else OK, "not cloud-synced",
                   f"{reason}. MOVE THE REPO to the root of C: before anything else" if reason else "the register is outside every sync root")
    except Exception as exc:  # noqa: BLE001
        report.add(FAIL, "not cloud-synced", f"could not run the check: {exc}")  # swallow: reported
    import _gate  # noqa: PLC0415

    marker = _gate.BUILD_MARKER.exists()
    report.add(WARN if marker else OK, "build-machine marker",
               ("present: this machine may edit code and permissions; correct ONLY on Mike's build machine"
                if marker else "absent: code and permissions are locked (correct for Taylor's machine)"))


def check_database(report: Report) -> None:
    try:
        import ea_db  # noqa: PLC0415

        conn = ea_db.connect()
        ea_db.migrate(conn)
    except Exception as exc:  # noqa: BLE001
        report.add(FAIL, "register", f"cannot open or migrate: {exc}")  # swallow: reported
        return
    try:
        report.add(OK, "register", f"{ea_db.DB_PATH} schema v{ea_db.user_version(conn)}")
        bad = ea_db.people_column_violations(conn)
        report.add(FAIL if bad else OK, "people columns", f"unapproved: {bad}" if bad else "work identity only")
        counts = ea_db.table_counts(conn)
        missing = [n for n, c in counts.items() if c < 0]
        report.add(FAIL if missing else OK, "tables", f"absent: {missing}" if missing else
                   ", ".join(f"{k}={counts[k]}" for k in ("people", "docs", "meetings", "actions", "topics", "needs_input")))
        people = conn.execute("SELECT COUNT(*) FROM people WHERE one_on_one = 1").fetchone()[0]
        report.add(OK if people == 6 else WARN, "1:1 roster", f"{people} people with a 1:1 (expected 6; register.py seed --roster)")
        docs = conn.execute("SELECT COUNT(*) FROM docs WHERE fixture = 0 AND role = 'running_1on1'").fetchone()[0]
        confirmed = conn.execute("SELECT COUNT(*) FROM docs WHERE fixture = 0 AND role = 'running_1on1' AND map_confirmed = 1").fetchone()[0]
        report.add(OK if docs == 6 and confirmed == 6 else WARN, "running Docs linked",
                   f"{docs} of 6 linked, {confirmed} maps confirmed with Taylor")
        series = conn.execute("SELECT COUNT(*) FROM meetings WHERE source = 'calendar'").fetchone()[0]
        report.add(OK if series == 6 else WARN, "Calendar series linked", f"{series} of 6")
        import _health  # noqa: PLC0415

        hours = _health.tick_age_hours(str(ea_db.DB_PATH)) if not ea_db.fixture_mode() else None
        report.add(OK if _health.healthy(hours) else (WARN if hours is None else FAIL), "last tick",
                   _health.render_age(hours))
    finally:
        conn.close()


def check_audit_and_deviations(report: Report) -> None:
    import _audit  # noqa: PLC0415

    reason = _audit.degraded_reason()
    report.add(FAIL if reason else OK, "audit log", f"DEGRADED: {reason[:100]}" if reason else "recording")
    import docs_edit  # noqa: PLC0415

    approved, why = docs_edit.live_writes_approved(docs_edit.load_deviations())
    report.add(OK if approved else WARN, "live Doc writes", "approved (D-1)" if approved else f"OFF: {why}")


def check_google(report: Report, offline: bool) -> None:
    import google_creds  # noqa: PLC0415

    for path, label in ((google_creds.CLIENT_PATH, "OAuth client"), (google_creds.TOKEN_PATH, "OAuth token")):
        report.add(OK if path.exists() else FAIL, label, str(path) if path.exists() else f"missing at {path}")
    try:
        granted = google_creds.granted_scopes()
    except google_creds.CredentialsError as exc:
        report.add(FAIL, "token scopes", str(exc))
        return
    for scope in google_creds.PHASE1_SCOPES:
        report.add(OK if scope in granted else FAIL, f"scope {scope.rsplit('/', 1)[-1]}",
                   "granted" if scope in granted else "NOT granted: python scripts/google_auth.py")
    if offline:
        report.add(WARN, "network checks", "skipped (--offline): refresh, Docs and Calendar were NOT checked")
        return
    try:
        google_creds.load_credentials([google_creds.DOCUMENTS])
        report.add(OK, "token refresh", "documents scope refreshes")
    except google_creds.CredentialsError as exc:
        report.add(FAIL, "token refresh", str(exc))
        return
    import docs_read  # noqa: PLC0415
    import ea_db  # noqa: PLC0415

    conn = ea_db.connect()
    try:
        docs = conn.execute("SELECT doc_id, title FROM docs WHERE fixture = ? AND role = 'running_1on1'",
                            (1 if ea_db.fixture_mode() else 0,)).fetchall()
    finally:
        conn.close()
    if not docs:
        report.add(WARN, "Docs API", "no running Doc registered, so no Doc was read")
    else:
        service = docs_read.docs_service()
        for row in docs:
            try:
                document = docs_read.fetch(service, row["doc_id"])
                editable = bool(document.get("revisionId"))
                report.add(OK if editable else FAIL, f"Doc {row['title'][:28]}",
                           "readable and editable" if editable else "readable but NOT editable by this account")
            except docs_read.DocReadError as exc:
                report.add(FAIL, f"Doc {row['title'][:28]}", str(exc))
    if google_creds.CALENDAR_READONLY not in granted:
        report.add(FAIL, "Calendar API", "not checked: the token has no calendar.readonly")
        return
    try:
        cal = google_creds.service("calendar", "v3", [google_creds.CALENDAR_READONLY])
        cal.events().list(calendarId="primary", maxResults=1).execute()
        report.add(OK, "Calendar API", "primary calendar readable")
    except Exception as exc:  # noqa: BLE001
        report.add(FAIL, "Calendar API", f"{exc.__class__.__name__}: {str(exc)[:120]} (API disabled on the project?)")  # swallow: reported


def check_task(report: Report) -> None:
    if os.name != "nt":
        report.add(WARN, "scheduled task", "not Windows; not checked")
        return
    code, out = _run(["powershell", "-NoProfile", "-Command",
                      "$t = Get-ScheduledTask -TaskName 'EA-Tick' -ErrorAction SilentlyContinue; "
                      "if ($t) { '{0}|{1}|{2}' -f $t.State, $t.Settings.DisallowStartIfOnBatteries, $t.Settings.StopIfGoingOnBatteries }"], 60)
    if code != 0 or not out:
        report.add(WARN, "scheduled task", "EA-Tick is not registered (scripts/schedule_ea_tick.ps1 -RunNow)")
        return
    state, disallow, stop = (out.splitlines()[-1].split("|") + ["", "", ""])[:3]
    battery_ok = disallow.strip().lower() == "false" and stop.strip().lower() == "false"
    report.add(OK if battery_ok else FAIL, "scheduled task",
               f"EA-Tick {state}; " + ("runs on battery" if battery_ok else "WILL NOT RUN ON BATTERY: re-register"))


def check_validators(report: Report) -> None:
    for argv, name in (([sys.executable, "scripts/validate_guardrails.py", "--self-test"], "guardrail self-test"),
                       ([sys.executable, "scripts/validate_agent_contracts.py"], "agent contracts"),
                       ([sys.executable, "scripts/register.py", "--self-test"], "register self-test"),
                       ([sys.executable, "scripts/check_vendored.py"], "vendored files")):
        code, out = _run(argv)
        last = out.splitlines()[-1] if out else f"exit {code}"
        report.add(OK if code == 0 else (WARN if name == "vendored files" else FAIL), name, last[:110])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    import ea_db  # noqa: PLC0415

    ea_db.console_utf8()
    print(f"EA doctor: {REPO_ROOT}")
    print(f"  {platform.platform()}\n")
    report = Report()
    for step in (check_prerequisites, check_location, check_database, check_audit_and_deviations):
        try:
            step(report)
        except Exception as exc:  # noqa: BLE001
            report.add(FAIL, step.__name__, f"the check itself crashed: {exc.__class__.__name__}: {exc}")  # swallow: reported
    try:
        check_google(report, args.offline)
    except Exception as exc:  # noqa: BLE001
        report.add(FAIL, "google", f"the check itself crashed: {exc.__class__.__name__}: {exc}")  # swallow: reported
    check_task(report)
    check_validators(report)
    print(report.render())
    worst = report.worst()
    print()
    if worst == FAIL:
        print("FAIL: something is broken. Paste this whole output to Mike.")
        return 1
    if worst == WARN:
        print("WARN: nothing is broken, but some things are not set up yet.")
        return 0
    print("OK: everything this machine can check is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
