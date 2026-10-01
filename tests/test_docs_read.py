"""docs_read.py against a recorded documents.get response. No network.

tests/fixtures/kaed_fixture_document.json is the real response for the Kaed fixture
Doc built by make_fixtures.py on 2026-10-01, with the Doc id, revision, and the
owner's name and email replaced. It is the shape the live Docs have (tabs, a
newest-first RUNNING AGENDA block, bold numbered sections, the 4-column Action
Items table with date and person chips, plain labels), so these tests exercise the
parser on what the API actually returns.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import docs_read as dr  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
DOC = json.loads((FIXTURES / "kaed_fixture_document.json").read_text(encoding="utf-8"))
MAP = json.loads((FIXTURES / "kaed_section_map.json").read_text(encoding="utf-8"))


def table_rows(document: dict, block: int = 0) -> list:
    tables = [b for b in document["tabs"][0]["documentTab"]["body"]["content"] if "table" in b]
    return tables[block]["table"]["tableRows"]


def set_cell_text(row: dict, column: int, text: str) -> None:
    """Rewrite one cell's first text run in a copied response (indices are not re-flowed)."""
    para = row["tableCells"][column]["content"][0]["paragraph"]
    para["elements"] = [{"startIndex": para["elements"][0]["startIndex"],
                         "endIndex": para["elements"][0]["startIndex"] + 1,
                         "textRun": {"content": text + "\n", "textStyle": {}}}]


class Structure(unittest.TestCase):
    def setUp(self):
        self.parsed = dr.parse(DOC, MAP)

    def test_tabs_are_walked_not_body(self):
        self.assertEqual([t["title"] for t in self.parsed["tabs"]], ["RUNNING AGENDA", "Template", "One on One"])
        self.assertEqual(self.parsed["tabs"][self.parsed["target_tab"]]["title"], "RUNNING AGENDA")

    def test_meeting_blocks_newest_first(self):
        self.assertEqual(len(self.parsed["blocks"]), 2)
        self.assertEqual(self.parsed["newest_block"], 0)

    def test_every_logical_section_maps(self):
        self.assertEqual(self.parsed["unmapped"], [])
        self.assertEqual(set(self.parsed["sections"]),
                         {"wins", "open_actions", "feedback", "goals", "taylor_topics", "their_topics"})

    def test_sections_found_by_label_text_not_heading_level(self):
        tab = self.parsed["tabs"][self.parsed["target_tab"]]
        wins = self.parsed["sections"]["wins"]
        anchor = tab["items"][wins["anchor_item"]]
        self.assertEqual(anchor["style"], "NORMAL_TEXT")
        self.assertTrue(anchor["bold"] and anchor["numbered"])

    def test_action_table_header_and_rows(self):
        rows = dr._section_rows(self.parsed, "open_actions")  # noqa: SLF001
        self.assertEqual(self.parsed["sections"]["open_actions"]["header_row"], 1)
        self.assertEqual(len(rows), 1)

    def test_chips_are_read_as_elements(self):
        newest = dr._section_rows(self.parsed, "open_actions")[0][1]  # noqa: SLF001
        date_chip = newest["cells"][2]["chips"][0]
        self.assertEqual(date_chip["type"], "date")
        self.assertEqual(date_chip["timestamp"][:10], "2026-10-09")
        self.assertEqual(newest["cells"][2]["text"], "Oct 9, 2026")
        history = [it for it in self.parsed["tabs"][0]["items"] if it["kind"] == "table"][1]
        person = history["rows"][2]["cells"][0]["chips"][0]
        self.assertEqual((person["type"], person["email"]), ("person", "owner@example.com"))

    def test_rich_link_chip(self):
        links = [c for it in self.parsed["tabs"][0]["items"] if it["kind"] == "paragraph"
                 for c in it["chips"] if c["type"] == "richLink"]
        self.assertEqual(len(links), 1)
        self.assertIn("FIXTURE_DOC_ID", links[0]["uri"])

    def test_a_label_the_doc_does_not_have_is_unmapped(self):
        bad = copy.deepcopy(MAP)
        bad["sections"]["their_topics"]["anchor"] = "Casey Notes"
        parsed = dr.parse(DOC, bad)
        self.assertIn("their_topics", parsed["unmapped"])

    def test_missing_tab_maps_nothing(self):
        bad = dict(MAP, tab_title="Running Notes")
        parsed = dr.parse(DOC, bad)
        self.assertIsNone(parsed["target_tab"])
        self.assertEqual(sorted(parsed["unmapped"]), sorted(MAP["sections"]))

    def test_no_revision_id_means_not_editable(self):
        document = dict(DOC)
        document.pop("revisionId")
        parsed = dr.parse(document, MAP)
        self.assertFalse(parsed["editable"])
        self.assertTrue(dr.revision_key(parsed).startswith("content:"))

    def test_utf16_units(self):
        self.assertEqual(dr.u16("abc"), 3)
        self.assertEqual(dr.u16(chr(0x1D11E)), 2)  # outside the BMP: two UTF-16 units


class Completion(unittest.TestCase):
    def test_status_cell_words(self):
        for text, want in [("", "open"), ("Done", "checked"), ("done 2026-10-01", "checked"),
                           ("Complete", "checked"), ("x", "checked"), (chr(0x2713), "checked"),
                           ("In progress", "open"), ("not done", "ambiguous"),
                           ("mostly done", "ambiguous"), ("almost complete", "ambiguous"),
                           ("waiting on Casey", "open")]:
            with self.subTest(text=text):
                self.assertEqual(dr.classify_status(text), want)

    def test_an_unknown_chip_in_status_is_never_done(self):
        self.assertEqual(dr.classify_status("Done", [{"type": "unknown"}]), "ambiguous")

    def test_a_chip_the_api_cannot_read_is_unreadable_not_open(self):
        # A Status dropdown chip arrives as the U+E907 placeholder. Its value is
        # invisible to the API, so it must be reported, not read as "open".
        self.assertEqual(dr.classify_status(dr.CHIP_PLACEHOLDER, [{"type": "unknown"}]), "unreadable")

    def test_checklist_line_markers(self):
        for text, want in [("Send the deck (done 2026-10-01)", "checked"), ("[x] Send the deck", "checked"),
                           ("Send the deck [A-0003]", "open"), ("Send the deck, done", "checked")]:
            with self.subTest(text=text):
                self.assertEqual(dr.classify_status_line(text), want)


class Locate(unittest.TestCase):
    def doc_with_row(self, title: str, status: str) -> dict:
        document = copy.deepcopy(DOC)
        row = table_rows(document, 0)[2]
        set_cell_text(row, 1, title)
        set_cell_text(row, 3, status)
        return document

    def test_by_ref_token_and_status(self):
        parsed = dr.parse(self.doc_with_row("Send Casey the bonus structure [A-0001]", "Done"), MAP)
        found = dr.locate(parsed, item_kind="action", item_ref="A-0001", named_range=None,
                          stored_hash=None, columns=MAP["sections"]["open_actions"]["columns"])
        self.assertEqual((found["state"], found["via"]), ("checked", "ref_token"))

    def test_by_text_hash_when_the_token_was_deleted(self):
        parsed = dr.parse(self.doc_with_row("Send Casey the bonus structure", ""), MAP)
        found = dr.locate(parsed, item_kind="action", item_ref="A-0001", named_range=None,
                          stored_hash=dr.text_hash("Send Casey the bonus structure [A-0001]"),
                          columns=MAP["sections"]["open_actions"]["columns"])
        self.assertEqual((found["state"], found["via"]), ("open", "text_hash"))

    def test_gone_is_missing_not_cancelled(self):
        parsed = dr.parse(DOC, MAP)
        found = dr.locate(parsed, item_kind="action", item_ref="A-0099", named_range="ea:action:A-0099",
                          stored_hash="0" * 16, columns=None)
        self.assertEqual(found["state"], "missing")


if __name__ == "__main__":
    unittest.main()
