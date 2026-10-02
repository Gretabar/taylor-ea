"""statusLine: this turn's dispatch state and the scheduler's pulse, always on screen.

PORTED FROM PIPER's statusline-piper.py. The label comes from context/identity.json
(the display name lives only there), the tick read and its rendering come from
_health.py so this bar and the roll call's fallback line cannot disagree, and the
tick job is ea_tick.

    NAME  ticks OK (2h ago)   REED>PAGE>WREN (3)     green
    NAME  ticks OK (2h ago)   WREN running           green   (its result is not written yet)
    NAME  ticks OK (2h ago)   read only              dim     (/owe, /morning)
    NAME  ticks OK (2h ago)   -- SOLO --             yellow  (no dispatch, and it wrote)
    NAME  LAST TICK 6 DAYS AGO                       red
    ...   BUILD MODE until Thu 18:30 (3h 10m left)   bold magenta, after the rest, while
                                                     state/BUILD_MODE is unexpired

WHETHER THE VS CODE EXTENSION RENDERS THIS IS UNVERIFIED. team-rollcall.py carries
the tick line too, as the fallback.

Two constraints, both inherited: it must AGREE with the roll call (both take the
turn's verdict from _activity.py, which reads _transcript.py), and it runs on
essentially every repaint (300ms debounce, an in-flight script is cancelled), so the
verdict is cached on (path, size, mtime_ns) and the warm path imports neither. The
local imports inside the uncached helpers are the optimisation; do not hoist them.

The output contract is narrow and absolute: exactly one line, never a traceback,
always exit 0.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _health  # noqa: E402

MAX_SHOWN = 3

GREEN = "\033[32m"
MAGENTA = "\033[1;35m"
RED = "\033[1;31m"
BRIGHT_YELLOW = "\033[1;33m"
DIM = "\033[2m"
RESET = "\033[0m"

CACHE_FORMAT = 3  # 3: dispatches need positive evidence, and "pending" exists


def _color_enabled() -> bool:
    """Honour the standard opt-outs. Deliberately not an isatty test: stdout is a pipe."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return os.environ.get("CLICOLOR") != "0"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def _stamp(path: str) -> list[int]:
    try:
        st = os.stat(path)
    except OSError:
        return [-1, -1]  # swallow: forces a recompute, which fails into the honest unknown
    return [st.st_size, st.st_mtime_ns]


def _db_stamp() -> list[int]:
    """Covers the database and its WAL: under WAL a committed tick lands in -wal first."""
    path = _health.db_path()
    return _stamp(path) + _stamp(path + "-wal")


def _cache_file(transcript_path: str) -> str:
    root = os.environ.get("TEMP") or os.environ.get("TMP") or os.environ.get("TMPDIR") or HERE
    stem = "".join(c if c.isalnum() else "-" for c in os.path.basename(transcript_path))
    return os.path.join(root, f"ea-statusline-{stem[-80:]}.json")


def _read_cache(path: str, key: dict) -> dict | None:
    """The cached entry for exactly this state, or None. None never means "solo"."""
    try:
        with open(path, "rb") as fh:
            entry = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        return None  # swallow: a missing or half-written cache just means recompute
    if not isinstance(entry, dict) or entry.get("fmt") != CACHE_FORMAT:
        return None
    for field, value in key.items():
        if entry.get(field) != value:
            return None
    return entry


def _write_cache(path: str, entry: dict) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(json.dumps(entry).encode("utf-8"))
        os.replace(tmp, path)
    except OSError:
        # swallow: an unwritable cache costs speed on the next repaint, never correctness
        try:
            os.unlink(tmp)
        except OSError:
            pass  # swallow: nothing to clean up if the temp file never landed


def _verdict_uncached(transcript_path: str) -> tuple[str, list[str]]:
    from _activity import verdict_for

    verdict = verdict_for(transcript_path)
    return verdict.kind, list(verdict.names)


def render(label: str, kind: str | None, names: list[str], hours: float | None, color: bool,
           build: str = "") -> str:
    """One line. `kind` is an _activity verdict; anything else renders as unknown.

    The kinds are spelled out rather than imported so the warm path imports nothing;
    the guardrail self-test renders every outcome and goes red if the two drift.
    `build` is _health.build_mode_text(): while build mode is on it closes the line, loudly.
    """
    suffix = ("  " + _paint(build, MAGENTA, color)) if build else ""
    tick = _health.render_age(hours)
    if not _health.healthy(hours):
        # The unhealthy bar carries the tick, and build mode if it is on, and nothing else.
        return _paint(f"{label}  {tick}", RED, color) + suffix
    if kind == "dispatched" and names:
        chain = ">".join(names[-MAX_SHOWN:])
        if len(names) > MAX_SHOWN:
            chain = f"+{len(names) - MAX_SHOWN}>{chain}"
        team, team_color = f"{chain}  ({len(names)})", GREEN
    elif kind == "pending" and names:
        # An agent whose result is not written yet. Not counted as dispatched until it is.
        team, team_color = f"{'>'.join(names[-MAX_SHOWN:])} running", GREEN
    elif kind == "wrote":
        team, team_color = "-- SOLO --", BRIGHT_YELLOW
    elif kind == "read_only":
        team, team_color = "read only", DIM
    else:
        team, team_color = "team ?", DIM
    return _paint(f"{label}  {tick}", GREEN, color) + "  " + _paint(team, team_color, color) + suffix


def status(color: bool) -> str:
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
    transcript_path = payload.get("transcript_path") or ""
    label = _health.system_label()
    build = _health.build_mode_text(_health.build_mode())  # never cached: it can change between repaints

    db_stamp = _db_stamp()
    if not transcript_path or _stamp(transcript_path) == [-1, -1]:
        return render(label, None, [], _health.tick_age_hours(), color, build)

    transcript_stamp = _stamp(transcript_path)
    cache_path = _cache_file(transcript_path)
    key = {
        "detector": _stamp(os.path.join(HERE, "_transcript.py")) + _stamp(os.path.join(HERE, "_activity.py")),
        "transcript": transcript_stamp,
        "db": db_stamp,
    }
    entry = _read_cache(cache_path, key)
    if entry is not None:
        names = entry.get("names")
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            return render(label, None, [], entry.get("tick_hours"), color, build)
        return render(label, entry.get("kind"), names, entry.get("tick_hours"), color, build)

    kind, names = _verdict_uncached(transcript_path)
    hours = _health.tick_age_hours()
    if _stamp(transcript_path) == transcript_stamp and _db_stamp() == db_stamp:
        _write_cache(cache_path, {"fmt": CACHE_FORMAT, **key, "kind": kind, "names": names, "tick_hours": hours})
    return render(label, kind, names, hours, color, build)


def main() -> int:
    color = _color_enabled()
    try:
        line = status(color)
    except Exception:
        # swallow: the status bar degrades to a marker, never to a traceback
        line = _paint("EA  ?", DIM, color)
    try:
        flat = line.replace("\r", " ").replace("\n", " ")
        sys.stdout.buffer.write((flat + "\n").encode("utf-8"))
        sys.stdout.flush()
    except Exception:
        return 0  # swallow: a closed stdout is not worth a non-zero exit from a status line
    return 0


if __name__ == "__main__":
    sys.exit(main())
