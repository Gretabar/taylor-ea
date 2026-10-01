---
name: delivery-gate
description: "WREN's rules for writing to a running Doc: run scripts/docs_edit.py with PAGE's proposal, read the RESULT, and report success only when the read-back proved it. Owner: WREN."
---

# Delivery gate

Owner: WREN.

## The command

`python scripts/docs_edit.py <kind> --doc <id> --proposal <path>`

## What it guarantees, in order

1. Refuses (exit 2) before touching anything: an unregistered Doc; a live Doc while
   `EA_FIXTURE_MODE=1`; a live Doc before Taylor approves deviation D-1; a section map he has not
   confirmed; a proposal that is not PAGE's exact bytes; a proposal the privacy screen flagged that
   SAGE has not approved, or is holding; no revisionId (no edit rights).
2. Reads the Doc fresh and writes under `writeControl.requiredRevisionId`.
3. A manager editing at the same moment makes Google refuse; it retries once from a fresh read,
   then exits 3.
4. A new action row is inserted and filled in two verified phases; if the fill fails, the empty
   row is removed again (or named, exit 4, if it cannot be).
5. Reads the Doc back and requires the exact words in the right place, with the named range
   `ea:<kind>:<ref>` on them, before recording anything as done.
6. Writes one audit row, success or failure.

## Reporting

| Exit | Say |
| --- | --- |
| 0 UPDATED | done, where, which ref |
| 0 NO CHANGE | the Doc already said it |
| 2 | not updated, the reason, what would allow it |
| 3 | not updated, the reason |
| 4 | not verified: treat as not done, name the Doc, tell Mike |
| 9 | not updated, it crashed, tell Mike |

Never "updated" without exit 0 and UPDATED. Never retry around a refusal. A proposal that failed
for a temporary reason (a stale revision, a token, a 5xx) can be delivered again later with the
same command; one that was refused needs its cause fixed first.
