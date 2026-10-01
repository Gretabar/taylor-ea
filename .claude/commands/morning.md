---
description: "The morning screen in chat: is the system running, what is due or overdue, what needs your answer, and what was written to your Docs yesterday"
---

# /morning

READ lane, chat only: nothing is sent, no Doc is written, nothing is dispatched. The reconcile
below updates the register from the Docs exactly as the scheduled tick does. Invoke the
**morning-brief** skill.

1. `python scripts/docs_reconcile.py` (pull in any Done a manager typed overnight)
2. `python scripts/register.py morning`

Report it in the order the script prints it. The first line is whether the background tick is
alive, because an empty list looks identical whether nothing is due or nothing has run for six
days. A red LAST TICK, or an AUDIT DEGRADED banner, goes first and gets its own lines: "tell Mike".

If a script fails, say which one and stop reporting that part; never present a partial screen as a
complete one. Close with the single most useful next action, in one sentence.

Phase 3 turns this into the 7am email. Until then it is a chat screen only.
