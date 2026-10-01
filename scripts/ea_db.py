"""The one SQLite database this system keeps, and the only module that defines its shape.

PORTED FROM PIPER's piper_db.py: connect(read_only), migrate() under user_version,
WAL, and the people-column allowlist the doctor enforces are all kept. The schema
itself is new.

WHY SQLITE (and why this is deviation D-1 in docs/DEVIATIONS.md). Blueprint s.3
says to reuse an existing GRETA data store first, with Google Sheets as the
fallback. The proposal is a local database instead: it is on Taylor's machine with
no dependency on Mike's Supabase, it is transactional, it carries a real change
history table, and the running Docs stay the human-visible view the blueprint
requires. Taylor approves D-1 in writing before the first write to a live Doc;
until then scripts/docs_edit.py refuses every non-fixture Doc.

ONE ROW PER COMMITMENT, EVER. A changed deadline, owner or status is an UPDATE plus
an action_events row, never a second action. "How many times did this move" is a
COUNT over action_events where field = 'due_date'.

STABLE HUMAN IDS. A-0007 (action), T-0012 (topic), Q-0003 (Needs Your Input) come
from the counters table and are never reused, so a ref Taylor saw last month still
means the same thing.

TWO DATABASES, ON PURPOSE. state/ea.db is the register. state/fixtures.db is the
fixture world the acceptance harness writes. EA_FIXTURE_MODE=1 selects the fixture
database, so a test action can never land in Taylor's real register, and the fixture
Docs are only ever registered there.

WHY THE PEOPLE COLUMN ALLOWLIST IS ENFORCED IN CODE. `people` is where scope creep
becomes a privacy problem. Work identity only: no personal phone, address or notes.
ea_doctor.py asserts the live table against PEOPLE_ALLOWED_COLUMNS.

Usage:
    python scripts/ea_db.py --init          create or migrate, then report
    python scripts/ea_db.py --status        report without migrating
    python scripts/ea_db.py --path          print the resolved database path
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
LIVE_DB = REPO_ROOT / "state" / "ea.db"
FIXTURE_DB = REPO_ROOT / "state" / "fixtures.db"


def fixture_mode() -> bool:
    return os.environ.get("EA_FIXTURE_MODE") == "1"


def _resolve_db() -> Path:
    if os.environ.get("EA_DB"):
        return Path(os.environ["EA_DB"])
    return FIXTURE_DB if fixture_mode() else LIVE_DB


DB_PATH = _resolve_db()

SCHEMA_VERSION = 1

PEOPLE_ALLOWED_COLUMNS = {
    "id", "key", "full_name", "work_email", "role", "aliases_json",
    "cadence", "one_on_one", "active", "updated_at",
}

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        -- Stable human IDs. One row per prefix; the value only ever grows.
        CREATE TABLE IF NOT EXISTS counters (
            name  TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );

        -- Work identity only. See PEOPLE_ALLOWED_COLUMNS. aliases_json holds
        -- transcription variants (G5): a lookup, never a new row.
        CREATE TABLE IF NOT EXISTS people (
            id           INTEGER PRIMARY KEY,
            key          TEXT NOT NULL UNIQUE,
            full_name    TEXT NOT NULL,
            work_email   TEXT,
            role         TEXT,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            cadence      TEXT,
            one_on_one   INTEGER NOT NULL DEFAULT 0,
            active       INTEGER NOT NULL DEFAULT 1,
            updated_at   TEXT NOT NULL
        );

        -- Cadence is DATA observed from Calendar gaps (P1.6), never assumed.
        CREATE TABLE IF NOT EXISTS meetings (
            id               INTEGER PRIMARY KEY,
            person_id        INTEGER NOT NULL REFERENCES people(id),
            kind             TEXT NOT NULL DEFAULT '1on1',
            calendar_id      TEXT,
            series_event_id  TEXT,
            next_event_id    TEXT,
            next_at          TEXT,
            last_at          TEXT,
            cadence_observed TEXT,
            timezone         TEXT,
            refreshed_at     TEXT,
            source           TEXT NOT NULL,
            fixture          INTEGER NOT NULL DEFAULT 0,
            note             TEXT,
            UNIQUE (calendar_id, series_event_id)
        );

        -- The registered running Docs. This table IS the write allowlist:
        -- docs_edit.py refuses any doc_id not in it. section_map_json anchors on
        -- label text, never on heading levels; an unmapped section refuses.
        CREATE TABLE IF NOT EXISTS docs (
            id               INTEGER PRIMARY KEY,
            doc_id           TEXT NOT NULL UNIQUE,
            person_id        INTEGER REFERENCES people(id),
            meeting_id       INTEGER REFERENCES meetings(id),
            title            TEXT,
            url              TEXT,
            role             TEXT NOT NULL DEFAULT 'running_1on1',
            fixture          INTEGER NOT NULL DEFAULT 0,
            tab_id           TEXT,
            section_map_json TEXT,
            map_confirmed    INTEGER NOT NULL DEFAULT 0,
            last_revision_id TEXT,
            editable         INTEGER,
            verified_at      TEXT,
            created_at       TEXT NOT NULL
        );

        -- One row per commitment, ever. Changes are UPDATE plus an event row.
        CREATE TABLE IF NOT EXISTS actions (
            id                    INTEGER PRIMARY KEY,
            ref                   TEXT NOT NULL UNIQUE,
            text                  TEXT NOT NULL,
            owner_person_id       INTEGER REFERENCES people(id),
            owner_unresolved      INTEGER NOT NULL DEFAULT 0,
            owner_note            TEXT,
            due_date              TEXT,
            due_unresolved        INTEGER NOT NULL DEFAULT 0,
            due_note              TEXT,
            status                TEXT NOT NULL DEFAULT 'open',
            snoozed_until         TEXT,
            counterpart_person_id INTEGER REFERENCES people(id),
            origin_kind           TEXT NOT NULL,
            origin_ref            TEXT,
            origin_at             TEXT NOT NULL,
            meeting_id            INTEGER REFERENCES meetings(id),
            project_ref           TEXT,
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL,
            completed_at          TEXT,
            completed_via         TEXT
        );

        CREATE TABLE IF NOT EXISTS action_events (
            id        INTEGER PRIMARY KEY,
            action_id INTEGER NOT NULL REFERENCES actions(id),
            ts        TEXT NOT NULL,
            actor     TEXT NOT NULL,
            field     TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            source    TEXT,
            note      TEXT
        );
        CREATE INDEX IF NOT EXISTS action_events_action ON action_events (action_id, field);

        -- A discussion topic is never an action: no owner, no date (P1.1).
        CREATE TABLE IF NOT EXISTS topics (
            id                 INTEGER PRIMARY KEY,
            ref                TEXT NOT NULL UNIQUE,
            person_id          INTEGER NOT NULL REFERENCES people(id),
            meeting_id         INTEGER REFERENCES meetings(id),
            text               TEXT NOT NULL,
            side               TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'queued',
            placed_doc_id      TEXT,
            placed_revision_id TEXT,
            last_error         TEXT,
            origin_kind        TEXT NOT NULL,
            origin_ref         TEXT,
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        );

        -- Needs Your Input. Linked to the record it is about, never a competing
        -- obligation of its own.
        CREATE TABLE IF NOT EXISTS needs_input (
            id          INTEGER PRIMARY KEY,
            ref         TEXT NOT NULL UNIQUE,
            question    TEXT NOT NULL,
            context     TEXT,
            source_kind TEXT,
            source_ref  TEXT,
            action_id   INTEGER REFERENCES actions(id),
            topic_id    INTEGER REFERENCES topics(id),
            asked_at    TEXT NOT NULL,
            resolved_at TEXT,
            resolution  TEXT,
            status      TEXT NOT NULL DEFAULT 'open'
        );

        -- The register-to-Doc map and the dedupe key for placements.
        CREATE TABLE IF NOT EXISTS doc_items (
            id                    INTEGER PRIMARY KEY,
            doc_id                TEXT NOT NULL,
            item_kind             TEXT NOT NULL,
            item_ref              TEXT NOT NULL,
            section               TEXT,
            named_range           TEXT,
            text_hash             TEXT,
            inserted_revision_id  TEXT,
            last_seen_revision_id TEXT,
            last_seen_state       TEXT NOT NULL DEFAULT 'open',
            last_seen_text        TEXT,
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL,
            UNIQUE (doc_id, item_kind, item_ref)
        );

        CREATE TABLE IF NOT EXISTS doc_snapshots (
            id          INTEGER PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            parsed_json TEXT NOT NULL,
            sha256      TEXT NOT NULL,
            taken_at    TEXT NOT NULL,
            UNIQUE (doc_id, revision_id)
        );

        -- The replay guard: one completion per (doc, revision, action, direction).
        CREATE TABLE IF NOT EXISTS reconcile_events (
            id          INTEGER PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            action_ref  TEXT NOT NULL,
            direction   TEXT NOT NULL,
            outcome     TEXT NOT NULL,
            ts          TEXT NOT NULL,
            UNIQUE (doc_id, revision_id, action_ref, direction)
        );

        -- The /add replay guard: sha256(person, normalised text, instruction date).
        CREATE TABLE IF NOT EXISTS captures (
            id              INTEGER PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            kind            TEXT NOT NULL,
            item_ref        TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );

        -- PAGE's proposal index. WREN delivers PAGE's exact bytes: docs_edit.py
        -- recomputes the sha256 of the file it is handed and refuses unless it
        -- matches the row written when the proposal was made.
        CREATE TABLE IF NOT EXISTS proposals (
            id                 INTEGER PRIMARY KEY,
            path               TEXT NOT NULL UNIQUE,
            sha256             TEXT NOT NULL,
            kind               TEXT NOT NULL,
            doc_id             TEXT NOT NULL,
            item_ref           TEXT NOT NULL,
            created_by         TEXT,
            created_at         TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'pending',
            applied_at         TEXT,
            result_revision_id TEXT,
            error              TEXT
        );

        -- PIPER verbatim from here down.
        CREATE TABLE IF NOT EXISTS approvals (
            id             INTEGER PRIMARY KEY,
            kind           TEXT NOT NULL,
            target         TEXT NOT NULL,
            record_count   INTEGER NOT NULL DEFAULT 0,
            payload_sha256 TEXT NOT NULL,
            summary        TEXT NOT NULL,
            requested_by   TEXT,
            state          TEXT NOT NULL DEFAULT 'pending',
            created_at     TEXT NOT NULL,
            expires_at     TEXT NOT NULL,
            approved_at    TEXT,
            approved_by    TEXT,
            consumed_at    TEXT,
            revoked_at     TEXT,
            revoke_reason  TEXT
        );
        CREATE INDEX IF NOT EXISTS approvals_lookup ON approvals (payload_sha256, state);

        CREATE TABLE IF NOT EXISTS audit (
            id             INTEGER PRIMARY KEY,
            ts             TEXT NOT NULL,
            session_id     TEXT,
            agent          TEXT,
            hook           TEXT,
            tool           TEXT,
            decision       TEXT NOT NULL,
            rule_id        TEXT,
            target         TEXT,
            payload_sha256 TEXT,
            record_count   INTEGER,
            approval_id    INTEGER,
            detail         TEXT
        );
        CREATE INDEX IF NOT EXISTS audit_ts ON audit (ts);

        CREATE TABLE IF NOT EXISTS job_ticks (
            id     INTEGER PRIMARY KEY,
            job    TEXT NOT NULL,
            ts     TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT,
            host   TEXT,
            pid    INTEGER
        );
        CREATE INDEX IF NOT EXISTS job_ticks_job_ts ON job_ticks (job, ts);
        """,
    ),
]

TABLES = (
    "counters", "people", "meetings", "docs", "actions", "action_events", "topics",
    "needs_input", "doc_items", "doc_snapshots", "reconcile_events", "captures",
    "proposals", "approvals", "audit", "job_ticks",
)


def now_iso() -> str:
    """UTC, second precision, with the offset. Every timestamp in this DB is this."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """Open the database with the pragmas this system depends on."""
    target = Path(path or DB_PATH)
    if read_only:
        uri = f"file:{target.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target), timeout=30.0)
    conn.row_factory = sqlite3.Row
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply every migration newer than user_version, each in one transaction."""
    applied: list[int] = []
    current = user_version(conn)
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version={version}")
        applied.append(version)
    return applied


def people_column_violations(conn: sqlite3.Connection) -> list[str]:
    """Columns on `people` nobody signed off. Empty list means clean."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)").fetchall()}
    return sorted(columns - PEOPLE_ALLOWED_COLUMNS)


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in TABLES:
        try:
            counts[name] = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        except sqlite3.Error:
            counts[name] = -1  # read by ea_doctor as "table absent"
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="The register database: create, migrate, report.")
    parser.add_argument("--init", action="store_true", help="create or migrate the database")
    parser.add_argument("--status", action="store_true", help="report without migrating")
    parser.add_argument("--path", action="store_true", help="print the resolved database path")
    args = parser.parse_args()

    if args.path:
        print(DB_PATH)
        return 0
    if not (args.init or args.status):
        parser.print_help()
        return 2

    if args.status and not DB_PATH.exists():
        print(f"{DB_PATH} does not exist yet. Run: python scripts/ea_db.py --init")
        return 1

    existed = DB_PATH.exists()
    conn = connect()
    try:
        if args.init:
            applied = migrate(conn)
            print(f"{'migrated' if existed else 'created'}: {DB_PATH}")
            print(f"  schema version {user_version(conn)}"
                  + (f" (applied {applied})" if applied else " (already current)"))
        else:
            print(f"{DB_PATH}  schema version {user_version(conn)}"
                  + ("  [FIXTURE DATABASE]" if DB_PATH == FIXTURE_DB else ""))

        violations = people_column_violations(conn)
        if violations:
            print("\nFAIL: `people` carries columns nobody signed off:")
            for column in violations:
                print(f"  {column}")
            return 1

        print("\ntable counts:")
        for name, count in table_counts(conn).items():
            print(f"  {name:18} {'absent' if count < 0 else count}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
