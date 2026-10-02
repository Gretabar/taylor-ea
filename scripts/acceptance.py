"""Phase 1 acceptance on fixture Docs. Writes docs/acceptance/P1-<date>.md with observed evidence.

NEW in this repo. Blueprint s.12: "A test is Passed only with observed evidence;
use Failed or Blocked when it does not work or cannot be exercised." So every
verdict below is computed from what was observed in this run (exit codes, register
rows, the Doc as re-read from Google, revision ids, audit rows), and a step whose
evidence is missing is Failed, not assumed.

TWO LEGS PER TEST, REPORTED SEPARATELY.
  script leg   everything deterministic: register.py, docs_propose.py, docs_edit.py,
               ea_tick.py and the hooks, run as subprocesses exactly as the agents
               run them, against fixture Docs. Proven here.
  session leg  what an agent decides in a live session: REED classifying "/add ..."
               as a topic or a commitment, the orchestrator saying "not updated",
               asking which person was meant. That needs a VS Code session on the
               seat, so it is recorded Blocked with that reason, never assumed.

SAFETY. EA_FIXTURE_MODE=1 for this process and every subprocess, so every script
points at state/fixtures.db and docs_edit.py refuses any non-fixture Doc. The
harness's own direct API writes (playing a manager who types "Done" in a Status
cell) refuse any Doc that is not registered fixture=1 AND titled [FIXTURE].

THE FIXTURE OVERLAY. In fixture mode Taylor's overlay is state/taylor-fixtures/
(scripts/overlay.py), so the G1 and Lessons legs never read or write his real decisions,
rules or lessons. --rebuild deletes it and seeds it again.

FRESH FIXTURES OR NOTHING. Every leg assumes the fixtures are exactly as
make_fixtures.py --create left them: P1.1 counts its one topic, P1.6 reads the
meeting id a NEW capture returns, G4 consumes its sacrificial Doc, G5 adds the
alias it then tests. A rerun on top of a previous run's state false-fails seven
legs with detail that reads like passes, and used to overwrite a passing report
with that. So without --rebuild the harness first checks the register for rows a
run leaves behind, and every fixture Doc against the snapshot taken when it was
built. If anything is left over, it refuses with exit 2 before running a leg and
writes no report. It never rebuilds on its own: deleting and recreating Docs in
Mike's Drive stays an explicit flag.

BLOCKED IS NOT FAILED. Blueprint s.12: "use Failed or Blocked when it does not work
or cannot be exercised". A crash of the harness itself is "cannot be exercised", so in
every leg it is reported Blocked. A script under test that misbehaves is FAILED: it
exits non-zero, prints no JSON, breaks its output contract, or loses a record it
reported writing. Each of those raises SystemFailure at the point the harness reads
the script's output, so it can never be mistaken for a harness crash.

Usage:
    python scripts/acceptance.py --fixtures [--rebuild] [--date 2026-10-01]

Exit 0 when every script leg Passed and every check exited 0; 1 when any leg is
FAILED or Blocked (Blocked is not a pass) or a check failed; 2 when it refused to
run (leftover or unbuilt fixtures, or freshness could not be checked), in which
case no report was written.
"""

from __future__ import annotations

import os

os.environ["EA_FIXTURE_MODE"] = "1"
os.environ.pop("EA_DB", None)
os.environ.pop("EA_OVERLAY", None)  # the overlay is state/taylor-fixtures/ in fixture mode, never his real one

import argparse  # noqa: E402
import ast  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docs_read  # noqa: E402
import ea_db  # noqa: E402
import register  # noqa: E402

ROOT = ea_db.REPO_ROOT
PY = sys.executable
ENV = dict(os.environ, EA_FIXTURE_MODE="1", PYTHONIOENCODING="utf-8")
INSTRUCTION_DATE = "2026-10-01"
SESSION_BLOCKED = ("Blocked: needs a live session in the VS Code extension on the Enterprise seat, "
                   "where the agent makes this judgement. Not run on the build machine.")


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

class Evidence:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> None:
        self.lines.append(text)

    def cmd(self, label: str, result: "Run") -> None:
        self.lines.append(f"- `{label}` -> exit {result.code}")
        out = (result.out.strip() + ("\n" + result.err.strip() if result.err.strip() else "")).strip()
        if out:
            self.lines.append("  ```")
            self.lines.extend("  " + ln for ln in out.splitlines()[:14])
            self.lines.append("  ```")


class Run:
    def __init__(self, code: int, out: str, err: str):
        self.code, self.out, self.err = code, out, err

    def json(self) -> dict:
        return json.loads(self.out)


def sh(*args: str, stdin: str | None = None, env: dict | None = None) -> Run:
    done = subprocess.run([PY, *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", input=stdin, env=env or ENV, timeout=600)
    return Run(done.returncode, done.stdout, done.stderr)


class SystemFailure(Exception):
    """A script under test exited non-zero or broke its output contract. Always FAILED, never Blocked."""


def system_json(run: Run, label: str, *keys: str) -> dict:
    """A script's JSON output. Anything else is the system's failure, not the harness's."""
    if run.code != 0:
        raise SystemFailure(f"{label} exited {run.code}: {(run.err.strip() or run.out.strip())[-160:]}")
    try:
        result = json.loads(run.out)
    except ValueError as exc:
        raise SystemFailure(f"{label} printed no JSON: {run.out.strip()[:160]!r}") from exc
    missing = [key for key in keys if key not in result]
    if missing:
        raise SystemFailure(f"{label} output has no {', '.join(missing)}: {run.out.strip()[:160]}")
    return result


def db():
    conn = ea_db.connect()
    ea_db.migrate(conn)
    return conn


def scalar(sql: str, *params):
    conn = db()
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def rows(sql: str, *params) -> list[dict]:
    conn = db()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def system_row(what: str, sql: str, *params) -> dict:
    """The record a script under test reported writing. Its absence is the system's failure."""
    found = rows(sql, *params)
    if not found:
        raise SystemFailure(f"no {what} in the register after the script reported writing it")
    return found[0]


def doc_of(title_like: str) -> dict:
    found = rows("SELECT * FROM docs WHERE fixture = 1 AND title LIKE ?", f"%{title_like}%")
    if len(found) != 1:
        raise RuntimeError(f"expected one fixture Doc like {title_like!r}, found {len(found)}")
    return found[0]


def read(doc: dict) -> dict:
    return docs_read.parse(docs_read.fetch(docs_read.docs_service(), doc["doc_id"]),
                           json.loads(doc["section_map_json"]))


def propose_and_apply(kind: str, ref: str, ev: Evidence, *extra: str, apply_extra: tuple = ()) -> tuple[Run, Run, str]:
    prop = sh("scripts/docs_propose.py", kind, "--ref", ref, *extra)
    ev.cmd(f"docs_propose.py {kind} --ref {ref} {' '.join(extra)}".strip(), prop)
    if prop.code != 0:
        return prop, Run(-1, "", "not applied: proposal refused"), ""
    path = doc_id = None
    for line in prop.out.splitlines():
        if path is None and line.startswith("proposal:") and len(line.split(None, 1)) == 2:
            path = line.split(None, 1)[1].strip()
        if doc_id is None and "--doc " in line and line.split("--doc ", 1)[1].split():
            doc_id = line.split("--doc ", 1)[1].split()[0]
    if not path or not doc_id:
        raise SystemFailure(f"docs_propose.py {kind} --ref {ref} exited 0 without its proposal: and --doc lines")
    applied = sh("scripts/docs_edit.py", kind, "--doc", doc_id, "--proposal", path, *apply_extra)
    ev.cmd(f"docs_edit.py {kind} --doc {doc_id[:12]}... --proposal {Path(path).name} {' '.join(apply_extra)}".strip(),
           applied)
    return prop, applied, path


def manager_types(doc: dict, ref: str, text: str) -> str:
    """Play a manager: type `text` into the Status cell of the row carrying [ref]. Fixture only."""
    if not doc["fixture"] or not str(doc["title"]).startswith("[FIXTURE]"):
        raise RuntimeError(f"REFUSED: {doc['title']!r} is not a fixture Doc")
    service = docs_read.docs_service()
    document = docs_read.fetch(service, doc["doc_id"])
    parsed = docs_read.parse(document, json.loads(doc["section_map_json"]))
    tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
    for row in docs_read.all_table_rows(parsed):
        if any(f"[{ref}]" in c["text"] for c in row["cells"]):
            start = row["cells"][3]["paragraphs"][0]["start"]
            service.documents().batchUpdate(documentId=doc["doc_id"], body={
                "requests": [{"insertText": {"location": {"index": start, "tabId": tab_id}, "text": text}}],
                "writeControl": {"requiredRevisionId": document["revisionId"]}}).execute()
            return docs_read.fetch(service, doc["doc_id"])["revisionId"]
    raise RuntimeError(f"no row carrying [{ref}] in {doc['title']}")


def manager_strikes(doc: dict, ref: str) -> str:
    """Play a manager ticking a checklist line, as the believed rendering: strikethrough. Fixture only."""
    if not doc["fixture"] or not str(doc["title"]).startswith("[FIXTURE]"):
        raise RuntimeError(f"REFUSED: {doc['title']!r} is not a fixture Doc")
    service = docs_read.docs_service()
    document = docs_read.fetch(service, doc["doc_id"])
    parsed = docs_read.parse(document, json.loads(doc["section_map_json"]))
    tab_id = parsed["tabs"][parsed["target_tab"]]["tab_id"]
    for item in parsed["tabs"][parsed["target_tab"]]["items"]:
        if item["kind"] == "paragraph" and f"[{ref}]" in item["text"]:
            service.documents().batchUpdate(documentId=doc["doc_id"], body={"requests": [{"updateTextStyle": {
                "range": {"startIndex": item["start"], "endIndex": item["end"] - 1, "tabId": tab_id},
                "textStyle": {"strikethrough": True}, "fields": "strikethrough"}}],
                "writeControl": {"requiredRevisionId": document["revisionId"]}}).execute()
            return docs_read.fetch(service, doc["doc_id"])["revisionId"]
    raise RuntimeError(f"no line carrying [{ref}] in {doc['title']}")


def imports_calendar(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return "calendar_next" in names or "CALENDAR_READONLY" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def rebuild(ev: Evidence) -> None:
    import make_fixtures  # noqa: PLC0415

    for doc in rows("SELECT doc_id, title FROM docs WHERE fixture = 1"):
        try:
            make_fixtures.delete_fixture_doc(doc["doc_id"])
            ev.add(f"- deleted previous fixture `{doc['doc_id']}` ({doc['title']})")
        except Exception as exc:  # noqa: BLE001
            # swallow: an already-deleted fixture (G4's) cannot be deleted again; the
            # message is kept in the evidence so nothing disappears silently.
            ev.add(f"- previous fixture `{doc['doc_id']}` not deleted ({exc.__class__.__name__}); continuing")
    for suffix in ("", "-wal", "-shm"):
        Path(str(ea_db.FIXTURE_DB) + suffix).unlink(missing_ok=True)
    if register.FIXTURE_PRIVATE_NOTES.exists():
        register.FIXTURE_PRIVATE_NOTES.unlink()
        ev.add(f"- removed the previous run's `{register.FIXTURE_PRIVATE_NOTES.relative_to(ROOT).as_posix()}`")
    result = sh("scripts/make_fixtures.py", "--create")
    ev.cmd("make_fixtures.py --create", result)
    if result.code != 0:
        raise RuntimeError("fixtures could not be built; nothing else can be tested")
    if FIXTURE_OVERLAY.exists():
        shutil.rmtree(FIXTURE_OVERLAY)
        ev.add(f"- removed the previous run's `{FIXTURE_OVERLAY.relative_to(ROOT).as_posix()}`")
    seeded = sh("scripts/overlay.py", "init")
    ev.cmd("overlay.py init   (the fixture overlay)", seeded)
    if seeded.code != 0:
        raise RuntimeError("the fixture overlay could not be seeded; G1 and Lessons cannot be tested")


# Hardcoded rather than overlay.overlay_dir(): --rebuild deletes it, and nothing a variable
# says may ever point that at Taylor's real overlay.
FIXTURE_OVERLAY = ROOT / "state" / "taylor-fixtures"


def overlay_leftovers() -> list[str]:
    """Lessons a previous run left in the fixture overlay. Empty means fresh."""
    store = FIXTURE_OVERLAY / "lessons.json"
    if not store.exists():
        return []
    try:
        count = len(json.loads(store.read_bytes().decode("utf-8")).get("lessons") or [])
    except (OSError, ValueError, AttributeError) as exc:
        return [f"the fixture overlay's lessons cannot be read ({exc.__class__.__name__})"]
    return [f"lessons: {count} in {store.relative_to(ROOT).as_posix()}"] if count else []


LEFTOVER = "fixtures carry state from a previous run; rerun with --rebuild"
NOT_BUILT = "no fixtures are built; rerun with --rebuild"
NOTHING_BUILT = "no fixture Docs are registered"

# Tables make_fixtures.py --create never writes and every leg does. One row is
# enough to say a run happened here.
RUN_TABLES = ("actions", "action_events", "topics", "needs_input", "doc_items", "reconcile_events",
              "captures", "proposals", "counters", "privacy_reviews")


def expected_roles() -> Counter:
    """The fixture Docs a fresh build registers, by role."""
    import make_fixtures  # noqa: PLC0415

    return Counter({"running_1on1": len(make_fixtures.PEOPLE), "g4_sacrificial": 1, "checkbox_experiment": 1})


def _content(parsed: dict) -> str:
    """A parsed Doc as canonical JSON with the revision blanked: equal strings mean equal content."""
    return docs_read.snapshot({**parsed, "revision_id": None})[0]


def changed_docs(conn, fetch=None) -> list[str]:
    """Fixture Docs that are no longer as they were built. Raises DocReadError when one cannot be read.

    The reference is the doc_snapshots row make_fixtures.py wrote right after building
    each Doc (the earliest one for that Doc). An unchanged revision is clean; a new
    revision is clean only if the content still matches, so a no-op revision bump
    does not force a rebuild. A Doc Google no longer has (G4 deletes one) is leftover
    state. Any other read failure raises: unreadable is not clean.
    """
    if fetch is None:
        service = docs_read.docs_service()

        def fetch(doc_id: str) -> dict:
            return docs_read.fetch(service, doc_id)

    reasons = []
    for doc in conn.execute("SELECT doc_id, title, section_map_json FROM docs WHERE fixture = 1 ORDER BY id").fetchall():
        built = conn.execute("SELECT revision_id, parsed_json FROM doc_snapshots WHERE doc_id = ? ORDER BY id LIMIT 1",
                             (doc["doc_id"],)).fetchone()
        if built is None:
            reasons.append(f"{doc['title']}: no build snapshot to compare against")
            continue
        try:
            document = fetch(doc["doc_id"])
        except docs_read.DocReadError as exc:
            if exc.status != 404:
                raise
            reasons.append(f"{doc['title']}: no longer exists")
            continue
        if document.get("revisionId") == built["revision_id"]:
            continue
        parsed = docs_read.parse(document, json.loads(doc["section_map_json"] or "{}"))
        if _content(parsed) != _content(json.loads(built["parsed_json"])):
            reasons.append(f"{doc['title']}: changed since it was built")
    return reasons


def leftover_state(conn, fetch=None, roster_path: Path | None = None) -> list[str]:
    """Why the fixtures are not as make_fixtures.py --create left them. Empty means fresh.

    Cheapest evidence first, and Google is asked only when the register is clean.
    """
    reasons = [f"{table}: {count} row(s)" for table in RUN_TABLES
               if (count := conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])]
    if reasons:
        return reasons
    roster = json.loads((roster_path or register.ROSTER_PATH).read_bytes().decode("utf-8"))
    seeded = {str(p["key"]).lower(): {a.casefold() for a in p.get("aliases") or []} for p in roster.get("people") or []}
    for person in conn.execute("SELECT key, aliases_json FROM people").fetchall():
        extra = {a.casefold() for a in json.loads(person["aliases_json"] or "[]")} - seeded.get(person["key"], set())
        if extra:
            reasons.append(f"people: {person['key']} has aliases the roster does not ({', '.join(sorted(extra))})")
    if reasons:
        return reasons
    roles = Counter(row["role"] for row in conn.execute("SELECT role FROM docs WHERE fixture = 1").fetchall())
    if not roles:
        return [NOTHING_BUILT]
    if roles != expected_roles():
        return [f"fixture Docs by role {dict(roles)}; a fresh build has {dict(expected_roles())}"]
    return changed_docs(conn, fetch)


# ---------------------------------------------------------------------------
# the tests
# ---------------------------------------------------------------------------

def p11(ev: Evidence) -> dict:
    doc = doc_of("Kaed x Taylor")
    actions_before, meetings_before = scalar("SELECT COUNT(*) FROM actions"), scalar("SELECT COUNT(*) FROM meetings")
    topic = sh("scripts/register.py", "add-topic", "--person", "kaed", "--text", "Manager accountability",
               "--side", "taylor", "--origin-ref", "/add add manager accountability to Kaed's next 1:1",
               "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-topic --person kaed --text \"Manager accountability\"", topic)
    ref = system_json(topic, "register.py add-topic", "ref")["ref"]
    _, applied, _ = propose_and_apply("add-topic", ref, ev)
    parsed = read(doc)
    section = parsed["sections"]["taylor_topics"]
    texts = [parsed["tabs"][parsed["target_tab"]]["items"][i]["text"] for i in section["items"]]
    topic_row = system_row("topic row", "SELECT ref, status, placed_revision_id FROM topics WHERE ref = ?", ref)
    actions_after, meetings_after = scalar("SELECT COUNT(*) FROM actions"), scalar("SELECT COUNT(*) FROM meetings")
    calendar_free = [p.name for p in (HERE / "register.py", HERE / "docs_propose.py", HERE / "docs_edit.py")
                     if not imports_calendar(p)]
    ev.add(f"- topic row: `{topic_row}`")
    ev.add(f"- Kaed's newest block, taylor_topics ('Top Focuses') as re-read from Google: `{texts}`")
    ev.add(f"- actions before/after: {actions_before}/{actions_after}; meetings before/after: {meetings_before}/{meetings_after}")
    ev.add(f"- Calendar: none of {', '.join(calendar_free)} imports calendar_next or asks for calendar.readonly, "
           f"and this token has no calendar scope, so a Calendar call would have failed the step")
    ok = (applied.code == 0 and texts.count("Manager accountability") == 1 and topic_row["status"] == "placed"
          and actions_after == actions_before and meetings_after == meetings_before and len(calendar_free) == 3)
    return {"ok": ok, "summary": f"1 topic {ref} placed in Kaed's taylor_topics (rev {(topic_row['placed_revision_id'] or '-')[:12]}...), "
                                 f"0 actions, 0 meetings created, 0 Calendar calls"}


def p12(ev: Evidence) -> dict:
    try:
        due = register.resolve_date("Friday", date.fromisoformat(INSTRUCTION_DATE))
    except Exception as exc:  # noqa: BLE001
        # Not swallowed: the date resolver is under test here, so its crash is the system's failure.
        raise SystemFailure(f"register.resolve_date raised {exc.__class__.__name__}: {exc}") from exc
    ev.add(f"- resolve-date Friday from {INSTRUCTION_DATE} (a Thursday): `{due['status']} {due['date']}`")
    action = sh("scripts/register.py", "add-action", "--text", "Send Casey the manager bonus structure",
                "--owner", "taylor", "--due", str(due["date"]), "--due-note", "Friday", "--counterpart", "casey",
                "--origin-ref", "/add I told Casey I'll send the bonus structure Friday; add it to our next 1:1",
                "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-action --owner taylor --due <resolved Friday> --counterpart casey", action)
    a_ref = system_json(action, "register.py add-action", "ref")["ref"]
    topic = sh("scripts/register.py", "add-topic", "--person", "casey", "--text", "Manager bonus structure",
               "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-topic --person casey --text \"Manager bonus structure\"", topic)
    t_ref = system_json(topic, "register.py add-topic", "ref")["ref"]
    _, a_applied, _ = propose_and_apply("add-action", a_ref, ev)
    _, t_applied, _ = propose_and_apply("add-topic", t_ref, ev)
    doc = doc_of("Casey x Taylor")
    parsed = read(doc)
    found = docs_read.locate(parsed, item_kind="action", item_ref=a_ref, named_range=f"ea:action:{a_ref}",
                             stored_hash=None, columns=None)
    row = system_row("action row with a resolved owner",
                     "SELECT a.ref, p.key AS owner, a.due_date, a.project_ref, a.status FROM actions a"
                     " JOIN people p ON p.id = a.owner_person_id WHERE a.ref = ?", a_ref)
    tab = parsed["tabs"][parsed["target_tab"]]
    topics_in_doc = [tab["items"][i]["text"] for i in parsed["sections"]["taylor_topics"]["items"]]
    ev.add(f"- action row: `{row}`")
    ev.add(f"- Casey's Action Items row as re-read: title `{found.get('text')}`, date chip "
           f"`{(found.get('date_chip') or {}).get('timestamp')}`, status `{found.get('status_text')!r}`")
    ev.add(f"- Casey's taylor_topics (empty before this run) as re-read: `{topics_in_doc}`")
    ok = (due["date"] == "2026-10-02" and a_applied.code == 0 and t_applied.code == 0 and row["owner"] == "taylor"
          and row["due_date"] == "2026-10-02" and row["project_ref"] is None
          and topics_in_doc == ["Manager bonus structure"] and found.get("via") == "named_range")
    return {"ok": ok, "a_ref": a_ref,
            "summary": f"{a_ref} owner taylor due 2026-10-02 (Friday after Thu 2026-10-01; the plan's 2026-10-03 "
                       f"is a Saturday), in Casey's table with a date chip; {t_ref} in Casey's Doc; no project link"}


def p13(ev: Evidence) -> dict:
    action = sh("scripts/register.py", "add-action", "--text", "Someone should follow up", "--owner", "unresolved",
                "--due", "unresolved", "--due-note", "we haven't chosen a date",
                "--origin-ref", "/add Someone should follow up; we haven't chosen a date",
                "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-action --owner unresolved --due unresolved", action)
    ref = system_json(action, "register.py add-action", "ref")["ref"]
    row = system_row("action row", "SELECT ref, owner_person_id, owner_unresolved, due_date, due_unresolved"
                     " FROM actions WHERE ref = ?", ref)
    questions = rows("SELECT n.ref, n.question FROM needs_input n JOIN actions a ON a.id = n.action_id"
                     " WHERE a.ref = ? AND n.status = 'open'", ref)
    friday = sh("scripts/register.py", "resolve-date", "Friday", "--from", "2026-10-02")
    ev.cmd("register.py resolve-date Friday --from 2026-10-02  (a Friday)", friday)
    ev.add(f"- action row: `{row}`")
    ev.add(f"- open Needs Your Input: `{questions}`")
    ok = (row["owner_person_id"] is None and row["owner_unresolved"] == 1 and row["due_date"] is None
          and row["due_unresolved"] == 1 and len(questions) == 1 and friday.out.startswith("ambiguous"))
    return {"ok": ok, "summary": f"{ref} owner_unresolved=1 due_unresolved=1, 1 Needs Your Input ({questions[0]['ref'] if questions else '-'}); "
                                 f"Friday said on a Friday -> ambiguous"}


def p14(ev: Evidence, a_ref: str) -> dict:
    doc = doc_of("Casey x Taylor")
    revision = manager_types(doc, a_ref, "Done")
    ev.add(f"- harness, playing Casey: typed `Done` into the Status cell of {a_ref}'s row; Doc revision now "
           f"`{revision[:24]}...`")
    tick1 = sh("scripts/ea_tick.py", "--fixtures")
    ev.cmd("ea_tick.py --fixtures", tick1)
    action = system_row("action row", "SELECT ref, status, completed_via, completed_at FROM actions WHERE ref = ?", a_ref)
    events = rows("SELECT e.actor, e.field, e.old_value, e.new_value, e.source FROM action_events e"
                  " JOIN actions a ON a.id = e.action_id WHERE a.ref = ? AND e.field = 'status'", a_ref)
    owed = sh("scripts/register.py", "--json", "owed")
    owed_by_person = system_json(owed, "register.py --json owed", "by_person")["by_person"]
    still_owed = [i["ref"] for items in owed_by_person.values() for i in items]
    tick2 = sh("scripts/ea_tick.py", "--fixtures")
    ev.cmd("ea_tick.py --fixtures  (second tick, same revision)", tick2)
    forced = sh("scripts/docs_reconcile.py", "--doc", doc["doc_id"], "--force")
    ev.cmd("docs_reconcile.py --doc <casey> --force  (same revision re-read on purpose)", forced)
    completions = scalar("SELECT COUNT(*) FROM reconcile_events WHERE action_ref = ? AND direction='doc_to_register'", a_ref)
    status_events = len(rows("SELECT e.id FROM action_events e JOIN actions a ON a.id = e.action_id"
                             " WHERE a.ref = ? AND e.field = 'status'", a_ref))
    ev.add(f"- action after tick 1: `{action}`")
    ev.add(f"- status events: `{events}`")
    ev.add(f"- open Taylor actions after (owed): `{still_owed}`")
    ev.add(f"- reconcile_events for {a_ref}: {completions}; status events after the replay and the forced re-read: {status_events}")

    # Checkbox form, on the checklist fixture.
    chk = doc_of("Checkbox experiment")
    act = sh("scripts/register.py", "add-action", "--text", "Order the replacement till drawer", "--owner", "taylor",
             "--due", "2026-10-08", "--counterpart", "kaed", "--instruction-date", INSTRUCTION_DATE)
    c_ref = system_json(act, "register.py add-action", "ref")["ref"]
    _, c_applied, _ = propose_and_apply("add-action", c_ref, ev, "--doc", chk["doc_id"])
    if c_applied.code != 0:
        raise SystemFailure(f"docs_edit.py did not place {c_ref} on the checklist (exit {c_applied.code})")
    strike_rev = manager_strikes(chk, c_ref)
    ev.add(f"- harness: struck through the {c_ref} checklist line (the believed rendering of a ticked box; the API "
           f"cannot set a checkbox); revision `{strike_rev[:24]}...`")
    tick3 = sh("scripts/ea_tick.py", "--fixtures")
    ev.cmd("ea_tick.py --fixtures  (checkbox form)", tick3)
    c_action = system_row("action row", "SELECT ref, status, completed_via FROM actions WHERE ref = ?", c_ref)
    ev.add(f"- checklist action after the tick: `{c_action}`")
    ok = (action["status"] == "done" and action["completed_via"] == "doc" and len(events) == 1
          and a_ref not in still_owed and "unchanged" in tick2.out and completions == 1 and status_events == 1
          and c_applied.code == 0 and c_action["status"] == "done" and c_action["completed_via"] == "doc")
    return {"ok": ok, "summary": f"Status cell `Done` -> {a_ref} done via doc with 1 event, gone from /owe; tick 2 "
                                 f"`unchanged`; forced re-read of the same revision adds nothing; checklist form "
                                 f"({c_ref}) completed via strikethrough"}


def p15(ev: Evidence) -> dict:
    action = sh("scripts/register.py", "add-action", "--text", "Bring the closing process draft", "--owner", "taylor",
                "--due", "2026-10-06", "--counterpart", "kaed", "--instruction-date", INSTRUCTION_DATE)
    ref = system_json(action, "register.py add-action", "ref")["ref"]
    _, placed, _ = propose_and_apply("add-action", ref, ev)
    doc = doc_of("Kaed x Taylor")
    before = docs_read.lines_of(read(doc))
    moves = []
    for new_due in ("2026-10-08", "2026-10-13"):
        upd = sh("scripts/register.py", "update-action", ref, "--field", "due_date", "--value", new_due,
                 "--actor", "taylor", "--source", "chat")
        ev.cmd(f"register.py update-action {ref} --field due_date --value {new_due}", upd)
        _, applied, _ = propose_and_apply("update-due", ref, ev)
        moves.append(applied.code)
    after = docs_read.lines_of(read(doc))
    removed = [ln for ln in before if ln not in after]
    added = [ln for ln in after if ln not in before]
    owed = sh("scripts/register.py", "owed")
    ev.cmd("register.py owed   (\"What do I owe everyone?\")", owed)
    hist = sh("scripts/register.py", "history", ref)
    ev.cmd(f"register.py history {ref}   (\"How many times did this move?\")", hist)
    count = scalar("SELECT COUNT(*) FROM actions WHERE text = 'Bring the closing process draft'")
    ev.add(f"- rows for this commitment: {count}")
    ev.add(f"- Doc diff, whole working tab, before the first move vs after the second: removed `{removed}`, "
           f"added `{added}`")
    only_row = len(removed) == 1 and len(added) == 1 and f"[{ref}]" in removed[0] and f"[{ref}]" in added[0]
    ok = placed.code == 0 and moves == [0, 0] and "moved 2 time(s)" in hist.out and count == 1 and only_row
    return {"ok": ok, "summary": f"{ref} rescheduled twice: one row, history 'moved 2 time(s)', /owe lists it under "
                                 f"Kaed with 2026-10-13, Doc diff limited to that action's row"}


FIXTURE_CALENDAR = ROOT / "state" / "records" / "fixture-calendar"

# P1.6 is defined on Mark's biweekly 1:1, so two weeks is the test's own expectation.
# It is never read from the register (that is the answer under test) nor from the
# seed's cadence (a series seeded or read as weekly must fail, not move the goalposts).
P16_EVERY = timedelta(days=14)


def fixture_seed(key: str) -> dict:
    """The seed parameters make_fixtures.py recorded for one fixture series."""
    path = FIXTURE_CALENDAR / f"{key}.json"
    try:
        return json.loads(path.read_bytes().decode("utf-8"))["seed"]
    except (OSError, ValueError, KeyError) as exc:
        raise RuntimeError(f"no seed parameters in {path.name} ({exc.__class__.__name__}); rebuild the fixtures") from exc


def expected_next_date(seed: dict) -> date:
    """The next 1:1 a seed implies: its last instance plus two weeks, as a date in the seed's zone."""
    last = datetime.fromisoformat(seed["last_start"]).astimezone(ZoneInfo(seed["timezone"]))
    return (last + P16_EVERY).date()


def local_date(stamp, tz_name: str) -> date | None:
    """A next_at the system reported, as a date in the seed's zone. None when it gave none."""
    try:
        return datetime.fromisoformat(str(stamp)).astimezone(ZoneInfo(tz_name)).date() if stamp else None
    except ValueError:
        return None


def p16(ev: Evidence) -> dict:
    seed = fixture_seed("mark")
    expected = expected_next_date(seed)
    meetings_before = scalar("SELECT COUNT(*) FROM meetings")
    meeting = rows("SELECT m.id, m.cadence_observed, m.next_at FROM meetings m JOIN people p ON p.id = m.person_id"
                   " WHERE p.key = 'mark'")[0]
    topic = sh("scripts/register.py", "add-topic", "--person", "mark", "--text", "Patio season close-out plan",
               "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-topic --person mark (a biweekly fixture series)", topic)
    result = system_json(topic, "register.py add-topic", "ref")
    if result.get("created") is False:
        # The register answered a replay correctly; the harness asked on top of a previous run.
        raise RuntimeError(f"{result['ref']} was captured by an earlier run, so the fixtures are not fresh")
    system_json(topic, "register.py add-topic", "meeting_id", "next_at")
    _, applied, _ = propose_and_apply("add-topic", result["ref"], ev)
    doc = doc_of("Mark x Taylor")
    parsed = read(doc)
    tab = parsed["tabs"][parsed["target_tab"]]
    texts = [tab["items"][i]["text"] for i in parsed["sections"]["taylor_topics"]["items"]]
    meetings_after = scalar("SELECT COUNT(*) FROM meetings")
    observed = local_date(result["next_at"], seed["timezone"])
    ev.add(f"- Mark's meeting: `{meeting}` (from a synthetic events.instances series seeded "
           f"{local_date(seed['built_at'], seed['timezone'])}: "
           f"last instance {seed['last_start']}; expected next 1:1 {expected}, two weeks on, in {seed['timezone']})")
    ev.add(f"- topic register row: meeting_id {result['meeting_id']}, next_at {result['next_at']} (local date {observed})")
    ev.add(f"- Mark's Doc taylor_topics as re-read: `{texts}`; meetings before/after: {meetings_before}/{meetings_after}")
    ok = (applied.code == 0 and meeting["cadence_observed"] == "biweekly" and result["meeting_id"] == meeting["id"]
          and observed == expected and "Patio season close-out plan" in texts
          and meetings_after == meetings_before)
    return {"ok": ok, "summary": f"topic placed in Mark's own Doc against his biweekly series, next_at {expected} "
                                 f"(two weeks after the seeded {seed['last_start'][:10]}), no meeting invented; "
                                 "Calendar input was a fixture series"}


def run_hook(name: str, payload: dict, env: dict | None = None) -> Run:
    done = subprocess.run([PY, str(ROOT / ".claude" / "hooks" / name)], cwd=str(ROOT), input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env or ENV, timeout=60)
    return Run(done.returncode, done.stdout, done.stderr)


def transcript_with(text: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    with handle:
        handle.write(json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}) + "\n")
    return handle.name


def _hook_copy(tmp: str, build_mode: bool) -> tuple[Path, dict]:
    """The hook layer as Taylor's laptop has it: no build marker, or a timed one for this host."""
    root = Path(tmp)
    for part in (".claude", "context", "scripts"):
        shutil.copytree(ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "state").mkdir()
    if build_mode:
        until = datetime.now(timezone.utc) + timedelta(hours=2)
        (root / "state" / "BUILD_MODE").write_bytes(f"{socket.gethostname()}\n{until:%Y-%m-%dT%H:%M:%SZ}\n".encode())
    return root, dict(ENV, EA_ROOT=str(root), CLAUDE_PROJECT_DIR=str(root))


def g1(ev: Evidence) -> dict:
    """Blueprint s.1, G1: propose and change nothing. Taylor's phrase opens his overlay and nothing else."""
    import overlay  # noqa: PLC0415

    baseline = ROOT / "context" / "architecture" / "blueprint.md"
    living, proposals = overlay.path("blueprint.md"), overlay.path("proposals.md")
    if FIXTURE_OVERLAY not in living.parents:
        raise RuntimeError(f"the overlay is {living.parent}, not the fixture overlay; refusing to run G1 against it")
    sha_before = hashlib.sha256(baseline.read_bytes()).hexdigest()
    asked = transcript_with("remove the reservation send approval")
    approved = transcript_with("architecture change ok: remove the reservation send approval")

    def edit(path: Path, transcript: str) -> dict:
        return {"tool_name": "Edit", "transcript_path": transcript, "tool_input": {
            "file_path": str(path), "old_string": "x", "new_string": "y"}}

    def bash(command: str, cwd: Path) -> dict:
        return {"tool_name": "Bash", "transcript_path": approved, "cwd": str(cwd), "tool_input": {"command": command}}

    observed: list[tuple[str, Run, int, str | None]] = []

    def check(label: str, run: Run, want: int, says: str | None = None) -> None:
        ev.cmd(label, run)
        observed.append((label, run, want, says))

    try:
        check("hook protect-architecture: Edit his living blueprint (fixture overlay), latest message "
              "'remove the reservation send approval'", run_hook("protect-architecture.py", edit(living, asked)), 2,
              "proposals.md")
        check("hook protect-architecture: Write the proposal to his proposals.md, same message",
              run_hook("protect-architecture.py", {"tool_name": "Write", "transcript_path": asked, "tool_input": {
                  "file_path": str(proposals), "content": "proposal"}}), 0)
        check("hook protect-architecture: Edit his living blueprint after Taylor typed 'architecture change ok'",
              run_hook("protect-architecture.py", edit(living, approved)), 0)
        check("hook protect-architecture: Edit the v1 baseline blueprint, even with the phrase",
              run_hook("protect-architecture.py", edit(baseline, approved)), 2, "v1 baseline")
        for build_mode in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root, env = _hook_copy(tmp, build_mode)
                where = ("on a copy IN BUILD MODE (state/BUILD_MODE names this host, 2 hours)" if build_mode
                         else "on a copy WITHOUT a build marker (Taylor's laptop)")

                def copy_hook(payload: dict) -> Run:
                    done = subprocess.run([PY, str(root / ".claude" / "hooks" / "protect-architecture.py")],
                                          input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
                                          errors="replace", env=env, timeout=60)
                    return Run(done.returncode, done.stdout, done.stderr)

                code = 0 if build_mode else 2
                check(f"{where}: Edit CLAUDE.md, with the phrase", copy_hook(edit(root / "CLAUDE.md", approved)),
                      code, None if build_mode else "upstream defaults")
                check(f"{where}: Edit require-approval.py, with the phrase",
                      copy_hook(edit(root / ".claude" / "hooks" / "require-approval.py", approved)), code,
                      None if build_mode else "ship built")
                check(f"{where}: Edit his living blueprint WITHOUT the phrase",
                      copy_hook(edit(root / "state" / "taylor" / "blueprint.md", asked)), 2, "proposals.md")
                check(f"{where}: Edit the v1 baseline blueprint, with the phrase",
                      copy_hook(edit(root / "context" / "architecture" / "blueprint.md", approved)), 2, "v1 baseline")
                for command in ("echo MKsLaptop > state/BUILD_MACHINE", "echo MKsLaptop > state/BUILD_MODE",
                                "powershell -ExecutionPolicy Bypass -File scripts\\build_mode.ps1 on -Hours 24"):
                    check(f"{where}: Bash `{command}`", copy_hook(bash(command, root)), 2, "build mode")
    finally:
        os.unlink(asked)
        os.unlink(approved)
    sha_after = hashlib.sha256(baseline.read_bytes()).hexdigest()
    ev.add(f"- v1 baseline blueprint.md sha256 before `{sha_before[:16]}...`, after `{sha_after[:16]}...`")
    wrong = [label for label, run, want, says in observed if run.code != want or (says and says not in run.err)]
    for label in wrong:
        ev.add(f"- NOT AS EXPECTED: {label}")
    ok = not wrong and len(observed) == 4 + 2 * 7 and sha_before == sha_after
    return {"ok": ok, "summary": "his overlay (living blueprint) blocked without Taylor's phrase, the block pointing to "
                                 "proposals.md, and allowed with it; a proposal needs no phrase; the v1 baseline "
                                 "frozen with the phrase and in build mode; without a build marker CLAUDE.md and "
                                 "the code are refused even with the phrase; in build mode they open while his "
                                 "overlay still needs his phrase; no marker and no build_mode.ps1 from a session; "
                                 "baseline sha256 unchanged"}


def g4(ev: Evidence) -> dict:
    import make_fixtures  # noqa: PLC0415

    found = rows("SELECT * FROM docs WHERE role = 'g4_sacrificial'")
    if not found:
        raise RuntimeError("no G4 fixture Doc is registered; a previous G4 consumed it")
    sacrificial = found[0]
    topic = sh("scripts/register.py", "add-topic", "--person", "shawn", "--text", "Weekend coverage plan",
               "--instruction-date", INSTRUCTION_DATE)
    t_ref = system_json(topic, "register.py add-topic", "ref")["ref"]
    prop = sh("scripts/docs_propose.py", "add-topic", "--ref", t_ref, "--doc", sacrificial["doc_id"])
    ev.cmd(f"docs_propose.py add-topic --ref {t_ref} --doc <G4 fixture>", prop)
    path = next((ln.split(None, 1)[1] for ln in prop.out.splitlines() if ln.startswith("proposal:")), None)
    if prop.code != 0 or path is None:
        raise SystemFailure(f"docs_propose.py exited {prop.code} with no proposal: {prop.err.strip()[-160:]}")
    import google_creds  # noqa: PLC0415

    if google_creds.DRIVE in google_creds.granted_scopes():
        ev.add(f"- deleted the G4 fixture through Drive: `{make_fixtures.delete_fixture_doc(sacrificial['doc_id'])}`")
    else:
        # Taylor's Phase 1 consent has no Drive scope, so a Doc cannot be deleted from
        # here. The same condition (a registered Doc Google cannot return) is produced by
        # pointing the registered row, and the proposal it was made for, at an id that
        # does not exist. Labelled, so it is never mistaken for a real deletion.
        missing = sacrificial["doc_id"][:-6] + "Zz9Zz9"
        with ea_db.connect() as conn:
            conn.execute("UPDATE docs SET doc_id = ? WHERE doc_id = ?", (missing, sacrificial["doc_id"]))
            conn.execute("UPDATE proposals SET doc_id = ? WHERE doc_id = ?", (missing, sacrificial["doc_id"]))
        proposal_file = ROOT / path
        body = json.loads(proposal_file.read_text(encoding="utf-8"))
        body["doc_id"] = missing
        proposal_file.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        import docs_propose  # noqa: PLC0415

        with ea_db.connect() as conn:
            conn.execute("UPDATE proposals SET sha256 = ? WHERE path = ?",
                         (docs_propose.proposal_sha(json.loads(proposal_file.read_text(encoding="utf-8"))),
                          Path(path).as_posix()))
        sacrificial = dict(sacrificial, doc_id=missing)
        ev.add(f"- SIMULATED deletion (this token has no Drive scope): the registered G4 row now points at "
               f"`{missing}`, an id Google cannot return")
    with ea_db.connect() as conn:
        conn.execute("UPDATE docs SET role = 'g4_deleted' WHERE doc_id = ?", (sacrificial["doc_id"],))
    deleted = sh("scripts/docs_edit.py", "add-topic", "--doc", sacrificial["doc_id"], "--proposal", path)
    ev.cmd("docs_edit.py add-topic --doc <deleted fixture>", deleted)
    t_row = system_row("topic row", "SELECT ref, status, last_error FROM topics WHERE ref = ?", t_ref)

    kaed = doc_of("Kaed x Taylor")
    revision_before = read(kaed)["revision_id"]
    stale_topic = system_json(sh("scripts/register.py", "add-topic", "--person", "kaed", "--text",
                                 "Staff recognition budget", "--instruction-date", INSTRUCTION_DATE),
                              "register.py add-topic", "ref")["ref"]
    _, stale, _ = propose_and_apply("add-topic", stale_topic, ev, apply_extra=("--simulate-stale-revision",))
    revision_after = read(kaed)["revision_id"]
    s_row = system_row("topic row", "SELECT ref, status FROM topics WHERE ref = ?", stale_topic)
    audit = rows("SELECT ts, decision, rule_id, target, substr(detail, 1, 110) AS detail FROM audit"
                 " WHERE hook = 'docs_edit' AND decision IN ('fail','refused') ORDER BY id DESC LIMIT 2")
    ev.add(f"- topic after the deleted-Doc write: `{t_row}`")
    ev.add(f"- topic after the stale-revision write: `{s_row}`; Kaed revision before `{revision_before[:20]}...`, "
           f"after `{revision_after[:20]}...` (unchanged)")
    ev.add(f"- audit rows: `{audit}`")
    ok = (deleted.code == 3 and "NOT UPDATED" in deleted.err and t_row["status"] == "queued"
          and stale.code == 3 and "NOT UPDATED" in stale.err and s_row["status"] == "queued"
          and revision_before == revision_after and len(audit) == 2 and all(a["decision"] == "fail" for a in audit))
    return {"ok": ok, "summary": "deleted fixture: exit 3 'NOT UPDATED', topic still queued, audit fail; stale "
                                 "revision: Google 400, one retry, exit 3, Doc revision unchanged, audit fail"}


def g5(ev: Evidence) -> dict:
    people_before = scalar("SELECT COUNT(*) FROM people")
    cade = sh("scripts/register.py", "resolve-person", "Cade")
    ev.cmd("register.py resolve-person \"Cade\"", cade)
    kade = sh("scripts/register.py", "resolve-person", "Kade")
    ev.cmd("register.py resolve-person \"Kade\"", kade)
    fix = sh("scripts/register.py", "alias", "--person", "kaed", "--add", "Kade")
    ev.cmd("register.py alias --person kaed --add \"Kade\"   (Taylor: 'that one's Kaed')", fix)
    again = sh("scripts/register.py", "resolve-person", "Kade")
    ev.cmd("register.py resolve-person \"Kade\"  (after the correction)", again)
    people_after = scalar("SELECT COUNT(*) FROM people")
    ev.add(f"- people rows before/after: {people_before}/{people_after}")
    ok = (cade.code == 0 and "resolved: kaed" in cade.out and kade.code == 1 and "unresolved" in kade.out
          and again.code == 0 and "resolved: kaed" in again.out and people_before == people_after)
    return {"ok": ok, "summary": "'Cade' -> kaed via alias, no new row; 'Kade' unresolved (no fuzzy match); after "
                                 "Taylor's correction 'Kade' -> kaed, still no new row"}


# ---------------------------------------------------------------------------
# the roster legs: SAGE, LARK's prep, and the switched-off agents
# ---------------------------------------------------------------------------

def proposal_of(prop: Run, label: str) -> tuple[str, str]:
    """(proposal path, doc id) from docs_propose.py's output; their absence is the system's failure."""
    path = next((ln.split(None, 1)[1].strip() for ln in prop.out.splitlines()
                 if ln.startswith("proposal:") and len(ln.split(None, 1)) == 2), None)
    doc_id = next((ln.split("--doc ", 1)[1].split()[0] for ln in prop.out.splitlines()
                   if "--doc " in ln and ln.split("--doc ", 1)[1].split()), None)
    if prop.code != 0 or not path or not doc_id:
        raise SystemFailure(f"{label} exited {prop.code} without its proposal: and --doc lines: "
                            f"{(prop.err.strip() or prop.out.strip())[-160:]}")
    return path, doc_id


def topic_texts(doc: dict, section: str = "taylor_topics") -> list[str]:
    parsed = read(doc)
    tab = parsed["tabs"][parsed["target_tab"]]
    return [tab["items"][i]["text"] for i in parsed["sections"][section]["items"]]


def sage(ev: Evidence) -> dict:
    """Privacy: personal words are held for SAGE, WREN refuses without a stamp, a hold writes
    nothing, an approval lands, and a clean topic flows with no SAGE at all."""
    doc = doc_of("Kaed x Taylor")
    rev_start = read(doc)["revision_id"]

    def topic(text: str) -> str:
        made = sh("scripts/register.py", "add-topic", "--person", "kaed", "--text", text,
                  "--instruction-date", INSTRUCTION_DATE)
        ev.cmd(f"register.py add-topic --person kaed --text \"{text}\"", made)
        return system_json(made, "register.py add-topic", "ref")["ref"]

    def deliver(path: str, doc_id: str, label: str) -> Run:
        applied = sh("scripts/docs_edit.py", "add-topic", "--doc", doc_id, "--proposal", path)
        ev.cmd(f"docs_edit.py add-topic --doc {doc_id[:12]}... --proposal {Path(path).name}   ({label})", applied)
        return applied

    # 1. Personal context SAGE keeps out of the manager's Doc.
    held_text = "Family matter Kaed raised after the meeting"
    held = topic(held_text)
    prop = sh("scripts/docs_propose.py", "add-topic", "--ref", held)
    ev.cmd(f"docs_propose.py add-topic --ref {held}", prop)
    held_path, doc_id = proposal_of(prop, "docs_propose.py add-topic")
    unstamped = deliver(held_path, doc_id, "no SAGE stamp yet")
    hold = sh("scripts/privacy_review.py", "--hold", held_path, "--reason",
              "Personal family context belongs in Taylor's private notes, not in the Doc Kaed reads.")
    ev.cmd(f"privacy_review.py --hold {Path(held_path).name} --reason ...   (as SAGE)", hold)
    after_hold = deliver(held_path, doc_id, "after SAGE's hold")
    rev_after_hold = read(doc)["revision_id"]
    held_row = system_row("held topic", "SELECT ref, status FROM topics WHERE ref = ?", held)
    held_items = scalar("SELECT COUNT(*) FROM doc_items WHERE item_ref = ?", held)
    notes = register.FIXTURE_PRIVATE_NOTES
    notes_before = notes.read_text(encoding="utf-8") if notes.exists() else ""
    kept = sh("scripts/register.py", "keep-private", held)
    ev.cmd(f"register.py keep-private {held}   (Taylor: yes, keep it private)", kept)
    notes_after = notes.read_text(encoding="utf-8") if notes.exists() else ""
    held_after = system_row("held topic", "SELECT ref, status FROM topics WHERE ref = ?", held)

    # 2. Personal context that is the work itself: SAGE approves, and only then does it land.
    ok_text = "Shift swap to cover a medical appointment"
    approved = topic(ok_text)
    prop2 = sh("scripts/docs_propose.py", "add-topic", "--ref", approved)
    ev.cmd(f"docs_propose.py add-topic --ref {approved}", prop2)
    ok_path, _ = proposal_of(prop2, "docs_propose.py add-topic")
    unstamped2 = deliver(ok_path, doc_id, "no SAGE stamp yet")
    rev_before_approve = read(doc)["revision_id"]
    approve = sh("scripts/privacy_review.py", "--approve", ok_path, "--reason",
                 "The shift swap is the work Kaed has to act on, and it names no medical detail.")
    ev.cmd(f"privacy_review.py --approve {Path(ok_path).name} --reason ...   (as SAGE)", approve)
    landed = deliver(ok_path, doc_id, "after SAGE's approval")

    # 3. A clean topic: the screen passes it, and it flows with no SAGE.
    clean_text = "Christmas lights for the patio"
    clean = topic(clean_text)
    prop3 = sh("scripts/docs_propose.py", "add-topic", "--ref", clean)
    ev.cmd(f"docs_propose.py add-topic --ref {clean}", prop3)
    clean_path, _ = proposal_of(prop3, "docs_propose.py add-topic")
    landed3 = deliver(clean_path, doc_id, "no SAGE involved")
    texts = topic_texts(doc)
    stamps = rows("SELECT item_ref, verdict, category, reviewer FROM privacy_reviews ORDER BY id")

    # 4. The SAGE-only gate, driven with payloads shaped like the live session's (audit rows 61 to 63:
    #    a main-thread call carries no agent_id; a subagent call carries agent_id and agent_type).
    command = f'python scripts/privacy_review.py --approve {held_path} --reason "x"'
    base = {"session_id": "acceptance-sage", "transcript_path": str(ROOT / "no-transcript.jsonl"), "cwd": str(ROOT),
            "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command, "description": "record a privacy verdict"},
            "tool_use_id": "toolu_acceptance_sage"}
    as_wren = run_hook("require-privacy-agent.py", {**base, "agent_id": "a8a24234a720a8154", "agent_type": "wren"})
    ev.cmd("hook require-privacy-agent: privacy_review.py from WREN (agent_id + agent_type wren)", as_wren)
    as_main = run_hook("require-privacy-agent.py", base)
    ev.cmd("hook require-privacy-agent: privacy_review.py from the main thread (no agent_id)", as_main)
    as_sage = run_hook("require-privacy-agent.py", {**base, "agent_id": "a9e344b62c1f7e11b", "agent_type": "sage"})
    ev.cmd("hook require-privacy-agent: privacy_review.py from SAGE", as_sage)

    ev.add(f"- Kaed's Doc revision: start `{rev_start[:20]}...`, after the hold `{rev_after_hold[:20]}...` "
           f"(unchanged), before the approval `{rev_before_approve[:20]}...`")
    ev.add(f"- held topic before keep-private `{held_row}`, doc_items rows for it: {held_items}; "
           f"after keep-private `{held_after}`")
    ev.add(f"- private notes gained the held words: {held_text in notes_after and held_text not in notes_before}")
    ev.add(f"- Kaed's taylor_topics as re-read from Google: `{texts}`")
    ev.add(f"- privacy_reviews rows: `{stamps}`")
    ok = ("privacy_review: required" in prop.out and unstamped.code == 2 and "SAGE" in unstamped.err
          and hold.code == 0 and after_hold.code == 2 and "holding" in after_hold.err
          and rev_after_hold == rev_start and held_row["status"] == "queued" and held_items == 0
          and held_text not in texts and kept.code == 0 and held_after["status"] == "dropped"
          and held_text in notes_after and held_text not in notes_before
          and "privacy_review: required" in prop2.out and unstamped2.code == 2 and approve.code == 0
          and landed.code == 0 and ok_text in texts
          and "privacy_review: not_required" in prop3.out and landed3.code == 0 and clean_text in texts
          and not any(s["item_ref"] == clean for s in stamps)
          and [(s["item_ref"], s["verdict"]) for s in stamps] == [(held, "hold"), (approved, "approve")]
          and all(s["reviewer"] == "SAGE" for s in stamps)
          and as_wren.code == 2 and as_main.code == 2 and as_sage.code == 0)
    return {"ok": ok, "summary": f"{held} (family) held: WREN refused without a stamp and again after SAGE's hold, "
                                 f"Doc revision unchanged, kept in the private notes on request; {approved} (health) "
                                 f"refused until SAGE approved, then landed; {clean} flowed with no SAGE; "
                                 f"privacy_review.py refused from WREN and the main thread, allowed from SAGE"}


def register_digest() -> str:
    """The register's whole logical content, read through a read-only connection."""
    import sqlite3  # noqa: PLC0415

    conn = sqlite3.connect(ea_db.read_only_uri(ea_db.FIXTURE_DB), uri=True)
    try:
        return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()
    finally:
        conn.close()


def register_files() -> dict[str, tuple[str, int] | None]:
    """(sha256, size) of the register file and its -wal and -shm, or None for a file that is absent.

    The logical digest above cannot see a write to the file itself, nor tell SQLite's own
    WAL index files from data, so LARK's leg compares these too.
    """
    out: dict[str, tuple[str, int] | None] = {}
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(ea_db.FIXTURE_DB) + suffix)
        out[suffix or "db"] = ((hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)
                               if path.exists() else None)
    return out


def files_unchanged(before: dict, after: dict) -> bool:
    """No data written: the database's bytes are identical, and the -wal is unchanged or was created
    empty. The -shm is SQLite's shared-memory index (readers mark it), reported but not compared."""
    wal_ok = after["-wal"] == before["-wal"] or (before["-wal"] is None and after["-wal"] is not None
                                                   and after["-wal"][1] == 0)
    return before["db"] is not None and after["db"] == before["db"] and wal_ok


def lark_prep(ev: Evidence) -> dict:
    """LARK's prep is read only, and is blueprint s.10's deeper briefing, Taylor's part first."""
    doc = doc_of("Kaed x Taylor")
    for args in (("--text", "Send Kaed the patio staffing numbers", "--owner", "taylor", "--due", "2026-10-06"),
                 ("--text", "Bring the bar inventory variance", "--owner", "kaed", "--due", "2026-10-07"),
                 ("--text", "Draft the weekend coverage rota", "--owner", "kaed", "--due", "unresolved")):
        made = sh("scripts/register.py", "add-action", *args, "--counterpart", "kaed",
                  "--instruction-date", INSTRUCTION_DATE)
        ev.cmd(f"register.py add-action {' '.join(args)} --counterpart kaed   (setup)", made)
        system_json(made, "register.py add-action", "ref")
    you_owe = [r["ref"] for r in rows("SELECT a.ref FROM actions a JOIN people o ON o.id = a.owner_person_id"
                                      " JOIN people c ON c.id = a.counterpart_person_id WHERE o.key = 'taylor'"
                                      " AND c.key = 'kaed' AND a.status IN ('open', 'snoozed')")]
    to_answer = [r["ref"] for r in rows("SELECT n.ref FROM needs_input n JOIN actions a ON a.id = n.action_id"
                                        " JOIN people p ON p.id = a.counterpart_person_id"
                                        " WHERE p.key = 'kaed' AND n.status = 'open'")]
    they_owe = [r["ref"] for r in rows("SELECT a.ref FROM actions a JOIN people o ON o.id = a.owner_person_id"
                                       " WHERE o.key = 'kaed' AND a.status IN ('open', 'snoozed')")]

    db_before = register_digest()
    files_before = register_files()
    service = docs_read.docs_service()
    doc_before = docs_read.fetch(service, doc["doc_id"])
    brief = sh("scripts/prep.py", "--person", "Kaed")
    ev.cmd("prep.py --person Kaed   (\"prep me for Kaed\")", brief)
    deep = sh("scripts/prep.py", "--person", "kaed", "--deep")
    ev.cmd("prep.py --person kaed --deep   (still accepted; the briefing is always the deep one)", deep)
    files_after = register_files()
    db_after = register_digest()
    doc_after = docs_read.fetch(service, doc["doc_id"])
    smap = json.loads(doc["section_map_json"])
    doc_same = (doc_before.get("revisionId") == doc_after.get("revisionId")
                and _content(docs_read.parse(doc_before, smap)) == _content(docs_read.parse(doc_after, smap)))
    ev.add(f"- expected from the register: Taylor owes Kaed `{you_owe}`, Taylor must answer `{to_answer}`, "
           f"Kaed owes Taylor `{they_owe}`")
    ev.add(f"- register sha256 (logical dump) before `{db_before[:16]}...`, after `{db_after[:16]}...`")

    def shown(entry) -> str:
        return "absent" if entry is None else f"{entry[0][:12]}, {entry[1]} bytes"

    for name in ("db", "-wal", "-shm"):
        ev.add(f"- register file `{name}` before: {shown(files_before[name])}; after: {shown(files_after[name])}")
    ev.add(f"- database bytes identical and -wal unchanged or created empty: {files_unchanged(files_before, files_after)} "
           f"(SQLite's -shm index is reported, not compared: readers mark it)")
    ev.add(f"- Kaed's Doc revision before `{str(doc_before.get('revisionId'))[:20]}...`, after "
           f"`{str(doc_after.get('revisionId'))[:20]}...`; content identical: {doc_same}")
    # Each listed line's leading ref, by the section it is listed under. A question may quote
    # Kaed's action ref inside its own text; that is Taylor's question, not Kaed's list.
    def sections_of(text: str) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        heading = ""
        for line in text.splitlines():
            if not line.startswith("  "):
                heading = line
            elif line.split():
                found.setdefault(heading, set()).add(line.split()[0])
        return found

    # Headings start a line; a topic line may itself say "in the Doc: ...", so never search the text.
    headings = ["You owe Kaed", "You need to answer or decide", "Kaed owes you", "Topics for the next 1:1",
                "Carried forward in the Doc", "Last 1:1", "Next 1:1:", "Doc: "]
    printed = brief.out.splitlines()
    at = [next((i for i, line in enumerate(printed) if line.startswith(h)), -1) for h in headings]
    in_order = -1 not in at and at == sorted(at)
    listed = sections_of(brief.out)
    ev.add(f"- headings by the line they start: {dict(zip(headings, at))}; in blueprint s.10's order: {in_order}")
    ok = (brief.code == 0 and deep.code == 0 and brief.out == deep.out and db_before == db_after
          and files_unchanged(files_before, files_after) and doc_same and bool(you_owe) and bool(to_answer)
          and bool(they_owe) and doc["url"] in brief.out and in_order
          and set(you_owe) <= listed.get("You owe Kaed", set())
          and set(to_answer) <= listed.get("You need to answer or decide", set())
          and set(they_owe) <= listed.get("Kaed owes you", set())
          and "Carried forward in the Doc, as last read" in brief.out)
    return {"ok": ok, "summary": f"no data written (the register's bytes, -wal and contents, and Kaed's Doc, unchanged); "
                                 f"the briefing in blueprint s.10's order: what Taylor owes Kaed "
                                 f"({', '.join(you_owe)}) and must answer ({', '.join(to_answer)}) first, then what "
                                 f"Kaed owes ({', '.join(they_owe)}), the topics, what the Doc carries forward and "
                                 f"the last 1:1 as last read, the next 1:1 and the Doc link"}


def lessons_leg(ev: Evidence) -> dict:
    """Blueprint s.1 learning, G2's mechanism: a preference is in effect next session; a price is asked once, never adopted."""
    if overlay_leftovers():
        raise RuntimeError(f"the fixture overlay already holds lessons ({overlay_leftovers()[0]}); rerun with --rebuild")
    seeded = sh("scripts/overlay.py", "init")
    ev.cmd("overlay.py init   (the fixture overlay; a no-op after --rebuild)", seeded)

    def next_session(label: str) -> Run:
        done = subprocess.run([PY, str(ROOT / ".claude" / "hooks" / "session-start.py")], cwd=str(ROOT),
                              input='{"source": "startup"}', capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=ENV, timeout=60)
        run = Run(done.returncode, done.stdout, done.stderr)
        ev.cmd(f"hook session-start   ({label})", run)
        return run

    def asked() -> list[dict]:
        return rows("SELECT ref, source_ref FROM needs_input WHERE source_kind = 'lesson' AND status = 'open'")

    preference = "Answer first, then the detail"
    record = f'python scripts/lessons.py record --kind preference --text "{preference}"'
    by_main = run_hook("require-lessons-agent.py", {"tool_name": "Bash", "tool_input": {"command": record}})
    ev.cmd("hook require-lessons-agent: the orchestrator (main thread) records a lesson", by_main)
    by_reed = run_hook("require-lessons-agent.py", {"tool_name": "Bash", "agent_id": "acceptance-reed",
                                                    "agent_type": "reed", "tool_input": {"command": record}})
    ev.cmd("hook require-lessons-agent: REED records the same lesson", by_reed)

    before = next_session("before anything is learned")
    made = sh("scripts/lessons.py", "record", "--kind", "preference", "--text", preference,
              "--said", "answer first, then the detail")
    ev.cmd(f"lessons.py record --kind preference --text \"{preference}\"   (REED)", made)
    taught = system_json(made, "lessons.py record", "ref", "active")
    after = next_session("the next session")

    price = ("scripts/lessons.py", "record", "--kind", "preference", "--text", "The corporate package is $45 now",
             "--said", "the corporate package is $45 now")
    first = sh(*price)
    ev.cmd("lessons.py record --kind preference --text \"The corporate package is $45 now\"   (REED, as a "
           "preference on purpose: the screen decides)", first)
    held = system_json(first, "lessons.py record", "ref", "active", "question", "kind")
    once = asked()
    again = sh(*price)
    ev.cmd("lessons.py record ... \"The corporate package is $45 now\"   (Taylor says it again)", again)
    repeat = system_json(again, "lessons.py record", "ref", "active")
    twice = asked()
    ev.add(f"- open Needs Your Input questions from lessons after the first instance: {once}; after the repeat: {twice}")
    later = next_session("after the price, twice")
    listing = sh("scripts/lessons.py", "list")
    ev.cmd("lessons.py list   (\"show me what you've learned\")", listing)

    path = transcript_with("from now on, answer first")
    try:
        with open(path, "a", encoding="utf-8") as handle:
            for row in ({"type": "assistant", "message": {"role": "assistant", "content": [
                            {"type": "tool_use", "id": "toolu_lesson", "name": "Bash", "input": {"command": record}}]}},
                        {"type": "user", "message": {"role": "user", "content": [
                            {"type": "tool_result", "tool_use_id": "toolu_lesson", "content": "{}"}]}},
                        {"type": "assistant", "message": {"role": "assistant", "content": [
                            {"type": "text", "text": "Noted."}]}}):
                handle.write(json.dumps(row) + "\n")
        roll = run_hook("team-rollcall.py", {"transcript_path": path})
    finally:
        os.unlink(path)
    ev.cmd("hook team-rollcall on a turn where the orchestrator recorded a lesson itself", roll)

    in_effect = preference not in before.out and preference in after.out and taught["active"] is True
    one_question = (held["active"] is False and held["kind"] == "rule-candidate" and len(once) == 1
                    and once[0]["ref"] == held["question"] and repeat["ref"] == held["ref"] and twice == once)
    never_loaded = "$45" not in later.out and "NOT in effect" in later.out and "Waiting for your answer" in listing.out
    ok = (by_main.code == 2 and by_reed.code == 0 and in_effect and one_question and never_loaded
          and "THIS TURN RAN SOLO" in roll.out)
    return {"ok": ok, "summary": f"only REED records a lesson; a preference is in effect from the next session (the "
                                 f"session-start hook loads it); 'the corporate package is $45 now' is no lesson in "
                                 f"effect and exactly one question ({held['question']}), saying it again asks nothing "
                                 f"more, and no session loads it; a lesson the orchestrator writes itself is a SOLO "
                                 f"write in the roll call"}


# Mike's brief, as docs/FOR-TAYLOR.md quotes it: the exact lines each refusal must print.
NOT_SWITCHED_ON = {
    "milo": ("NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.",
             'To switch it on: say "architecture change ok: switch on Phase 2", and Mike builds it.'),
    "penn": ("NOT SWITCHED ON: PENN (sales and events pipeline) is outside your architecture.",
             'To switch it on: say "architecture change ok: add PENN", then Mike builds it.'),
    "tally": ("NOT SWITCHED ON: TALLY (reporting) is Phase 6, which you deferred.",
              'To switch it on: say "architecture change ok: resume Phase 6", then Mike builds it.'),
}


def inactive_dispatch(ev: Evidence) -> dict:
    """MILO, PENN and TALLY are refused before they start, with exactly the lines Taylor's docs quote.

    The payload is shaped like the live VS Code session's (5e587b4f, claude-vscode v2.1.222):
    the common hook fields, tool_name Agent, a tool_use_id, and the Agent input keys that
    session's dispatches carried (subagent_type, description, run_in_background, prompt).
    A dispatch comes from the main thread, so like audit row 61 it carries no agent_id.
    """
    transcript = transcript_with("process my 1:1 transcript with Kaed, and prep me for Kaed")

    def payload(agent: str) -> dict:
        return {"session_id": "acceptance-inactive", "transcript_path": transcript, "cwd": str(ROOT),
                "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "Agent",
                "tool_input": {"subagent_type": agent, "description": f"{agent} acceptance dispatch",
                               "run_in_background": False, "prompt": f"OBJECTIVE: {agent} acceptance dispatch"},
                "tool_use_id": f"toolu_acceptance_{agent}"}

    try:
        refused = {}
        for agent in NOT_SWITCHED_ON:
            refused[agent] = run_hook("require-active-agent.py", payload(agent))
            ev.cmd(f"hook require-active-agent: Agent {agent}", refused[agent])
        controls = {agent: run_hook("require-active-agent.py", payload(agent)) for agent in ("reed", "lark")}
        for agent, result in controls.items():
            ev.cmd(f"hook require-active-agent: Agent {agent}   (control)", result)
        # Explore depends on build mode, so it is asked of two copies rather than of this machine,
        # whose own marker (Mike's build machine, or none on a fresh clone) would decide it.
        explore: dict[bool, Run] = {}
        for build_mode in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root, env = _hook_copy(tmp, build_mode)
                done = subprocess.run([PY, str(root / ".claude" / "hooks" / "require-active-agent.py")],
                                      input=json.dumps(payload("Explore")), capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", env=env, timeout=60)
                explore[build_mode] = Run(done.returncode, done.stdout, done.stderr)
            ev.cmd("hook require-active-agent: Agent Explore on a copy "
                   + ("IN BUILD MODE (state/BUILD_MODE, this host)" if build_mode else "with no build marker")
                   + "   (control)", explore[build_mode])
        banner_milo = run_hook("announce-dispatch.py", payload("milo"))
        banner_reed = run_hook("announce-dispatch.py", payload("reed"))
        ev.cmd("hook announce-dispatch: Agent milo   (no banner for a refused dispatch)", banner_milo)
        ev.cmd("hook announce-dispatch: Agent reed   (control)", banner_reed)
    finally:
        os.unlink(transcript)
    relay = sh("scripts/team.py", "--agent", "MILO")
    ev.cmd("team.py --agent MILO   (what the orchestrator relays without dispatching)", relay)
    audit = rows("SELECT decision, rule_id FROM audit WHERE hook = 'require-active-agent'"
                 " AND session_id = 'acceptance-inactive' ORDER BY id")
    ev.add(f"- audit rows: `{audit}`")
    exact = {agent: refused[agent].code == 2 and refused[agent].err == "\n".join(lines) + "\n"
             for agent, lines in NOT_SWITCHED_ON.items()}
    ev.add(f"- refusal printed exactly the two lines: `{exact}`")
    ok = (all(exact.values()) and controls["reed"].code == 0 and not controls["reed"].err.strip()
          and controls["lark"].code == 0 and explore[False].code == 2 and "NOT ON THIS TEAM" in explore[False].err
          and explore[True].code == 0
          and not banner_milo.out.strip() and ">> REED dispatched" in banner_reed.out
          and relay.code == 0 and relay.out == "\n".join(NOT_SWITCHED_ON["milo"]) + "\n"
          and [a["decision"] for a in audit] == ["deny", "deny", "deny", "allow", "allow"])
    return {"ok": ok, "summary": "MILO, PENN and TALLY refused by the real hook with exactly the lines FOR-TAYLOR "
                                 "quotes, nothing else printed; REED and LARK allowed; Explore refused without a "
                                 "build marker and let through only in build mode; no dispatch banner for a refused "
                                 "agent; team.py relays the same lines; five audit rows"}


def checkbox_experiment(ev: Evidence) -> str:
    chk = doc_of("Checkbox experiment")
    probe = sh("scripts/docs_read.py", "--doc", chk["doc_id"], "--checkbox-probe")
    ev.cmd("docs_read.py --doc <checkbox fixture> --checkbox-probe", probe)
    return probe.out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def run_leg(fn) -> tuple[Evidence, dict]:
    """Run one leg. Never Passed without the leg's own observed evidence.

    A SystemFailure is FAILED. Any other exception is the harness failing to exercise
    the test, which is Blocked in every leg (blueprint s.12).
    """
    ev = Evidence()
    try:
        result = fn(ev)
    except SystemFailure as exc:
        return ev, {"ok": False, "summary": f"system failure: {exc}"}
    except Exception as exc:  # noqa: BLE001
        # swallow: recorded as Blocked with the exception, never as Passed. One leg
        # the harness could not exercise must not hide the evidence of the others.
        return ev, {"ok": False, "blocked": True, "summary": f"harness error {exc.__class__.__name__}: {exc}"}
    if not result["ok"]:
        # A leg's summary describes the outcome it checks for. On a failure that is what
        # was expected, not what happened, and it must not read like a pass.
        result = {**result, "summary": f"expected, not observed: {result['summary']}"}
    return ev, result


def verdict(result: dict) -> str:
    if result["ok"]:
        return "Passed"
    return "Blocked" if result.get("blocked") else "FAILED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fixtures", action="store_true", required=True)
    parser.add_argument("--rebuild", action="store_true", help="delete and rebuild every fixture Doc first")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    if not args.rebuild:
        conn = None
        try:
            conn = db()
            reasons = leftover_state(conn) or overlay_leftovers()
        except Exception as exc:  # noqa: BLE001
            # Not swallowed: refused loudly, before any leg and without a report. A
            # fixture that could not be checked has not been shown to be fresh.
            print(f"cannot check that the fixtures are fresh ({exc.__class__.__name__}: {exc}); nothing was run",
                  file=sys.stderr)
            return 2
        finally:
            if conn is not None:
                conn.close()
        if reasons:
            print(NOT_BUILT if reasons == [NOTHING_BUILT] else LEFTOVER, file=sys.stderr)
            return 2

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sections: list[tuple[str, Evidence, dict]] = []
    setup = Evidence()
    if args.rebuild:
        rebuild(setup)
    fixtures = rows("SELECT d.title, d.doc_id, d.role, p.key FROM docs d LEFT JOIN people p ON p.id = d.person_id"
                    " WHERE d.fixture = 1 ORDER BY d.role, p.key")

    guard = sh("scripts/validate_guardrails.py", "--self-test", "--verbose")
    mutation = sh("scripts/validate_guardrails.py", "--mutation-test")
    register_test = sh("scripts/register.py", "--self-test")
    units = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=str(ROOT),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=600)
    contracts = sh("scripts/validate_agent_contracts.py")
    vendored = sh("scripts/check_vendored.py", "--upstream", "PIPER=C:/PIPER", "--upstream", "STEVIE=C:/Users/kells/STEVIE")         if Path("C:/PIPER").exists() else sh("scripts/check_vendored.py")

    tests = [("P1.1", p11), ("P1.2", p12), ("P1.3", p13)]
    results: dict[str, dict] = {}
    for name, fn in tests:
        ev, results[name] = run_leg(fn)
        sections.append((name, ev, results[name]))
    for name, fn in (("P1.4", lambda ev: p14(ev, results["P1.2"].get("a_ref", "A-0001"))), ("P1.5", p15),
                     ("P1.6", p16), ("G1", g1), ("G4", g4), ("G5", g5),
                     ("SAGE", sage), ("LARK prep", lark_prep), ("Inactive dispatch", inactive_dispatch),
                     ("Lessons", lessons_leg)):
        ev, results[name] = run_leg(fn)
        sections.append((name, ev, results[name]))
    probe_ev = Evidence()
    probe = checkbox_experiment(probe_ev)

    session = {
        "P1.1": "REED classifying '/add add manager accountability to Kaed's next 1:1' as a topic, not an action",
        "P1.2": "REED splitting one sentence into a Taylor action and a Casey topic",
        "P1.3": "REED recording no owner or date, and asking one targeted question only if it matters",
        "P1.4": "a manager typing Done in a LIVE Doc, under Taylor's token",
        "P1.5": "Taylor asking 'What do I owe everyone?' and 'How many times did this move?' through /owe",
        "P1.6": "a LIVE Calendar series (no calendar.readonly on the build token; build step 5 is Blocked)",
        "G1": "the orchestrator answering 'remove the reservation send approval' with a proposal in "
              "state/taylor/proposals.md",
        "G4": "the orchestrator telling Taylor 'not updated' in his terms",
        "G5": "the orchestrator asking which person was meant",
        "SAGE": "SAGE's own judgement on a live flagged proposal, and the orchestrator's one-line relay of a hold",
        "LARK prep": "LARK presenting a live 'prep me for Kaed' in that order, Taylor's part first",
        "Inactive dispatch": "the orchestrator relaying the lines without dispatching, in a live VS Code session",
        "Lessons": "REED telling a preference from a rule in Taylor's own words, SAGE's G2 judgement when unsure, "
                   "and the one question reaching Taylor",
    }
    lines = [
        f"# Phase 1 acceptance, {args.date}",
        "",
        f"Run started {started} on `{socket.gethostname()}` by `scripts/acceptance.py --fixtures"
        f"{' --rebuild' if args.rebuild else ''}`. Every verdict below was computed from what this run observed.",
        "",
        "Blueprint s.12: a test is Passed only with observed evidence; Failed or Blocked otherwise. Each test has",
        "a script leg (deterministic code, run here against fixture Docs through the same commands the agents",
        "use) and a session leg (an agent's judgement in a live VS Code session). The session leg is Blocked on",
        "the build machine for every test, and is listed so it is not mistaken for done.",
        "",
        "## Results",
        "",
        "| Test | Script leg (fixtures) | Session leg | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for name in ("P1.1", "P1.2", "P1.3", "P1.4", "P1.5", "P1.6", "G1"):
        r = results[name]
        lines.append(f"| {name} | {verdict(r)} | Blocked: {session[name]} | {r['summary']} |")
    lines.append(f"| G2 | Blocked | Blocked | Learning from repeated DRAFT edits needs the Phase 3 and 5 draft workflows. "
                 f"The mechanism it will use is the Lessons leg below: {verdict(results['Lessons'])}. |")
    lines.append("| G3 | Blocked | Blocked | Out of Phase 1 scope: private transcripts are Phase 2 (Wispr). |")
    for name in ("G4", "G5", "SAGE", "LARK prep", "Inactive dispatch", "Lessons"):
        r = results[name]
        lines.append(f"| {name} | {verdict(r)} | Blocked: {session[name]} | {r['summary']} |")
    lines += ["", "SAGE, LARK prep and Inactive dispatch are the roster expansion's legs: blueprint s.2 enforced on",
              "every Doc proposal, LARK's read-only prep under deviation D-3, and the switched-off agents refused",
              "before they start. Lessons is blueprint s.1's learning loop, run in the fixture overlay",
              "(state/taylor-fixtures/). None of them is a blueprint test id.",
              "", "## Fixture Docs (Mike's Drive, registered fixture=1 in state/fixtures.db)", "",
              "| Role | Person | Doc id | Title |", "| --- | --- | --- | --- |"]
    lines += [f"| {f['role']} | {f['key'] or '-'} | `{f['doc_id']}` | {f['title']} |" for f in fixtures]
    if setup.lines:
        lines += ["", "### Rebuild", ""] + setup.lines
    for name, ev, result in sections:
        lines += ["", f"## {name}: {verdict(result)} (script leg)", ""] + ev.lines
    lines += ["", "## Checkbox experiment", "",
              "Run on the `[FIXTURE] Checkbox experiment` Doc, whose checklist was created with the API's",
              "BULLET_CHECKBOX preset. What the API returns for an unchecked checklist item:", ""] + probe_ev.lines + [
              "", "Findings, observed: the bullet carries only a listId; the list's nesting level reports",
              "`glyphType: GLYPH_TYPE_UNSPECIFIED`, `glyphFormat: \"%0\"` and no glyph symbol. There is no field for",
              "checked or unchecked, and the batchUpdate request list has no request that sets one, so the API",
              "cannot tick a box. What a HUMAN tick looks like through the API is therefore not observable from",
              "this machine without a browser click. Status-cell convention adopted: completion is the word Done",
              "in the action table's Status cell, which the live Docs already have. See docs/OPEN-QUESTIONS.md."]
    lines += ["", "## Guardrail self-test (verbose)", "", f"`python scripts/validate_guardrails.py --self-test --verbose` -> exit {guard.code}", "", "```"]
    lines += guard.out.strip().splitlines() + ["```", "", f"`python scripts/validate_guardrails.py --mutation-test` -> exit {mutation.code}", "", "```"]
    lines += mutation.out.strip().splitlines() + ["```", "", "## Register self-test and unit tests", "",
                                                   f"`python scripts/register.py --self-test` -> exit {register_test.code}", "", "```"]
    lines += register_test.out.strip().splitlines() + ["```", "", f"`python -m unittest discover -s tests -t .` -> exit {units.returncode}", "", "```"]
    lines += (units.stderr.strip().splitlines()[-4:]) + ["```", "",
              f"`python scripts/validate_agent_contracts.py` -> exit {contracts.code}", "", "```"]
    lines += contracts.out.strip().splitlines() + ["```", "", f"`python scripts/check_vendored.py` (upstreams when present) -> exit {vendored.code}", "", "```"]
    lines += vendored.out.strip().splitlines() + ["```", ""]

    text = "\n".join(lines) + "\n"
    import validate_content_rules  # noqa: PLC0415

    findings = validate_content_rules.check_text(text, "docs/acceptance/report.md")
    if findings:
        text += "\nCONTENT-RULE FINDINGS IN THIS REPORT: " + "; ".join(str(f) for f in findings) + "\n"
    out = ROOT / "docs" / "acceptance" / f"P1-{args.date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text.encode("utf-8"))
    failed = [n for n, r in results.items() if not r["ok"]]
    print(f"wrote {out.relative_to(ROOT)}")
    for name in ("P1.1", "P1.2", "P1.3", "P1.4", "P1.5", "P1.6", "G1", "G4", "G5",
                 "SAGE", "LARK prep", "Inactive dispatch", "Lessons"):
        print(f"  {name:17} {verdict(results[name]):7}  {results[name]['summary'][:110]}")
    print(f"  guardrails exit {guard.code}, mutation exit {mutation.code}, register self-test exit "
          f"{register_test.code}, unit tests exit {units.returncode}, contracts exit {contracts.code}, "
          f"vendored exit {vendored.code}")
    return 1 if (failed or guard.code or mutation.code or register_test.code or units.returncode
                 or contracts.code or vendored.code) else 0


if __name__ == "__main__":
    sys.exit(main())
