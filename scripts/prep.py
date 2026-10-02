"""Prep Taylor for a 1:1: the deeper on-demand briefing, his part first. Read only.

NEW in this repo, LARK's one script (deviation D-3: read-only prep, ahead of Phase 7).
Blueprint s.10: "'Prep me for Kaed' retrieves a deeper briefing on demand from the calendar,
working record, relevant history, actions, projects and authorized email context." So
asking for prep IS the deeper briefing, in this order:

    1. Taylor's part: what he owes that person (his open actions, counterpart = them), and
       what he must answer or decide (open Needs Your Input linked to them).
       "No outstanding prep." when both are empty.
    2. What they owe him (their open actions).
    3. Topics for the next 1:1, both sides, and whether each is in the Doc yet.
    4. From the Doc, as the background check last read it (the snapshot in the register):
       open rows it carries forward that the lists above do not already show, and what the
       last 1:1 recorded (its sections, and what was marked done).
    5. The next 1:1 time and the link to the running Doc.

Taylor's part only, with the rest on request, is test P3.7's rule for the 7AM BRIEF's meeting
entries (Phase 3, scripts/register.py morning), not for prep. Calendar beyond the next 1:1,
projects and email are Phase 4 and 7 sources and are not read here.

IT WRITES NO DATA, and that is enforced, not promised. The register is opened with a
read-only SQLite connection (mode=ro, in a URI built by Path.as_uri() so a '#' or '?'
in the path cannot cut it short and drop mode=ro) and never migrated, because a
migration is a write. A register that is not at this schema version is refused with
exit 3 rather than read half-built. No Doc is read: the Doc link and the next 1:1 time
come from the register, which the tick keeps current, and so do the Doc's carried-forward
rows and the last 1:1, read from the snapshot the tick stored. No audit row, no proposal.

WHAT SQLITE ITSELF MAY LEAVE, stated: the register runs in WAL mode, and when no other
connection has it open, opening it even read-only makes SQLite create its WAL index
files beside it (state/ea.db-wal, empty, and state/ea.db-shm, the shared-memory index).
They hold no data of their own and the next writer reuses them. So "writes nothing"
means the database file's bytes and the -wal's contents are unchanged: the acceptance
harness compares exactly those, lists both files before and after, and hashes the
register's logical contents, and it re-reads the Doc around a run to show it unchanged.

Usage (LARK):
    python scripts/prep.py --person Kaed            the briefing, Taylor's part first
    python scripts/prep.py --person kaed --json     everything, machine-readable
    (--deep is still accepted and changes nothing: the briefing is always the deep one)

Exit 0 printed; 1 the person is not one exact match; 2 the register does not exist;
3 the register exists but is not set up at this schema version, or cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docs_read  # noqa: E402  -- its pure parsing helpers only; nothing here reads a Doc
import ea_db  # noqa: E402
import register  # noqa: E402

OPEN = ("open", "snoozed")


class PrepRefused(Exception):
    """Nothing to print for the reason given; exit 1."""


def _actions(conn, where: str, params: tuple) -> list[dict]:
    rows = conn.execute(
        "SELECT ref, text, due_date, due_note, status, owner_unresolved, due_unresolved FROM actions"
        f" WHERE status IN ('open', 'snoozed') AND {where} ORDER BY (due_date IS NULL), due_date, ref", params)
    return [dict(r) for r in rows]


def build(conn, heard: str, today: date | None = None) -> dict:
    """Everything prep knows about one person, from the register only."""
    found = register.resolve_person(conn, heard)
    if found["status"] != "resolved":
        raise PrepRefused(found.get("reason") or f"{heard!r} is not one person on the roster")
    person = conn.execute("SELECT * FROM people WHERE key = ?", (found["key"],)).fetchone()
    me = conn.execute("SELECT * FROM people WHERE key = ?", (register.owner_key(),)).fetchone()
    tz_name = register.identity().get("timezone") or "America/Toronto"
    day = today or datetime.now(register.zone(tz_name)).date()
    fixture = 1 if ea_db.fixture_mode() else 0

    you_owe = _actions(conn, "owner_person_id = ? AND counterpart_person_id = ?",
                       (me["id"] if me else -1, person["id"])) if me else []
    they_owe = _actions(conn, "owner_person_id = ?", (person["id"],))
    to_answer = [dict(r) for r in conn.execute(
        "SELECT n.ref, n.question, n.asked_at FROM needs_input n"
        " LEFT JOIN actions a ON a.id = n.action_id LEFT JOIN topics t ON t.id = n.topic_id"
        " WHERE n.status = 'open' AND (a.counterpart_person_id = ? OR a.owner_person_id = ? OR t.person_id = ?)"
        " ORDER BY n.id", (person["id"], person["id"], person["id"]))]
    agenda = [dict(r) for r in conn.execute(
        "SELECT ref, text, side, status FROM topics WHERE person_id = ? AND status IN ('queued', 'placed')"
        " ORDER BY id", (person["id"],))]
    meeting = register.meeting_for(conn, person["id"])
    doc = conn.execute("SELECT doc_id, title, url, section_map_json FROM docs"
                       " WHERE person_id = ? AND role = 'running_1on1' AND fixture = ?",
                       (person["id"], fixture)).fetchone()
    snapshot = conn.execute("SELECT parsed_json, taken_at FROM doc_snapshots WHERE doc_id = ? ORDER BY id DESC LIMIT 1",
                            (doc["doc_id"],)).fetchone() if doc else None
    next_at = None
    if meeting is not None and meeting["next_at"]:
        moment = datetime.fromisoformat(meeting["next_at"]).astimezone(register.zone(tz_name))
        next_at = moment.strftime("%a %Y-%m-%d %H:%M ") + tz_name
    for item in you_owe + they_owe:
        item["overdue"] = bool(item["due_date"]) and item["due_date"] < day.isoformat()
    carried, last = [], []
    if snapshot is not None:
        try:
            parsed = json.loads(snapshot["parsed_json"])
            smap = json.loads(doc["section_map_json"] or "{}")
            carried, last = doc_history(parsed, smap, {i["ref"] for i in you_owe + they_owe})
        except (ValueError, KeyError, IndexError, TypeError):
            carried, last = None, None  # an unreadable snapshot is reported as such, never as "nothing"
    return {"person": person["key"], "name": (person["full_name"] or person["key"]).split()[0],
            "date": day.isoformat(), "next_1on1": next_at, "doc_url": doc["url"] if doc else None,
            "doc_title": doc["title"] if doc else None, "you_owe": you_owe, "to_answer": to_answer,
            "they_owe": they_owe, "agenda": agenda, "carried": carried, "last_1on1": last,
            "doc_read_at": (datetime.fromisoformat(snapshot["taken_at"]).astimezone(register.zone(tz_name))
                            .strftime("%a %Y-%m-%d") if snapshot is not None else None)}


REF = re.compile(r"\b[AT]-\d{4}\b")
HISTORY_LINES = 12


def _cell(row: dict, columns: dict, name: str) -> dict:
    index = columns.get(name)
    return row["cells"][index] if isinstance(index, int) and index < len(row["cells"]) else {"text": "", "chips": []}


def _rows(table: dict, header_row: int, columns: dict) -> list[tuple[str, str, str, str]]:
    """(assignee, title, date, open|checked|...) for every data row of an action table."""
    out = []
    for row in table["rows"][header_row + 1:]:
        title = _cell(row, columns, "title")["text"].strip()
        if not title:
            continue
        status = _cell(row, columns, "status")
        out.append((_cell(row, columns, "assignee")["text"].strip(), title, _cell(row, columns, "date")["text"].strip(),
                    docs_read.classify_status(status["text"], status.get("chips"))))
    return out


def doc_history(parsed: dict, smap: dict, listed: set[str]) -> tuple[list[dict], list[str]]:
    """(open rows the Doc carries into the next 1:1 that `listed` does not already show,
    what the last 1:1 recorded), from a stored snapshot of the running Doc."""
    if parsed.get("target_tab") is None or not parsed.get("blocks") or parsed.get("newest_block") is None:
        return [], []
    items = parsed["tabs"][parsed["target_tab"]]["items"]
    specs = smap.get("sections") or {}
    carried = []
    table = (parsed.get("sections") or {}).get("open_actions")
    if table and table.get("kind") == "table":
        columns = table.get("columns") or (specs.get("open_actions") or {}).get("columns") or {}
        for assignee, title, when, state in _rows(items[table["table_item"]], table["header_row"], columns):
            if state != "checked" and not set(REF.findall(title)) & listed:
                carried.append({"assignee": assignee, "title": title, "date": when})

    newest = parsed["newest_block"]
    previous = newest + 1 if (smap.get("block_order") or "newest_first") == "newest_first" else newest - 1
    if not 0 <= previous < len(parsed["blocks"]):
        return carried, []
    block = parsed["blocks"][previous]
    labels = [docs_read.norm(x) for x in smap.get("labels") or []]
    labels += [docs_read.norm(s.get("anchor") or "") for s in specs.values() if s.get("kind") != "table"]
    labels = [label for label in dict.fromkeys(labels) if label]
    last: list[str] = []
    for key, spec in specs.items():
        if spec.get("kind") == "table":
            header = [docs_read.norm(h) for h in spec.get("header") or []]
            for i in range(block["first_item"], block["end_item"]):
                it = items[i]
                if it["kind"] != "table" or not it["rows"]:
                    continue
                row_index = next((n for n, row in enumerate(it["rows"])
                                  if [docs_read.norm(c["text"]) for c in row["cells"]][:len(header)] == header), None)
                if row_index is None:
                    continue
                for assignee, title, when, state in _rows(it, row_index, spec.get("columns") or {}):
                    last.append(f"{'Done' if state == 'checked' else 'Open then'}: {title}"
                                + (f" ({assignee})" if assignee else ""))
                break
            continue
        label = docs_read.norm(spec.get("anchor") or "")
        anchor = next((i for i in range(block["first_item"], block["end_item"])
                       if docs_read._is_anchor(items[i], label)), None)
        if anchor is None:
            continue
        texts = []
        for i in range(anchor + 1, block["end_item"]):
            if docs_read._is_boundary(items[i], labels):
                break
            if items[i]["kind"] == "paragraph" and items[i]["text"].strip():
                texts.append(items[i]["text"].strip())
        if texts:
            last.append(f"{spec.get('anchor')}: " + "; ".join(texts))
    return carried, [line[:200] for line in last[:HISTORY_LINES]]


def _due(item: dict) -> str:
    if not item["due_date"]:
        return "date unresolved"
    return ("OVERDUE " if item["overdue"] else "due ") + item["due_date"]


def render(prep: dict) -> str:
    """The briefing, in blueprint s.10's order with Taylor's part first."""
    name = prep["name"]
    lines = [f"PREP {name}"]
    if not prep["you_owe"] and not prep["to_answer"]:
        lines.append("No outstanding prep.")
    if prep["you_owe"]:
        lines.append(f"You owe {name}")
        lines += [f"  {i['ref']}  {_due(i)}  {i['text']}" for i in prep["you_owe"]]
    if prep["to_answer"]:
        lines.append("You need to answer or decide")
        lines += [f"  {q['ref']}  {q['question']}" for q in prep["to_answer"]]
    lines.append(f"{name} owes you")
    lines += [f"  {i['ref']}  {_due(i)}  {i['text']}" for i in prep["they_owe"]] or ["  nothing open"]
    lines.append("Topics for the next 1:1")
    lines += [f"  {t['ref']}  {'yours' if t['side'] == 'taylor' else 'theirs'}, "
              f"{'in the Doc' if t['status'] == 'placed' else 'not in the Doc yet'}: {t['text']}"
              for t in prep["agenda"]] or ["  nothing queued"]
    read = f", as last read {prep['doc_read_at']}" if prep["doc_read_at"] else ""
    if prep["carried"] is None:
        lines.append("From the Doc: the stored copy could not be read, so nothing is shown from it. Tell Mike.")
    elif prep["doc_read_at"] is None:
        lines.append("From the Doc: not read yet; the background check reads it, and nothing is guessed meanwhile.")
    else:
        lines.append(f"Carried forward in the Doc{read}")
        lines += [f"  {c['assignee'] + ': ' if c['assignee'] else ''}{c['title']}" + (f" ({c['date']})" if c["date"] else "")
                  for c in prep["carried"]] or ["  nothing beyond the lists above"]
        lines.append(f"Last 1:1{read}")
        lines += [f"  {line}" for line in prep["last_1on1"]] or ["  no earlier 1:1 in the Doc"]
    lines.append(f"Next 1:1: {prep['next_1on1'] or 'none on record'}")
    lines.append(f"Doc: {prep['doc_url'] or 'no running Doc linked'}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--person", required=True, help="a person key, or a name as heard")
    parser.add_argument("--deep", action="store_true", help="accepted and ignored: the briefing is always the deep one")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--date", help="the day to prepare for (YYYY-MM-DD), default today")
    args = parser.parse_args()
    ea_db.console_utf8()
    if not ea_db.DB_PATH.exists():
        print(f"NO PREP: the register {ea_db.DB_PATH} does not exist yet.", file=sys.stderr)
        return 2
    conn = ea_db.connect(read_only=True)
    try:
        try:
            version = ea_db.user_version(conn)
        except sqlite3.Error as exc:
            print(f"NO PREP: the register {ea_db.DB_PATH} cannot be read ({exc}). Nothing was changed. "
                  f"Run python scripts/ea_doctor.py and send Mike the output.", file=sys.stderr)
            return 3
        if version != ea_db.SCHEMA_VERSION:
            print(f"NO PREP: the register {ea_db.DB_PATH} is not set up for this version (schema {version}, "
                  f"prep needs {ea_db.SCHEMA_VERSION}). Prep only reads, so it does not set it up; nothing was "
                  f"changed. Run python scripts/ea_doctor.py and send Mike the output.", file=sys.stderr)
            return 3
        prep = build(conn, args.person, date.fromisoformat(args.date) if args.date else None)
    except (PrepRefused, register.RegisterError) as exc:
        print(f"NO PREP: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(json.dumps(prep, indent=2, ensure_ascii=False) if args.json else render(prep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
