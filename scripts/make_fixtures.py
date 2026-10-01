"""Create the fixture Docs the acceptance harness writes to, in the shape of the live ones.

NEW in this repo. Blueprint s.12: run acceptance "with controlled fixtures" and do
not send test messages to employees as if they were real. So nothing in a test
ever touches a live running Doc: the harness writes ONLY to Docs this script
created, registered as fixture=1 in state/fixtures.db, a database the live register
never sees.

THE SHAPE IS THE LIVE ONE, from the 2026-10-01 read-only inspection (structure
only, no content copied):
  three tabs: "RUNNING AGENDA" (the working tab), "Template", "One on One" (empty)
  newest-first meeting blocks, each under a HEADING_2 "RUNNING AGENDA:"
  bold numbered agenda items: "Wins + Challenges from the week (personal +
    professional)", "Follow-Ups: Updates + Action Items", "Feedback",
    "Strategic Priorities", with nested items under them
  the open-actions table under item 2: title row "Action Items", header
    "Assignee | Title | Date | Status", rows whose Date cell holds a DATE CHIP
  plain labels "Top Focuses" and "<Name> Notes", with bullets under them
Variations on purpose: Casey's newest "Top Focuses" is EMPTY (exercises the
empty-section write path); Kaed's history block carries a person chip and a rich
link chip (exercises the chip parser on every chip type).

SAFETY OF CHIPS. Person chips name only m.kelly@gretabar.com, the owner of these
Docs. An @-mention of Taylor or a manager from a fixture could notify them, which
would be a test message to a person.

BUILT IN ROUNDS, RE-READ BETWEEN EACH. Text and styles in one batch; tables where
the placeholders landed; cells and chips once the tables exist; then a verify pass
through scripts/docs_read.py with the same section map docs_edit.py will use. A
fixture that does not parse the way the live Docs parse is not registered.

Usage:
    python scripts/make_fixtures.py --create             build every missing fixture
    python scripts/make_fixtures.py --create --only kaed
    python scripts/make_fixtures.py --status
"""

from __future__ import annotations

import os

os.environ.setdefault("EA_FIXTURE_MODE", "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import calendar_next  # noqa: E402
import docs_read  # noqa: E402
import ea_db  # noqa: E402
import link_docs  # noqa: E402
import register  # noqa: E402

PEOPLE = (
    ("kaed", "Kaed", "weekly"),
    ("casey", "Casey", "biweekly"),
    ("tania", "Tania", "monthly"),
    ("shawn", "Shawn", "weekly"),
    ("mark", "Mark", "biweekly"),
    ("anya", "Anya", "monthly"),
)
CADENCE_DAYS = {"weekly": 7, "biweekly": 14, "monthly": "monthly"}
OWNER_CHIP_EMAIL = "m.kelly@gretabar.com"
TABLE_TOKEN = "<<TABLE>>"
LINK_TOKEN = "Reference doc: "
TABS = ("RUNNING AGENDA", "Template", "One on One")
SECTIONS = ("Wins + Challenges from the week (personal + professional)",
            "Follow-Ups: Updates + Action Items", "Feedback", "Strategic Priorities")


def section_map(first_name: str) -> dict:
    return {
        "version": 1, "tab_title": "RUNNING AGENDA", "block_heading": "RUNNING AGENDA:",
        "block_order": "newest_first", "ref_tokens": True,
        "labels": list(SECTIONS) + ["Top Focuses", f"{first_name} Notes"],
        "sections": {
            "wins": {"anchor": "Wins + Challenges", "kind": "list"},
            "open_actions": {"anchor": "Action Items", "kind": "table",
                             "header": ["Assignee", "Title", "Date", "Status"],
                             "columns": {"assignee": 0, "title": 1, "date": 2, "status": 3}},
            "feedback": {"anchor": "Feedback", "kind": "list"},
            "goals": {"anchor": "Strategic Priorities", "kind": "list"},
            "taylor_topics": {"anchor": "Top Focuses", "kind": "list"},
            "their_topics": {"anchor": f"{first_name} Notes", "kind": "list"},
        },
        "fixture_note": "taylor_topics -> 'Top Focuses' and their_topics -> '<Name> Notes' are the "
                        "fixture convention; the live mapping is confirmed with Taylor per Doc.",
    }


CHECKBOX_MAP = {
    "version": 1, "tab_title": "RUNNING AGENDA", "block_heading": "RUNNING AGENDA:",
    "block_order": "newest_first", "ref_tokens": True, "labels": ["Action checklist"],
    "sections": {"open_actions": {"anchor": "Action checklist", "kind": "checklist"}},
}


def block(first_name: str, *, history: bool, empty_focuses: bool) -> list[tuple[str, str]]:
    """(kind, text) paragraphs for one meeting block."""
    tag = "past meeting" if history else "fixture"
    out = [("H2", "RUNNING AGENDA:"),
           ("NUM0", SECTIONS[0]), ("NUM1", f"Wins placeholder ({tag})"),
           ("NUM0", SECTIONS[1]), ("TABLE", TABLE_TOKEN),
           ("NUM0", SECTIONS[2]), ("NUM1", f"Feedback placeholder ({tag})"),
           ("NUM0", SECTIONS[3]), ("NUM1", f"Priority placeholder ({tag})"),
           ("LABEL", "Top Focuses")]
    if not empty_focuses:
        out.append(("BUL", f"Focus placeholder ({tag})"))
    out += [("LABEL", f"{first_name} Notes"), ("BUL", f"Note placeholder ({tag})")]
    if history and first_name == "Kaed":
        out.append(("BUL", LINK_TOKEN))
    out.append(("BLANK", ""))
    return out


def template_block(first_name: str) -> list[tuple[str, str]]:
    return [("H2", "RUNNING AGENDA:"), ("NUM0", SECTIONS[0]), ("NUM0", SECTIONS[1]),
            ("TABLE", TABLE_TOKEN), ("NUM0", SECTIONS[2]), ("NUM0", SECTIONS[3]),
            ("LABEL", "Top Focuses"), ("LABEL", f"{first_name} Notes"), ("BLANK", "")]


CHECKBOX_BLOCK = [("H2", "RUNNING AGENDA:"), ("LABELB", "Action checklist"),
                  ("CHK", "Checkbox seed item one"), ("CHK", "Checkbox seed item two"), ("BLANK", "")]


# ---------------------------------------------------------------------------
# request building
# ---------------------------------------------------------------------------

def text_requests(spec: list[tuple[str, str]], tab_id: str) -> list[dict]:
    """insertText for the whole tab, then styles, then bullets from the END backwards.

    createParagraphBullets strips the leading tabs that set nesting level, which
    shifts every later index. Styles therefore go first, on the original offsets,
    and bullet ranges go last, latest first, so no range moves under another.
    """
    paragraphs, cursor = [], 1
    for kind, text in spec:
        body = ("\t" + text) if kind in ("NUM1", "TABLE") else text
        paragraphs.append({"kind": kind, "start": cursor, "text": body,
                           "end": cursor + docs_read.u16(body) + 1})
        cursor = paragraphs[-1]["end"]
    full = "".join(p["text"] + "\n" for p in paragraphs)
    requests = [{"insertText": {"location": {"index": 1, "tabId": tab_id}, "text": full}}]
    for p in paragraphs:
        rng = {"startIndex": p["start"], "endIndex": p["end"], "tabId": tab_id}
        if p["kind"] == "H2":
            requests.append({"updateParagraphStyle": {"range": rng, "paragraphStyle": {"namedStyleType": "HEADING_2"},
                                                      "fields": "namedStyleType"}})
        if p["kind"] in ("NUM0", "LABELB") and p["text"]:
            requests.append({"updateTextStyle": {"range": {**rng, "endIndex": p["end"] - 1},
                                                 "textStyle": {"bold": True}, "fields": "bold"}})
    groups, current = [], None
    for p in paragraphs:
        preset = {"NUM0": "NUMBERED_DECIMAL_ALPHA_ROMAN", "NUM1": "NUMBERED_DECIMAL_ALPHA_ROMAN",
                  "TABLE": "NUMBERED_DECIMAL_ALPHA_ROMAN", "BUL": "BULLET_DISC_CIRCLE_SQUARE",
                  "CHK": "BULLET_CHECKBOX"}.get(p["kind"])
        if preset and current and current["preset"] == preset:
            current["last"] = p
        elif preset:
            current = {"preset": preset, "first": p, "last": p}
            groups.append(current)
        else:
            current = None
    for group in sorted(groups, key=lambda g: g["first"]["start"], reverse=True):
        requests.append({"createParagraphBullets": {
            "range": {"startIndex": group["first"]["start"], "endIndex": group["last"]["start"] + 1, "tabId": tab_id},
            "bulletPreset": group["preset"]}})
    return requests


def date_chip(day: str, tz_name: str) -> dict:
    """Noon local on `day`, so the chip shows that date in every zone Taylor is likely in.

    timeZoneId is deliberately absent: the API rejects it unless the time format is
    TIME_FORMAT_HOUR_MINUTE_TIMEZONE ("Time zone ID must be unset if time format is
    not ..."), observed 2026-10-01. Noon local keeps the date right without it.
    """
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    moment = datetime.fromisoformat(day + "T12:00:00").replace(tzinfo=ZoneInfo(tz_name))
    return {"timestamp": moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "locale": "en", "dateFormat": "DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED",
            "timeFormat": "TIME_FORMAT_DISABLED"}


# ---------------------------------------------------------------------------
# API plumbing
# ---------------------------------------------------------------------------

def call(request, label: str):
    """Execute with backoff on 429 and 5xx. Anything else is raised, named."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    for attempt in range(6):
        try:
            return request.execute()
        except HttpError as exc:
            status = int(getattr(exc.resp, "status", 0) or 0)
            if status in (429, 500, 502, 503) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{label}: HTTP {status}: {exc}") from exc
    raise RuntimeError(f"{label}: gave up after retries")


def batch(service, doc_id: str, requests: list[dict], label: str) -> dict:
    if not requests:
        return {}
    return call(service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}), label)


def get(service, doc_id: str) -> dict:
    return call(service.documents().get(documentId=doc_id, includeTabsContent=True), f"get {doc_id}")


def tab_ids(document: dict) -> dict[str, str]:
    return {t["tabProperties"]["title"]: t["tabProperties"]["tabId"] for t in document.get("tabs") or []}


def place_tables(service, doc_id: str, document: dict) -> None:
    """Swap each placeholder paragraph for a 4-column table, latest first."""
    requests = []
    targets = []
    for tab in docs_read.flatten_tabs(document):
        for item in tab["items"]:
            if item["kind"] == "paragraph" and item["text"].strip() == TABLE_TOKEN:
                targets.append((tab["tab_id"], item, tab["title"]))
    for tab_id, item, title in sorted(targets, key=lambda t: t[1]["start"], reverse=True):
        rows = 2 if title == "Template" else 3
        rng = {"startIndex": item["start"], "endIndex": item["end"], "tabId": tab_id}
        requests += [
            {"deleteParagraphBullets": {"range": rng}},
            {"deleteContentRange": {"range": {**rng, "endIndex": item["end"] - 1}}},
            {"insertTable": {"rows": rows, "columns": 4, "location": {"index": item["start"], "tabId": tab_id}}},
        ]
    batch(service, doc_id, requests, "place tables")


def fill_tables(service, doc_id: str, document: dict, tz_name: str) -> None:
    """Title row, header row and one seed row per table. Every cell latest first."""
    requests = []
    for tab in docs_read.flatten_tabs(document):
        tables = [it for it in tab["items"] if it["kind"] == "table"]
        for position, table in sorted(enumerate(tables), key=lambda t: t[1]["start"], reverse=True):
            history = tab["title"] == "RUNNING AGENDA" and position > 0
            plan = [["Action Items", "", "", ""], ["Assignee", "Title", "Date", "Status"]]
            if tab["title"] == "RUNNING AGENDA":
                plan.append([("person", OWNER_CHIP_EMAIL) if history else "",
                             "Past fixture action (no register row)" if history else "Seed fixture action (no register row)",
                             ("date", "2026-09-25" if history else "2026-10-09"),
                             "Done" if history else ""])
            for r in range(len(table["rows"]) - 1, -1, -1):
                for c in range(len(table["rows"][r]["cells"]) - 1, -1, -1):
                    value = plan[r][c] if r < len(plan) else ""
                    index = table["rows"][r]["cells"][c]["paragraphs"][0]["start"]
                    loc = {"index": index, "tabId": tab["tab_id"]}
                    if isinstance(value, tuple) and value[0] == "date":
                        requests.append({"insertDate": {"location": loc, "dateElementProperties": date_chip(value[1], tz_name)}})
                    elif isinstance(value, tuple) and value[0] == "person":
                        requests.append({"insertPerson": {"location": loc, "personProperties": {"email": value[1]}}})
                    elif value:
                        requests.append({"insertText": {"location": loc, "text": value}})
    batch(service, doc_id, requests, "fill tables")


def add_rich_link(service, doc_id: str, document: dict) -> None:
    """One rich-link chip, so the parser is proven on every chip type.

    insertRichLink needs a Drive scope ("The request scopes are not sufficient for
    reading from Drive", observed 2026-10-01). Taylor's Phase 1 consent has none, so
    on his machine this is skipped with a note; reading a rich link needs only the
    documents scope.
    """
    import google_creds  # noqa: PLC0415

    drive_scope = next((s for s in (google_creds.DRIVE_FILE, google_creds.DRIVE)
                        if s in google_creds.granted_scopes()), None)
    if drive_scope is None:
        print("  note: no Drive scope on this token; the rich-link chip is skipped")
        return
    service = google_creds.service("docs", "v1", [google_creds.DOCUMENTS, drive_scope])
    for tab in docs_read.flatten_tabs(document):
        for item in tab["items"]:
            if item["kind"] == "paragraph" and item["text"].startswith(LINK_TOKEN.strip()):
                batch(service, doc_id, [{"insertRichLink": {
                    "location": {"index": item["end"] - 1, "tabId": tab["tab_id"]},
                    "richLinkProperties": {"uri": f"https://docs.google.com/document/d/{doc_id}/edit"}}}],
                      "rich link")
                return


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------

def build_person_doc(service, first_name: str, tz_name: str, *, title: str, empty_focuses: bool) -> str:
    created = call(service.documents().create(body={"title": title}), "create")
    doc_id = created["documentId"]
    first_tab = tab_ids(get(service, doc_id))
    t0 = next(iter(first_tab.values()))
    batch(service, doc_id, [
        {"updateDocumentTabProperties": {"tabProperties": {"tabId": t0, "title": TABS[0]}, "fields": "title"}},
        {"addDocumentTab": {"tabProperties": {"title": TABS[1], "index": 1}}},
        {"addDocumentTab": {"tabProperties": {"title": TABS[2], "index": 2}}},
    ], "tabs")
    ids = tab_ids(get(service, doc_id))
    working = block(first_name, history=False, empty_focuses=empty_focuses) + \
        block(first_name, history=True, empty_focuses=False)
    batch(service, doc_id, text_requests(working, ids[TABS[0]]) +
          text_requests(template_block(first_name), ids[TABS[1]]), "text")
    place_tables(service, doc_id, get(service, doc_id))
    fill_tables(service, doc_id, get(service, doc_id), tz_name)
    add_rich_link(service, doc_id, get(service, doc_id))
    return doc_id


def build_checkbox_doc(service, title: str) -> str:
    created = call(service.documents().create(body={"title": title}), "create")
    doc_id = created["documentId"]
    t0 = next(iter(tab_ids(get(service, doc_id)).values()))
    batch(service, doc_id, [{"updateDocumentTabProperties": {"tabProperties": {"tabId": t0, "title": TABS[0]},
                                                             "fields": "title"}}], "tab")
    batch(service, doc_id, text_requests(CHECKBOX_BLOCK, t0), "text")
    return doc_id


def verify(service, doc_id: str, smap: dict, expect_table: bool) -> dict:
    """Parse the new Doc with the map docs_edit.py will use. Raises when it does not match."""
    document = get(service, doc_id)
    parsed = docs_read.parse(document, smap)
    problems = []
    if not parsed["editable"]:
        problems.append("no revisionId returned: this account cannot edit its own fixture")
    if parsed["unmapped"]:
        problems.append(f"unmapped sections: {parsed['unmapped']}")
    if expect_table:
        titles = [t["title"] for t in parsed["tabs"]]
        if titles[:3] != list(TABS):
            problems.append(f"tabs are {titles}")
        if len(parsed["blocks"]) != 2:
            problems.append(f"{len(parsed['blocks'])} meeting blocks, expected 2")
        rows = docs_read._section_rows(parsed, "open_actions")  # noqa: SLF001
        if not rows or not any(c.get("type") == "date" for _, r in rows for c in r["cells"][2]["chips"]):
            problems.append("the newest Action Items table has no row with a date chip")
    if problems:
        raise RuntimeError(f"fixture {doc_id} does not parse like a live Doc: " + "; ".join(problems))
    return parsed


def seed_meeting(conn, key: str, cadence: str, tz_name: str, now: datetime) -> int:
    """A fixture meeting from a synthetic events.instances response: last yesterday, next one gap on."""
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    yesterday = (now.astimezone(ZoneInfo(tz_name)) - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    if CADENCE_DAYS[cadence] == "monthly":
        yesterday = yesterday.replace(day=min(yesterday.day, 28))  # every month has a 28th
    every = CADENCE_DAYS[cadence]
    if every == "monthly":
        first = yesterday.replace(month=yesterday.month - 1) if yesterday.month > 1 else yesterday.replace(year=yesterday.year - 1, month=12)
    else:
        first = yesterday - timedelta(days=every)
    response = calendar_next.synthetic_instances(first, every, 6, series_id=f"fixture-{key}")
    result = calendar_next.next_meeting(response, now, tz_name)
    records = ea_db.REPO_ROOT / "state" / "records" / "fixture-calendar"
    records.mkdir(parents=True, exist_ok=True)
    (records / f"{key}.json").write_text(json.dumps({"ea-class": "records", "response": response}, indent=1),
                                         encoding="utf-8")
    pid = conn.execute("SELECT id FROM people WHERE key = ?", (key,)).fetchone()["id"]
    with conn:
        conn.execute(
            "INSERT INTO meetings (person_id, kind, calendar_id, series_event_id, next_event_id, next_at,"
            " cadence_observed, timezone, refreshed_at, source, fixture, note)"
            " VALUES (?, '1on1', 'fixture', ?, ?, ?, ?, ?, ?, 'fixture', 1, ?)"
            " ON CONFLICT(calendar_id, series_event_id) DO UPDATE SET next_event_id=excluded.next_event_id,"
            " next_at=excluded.next_at, cadence_observed=excluded.cadence_observed, refreshed_at=excluded.refreshed_at",
            (pid, f"fixture-{key}", result["next_event_id"], result["next_at"], result["cadence_observed"],
             tz_name, ea_db.now_iso(), "synthetic events.instances; see state/records/fixture-calendar"))
    return int(conn.execute("SELECT id FROM meetings WHERE series_event_id = ?", (f"fixture-{key}",)).fetchone()["id"])


def delete_fixture_doc(doc_id: str) -> str:
    """Delete one fixture Doc through Drive. Refuses anything not titled [FIXTURE] and owned here.

    Used for G4 (a required source that disappears) and to clean up a half-built
    fixture. Needs a Drive scope, which Taylor's Phase 1 consent does not request;
    on his machine acceptance.py falls back to a registered id that does not exist.
    """
    import google_creds  # noqa: PLC0415

    drive = google_creds.service("drive", "v3", [google_creds.DRIVE])
    meta = call(drive.files().get(fileId=doc_id, fields="name,ownedByMe,mimeType"), "drive get")
    if not str(meta.get("name", "")).startswith("[FIXTURE]") or not meta.get("ownedByMe"):
        raise RuntimeError(f"REFUSED: {doc_id} is not a [FIXTURE] Doc owned by this account ({meta.get('name')!r})")
    call(drive.files().delete(fileId=doc_id), "drive delete")
    return str(meta["name"])


def existing(conn, title: str):
    return conn.execute("SELECT * FROM docs WHERE title = ? AND fixture = 1", (title,)).fetchone()


def create(only: set[str] | None) -> int:
    if not ea_db.fixture_mode() or ea_db.DB_PATH != ea_db.FIXTURE_DB:
        print("REFUSED: make_fixtures runs only against state/fixtures.db (EA_FIXTURE_MODE=1, no EA_DB).",
              file=sys.stderr)
        return 2
    tz_name = register.identity().get("timezone") or "America/Toronto"
    service = docs_read.docs_service()
    conn = ea_db.connect()
    ea_db.migrate(conn)
    register.seed_roster(conn)
    now = datetime.now(timezone.utc)
    built = []
    try:
        plan = [(k, n, c, f"[FIXTURE] {n} x Taylor 1:1", "running_1on1") for k, n, c in PEOPLE]
        plan += [("shawn", "Shawn", "weekly", "[FIXTURE] G4 deleted doc", "g4_sacrificial"),
                 ("kaed", "Kaed", "weekly", "[FIXTURE] Checkbox experiment", "checkbox_experiment")]
        for key, first_name, cadence, title, role in plan:
            if only and key not in only and role == "running_1on1":
                continue
            if only and role != "running_1on1" and not ({"g4", "checkbox"} & only):
                continue
            meeting_id = seed_meeting(conn, key, cadence, tz_name, now)
            row = existing(conn, title)
            if row is not None:
                print(f"  exists   {title}  {row['doc_id']}")
                continue
            if role == "checkbox_experiment":
                doc_id = build_checkbox_doc(service, title)
                smap = CHECKBOX_MAP
                parsed = verify(service, doc_id, smap, expect_table=False)
            else:
                doc_id = build_person_doc(service, first_name, tz_name, title=title,
                                          empty_focuses=(key == "casey" and role == "running_1on1"))
                smap = section_map(first_name)
                parsed = verify(service, doc_id, smap, expect_table=True)
            tab = parsed["tabs"][parsed["target_tab"]]
            link_docs.register_doc(conn, doc_id=doc_id, title=title, person_key=key, fixture=True,
                                   section_map=smap, tab_id=tab["tab_id"], role=role, confirmed=True,
                                   revision_id=parsed["revision_id"])
            with conn:
                conn.execute("UPDATE docs SET meeting_id = ?, verified_at = ?, editable = 1 WHERE doc_id = ?",
                             (meeting_id if role == "running_1on1" else None, ea_db.now_iso(), doc_id))
            body, digest = docs_read.snapshot(parsed)
            with conn:
                conn.execute("INSERT OR IGNORE INTO doc_snapshots (doc_id, revision_id, parsed_json, sha256, taken_at)"
                             " VALUES (?,?,?,?,?)", (doc_id, parsed["revision_id"], body, digest, ea_db.now_iso()))
            built.append((title, doc_id, parsed["revision_id"]))
            print(f"  created  {title}  {doc_id}  rev {parsed['revision_id'][:16]}...")
    finally:
        conn.close()
    print(f"{len(built)} fixture Doc(s) created; all registered fixture=1 in {ea_db.DB_PATH}")
    return 0


def status() -> int:
    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        rows = conn.execute("SELECT d.*, p.key FROM docs d LEFT JOIN people p ON p.id = d.person_id"
                            " WHERE d.fixture = 1 ORDER BY d.role, p.key").fetchall()
        for r in rows:
            print(f"  {r['role']:<20} {r['key'] or '-':<6} {r['doc_id']}  {r['title']}")
        meetings = conn.execute("SELECT m.*, p.key FROM meetings m JOIN people p ON p.id = m.person_id"
                                " WHERE m.fixture = 1 ORDER BY p.key").fetchall()
        for m in meetings:
            print(f"  meeting {m['key']:<6} {m['cadence_observed']:<9} next {m['next_at']}")
        if not rows:
            print("no fixture Docs registered")
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--delete-unregistered", metavar="DOC_ID",
                        help="delete a half-built [FIXTURE] Doc that was never registered")
    args = parser.parse_args()
    if args.delete_unregistered:
        conn = ea_db.connect()
        try:
            if conn.execute("SELECT 1 FROM docs WHERE doc_id = ?", (args.delete_unregistered,)).fetchone():
                print("REFUSED: that Doc is registered; it is not a half-built leftover", file=sys.stderr)
                return 2
        finally:
            conn.close()
        print(f"deleted {delete_fixture_doc(args.delete_unregistered)}")
        return 0
    if args.create:
        return create(set(args.only) if args.only else None)
    if args.status:
        return status()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
