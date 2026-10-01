"""Doc-to-register reconciliation. READS Docs, writes only the register. Never edits a Doc.

NEW in this repo. Blueprint s.4: "Completion reported in a meeting document ...
updates the same canonical action", and managers must not have to keep a second
system; the Doc stays their surface. So when a manager types Done in the Status
cell of an action's row, the register action completes, with history, and leaves
/owe. The scheduled tick runs this; /add and /morning run it inline too.

WHAT COUNTS AS DONE. The Status cell, classified by docs_read.classify_status:
"Done", "Done 2026-10-01", "Complete", "x" are done; empty or "In progress" is open;
"not done", "mostly done" are AMBIGUOUS and surfaced as one Needs Your Input
question, never auto-completed; a chip the API cannot read (a dropdown) is
UNREADABLE and reported, never guessed. On a checklist line, strikethrough or a
"(done ...)" marker counts. The live Docs have no checkboxes and no strikethrough;
see docs/OPEN-QUESTIONS.md for what the checkbox experiment showed.

REPLAY-SAFE. reconcile_events has UNIQUE(doc, revision, action, direction): the same
revision can never complete the same action twice. An unchanged revision is skipped
before anything is parsed, so a second tick on an unchanged Doc does nothing.

NEVER DESTRUCTIVE. An item the Doc no longer shows is `missing`, reported, and NEVER
cancelled: a manager tidying a table must not erase a commitment. A Done that a
manager later clears does not silently reopen the action; it is reported as a
conflict for Taylor. The API does not say who typed a change, so the actor is
recorded as the tick or the agent, with the cell's words as the note.

THE OTHER DIRECTION is not here. Register-to-Doc (Taylor says "done" in chat, and
the Doc should show it) is WREN's, in a session, through docs_edit.py mark-done.
This module lists such rows as `register_ahead` so /morning can say so.
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


def _ask_once(conn, action, question: str, source_ref: str) -> str | None:
    """One open question per action about its Doc status, never a pile of duplicates."""
    existing = conn.execute("SELECT ref FROM needs_input WHERE action_id = ? AND source_kind = 'doc_status'"
                            " AND status = 'open'", (action["id"],)).fetchone()
    if existing:
        return None
    ref = register.next_ref(conn, "question")
    conn.execute("INSERT INTO needs_input (ref, question, context, source_kind, source_ref, action_id, asked_at, status)"
                 " VALUES (?,?,?,'doc_status',?,?,?,'open')",
                 (ref, question, "read from the running Doc; nothing was assumed", source_ref, action["id"],
                  ea_db.now_iso()))
    return ref


def reconcile_doc(conn: sqlite3.Connection, service, doc_row, *, actor: str = "tick", force: bool = False) -> dict:
    """Bring the register up to date with one Doc. Returns a report; raises nothing it can name."""
    report = {"doc_id": doc_row["doc_id"], "title": doc_row["title"], "status": "ok", "completed": [],
              "ambiguous": [], "unreadable": [], "missing": [], "conflicts": [], "register_ahead": [],
              "questions": [], "warnings": []}
    smap = json.loads(doc_row["section_map_json"] or "{}")
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
    if parsed["unmapped"]:
        report["warnings"].append(f"unmapped sections: {', '.join(parsed['unmapped'])}")

    now = ea_db.now_iso()
    if revision == doc_row["last_revision_id"] and not force:
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
                report["conflicts"].append(f"{action['ref']} is cancelled in the register but reads done in the Doc")
            elif state == "open" and action["status"] == "done":
                if action["completed_via"] == "doc":
                    report["conflicts"].append(f"{action['ref']} was completed from the Doc, and the Doc no longer "
                                               f"reads done; left done, ask Taylor")
                else:
                    report["register_ahead"].append(action["ref"])
            elif state == "ambiguous" and action["status"] != "done":
                q = _ask_once(conn, action, f"{action['ref']} '{action['text']}': its row in {doc_row['title']} "
                                            f"reads {words!r}. Is it done?", source)
                report["ambiguous"].append(action["ref"])
                if q:
                    report["questions"].append(q)
            elif state == "unreadable":
                report["unreadable"].append(action["ref"])
        conn.execute("UPDATE docs SET last_revision_id=?, verified_at=?, editable=? WHERE id=?",
                     (revision, now, 1 if parsed["revision_id"] else 0, doc_row["id"]))
    return report


def docs_for_tick(conn, fixtures: bool) -> list:
    marks = ",".join("?" for _ in TICK_ROLES)
    return conn.execute(f"SELECT * FROM docs WHERE fixture = ? AND role IN ({marks}) ORDER BY id",
                        (1 if fixtures else 0, *TICK_ROLES)).fetchall()


def render(report: dict) -> str:
    head = f"  {report['status']:<10} {report['title']}"
    parts = []
    for key in ("completed", "ambiguous", "unreadable", "missing", "register_ahead"):
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
            report = reconcile_doc(conn, service, row, actor=args.actor, force=args.force)
            print(render(report))
            if report["status"] == "unreadable":
                worst = 4
        return worst
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
