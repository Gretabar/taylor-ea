"""PAGE's half of a Doc write: decide exactly what goes where, and write it down as a proposal.

NEW in this repo. WREN delivers PAGE's exact bytes and nothing else. So the
proposal is a file under state/proposals/ AND a row in the `proposals` index
holding the file's sha256 (approvals.canonical, the one canonical encoding in this
repo). scripts/docs_edit.py recomputes the hash of the file it is handed and
refuses on any difference: an agent cannot "improve" the wording between proposal
and delivery.

THE TEXT COMES FROM THE REGISTER, not from free-hand prose. A topic's line is the
topic's text; an action's row is owner, text plus its ref, due date, empty status.
Doc-bound text is checked here against the content rules (no em dash, no emoji),
because it never passes through a Write hook: the API is the only path it takes.

THE PROPOSAL RECORDS INTENT, NOT POSITIONS. Indices go stale the moment a manager
types. docs_edit.py recomputes every index from a fresh read; the proposal carries
the section, the exact text, and the revision it was based on, for the audit trail.

This script only READS a Doc. It is deliberately a separate file from
docs_edit.py so the WREN-only gate (require-delivery-agent.py) stays a simple
whole-file rule: PAGE runs this, WREN runs that.

Usage:
    python scripts/docs_propose.py add-topic  --ref T-0001 [--doc <id>] [--section taylor_topics]
    python scripts/docs_propose.py add-action --ref A-0001 [--doc <id>]
    python scripts/docs_propose.py mark-done  --ref A-0001 [--doc <id>]
    python scripts/docs_propose.py update-due --ref A-0001 [--doc <id>]

Exit 0 proposal written; 1 refused (with the reason); 3 the Doc could not be read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approvals  # noqa: E402
import docs_read  # noqa: E402
import ea_db  # noqa: E402
import register  # noqa: E402
import validate_content_rules  # noqa: E402

PROPOSALS = ea_db.REPO_ROOT / "state" / "proposals"
KINDS = ("add-topic", "add-action", "mark-done", "update-due")


class ProposalRefused(Exception):
    """Nothing was proposed, for the reason given."""


def proposal_sha(proposal: dict) -> str:
    return hashlib.sha256(approvals.canonical("docs_edit", proposal)).hexdigest()


def _doc_for(conn, person_id: int | None, doc_id: str | None):
    if doc_id:
        row = conn.execute("SELECT * FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
        if row is None:
            raise ProposalRefused(f"Doc {doc_id} is not registered (python scripts/link_docs.py --status)")
        return row
    rows = conn.execute("SELECT * FROM docs WHERE person_id = ? AND role = 'running_1on1'", (person_id,)).fetchall()
    if not rows:
        raise ProposalRefused("this person has no registered running 1:1 Doc yet; link it first")
    if len(rows) > 1:
        raise ProposalRefused("this person has more than one running Doc registered; pass --doc")
    return rows[0]


def _first_name(conn, person_id: int | None) -> str:
    if person_id is None:
        return ""
    row = conn.execute("SELECT full_name, key FROM people WHERE id = ?", (person_id,)).fetchone()
    return (row["full_name"] or row["key"]).split()[0] if row else ""


def _check_text(*texts: str) -> None:
    for text in texts:
        findings = validate_content_rules.check_doc_bound(text or "")
        if findings:
            raise ProposalRefused("Doc-bound text breaks a content rule (" + ", ".join(f.rule for f in findings)
                                  + "). Rewrite the register text without it: register.py update-action "
                                    "<ref> --field text, or a new topic.")


def build(conn, kind: str, ref: str, *, doc_id: str | None, section: str | None, document: dict | None = None) -> dict:
    """The proposal dict for one write. Reads the Doc unless `document` is supplied (tests)."""
    if kind not in KINDS:
        raise ProposalRefused(f"kind must be one of {', '.join(KINDS)}")
    ref = ref.strip().upper()
    today = register.today_local().isoformat()

    if kind == "add-topic":
        topic = conn.execute("SELECT * FROM topics WHERE ref = ?", (ref,)).fetchone()
        if topic is None:
            raise ProposalRefused(f"no topic {ref}")
        if topic["status"] != "queued":
            raise ProposalRefused(f"{ref} is {topic['status']}, not queued; it has already been placed or dropped")
        doc = _doc_for(conn, topic["person_id"], doc_id)
        section = section or ("taylor_topics" if topic["side"] == "taylor" else "their_topics")
        item_kind, text, cells, status_text, due = "topic", topic["text"].strip(), None, None, None
    else:
        action = conn.execute("SELECT * FROM actions WHERE ref = ?", (ref,)).fetchone()
        if action is None:
            raise ProposalRefused(f"no action {ref}")
        doc = _doc_for(conn, action["counterpart_person_id"] or action["owner_person_id"], doc_id)
        section = section or "open_actions"
        item_kind, text, cells, status_text, due = "action", None, None, None, None

    smap = json.loads(doc["section_map_json"] or "{}")
    spec = (smap.get("sections") or {}).get(section)
    if spec is None:
        raise ProposalRefused(f"section {section!r} is not in this Doc's map; nothing to place it in")
    if document is None:
        try:
            document = docs_read.fetch(docs_read.docs_service(), doc["doc_id"])
        except docs_read.DocReadError as exc:
            raise ProposalRefused(f"could not read the Doc: {exc}") from exc
    parsed = docs_read.parse(document, smap)
    if section in parsed["unmapped"]:
        raise ProposalRefused(f"the Doc has no {spec.get('anchor')!r} in its newest block; refusing to guess "
                              f"where {section} goes")

    if kind in ("add-action", "mark-done", "update-due"):
        action = conn.execute("SELECT * FROM actions WHERE ref = ?", (ref,)).fetchone()
        owner = _first_name(conn, action["owner_person_id"]) or "TBD"
        title = action["text"].strip() + (f" [{ref}]" if smap.get("ref_tokens", True) else "")
        due = action["due_date"]
        placed = conn.execute("SELECT * FROM doc_items WHERE doc_id = ? AND item_kind = 'action' AND item_ref = ?",
                              (doc["doc_id"], ref)).fetchone()
        if kind == "add-action":
            if placed is not None and placed["last_seen_state"] != "missing":
                raise ProposalRefused(f"{ref} is already in this Doc ({placed['last_seen_state']})")
            if spec.get("kind") == "table":
                cells = {"assignee": owner, "title": title, "date": due, "date_text": "TBD", "status": ""}
            else:
                text = f"{title} (due {due or 'TBD'})"
        else:
            if placed is None:
                raise ProposalRefused(f"{ref} was never placed in this Doc; propose add-action first")
            if kind == "mark-done":
                if action["status"] != "done":
                    raise ProposalRefused(f"{ref} is {action['status']} in the register; complete it there first "
                                          f"(register.py complete {ref} --via chat)")
                status_text = f"Done {today}"
            elif not due:
                raise ProposalRefused(f"{ref} has no due date in the register to write")
        _check_text(owner, title, text or "", status_text or "")
    else:
        _check_text(text)

    return {
        "ea-class": "records",
        "version": 1,
        "kind": kind,
        "doc_id": doc["doc_id"],
        "doc_title": doc["title"],
        "section": section,
        "section_kind": spec.get("kind") or "list",
        "item_kind": item_kind,
        "item_ref": ref,
        "named_range": f"ea:{item_kind}:{ref}",
        "text": text,
        "cells": cells,
        "status_text": status_text,
        "date": due,
        "basis_revision_id": parsed["revision_id"],
        "created_at": ea_db.now_iso(),
        "created_by": "PAGE",
    }


def write(conn, proposal: dict) -> tuple[Path, str]:
    """Write the file and its index row. Supersedes an earlier pending proposal for the same write."""
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    stamp = proposal["created_at"][:19].replace(":", "").replace("-", "")
    path = PROPOSALS / f"{stamp}-{proposal['kind']}-{proposal['item_ref']}-{proposal['doc_id'][:8]}.json"
    body = json.dumps(proposal, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(body.encode("utf-8"))
    digest = proposal_sha(json.loads(body))
    rel = path.relative_to(ea_db.REPO_ROOT).as_posix()
    with conn:
        conn.execute("UPDATE proposals SET status='superseded' WHERE doc_id=? AND item_ref=? AND kind=?"
                     " AND status IN ('pending','failed')",
                     (proposal["doc_id"], proposal["item_ref"], proposal["kind"]))
        conn.execute("INSERT INTO proposals (path, sha256, kind, doc_id, item_ref, created_by, created_at, status)"
                     " VALUES (?,?,?,?,?,?,?,'pending')",
                     (rel, digest, proposal["kind"], proposal["doc_id"], proposal["item_ref"], "PAGE",
                      proposal["created_at"]))
    return path, digest


def preview(proposal: dict) -> str:
    where = f"{proposal['doc_title']} > {proposal['section']}"
    if proposal["cells"]:
        c = proposal["cells"]
        what = f"new row: {c['assignee']} | {c['title']} | {c['date'] or c['date_text']} | {c['status'] or '(blank)'}"
    elif proposal["status_text"]:
        what = f"Status cell -> {proposal['status_text']!r}"
    elif proposal["kind"] == "update-due":
        what = f"Date cell -> {proposal['date']}"
    else:
        what = f"new line: {proposal['text']!r}"
    return f"{proposal['kind']} {proposal['item_ref']} into {where}\n  {what}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--doc")
    parser.add_argument("--section")
    args = parser.parse_args()
    ea_db.console_utf8()
    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        proposal = build(conn, args.kind, args.ref, doc_id=args.doc, section=args.section)
        path, digest = write(conn, proposal)
    except ProposalRefused as exc:
        print(f"NOT PROPOSED: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(preview(proposal))
    print(f"proposal: {path.relative_to(ea_db.REPO_ROOT).as_posix()}")
    print(f"sha256:   {digest}")
    print(f"WREN applies it with: python scripts/docs_edit.py {args.kind} --doc {proposal['doc_id']} "
          f"--proposal {path.relative_to(ea_db.REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
