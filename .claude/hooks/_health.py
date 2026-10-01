"""Tick health and the display label, shared by statusline-ea.py and team-rollcall.py.

NEW in this repo. PIPER computed tick age inside the status line only. Here the
roll call carries the same line as a fallback, because whether the VS Code
extension renders a custom statusLine is unverified, and a liveness signal that
silently does not render is the eleven-week QueueSweep failure again. Two copies
of the age calculation would be two answers to "is it alive", so it lives here.

Standard library only and nothing heavy at import: the status line imports this on
every repaint that misses its cache.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.environ.get("EA_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(HERE))

TICK_JOB = "ea_tick"
TICK_OK_HOURS = 26  # a daily job, a night's sleep, an hour of slack


def db_path() -> str:
    """The LIVE register. Fixture runs never count as liveness."""
    return os.environ.get("EA_DB") or os.path.join(REPO_ROOT, "state", "ea.db")


def system_label() -> str:
    """The display name from context/identity.json, or the codename when unreadable."""
    try:
        with open(os.path.join(REPO_ROOT, "context", "identity.json"), "rb") as fh:
            name = json.loads(fh.read().decode("utf-8")).get("system_name")
        return str(name).strip() or "EA"
    except (OSError, ValueError, AttributeError):
        return "EA"  # swallow: the label is cosmetic; the codename is a true name


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
        conn = sqlite3.connect(f"file:{target.replace(os.sep, '/')}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
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
