---
name: morning-brief
description: "The /morning screen: tick health first, then today's meetings, Taylor's actions due within 48 hours or overdue, Needs Your Input, Doc items that need a look, and yesterday's Doc writes. Owner: LARK. Ported from PIPER's morning-brief; chat only until Phase 3 makes it the 7am email."
---

# Morning brief

Owner: LARK, whose lane the daily brief is. `/morning` itself runs on the main thread with no
dispatch: a chat screen built from two scripts does not need an agent's time, and Taylor's seat has
a spend cap. Ported from PIPER's morning-brief: the tick-first order and the "an empty brief must
still appear" rule are kept.

## Run

1. `python scripts/docs_reconcile.py`
2. `python scripts/register.py morning`

Everything comes from those two. Never from memory, never from an earlier session.

## Shape

```
MORNING <date>
tick OK (2h ago)                      or a framed LAST TICK block, first, in full
Today                                 each 1:1 today, its time and its Doc link
Your actions due in 48h or overdue    Taylor's only (blueprint section 6: no employee action lists)
Needs Your Input                      every open question, oldest first
Doc items to look at                  missing, ambiguous or unreadable rows
Done in chat, not yet shown in the Doc
Doc writes yesterday                  from the audit table
```

An empty section says "nothing" in one line; it never disappears, because a missing section and an
empty one look the same otherwise. Close with one sentence: the single next action.

## Not this skill's job

It dispatches nothing and writes no Doc. A "Done in chat, not yet shown in the Doc" line is an
offer: if Taylor says yes, that is a capture (PAGE proposes mark-done, WREN delivers).
