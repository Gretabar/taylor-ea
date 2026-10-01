"""Prep Taylor for a 1:1: what he owes, what he must answer or decide, and where the Doc is. Read only.

NEW in this repo, LARK's one script (deviation D-3: read-only prep, ahead of Phase 7).
Blueprint P3.7: "link the working Doc and show Taylor's answer only. A deeper briefing
is available on request." So the default output is exactly that:

    the next 1:1 with that person, and the link to the running Doc
    what Taylor owes that person            (his open actions, counterpart = them)
    what Taylor must answer or decide       (open Needs Your Input linked to them)
    "No outstanding prep." when both are empty (blueprint s.6)

and --deep adds what they owe Taylor and the topics on the agenda for the next 1:1.
Blueprint s.6 keeps employee action lists out of the brief; they are here only on
request, which is the "deeper briefing" P3.7 allows.

IT WRITES NOTHING, and that is enforced, not promised. The register is opened with a
read-only SQLite connection and never migrated (a migration is a write). No Doc is
read: the Doc link and the next 1:1 time come from the register, which the tick keeps
current. No audit row, no proposal, no file. The acceptance harness hashes the whole
register and re-reads the Doc around a run to show both unchanged.

Usage (LARK):
    python scripts/prep.py --person Kaed            the brief: Taylor's items only
    python scripts/prep.py --person kaed --deep     plus what Kaed owes, and the agenda
    python scripts/prep.py --person kaed --json     everything, machine-readable

Exit 0 printed; 1 the person is not one exact match; 2 the register does not exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    doc = conn.execute("SELECT title, url FROM docs WHERE person_id = ? AND role = 'running_1on1' AND fixture = ?",
                       (person["id"], fixture)).fetchone()
    next_at = None
    if meeting is not None and meeting["next_at"]:
        moment = datetime.fromisoformat(meeting["next_at"]).astimezone(register.zone(tz_name))
        next_at = moment.strftime("%a %Y-%m-%d %H:%M ") + tz_name
    for item in you_owe + they_owe:
        item["overdue"] = bool(item["due_date"]) and item["due_date"] < day.isoformat()
    return {"person": person["key"], "name": (person["full_name"] or person["key"]).split()[0],
            "date": day.isoformat(), "next_1on1": next_at, "doc_url": doc["url"] if doc else None,
            "doc_title": doc["title"] if doc else None, "you_owe": you_owe, "to_answer": to_answer,
            "they_owe": they_owe, "agenda": agenda}


def _due(item: dict) -> str:
    if not item["due_date"]:
        return "date unresolved"
    return ("OVERDUE " if item["overdue"] else "due ") + item["due_date"]


def render(prep: dict, deep: bool) -> str:
    name = prep["name"]
    lines = [f"PREP {name}",
             f"Next 1:1: {prep['next_1on1'] or 'none on record'}",
             f"Doc: {prep['doc_url'] or 'no running Doc linked'}"]
    if not prep["you_owe"] and not prep["to_answer"]:
        lines.append("No outstanding prep.")
    if prep["you_owe"]:
        lines.append(f"You owe {name}")
        lines += [f"  {i['ref']}  {_due(i)}  {i['text']}" for i in prep["you_owe"]]
    if prep["to_answer"]:
        lines.append("You need to answer or decide")
        lines += [f"  {q['ref']}  {q['question']}" for q in prep["to_answer"]]
    if not deep:
        more = []
        if prep["they_owe"]:
            more.append(f"what {name} owes you ({len(prep['they_owe'])})")
        if prep["agenda"]:
            more.append(f"the agenda for the next 1:1 ({len(prep['agenda'])})")
        if more:
            lines.append("On request: " + " and ".join(more) + ".")
        return "\n".join(lines)
    lines.append(f"{name} owes you")
    lines += [f"  {i['ref']}  {_due(i)}  {i['text']}" for i in prep["they_owe"]] or ["  nothing open"]
    lines.append("On the agenda for the next 1:1")
    lines += [f"  {t['ref']}  {'in the Doc' if t['status'] == 'placed' else 'not in the Doc yet'}, "
              f"{'yours' if t['side'] == 'taylor' else 'theirs'}: {t['text']}" for t in prep["agenda"]] or ["  nothing queued"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--person", required=True, help="a person key, or a name as heard")
    parser.add_argument("--deep", action="store_true", help="add what they owe and the agenda")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--date", help="the day to prepare for (YYYY-MM-DD), default today")
    args = parser.parse_args()
    ea_db.console_utf8()
    if not ea_db.DB_PATH.exists():
        print(f"NO PREP: the register {ea_db.DB_PATH} does not exist yet.", file=sys.stderr)
        return 2
    conn = ea_db.connect(read_only=True)
    try:
        prep = build(conn, args.person, date.fromisoformat(args.date) if args.date else None)
    except (PrepRefused, register.RegisterError) as exc:
        print(f"NO PREP: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(json.dumps(prep, indent=2, ensure_ascii=False) if args.json else render(prep, args.deep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
