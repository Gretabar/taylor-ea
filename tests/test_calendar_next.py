"""calendar_next.py against recorded events.instances shapes. No network.

The live Calendar leg is Blocked (no calendar.readonly on the build token), so
these are the evidence that the cadence and next-meeting logic is right on the
shapes the API returns: confirmed and cancelled instances, dateTime with an offset,
"Z" UTC times, all-day dates, a DST change, and an empty series.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import calendar_next as cn  # noqa: E402
import ea_db  # noqa: E402

TZ = "America/Toronto"
TORONTO = ZoneInfo(TZ)
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)  # Thursday 2026-10-01, 08:00 Toronto


def series(first: datetime, every, count: int, cancelled=()) -> dict:
    return cn.synthetic_instances(first, every, count, series_id="abc123", cancelled=cancelled)


class Cadence(unittest.TestCase):
    def test_weekly(self):
        r = cn.next_meeting(series(datetime(2026, 10, 7, 10, tzinfo=TORONTO), 7, 6), NOW, TZ)
        self.assertEqual(r["cadence_observed"], "weekly")
        self.assertTrue(r["next_at"].startswith("2026-10-07T10:00"))

    def test_biweekly_is_two_weeks_out(self):
        # The P1.6 fixture shape: last meeting Wed 2026-09-30, next Wed 2026-10-14.
        r = cn.next_meeting(series(datetime(2026, 10, 14, 10, tzinfo=TORONTO), 14, 6), NOW, TZ)
        self.assertEqual(r["cadence_observed"], "biweekly")
        self.assertTrue(r["next_at"].startswith("2026-10-14T10:00"))

    def test_monthly(self):
        r = cn.next_meeting(series(datetime(2026, 10, 21, 10, tzinfo=TORONTO), "monthly", 6), NOW, TZ)
        self.assertEqual(r["cadence_observed"], "monthly")
        self.assertTrue(r["next_at"].startswith("2026-10-21"))

    def test_cancelled_week_does_not_make_weekly_look_biweekly(self):
        # showDeleted=True returns the cancelled instance; it still counts for cadence.
        r = cn.next_meeting(series(datetime(2026, 10, 7, 10, tzinfo=TORONTO), 7, 6, cancelled=(2,)), NOW, TZ)
        self.assertEqual(r["cadence_observed"], "weekly")

    def test_cancelled_next_meeting_is_skipped_not_reported(self):
        r = cn.next_meeting(series(datetime(2026, 10, 7, 10, tzinfo=TORONTO), 7, 6, cancelled=(0,)), NOW, TZ)
        self.assertTrue(r["next_at"].startswith("2026-10-14"))
        self.assertEqual(r["cancelled_skipped"], 1)

    def test_weekly_across_the_dst_change(self):
        # Toronto leaves DST on 2026-11-01; 10:00 local stays a 7-day gap in local dates.
        r = cn.next_meeting(series(datetime(2026, 10, 22, 10, tzinfo=TORONTO), 7, 4), NOW, TZ)
        self.assertEqual(r["cadence_observed"], "weekly")

    def test_empty_series_invents_nothing(self):
        r = cn.next_meeting({"kind": "calendar#events", "items": []}, NOW, TZ)
        self.assertIsNone(r["next_at"])
        self.assertIsNone(r["next_event_id"])
        self.assertIn("nothing was invented", r["note"])

    def test_all_cancelled_invents_nothing(self):
        r = cn.next_meeting(series(datetime(2026, 10, 7, 10, tzinfo=TORONTO), 7, 3, cancelled=(0, 1, 2)), NOW, TZ)
        self.assertIsNone(r["next_at"])

    def test_single_instance_cadence_unknown(self):
        r = cn.next_meeting(series(datetime(2026, 10, 7, 10, tzinfo=TORONTO), 7, 1), NOW, TZ)
        self.assertEqual(r["cadence_observed"], "unknown")

    def test_irregular(self):
        items = {"items": [
            {"id": "a", "status": "confirmed", "start": {"dateTime": "2026-10-05T10:00:00-04:00"}},
            {"id": "b", "status": "confirmed", "start": {"dateTime": "2026-10-08T10:00:00-04:00"}},
            {"id": "c", "status": "confirmed", "start": {"dateTime": "2026-10-18T10:00:00-04:00"}},
        ]}
        self.assertEqual(cn.next_meeting(items, NOW, TZ)["cadence_observed"], "irregular")

    def test_utc_z_and_all_day_shapes_parse(self):
        items = {"items": [
            {"id": "z", "status": "confirmed", "start": {"dateTime": "2026-10-07T14:00:00Z"}},
            {"id": "d", "status": "confirmed", "start": {"date": "2026-10-14"}},
        ]}
        parsed = cn.parse_instances(items, TZ)
        self.assertEqual([p["id"] for p in parsed], ["z", "d"])
        self.assertEqual(parsed[0]["start"].astimezone(TORONTO).hour, 10)

    def test_past_instances_are_not_next(self):
        items = series(datetime(2026, 9, 23, 10, tzinfo=TORONTO), 7, 4)
        r = cn.next_meeting(items, NOW, TZ)
        self.assertTrue(r["next_at"].startswith("2026-10-07"))


class FakeService:
    """Stands in for googleapiclient's calendar service: records calls, returns a canned response."""

    def __init__(self, response: dict):
        self.response, self.calls = response, []

    def events(self):
        return self

    def instances(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def execute(self):
        return self.response


class Refresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = ea_db.connect(Path(self.tmp.name) / "cal.db")
        ea_db.migrate(self.conn)
        now = ea_db.now_iso()
        self.conn.execute("INSERT INTO people (key, full_name, one_on_one, updated_at) VALUES ('casey','Casey',1,?)", (now,))
        pid = self.conn.execute("SELECT id FROM people WHERE key='casey'").fetchone()[0]
        self.conn.execute("INSERT INTO meetings (person_id, kind, calendar_id, series_event_id, timezone, source)"
                          " VALUES (?, '1on1', 'primary', 'abc123', ?, 'calendar')", (pid, TZ))
        self.conn.execute("INSERT INTO meetings (person_id, kind, calendar_id, series_event_id, timezone, source, fixture)"
                          " VALUES (?, '1on1', 'fixture', 'fx', ?, 'fixture', 1)", (pid, TZ))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_refresh_updates_the_linked_series_and_reads_with_show_deleted(self):
        service = FakeService(series(datetime(2026, 10, 14, 10, tzinfo=TORONTO), 14, 6))
        results = cn.refresh(self.conn, now=NOW, service=service)
        self.assertEqual(len(results), 1)
        self.assertEqual(service.calls[0]["showDeleted"], True)
        self.assertEqual(service.calls[0]["eventId"], "abc123")
        row = self.conn.execute("SELECT * FROM meetings WHERE source='calendar'").fetchone()
        self.assertEqual(row["cadence_observed"], "biweekly")
        self.assertTrue(row["next_at"].startswith("2026-10-14"))

    def test_refresh_never_touches_fixture_meetings(self):
        cn.refresh(self.conn, now=NOW, service=FakeService(series(datetime(2026, 10, 7, 10, tzinfo=TORONTO), 7, 3)))
        fixture = self.conn.execute("SELECT * FROM meetings WHERE source='fixture'").fetchone()
        self.assertIsNone(fixture["refreshed_at"])

    def test_no_linked_series_makes_no_call(self):
        self.conn.execute("DELETE FROM meetings WHERE source='calendar'")
        self.conn.commit()
        self.assertEqual(cn.refresh(self.conn, now=NOW, service=None), [])

    def test_a_meeting_row_is_never_created_by_refresh(self):
        before = self.conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
        cn.refresh(self.conn, now=NOW, service=FakeService({"items": []}))
        self.assertEqual(before, self.conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
