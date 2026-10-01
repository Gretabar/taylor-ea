"""Doc-to-register reconciliation. READS Docs, writes only the register. Never edits a Doc.

NEW in this repo. Blueprint s.4: "Completion reported in a meeting document ...
updates the same canonical action", and managers must not have to keep a second
system; the Doc stays their surface. So when a manager types Done in the Status
cell of an action's row, the register action completes, with history, and leaves
/owe. The scheduled tick runs this; /add and /morning run it inline too.

WHAT COUNTS AS DONE. The Status cell, classified by docs_read.classify_status:
"Done", "Done 2026-10-01", "Complete", "x" are done; empty or "In progress" is open;
"not done", "mostly done" are AMBIGUOUS and become one Needs Your Input question,
never an auto-completion; a chip the API cannot read (a dropdown) is UNREADABLE and
becomes a question too, never a guess. On a checklist line, strikethrough of
visible text or a "(done ...)" marker counts. The live Docs have no checkboxes;
see docs/OPEN-QUESTIONS.md for what the checkbox experiment showed.

REPLAY-SAFE, TWICE OVER. (1) reconcile_events has UNIQUE(doc, revision, action,
direction), so the same revision cannot complete the same action twice; (2) only
an action still open, snoozed or delegated is completed at all. Either alone would
hold today; both are kept so neither is removed as redundant.

THE WATERMARK IS ITS OWN COLUMN. docs.reconciled_revision_id is written here and
nowhere else. docs_edit.py stamps docs.last_revision_id after its own writes, and
when the two were one column a manager's Done typed just before a WREN write was
skipped as "unchanged" forever (silent-failure review, 2026-10-01).

A DOC THAT NO LONGER PARSES IS UNREADABLE, NOT EMPTY. If the working tab or the
meeting heading cannot be found, every item would look missing. That is reported
as `unreadable` (structure), nothing in doc_items is touched, and the watermark
does not move, so the next tick tries again instead of declaring the Doc clean.

NEVER DESTRUCTIVE. An item the Doc no longer shows is `missing`, reported, NEVER
cancelled. A Done a manager later clears is a conflict for Taylor, never a silent
reopen. Every one of those reaches Needs Your Input, not just a log line.

The other direction (Taylor says "done" in chat, the Doc should show it) is WREN's,
in a session, through docs_edit.py mark-done; such rows are listed as
`register_ahead` so /morning can say so.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docs_read  # noqa: E402
import ea_db  # noqa: E402
import register  # noqa: E402

TICK_ROLES = ("running_1on1", "checkbox_experiment")


def _ask_once(conn, action, kind: str, question: str, source_ref: str) -> str | None:
    """One open question per action per kind, never a pile of duplicates."""
    existing = conn.execute("SELECT ref FROM needs_input WHERE action_id = ? AND source_kind = ? AND status = 'open'",
                            (action["id"], kind)).fetchone()
    if existing:
        return None
    ref = register.next_ref(conn, "question")
    conn.execute("INSERT INTO needs_input (ref, question, context, source_kind, source_ref, action_id, asked_at, status)"
                 " VALUES (?,?,?,?,?,?,?,'open')",
                 (ref, question, "read from the running Doc; nothing was assumed", kind, source_ref,
                  action["id"], ea_db.now_iso()))
    return ref


def _structurally_unreadable(parsed: dict, smap: dict) -> str:
    """Why the Doc cannot be reconciled at all, or "" when it can."""
    if parsed["target_tab"] is None:
        return f"the working tab {smap.get('tab_title')!r} was not found (renamed or deleted?)"
    if not parsed["blocks"]:
        return f"no meeting heading {smap.get('block_heading')!r} was found in the working tab"
    mapped = set((smap.get("sections") or {}).keys())
    if mapped and mapped <= set(parsed["unmapped"]):
        return "none of the mapped sections were found in the newest meeting block"
    return ""


def reconcile_doc(conn: sqlite3.Connection, service, doc_row, *, actor: str = "tick", force: bool = False) -> dict:
    """Bring the register up to date with one Doc. Returns a report; a failure is in the report."""
    report = {"doc_id": doc_row["doc_id"], "title": doc_row["title"], "status": "ok", "completed": [],
              "ambiguous": [], "unreadable": [], "missing": [], "conflicts": [], "register_ahead": [],
              "questions": [], "warnings": []}
    try:
        smap = json.loads(doc_row["section_map_json"] or "{}")
    except ValueError as exc:
        report.update(status="unreadable", error=f"the stored section map is not valid JSON ({exc})")
        return report
    try:
        document = docs_read.fetch(service, doc_row["doc_id"])
    except docs_read.DocReadError as exc:
        report.update(status="unreadable", error=str(exc))
        return report
    parsed = docs_read.parse(document, smap)
    revision = docs_read.revision_key(parsed)
    report["revision"] = revision
    if not parsed["revision_id"]:
        report["warnings"].append("no revisionId: this account cannot edit this Doc; completions are still read")

    broken = _structurally_unreadable(parsed, smap)
    if broken:
        # Nothing is marked missing and the watermark does not move: an unparseable
        # Doc must never be recorded as a Doc in which everything disappeared.
        report.update(status="unreadable", error=f"structure: {broken}")
        return report
    if parsed["unmapped"]:
        report["warnings"].append(f"unmapped sections: {', '.join(parsed['unmapped'])}")

    now = ea_db.now_iso()
    if revision == doc_row["reconciled_revision_id"] and not force:
        with conn:
            conn.execute("UPDATE docs SET verified_at = ? WHERE id = ?", (now, doc_row["id"]))
        report["status"] = "unchanged"
        return report

    body, digest = docs_read.snapshot(parsed)
    items = conn.execute("SELECT * FROM doc_items WHERE doc_id = ?", (doc_row["doc_id"],)).fetchall()
    with conn:
        conn.execute("INSERT OR IGNORE INTO doc_snapshots (doc_id, revision_id, parsed_json, sha256, taken_at)"
                     " VALUES (?,?,?,?,?)", (doc_row["doc_id"], revision, body, digest, now))
        for item in items:
            section = (smap.get("sections") or {}).get(item["section"]) or {}
            located = docs_read.locate(parsed, item_kind=item["item_kind"], item_ref=item["item_ref"],
                                       named_range=item["named_range"], stored_hash=item["text_hash"],
                                       columns=section.get("columns"))
            state = located["state"]
            if item["item_kind"] == "topic":
                state = "missing" if state == "missing" else "open"
            conn.execute("UPDATE doc_items SET last_seen_state=?, last_seen_revision_id=?, last_seen_text=?,"
                         " updated_at=? WHERE id=?",
                         (state, revision, located.get("text") or item["last_seen_text"], now, item["id"]))
            if state == "missing":
                report["missing"].append(item["item_ref"])
                continue
            if item["item_kind"] != "action":
                continue
            action = conn.execute("SELECT * FROM actions WHERE ref = ?", (item["item_ref"],)).fetchone()
            if action is None:
                report["warnings"].append(f"{item['item_ref']} is in the Doc but not in the register")
                continue
            words = located.get("status_text") or located.get("text") or ""
            source = f"doc:{doc_row['doc_id']}@{revision[:24]}"
            if state == "checked" and action["status"] in ("open", "snoozed", "delegated"):
                # Guard 1 of 2: the UNIQUE replay key. Guard 2 is the status test above.
                inserted = conn.execute(
                    "INSERT OR IGNORE INTO reconcile_events (doc_id, revision_id, action_ref, direction, outcome, ts)"
                    " VALUES (?,?,?,'doc_to_register','completed',?)",
                    (doc_row["doc_id"], revision, action["ref"], now)).rowcount
                if not inserted:
                    continue  # this revision already completed it; replay is a no-op
                conn.execute("UPDATE actions SET status='done', completed_at=?, completed_via='doc', updated_at=?"
                             " WHERE id=?", (now, now, action["id"]))
                conn.execute("INSERT INTO action_events (action_id, ts, actor, field, old_value, new_value, source, note)"
                             " VALUES (?,?,?,?,?,?,?,?)",
                             (action["id"], now, actor, "status", action["status"], "done", source,
                              f"the Doc reads {words!r}; the API does not record who typed it"))
                report["completed"].append(action["ref"])
            elif state == "checked" and action["status"] == "cancelled":
                conflict = f"{action['ref']} is cancelled in the register but reads done in {doc_row['title']}"
                report["conflicts"].append(conflict)
                q = _ask_once(conn, action, "doc_conflict", f"{conflict}. Which is right?", source)
                if q:
                    report["questions"].append(q)
            elif state == "open" and action["status"] == "done":
                if action["completed_via"] == "doc":
                    conflict = (f"{action['ref']} was completed from {doc_row['title']}, and the Doc no longer "
                                f"reads done; it was left done")
                    report["conflicts"].append(conflict)
                    q = _ask_once(conn, action, "doc_conflict", f"{conflict}. Is it still done?", source)
                    if q:
                        report["questions"].append(q)
                else:
                    report["register_ahead"].append(action["ref"])
            elif state == "ambiguous":
                report["ambiguous"].append(action["ref"])
                if action["status"] != "done":
                    q = _ask_once(conn, action, "doc_status", f"{action['ref']} '{action['text']}': its row in "
                                  f"{doc_row['title']} reads {words!r}. Is it done?", source)
                    if q:
                        report["questions"].append(q)
            elif state == "unreadable":
                report["unreadable"].append(action["ref"])
                q = _ask_once(conn, action, "doc_unreadable",
                              f"{action['ref']} '{action['text']}': the Status cell in {doc_row['title']} holds a "
                              f"chip the API cannot read (a dropdown?). Is it done? Typing Done as text makes it "
                              f"readable.", source)
                if q:
                    report["questions"].append(q)
        conn.execute("UPDATE docs SET reconciled_revision_id=?, verified_at=?, editable=? WHERE id=?",
                     (revision, now, 1 if parsed["revision_id"] else 0, doc_row["id"]))
    return report


def safe_reconcile(conn, service, doc_row, *, actor: str, force: bool = False) -> dict:
    """reconcile_doc, with any failure contained to this one Doc and reported as unreadable."""
    try:
        return reconcile_doc(conn, service, doc_row, actor=actor, force=force)
    except Exception as exc:  # noqa: BLE001
        # Not swallowed: returned as this Doc's failure, which the tick and /morning
        # report and which makes the tick exit partial. One bad Doc must not stop the
        # Docs after it from being reconciled.
        return {"doc_id": doc_row["doc_id"], "title": doc_row["title"], "status": "unreadable",
                "error": f"{exc.__class__.__name__}: {exc}", "completed": [], "ambiguous": [], "unreadable": [],
                "missing": [], "conflicts": [], "register_ahead": [], "questions": [], "warnings": []}


def docs_for_tick(conn, fixtures: bool) -> list:
    marks = ",".join("?" for _ in TICK_ROLES)
    return conn.execute(f"SELECT * FROM docs WHERE fixture = ? AND role IN ({marks}) ORDER BY id",
                        (1 if fixtures else 0, *TICK_ROLES)).fetchall()


def render(report: dict) -> str:
    head = f"  {report['status']:<10} {report['title']}"
    parts = []
    for key in ("completed", "ambiguous", "unreadable", "missing", "register_ahead", "questions"):
        if report.get(key):
            parts.append(f"{key}: {', '.join(report[key])}")
    lines = [head + (("  " + "; ".join(parts)) if parts else "")]
    lines += [f"      conflict: {c}" for c in report.get("conflicts") or []]
    lines += [f"      warning: {w}" for w in report.get("warnings") or []]
    if report.get("error"):
        lines.append(f"      error: {report['error']}")
    return "\n".join(lines)


def main() -> int:
    import argparse  # noqa: PLC0415

    ea_db.console_utf8()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--doc", help="one Doc; default every Doc the tick covers")
    parser.add_argument("--force", action="store_true", help="re-read even if the revision is unchanged")
    parser.add_argument("--actor", default="agent:reed")
    args = parser.parse_args()
    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        rows = (conn.execute("SELECT * FROM docs WHERE doc_id = ?", (args.doc,)).fetchall() if args.doc
                else docs_for_tick(conn, ea_db.fixture_mode()))
        if not rows:
            print("no registered Docs to reconcile")
            return 0
        service = docs_read.docs_service()
        worst = 0
        for row in rows:
            report = safe_reconcile(conn, service, row, actor=args.actor, force=args.force)
            print(render(report))
            if report["status"] == "unreadable" or report["conflicts"]:
                worst = 4
        return worst
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
