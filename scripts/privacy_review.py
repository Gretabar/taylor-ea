"""SAGE's verdict on a flagged proposal: approve it for the Doc, or hold it back.

NEW in this repo. Blueprint s.2: raw and personal context stays private; sensitive
context reaches a manager-readable Doc only when it is genuinely work relevant and
right for that audience. scripts/privacy_screen.py decides which proposals SAGE must
see; this script records what SAGE decided, and scripts/docs_edit.py obeys it.

THE VERDICT IS BOUND TO THE BYTES. The stamp carries the proposal's sha256 (the same
canonical hash WREN's delivery checks), so approving one wording does not approve a
reworded one, and a proposal edited after the stamp is refused for both reasons. The
newest stamp for a sha256 is the one that counts; a hold followed by an approval
(Taylor explained why the line belongs in the Doc) is a decision with a history. The
script prints the exact words the verdict covers, and docs_edit.py reads the newest
verdict again immediately before it writes, so a hold recorded while WREN is mid-write
still stops the words reaching the Doc.

ONLY SAGE RUNS THIS. .claude/hooks/require-privacy-agent.py refuses it from every
other caller, the orchestrator included, using Claude Code's own agent fields. So the
reviewer recorded here is SAGE by construction; the script cannot see its caller and
does not pretend to.

IT REFUSES TO STAMP WHAT THE SCREEN DID NOT FLAG. SAGE reviews flagged proposals
only; a stamp on anything else would be noise in the record of decisions.

THE REASON IS FOR TAYLOR. On a hold the orchestrator tells him why in one line, so
the reason must be one plain sentence, and the content rules apply (no em dash, no
emoji).

Usage (SAGE only):
    python scripts/privacy_review.py --approve state/proposals/<file>.json --reason "..."
    python scripts/privacy_review.py --hold    state/proposals/<file>.json --reason "..."

Exit 0 recorded; 1 refused, with the reason; 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / ".claude" / "hooks"))

import approvals  # noqa: E402
import ea_db  # noqa: E402
import privacy_screen  # noqa: E402
import validate_content_rules  # noqa: E402

import _audit  # noqa: E402

REVIEWER = "SAGE"
VERDICTS = ("approve", "hold")


class ReviewRefused(Exception):
    """Nothing was recorded, for the reason given."""


def load_flagged(conn, path: Path) -> tuple[dict, str, str]:
    """(proposal, sha256, repo-relative path) for a pending proposal the screen flagged."""
    try:
        proposal = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewRefused(f"the proposal {path} cannot be read: {exc}") from exc
    if not isinstance(proposal, dict):
        raise ReviewRefused(f"{path} is not a proposal")
    try:
        rel = path.resolve().relative_to(ea_db.REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ReviewRefused(f"the proposal {path} is outside the repo") from exc
    index = conn.execute("SELECT * FROM proposals WHERE path = ?", (rel,)).fetchone()
    if index is None:
        raise ReviewRefused(f"{rel} is not in the proposal index; only a proposal PAGE wrote can be reviewed")
    digest = hashlib.sha256(approvals.canonical("docs_edit", proposal)).hexdigest()
    if digest != index["sha256"]:
        raise ReviewRefused(f"{rel} has changed since PAGE wrote it; ask PAGE for a new proposal")
    if index["status"] not in ("pending", "failed"):
        raise ReviewRefused(f"{rel} is {index['status']}; only a proposal still waiting for WREN is reviewed")
    required, _ = privacy_screen.review_required(proposal)
    if not required:
        raise ReviewRefused(f"{rel} is not flagged by the privacy screen; SAGE reviews flagged proposals only")
    return proposal, digest, rel


def record(conn, proposal: dict, digest: str, rel: str, verdict: str, reason: str) -> dict:
    """Write one stamp. Returns what was recorded."""
    if verdict not in VERDICTS:
        raise ReviewRefused(f"the verdict must be one of {', '.join(VERDICTS)}")
    reason = " ".join((reason or "").split())
    if not reason:
        raise ReviewRefused("a verdict needs a reason Taylor can read in one sentence")
    findings = validate_content_rules.check_doc_bound(reason)
    if findings:
        raise ReviewRefused("the reason breaks a content rule (" + ", ".join(f.rule for f in findings)
                            + "); rewrite it as one plain sentence")
    _, category = privacy_screen.review_required(proposal)
    now = ea_db.now_iso()
    with conn:
        conn.execute("INSERT INTO privacy_reviews (proposal_path, proposal_sha256, item_ref, verdict, category,"
                     " reason, reviewer, ts) VALUES (?,?,?,?,?,?,?,?)",
                     (rel, digest, proposal.get("item_ref"), verdict, category, reason, REVIEWER, now))
    _audit.record(hook="privacy_review", tool="privacy_review", agent=REVIEWER, decision=verdict,
                  rule_id=category, target=rel, payload_sha256=digest, detail=reason[:300])
    return {"verdict": verdict, "category": category, "reason": reason, "proposal": rel,
            "item_ref": proposal.get("item_ref"), "kind": proposal.get("kind"), "doc_id": proposal.get("doc_id"),
            "sha256": digest, "words": privacy_screen.doc_bound_texts(proposal)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--approve", metavar="PROPOSAL")
    choice.add_argument("--hold", metavar="PROPOSAL")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    ea_db.console_utf8()
    verdict, target = ("approve", args.approve) if args.approve else ("hold", args.hold)
    path = Path(target)
    if not path.is_absolute():
        path = ea_db.REPO_ROOT / path
    conn = ea_db.connect()
    ea_db.migrate(conn)
    try:
        proposal, digest, rel = load_flagged(conn, path)
        result = record(conn, proposal, digest, rel, verdict, args.reason)
    except ReviewRefused as exc:
        print(f"NOT RECORDED: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"REVIEWED: {result['verdict']} {result['item_ref']} ({result['category']}): {result['reason']}")
    # The verdict is bound to these bytes, not to the item: show exactly what it covers.
    print(f"This verdict covers exactly these words (sha256 {result['sha256'][:16]}); "
          f"any other wording needs a new review:")
    for words in result["words"]:
        print(f"  {words}")
    if verdict == "approve":
        print(f"WREN may deliver it: python scripts/docs_edit.py {result['kind']} --doc {result['doc_id']} "
              f"--proposal {result['proposal']}")
    else:
        print("Nothing goes to the Doc. Tell Taylor why in one line, and offer to keep it in his private "
              f"notes instead (REED: python scripts/register.py keep-private {result['item_ref']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
