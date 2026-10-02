"""The Action Register CLI. REED drives it through Bash; nothing here guesses.

NEW in this repo. Blueprint s.1 and s.4 are the specification:

  Never invent owners, deadlines, decisions or completion. Unknown owners or dates
  stay VISIBLY unresolved, and a question is asked only when the answer matters.
  "I'll send Casey the bonus structure Friday" records Taylor as owner and the
  stated deadline, resolved against the actual instruction date and timezone; "do
  not guess if the intended Friday is ambiguous". One action per commitment, ever:
  completion, cancellation, reassignment, rescheduling, delegation and snoozes
  update the SAME action and keep its history. Speech-transcription variants of a
  name are aliases of an existing person, never a new person (G5).

So this file is deterministic by contract. The judgement (is this clause a topic,
a commitment, a completion?) is REED's, made with Taylor present. Everything after
that judgement is here, where it can be tested: the IDs, the date arithmetic, the
identity lookup, the history, the replay guard.

COMMANDS
    add-action      --text --owner <key|unresolved> --due <date|unresolved> [--due-note]
                    [--counterpart <key>] [--origin-kind chat] [--origin-ref ...]
                    [--instruction-date YYYY-MM-DD] [--no-question]
    add-topic       --person <key> --text [--side taylor|theirs] [--origin-ref ...]
    update-action   <ref> --field due_date|owner|status|snoozed_until|text --value V
                    --actor taylor|agent:reed|... [--source ...] [--note ...]
    complete        <ref> --via chat|doc [--actor ...] [--source ...]
    owed            [--person <key>] [--json]     Taylor's open commitments, by person
    morning         [--date YYYY-MM-DD]           the /morning screen, from the register only
    history         <ref>                         every change, and the move count
    needs-input     list | resolve <Q-ref> --answer "..." | add --question ...
    resolve-person  "<name as heard>"             resolved | ambiguous | unresolved
    resolve-date    "<phrase>" [--from YYYY-MM-DD] [--tz Zone]
    alias           --person <key> --add "<variant>"   a G5 correction, never a new row
    keep-private    <T-ref|A-ref>                 Taylor's private notes instead of a Doc
    seed            --roster                      load context/roster.json
    topics          [--person <key>] [--status queued|placed|...]
    show            <ref>
    --self-test

Exit codes: 0 ok, 1 not found or refused, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ea_db  # noqa: E402

REPO_ROOT = ea_db.REPO_ROOT
ROSTER_PATH = REPO_ROOT / "context" / "roster.json"
PRIVATE_NOTES = REPO_ROOT / "state" / "private" / "notes.md"
FIXTURE_PRIVATE_NOTES = REPO_ROOT / "state" / "private" / "fixture-notes.md"
PRIVATE_HEADER = ("<!-- ea-class: private -->\n# Private notes\n\n"
                  "Kept on this machine only and never written to a running Doc (blueprint section 2).\n\n")

PREFIXES = {"action": "A", "topic": "T", "question": "Q"}
ACTION_STATUSES = ("open", "done", "cancelled", "snoozed", "delegated")
TOPIC_SIDES = ("taylor", "theirs")

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


class RegisterError(Exception):
    """A request the register refuses, with the reason in words."""


# ---------------------------------------------------------------------------
# identity and time
# ---------------------------------------------------------------------------

def identity() -> dict:
    """context/identity.json with Taylor's overrides (state/taylor/identity.json) laid over it."""
    import overlay  # noqa: PLC0415

    try:
        return overlay.identity(REPO_ROOT)
    except overlay.OverlayUnreadable as exc:
        raise RegisterError(f"the identity file is unreadable ({exc}); the owner and the "
                            f"timezone cannot be known, so nothing is recorded") from exc


def zone(name: str | None = None):
    """The configured timezone. Windows needs the tzdata package for this to work."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415

    tz_name = name or identity().get("timezone") or "America/Toronto"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise RegisterError(f"timezone {tz_name!r} not found. On Windows install tzdata: "
                            f"python -m pip install tzdata") from exc


def today_local(tz_name: str | None = None) -> date:
    return datetime.now(zone(tz_name)).date()


def owner_key() -> str:
    return str(identity().get("owner_person_key") or "taylor")


def normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).rstrip(" .;,").casefold()


# ---------------------------------------------------------------------------
# refs and people
# ---------------------------------------------------------------------------

def next_ref(conn: sqlite3.Connection, kind: str) -> str:
    """The next stable human ID. Call inside the caller's transaction."""
    prefix = PREFIXES[kind]
    row = conn.execute("SELECT value FROM counters WHERE name = ?", (prefix,)).fetchone()
    value = (int(row["value"]) if row else 0) + 1
    conn.execute("INSERT INTO counters (name, value) VALUES (?, ?)"
                 " ON CONFLICT(name) DO UPDATE SET value = excluded.value", (prefix, value))
    return f"{prefix}-{value:04d}"


def person(conn: sqlite3.Connection, key: str | None) -> sqlite3.Row | None:
    if not key:
        return None
    return conn.execute("SELECT * FROM people WHERE key = ?", (key.strip().lower(),)).fetchone()


def require_person(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    row = person(conn, key)
    if row is None:
        known = ", ".join(r["key"] for r in conn.execute("SELECT key FROM people ORDER BY key"))
        raise RegisterError(f"no person with key {key!r}. Known keys: {known or 'none (run seed --roster)'}. "
                            f"Use resolve-person for a name as heard.")
    return row


def _name_forms(row: sqlite3.Row) -> dict[str, str]:
    """Every exact form that names this person, mapped to how it matched."""
    forms = {row["key"].casefold(): "key"}
    full = (row["full_name"] or "").strip()
    if full:
        forms.setdefault(full.casefold(), "full_name")
        forms.setdefault(full.split()[0].casefold(), "first_name")
    for alias in json.loads(row["aliases_json"] or "[]"):
        forms.setdefault(str(alias).strip().casefold(), "alias")
    return forms


def resolve_person(conn: sqlite3.Connection, heard: str) -> dict:
    """Exact lookup over key, full name, first name and aliases. NEVER fuzzy.

    A near-miss spelling ("Kade" when only "Cade" is a known alias) is unresolved on
    purpose: guessing a person is how an action lands in the wrong manager's Doc.
    Two people matching is `ambiguous`, with both named, so REED asks.
    """
    cleaned = re.sub(r"['’]s$", "", (heard or "").strip()).strip()
    probe = re.sub(r"\s+", " ", cleaned).casefold()
    if not probe:
        return {"status": "unresolved", "heard": heard, "reason": "empty name"}
    matches = []
    for row in conn.execute("SELECT * FROM people WHERE active = 1 ORDER BY key"):
        via = _name_forms(row).get(probe)
        if via:
            matches.append({"key": row["key"], "full_name": row["full_name"], "via": via})
    if len(matches) == 1:
        return {"status": "resolved", "heard": heard, **matches[0]}
    if len(matches) > 1:
        return {"status": "ambiguous", "heard": heard, "candidates": matches,
                "reason": f"{heard!r} names more than one person; ask which one"}
    return {"status": "unresolved", "heard": heard,
            "reason": f"{heard!r} matches no key, name or known alias. Ask; do not guess. "
                      f"If Taylor confirms who it is, record the variant with `alias`."}


def add_alias(conn: sqlite3.Connection, key: str, variant: str) -> dict:
    """A G5 correction: a transcription variant becomes a lookup, never a new person."""
    row = require_person(conn, key)
    variant = variant.strip()
    if not variant:
        raise RegisterError("the alias is empty")
    clash = resolve_person(conn, variant)
    if clash["status"] == "resolved" and clash["key"] != row["key"]:
        raise RegisterError(f"{variant!r} already resolves to {clash['key']}; one variant cannot "
                            f"name two people. Remove it there first.")
    aliases = json.loads(row["aliases_json"] or "[]")
    if variant.casefold() in {a.casefold() for a in aliases} or clash.get("key") == row["key"]:
        return {"key": row["key"], "alias": variant, "added": False}
    aliases.append(variant)
    with conn:
        conn.execute("UPDATE people SET aliases_json = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(aliases), ea_db.now_iso(), row["id"]))
    return {"key": row["key"], "alias": variant, "added": True}


def seed_roster(conn: sqlite3.Connection, path: Path = ROSTER_PATH) -> dict:
    """Insert missing people; fill blank fields; union aliases. Never deletes, never duplicates."""
    data = json.loads(path.read_bytes().decode("utf-8"))
    added, updated = [], []
    now = ea_db.now_iso()
    with conn:
        for entry in data.get("people") or []:
            key = str(entry["key"]).strip().lower()
            row = person(conn, key)
            if row is None:
                conn.execute(
                    "INSERT INTO people (key, full_name, work_email, role, aliases_json, cadence,"
                    " one_on_one, active, updated_at) VALUES (?,?,?,?,?,?,?,1,?)",
                    (key, entry.get("full_name") or key.title(), entry.get("work_email"),
                     entry.get("role"), json.dumps(entry.get("aliases") or []), entry.get("cadence"),
                     1 if entry.get("one_on_one") else 0, now))
                added.append(key)
                continue
            aliases = json.loads(row["aliases_json"] or "[]")
            merged = aliases + [a for a in entry.get("aliases") or []
                                if a.casefold() not in {x.casefold() for x in aliases}]
            changes = {
                "work_email": row["work_email"] or entry.get("work_email"),
                "role": row["role"] or entry.get("role"),
                "aliases_json": json.dumps(merged),
            }
            if (changes["work_email"] != row["work_email"] or changes["role"] != row["role"]
                    or merged != aliases):
                conn.execute("UPDATE people SET work_email=?, role=?, aliases_json=?, updated_at=?"
                             " WHERE id=?", (changes["work_email"], changes["role"],
                                             changes["aliases_json"], now, row["id"]))
                updated.append(key)
    return {"added": added, "updated": updated,
            "total": int(conn.execute("SELECT COUNT(*) FROM people").fetchone()[0])}


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------

def _next_weekday(after: date, weekday: int) -> date:
    """The first `weekday` strictly after `after`."""
    return after + timedelta(days=((weekday - after.weekday() - 1) % 7) + 1)


def resolve_date(phrase: str, from_date: date) -> dict:
    """Resolve a relative date phrase against the instruction date. Never guesses.

    Returns {"status": resolved|ambiguous|unresolved, "date", "candidates", "reason"}.
    A weekday named on that same weekday is AMBIGUOUS ("Friday" said on a Friday:
    today, or a week today?), and so is "next Friday" (the coming one, or the one
    after?). Blueprint s.4: do not guess if the intended Friday is ambiguous.
    """
    raw = (phrase or "").strip()
    p = re.sub(r"\s+", " ", raw.casefold()).strip(" .,")
    p = re.sub(r"^(by|on|due|for)\s+", "", p)
    out = {"phrase": raw, "from": from_date.isoformat(), "date": None, "candidates": []}

    def resolved(d: date, why: str) -> dict:
        return {**out, "status": "resolved", "date": d.isoformat(), "reason": why}

    def ambiguous(cands: list[date], why: str) -> dict:
        return {**out, "status": "ambiguous", "candidates": [c.isoformat() for c in cands], "reason": why}

    if not p:
        return {**out, "status": "unresolved", "reason": "no date was given"}
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
        try:
            return resolved(date.fromisoformat(p), "an explicit ISO date")
        except ValueError:
            return {**out, "status": "unresolved", "reason": f"{raw!r} is not a real date"}
    if p in ("today", "tonight", "end of day", "eod", "end of today"):
        return resolved(from_date, "today, the instruction date")
    if p == "tomorrow":
        return resolved(from_date + timedelta(days=1), "the day after the instruction date")
    match = re.fullmatch(r"in (\d{1,3}) (day|days|week|weeks)", p)
    if match:
        n = int(match.group(1)) * (7 if match.group(2).startswith("week") else 1)
        return resolved(from_date + timedelta(days=n), f"{n} days after the instruction date")

    match = re.fullmatch(r"(this |next )?([a-z]+)", p)
    if match and match.group(2) in WEEKDAYS:
        qualifier, wd = (match.group(1) or "").strip(), WEEKDAYS[match.group(2)]
        name = DAY_NAMES[wd]
        coming = _next_weekday(from_date, wd)
        if qualifier == "next":
            following = coming + timedelta(days=7)
            return ambiguous([coming, following],
                             f"'next {name}' said on a {DAY_NAMES[from_date.weekday()]} can mean "
                             f"{coming.isoformat()} or {following.isoformat()}")
        if from_date.weekday() == wd:
            if qualifier == "this":
                return resolved(from_date, f"'this {name}' said on a {name} is today")
            return ambiguous([from_date, coming],
                             f"the instruction was given on a {name}, so '{name}' can mean today "
                             f"({from_date.isoformat()}) or a week today ({coming.isoformat()})")
        if qualifier == "this" and wd < from_date.weekday():
            return ambiguous([coming], f"'this {name}' already passed this week")
        return resolved(coming, f"the first {name} after the instruction date "
                                f"({DAY_NAMES[from_date.weekday()]} {from_date.isoformat()})")

    if p in ("next week", "end of week", "eow", "end of the week", "this week", "later", "soon", "asap"):
        return {**out, "status": "unresolved", "reason": f"{raw!r} does not name a day"}

    match = re.fullmatch(r"([a-z]+)\.? (\d{1,2})(?:st|nd|rd|th)?|(\d{1,2})(?:st|nd|rd|th)? ([a-z]+)\.?", p)
    if match:
        month_word = match.group(1) or match.group(4)
        day_num = int(match.group(2) or match.group(3))
        if month_word in MONTHS:
            month = MONTHS[month_word]
            for year in (from_date.year, from_date.year + 1):
                try:
                    candidate = date(year, month, day_num)
                except ValueError:
                    return {**out, "status": "unresolved", "reason": f"{raw!r} is not a real date"}
                if candidate >= from_date:
                    return resolved(candidate, "a month and day, the next occurrence")
    return {**out, "status": "unresolved",
            "reason": f"{raw!r} is not a date phrase this resolver knows; keep it as a note and ask"}


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------

def meeting_for(conn: sqlite3.Connection, person_id: int | None) -> sqlite3.Row | None:
    """The person's 1:1 meeting row, if one is known. Never invented."""
    if person_id is None:
        return None
    return conn.execute(
        "SELECT * FROM meetings WHERE person_id = ? AND kind = '1on1'"
        " ORDER BY (next_at IS NULL), next_at LIMIT 1", (person_id,)).fetchone()


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------

def _capture_key(kind: str, who: str, text: str, instruction_date: str) -> str:
    material = json.dumps([kind, who, normalise_text(text), instruction_date], ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _event(conn, action_id: int, actor: str, field: str, old, new, source: str = "", note: str = "") -> None:
    conn.execute(
        "INSERT INTO action_events (action_id, ts, actor, field, old_value, new_value, source, note)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (action_id, ea_db.now_iso(), actor, field, None if old is None else str(old),
         None if new is None else str(new), source, note))


def _validate_iso(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise RegisterError(f"{value!r} is not a YYYY-MM-DD date. Resolve phrases with resolve-date first; "
                            f"if it cannot be resolved, use 'unresolved' and a --due-note") from exc


def add_action(conn: sqlite3.Connection, *, text: str, owner: str, due: str, due_note: str = "",
               counterpart: str | None = None, origin_kind: str = "chat", origin_ref: str = "",
               instruction_date: str | None = None, actor: str = "agent:reed",
               ask: bool = True) -> dict:
    """Record one commitment. Replaying the same capture returns the same ref."""
    text = (text or "").strip()
    if not text:
        raise RegisterError("an action needs text")
    instruction = instruction_date or today_local().isoformat()

    owner_row = None
    if owner != "unresolved":
        owner_row = require_person(conn, owner)
    counterpart_row = require_person(conn, counterpart) if counterpart else None
    due_date = None if due == "unresolved" else _validate_iso(due)

    key = _capture_key("action", counterpart or owner, text, instruction)
    existing = conn.execute("SELECT item_ref FROM captures WHERE idempotency_key = ?", (key,)).fetchone()
    if existing:
        return {"ref": existing["item_ref"], "created": False,
                "note": "already captured from the same words on the same day; nothing duplicated"}

    meeting = meeting_for(conn, counterpart_row["id"] if counterpart_row else None)
    now = ea_db.now_iso()
    with conn:
        ref = next_ref(conn, "action")
        cursor = conn.execute(
            "INSERT INTO actions (ref, text, owner_person_id, owner_unresolved, due_date,"
            " due_unresolved, due_note, status, counterpart_person_id, origin_kind, origin_ref,"
            " origin_at, meeting_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,'open',?,?,?,?,?,?,?)",
            (ref, text, owner_row["id"] if owner_row else None, 0 if owner_row else 1, due_date,
             0 if due_date else 1, due_note or None, counterpart_row["id"] if counterpart_row else None,
             origin_kind, origin_ref or None, now, meeting["id"] if meeting else None, now, now))
        action_id = int(cursor.lastrowid)
        _event(conn, action_id, actor, "created", None,
               f"owner={owner_row['key'] if owner_row else 'UNRESOLVED'} due={due_date or 'UNRESOLVED'}",
               source=f"{origin_kind}:{origin_ref}"[:200], note=f"instruction date {instruction}")
        conn.execute("INSERT INTO captures (idempotency_key, kind, item_ref, created_at) VALUES (?,?,?,?)",
                     (key, "action", ref, now))
        question_ref = None
        if ask and (owner_row is None or due_date is None):
            missing = [w for w, gap in (("who owns it", owner_row is None), ("when it is due", due_date is None)) if gap]
            question_ref = next_ref(conn, "question")
            conn.execute(
                "INSERT INTO needs_input (ref, question, context, source_kind, source_ref, action_id,"
                " asked_at, status) VALUES (?,?,?,?,?,?,?,'open')",
                (question_ref, f"{ref} '{text}': {' and '.join(missing)}?",
                 f"captured {instruction}; nothing was assumed. {('Note: ' + due_note) if due_note else ''}".strip(),
                 origin_kind, origin_ref or None, action_id, now))
    return {"ref": ref, "created": True, "owner": owner_row["key"] if owner_row else None,
            "due_date": due_date, "needs_input": question_ref,
            "meeting_id": meeting["id"] if meeting else None}


def add_topic(conn: sqlite3.Connection, *, person_key: str, text: str, side: str = "taylor",
              origin_kind: str = "chat", origin_ref: str = "", instruction_date: str | None = None) -> dict:
    """Queue a discussion topic for a person's next 1:1. Never an owner, never a date (P1.1)."""
    text = (text or "").strip()
    if not text:
        raise RegisterError("a topic needs text")
    if side not in TOPIC_SIDES:
        raise RegisterError(f"side must be one of {', '.join(TOPIC_SIDES)}")
    row = require_person(conn, person_key)
    if not row["one_on_one"]:
        raise RegisterError(f"{row['key']} has no running 1:1 with Taylor, so there is no next 1:1 "
                            f"to put a topic in. Ask where it belongs.")
    instruction = instruction_date or today_local().isoformat()
    key = _capture_key("topic", row["key"], text, instruction)
    existing = conn.execute("SELECT item_ref FROM captures WHERE idempotency_key = ?", (key,)).fetchone()
    if existing:
        return {"ref": existing["item_ref"], "created": False,
                "note": "already captured from the same words on the same day; nothing duplicated"}
    meeting = meeting_for(conn, row["id"])
    now = ea_db.now_iso()
    with conn:
        ref = next_ref(conn, "topic")
        conn.execute(
            "INSERT INTO topics (ref, person_id, meeting_id, text, side, status, origin_kind,"
            " origin_ref, created_at, updated_at) VALUES (?,?,?,?,?,'queued',?,?,?,?)",
            (ref, row["id"], meeting["id"] if meeting else None, text, side, origin_kind,
             origin_ref or None, now, now))
        conn.execute("INSERT INTO captures (idempotency_key, kind, item_ref, created_at) VALUES (?,?,?,?)",
                     (key, "topic", ref, now))
    return {"ref": ref, "created": True, "person": row["key"],
            "meeting_id": meeting["id"] if meeting else None,
            "next_at": meeting["next_at"] if meeting else None}


def action_by_ref(conn: sqlite3.Connection, ref: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM actions WHERE ref = ?", (ref.strip().upper(),)).fetchone()
    if row is None:
        raise RegisterError(f"no action {ref}")
    return row


def _maybe_close_question(conn, action: sqlite3.Row, actor: str) -> str | None:
    """Close the open question about an action once both its fields are known."""
    if action["owner_unresolved"] or action["due_unresolved"]:
        return None
    q = conn.execute("SELECT * FROM needs_input WHERE action_id = ? AND status = 'open'"
                     " ORDER BY id LIMIT 1", (action["id"],)).fetchone()
    if q is None:
        return None
    conn.execute("UPDATE needs_input SET status='resolved', resolved_at=?, resolution=? WHERE id=?",
                 (ea_db.now_iso(), f"answered by {actor}: owner and date now recorded", q["id"]))
    return q["ref"]


def update_action(conn: sqlite3.Connection, ref: str, field: str, value: str, *, actor: str,
                  source: str = "", note: str = "") -> dict:
    """Change one field of an existing action. Same row, plus one event. Never a second action."""
    action = action_by_ref(conn, ref)
    now = ea_db.now_iso()
    sets: dict[str, object]
    if field == "due_date":
        if value == "unresolved":
            old, new, sets = action["due_date"], None, {"due_date": None, "due_unresolved": 1}
        else:
            new = _validate_iso(value)
            old, sets = action["due_date"], {"due_date": new, "due_unresolved": 0}
    elif field == "owner":
        if value == "unresolved":
            old_row = conn.execute("SELECT key FROM people WHERE id=?", (action["owner_person_id"],)).fetchone()
            old, new, sets = old_row["key"] if old_row else None, None, {"owner_person_id": None, "owner_unresolved": 1}
        else:
            row = require_person(conn, value)
            old_row = conn.execute("SELECT key FROM people WHERE id=?", (action["owner_person_id"],)).fetchone()
            old, new, sets = old_row["key"] if old_row else None, row["key"], {"owner_person_id": row["id"], "owner_unresolved": 0}
    elif field == "status":
        if value not in ACTION_STATUSES:
            raise RegisterError(f"status must be one of {', '.join(ACTION_STATUSES)}")
        if value == "done":
            raise RegisterError("use `complete <ref> --via chat|doc`, which records how it was completed")
        old, new, sets = action["status"], value, {"status": value}
    elif field == "snoozed_until":
        new = _validate_iso(value)
        old, sets = action["snoozed_until"], {"snoozed_until": new, "status": "snoozed"}
    elif field == "text":
        new = (value or "").strip()
        if not new:
            raise RegisterError("text cannot be empty")
        old, sets = action["text"], {"text": new}
    else:
        raise RegisterError(f"cannot update field {field!r}. Fields: due_date, owner, status, snoozed_until, text")

    if old == new and field != "snoozed_until":
        return {"ref": action["ref"], "changed": False, "field": field, "value": new}
    with conn:
        assignments = ", ".join(f"{k} = ?" for k in sets) + ", updated_at = ?"
        conn.execute(f"UPDATE actions SET {assignments} WHERE id = ?", (*sets.values(), now, action["id"]))
        _event(conn, action["id"], actor, field, old, new, source, note)
        closed = _maybe_close_question(conn, action_by_ref(conn, ref), actor)
    return {"ref": action["ref"], "changed": True, "field": field, "old": old, "new": new,
            "question_closed": closed}


def complete(conn: sqlite3.Connection, ref: str, *, via: str, actor: str, source: str = "",
             note: str = "") -> dict:
    if via not in ("chat", "doc"):
        raise RegisterError("--via must be chat or doc")
    action = action_by_ref(conn, ref)
    if action["status"] == "done":
        return {"ref": action["ref"], "changed": False, "status": "done",
                "completed_via": action["completed_via"]}
    now = ea_db.now_iso()
    with conn:
        conn.execute("UPDATE actions SET status='done', completed_at=?, completed_via=?, updated_at=?"
                     " WHERE id=?", (now, via, now, action["id"]))
        _event(conn, action["id"], actor, "status", action["status"], "done", source, note or f"completed via {via}")
    return {"ref": action["ref"], "changed": True, "status": "done", "completed_via": via}


def private_notes_path() -> Path:
    """Taylor's private notes; the fixture world keeps its own, so a test never writes into his."""
    return FIXTURE_PRIVATE_NOTES if ea_db.fixture_mode() else PRIVATE_NOTES


def _append_private(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as handle:
        if handle.tell() == 0:
            handle.write(PRIVATE_HEADER.encode("utf-8"))
        handle.write((line + "\n").encode("utf-8"))


def keep_private(conn: sqlite3.Connection, ref: str, *, actor: str = "taylor", notes_path: Path | None = None) -> dict:
    """Keep an item in Taylor's private notes instead of a manager-readable Doc (blueprint s.2).

    What SAGE offers after a hold, carried out only when Taylor says yes. One line
    goes into the private notes (state/private), and any proposal still waiting to
    put the item into a Doc is withdrawn, so WREN can never deliver it later. A topic
    leaves the agenda queue ('dropped'); an action stays open in the register,
    because the commitment is still real and only its place in the Doc is given up.
    Nothing is deleted. An item already placed in a Doc is refused: keeping it
    private now would not take the line back out, and saying so is the honest answer.
    """
    ref = ref.strip().upper()
    if ref.startswith("T-"):
        row = conn.execute("SELECT t.*, p.key AS person FROM topics t JOIN people p ON p.id = t.person_id"
                           " WHERE t.ref = ?", (ref,)).fetchone()
        if row is None:
            raise RegisterError(f"no topic {ref}")
        if row["status"] == "placed":
            raise RegisterError(f"{ref} is already in {row['person'].title()}'s Doc; keeping it private now would "
                                f"not take that line out. Ask Taylor what he wants done with it.")
        what, person, text, action_id = "topic", row["person"], row["text"], None
    elif ref.startswith("A-"):
        row = action_by_ref(conn, ref)
        if conn.execute("SELECT 1 FROM doc_items WHERE item_kind = 'action' AND item_ref = ?", (ref,)).fetchone():
            raise RegisterError(f"{ref} is already in a Doc; keeping it private now would not take that row out. "
                                f"Ask Taylor what he wants done with it.")
        what, text, action_id = "action", row["text"], row["id"]
        person = _person_key(conn, row["counterpart_person_id"] or row["owner_person_id"]) or "no person"
    else:
        raise RegisterError("keep-private takes a topic (T-0000) or an action (A-0000) ref")

    hold = conn.execute("SELECT category, reason FROM privacy_reviews WHERE item_ref = ? AND verdict = 'hold'"
                        " ORDER BY id DESC LIMIT 1", (ref,)).fetchone()
    line = f"- {today_local().isoformat()}, {person.title()} ({what} {ref}): {text}"
    if hold:
        line += f" SAGE held it ({hold['category']}): {hold['reason']}"
    path = notes_path or private_notes_path()
    # The private copy is written before the queue entry is withdrawn, so a failure
    # in between leaves the item queued (and visible) rather than nowhere.
    _append_private(path, line)
    now = ea_db.now_iso()
    with conn:
        withdrawn = conn.execute("UPDATE proposals SET status = 'superseded', error = ? WHERE item_ref = ?"
                                 " AND status IN ('pending', 'failed')",
                                 ("kept private at Taylor's request", ref)).rowcount
        if what == "topic":
            conn.execute("UPDATE topics SET status = 'dropped', last_error = NULL, updated_at = ? WHERE ref = ?",
                         (now, ref))
        else:
            _event(conn, action_id, actor, "doc", None, "kept private", source="chat",
                   note="not placed in a Doc, at Taylor's request")
    return {"ref": ref, "kept_private": True, "notes": path.relative_to(REPO_ROOT).as_posix()
            if path.is_relative_to(REPO_ROOT) else str(path), "proposals_withdrawn": withdrawn,
            "topic_status": "dropped" if what == "topic" else None}


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------

def _person_key(conn, person_id) -> str | None:
    if person_id is None:
        return None
    row = conn.execute("SELECT key FROM people WHERE id = ?", (person_id,)).fetchone()
    return row["key"] if row else None


def owed(conn: sqlite3.Connection, person_key: str | None = None) -> dict:
    """Taylor's open commitments by person, then what is unresolved, then open questions."""
    me = person(conn, owner_key())
    filter_id = require_person(conn, person_key)["id"] if person_key else None
    rows = conn.execute(
        "SELECT * FROM actions WHERE status IN ('open','snoozed') ORDER BY (due_date IS NULL), due_date, ref"
    ).fetchall()
    by_person: dict[str, list] = {}
    unresolved = []
    for row in rows:
        if filter_id is not None and filter_id not in (row["counterpart_person_id"], row["owner_person_id"]):
            continue
        item = {"ref": row["ref"], "text": row["text"], "due_date": row["due_date"],
                "due_note": row["due_note"], "status": row["status"],
                "owner": _person_key(conn, row["owner_person_id"]),
                "counterpart": _person_key(conn, row["counterpart_person_id"])}
        if row["owner_unresolved"] or row["due_unresolved"]:
            unresolved.append({**item, "owner_unresolved": bool(row["owner_unresolved"]),
                               "due_unresolved": bool(row["due_unresolved"])})
            if row["owner_unresolved"]:
                continue
        if me is not None and row["owner_person_id"] == me["id"]:
            by_person.setdefault(item["counterpart"] or "(no person)", []).append(item)
    questions = [dict(q) for q in conn.execute(
        "SELECT ref, question, context, asked_at FROM needs_input WHERE status = 'open' ORDER BY id")]
    return {"owner": owner_key(), "by_person": by_person, "unresolved": unresolved, "needs_input": questions}


def history(conn: sqlite3.Connection, ref: str) -> dict:
    action = action_by_ref(conn, ref)
    events = [dict(e) for e in conn.execute(
        "SELECT ts, actor, field, old_value, new_value, source, note FROM action_events"
        " WHERE action_id = ? ORDER BY id", (action["id"],))]
    moves = sum(1 for e in events if e["field"] == "due_date" and e["old_value"] and e["new_value"])
    dated = sum(1 for e in events if e["field"] == "due_date")
    return {"ref": action["ref"], "text": action["text"], "status": action["status"],
            "due_date": action["due_date"], "completed_via": action["completed_via"],
            "moved": moves, "date_changes": dated, "events": events}


def morning(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Everything /morning shows, from the register and the audit table only. Read only.

    Order is the design: liveness first, because an empty list looks identical
    whether nothing is due or nothing has run for six days.
    """
    tz_name = identity().get("timezone") or "America/Toronto"
    tz = zone(tz_name)
    day = today or datetime.now(tz).date()
    out: dict = {"date": day.isoformat()}

    job = "ea_tick_fixtures" if ea_db.fixture_mode() else "ea_tick"
    tick = conn.execute("SELECT ts FROM job_ticks WHERE job = ? AND status = 'ok' ORDER BY ts DESC LIMIT 1",
                        (job,)).fetchone()
    if tick is None:
        out["tick_hours"] = None
    else:
        stamp = datetime.fromisoformat(tick["ts"])
        out["tick_hours"] = round((datetime.now(stamp.tzinfo) - stamp).total_seconds() / 3600.0, 1)
    marker = REPO_ROOT / "state" / "AUDIT-DEGRADED"
    out["audit_degraded"] = marker.exists()
    fx = 1 if ea_db.fixture_mode() else 0  # the fixture database shows its fixtures; the live one never does

    meetings = []
    for m in conn.execute("SELECT m.*, p.key, p.full_name FROM meetings m JOIN people p ON p.id = m.person_id"
                          " WHERE m.next_at IS NOT NULL AND m.fixture = ?", (fx,)):
        when = datetime.fromisoformat(m["next_at"]).astimezone(tz)
        if when.date() == day:
            doc = conn.execute("SELECT url FROM docs WHERE person_id = ? AND role = 'running_1on1' AND fixture = ?",
                               (m["person_id"], fx)).fetchone()
            meetings.append({"person": m["key"], "at": when.strftime("%H:%M"), "doc": doc["url"] if doc else None})
    out["meetings_today"] = meetings

    me = person(conn, owner_key())
    horizon = (day + timedelta(days=2)).isoformat()
    out["due_soon"] = [dict(r) for r in conn.execute(
        "SELECT ref, text, due_date, status FROM actions WHERE owner_person_id = ? AND status = 'open'"
        " AND due_date IS NOT NULL AND due_date <= ? ORDER BY due_date", (me["id"] if me else -1, horizon))]
    for item in out["due_soon"]:
        item["overdue"] = item["due_date"] < day.isoformat()
    out["doc_attention"] = [dict(r) for r in conn.execute(
        "SELECT i.item_ref, i.last_seen_state, d.title FROM doc_items i JOIN docs d ON d.doc_id = i.doc_id"
        " WHERE d.fixture = ? AND i.last_seen_state IN ('missing','ambiguous','unreadable') ORDER BY i.item_ref",
        (fx,))]
    out["needs_input"] = [dict(r) for r in conn.execute(
        "SELECT ref, question FROM needs_input WHERE status = 'open' ORDER BY id")]
    out["register_ahead"] = [dict(r) for r in conn.execute(
        "SELECT a.ref, a.text, d.title FROM actions a JOIN doc_items i ON i.item_ref = a.ref AND i.item_kind = 'action'"
        " JOIN docs d ON d.doc_id = i.doc_id WHERE a.status = 'done' AND a.completed_via = 'chat'"
        " AND i.last_seen_state = 'open' AND d.fixture = ?", (fx,))]
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    out["doc_writes_yesterday"] = [dict(r) for r in conn.execute(
        "SELECT ts, decision, rule_id, target, detail FROM audit WHERE hook = 'docs_edit' AND ts >= ? AND ts < ?"
        " ORDER BY ts", (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")))]
    return out


def render_morning(m: dict) -> str:
    rule = "=" * 60
    lines = [f"MORNING {m['date']}"]
    hours = m["tick_hours"]
    if hours is None or hours > 26:
        lines += [rule, "LAST TICK " + ("NEVER RECORDED" if hours is None else f"{hours / 24:.1f} DAYS AGO"),
                  "The background reconcile has not run. Everything below may be stale. Tell Mike.", rule]
    else:
        lines.append(f"tick OK ({hours:.0f}h ago)")
    if m["audit_degraded"]:
        lines += [rule, "AUDIT DEGRADED: decisions are not being fully recorded. Tell Mike.", rule]
    sections = [
        ("Today", [f"{x['at']}  {x['person'].title()}  {x['doc'] or '(no Doc linked)'}" for x in m["meetings_today"]]),
        ("Your actions due in 48h or overdue",
         [f"{x['ref']}  {'OVERDUE ' if x['overdue'] else ''}{x['due_date']}  {x['text']}" for x in m["due_soon"]]),
        ("Needs Your Input", [f"{x['ref']}  {x['question']}" for x in m["needs_input"]]),
        ("Doc items to look at", [f"{x['item_ref']}  {x['last_seen_state']}  in {x['title']}" for x in m["doc_attention"]]),
        ("Done in chat, not yet shown in the Doc", [f"{x['ref']}  {x['text']}  ({x['title']})" for x in m["register_ahead"]]),
        ("Doc writes yesterday", [f"{x['ts'][11:16]}Z  {x['decision']:<8} {x['rule_id']}  {(x['detail'] or '')[:70]}"
                                  for x in m["doc_writes_yesterday"]]),
    ]
    for title, items in sections:
        lines.append(title)
        lines += [f"  {item}" for item in items] or ["  nothing"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render_owed(result: dict) -> str:
    lines = [f"What {result['owner'].title()} owes"]
    if not result["by_person"]:
        lines.append("  nothing open")
    for who, items in sorted(result["by_person"].items()):
        lines.append(f"  {who.title()}")
        for item in items:
            due = item["due_date"] or "date unresolved"
            flag = "  (snoozed)" if item["status"] == "snoozed" else ""
            lines.append(f"    {item['ref']}  due {due}  {item['text']}{flag}")
    lines.append("Unresolved owner or date")
    if not result["unresolved"]:
        lines.append("  none")
    for item in result["unresolved"]:
        gaps = [g for g, on in (("owner", item["owner_unresolved"]), ("date", item["due_unresolved"])) if on]
        lines.append(f"    {item['ref']}  missing {' and '.join(gaps)}  {item['text']}")
    lines.append("Needs Your Input")
    if not result["needs_input"]:
        lines.append("  none open")
    for q in result["needs_input"]:
        lines.append(f"    {q['ref']}  {q['question']}")
    return "\n".join(lines)


def render_history(result: dict) -> str:
    lines = [f"{result['ref']}  {result['text']}",
             f"  status {result['status']}, due {result['due_date'] or 'unresolved'}",
             f"  moved {result['moved']} time(s)  (date changes recorded: {result['date_changes']})"]
    for e in result["events"]:
        change = f"{e['old_value']} -> {e['new_value']}" if e["old_value"] else (e["new_value"] or "")
        lines.append(f"  {e['ts']}  {e['actor']:<12} {e['field']:<10} {change}  {e['source'] or ''}".rstrip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def self_test() -> int:
    problems: list[str] = []

    def check(label: str, want, got) -> None:
        if want != got:
            problems.append(f"{label}: expected {want!r}, got {got!r}")

    with tempfile.TemporaryDirectory() as tmp:
        conn = ea_db.connect(Path(tmp) / "register-test.db")
        try:
            ea_db.migrate(conn)
            seeded = seed_roster(conn)
            check("seed loads the roster", 8, seeded["total"])
            check("re-seeding duplicates nobody", 8, seed_roster(conn)["total"])

            # Dates. The first two are pinned by the orchestrator: 2026-10-01 is a Thursday.
            thu, fri = date(2026, 10, 1), date(2026, 10, 2)
            for label, phrase, start, status, value in [
                ("Friday from Thursday 2026-10-01 is 2026-10-02 (P1.2)", "Friday", thu, "resolved", "2026-10-02"),
                ("Thursday said on Thursday 2026-10-01 is ambiguous", "Thursday", thu, "ambiguous", None),
                ("Friday said on a Friday is ambiguous (P1.3)", "Friday", fri, "ambiguous", None),
                ("by Friday from Thursday", "by Friday", thu, "resolved", "2026-10-02"),
                ("next Friday is ambiguous", "next Friday", thu, "ambiguous", None),
                ("this Friday from Thursday", "this Friday", thu, "resolved", "2026-10-02"),
                ("tomorrow", "tomorrow", thu, "resolved", "2026-10-02"),
                ("an explicit date", "2026-10-09", thu, "resolved", "2026-10-09"),
                ("month and day", "Oct 9", thu, "resolved", "2026-10-09"),
                ("in 2 weeks", "in 2 weeks", thu, "resolved", "2026-10-15"),
                ("no date chosen", "we haven't chosen a date", thu, "unresolved", None),
                ("next week names no day", "next week", thu, "unresolved", None),
            ]:
                result = resolve_date(phrase, start)
                check(f"resolve-date {label} (status)", status, result["status"])
                check(f"resolve-date {label} (date)", value, result["date"])

            # People. Exact lookups only.
            for label, heard, status, key in [
                ("a first name", "Kaed", "resolved", "kaed"),
                ("case-insensitive", "kaed", "resolved", "kaed"),
                ("a possessive", "Kaed's", "resolved", "kaed"),
                ("a known alias (G5)", "Cade", "resolved", "kaed"),
                ("a near-miss is NOT fuzzy-matched (G5)", "Kade", "unresolved", None),
                ("nobody in particular", "Someone", "unresolved", None),
                ("the owner", "Taylor", "resolved", "taylor"),
            ]:
                result = resolve_person(conn, heard)
                check(f"resolve-person {label} (status)", status, result["status"])
                check(f"resolve-person {label} (key)", key, result.get("key"))
            people_before = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            add_alias(conn, "kaed", "Kade")
            check("a G5 correction makes the variant resolve", "kaed", resolve_person(conn, "Kade").get("key"))
            check("a G5 correction creates no person", people_before,
                  conn.execute("SELECT COUNT(*) FROM people").fetchone()[0])
            add_alias(conn, "casey", "KC")
            try:
                add_alias(conn, "tania", "KC")
                problems.append("one variant naming two people was accepted")
            except RegisterError:
                pass
            conn.execute("UPDATE people SET aliases_json = ? WHERE key = 'mark'", (json.dumps(["Cade"]),))
            conn.commit()
            check("two people answering to one variant is ambiguous", "ambiguous",
                  resolve_person(conn, "Cade")["status"])
            conn.execute("UPDATE people SET aliases_json = '[]' WHERE key = 'mark'")
            conn.commit()

            # P1.2: one Taylor action with the stated date, one Casey topic.
            a1 = add_action(conn, text="Send Casey the manager bonus structure", owner="taylor",
                            due="2026-10-02", due_note="Friday", counterpart="casey",
                            instruction_date="2026-10-01")
            check("the first action is A-0001", "A-0001", a1["ref"])
            check("a clear commitment asks nothing", None, a1["needs_input"])
            again = add_action(conn, text="Send Casey the manager bonus structure.", owner="taylor",
                               due="2026-10-02", counterpart="casey", instruction_date="2026-10-01")
            check("a replayed capture returns the same ref", ("A-0001", False), (again["ref"], again["created"]))
            check("a replayed capture adds no row", 1, conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0])
            t1 = add_topic(conn, person_key="casey", text="Manager bonus structure", instruction_date="2026-10-01")
            check("a topic is a topic", ("T-0001", True), (t1["ref"], t1["created"]))
            check("a topic creates no action", 1, conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0])
            try:
                add_topic(conn, person_key="moreen", text="x", instruction_date="2026-10-01")
                problems.append("a topic for someone with no 1:1 was accepted")
            except RegisterError:
                pass

            # P1.3: nothing invented, one question.
            a2 = add_action(conn, text="Follow up", owner="unresolved", due="unresolved",
                            due_note="we haven't chosen a date", instruction_date="2026-10-01")
            row = action_by_ref(conn, a2["ref"])
            check("unknown owner stays unresolved", (None, 1), (row["owner_person_id"], row["owner_unresolved"]))
            check("unknown date stays unresolved", (None, 1), (row["due_date"], row["due_unresolved"]))
            check("one clarification is opened", 1, conn.execute(
                "SELECT COUNT(*) FROM needs_input WHERE action_id = ? AND status='open'", (row["id"],)).fetchone()[0])

            # P1.5: two reschedules, one row, a move count of two.
            update_action(conn, "A-0001", "due_date", "2026-10-06", actor="taylor", source="chat")
            update_action(conn, "A-0001", "due_date", "2026-10-09", actor="taylor", source="chat")
            hist = history(conn, "A-0001")
            check("moved twice", 2, hist["moved"])
            check("still one action", 2, conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0])
            check("an unchanged value writes no event", False,
                  update_action(conn, "A-0001", "due_date", "2026-10-09", actor="taylor")["changed"])
            check("history still says two", 2, history(conn, "A-0001")["moved"])

            # Answering the question closes it; owed reflects it.
            update_action(conn, a2["ref"], "owner", "kaed", actor="taylor")
            closed = update_action(conn, a2["ref"], "due_date", "2026-10-07", actor="taylor")
            check("answering both fields closes the question", "Q-0001", closed["question_closed"])
            result = owed(conn)
            check("owed lists Taylor's open action under Casey", ["A-0001"],
                  [i["ref"] for i in result["by_person"].get("casey", [])])
            check("Kaed's action is not Taylor's", [], [i["ref"] for i in result["by_person"].get("kaed", [])])

            # Completion keeps history and leaves owed.
            complete(conn, "A-0001", via="chat", actor="taylor")
            check("complete records the channel", ("done", "chat"),
                  tuple(action_by_ref(conn, "A-0001")[k] for k in ("status", "completed_via")))
            check("completed work leaves owed", [], [i["ref"] for items in owed(conn)["by_person"].values() for i in items])
            check("completed work stays queryable", "done", history(conn, "A-0001")["status"])

            # Kept private instead of a Doc: the topic leaves the queue, the words go to the notes.
            notes = Path(tmp) / "private-notes.md"
            kept = keep_private(conn, "T-0001", notes_path=notes)
            check("keep-private drops the topic from the Doc queue", "dropped",
                  conn.execute("SELECT status FROM topics WHERE ref = 'T-0001'").fetchone()[0])
            written = notes.read_text(encoding="utf-8")
            check("keep-private writes a declared private note", (True, True),
                  ("ea-class: private" in written, "Manager bonus structure" in written))
            check("keep-private reports where it wrote", str(notes), kept["notes"])

            # Refs are never reused.
            a3 = add_action(conn, text="Another", owner="taylor", due="2026-10-20", instruction_date="2026-10-01")
            check("refs keep counting", "A-0003", a3["ref"])
            keep_private(conn, "A-0003", notes_path=notes)
            check("a commitment kept private is still owed", "open", action_by_ref(conn, "A-0003")["status"])
            for bad_field in ("priority", "id"):
                try:
                    update_action(conn, "A-0003", bad_field, "x", actor="taylor")
                    problems.append(f"update of {bad_field} was accepted")
                except RegisterError:
                    pass
        finally:
            conn.close()

    if problems:
        print(f"SELF-TEST FAIL -- {len(problems)} problem(s):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("SELF-TEST OK -- register: dates (incl. Friday from Thursday 2026-10-01 -> 2026-10-02 and "
          "Thursday-on-Thursday ambiguous), identity (alias, near-miss, ambiguity, G5 correction), "
          "idempotent capture, unresolved fields with one question, move count 2, completion history, "
          "keep-private")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _emit(obj, as_json: bool, text: str | None = None) -> None:
    if as_json or text is None:
        sys.stdout.buffer.write((json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
    else:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    parser = argparse.ArgumentParser(description="The Action Register.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add-action")
    p.add_argument("--text", required=True)
    p.add_argument("--owner", required=True, help="person key, or 'unresolved'")
    p.add_argument("--due", required=True, help="YYYY-MM-DD, or 'unresolved'")
    p.add_argument("--due-note", default="")
    p.add_argument("--counterpart", help="whose 1:1 this belongs to")
    p.add_argument("--origin-kind", default="chat")
    p.add_argument("--origin-ref", default="")
    p.add_argument("--instruction-date")
    p.add_argument("--actor", default="agent:reed")
    p.add_argument("--no-question", action="store_true")

    p = sub.add_parser("add-topic")
    p.add_argument("--person", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--side", default="taylor", choices=TOPIC_SIDES)
    p.add_argument("--origin-kind", default="chat")
    p.add_argument("--origin-ref", default="")
    p.add_argument("--instruction-date")

    p = sub.add_parser("update-action")
    p.add_argument("ref")
    p.add_argument("--field", required=True)
    p.add_argument("--value", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--source", default="")
    p.add_argument("--note", default="")

    p = sub.add_parser("complete")
    p.add_argument("ref")
    p.add_argument("--via", required=True, choices=("chat", "doc"))
    p.add_argument("--actor", default="taylor")
    p.add_argument("--source", default="")

    p = sub.add_parser("owed")
    p.add_argument("--person")
    p.add_argument("history_ref", nargs="*", help="`owed history <ref>` is accepted as a synonym of `history <ref>`")

    p = sub.add_parser("history")
    p.add_argument("ref")

    p = sub.add_parser("needs-input")
    nsub = p.add_subparsers(dest="ncmd", required=True)
    nsub.add_parser("list")
    r = nsub.add_parser("resolve")
    r.add_argument("ref")
    r.add_argument("--answer", required=True)
    r.add_argument("--actor", default="taylor")
    a = nsub.add_parser("add")
    a.add_argument("--question", required=True)
    a.add_argument("--context", default="")
    a.add_argument("--action")
    a.add_argument("--source-kind", default="chat")
    a.add_argument("--source-ref", default="")

    p = sub.add_parser("resolve-person")
    p.add_argument("name")

    p = sub.add_parser("resolve-date")
    p.add_argument("phrase")
    p.add_argument("--from", dest="from_date")
    p.add_argument("--tz")

    p = sub.add_parser("alias")
    p.add_argument("--person", required=True)
    p.add_argument("--add", required=True)

    p = sub.add_parser("keep-private")
    p.add_argument("ref")
    p.add_argument("--actor", default="taylor")

    p = sub.add_parser("seed")
    p.add_argument("--roster", action="store_true", required=True)

    p = sub.add_parser("topics")
    p.add_argument("--person")
    p.add_argument("--status")

    p = sub.add_parser("show")
    p.add_argument("ref")

    p = sub.add_parser("morning")
    p.add_argument("--date")

    args = parser.parse_args()
    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        if args.cmd == "resolve-date":
            start = date.fromisoformat(args.from_date) if args.from_date else today_local(args.tz)
            result = resolve_date(args.phrase, start)
            _emit(result, args.json, f"{result['status']}: {result['date'] or ', '.join(result['candidates']) or '-'}"
                                     f"  ({result['reason']})")
            return 0
        if args.cmd == "resolve-person":
            result = resolve_person(conn, args.name)
            text = (f"resolved: {result['key']} (via {result['via']})" if result["status"] == "resolved"
                    else f"{result['status']}: {result.get('reason')}"
                    + ("" if result["status"] != "ambiguous"
                       else "  candidates: " + ", ".join(c["key"] for c in result["candidates"])))
            _emit(result, args.json, text)
            return 0 if result["status"] == "resolved" else 1
        if args.cmd == "seed":
            result = seed_roster(conn)
            _emit(result, args.json, f"people: {result['total']} (added {len(result['added'])}, "
                                     f"updated {len(result['updated'])})")
            return 0
        if args.cmd == "alias":
            result = add_alias(conn, args.person, args.add)
            _emit(result, args.json, f"{'added' if result['added'] else 'already known'}: "
                                     f"{result['alias']!r} -> {result['key']}")
            return 0
        if args.cmd == "keep-private":
            _emit(keep_private(conn, args.ref, actor=args.actor), True)
            return 0
        if args.cmd == "add-action":
            result = add_action(conn, text=args.text, owner=args.owner.lower(), due=args.due,
                                due_note=args.due_note, counterpart=args.counterpart,
                                origin_kind=args.origin_kind, origin_ref=args.origin_ref,
                                instruction_date=args.instruction_date, actor=args.actor,
                                ask=not args.no_question)
            _emit(result, True)
            return 0
        if args.cmd == "add-topic":
            result = add_topic(conn, person_key=args.person, text=args.text, side=args.side,
                               origin_kind=args.origin_kind, origin_ref=args.origin_ref,
                               instruction_date=args.instruction_date)
            _emit(result, True)
            return 0
        if args.cmd == "update-action":
            _emit(update_action(conn, args.ref, args.field, args.value, actor=args.actor,
                                source=args.source, note=args.note), True)
            return 0
        if args.cmd == "complete":
            _emit(complete(conn, args.ref, via=args.via, actor=args.actor, source=args.source), True)
            return 0
        if args.cmd == "owed":
            if args.history_ref:
                if args.history_ref[0] != "history" or len(args.history_ref) != 2:
                    parser.error("use `owed [--person KEY]` or `owed history <ref>`")
                result = history(conn, args.history_ref[1])
                _emit(result, args.json, render_history(result))
                return 0
            result = owed(conn, args.person)
            _emit(result, args.json, render_owed(result))
            return 0
        if args.cmd == "history":
            result = history(conn, args.ref)
            _emit(result, args.json, render_history(result))
            return 0
        if args.cmd == "needs-input":
            if args.ncmd == "list":
                rows = [dict(r) for r in conn.execute(
                    "SELECT ref, question, context, asked_at FROM needs_input WHERE status='open' ORDER BY id")]
                _emit(rows, args.json, "\n".join(f"{r['ref']}  {r['question']}" for r in rows) or "none open")
                return 0
            if args.ncmd == "resolve":
                row = conn.execute("SELECT * FROM needs_input WHERE ref = ?", (args.ref.upper(),)).fetchone()
                if row is None:
                    raise RegisterError(f"no question {args.ref}")
                if row["source_kind"] == "lesson" and row["status"] == "open":
                    # Resolved here, his yes would close the question and never adopt the rule.
                    raise RegisterError(f"{row['ref']} asks whether {row['source_ref']} becomes a rule; record "
                                        f"Taylor's answer with python scripts/lessons.py answer {row['source_ref']} "
                                        f"--yes (or --no), which closes this question too")
                with conn:
                    conn.execute("UPDATE needs_input SET status='resolved', resolved_at=?, resolution=? WHERE id=?",
                                 (ea_db.now_iso(), f"{args.actor}: {args.answer}", row["id"]))
                _emit({"ref": row["ref"], "status": "resolved"}, True)
                return 0
            action_id = action_by_ref(conn, args.action)["id"] if args.action else None
            with conn:
                ref = next_ref(conn, "question")
                conn.execute("INSERT INTO needs_input (ref, question, context, source_kind, source_ref,"
                             " action_id, asked_at, status) VALUES (?,?,?,?,?,?,?,'open')",
                             (ref, args.question, args.context, args.source_kind, args.source_ref,
                              action_id, ea_db.now_iso()))
            _emit({"ref": ref, "status": "open"}, True)
            return 0
        if args.cmd == "topics":
            sql, params = "SELECT t.*, p.key AS person FROM topics t JOIN people p ON p.id = t.person_id WHERE 1=1", []
            if args.person:
                sql += " AND p.key = ?"
                params.append(args.person.lower())
            if args.status:
                sql += " AND t.status = ?"
                params.append(args.status)
            rows = [dict(r) for r in conn.execute(sql + " ORDER BY t.id", params)]
            _emit(rows, args.json, "\n".join(
                f"{r['ref']}  {r['person']:<7} {r['status']:<8} {r['text']}" for r in rows) or "no topics")
            return 0
        if args.cmd == "morning":
            result = morning(conn, date.fromisoformat(args.date) if args.date else None)
            _emit(result, args.json, render_morning(result))
            return 0
        if args.cmd == "show":
            ref = args.ref.upper()
            table = {"A": "actions", "T": "topics", "Q": "needs_input"}.get(ref[:1])
            row = conn.execute(f"SELECT * FROM {table} WHERE ref = ?", (ref,)).fetchone() if table else None
            if row is None:
                raise RegisterError(f"nothing with ref {args.ref}")
            _emit(dict(row), True)
            return 0
    except RegisterError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())
