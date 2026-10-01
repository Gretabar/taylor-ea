---
description: "Do the thing you just recommended, without asking again"
---

# /boi

Ported from PIPER. `/boi` means: stop hedging and execute the most recent recommendation made in
this conversation.

1. Find the last recommendation: the specific action proposed in the most recent turn or turns.
   If several options were offered without a pick, choose the one that best fits how this system
   works (one clear next step, nothing outside Phase 1) and say which.
2. Do it now, through the normal lanes: a capture still goes REED, PAGE, WREN.
3. If there is no clear last recommendation, say so in one sentence and ask. Never invent one.

## What /boi never overrides

`/boi` overrides hesitation about a recommendation. It overrides nothing else:

- a hook that refused (delivery agent, architecture, cloud path, data class, approval);
- an unapproved deviation (D-1 gates every write to a live Doc);
- an unresolved owner or date: `/boi` does not license a guess;
- the rule that nothing is reported as done unless WREN's RESULT said UPDATED.

If the last recommendation was blocked by one of these, say which and what would clear it, in one
sentence.
