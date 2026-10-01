---
description: "What you still owe, by person or for everyone; add 'history <ref>' to see how many times something moved"
argument-hint: "[person] | history <ref>"
---

# /owe - what Taylor owes

READ lane: no Doc is written and nothing is dispatched. Run the script that matches the
argument and report what it prints, nothing from memory.

| Taylor typed | Run |
| --- | --- |
| `/owe` | `python scripts/register.py owed` |
| `/owe casey` | `python scripts/register.py owed --person casey` (resolve a name first with `python scripts/register.py resolve-person "<name>"` if it is not a key) |
| `/owe history A-0012` | `python scripts/register.py history A-0012` |

Before answering, run `python scripts/docs_reconcile.py` so a Done a manager typed in a Doc is
counted. Then answer in three short parts, in this order: what Taylor owes, by person; anything
whose owner or date is unresolved; open Needs Your Input questions. For history, lead with the
number of moves, then the dates.

Argument: $ARGUMENTS
