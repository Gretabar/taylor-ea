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

BLOCKED IS NOT FAILED. A leg that could not be exercised is Blocked. P1.6 and G4
stand on fixture preconditions the system under test does not own, so a harness
exception there is reported Blocked; a script that exits non-zero or breaks its
output contract is a SystemFailure and is still FAILED.

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
from datetime import date, datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

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
    path = next(ln.split(None, 1)[1] for ln in prop.out.splitlines() if ln.startswith("proposal:"))
    doc_id = next(ln.split("--doc ")[1].split()[0] for ln in prop.out.splitlines() if "--doc " in ln)
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
    result = sh("scripts/make_fixtures.py", "--create")
    ev.cmd("make_fixtures.py --create", result)
    if result.code != 0:
        raise RuntimeError("fixtures could not be built; nothing else can be tested")


LEFTOVER = "fixtures carry state from a previous run; rerun with --rebuild"
NOT_BUILT = "no fixtures are built; rerun with --rebuild"
NOTHING_BUILT = "no fixture Docs are registered"

# Tables make_fixtures.py --create never writes and every leg does. One row is
# enough to say a run happened here.
RUN_TABLES = ("actions", "action_events", "topics", "needs_input", "doc_items", "reconcile_events",
              "captures", "proposals", "counters")


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
    ref = topic.json()["ref"]
    _, applied, _ = propose_and_apply("add-topic", ref, ev)
    parsed = read(doc)
    section = parsed["sections"]["taylor_topics"]
    texts = [parsed["tabs"][parsed["target_tab"]]["items"][i]["text"] for i in section["items"]]
    topic_rows = rows("SELECT ref, status, placed_revision_id FROM topics WHERE ref = ?", ref)
    actions_after, meetings_after = scalar("SELECT COUNT(*) FROM actions"), scalar("SELECT COUNT(*) FROM meetings")
    calendar_free = [p.name for p in (HERE / "register.py", HERE / "docs_propose.py", HERE / "docs_edit.py")
                     if not imports_calendar(p)]
    ev.add(f"- topic row: `{topic_rows}`")
    ev.add(f"- Kaed's newest block, taylor_topics ('Top Focuses') as re-read from Google: `{texts}`")
    ev.add(f"- actions before/after: {actions_before}/{actions_after}; meetings before/after: {meetings_before}/{meetings_after}")
    ev.add(f"- Calendar: none of {', '.join(calendar_free)} imports calendar_next or asks for calendar.readonly, "
           f"and this token has no calendar scope, so a Calendar call would have failed the step")
    ok = (applied.code == 0 and texts.count("Manager accountability") == 1 and topic_rows[0]["status"] == "placed"
          and actions_after == actions_before and meetings_after == meetings_before and len(calendar_free) == 3)
    return {"ok": ok, "summary": f"1 topic {ref} placed in Kaed's taylor_topics (rev {topic_rows[0]['placed_revision_id'][:12]}...), "
                                 f"0 actions, 0 meetings created, 0 Calendar calls"}


def p12(ev: Evidence) -> dict:
    due = register.resolve_date("Friday", date.fromisoformat(INSTRUCTION_DATE))
    ev.add(f"- resolve-date Friday from {INSTRUCTION_DATE} (a Thursday): `{due['status']} {due['date']}`")
    action = sh("scripts/register.py", "add-action", "--text", "Send Casey the manager bonus structure",
                "--owner", "taylor", "--due", str(due["date"]), "--due-note", "Friday", "--counterpart", "casey",
                "--origin-ref", "/add I told Casey I'll send the bonus structure Friday; add it to our next 1:1",
                "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-action --owner taylor --due <resolved Friday> --counterpart casey", action)
    a_ref = action.json()["ref"]
    topic = sh("scripts/register.py", "add-topic", "--person", "casey", "--text", "Manager bonus structure",
               "--instruction-date", INSTRUCTION_DATE)
    ev.cmd("register.py add-topic --person casey --text \"Manager bonus structure\"", topic)
    t_ref = topic.json()["ref"]
    _, a_applied, _ = propose_and_apply("add-action", a_ref, ev)
    _, t_applied, _ = propose_and_apply("add-topic", t_ref, ev)
    doc = doc_of("Casey x Taylor")
    parsed = read(doc)
    found = docs_read.locate(parsed, item_kind="action", item_ref=a_ref, named_range=f"ea:action:{a_ref}",
                             stored_hash=None, columns=None)
    row = rows("SELECT a.ref, p.key AS owner, a.due_date, a.project_ref, a.status FROM actions a"
               " JOIN people p ON p.id = a.owner_person_id WHERE a.ref = ?", a_ref)[0]
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
    ref = action.json()["ref"]
    row = rows("SELECT ref, owner_person_id, owner_unresolved, due_date, due_unresolved FROM actions WHERE ref = ?", ref)[0]
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
    action = rows("SELECT ref, status, completed_via, completed_at FROM actions WHERE ref = ?", a_ref)[0]
    events = rows("SELECT e.actor, e.field, e.old_value, e.new_value, e.source FROM action_events e"
                  " JOIN actions a ON a.id = e.action_id WHERE a.ref = ? AND e.field = 'status'", a_ref)
    owed = sh("scripts/register.py", "--json", "owed")
    still_owed = [i["ref"] for items in owed.json()["by_person"].values() for i in items]
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
    c_ref = act.json()["ref"]
    _, c_applied, _ = propose_and_apply("add-action", c_ref, ev, "--doc", chk["doc_id"])
    strike_rev = manager_strikes(chk, c_ref)
    ev.add(f"- harness: struck through the {c_ref} checklist line (the believed rendering of a ticked box; the API "
           f"cannot set a checkbox); revision `{strike_rev[:24]}...`")
    tick3 = sh("scripts/ea_tick.py", "--fixtures")
    ev.cmd("ea_tick.py --fixtures  (checkbox form)", tick3)
    c_action = rows("SELECT ref, status, completed_via FROM actions WHERE ref = ?", c_ref)[0]
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
    ref = action.json()["ref"]
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


def p16(ev: Evidence) -> dict:
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
    ev.add(f"- Mark's meeting: `{meeting}` (from a synthetic events.instances series: last 2026-09-30, every 14 days)")
    ev.add(f"- topic register row: meeting_id {result['meeting_id']}, next_at {result['next_at']}")
    ev.add(f"- Mark's Doc taylor_topics as re-read: `{texts}`; meetings before/after: {meetings_before}/{meetings_after}")
    ok = (applied.code == 0 and meeting["cadence_observed"] == "biweekly" and result["meeting_id"] == meeting["id"]
          and str(result["next_at"]).startswith("2026-10-14") and "Patio season close-out plan" in texts
          and meetings_after == meetings_before)
    return {"ok": ok, "summary": "topic placed in Mark's own Doc against his biweekly series, next_at 2026-10-14 "
                                 "(two weeks out), no meeting invented; Calendar input was a fixture series"}


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


def g1(ev: Evidence) -> dict:
    blueprint = ROOT / "context" / "architecture" / "blueprint.md"
    sha_before = hashlib.sha256(blueprint.read_bytes()).hexdigest()
    asked = transcript_with("remove the reservation send approval")
    approved = transcript_with("architecture change ok: remove the reservation send approval")
    try:
        a_block = run_hook("protect-architecture.py", {"tool_name": "Edit", "transcript_path": asked, "tool_input": {
            "file_path": str(blueprint), "old_string": "x", "new_string": "y"}})
        ev.cmd("hook protect-architecture: Edit blueprint.md, latest message 'remove the reservation send approval'", a_block)
        a_claude = run_hook("protect-architecture.py", {"tool_name": "Edit", "transcript_path": asked, "tool_input": {
            "file_path": str(ROOT / "CLAUDE.md"), "old_string": "x", "new_string": "y"}})
        ev.cmd("hook protect-architecture: Edit CLAUDE.md, same message", a_claude)
        a_memo = run_hook("protect-architecture.py", {"tool_name": "Write", "transcript_path": asked, "tool_input": {
            "file_path": str(ROOT / "docs" / "DEVIATIONS.md"), "content": "proposal"}})
        ev.cmd("hook protect-architecture: Write docs/DEVIATIONS.md (where the proposal goes)", a_memo)
        a_ok = run_hook("protect-architecture.py", {"tool_name": "Edit", "transcript_path": approved, "tool_input": {
            "file_path": str(blueprint), "old_string": "x", "new_string": "y"}})
        ev.cmd("hook protect-architecture: Edit blueprint.md after Taylor typed 'architecture change ok'", a_ok)

        # Layer B on "Taylor's machine": a copy of the hook layer with no build marker.
        with tempfile.TemporaryDirectory() as tmp:
            for part in (".claude", "context", "scripts"):
                shutil.copytree(ROOT / part, Path(tmp) / part, ignore=shutil.ignore_patterns("__pycache__"))
            (Path(tmp) / "state").mkdir()
            env = dict(ENV, EA_ROOT=tmp, CLAUDE_PROJECT_DIR=tmp)
            b_block = subprocess.run([PY, str(Path(tmp) / ".claude" / "hooks" / "protect-architecture.py")],
                                     input=json.dumps({"tool_name": "Edit", "transcript_path": approved, "tool_input": {
                                         "file_path": str(Path(tmp) / ".claude" / "hooks" / "require-approval.py"),
                                         "old_string": "x", "new_string": "y"}}),
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)
            b = Run(b_block.returncode, b_block.stdout, b_block.stderr)
            ev.cmd("hook protect-architecture on a copy WITHOUT state/BUILD_MACHINE: Edit require-approval.py, "
                   "even with 'architecture change ok'", b)
            marker = subprocess.run([PY, str(Path(tmp) / ".claude" / "hooks" / "protect-architecture.py")],
                                    input=json.dumps({"tool_name": "Bash", "transcript_path": approved, "tool_input": {
                                        "command": "echo MKsLaptop > state/BUILD_MACHINE"}, "cwd": tmp}),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)
            m = Run(marker.returncode, marker.stdout, marker.stderr)
            ev.cmd("hook protect-architecture on that copy: Bash `echo ... > state/BUILD_MACHINE`", m)
        b_build = run_hook("protect-architecture.py", {"tool_name": "Edit", "transcript_path": asked, "tool_input": {
            "file_path": str(ROOT / ".claude" / "hooks" / "require-approval.py"), "old_string": "x", "new_string": "y"}})
        ev.cmd(f"hook protect-architecture on the build machine ({socket.gethostname()}, marker present): Edit "
               f"require-approval.py", b_build)
    finally:
        os.unlink(asked)
        os.unlink(approved)
    sha_after = hashlib.sha256(blueprint.read_bytes()).hexdigest()
    ev.add(f"- blueprint.md sha256 before `{sha_before[:16]}...`, after `{sha_after[:16]}...`")
    ok = (a_block.code == 2 and "DEVIATIONS.md" in a_block.err and a_claude.code == 2 and a_memo.code == 0
          and a_ok.code == 0 and b.code == 2 and m.code == 2 and b_build.code == 0 and sha_before == sha_after)
    return {"ok": ok, "summary": "rules text blocked without Taylor's phrase (block text points to DEVIATIONS.md), "
                                 "allowed with it; code and permissions blocked on a machine without the build "
                                 "marker even with the phrase; the marker cannot be minted from a session; "
                                 "blueprint sha256 unchanged"}


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
    t_row = rows("SELECT ref, status, last_error FROM topics WHERE ref = ?", t_ref)[0]

    kaed = doc_of("Kaed x Taylor")
    revision_before = read(kaed)["revision_id"]
    stale_topic = system_json(sh("scripts/register.py", "add-topic", "--person", "kaed", "--text",
                                 "Staff recognition budget", "--instruction-date", INSTRUCTION_DATE),
                              "register.py add-topic", "ref")["ref"]
    _, stale, _ = propose_and_apply("add-topic", stale_topic, ev, apply_extra=("--simulate-stale-revision",))
    revision_after = read(kaed)["revision_id"]
    s_row = rows("SELECT ref, status FROM topics WHERE ref = ?", stale_topic)[0]
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


def checkbox_experiment(ev: Evidence) -> str:
    chk = doc_of("Checkbox experiment")
    probe = sh("scripts/docs_read.py", "--doc", chk["doc_id"], "--checkbox-probe")
    ev.cmd("docs_read.py --doc <checkbox fixture> --checkbox-probe", probe)
    return probe.out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

# A harness crash in these legs is Blocked, not FAILED. Each stands on a fixture
# precondition the system under test does not own (P1.6 a seeded Calendar series, G4
# a sacrificial Doc that a previous G4 deleted), so an exception there says the test
# could not be exercised. A SystemFailure is FAILED in every leg.
BLOCK_ON_HARNESS_ERROR = frozenset({"P1.6", "G4"})


def run_leg(name: str, fn) -> tuple[Evidence, dict]:
    """Run one leg. Never Passed without the leg's own observed evidence."""
    ev = Evidence()
    try:
        result = fn(ev)
    except SystemFailure as exc:
        return ev, {"ok": False, "summary": f"system failure: {exc}"}
    except Exception as exc:  # noqa: BLE001
        # swallow: recorded as FAILED or Blocked with the exception, never as Passed.
        # One broken test must not hide the evidence of the others.
        result = {"ok": False, "summary": f"harness error {exc.__class__.__name__}: {exc}"}
        if name in BLOCK_ON_HARNESS_ERROR:
            result["blocked"] = True
        return ev, result
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
            reasons = leftover_state(conn)
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
        ev, results[name] = run_leg(name, fn)
        sections.append((name, ev, results[name]))
    for name, fn in (("P1.4", lambda ev: p14(ev, results["P1.2"].get("a_ref", "A-0001"))), ("P1.5", p15),
                     ("P1.6", p16), ("G1", g1), ("G4", g4), ("G5", g5)):
        ev, results[name] = run_leg(name, fn)
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
        "G1": "the orchestrator answering 'remove the reservation send approval' with a DEVIATIONS.md proposal",
        "G4": "the orchestrator telling Taylor 'not updated' in his terms",
        "G5": "the orchestrator asking which person was meant",
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
    lines.append("| G2 | Blocked | Blocked | Out of Phase 1 scope: preference learning needs the Phase 3 and 5 draft workflows. |")
    lines.append("| G3 | Blocked | Blocked | Out of Phase 1 scope: private transcripts are Phase 2 (Wispr). |")
    for name in ("G4", "G5"):
        r = results[name]
        lines.append(f"| {name} | {verdict(r)} | Blocked: {session[name]} | {r['summary']} |")
    lines += ["", "## Fixture Docs (Mike's Drive, registered fixture=1 in state/fixtures.db)", "",
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
    for name in ("P1.1", "P1.2", "P1.3", "P1.4", "P1.5", "P1.6", "G1", "G4", "G5"):
        print(f"  {name:5} {verdict(results[name]):7}  {results[name]['summary'][:110]}")
    print(f"  guardrails exit {guard.code}, mutation exit {mutation.code}, register self-test exit "
          f"{register_test.code}, unit tests exit {units.returncode}, contracts exit {contracts.code}, "
          f"vendored exit {vendored.code}")
    return 1 if (failed or guard.code or mutation.code or register_test.code or units.returncode
                 or contracts.code or vendored.code) else 0


if __name__ == "__main__":
    sys.exit(main())
