"""Regression tests for the silent-failure review of docs_edit.py and docs_reconcile.py (2026-10-01).

Each test is one finding, written as the failure scenario the reviewer described,
against the recorded fixture response and a fake Docs service. No network.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import docs_edit  # noqa: E402
import docs_read as dr  # noqa: E402
import docs_reconcile  # noqa: E402
import ea_db  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
DOC = json.loads((FIXTURES / "kaed_fixture_document.json").read_text(encoding="utf-8"))
MAP = json.loads((FIXTURES / "kaed_section_map.json").read_text(encoding="utf-8"))


def with_row(title: str, status: str, revision: str) -> dict:
    """The fixture response with the newest table's seed row rewritten, at a given revision."""
    document = copy.deepcopy(DOC)
    document["revisionId"] = revision
    table = [b for b in document["tabs"][0]["documentTab"]["body"]["content"] if "table" in b][0]
    row = table["table"]["tableRows"][2]
    for column, text in ((1, title), (3, status)):
        para = row["tableCells"][column]["content"][0]["paragraph"]
        para["elements"] = [{"startIndex": para["elements"][0]["startIndex"],
                             "endIndex": para["elements"][0]["startIndex"] + 1,
                             "textRun": {"content": text + "\n", "textStyle": {}}}]
    return document


class FakeService:
    def __init__(self, document: dict):
        self.document = document

    def documents(self):
        return self

    def get(self, **_kwargs):
        return self

    def execute(self):
        return self.document


class Register(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = ea_db.connect(Path(self.tmp.name) / "r.db")
        ea_db.migrate(self.conn)
        now = ea_db.now_iso()
        c = self.conn
        c.execute("INSERT INTO people (key, full_name, one_on_one, updated_at) VALUES ('taylor','Taylor',0,?)", (now,))
        c.execute("INSERT INTO people (key, full_name, one_on_one, updated_at) VALUES ('kaed','Kaed',1,?)", (now,))
        c.execute("INSERT INTO docs (doc_id, title, fixture, section_map_json, map_confirmed, last_revision_id,"
                  " reconciled_revision_id, role, created_at) VALUES ('FIXTURE_DOC_ID','[FIXTURE] Kaed',1,?,1,"
                  " 'R3','R1','running_1on1',?)", (json.dumps(MAP), now))
        c.execute("INSERT INTO actions (ref, text, owner_person_id, status, origin_kind, origin_at, created_at,"
                  " updated_at) VALUES ('A-0001','Send the plan',1,'open','chat',?,?,?)", (now, now, now))
        c.execute("INSERT INTO doc_items (doc_id, item_kind, item_ref, section, named_range, text_hash,"
                  " last_seen_state, created_at, updated_at) VALUES ('FIXTURE_DOC_ID','action','A-0001',"
                  " 'open_actions','ea:action:A-0001',?,'open',?,?)",
                  (dr.text_hash("Send the plan [A-0001]"), now, now))
        c.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def doc_row(self):
        return self.conn.execute("SELECT * FROM docs WHERE doc_id='FIXTURE_DOC_ID'").fetchone()

    def test_f1_done_typed_before_a_wren_write_is_still_ingested(self):
        # The Doc is at R3, which docs_edit stamped as last_revision_id after its own
        # write. The manager's Done is inside R3. The watermark (R1) is what counts.
        service = FakeService(with_row("Send the plan [A-0001]", "Done", "R3"))
        report = docs_reconcile.reconcile_doc(self.conn, service, self.doc_row())
        self.assertEqual(report["completed"], ["A-0001"])
        self.assertEqual(self.doc_row()["reconciled_revision_id"], "R3")

    def test_f2_a_renamed_tab_is_unreadable_not_everything_missing(self):
        document = with_row("Send the plan [A-0001]", "", "R4")
        document["tabs"][0]["tabProperties"]["title"] = "Agenda 2026"
        report = docs_reconcile.reconcile_doc(self.conn, FakeService(document), self.doc_row())
        self.assertEqual(report["status"], "unreadable")
        self.assertEqual(report["missing"], [])
        item = self.conn.execute("SELECT last_seen_state FROM doc_items").fetchone()
        self.assertEqual(item["last_seen_state"], "open")
        self.assertEqual(self.doc_row()["reconciled_revision_id"], "R1")

    def test_f3_an_empty_title_cell_never_completes_an_action(self):
        document = with_row(" ", "", "R5")
        parsed = dr.parse(document, MAP)
        row = dr._section_rows(parsed, "open_actions")[0][1]  # noqa: SLF001
        self.assertFalse(row["cells"][1]["struck"])
        report = docs_reconcile.reconcile_doc(self.conn, FakeService(document), self.doc_row())
        self.assertEqual(report["completed"], [])

    def test_f4_a_corrupt_section_map_is_one_unreadable_doc_not_a_crash(self):
        self.conn.execute("UPDATE docs SET section_map_json = '{not json' WHERE doc_id='FIXTURE_DOC_ID'")
        self.conn.commit()
        report = docs_reconcile.safe_reconcile(self.conn, FakeService(DOC), self.doc_row(), actor="tick")
        self.assertEqual(report["status"], "unreadable")

    def test_f5_an_unreadable_status_chip_becomes_a_question(self):
        document = with_row("Send the plan [A-0001]", "", "R6")
        table = [b for b in document["tabs"][0]["documentTab"]["body"]["content"] if "table" in b][0]
        para = table["table"]["tableRows"][2]["tableCells"][3]["content"][0]["paragraph"]
        para["elements"][0]["textRun"]["content"] = dr.CHIP_PLACEHOLDER + "\n"
        report = docs_reconcile.reconcile_doc(self.conn, FakeService(document), self.doc_row())
        self.assertEqual(report["unreadable"], ["A-0001"])
        self.assertEqual(len(report["questions"]), 1)
        again = docs_reconcile.reconcile_doc(self.conn, FakeService(document), self.doc_row(), force=True)
        self.assertEqual(again["questions"], [], "one question per action, not one per tick")


class EditPlanning(unittest.TestCase):
    def test_f12_mark_done_on_a_hedged_line_is_idempotent(self):
        parsed = {"tabs": [{"tab_id": "t.0", "items": []}], "target_tab": 0}
        located = {"shape": "paragraph", "text": "Not the final draft [A-0007] (done 2026-10-01)", "para_end": 99}
        with self.assertRaises(docs_edit.NoChange):
            docs_edit.plan_mark_done(parsed, located, "open_actions", "Done 2026-10-01")

    def test_f14_duplicate_columns_are_refused_before_any_row_exists(self):
        parsed = dr.parse(DOC, MAP)
        parsed["sections"]["open_actions"]["columns"] = {"status": 2, "date": 2}
        with self.assertRaises(docs_edit.Refused):
            docs_edit.plan_row_insert(parsed, "open_actions")

    def test_f13_mark_done_is_verified_by_its_own_words(self):
        parsed = dr.parse(with_row("Send the plan [A-0001]", "Done", "R7"), MAP)
        proposal = {"section": "open_actions", "item_kind": "action", "item_ref": "A-0001",
                    "named_range": "ea:action:A-0001", "kind": "mark-done", "status_text": "Done 2026-10-01"}
        parsed["tabs"][0]["named_ranges"] = {"ea:action:A-0001": {"namedRanges": [{"ranges": [
            {"startIndex": dr._section_rows(parsed, "open_actions")[0][1]["start"] + 1}]}]}}  # noqa: SLF001
        with self.assertRaises(docs_edit.Unverified):
            docs_edit.verify(parsed, proposal, "America/Toronto")


if __name__ == "__main__":
    unittest.main()
