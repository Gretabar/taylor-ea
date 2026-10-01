# Open questions

What the Phase 1 build could not settle from Mike's machine. Each one says what was observed, what
was assumed (if anything) and who answers it. Nothing here was filled in by guessing.

## 1. How a ticked checkbox reads through the API (the checkbox experiment)

**Done, as far as the API allows. Status-cell convention adopted.**

Observed on 2026-10-01 on the `[FIXTURE] Checkbox experiment` Doc, whose checklist was created
with the API's BULLET_CHECKBOX preset:

- A checklist item's bullet carries only a list id. The list's nesting level reports
  `glyphType: GLYPH_TYPE_UNSPECIFIED`, `glyphFormat: "%0"`, and no glyph symbol.
- There is no field anywhere for checked or unchecked, and no batchUpdate request that sets one, so
  the API cannot tick a box, and the unchecked state is indistinguishable from the checked state
  unless ticking changes something else (strikethrough is the common belief, unverified).

What it means: completion is read from the action table's Status cell, which the live Docs already
have. A manager types Done there; the next tick completes the action. Checklist lines still work
through a struck-through line or a "(done ...)" marker, and the acceptance harness exercised that
path by striking a line through the API.

Still open: what a HUMAN tick on a checkbox produces in the API. Mike can settle it in two minutes:
open the checkbox fixture Doc, tick "Checkbox seed item one", then run
`python scripts/docs_read.py --doc <checkbox fixture id> --checkbox-probe` with `EA_FIXTURE_MODE=1`
and see whether `struck` turns true. Only matters if a Doc uses checklists for actions.

## 2. Which label in each live Doc holds Taylor's topics, and which the manager's

Unknown until Taylor says. The one inspected Doc (Tania's) has "Top Focuses" and "<Name> Notes"
as plain labels and bold numbered agenda items. The fixtures map Taylor's topics to "Top Focuses"
and the manager's to "<Name> Notes"; that is a fixture convention, not a finding.
`link_docs.py --detect` proposes a map per Doc and marks these two as assumptions; writes to a live
Doc refuse until Taylor confirms the map (`link_docs.py --confirm`).

## 3. The five other running Docs

Only Tania's Doc was visible to Mike's account. Taylor supplies the links to the other five (the
live working Docs, not exports), and the Kaed x Taylor example docx, which is in his claude.ai
project, not on this machine.

## 4. Status cells that hold a dropdown chip

If managers use a Google Docs dropdown chip for Status, the API returns only a placeholder (U+E907)
for it, so its value cannot be read. The reconciler reports such a row as unreadable and asks once
in Needs Your Input; it never treats it as done or open. If dropdowns are in use, completion has to
be typed as the word Done. Taylor or Mike checks one live Doc.

## 5. New rows copy chip placeholders from the row above

Observed: `insertTableRow` copies a chip placeholder into the new row wherever the row above holds
a chip (a date, a person). The writer clears them in the cells it fills, in a second verified
phase. Rows a manager adds by hand may carry them; that is harmless to reading.

## 6. Calendar

UNPROVEN on this project: the build token had no calendar scope, so whether the Calendar API is
enabled on `bigquery-487308` is unknown until Taylor's consent with `calendar.readonly` and one
`ea_doctor.py` run. Also needed from Taylor: the six series (or ten minutes to confirm
`calendar_next.py --discover`), and each manager's work email, which is how discovery matches
attendees reliably.

## 7. Timezone

`America/Toronto` is assumed from YYZ. Taylor confirms it (blueprint section 11 asks for it to be
verified). It decides every relative date and the 07:00 tick.

## 8. Visible refs in the Docs

Each action row's Title ends with its register ref, for example "[A-0007]". It makes completion
reconciliation survive a manager retyping the line (the named range would not). Taylor decides
whether he wants them visible; `ref_tokens` in a Doc's map turns them off.

## 9. Assignee and date formats

The writer puts the owner's first name as plain text in Assignee (not a person chip, which could
notify the person) and a date chip shown as "Oct 2, 2026" in Date, or "TBD". Taylor may prefer the
format his Docs already use.

## 10. Edit rights and shared drives

`link_docs.py --verify` reads each Doc and reports whether Google returned a revisionId, which it
does only to editors. A Doc owned by a manager and shared to Taylor as a viewer will show READ ONLY
and every write to it will refuse. Completion is still read from it.

## 11. Which Google account the token belongs to

The consent asks for no email scope, so the doctor cannot confirm the token is Taylor's and not
someone else's. INSTALL step 5 has Taylor sign in himself; adding the email scope would let the
doctor check it, at the cost of one more line on the consent screen.

## 12. PowerShell is a second shell (a finding that also applies to PIPER)

Claude Code on Windows with Git Bash enables a native PowerShell tool by default for claude.ai
accounts and treats it as the primary shell. Every shell gate here matches `Bash|PowerShell`.
PIPER's gates match `Bash` only, so on Cass's machine a PowerShell command can pass its shell gates
unchecked. Reported to Mike; not changed in PIPER by this build.
