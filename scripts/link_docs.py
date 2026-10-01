"""Register Taylor's running 1:1 Docs, propose each one's section map, and verify access.

NEW in this repo. The `docs` table is the write allowlist: scripts/docs_edit.py
refuses any Doc that is not registered here. So registering a Doc is the decision
that makes it writable, and it is made deliberately, one Doc at a time, with the
section map confirmed with Taylor (blueprint s.4: keep each person's tailored
structure; the arrangement fits the actual Doc).

--verify IS READ ONLY. The plan sketched a named-range create-and-delete probe to
prove edit rights. The 2026-10-01 inspection found something better: documents.get
returns revisionId ONLY to editors. So a plain read proves edit access, and
verifying a live Doc never writes to it.

DETECTION PROPOSES, TAYLOR CONFIRMS. --detect reads the working tab and proposes a
map from what is there: the "RUNNING AGENDA:" block heading, the bold numbered
agenda items, the plain labels, and the Action Items table. Which label holds
Taylor's topics and which holds the manager's is NOT knowable from the Doc, so the
proposal says which mappings are assumptions, and the map stays unconfirmed until
Taylor says so. An unconfirmed map still reads; it never writes (docs_edit.py
refuses a live Doc whose map is unconfirmed).

Usage:
    python scripts/link_docs.py --status
    python scripts/link_docs.py --add <url-or-id> --person kaed
    python scripts/link_docs.py --detect --doc <id>
    python scripts/link_docs.py --set-map --doc <id> --map-file map.json [--confirm]
    python scripts/link_docs.py --confirm --doc <id>
    python scripts/link_docs.py --verify [--doc <id>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docs_read  # noqa: E402
import ea_db  # noqa: E402

DOC_ID = re.compile(r"/document/d/([A-Za-z0-9_-]{20,})|^([A-Za-z0-9_-]{20,})$")
ACTION_HEADER = ["Assignee", "Title", "Date", "Status"]


def doc_id_of(url_or_id: str) -> str:
    match = DOC_ID.search((url_or_id or "").strip())
    if not match:
        raise ValueError(f"{url_or_id!r} is not a Google Docs URL or document id")
    return match.group(1) or match.group(2)


def register_doc(conn, *, doc_id: str, title: str, person_key: str | None, fixture: bool,
                 section_map: dict | None, tab_id: str | None = None, role: str = "running_1on1",
                 confirmed: bool = False, revision_id: str | None = None) -> int:
    """Insert or update one docs row. The single place a Doc becomes writable."""
    person_id = None
    meeting_id = None
    if person_key:
        row = conn.execute("SELECT id FROM people WHERE key = ?", (person_key,)).fetchone()
        if row is None:
            raise ValueError(f"no person {person_key!r}; run register.py seed --roster")
        person_id = row["id"]
        meeting = conn.execute("SELECT id FROM meetings WHERE person_id = ? AND kind = '1on1' LIMIT 1",
                               (person_id,)).fetchone()
        meeting_id = meeting["id"] if meeting else None
    now = ea_db.now_iso()
    with conn:
        conn.execute(
            "INSERT INTO docs (doc_id, person_id, meeting_id, title, url, role, fixture, tab_id,"
            " section_map_json, map_confirmed, last_revision_id, editable, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(doc_id) DO UPDATE SET person_id=excluded.person_id, meeting_id=excluded.meeting_id,"
            " title=excluded.title, role=excluded.role, tab_id=excluded.tab_id,"
            " section_map_json=excluded.section_map_json, map_confirmed=excluded.map_confirmed",
            (doc_id, person_id, meeting_id, title, f"https://docs.google.com/document/d/{doc_id}/edit",
             role, 1 if fixture else 0, tab_id, json.dumps(section_map) if section_map else None,
             1 if confirmed else 0, revision_id, 1 if revision_id else None, now))
    return int(conn.execute("SELECT id FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()["id"])


def detect(document: dict, first_name: str = "") -> dict:
    """Propose a section map from what the Doc contains. Assumptions are flagged."""
    tabs = docs_read.flatten_tabs(document)
    best, best_count = None, -1
    for i, tab in enumerate(tabs):
        count = sum(1 for it in tab["items"] if it["kind"] == "paragraph"
                    and it["style"].startswith("HEADING") and docs_read.norm(it["text"]) == "running agenda")
        if count > best_count or (count == best_count and docs_read.norm(tab["title"]) == "running agenda"):
            best, best_count = i, count
    proposal = {"version": 1, "tab_title": tabs[best]["title"] if best is not None else None,
                "block_heading": "RUNNING AGENDA:" if best_count > 0 else None,
                "block_order": "newest_first", "labels": [], "sections": {}, "ref_tokens": True,
                "assumptions": []}
    if best is None:
        return proposal
    items = tabs[best]["items"]
    first = next((i for i, it in enumerate(items) if it["kind"] == "paragraph"
                  and it["style"].startswith("HEADING")), 0)
    end = next((i for i, it in enumerate(items) if i > first and it["kind"] == "paragraph"
                and it["style"].startswith("HEADING")), len(items))
    for it in items[first:end]:
        if it["kind"] == "table":
            head = docs_read._header_row(it, ACTION_HEADER)  # noqa: SLF001
            if head is not None and "open_actions" not in proposal["sections"]:
                proposal["sections"]["open_actions"] = {
                    "anchor": it["rows"][0]["cells"][0]["text"] or "Action Items", "kind": "table",
                    "header": ACTION_HEADER, "columns": {"assignee": 0, "title": 1, "date": 2, "status": 3}}
            continue
        text = it["text"].strip()
        if not text or it["in_table"]:
            continue
        label_like = (it["bold"] and it["numbered"] and it["bullet"] and it["bullet"]["level"] == 0) or \
                     (not it["bullet"] and len(text) <= 60 and not text.endswith("."))
        if label_like and not it["style"].startswith("HEADING"):
            proposal["labels"].append(text)
    for label in proposal["labels"]:
        n = docs_read.norm(label)
        if n.startswith("wins"):
            proposal["sections"].setdefault("wins", {"anchor": label, "kind": "list"})
        elif n.startswith("feedback"):
            proposal["sections"].setdefault("feedback", {"anchor": label, "kind": "list"})
        elif n.startswith("strategic priorities"):
            proposal["sections"].setdefault("goals", {"anchor": label, "kind": "list"})
        elif n.startswith("top focuses"):
            proposal["sections"].setdefault("taylor_topics", {"anchor": label, "kind": "list"})
            proposal["assumptions"].append(f"taylor_topics -> {label!r} is an ASSUMPTION; confirm with Taylor")
        elif first_name and n == f"{first_name.casefold()} notes":
            proposal["sections"].setdefault("their_topics", {"anchor": label, "kind": "list"})
            proposal["assumptions"].append(f"their_topics -> {label!r} is an ASSUMPTION; confirm with Taylor")
    for key in ("taylor_topics", "their_topics", "open_actions"):
        if key not in proposal["sections"]:
            proposal["assumptions"].append(f"{key}: no label found; writes to it will refuse until mapped")
    return proposal


def status(conn) -> int:
    rows = conn.execute(
        "SELECT d.*, p.key AS person FROM docs d LEFT JOIN people p ON p.id = d.person_id ORDER BY d.fixture, p.key"
    ).fetchall()
    live = [r for r in rows if not r["fixture"] and r["role"] == "running_1on1"]
    expected = conn.execute("SELECT COUNT(*) FROM people WHERE one_on_one = 1 AND active = 1").fetchone()[0]
    print(f"{ea_db.DB_PATH}")
    print(f"running 1:1 Docs linked: {len(live)} of {expected} people with a 1:1")
    if not rows:
        print("  none registered. Link each with: python scripts/link_docs.py --add <url> --person <key>")
    for r in rows:
        smap = json.loads(r["section_map_json"]) if r["section_map_json"] else {}
        mapped = sorted((smap.get("sections") or {}).keys())
        print(f"  {'FIXTURE ' if r['fixture'] else ''}{(r['person'] or '-'):<7} {r['title']}")
        print(f"      id {r['doc_id']}  role {r['role']}")
        print(f"      editable: {'yes' if r['editable'] else ('NO' if r['editable'] == 0 else 'not verified')}"
              f"   verified: {r['verified_at'] or 'never'}   map: "
              f"{'confirmed' if r['map_confirmed'] else 'UNCONFIRMED'} ({', '.join(mapped) or 'none'})")
    missing = conn.execute(
        "SELECT key FROM people WHERE one_on_one = 1 AND active = 1 AND id NOT IN"
        " (SELECT person_id FROM docs WHERE fixture = 0 AND role = 'running_1on1' AND person_id IS NOT NULL)"
        " ORDER BY key").fetchall()
    if missing:
        print("not linked yet: " + ", ".join(r["key"] for r in missing) + "  (links needed from Taylor)")
    return 0


def verify(conn, doc_id: str | None) -> int:
    rows = conn.execute("SELECT * FROM docs" + (" WHERE doc_id = ?" if doc_id else ""),
                        (doc_id,) if doc_id else ()).fetchall()
    if not rows:
        print("nothing to verify")
        return 1
    service = docs_read.docs_service()
    worst = 0
    for row in rows:
        try:
            document = docs_read.fetch(service, row["doc_id"])
        except docs_read.DocReadError as exc:
            print(f"  FAIL {row['title']}: {exc}")
            worst = 1
            continue
        smap = json.loads(row["section_map_json"]) if row["section_map_json"] else None
        parsed = docs_read.parse(document, smap)
        with conn:
            conn.execute("UPDATE docs SET editable=?, verified_at=?, last_revision_id=COALESCE(?, last_revision_id)"
                         " WHERE id=?", (1 if parsed["editable"] else 0, ea_db.now_iso(),
                                         parsed["revision_id"], row["id"]))
        state = "editable" if parsed["editable"] else "READ ONLY (no revisionId: this account cannot edit it)"
        print(f"  OK   {row['title']}: {state}; unmapped: {', '.join(parsed['unmapped']) or 'none'}")
        if not parsed["editable"] or parsed["unmapped"]:
            worst = max(worst, 1)
    return worst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--add")
    parser.add_argument("--person")
    parser.add_argument("--detect", action="store_true")
    parser.add_argument("--set-map", action="store_true")
    parser.add_argument("--map-file")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--doc")
    args = parser.parse_args()

    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        if args.status:
            return status(conn)
        if args.verify:
            return verify(conn, doc_id_of(args.doc) if args.doc else None)
        if args.add or args.detect:
            doc_id = doc_id_of(args.add or args.doc or "")
            document = docs_read.fetch(docs_read.docs_service(), doc_id)
            first = ""
            if args.person:
                row = conn.execute("SELECT * FROM people WHERE key = ?", (args.person.lower(),)).fetchone()
                if row is None or not row["one_on_one"]:
                    print(f"REFUSED: {args.person!r} is not a person with a running 1:1", file=sys.stderr)
                    return 1
                first = (row["full_name"] or row["key"]).split()[0]
            proposal = detect(document, first)
            print(json.dumps(proposal, indent=2, ensure_ascii=False))
            if args.add:
                if not args.person:
                    print("REFUSED: --add needs --person", file=sys.stderr)
                    return 2
                if ea_db.fixture_mode():
                    print("REFUSED: --add registers a LIVE Doc and fixture mode is on", file=sys.stderr)
                    return 2
                register_doc(conn, doc_id=doc_id, title=document.get("title") or doc_id,
                             person_key=args.person.lower(), fixture=False, section_map=proposal,
                             confirmed=False, revision_id=document.get("revisionId"))
                print(f"registered (map UNCONFIRMED). Confirm the labels with Taylor, then:\n"
                      f"  python scripts/link_docs.py --confirm --doc {doc_id}")
            return 0
        if args.set_map or args.confirm:
            doc_id = doc_id_of(args.doc or "")
            row = conn.execute("SELECT * FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None:
                print(f"REFUSED: {doc_id} is not registered", file=sys.stderr)
                return 1
            smap = row["section_map_json"]
            if args.set_map:
                smap = json.dumps(json.loads(Path(args.map_file).read_bytes().decode("utf-8")))
            with conn:
                conn.execute("UPDATE docs SET section_map_json=?, map_confirmed=? WHERE id=?",
                             (smap, 1 if args.confirm else row["map_confirmed"], row["id"]))
            print(f"{doc_id}: map {'confirmed' if args.confirm else 'stored'}")
            return 0
        parser.print_help()
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
