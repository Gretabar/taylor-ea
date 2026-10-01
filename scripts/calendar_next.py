"""The next real 1:1 and the cadence the Calendar actually shows. READ ONLY.

NEW in this repo. Blueprint s.3: "Weekly, biweekly and monthly recurrence are data,
not hard-coded assumptions", and P1.6: a topic for a biweekly or monthly person
must land against "the actual next meeting and tailored document ... rather than a
newly invented weekly meeting". Blueprint s.11 lets Phase 1 READ Calendar for the
next meeting without enabling Phase 7 scheduling. Nothing in this file creates,
moves or cancels an event, and the scope it asks for is calendar.readonly.

HOW CADENCE IS OBSERVED. events.instances on the series, from now, with
showDeleted=True so a CANCELLED week still comes back (marked cancelled) instead of
silently vanishing. Without it, a weekly series with one cancelled week shows a
14-day gap and reads as biweekly. The cadence is a two-thirds vote over the gaps in
local calendar days, cancelled instances included; next_at is the first instance
that is NOT cancelled. Gaps are counted in local dates, so a DST change does not
turn 7 days into 6.99.

NEVER INVENTED. No upcoming instance means next_at stays NULL with a note saying
so. A person with no linked series has no meeting row at all, and a topic for them
is still placed in their Doc's upcoming block, which is where Taylor looks.

LIVE CALENDAR IS NOT PROVEN YET. The token on Mike's machine has no calendar scope.
Everything below is unit-tested against recorded events.instances shapes
(tests/test_calendar_next.py); the live leg is Blocked until a consent with
calendar.readonly (google_auth.py) and the Calendar API enabled on the project.

Usage:
    python scripts/calendar_next.py --status
    python scripts/calendar_next.py --refresh [--person kaed]
    python scripts/calendar_next.py --discover [--days 45]
    python scripts/calendar_next.py --link-series <eventId> --person kaed [--calendar primary]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ea_db  # noqa: E402

INSTANCES_WANTED = 6


class CalendarError(RuntimeError):
    """The Calendar could not be read (scope, API disabled, network, not found)."""


# ---------------------------------------------------------------------------
# pure functions (unit-tested)
# ---------------------------------------------------------------------------

def _zone(name: str):
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    return ZoneInfo(name)


def event_start(event: dict, tz_name: str) -> datetime | None:
    """An instance's start as an aware datetime. All-day events start at local midnight."""
    start = event.get("start") or {}
    if start.get("dateTime"):
        value = start["dateTime"].replace("Z", "+00:00")
        moment = datetime.fromisoformat(value)
        return moment if moment.tzinfo else moment.replace(tzinfo=_zone(start.get("timeZone") or tz_name))
    if start.get("date"):
        return datetime.combine(date.fromisoformat(start["date"]), time(0), tzinfo=_zone(tz_name))
    return None


def parse_instances(response: dict, tz_name: str) -> list[dict]:
    """[{id, start, cancelled}] sorted by start. Instances with no start are dropped."""
    out = []
    for event in response.get("items") or []:
        moment = event_start(event, tz_name)
        if moment is None:
            continue
        out.append({"id": event.get("id"), "start": moment,
                    "cancelled": event.get("status") == "cancelled"})
    return sorted(out, key=lambda e: e["start"])


def _gap_class(days: int) -> str | None:
    if 6 <= days <= 8:
        return "weekly"
    if 13 <= days <= 15:
        return "biweekly"
    if 27 <= days <= 35:
        return "monthly"
    return None


def observe_cadence(starts: list[datetime], tz_name: str) -> str:
    """weekly | biweekly | monthly | irregular | unknown, by a two-thirds vote of the gaps.

    Not a median: the median of two gaps is their average, and gaps of 3 and 10
    days would average to "weekly". Each local-date gap is classified on its own,
    and a class must cover at least two thirds of them, which still tolerates one
    outlier (an extra week off) in a longer run.
    """
    if len(starts) < 2:
        return "unknown"
    tz = _zone(tz_name)
    days = [s.astimezone(tz).date() for s in starts]
    gaps = [(b - a).days for a, b in zip(days, days[1:]) if (b - a).days > 0]
    if not gaps:
        return "unknown"
    classes = [c for c in (_gap_class(g) for g in gaps) if c]
    if not classes:
        return "irregular"
    best = max(set(classes), key=classes.count)
    return best if classes.count(best) * 3 >= len(gaps) * 2 else "irregular"


def next_meeting(response: dict, now: datetime, tz_name: str) -> dict:
    """The first upcoming non-cancelled instance, and the cadence the series shows."""
    instances = parse_instances(response, tz_name)
    upcoming = [i for i in instances if i["start"] >= now]
    live = [i for i in upcoming if not i["cancelled"]]
    result = {
        "cadence_observed": observe_cadence([i["start"] for i in instances], tz_name),
        "instances_seen": len(instances),
        "cancelled_skipped": sum(1 for i in upcoming if i["cancelled"] and (not live or i["start"] < live[0]["start"])),
        "next_event_id": live[0]["id"] if live else None,
        "next_at": live[0]["start"].isoformat() if live else None,
        "note": "" if live else "no upcoming instance in the series; nothing was invented",
    }
    return result


def synthetic_instances(first_start: datetime, every: int | str, count: int, *,
                        series_id: str = "fixture", cancelled: tuple[int, ...] = ()) -> dict:
    """An events.instances-shaped response, for tests and the fixture meetings.

    `every` is a number of days, or "monthly" (same day of month). The shape mirrors
    the API: items[] with id, status, recurringEventId, start.dateTime + timeZone.
    """
    tz = first_start.tzinfo
    items = []
    for n in range(count):
        if every == "monthly":
            month = first_start.month - 1 + n
            moment = first_start.replace(year=first_start.year + month // 12, month=month % 12 + 1)
        else:
            moment = first_start + timedelta(days=int(every) * n)
        moment = moment.replace(tzinfo=tz)
        stamp = moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        items.append({
            "kind": "calendar#event", "id": f"{series_id}_{stamp}",
            "status": "cancelled" if n in cancelled else "confirmed",
            "recurringEventId": series_id,
            "start": {"dateTime": moment.isoformat(), "timeZone": str(tz)},
            "originalStartTime": {"dateTime": moment.isoformat(), "timeZone": str(tz)},
        })
    return {"kind": "calendar#events", "items": items}


# ---------------------------------------------------------------------------
# live calendar
# ---------------------------------------------------------------------------

def calendar_service():
    import google_creds  # noqa: PLC0415

    try:
        return google_creds.service("calendar", "v3", [google_creds.CALENDAR_READONLY])
    except google_creds.CredentialsError as exc:
        raise CalendarError(str(exc)) from exc


def fetch_instances(service, calendar_id: str, series_id: str, now: datetime) -> dict:
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    try:
        return service.events().instances(
            calendarId=calendar_id, eventId=series_id, timeMin=now.isoformat(),
            maxResults=INSTANCES_WANTED, showDeleted=True).execute()
    except HttpError as exc:
        status = int(getattr(exc.resp, "status", 0) or 0)
        hint = {403: "forbidden: the Calendar API may be disabled on the project, or the scope is missing",
                404: "the series was not found on that calendar"}.get(status, "refused")
        raise CalendarError(f"events.instances {series_id}: HTTP {status}, {hint}") from exc


def apply(conn, meeting_id: int, result: dict, source_note: str = "") -> None:
    with conn:
        conn.execute(
            "UPDATE meetings SET next_event_id=?, next_at=?, cadence_observed=?, refreshed_at=?, note=? WHERE id=?",
            (result["next_event_id"], result["next_at"], result["cadence_observed"], ea_db.now_iso(),
             (result["note"] or source_note or None), meeting_id))


def refresh(conn, *, person_key: str | None = None, now: datetime | None = None,
            service=None) -> list[dict]:
    """Refresh next_at and cadence for every linked LIVE series. Fixture meetings are skipped."""
    import register  # noqa: PLC0415

    tz_name = register.identity().get("timezone") or "America/Toronto"
    moment = now or datetime.now(timezone.utc)
    sql = ("SELECT m.*, p.key FROM meetings m JOIN people p ON p.id = m.person_id"
           " WHERE m.source = 'calendar' AND m.series_event_id IS NOT NULL")
    params: tuple = ()
    if person_key:
        sql += " AND p.key = ?"
        params = (person_key,)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []
    service = service or calendar_service()
    out = []
    for row in rows:
        response = fetch_instances(service, row["calendar_id"] or "primary", row["series_event_id"], moment)
        result = next_meeting(response, moment, row["timezone"] or tz_name)
        apply(conn, row["id"], result)
        out.append({"person": row["key"], **result})
    return out


def discover(service, conn, days: int, now: datetime) -> list[dict]:
    """Recurring events in the window, grouped by series, with a proposed person. Proposes only."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    try:
        response = service.events().list(
            calendarId="primary", timeMin=now.isoformat(), timeMax=(now + timedelta(days=days)).isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=250).execute()
    except HttpError as exc:
        raise CalendarError(f"events.list: HTTP {getattr(exc.resp, 'status', '?')}") from exc
    people = conn.execute("SELECT key, full_name, work_email FROM people WHERE one_on_one = 1").fetchall()
    series: dict[str, dict] = {}
    for event in response.get("items") or []:
        sid = event.get("recurringEventId")
        if not sid:
            continue
        entry = series.setdefault(sid, {"series_event_id": sid, "summary": event.get("summary", ""),
                                        "attendees": sorted({a.get("email", "") for a in event.get("attendees") or []}),
                                        "count": 0, "proposed_person": None, "matched_by": None})
        entry["count"] += 1
    for entry in series.values():
        for p in people:
            if p["work_email"] and p["work_email"].lower() in {a.lower() for a in entry["attendees"]}:
                entry["proposed_person"], entry["matched_by"] = p["key"], "attendee email"
                break
            first = (p["full_name"] or p["key"]).split()[0].casefold()
            if first and first in entry["summary"].casefold():
                entry["proposed_person"], entry["matched_by"] = p["key"], "title only, CONFIRM"
    return sorted(series.values(), key=lambda e: e["summary"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def status(conn) -> int:
    import google_creds  # noqa: PLC0415

    try:
        granted = google_creds.granted_scopes()
        scope = "granted" if google_creds.CALENDAR_READONLY in granted else "NOT GRANTED (consent needed)"
    except google_creds.CredentialsError as exc:
        scope = f"no token ({exc})"
    print(f"calendar.readonly: {scope}")
    rows = conn.execute("SELECT m.*, p.key FROM meetings m JOIN people p ON p.id = m.person_id ORDER BY p.key").fetchall()
    expected = conn.execute("SELECT COUNT(*) FROM people WHERE one_on_one = 1 AND active = 1").fetchone()[0]
    live = [r for r in rows if r["source"] == "calendar"]
    print(f"1:1 series linked from Calendar: {len(live)} of {expected}")
    for r in rows:
        print(f"  {'FIXTURE ' if r['fixture'] else ''}{r['key']:<7} cadence {r['cadence_observed'] or 'unknown':<10} "
              f"next {r['next_at'] or 'unknown'}  refreshed {r['refreshed_at'] or 'never'}  [{r['source']}]")
        if r["note"]:
            print(f"      {r['note']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--person")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--link-series")
    parser.add_argument("--calendar", default="primary")
    args = parser.parse_args()
    ea_db.console_utf8()

    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        if args.status:
            return status(conn)
        now = datetime.now(timezone.utc)
        if args.discover:
            for entry in discover(calendar_service(), conn, args.days, now):
                print(json.dumps(entry, ensure_ascii=False))
            return 0
        if args.link_series:
            if not args.person:
                parser.error("--link-series needs --person")
            row = conn.execute("SELECT id FROM people WHERE key = ?", (args.person.lower(),)).fetchone()
            if row is None:
                print(f"REFUSED: no person {args.person}", file=sys.stderr)
                return 1
            import register  # noqa: PLC0415

            tz_name = register.identity().get("timezone") or "America/Toronto"
            with conn:
                conn.execute("INSERT INTO meetings (person_id, kind, calendar_id, series_event_id, timezone, source)"
                             " VALUES (?, '1on1', ?, ?, ?, 'calendar')"
                             " ON CONFLICT(calendar_id, series_event_id) DO NOTHING",
                             (row["id"], args.calendar, args.link_series, tz_name))
            for result in refresh(conn, person_key=args.person.lower(), now=now):
                print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.refresh:
            results = refresh(conn, person_key=args.person, now=now)
            for result in results:
                print(json.dumps(result, ensure_ascii=False))
            if not results:
                print("no Calendar series linked; nothing to refresh")
            return 0
        parser.print_help()
        return 2
    except CalendarError as exc:
        print(f"CALENDAR UNAVAILABLE: {exc}", file=sys.stderr)
        return 3
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
