---
description: "Capture a topic, a commitment or a completion the moment you think of it: recorded in the register and written into the right running 1:1 Doc"
argument-hint: <what you want captured, in your own words>
---

# /add - capture

The CAPTURE lane, end to end. Read `CLAUDE.md` first.

1. **REED**: run `python scripts/docs_reconcile.py` for the affected Docs, so a Done a manager
   typed is already known. Then classify each clause of Taylor's words as a topic, a commitment, a
   completion, or unresolved (the **capture-rules** skill), resolve each person and each date
   against today in Taylor's timezone, and record it with `scripts/register.py`. One targeted
   question only if something genuinely ambiguous matters now; otherwise unresolved fields stay
   unresolved and a Needs Your Input row is opened.
2. **PAGE**: one proposal per record that must reach a Doc, with `scripts/docs_propose.py`.
3. **SAGE**, only for a proposal PAGE's output marks `privacy_review: required`: approve or hold it
   with `scripts/privacy_review.py`. Skip this step for every other proposal.
4. **WREN**: deliver each proposal with `scripts/docs_edit.py`, which reads it back. A flagged
   proposal goes to WREN only after SAGE approved it.

Report one line per record: what, where, the ref, and WREN's RESULT. If a write did not land,
say "not updated" and why, and say that the register still holds it (a topic stays queued; a
proposal can be delivered again once the cause is fixed). If SAGE held it, tell Taylor why in one
line and offer to keep it in his private notes instead; on his yes, REED runs
`python scripts/register.py keep-private <ref>`. He can also reword it, or say why it belongs in
the Doc, and SAGE looks again.

The roll call at the bottom should read REED -> PAGE -> WREN, or REED -> PAGE -> SAGE -> WREN for a
flagged record. If a capture ends with "TEAM: NONE", nothing was dispatched, whatever the chat says.

Taylor's words:

$ARGUMENTS
