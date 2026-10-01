"""acceptance.py refuses to run on leftover fixture state, and reports a harness crash honestly.

Observed 2026-10-01: rerun without --rebuild on the state a previous run left, the
harness false-failed seven legs with detail that read like passes, exited 1, and
overwrote the committed passing report. These pin the fix:

  - a dirty state/fixtures.db is refused with exit 2 and one line, BEFORE any leg,
    and the report on disk is byte-for-byte untouched (sha256 before and after);
  - fresh fixtures pass the check, including a Doc whose revision moved with no
    content change, while changed, deleted and unreadable Docs do not;
  - a harness crash in P1.6 or G4 is Blocked, a broken script is still FAILED;
  - a FAILED leg's summary is marked as what was expected, so it cannot read like a pass.

The refusal tests drive the real script in a throwaway EA_ROOT. Everything else
runs in-process against the recorded Kaed response and a fake Docs fetch. No network.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import docs_read as dr  # noqa: E402
import ea_db  # noqa: E402
import register  # noqa: E402
from tests.test_review_regressions import DOC, MAP, with_row  # noqa: E402

LEFTOVER = "fixtures carry state from a previous run; rerun with --rebuild"


def load_acceptance():
    """Import acceptance.py without letting its fixture-mode environment leak into other tests."""
    with mock.patch.dict(os.environ):
        return importlib.import_module("acceptance")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_document(doc_id: str, revision: str = "rev-built") -> dict:
    document = json.loads(json.dumps(DOC))
    document["documentId"], document["revisionId"] = doc_id, revision
    return document


class RefusesLeftoverState(unittest.TestCase):
    """The real script, a throwaway EA_ROOT, a dirty fixtures.db."""

    def run_acceptance(self, root: Path) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "EA_DB"}
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "acceptance.py"), "--fixtures",
                               "--date", "2026-10-01"], env={**env, "EA_ROOT": str(root)},
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)

    def dirty_root(self, tmp: str, sql: str) -> Path:
        """An EA_ROOT whose fixtures.db has a registered fixture Doc and one row a previous run left.

        The registered Checkbox Doc matters for the test, not the fix: without it the
        pre-fix harness crashes in checkbox_experiment() before it writes a report, and
        the sha256 check below would never have seen the overwrite it exists to catch.
        """
        root = Path(tmp)
        (root / "state").mkdir()
        conn = ea_db.connect(root / "state" / "fixtures.db")
        try:
            ea_db.migrate(conn)
            now = ea_db.now_iso()
            conn.execute("INSERT INTO docs (doc_id, title, role, fixture, section_map_json, created_at)"
                         " VALUES ('CHK1', '[FIXTURE] Checkbox experiment', 'checkbox_experiment', 1, '{}', ?)",
                         (now,))
            conn.execute(sql, (now,) * sql.count("?"))
            conn.commit()
        finally:
            conn.close()
        return root

    def test_dirty_fixtures_db_refuses_and_leaves_the_committed_report_alone(self):
        for label, sql in [
            ("a leftover action", "INSERT INTO actions (ref, text, origin_kind, origin_at, created_at, updated_at)"
                                  " VALUES ('A-0001', 'Send Casey the bonus structure', 'chat', ?, ?, ?)"),
            ("a leftover doc_items row", "INSERT INTO doc_items (doc_id, item_kind, item_ref, created_at, updated_at)"
                                         " VALUES ('DOC1', 'topic', 'T-0001', ?, ?)"),
        ]:
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = self.dirty_root(tmp, sql)
                report = root / "docs" / "acceptance" / "P1-2026-10-01.md"
                report.parent.mkdir(parents=True)
                report.write_bytes(b"# Phase 1 acceptance, 2026-10-01\n\n| P1.1 | Passed |\n")
                before = sha256(report)

                done = self.run_acceptance(root)

                self.assertEqual(sha256(report), before, "the report on disk was rewritten")
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertEqual((done.stdout + done.stderr).strip(), LEFTOVER)
                self.assertEqual([p.name for p in report.parent.iterdir()], ["P1-2026-10-01.md"])

    def test_a_refusal_creates_no_report_where_there_was_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.dirty_root(tmp, "INSERT INTO captures (idempotency_key, kind, item_ref, created_at)"
                                        " VALUES ('replay-key', 'topic', 'T-0001', ?)")
            done = self.run_acceptance(root)
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            self.assertFalse((root / "docs").exists(), "a refusal wrote something under docs/")


class LeftoverStateCheck(unittest.TestCase):
    """leftover_state() against a fixtures.db shaped like a fresh build, and a fake Docs fetch."""

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        self.acceptance = load_acceptance()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = ea_db.connect(Path(tmp.name) / "fixtures.db")
        self.addCleanup(self.conn.close)
        ea_db.migrate(self.conn)
        register.seed_roster(self.conn)
        now = ea_db.now_iso()
        roles = [role for role, count in self.acceptance.expected_roles().items() for _ in range(count)]
        self.doc_ids = []
        with self.conn:
            for i, role in enumerate(roles):
                doc_id = f"FIXTURE-DOC-{i}"
                body, digest = dr.snapshot(dr.parse(build_document(doc_id), MAP))
                self.conn.execute("INSERT INTO docs (doc_id, title, role, fixture, section_map_json, created_at)"
                                  " VALUES (?, ?, ?, 1, ?, ?)", (doc_id, f"[FIXTURE] {i}", role, json.dumps(MAP), now))
                self.conn.execute("INSERT INTO doc_snapshots (doc_id, revision_id, parsed_json, sha256, taken_at)"
                                  " VALUES (?, 'rev-built', ?, ?, ?)", (doc_id, body, digest, now))
                self.doc_ids.append(doc_id)
        self.calls = []

    def check(self, served: dict | None = None) -> list[str]:
        """leftover_state, with Google serving each Doc as built unless `served` says otherwise."""
        def fetch(doc_id: str) -> dict:
            self.calls.append(doc_id)
            found = (served or {}).get(doc_id)
            if isinstance(found, Exception):
                raise found
            return found if found is not None else build_document(doc_id)
        return self.acceptance.leftover_state(self.conn, fetch)

    def test_fresh_fixtures_pass_and_every_doc_was_read(self):
        self.assertEqual(self.check(), [])
        self.assertEqual(sorted(self.calls), sorted(self.doc_ids))

    def test_a_new_revision_with_the_same_content_is_still_fresh(self):
        self.assertEqual(self.check({"FIXTURE-DOC-0": build_document("FIXTURE-DOC-0", "rev-later")}), [])

    def test_a_doc_whose_content_changed_is_leftover(self):
        changed = with_row("Send Casey the manager bonus structure [A-0001]", "Done", "rev-later")
        changed["documentId"] = "FIXTURE-DOC-0"
        self.assertEqual(self.check({"FIXTURE-DOC-0": changed}), ["[FIXTURE] 0: changed since it was built"])

    def test_a_deleted_doc_is_leftover(self):
        gone = dr.DocReadError("documents.get FIXTURE-DOC-6: HTTP 404, not found", 404)
        self.assertEqual(self.check({"FIXTURE-DOC-6": gone}), ["[FIXTURE] 6: no longer exists"])

    def test_a_doc_that_cannot_be_read_is_not_called_clean(self):
        with self.assertRaises(dr.DocReadError):
            self.check({"FIXTURE-DOC-2": dr.DocReadError("documents.get FIXTURE-DOC-2: HTTP 503, refused", 503)})

    def test_an_alias_g5_added_is_leftover_and_google_is_not_asked(self):
        register.add_alias(self.conn, "kaed", "Kade")
        reasons = self.check()
        self.assertEqual(len(reasons), 1)
        self.assertIn("kaed has aliases the roster does not (kade)", reasons[0])
        self.assertEqual(self.calls, [])

    def test_a_g4_doc_a_previous_run_consumed_is_leftover(self):
        with self.conn:
            self.conn.execute("UPDATE docs SET role = 'g4_deleted' WHERE role = 'g4_sacrificial'")
        reasons = self.check()
        self.assertEqual(len(reasons), 1)
        self.assertIn("g4_deleted", reasons[0])

    def test_register_rows_are_leftover_and_google_is_not_asked(self):
        with self.conn:
            self.conn.execute("INSERT INTO counters (name, value) VALUES ('action', 4)")
        self.assertEqual(self.check(), ["counters: 1 row(s)"])
        self.assertEqual(self.calls, [])

    def test_no_fixtures_at_all_is_not_called_leftover(self):
        with self.conn:
            self.conn.execute("DELETE FROM docs")
        self.assertEqual(self.check(), [self.acceptance.NOTHING_BUILT])


class HarnessCrashIsBlocked(unittest.TestCase):
    """P1.6 and G4: a harness crash is Blocked; the system under test failing is FAILED."""

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        self.acceptance = load_acceptance()
        self.meeting = {"id": 5, "cadence_observed": "biweekly", "next_at": "2026-10-14T10:00:00-06:00"}

    def leg(self, name, fn, *, sh_result, sacrificial=True):
        a = self.acceptance

        def rows(sql, *params):
            if "g4_sacrificial" in sql:
                return [{"doc_id": "G4DOC"}] if sacrificial else []
            return [self.meeting]

        with mock.patch.object(a, "sh", return_value=sh_result), mock.patch.object(a, "rows", side_effect=rows), \
                mock.patch.object(a, "scalar", return_value=6):
            _, result = a.run_leg(name, fn)
        return a.verdict(result), result["summary"]

    def test_p16_on_a_replayed_capture_is_blocked_not_failed(self):
        replay = self.acceptance.Run(0, json.dumps({"ref": "T-0004", "created": False, "note": "already captured"}), "")
        verdict, summary = self.leg("P1.6", self.acceptance.p16, sh_result=replay)
        self.assertEqual(verdict, "Blocked")
        self.assertIn("harness error RuntimeError: T-0004 was captured by an earlier run", summary)

    def test_p16_when_the_register_script_fails_is_failed(self):
        broken = self.acceptance.Run(1, "", "RegisterError: mark has no running 1:1")
        verdict, summary = self.leg("P1.6", self.acceptance.p16, sh_result=broken)
        self.assertEqual(verdict, "FAILED")
        self.assertIn("system failure: register.py add-topic exited 1", summary)

    def test_p16_when_a_new_capture_drops_meeting_id_is_failed(self):
        no_meeting = self.acceptance.Run(0, json.dumps({"ref": "T-0004", "created": True, "next_at": None}), "")
        verdict, summary = self.leg("P1.6", self.acceptance.p16, sh_result=no_meeting)
        self.assertEqual(verdict, "FAILED")
        self.assertIn("output has no meeting_id", summary)

    def test_g4_without_its_sacrificial_doc_is_blocked_not_failed(self):
        verdict, summary = self.leg("G4", self.acceptance.g4, sh_result=self.acceptance.Run(0, "{}", ""),
                                    sacrificial=False)
        self.assertEqual(verdict, "Blocked")
        self.assertIn("no G4 fixture Doc is registered", summary)

    def test_a_harness_crash_in_other_legs_is_still_failed(self):
        _, result = self.acceptance.run_leg("P1.1", lambda ev: {}["ref"])
        self.assertEqual(self.acceptance.verdict(result), "FAILED")

    def test_a_failed_leg_does_not_read_like_a_pass(self):
        summary = "1 topic T-0001 placed in Kaed's taylor_topics, 0 actions, 0 meetings created"
        _, failed = self.acceptance.run_leg("P1.1", lambda ev: {"ok": False, "summary": summary})
        _, passed = self.acceptance.run_leg("P1.1", lambda ev: {"ok": True, "summary": summary})
        self.assertEqual(failed["summary"], f"expected, not observed: {summary}")
        self.assertEqual(passed["summary"], summary)


if __name__ == "__main__":
    unittest.main()
