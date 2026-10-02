"""Tick health, the display label and build mode, shared by statusline-ea.py and team-rollcall.py.

NEW in this repo. The roll call carries the status line's tick line as a fallback,
because whether the VS Code extension renders a custom statusLine is unverified,
and a liveness signal that silently does not render is how a dead scheduled job
goes unnoticed for weeks. Two copies of the age calculation would be two answers to
"is it alive", so it lives here.

BUILD MODE lives here for the same reason: the gates (through _gate.is_build_machine),
the status line, the roll call and the doctor must agree on whether this machine may
change code right now. Two markers, both created outside Claude Code and both refused as
a write target by protect-architecture.py:

  state/BUILD_MACHINE   first line this host's name. Permanent: Mike's own build machine.
  state/BUILD_MODE      first line this host's name, second line an expiry (ISO 8601, UTC),
                        written by scripts/build_mode.ps1 from a terminal on Taylor's laptop.
                        An expired marker, one naming another host, or one whose expiry is
                        more than 24 hours ahead (build_mode.ps1 never writes that) is OFF.

Standard library only and nothing heavy at import: the status line imports this on
every repaint that misses its cache.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.environ.get("EA_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(HERE))

TICK_JOB = "ea_tick"
TICK_OK_HOURS = 26  # a daily job, a night's sleep, an hour of slack


def db_path() -> str:
    """The LIVE register. Fixture runs never count as liveness."""
    return os.environ.get("EA_DB") or os.path.join(REPO_ROOT, "state", "ea.db")


def read_only_uri(path: str) -> str:
    """mode=ro, with the path percent-encoded by Path.as_uri(). Pasted into an f-string, a '#'
    in a folder name starts the URI's fragment and SQLite opens a shorter path read-write."""
    return Path(path).resolve().as_uri() + "?mode=ro"


def system_label() -> str:
    """The display name: Taylor's (state/taylor/identity.json), else context/identity.json, else the codename."""
    try:
        scripts = os.path.join(REPO_ROOT, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import overlay  # noqa: PLC0415

        name = overlay.identity(REPO_ROOT).get("system_name")
        return str(name).strip() or "EA"
    except Exception:  # noqa: BLE001
        return "EA"  # swallow: the label is cosmetic; the codename is a true name


MAX_BUILD_HOURS = 24


@dataclass(frozen=True)
class BuildMode:
    """Whether this machine may change code right now, and why. `until` is None on the build machine."""

    on: bool
    source: str = ""  # "machine" (state/BUILD_MACHINE) or "timed" (state/BUILD_MODE)
    until: datetime | None = None
    note: str = ""  # why a marker that exists does not count


def _marker_lines(name: str) -> list[str] | None:
    try:
        with open(os.path.join(REPO_ROOT, "state", name), "rb") as fh:
            return [line.strip() for line in fh.read().decode("utf-8", errors="replace").splitlines() if line.strip()]
    except OSError:
        return None


def build_mode(now: datetime | None = None) -> BuildMode:
    """Build mode as both markers say it is. Anything doubtful is OFF: the safe side of a code lock."""
    host = socket.gethostname().strip().lower()
    machine = _marker_lines("BUILD_MACHINE")
    if machine and machine[0].lower() == host:
        return BuildMode(True, "machine")
    timed = _marker_lines("BUILD_MODE")
    if timed is None:
        return BuildMode(False, note="state/BUILD_MACHINE names another host" if machine else "")
    if not timed or timed[0].lower() != host:
        return BuildMode(False, note="state/BUILD_MODE names another machine")
    try:
        until = datetime.fromisoformat(timed[1].replace("Z", "+00:00")) if len(timed) > 1 else None
    except ValueError:
        until = None
    if until is None or until.tzinfo is None:
        return BuildMode(False, note="state/BUILD_MODE has no readable expiry")
    now = now or datetime.now(timezone.utc)
    if until <= now:
        return BuildMode(False, "timed", until, f"expired {until.astimezone():%a %Y-%m-%d %H:%M}")
    if until > now + timedelta(hours=MAX_BUILD_HOURS, minutes=5):
        return BuildMode(False, "timed", until, f"expiry more than {MAX_BUILD_HOURS} hours ahead, "
                                                "which build_mode.ps1 never writes")
    return BuildMode(True, "timed", until)


def build_mode_text(mode: BuildMode, now: datetime | None = None) -> str:
    """One line for the status line and the doctor: empty when off."""
    if not mode.on:
        return ""
    if mode.source == "machine":
        return "BUILD MACHINE"
    left = mode.until - (now or datetime.now(timezone.utc))
    hours, minutes = int(left.total_seconds() // 3600), int(left.total_seconds() % 3600 // 60)
    return f"BUILD MODE until {mode.until.astimezone():%a %H:%M} ({hours}h {minutes:02d}m left)"


def tick_age_hours(path: str | None = None) -> float | None:
    """Hours since the newest successful tick, or None when unknown.

    Read-only URI connection so a repaint never takes a write lock. `immutable` is
    deliberately NOT used: it would make SQLite ignore the WAL, and the newest tick
    is exactly the row that lives there.
    """
    target = path or db_path()
    if not os.path.exists(target):
        return None
    try:
        conn = sqlite3.connect(read_only_uri(target), uri=True, timeout=1.0)
    except (sqlite3.Error, OSError, ValueError):
        return None  # swallow: unknown, and rendered as unknown rather than healthy
    try:
        row = conn.execute(
            "SELECT ts FROM job_ticks WHERE job = ? AND status = 'ok' ORDER BY ts DESC LIMIT 1",
            (TICK_JOB,),
        ).fetchone()
    except sqlite3.Error:
        return None  # swallow: table absent or locked; unknown
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    try:
        stamp = datetime.fromisoformat(str(row[0]))
    except ValueError:
        return None  # swallow: a stamp we cannot parse is not evidence the job ran
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0


def healthy(hours: float | None) -> bool:
    return hours is not None and hours <= TICK_OK_HOURS


def render_age(hours: float | None) -> str:
    """Short when healthy, shouted when not."""
    if hours is None:
        return "NO TICK RECORDED"
    if hours < 1:
        return "ticks OK (<1h ago)"
    if hours <= TICK_OK_HOURS:
        return f"ticks OK ({int(round(hours))}h ago)"
    days = int(hours // 24)
    if days < 1:
        return f"LAST TICK {int(round(hours))} HOURS AGO"
    return f"LAST TICK {days} DAY{'S' if days != 1 else ''} AGO"
