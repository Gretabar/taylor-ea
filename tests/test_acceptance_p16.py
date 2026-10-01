"""P1.6's expected next 1:1 comes from what was seeded, not from what the code under test stored.

The harness used to hardcode next_at 2026-10-14, true only for fixtures built on
2026-10-01, so a --rebuild on any other day (install day on Taylor's machine) would
have failed P1.6 with nothing wrong. The expectation is now the seeded series' last
instance plus two weeks, in the seed's zone. The two weeks are the test's own
definition: a series the code reads as weekly must still fail, and so must a stored
next_at that drifted from the seed, which a circular oracle would wave through.

Each case seeds Mark's series on a given day through make_fixtures.seed_meeting into
a throwaway fixtures.db, runs the real register.py add-topic against it, and lets the
real p16 judge. The Doc write and read are stubbed: P1.1 to P1.5 cover those. No network.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ea_db  # noqa: E402
import register  # noqa: E402

TZ = "America/Toronto"


def load(name: str):
    """Import a script that sets fixture mode at import, without leaking that into other tests."""
    with mock.patch.dict(os.environ):
        return importlib.import_module(name)


class P16FollowsTheSeed(unittest.TestCase):

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        self.acceptance = load("acceptance")
        self.make_fixtures = load("make_fixtures")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "state").mkdir()
        self.db_path = self.root / "state" / "fixtures.db"
        self.records = self.root / "state" / "records" / "fixture-calendar"
        conn = self.connect()
        try:
            register.seed_roster(conn)
        finally:
            conn.close()

    def connect(self):
        conn = ea_db.connect(self.db_path)
        ea_db.migrate(conn)
        return conn

    def seed(self, day: date, cadence: str = "biweekly") -> dict:
        """Seed Mark's series as make_fixtures.py --create would on `day`, at noon local."""
        now = datetime(day.year, day.month, day.day, 12, tzinfo=ZoneInfo(TZ)).astimezone(timezone.utc)
        conn = self.connect()
        try:
            self.make_fixtures.seed_meeting(conn, "mark", cadence, TZ, now, records=self.records)
        finally:
            conn.close()
        return json.loads((self.records / "mark.json").read_text(encoding="utf-8"))["seed"]

    def run_p16(self) -> dict:
        a = self.acceptance
        parsed = {"tabs": [{"items": [{"text": "Patio season close-out plan"}]}], "target_tab": 0,
                  "sections": {"taylor_topics": {"items": [0]}}}
        with mock.patch.object(a, "db", self.connect), \
                mock.patch.object(a, "ENV", {**a.ENV, "EA_ROOT": str(self.root)}), \
                mock.patch.object(a, "FIXTURE_CALENDAR", self.records, create=True), \
                mock.patch.object(a, "propose_and_apply", return_value=(a.Run(0, "", ""), a.Run(0, "", ""), "")), \
                mock.patch.object(a, "doc_of", return_value={"doc_id": "MARK", "title": "[FIXTURE] Mark x Taylor 1:1"}), \
                mock.patch.object(a, "read", return_value=parsed):
            _, result = a.run_leg(a.p16)
        return result

    def test_built_on_2026_10_01_the_next_1on1_is_2026_10_14(self):
        self.seed(date(2026, 10, 1))
        result = self.run_p16()
        self.assertEqual(self.acceptance.verdict(result), "Passed", result["summary"])
        self.assertIn("2026-10-14", result["summary"])

    def test_built_on_2026_11_17_the_expectation_moves_to_2026_11_30(self):
        self.seed(date(2026, 11, 17))
        result = self.run_p16()
        self.assertEqual(self.acceptance.verdict(result), "Passed", result["summary"])
        self.assertIn("2026-11-30", result["summary"])

    def test_built_across_the_clock_change_the_date_still_holds(self):
        self.seed(date(2026, 10, 25))  # last 1:1 Oct 24 (EDT), next Nov 7 (EST)
        result = self.run_p16()
        self.assertEqual(self.acceptance.verdict(result), "Passed", result["summary"])
        self.assertIn("2026-11-07", result["summary"])

    def test_a_series_read_as_weekly_still_fails(self):
        self.seed(date(2026, 10, 1), cadence="weekly")
        conn = self.connect()
        try:
            stored = conn.execute("SELECT next_at FROM meetings").fetchone()["next_at"]
        finally:
            conn.close()
        self.assertTrue(stored.startswith("2026-10-07"), f"the code under test should answer +7, got {stored}")
        result = self.run_p16()
        self.assertEqual(self.acceptance.verdict(result), "FAILED", result["summary"])

    def test_a_stored_next_at_that_drifted_from_the_seed_fails(self):
        self.seed(date(2026, 10, 1))
        conn = self.connect()
        try:
            with conn:
                conn.execute("UPDATE meetings SET next_at = '2026-10-21T10:00:00-04:00'")
        finally:
            conn.close()
        result = self.run_p16()
        self.assertEqual(self.acceptance.verdict(result), "FAILED", result["summary"])

    def test_the_expectation_is_the_seeded_last_instance_plus_two_weeks(self):
        for day, want in ((date(2026, 10, 1), date(2026, 10, 14)), (date(2026, 11, 17), date(2026, 11, 30))):
            with self.subTest(built=day.isoformat()):
                self.assertEqual(self.acceptance.expected_next_date(self.seed(day)), want)
        weekly = self.seed(date(2026, 10, 1), cadence="weekly")
        self.assertEqual(self.acceptance.expected_next_date(weekly), date(2026, 10, 14),
                         "the two weeks are P1.6's definition, never the seed's cadence")


if __name__ == "__main__":
    unittest.main()
