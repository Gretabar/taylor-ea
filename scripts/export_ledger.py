"""A read-only snapshot of the register, as markdown. Truth is local; this is a view.

PORTED FROM PIPER's export_ledger.py. Two rules kept: it is a VIEW, never a source (nothing here
writes to the register, and the export carries a generated-at stamp so yesterday's file is not
mistaken for today's state); and NAMES MAKE IT A RECORD (every row names a manager, so the file
declares ea-class: records and may only land under state/records/).

Usage:
    python scripts/export_ledger.py                                   to stdout
    python scripts/export_ledger.py --out state/records/register-2026-10-01.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ea_db  # noqa: E402


def build(conn) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = ["<!-- ea-class: records -->", "", "# Register snapshot", "",
             f"Generated {stamp}. A VIEW: the register is state/ea.db and is the only thing to read from.", "",
             "## Open actions", "", "| ref | owner | due | counterpart | text |", "| --- | --- | --- | --- | --- |"]
    rows = conn.execute(
        "SELECT a.ref, o.key AS owner, a.due_date, a.due_unresolved, c.key AS counterpart, a.text FROM actions a"
        " LEFT JOIN people o ON o.id = a.owner_person_id LEFT JOIN people c ON c.id = a.counterpart_person_id"
        " WHERE a.status IN ('open','snoozed') ORDER BY a.ref").fetchall()
    for r in rows:
        lines.append(f"| {r['ref']} | {r['owner'] or 'UNRESOLVED'} | {r['due_date'] or 'UNRESOLVED'} | "
                     f"{r['counterpart'] or '-'} | {r['text'].replace('|', '/')} |")
    if not rows:
        lines.append("| - | - | - | - | nothing open |")
    lines += ["", "## Queued topics", ""]
    topics = conn.execute("SELECT t.ref, p.key, t.status, t.text FROM topics t JOIN people p ON p.id = t.person_id"
                          " WHERE t.status = 'queued' ORDER BY t.ref").fetchall()
    lines += [f"- {t['ref']} {t['key']}: {t['text']}" for t in topics] or ["- none"]
    lines += ["", "## Needs Your Input", ""]
    questions = conn.execute("SELECT ref, question FROM needs_input WHERE status = 'open' ORDER BY id").fetchall()
    lines += [f"- {q['ref']} {q['question']}" for q in questions] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out")
    args = parser.parse_args()
    ea_db.console_utf8()
    conn = ea_db.connect(read_only=True)
    try:
        text = build(conn)
    finally:
        conn.close()
    if not args.out:
        sys.stdout.write(text)
        return 0
    target = Path(args.out)
    if "state/records" not in target.as_posix():
        print("REFUSED: the snapshot names managers, so it belongs under state/records/.", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
