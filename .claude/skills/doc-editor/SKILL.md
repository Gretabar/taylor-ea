---
name: doc-editor
description: "PAGE's method for placing a register record in a running 1:1 Doc: read the structure, pick the section from the Doc's map, write the proposal with scripts/docs_propose.py, and hand WREN the path. Owner: PAGE."
---

# Doc editor

Owner: PAGE.

## Read before proposing

`python scripts/docs_read.py --doc <id>` prints the working tab, the meeting blocks (newest first),
each mapped section with its current lines, the action table's row count, and every section that
is UNMAPPED. An unmapped section is never written to: it means the Doc's labels and its map
disagree, and the fix is Taylor confirming the map (`scripts/link_docs.py --detect`), not a guess.

## Which section

| Record | Section | Written as |
| --- | --- | --- |
| Taylor's topic | `taylor_topics` | a new line under that label in the newest block |
| the manager's topic | `their_topics` | a new line under the manager's label |
| a new action | `open_actions` | a new row: Assignee, Title with its [A-0000] ref, a date chip or TBD, blank Status |
| a completion | the action's own row | the Status cell set to "Done <date>" |
| a new date | the action's own row | the Date cell's chip replaced |

Which label is `taylor_topics` and which is `their_topics` comes from the Doc's own map, confirmed
with Taylor per Doc (`docs.section_map_json`). Do not assume "Top Focuses" means Taylor's topics in
a live Doc until its map says so.

## Proposing

`python scripts/docs_propose.py <add-topic|add-action|mark-done|update-due> --ref <ref> [--doc <id>]`

The proposal's words come from the register, and the script refuses text that breaks a content
rule. Never open or edit the proposal file: its sha256 is recorded, and WREN refuses a changed byte.

Then read the `privacy_review:` line the script prints:

- `not_required`: hand WREN the proposal path and Doc id.
- `required (<category>: ...)`: the words carry personal context (health, family, leave,
  discipline, a complaint, legal matters, one person's pay). Hand the path to the orchestrator for
  SAGE, not to WREN; WREN's script refuses it until SAGE approves those exact bytes.

If a line feels personal and the screen did not flag it, say so to the orchestrator rather than
waving it through; the screen reads words, not meaning.

## What never happens

No line is deleted or moved. No historic meeting block is edited. Nothing is written outside the
newest meeting block, except a completion or a date change on the action's own row. The Template
tab is never touched.
