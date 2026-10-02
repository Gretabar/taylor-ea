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

## 12. What the privacy screen misses

`scripts/privacy_screen.py` reads words, not meaning. It flags health, family, leave, mental
health, addiction, discipline, harassment or complaints, legal or immigration matters, and one
person's pay, and was tuned so that "manager bonus structure", "Christmas lights", a guest
complaint and the health inspection pass. A personal matter written without any of its words
passes too. SAGE's and PAGE's prose say to route anything that feels personal through SAGE anyway,
but that is judgement, not a gate. Taylor's own phrasings over the first weeks are the real test;
a miss he notices is one line in the screen, added on Mike's machine.

## 13. A refused dispatch, observed live

The roll call skips a dispatch a gate refused, reading the refusal from the transcript
(`toolDenialKind`, or a `PreToolUse:` hook message). Both were observed on a live VS Code session
(v2.1.222) for a refused Bash call, and the same session shows PreToolUse hooks firing on the Agent
tool. A refused Agent call itself has not yet been seen live; the by-hand rows in INSTALL.md
section 0 are where it is seen.

## 14. Backing up what lives only on Taylor's laptop

For Mike and Taylor. Everything Taylor decides and everything the system learns lives only on his
laptop, outside git on purpose: his overlay (`state/taylor/`: his phase and deviation approvals,
his Architecture Change Log, his own rules, his living blueprint, his name for the system, his
lessons) and the register (`state/ea.db`: every action, topic, question and its history). A dead
or replaced laptop loses all of it; the code comes back with one clone, his history does not.

Where a backup may go is a privacy decision for Taylor, not a technical one: the register names
his managers and their commitments, and the overlay holds his private rules and notes. no-cloud.py
refuses every write into OneDrive, Dropbox, Google Drive or a mapped network drive, so today
nothing in this system can make a backup, and none is made. Options to put to him: an encrypted
USB copy he keeps, a private location he names (which needs a deliberate change to no-cloud.py),
or none, accepting the loss. Undecided.
