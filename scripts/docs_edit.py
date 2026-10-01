"""WREN's half of a Doc write: apply one proposal to one Doc, read it back, only then say so.

NEW in this repo. This is the only code that changes a running 1:1 Doc, and
.claude/hooks/require-delivery-agent.py lets only WREN run it. Blueprint s.1: never
report a successful capture or update that did not complete; make material
failures visible. G4 ("no false success") is observed here.

THE ORDER IS THE DESIGN.

  1. REFUSE before touching anything. The Doc must be registered (the docs table IS
     the allowlist); with EA_FIXTURE_MODE=1 it must be a fixture; a live Doc needs
     deviation D-1 approved by Taylor (context/architecture/deviations.json) and a
     section map he confirmed. The proposal file must hash to the row PAGE wrote
     (WREN delivers PAGE's bytes, never its own). Doc-bound text passes the content
     rules. An item already in the Doc is not placed twice.
  2. READ FRESH. documents.get, and refuse if it carries no revisionId: revisionId
     is returned only to editors, and writing without writeControl would be writing
     blind. Indices are recomputed from this read; the proposal's are never trusted.
  3. ONE ATOMIC batchUpdate with writeControl.requiredRevisionId. A table row is
     inserted AND filled in the same batch (the row/cell index model was verified
     on the fixtures), so a failure can never leave an empty row behind. If a
     manager edited in between, the API answers 400; one retry from a fresh read,
     then exit 3, loudly.
  4. READ BACK. A second get must show the text in the expected section of the
     newest meeting block and the named range ea:<kind>:<ref> resolving onto it.
     Only then: doc_items written, the proposal marked applied, the topic flipped to
     `placed`. A write the API accepted but the read-back cannot find exits 4 and is
     reported as WRITTEN BUT NOT VERIFIED, never as done.
  5. ONE AUDIT ROW PER CALL, success or failure, through _audit.record. /morning
     lists yesterday's Doc writes from it.

NEVER DELETE OR MOVE A LINE. Adds append; mark-done writes the Status cell (or
appends "(done <date>)" to a checklist line); update-due rewrites the Date cell of
that action's own row. Nothing else in the Doc is changed.

A NETWORK ERROR MID-WRITE IS AN UNKNOWN, NOT A FAILURE. The request may have been
applied with the response lost. So the Doc is read back: if the named range is
there and the text matches, it is a success (noted as such); if not, NOT UPDATED;
if the read-back itself fails, the outcome is reported as UNKNOWN with exit 4.

Usage (WREN only):
    python scripts/docs_edit.py add-topic  --doc <id> --proposal state/proposals/<file>.json
    python scripts/docs_edit.py add-action --doc <id> --proposal ...
    python scripts/docs_edit.py mark-done  --doc <id> --proposal ...
    python scripts/docs_edit.py update-due --doc <id> --proposal ...
    ... --simulate-stale-revision   (G4: write against an older revision; must exit 3)

Exit 0 updated (or nothing to change), 2 refused before writing, 3 not written,
4 written but not verified, 9 crashed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / ".claude" / "hooks"))

import approvals  # noqa: E402
import docs_read  # noqa: E402
import ea_db  # noqa: E402
import register  # noqa: E402
import validate_content_rules  # noqa: E402

import _audit  # noqa: E402

DEVIATIONS = ea_db.REPO_ROOT / "context" / "architecture" / "deviations.json"
KINDS = ("add-topic", "add-action", "mark-done", "update-due")
EXIT_OK, EXIT_REFUSED, EXIT_NOT_WRITTEN, EXIT_UNVERIFIED, EXIT_CRASH = 0, 2, 3, 4, 9


class Refused(Exception):
    """A precondition failed. Nothing was sent to Google."""


class NotWritten(Exception):
    """Google refused or failed the write. batchUpdate is atomic, so nothing changed."""


class Unverified(Exception):
    """The write may have landed, but the read-back cannot show it. Never reported as done."""


class AlreadyPlaced(Exception):
    """The named range for this add is already in the Doc: an earlier write landed."""


class NoChange(Exception):
    """The Doc already says what the proposal would write. Nothing to do, and not a failure."""


# ---------------------------------------------------------------------------
# preconditions (pure, so the guardrail self-test drives them)
# ---------------------------------------------------------------------------

def load_deviations() -> dict:
    """The deviation register, or {} when unreadable. {} means nothing is approved."""
    try:
        data = json.loads(DEVIATIONS.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return {}  # swallow: read by check_allowlist as "not approved", which refuses
    return data.get("deviations") or {}


def live_writes_approved(deviations: dict) -> tuple[bool, str]:
    gating = [(key, d) for key, d in deviations.items() if "live_doc_writes" in (d.get("gates") or [])]
    if not gating:
        return False, ("context/architecture/deviations.json is unreadable or names no deviation gating "
                       "live Doc writes, so none is treated as approved")
    pending = [key for key, d in gating if str(d.get("status")) != "approved"]
    if pending:
        return False, f"{', '.join(pending)} is not approved by Taylor yet (docs/DEVIATIONS.md)"
    return True, ""


def check_allowlist(conn, doc_id: str, *, fixture_mode: bool, deviations: dict):
    """The docs row for a Doc this call may write, or Refused naming why not."""
    row = conn.execute("SELECT * FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
    if row is None:
        raise Refused(f"Doc {doc_id} is not registered. The docs table is the write allowlist "
                      f"(python scripts/link_docs.py --status).")
    if fixture_mode and not row["fixture"]:
        raise Refused(f"EA_FIXTURE_MODE=1 and {row['title']!r} is a LIVE Doc. Tests write to fixtures only.")
    if not row["fixture"]:
        ok, why = live_writes_approved(deviations)
        if not ok:
            raise Refused(f"live Doc writes are not approved: {why}")
        if not row["map_confirmed"]:
            raise Refused(f"the section map for {row['title']!r} is not confirmed with Taylor "
                          f"(python scripts/link_docs.py --confirm --doc {doc_id})")
    return row


def require_revision(document: dict) -> str:
    revision = document.get("revisionId")
    if not revision:
        raise Refused("documents.get returned no revisionId. Google returns it only to editors, so this "
                      "account cannot edit this Doc. Refusing rather than writing without writeControl.")
    return str(revision)


def check_proposal(conn, path: Path, kind: str, doc_arg: str | None) -> dict:
    """Load the proposal and prove it is PAGE's exact bytes, still pending."""
    try:
        proposal = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"the proposal {path} cannot be read: {exc}") from exc
    if proposal.get("kind") != kind:
        raise Refused(f"the proposal is {proposal.get('kind')!r}, but {kind!r} was asked for")
    if doc_arg and doc_arg != proposal.get("doc_id"):
        raise Refused(f"--doc {doc_arg} does not match the proposal's Doc {proposal.get('doc_id')}")
    try:
        rel = path.resolve().relative_to(ea_db.REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise Refused(f"the proposal {path} is outside the repo") from exc
    index = conn.execute("SELECT * FROM proposals WHERE path = ?", (rel,)).fetchone()
    if index is None:
        raise Refused(f"{rel} is not in the proposal index; only a proposal PAGE wrote with "
                      f"scripts/docs_propose.py can be delivered")
    digest = hashlib.sha256(approvals.canonical("docs_edit", proposal)).hexdigest()
    if digest != index["sha256"]:
        raise Refused(f"{rel} has changed since PAGE wrote it (sha256 {digest[:12]} != {index['sha256'][:12]}). "
                      f"WREN delivers PAGE's bytes; ask PAGE for a new proposal.")
    if index["status"] not in ("pending", "failed"):
        raise Refused(f"{rel} is {index['status']}; a proposal is delivered once")
    for text in (proposal.get("text"), proposal.get("status_text"),
                 *((proposal.get("cells") or {}).get(k) for k in ("assignee", "title", "date_text"))):
        findings = validate_content_rules.check_doc_bound(text or "")
        if findings:
            raise Refused("Doc-bound text breaks a content rule: " + ", ".join(f.rule for f in findings))
    proposal["_index_id"] = index["id"]
    proposal["_sha256"] = digest
    return proposal


# ---------------------------------------------------------------------------
# request planning (pure)
# ---------------------------------------------------------------------------

def date_chip(day: str, tz_name: str) -> dict:
    """Noon local on `day`. timeZoneId must be absent unless the time format shows a zone."""
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    moment = datetime.fromisoformat(day + "T12:00:00").replace(tzinfo=ZoneInfo(tz_name))
    return {"timestamp": moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "locale": "en", "dateFormat": "DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED",
            "timeFormat": "TIME_FORMAT_DISABLED"}


def _rng(start: int, end: int, tab_id: str) -> dict:
    return {"startIndex": start, "endIndex": end, "tabId": tab_id}


def _named(name: str, start: int, end: int, tab_id: str) -> dict:
    return {"createNamedRange": {"name": name, "range": _rng(start, end, tab_id)}}


def plan_line(parsed: dict, section_key: str, text: str, named_range: str) -> list[dict]:
    """Append one line to a list or checklist section of the newest block."""
    tab = parsed["tabs"][parsed["target_tab"]]
    tab_id, items = tab["tab_id"], tab["items"]
    section = parsed["sections"][section_key]
    n = docs_read.u16(text)
    if section["items"]:
        # Before the last item's newline: the new paragraph inherits that item's
        # bullet and list, so it reads as one more entry of the same list.
        p = items[section["items"][-1]]["end"] - 1
        start = p + 1
        return [
            {"insertText": {"location": {"index": p, "tabId": tab_id}, "text": "\n" + text}},
            {"updateTextStyle": {"range": _rng(start, start + n, tab_id), "textStyle": {"strikethrough": False},
                                 "fields": "strikethrough,link"}},
            _named(named_range, start, start + n, tab_id),
        ]
    # Empty section: after the label. The new paragraph inherits the label's style
    # (bold, maybe a numbered agenda item), so it is reset and given its own bullet.
    anchor = items[section["anchor_item"]]
    p = anchor["end"] - 1
    start = p + 1
    requests = [
        {"insertText": {"location": {"index": p, "tabId": tab_id}, "text": "\n" + text}},
        {"updateTextStyle": {"range": _rng(start, start + n, tab_id),
                             "textStyle": {"bold": False, "strikethrough": False},
                             "fields": "bold,strikethrough,link"}},
        _named(named_range, start, start + n, tab_id),
    ]
    if anchor["bullet"]:
        requests.append({"deleteParagraphBullets": {"range": _rng(start, start + n + 1, tab_id)}})
    requests.append({"createParagraphBullets": {"range": _rng(start, start + n + 1, tab_id),
                                                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})
    return requests


def _columns(parsed: dict, section_key: str) -> dict:
    return {"assignee": 0, "title": 1, "date": 2, "status": 3, **(parsed["sections"][section_key].get("columns") or {})}


def _action_table(parsed: dict, section_key: str) -> dict:
    tab = parsed["tabs"][parsed["target_tab"]]
    return tab["items"][parsed["sections"][section_key]["table_item"]]


def plan_row_insert(parsed: dict, section_key: str) -> tuple[list[dict], int]:
    """Phase A of an action row: insert one empty row under the last row. Returns (requests, new row index).

    WHY TWO PHASES. insertTableRow copies a smart-chip PLACEHOLDER (U+E907) into the
    new row wherever the reference row holds a chip (observed 2026-10-01: a Date cell
    came back as [our date chip][placeholder]). The new row's cells are therefore not
    reliably empty, so their indices cannot be predicted inside one batch; a Title
    computed for empty cells would land in the Assignee cell whenever the row above
    had a person chip. Phase B fills the row from a fresh read instead.
    """
    tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
    table = _action_table(parsed, section_key)
    last = len(table["rows"]) - 1
    return [{"insertTableRow": {"tableCellLocation": {
        "tableStartLocation": {"index": table["start"], "tabId": tab_id},
        "rowIndex": last, "columnIndex": 0}, "insertBelow": True}}], last + 1


def row_is_blank(row: dict) -> bool:
    """Nothing in the row but empty paragraphs and chip placeholders."""
    for cell in row["cells"]:
        if cell["text"].replace(docs_read.CHIP_PLACEHOLDER, "").strip():
            return False
        if any(chip.get("type") != "unknown" for chip in cell["chips"]):
            return False
    return True


def plan_row_fill(parsed: dict, section_key: str, row: dict, cells: dict, named_range: str,
                  tz_name: str) -> list[dict]:
    """Phase B: replace each cell's content (placeholders included) with the proposal's value.

    Cells are processed from the last column backwards, so each delete-and-insert
    lands before anything to its left has moved. The Title's final start is its
    paragraph start plus the net change in the cells to its left.
    """
    tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
    cols = _columns(parsed, section_key)
    values: dict[int, tuple[str, str]] = {k: ("text", "") for k in range(len(row["cells"]))}
    values[cols["assignee"]] = ("text", cells.get("assignee") or "")
    values[cols["title"]] = ("text", cells["title"])
    values[cols["status"]] = ("text", cells.get("status") or "")
    values[cols["date"]] = ("date", cells["date"]) if cells.get("date") else ("text", cells.get("date_text") or "TBD")

    def width(value: tuple[str, str]) -> int:
        return 1 if value[0] == "date" else docs_read.u16(value[1])

    requests: list[dict] = []
    for k in range(len(row["cells"]) - 1, -1, -1):
        para = row["cells"][k]["paragraphs"][0]
        if para["end"] - 1 > para["start"]:
            requests.append({"deleteContentRange": {"range": _rng(para["start"], para["end"] - 1, tab_id)}})
        kind, value = values[k]
        location = {"index": para["start"], "tabId": tab_id}
        if kind == "date":
            requests.append({"insertDate": {"location": location, "dateElementProperties": date_chip(value, tz_name)}})
        elif value:
            requests.append({"insertText": {"location": location, "text": value}})
    title_para = row["cells"][cols["title"]]["paragraphs"][0]
    shift = sum(width(values[k]) - (row["cells"][k]["paragraphs"][0]["end"] - 1 - row["cells"][k]["paragraphs"][0]["start"])
                for k in range(cols["title"]))
    start = title_para["start"] + shift
    requests.append(_named(named_range, start, start + docs_read.u16(cells["title"]), tab_id))
    return requests


def _find_row(parsed: dict, located: dict) -> dict:
    for row in docs_read.all_table_rows(parsed):
        if row["start"] == located.get("row_start"):
            return row
    raise Refused("the action's row could not be found in a fresh read")


def _replace_cell(cell: dict, tab_id: str, insert: dict) -> list[dict]:
    """Requests that replace one cell's content with `insert` (a request at the cell's start)."""
    if len(cell["paragraphs"]) != 1:
        raise Refused("that cell holds more than one line; not rewriting it (nothing is ever deleted)")
    para = cell["paragraphs"][0]
    requests = []
    if para["end"] - 1 > para["start"]:
        requests.append({"deleteContentRange": {"range": _rng(para["start"], para["end"] - 1, tab_id)}})
    return requests + [insert]


def plan_mark_done(parsed: dict, located: dict, section_key: str, status_text: str) -> list[dict]:
    tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
    if located["shape"] == "row":
        cell = _find_row(parsed, located)["cells"][_columns(parsed, section_key)["status"]]
        start = cell["paragraphs"][0]["start"]
        return _replace_cell(cell, tab_id, {"insertText": {"location": {"index": start, "tabId": tab_id},
                                                           "text": status_text}})
    suffix = " (" + status_text[0].lower() + status_text[1:] + ")"
    return [{"insertText": {"location": {"index": located["para_end"] - 1, "tabId": tab_id}, "text": suffix}}]


def plan_update_due(parsed: dict, located: dict, section_key: str, due: str, tz_name: str) -> list[dict]:
    if located["shape"] != "row":
        raise Refused("update-due is supported for the action table only; this item is a checklist line")
    tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
    cell = _find_row(parsed, located)["cells"][_columns(parsed, section_key)["date"]]
    start = cell["paragraphs"][0]["start"]
    return _replace_cell(cell, tab_id, {"insertDate": {"location": {"index": start, "tabId": tab_id},
                                                       "dateElementProperties": date_chip(due, tz_name)}})


# ---------------------------------------------------------------------------
# read-back (pure)
# ---------------------------------------------------------------------------

def _chip_date(chip: dict | None, tz_name: str) -> str | None:
    if not chip or not chip.get("timestamp"):
        return None
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    moment = datetime.fromisoformat(chip["timestamp"].replace("Z", "+00:00"))
    return moment.astimezone(ZoneInfo(tz_name)).date().isoformat()


def verify(parsed: dict, proposal: dict, tz_name: str) -> dict:
    """The located item after the write, or Unverified naming exactly what is wrong."""
    if proposal["section"] in parsed["unmapped"]:
        raise Unverified(f"section {proposal['section']} is unmapped after the write")
    columns = parsed["sections"][proposal["section"]].get("columns")
    located = docs_read.locate(parsed, item_kind=proposal["item_kind"], item_ref=proposal["item_ref"],
                               named_range=proposal["named_range"], stored_hash=None, columns=columns)
    if located["via"] != "named_range":
        raise Unverified(f"the named range {proposal['named_range']} does not resolve onto the item "
                         f"(found via {located['via']})")
    kind = proposal["kind"]
    if kind == "add-topic" or (kind == "add-action" and not proposal["cells"]):
        if located["text"] != proposal["text"]:
            raise Unverified(f"the line reads {located['text']!r}, expected {proposal['text']!r}")
        tab = parsed["tabs"][parsed["target_tab"]]
        members = parsed["sections"][proposal["section"]].get("items") or []
        if not any(tab["items"][i]["start"] == located["para_start"] for i in members):
            raise Unverified(f"the line is not inside {proposal['section']} of the newest meeting block")
    elif kind == "add-action":
        cells = proposal["cells"]
        rows = [r for _, r in docs_read._section_rows(parsed, proposal["section"])]  # noqa: SLF001
        if not any(r["start"] == located["row_start"] for r in rows):
            raise Unverified("the new row is not in the newest block's action table")
        if located["text"] != cells["title"]:
            raise Unverified(f"the Title cell reads {located['text']!r}, expected {cells['title']!r}")
        if cells["date"] and _chip_date(located["date_chip"], tz_name) != cells["date"]:
            raise Unverified(f"the Date cell does not hold a {cells['date']} date chip")
        if not cells["date"] and located["date_text"] != cells["date_text"]:
            raise Unverified(f"the Date cell reads {located['date_text']!r}, expected {cells['date_text']!r}")
        if any(c.get("type") == "unknown" for c in located.get("date_cell_chips") or []):
            raise Unverified("a chip placeholder copied by insertTableRow is still in the Date cell")
        if located["state"] != "open":
            raise Unverified(f"the new row reads as {located['state']}, expected open")
    elif kind == "mark-done":
        if located["state"] != "checked":
            raise Unverified(f"after the write the item reads as {located['state']}, not done")
    elif kind == "update-due":
        if _chip_date(located.get("date_chip"), tz_name) != proposal["date"]:
            raise Unverified(f"the Date cell does not hold a {proposal['date']} date chip")
    return located


# ---------------------------------------------------------------------------
# the write
# ---------------------------------------------------------------------------

def plan(parsed: dict, proposal: dict, conn, tz_name: str) -> list[dict]:
    kind, section = proposal["kind"], proposal["section"]
    if section in parsed["unmapped"]:
        raise Refused(f"the Doc has no {section} in its newest meeting block; refusing to guess a place")
    if kind in ("add-topic", "add-action"):
        if docs_read._ranges(parsed, proposal["named_range"]):  # noqa: SLF001
            raise AlreadyPlaced(proposal["named_range"])
        if kind == "add-topic" or not proposal["cells"]:
            return plan_line(parsed, section, proposal["text"], proposal["named_range"])
        requests, new_row = plan_row_insert(parsed, section)
        proposal["_new_row"] = new_row
        return requests
    item = conn.execute("SELECT * FROM doc_items WHERE doc_id = ? AND item_kind = ? AND item_ref = ?",
                        (proposal["doc_id"], proposal["item_kind"], proposal["item_ref"])).fetchone()
    located = docs_read.locate(parsed, item_kind=proposal["item_kind"], item_ref=proposal["item_ref"],
                               named_range=proposal["named_range"],
                               stored_hash=item["text_hash"] if item else None,
                               columns=parsed["sections"][section].get("columns"))
    if located["state"] == "missing":
        raise Refused(f"{proposal['item_ref']} cannot be found in the Doc any more; not writing blind")
    if kind == "mark-done":
        if located["state"] == "checked":
            raise NoChange(f"{proposal['item_ref']} already reads as done in the Doc; nothing written")
        return plan_mark_done(parsed, located, section, proposal["status_text"])
    return plan_update_due(parsed, located, section, proposal["date"], tz_name)


def _stale_revision(conn, doc_id: str, current: str, basis: str | None = None) -> str:
    """A REAL older revision of this Doc, for --simulate-stale-revision (G4).

    A made-up string would test the wrong thing (an invalid id, not a stale one), so
    this uses the revision the proposal was based on, or the oldest recorded snapshot.
    """
    if basis and basis != current:
        return basis
    row = conn.execute("SELECT revision_id FROM doc_snapshots WHERE doc_id = ? AND revision_id != ?"
                       " AND revision_id NOT LIKE 'content:%' ORDER BY id LIMIT 1", (doc_id, current)).fetchone()
    if row is None:
        raise Refused("no older revision of this Doc is on record to simulate a stale write with")
    return str(row["revision_id"])


def _batch(service, doc_id: str, requests: list[dict], revision: str) -> dict:
    return service.documents().batchUpdate(documentId=doc_id, body={
        "requests": requests, "writeControl": {"requiredRevisionId": revision}}).execute()


def _http_status(exc: Exception) -> int:
    return int(getattr(getattr(exc, "resp", None), "status", 0) or 0)


def _fresh(service, proposal: dict, smap: dict, stage: str) -> tuple[dict, str]:
    """A fresh parse and its revision, for phase B. Any failure here leaves an
    inserted row unfilled, so it is reported as Unverified, never as refused."""
    try:
        document = docs_read.fetch(service, proposal["doc_id"])
        revision = require_revision(document)
    except (docs_read.DocReadError, Refused) as exc:
        raise Unverified(f"{stage}: the Doc could not be re-read after the row was inserted ({exc}); "
                         f"an empty row may be at row {proposal['_new_row']} of the action table") from exc
    return docs_read.parse(document, smap), revision


def fill_new_row(service, proposal: dict, smap: dict, tz_name: str, notes: list[str]) -> None:
    """Phase B. Fill the row phase A inserted, or remove it again. Never leaves it silently."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    section, index = proposal["section"], proposal["_new_row"]
    failure = ""
    for attempt in (1, 2):
        parsed, revision = _fresh(service, proposal, smap, "phase B")
        if section in parsed["unmapped"]:
            raise Unverified(f"the action table vanished after the row insert; row {index} may be left empty")
        table = _action_table(parsed, section)
        if len(table["rows"]) <= index:
            raise NotWritten("the row insert did not land (the table has no new row); nothing was written")
        if not row_is_blank(table["rows"][index]):
            raise Unverified(f"row {index} of the action table is no longer blank, so it was not touched; "
                             f"someone may be typing in it")
        requests = plan_row_fill(parsed, section, table["rows"][index], proposal["cells"],
                                 proposal["named_range"], tz_name)
        try:
            _batch(service, proposal["doc_id"], requests, revision)
            return
        except HttpError as exc:
            failure = f"HTTP {_http_status(exc)}: {str(getattr(exc, 'reason', '') or exc)[:200]}"
            if _http_status(exc) == 400 and attempt == 1:
                notes.append(f"phase B attempt 1 refused ({failure}); retried once from a fresh read")
                continue
            break
        except Exception as exc:  # noqa: BLE001
            # Not swallowed: an unanswered write is settled by the caller's read-back.
            notes.append(f"phase B got no HTTP answer ({exc.__class__.__name__}); outcome decided by read-back")
            return
    # Filling failed twice. Remove the empty row this call inserted: reverting its
    # own partial write is not deleting anybody's line.
    parsed, revision = _fresh(service, proposal, smap, "cleanup")
    table = _action_table(parsed, section)
    if len(table["rows"]) > index and row_is_blank(table["rows"][index]):
        tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
        try:
            _batch(service, proposal["doc_id"], [{"deleteTableRow": {"tableCellLocation": {
                "tableStartLocation": {"index": table["start"], "tabId": tab_id},
                "rowIndex": index, "columnIndex": 0}}}], revision)
        except Exception as exc:  # noqa: BLE001
            # Not swallowed: escalated as Unverified with the exact place to fix by hand.
            raise Unverified(f"the row could not be filled ({failure}) and the empty row it inserted at row "
                             f"{index} of the action table could not be removed ({exc.__class__.__name__}); "
                             f"delete that empty row by hand") from exc
        raise NotWritten(f"the row could not be filled ({failure}); the empty row it had inserted was removed")
    raise Unverified(f"the row could not be filled ({failure}) and row {index} is no longer blank; not touched")


def apply(kind: str, proposal_path: Path, *, doc_arg: str | None, simulate_stale: bool,
          service=None, conn=None) -> dict:
    """Run the whole write. Returns {"result", "exit", ...}. Records one audit row."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    own_conn = conn is None
    conn = conn or ea_db.connect()
    ea_db.migrate(conn)
    tz_name = register.identity().get("timezone") or "America/Toronto"
    outcome = {"kind": kind, "proposal": str(proposal_path), "doc_id": doc_arg}
    proposal: dict = {}
    notes: list[str] = []
    try:
        proposal = check_proposal(conn, proposal_path, kind, doc_arg)
        outcome["doc_id"] = proposal["doc_id"]
        doc = check_allowlist(conn, proposal["doc_id"], fixture_mode=ea_db.fixture_mode(),
                              deviations=load_deviations())
        smap = json.loads(doc["section_map_json"] or "{}")
        service = service or docs_read.docs_service()
        response = None
        for attempt in (1, 2):
            try:
                document = docs_read.fetch(service, proposal["doc_id"])
            except docs_read.DocReadError as exc:
                raise NotWritten(f"the Doc could not be read before writing: {exc}") from exc
            revision = require_revision(document)
            parsed = docs_read.parse(document, smap)
            try:
                requests = plan(parsed, proposal, conn, tz_name)
            except AlreadyPlaced:
                # An earlier run wrote this line and then failed before its bookkeeping
                # (or its read-back). Do not write it twice: verify what is there against
                # the proposal and, if it matches, finish the bookkeeping.
                located = verify(parsed, proposal, tz_name)
                record_success(conn, proposal, doc, located, revision)
                outcome.update(result="UPDATED", exit=EXIT_OK, revision=revision, ref=proposal["item_ref"],
                               where=f"{doc['title']} > {proposal['section']}",
                               notes=["recovered: the line was already in the Doc from an earlier write whose "
                                      "bookkeeping did not complete; verified and recorded, not written twice"])
                _audit.record(hook="docs_edit", tool="docs_edit", agent="WREN", decision="applied",
                              rule_id=f"{kind}:recovered", target=proposal["doc_id"],
                              payload_sha256=proposal["_sha256"], detail=f"{proposal['item_ref']} recovered")
                return outcome
            write_revision = (_stale_revision(conn, proposal["doc_id"], revision, proposal.get("basis_revision_id"))
                              if simulate_stale else revision)
            try:
                response = _batch(service, proposal["doc_id"], requests, write_revision)
                break
            except HttpError as exc:
                status = int(getattr(exc.resp, "status", 0) or 0)
                message = str(getattr(exc, "reason", "") or exc)[:300]
                if status == 400 and attempt == 1:
                    notes.append(f"attempt 1 refused by Google ({message}); retried once from a fresh read")
                    continue
                raise NotWritten(f"Google refused the write (HTTP {status}): {message}") from exc
            except Exception as exc:  # noqa: BLE001
                # Not swallowed: the outcome of a write whose response was lost is
                # UNKNOWN, so it is settled by the read-back below, never assumed.
                notes.append(f"the write call failed without an HTTP answer ({exc.__class__.__name__}: {exc}); "
                             f"outcome decided by read-back")
                break

        if proposal.get("_new_row") is not None:
            fill_new_row(service, proposal, smap, tz_name, notes)
            response = response or {"phase_b": "sent"}

        try:
            after = docs_read.parse(docs_read.fetch(service, proposal["doc_id"]), smap)
        except docs_read.DocReadError as exc:
            if response is None:
                raise Unverified(f"the write's outcome is UNKNOWN: the network failed and the read-back "
                                 f"failed too ({exc})") from exc
            raise Unverified(f"Google accepted the write but the read-back failed ({exc})") from exc
        try:
            located = verify(after, proposal, tz_name)
        except Unverified:
            if response is None:
                raise NotWritten("the network failed mid-write and the read-back shows nothing written")
            raise
        new_revision = after["revision_id"] or docs_read.revision_key(after)
        try:
            record_success(conn, proposal, doc, located, new_revision)
        except Exception as exc:  # noqa: BLE001
            # Not swallowed: the Doc DOES hold the verified line, so "not updated" would
            # be false and "updated" would hide a register that does not know it. Exit 4
            # names both facts; re-running the same proposal recovers (AlreadyPlaced).
            raise Unverified(f"the Doc was written and verified, but the register could not record it "
                             f"({exc.__class__.__name__}: {exc}). Re-run the same command to finish.") from exc
        outcome.update(result="UPDATED", exit=EXIT_OK, revision=new_revision, notes=notes,
                       where=f"{doc['title']} > {proposal['section']}", ref=proposal["item_ref"])
        _audit.record(hook="docs_edit", tool="docs_edit", agent="WREN", decision="applied", rule_id=kind,
                      target=proposal["doc_id"], payload_sha256=proposal["_sha256"],
                      detail=f"{proposal['item_ref']} into {proposal['section']}; rev {new_revision[:24]}"
                             + (f"; {'; '.join(notes)}" if notes else ""))
        return outcome
    except NoChange as exc:
        outcome.update(result="NO CHANGE", exit=EXIT_OK, detail=str(exc), revision="", ref=proposal.get("item_ref"))
        _audit.record(hook="docs_edit", tool="docs_edit", agent="WREN", decision="noop", rule_id=kind,
                      target=str(outcome.get("doc_id") or ""), payload_sha256=str(proposal.get("_sha256") or ""),
                      detail=str(exc)[:300])
        return outcome
    except Refused as exc:
        return _fail(conn, outcome, proposal, kind, EXIT_REFUSED, "refused", f"NOT UPDATED (refused): {exc}")
    except NotWritten as exc:
        return _fail(conn, outcome, proposal, kind, EXIT_NOT_WRITTEN, "fail",
                     f"NOT UPDATED: {exc}" + (f" [{'; '.join(notes)}]" if notes else ""))
    except Unverified as exc:
        return _fail(conn, outcome, proposal, kind, EXIT_UNVERIFIED, "fail",
                     f"WRITTEN BUT NOT VERIFIED (treat as not done): {exc}" + (f" [{'; '.join(notes)}]" if notes else ""))
    finally:
        if own_conn:
            conn.close()


def record_success(conn, proposal: dict, doc, located: dict, revision: str) -> None:
    """Register bookkeeping, only after a verified read-back, in one transaction."""
    now = ea_db.now_iso()
    kind, ref = proposal["kind"], proposal["item_ref"]
    state = "checked" if kind == "mark-done" else "open"
    text = located.get("text") or ""
    with conn:
        conn.execute(
            "INSERT INTO doc_items (doc_id, item_kind, item_ref, section, named_range, text_hash,"
            " inserted_revision_id, last_seen_revision_id, last_seen_state, last_seen_text, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(doc_id, item_kind, item_ref) DO UPDATE SET last_seen_revision_id=excluded.last_seen_revision_id,"
            " last_seen_state=excluded.last_seen_state, last_seen_text=excluded.last_seen_text, updated_at=excluded.updated_at",
            (proposal["doc_id"], proposal["item_kind"], ref, proposal["section"], proposal["named_range"],
             docs_read.text_hash(text), revision if kind.startswith("add-") else None, revision, state, text, now, now))
        conn.execute("UPDATE proposals SET status='applied', applied_at=?, result_revision_id=?, error=NULL WHERE id=?",
                     (now, revision, proposal["_index_id"]))
        conn.execute("UPDATE docs SET last_revision_id=?, verified_at=?, editable=1 WHERE doc_id=?",
                     (revision, now, proposal["doc_id"]))
        if kind == "add-topic":
            conn.execute("UPDATE topics SET status='placed', placed_doc_id=?, placed_revision_id=?, last_error=NULL,"
                         " updated_at=? WHERE ref=?", (proposal["doc_id"], revision, now, ref))
        else:
            action = conn.execute("SELECT id FROM actions WHERE ref = ?", (ref,)).fetchone()
            if action is not None:
                conn.execute("INSERT INTO action_events (action_id, ts, actor, field, old_value, new_value, source, note)"
                             " VALUES (?,?,?,?,?,?,?,?)",
                             (action["id"], now, "agent:wren", "doc", None, f"{kind} applied",
                              f"doc:{proposal['doc_id']}@{revision[:24]}", proposal["section"]))
        if kind == "mark-done":
            conn.execute("INSERT OR IGNORE INTO reconcile_events (doc_id, revision_id, action_ref, direction, outcome, ts)"
                         " VALUES (?,?,?,'register_to_doc','applied',?)", (proposal["doc_id"], revision, ref, now))


def _fail(conn, outcome: dict, proposal: dict, kind: str, code: int, decision: str, message: str) -> dict:
    """Record a failure everywhere it must be visible, then return it. Never raises."""
    outcome.update(result="NOT UPDATED" if code != EXIT_UNVERIFIED else "WRITTEN BUT NOT VERIFIED",
                   exit=code, detail=message)
    try:
        with conn:
            if proposal.get("_index_id"):
                conn.execute("UPDATE proposals SET status='failed', error=? WHERE id=?",
                             (message[:500], proposal["_index_id"]))
            if kind == "add-topic" and proposal.get("item_ref"):
                conn.execute("UPDATE topics SET last_error=?, updated_at=? WHERE ref=? AND status='queued'",
                             (message[:500], ea_db.now_iso(), proposal["item_ref"]))
    except Exception as exc:  # noqa: BLE001
        # swallow: the failure being recorded is reported to the caller and to the
        # audit log below; losing the register note must not mask the original error.
        outcome["detail"] += f" (and the register note could not be written: {exc.__class__.__name__})"
    _audit.record(hook="docs_edit", tool="docs_edit", agent="WREN", decision=decision, rule_id=kind,
                  target=str(outcome.get("doc_id") or ""), payload_sha256=str(proposal.get("_sha256") or ""),
                  detail=message[:500])
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--doc")
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--simulate-stale-revision", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        outcome = apply(args.kind, Path(args.proposal), doc_arg=args.doc,
                        simulate_stale=args.simulate_stale_revision)
    except Exception as exc:  # noqa: BLE001
        # swallow: converted into exit 9 with the reason, and an audit row, so a crash
        # is never mistaken for an update. _audit.record never raises.
        _audit.record(hook="docs_edit", tool="docs_edit", agent="WREN", decision="fail", rule_id=args.kind,
                      target=str(args.doc or ""), detail=f"crash {exc.__class__.__name__}: {exc}"[:500])
        print(f"RESULT: NOT UPDATED (crashed: {exc.__class__.__name__}: {exc})", file=sys.stderr)
        return EXIT_CRASH
    if args.json:
        print(json.dumps(outcome, indent=2, default=str))
    if outcome["exit"] == EXIT_OK and outcome["result"] == "NO CHANGE":
        print(f"RESULT: NO CHANGE ({outcome['detail']})")
    elif outcome["exit"] == EXIT_OK:
        print(f"RESULT: UPDATED {outcome.get('where')} ({outcome.get('ref')}), revision {outcome['revision'][:24]}...")
        for note in outcome.get("notes") or []:
            print(f"  note: {note}")
    else:
        print(f"RESULT: {outcome['detail']}", file=sys.stderr)
    return int(outcome["exit"])


if __name__ == "__main__":
    sys.exit(main())
