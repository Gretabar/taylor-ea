"""Approvals: a row bound to the bytes, approved once, spent once.

PORTED FROM PIPER. Cold in Phase 1: nothing Phase 1 does raises an approval, and
Taylor never sees one. canonical() is ALSO what scripts/docs_propose.py and
scripts/docs_edit.py hash a Doc edit proposal with, so WREN can prove it is
delivering PAGE's exact bytes. One canonical encoding, one place.

WHY HASH-BINDING RATHER THAN A NAMED PERMISSION. An approval that says "send the
reply" authorises a category, and a category can be re-drafted after it is
approved. The agent writes the exact payload, this module hashes it, Taylor
approves that hash, and the hook recomputes the hash from the tool input actually
being executed. If a single byte of the recipient list or the body changed
between approval and send, the hashes differ and the send is blocked. The
approval is about the bytes, which is the only thing anybody can actually check.

WHY SINGLE-USE. Without consumption an approved send can be replayed: the same
approved row authorises the same email again tomorrow. So consume()
marks the row spent inside the same transaction that selects it, under BEGIN
IMMEDIATE, and two concurrent hooks cannot both win.

WHY THE CLOCK RESTARTS AT APPROVAL. expires_at is set at creation so a pending
request does not sit in the queue forever, and it is RE-ANCHORED when Taylor
approves, because the window that carries risk is the gap between him looking at
the bytes and the bytes leaving. 24 hours by default.

WHY THE CANONICAL FORM LIVES HERE AND ONLY HERE. Two implementations of a
canonical JSON encoding is how one of them ends up sorting keys and the other
does not, and every approval then fails to match for a reason nobody can see.
The hook imports payload_hash from this file. It does not have its own.

Usage:
    python scripts/approvals.py create --kind send_email --target "1 recipient" \\
        --summary "<one line>" --tool Bash --input-file <file> --record-count 1
    python scripts/approvals.py list
    python scripts/approvals.py show --id 7
    python scripts/approvals.py approve --id 7 --by "Taylor Iwaasa"
    python scripts/approvals.py revoke --id 7 --reason "recipient list was wrong"
    python scripts/approvals.py verify --tool Bash --input-file <file>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ea_db  # noqa: E402

DEFAULT_TTL_HOURS = 24
TTL_HOURS_BY_KIND: dict[str, int] = {}

# The kinds later phases will raise. Not enforced: an unknown kind still works and
# gets the default expiry. A draft addressed ONLY to Taylor's own mailbox is exempt
# from the prompt by .claude/hooks/require-approval.py, so a draft_create row here
# means it reached somebody else too.
KNOWN_KINDS = (
    "send_email",
    "draft_create",
    "calendar_write",
)

STATES = ("pending", "approved", "consumed", "revoked", "expired")


class ApprovalError(RuntimeError):
    """The caller asked for something the ledger cannot do."""


def canonical(tool_name: str, tool_input: object) -> bytes:
    """The exact bytes an approval is bound to.

    sort_keys so key order in the payload cannot change the hash. separators
    without spaces so a pretty-printer cannot either. ensure_ascii=False so an
    accented name hashes as itself rather than as an escape sequence, and then
    encoded UTF-8 explicitly rather than relying on the locale codec, which is
    cp1252 on this machine.
    """
    document = {"tool": tool_name, "input": tool_input}
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def payload_hash(tool_name: str, tool_input: object) -> str:
    return hashlib.sha256(canonical(tool_name, tool_input)).hexdigest()


def ttl_hours(kind: str) -> int:
    return TTL_HOURS_BY_KIND.get(kind, DEFAULT_TTL_HOURS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None  # swallow: an unparseable stamp is treated as expired below
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def create(
    conn: sqlite3.Connection,
    *,
    kind: str,
    target: str,
    summary: str,
    tool_name: str,
    tool_input: object,
    record_count: int = 0,
    requested_by: str = "",
) -> tuple[int, str]:
    """Register a pending approval for one exact payload. Returns (id, sha256)."""
    if not kind or not target or not summary:
        raise ApprovalError("kind, target and summary are all required: Taylor has to be "
                            "able to read the row and know what he is approving")
    digest = payload_hash(tool_name, tool_input)
    now = _now()
    with conn:
        cursor = conn.execute(
            "INSERT INTO approvals (kind, target, record_count, payload_sha256, summary,"
            " requested_by, state, created_at, expires_at)"
            " VALUES (?,?,?,?,?,?, 'pending', ?, ?)",
            (kind, target, int(record_count), digest, summary, requested_by,
             _iso(now), _iso(now + timedelta(hours=ttl_hours(kind)))),
        )
    return int(cursor.lastrowid), digest


def approve(conn: sqlite3.Connection, approval_id: int, by: str) -> sqlite3.Row:
    """Approve a pending row and restart its clock. Raises if it is not approvable."""
    row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if row is None:
        raise ApprovalError(f"no approval with id {approval_id}")
    if row["state"] != "pending":
        raise ApprovalError(f"approval {approval_id} is {row['state']}, not pending")
    now = _now()
    with conn:
        conn.execute(
            "UPDATE approvals SET state='approved', approved_at=?, approved_by=?,"
            " expires_at=? WHERE id=?",
            (_iso(now), by, _iso(now + timedelta(hours=ttl_hours(row["kind"]))), approval_id),
        )
    return conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()


def revoke(conn: sqlite3.Connection, approval_id: int, reason: str) -> None:
    with conn:
        changed = conn.execute(
            "UPDATE approvals SET state='revoked', revoked_at=?, revoke_reason=?"
            " WHERE id=? AND state IN ('pending','approved')",
            (_iso(_now()), reason, approval_id),
        ).rowcount
    if not changed:
        raise ApprovalError(f"approval {approval_id} is not pending or approved")


def consume(conn: sqlite3.Connection, digest: str) -> tuple[sqlite3.Row | None, str]:
    """Spend the approval matching `digest`, atomically. Returns (row, reason).

    reason is "" on success, and otherwise names why nothing was spent, so the
    caller can say something more useful than "denied". The classification pass
    runs BEFORE the update and inside the same transaction, so the message
    describes the state the decision was actually made on.
    """
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        candidates = conn.execute(
            "SELECT * FROM approvals WHERE payload_sha256 = ? ORDER BY id", (digest,)
        ).fetchall()
        if not candidates:
            conn.rollback()
            return None, "no approval exists for these exact bytes"

        live = None
        reasons: list[str] = []
        for row in candidates:
            if row["state"] == "revoked":
                reasons.append(f"approval {row['id']} was revoked ({row['revoke_reason'] or 'no reason given'})")
                continue
            if row["state"] == "consumed" or row["consumed_at"]:
                reasons.append(f"approval {row['id']} was already spent at {row['consumed_at']}")
                continue
            if row["state"] == "pending":
                reasons.append(f"approval {row['id']} exists but Taylor has not approved it")
                continue
            expires = _parse(row["expires_at"])
            if expires is None or expires <= now:
                reasons.append(f"approval {row['id']} expired at {row['expires_at']}")
                continue
            live = row
            break

        if live is None:
            conn.rollback()
            return None, "; ".join(reasons) or "no usable approval"

        conn.execute(
            "UPDATE approvals SET state='consumed', consumed_at=? WHERE id=?",
            (_iso(now), live["id"]),
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return conn.execute("SELECT * FROM approvals WHERE id = ?", (live["id"],)).fetchone(), ""


def expire_stale(conn: sqlite3.Connection) -> int:
    """Mark past-expiry rows expired. Cosmetic: consume() checks the clock anyway."""
    with conn:
        return conn.execute(
            "UPDATE approvals SET state='expired'"
            " WHERE state IN ('pending','approved') AND expires_at <= ?",
            (_iso(_now()),),
        ).rowcount


def rows(conn: sqlite3.Connection, state: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
    if state:
        return conn.execute(
            "SELECT * FROM approvals WHERE state = ? ORDER BY id DESC LIMIT ?",
            (state, limit),
        ).fetchall()
    return conn.execute("SELECT * FROM approvals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def _tool_input(args: argparse.Namespace) -> object:
    if args.input_file:
        text = Path(args.input_file).read_bytes().decode("utf-8")
    elif args.input_json:
        text = args.input_json
    else:
        raise ApprovalError("pass --input-file or --input-json: an approval is bound "
                            "to bytes, so there have to be some")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApprovalError(f"the payload is not JSON: {exc}") from exc


def _print(row: sqlite3.Row) -> None:
    print(f"  #{row['id']:<4} {row['state']:<9} {row['kind']:<14} {row['summary']}")
    print(f"        target {row['target']}  records {row['record_count']}")
    print(f"        sha256 {row['payload_sha256']}")
    print(f"        created {row['created_at']}  expires {row['expires_at']}"
          + (f"  approved {row['approved_at']} by {row['approved_by']}" if row["approved_at"] else "")
          + (f"  consumed {row['consumed_at']}" if row["consumed_at"] else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("create", help="register a pending approval for exact bytes")
    make.add_argument("--kind", required=True, help=" | ".join(KNOWN_KINDS))
    make.add_argument("--target", required=True, help="who or what this reaches, in plain words")
    make.add_argument("--summary", required=True, help="what Taylor is approving, in one line")
    make.add_argument("--tool", required=True, help="the tool name the hook will see")
    make.add_argument("--input-file", help="JSON file holding the exact tool input")
    make.add_argument("--input-json", help="the exact tool input, inline")
    make.add_argument("--record-count", type=int, default=0)
    make.add_argument("--requested-by", default="")

    listing = sub.add_parser("list", help="show recent approvals")
    listing.add_argument("--state", choices=STATES)
    listing.add_argument("--limit", type=int, default=50)

    show = sub.add_parser("show", help="show one approval")
    show.add_argument("--id", type=int, required=True)

    ok = sub.add_parser("approve", help="approve a pending row")
    ok.add_argument("--id", type=int, required=True)
    ok.add_argument("--by", default="Taylor Iwaasa")

    kill = sub.add_parser("revoke", help="revoke a pending or approved row")
    kill.add_argument("--id", type=int, required=True)
    kill.add_argument("--reason", required=True)

    spend = sub.add_parser("consume", help="spend the approval matching these bytes")
    spend.add_argument("--tool", required=True)
    spend.add_argument("--input-file")
    spend.add_argument("--input-json")

    check = sub.add_parser("verify", help="report whether these bytes are approved, without spending")
    check.add_argument("--tool", required=True)
    check.add_argument("--input-file")
    check.add_argument("--input-json")

    args = parser.parse_args()
    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        if args.command == "create":
            approval_id, digest = create(
                conn, kind=args.kind, target=args.target, summary=args.summary,
                tool_name=args.tool, tool_input=_tool_input(args),
                record_count=args.record_count, requested_by=args.requested_by,
            )
            print(f"approval #{approval_id} pending")
            print(f"  sha256 {digest}")
            print(f"  expires in {ttl_hours(args.kind)}h unless approved sooner")
            print(f"\nTaylor approves it with:\n  python scripts/approvals.py approve --id {approval_id}")
            return 0

        if args.command == "list":
            expire_stale(conn)
            found = rows(conn, args.state, args.limit)
            if not found:
                print("no approvals" + (f" in state {args.state}" if args.state else ""))
                return 0
            for row in found:
                _print(row)
            return 0

        if args.command == "show":
            row = conn.execute("SELECT * FROM approvals WHERE id=?", (args.id,)).fetchone()
            if row is None:
                print(f"no approval with id {args.id}", file=sys.stderr)
                return 1
            _print(row)
            return 0

        if args.command == "approve":
            row = approve(conn, args.id, args.by)
            print(f"approval #{row['id']} approved by {row['approved_by']}")
            print(f"  it expires at {row['expires_at']} and can be spent once")
            return 0

        if args.command == "revoke":
            revoke(conn, args.id, args.reason)
            print(f"approval #{args.id} revoked")
            return 0

        digest = payload_hash(args.tool, _tool_input(args))
        if args.command == "verify":
            found = conn.execute(
                "SELECT * FROM approvals WHERE payload_sha256=? ORDER BY id", (digest,)
            ).fetchall()
            print(f"sha256 {digest}")
            if not found:
                print("  no approval exists for these exact bytes")
                return 1
            for row in found:
                _print(row)
            return 0

        row, reason = consume(conn, digest)
        if row is None:
            print(f"NOT APPROVED: {reason}", file=sys.stderr)
            return 1
        print(f"spent approval #{row['id']} ({row['summary']})")
        return 0
    except ApprovalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
