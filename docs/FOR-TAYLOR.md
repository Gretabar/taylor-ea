# NAME, for Taylor

NAME is the executive-assistant system Mike built for you, the same kind of system he runs for himself (STEVIE), scoped to exactly what Phase 1 of your own blueprint asks for: a running document for each of your six 1:1s and one canonical Action Register, kept straight without you having to hold all of it in your head. You'll see REED, PAGE, WREN, HUGO, SAGE and LARK named in what it does now, out of a team of thirteen. You don't need to track which does what to use it, it's here so you know what's actually happening when something runs. The full team is under Your team below.

## The five commands you'll use

**`/NAME <request>`.** The general front door. Say what you need in plain language and NAME works out which of the team handles it, no need to know the exact syntax. Example: "/NAME Casey's bonus structure deadline moved to Friday October 9" resolves to the right update without you having to know it's technically an owner and date change on an existing action.

**`/add <text>`.** The direct way to capture something the moment you think of it: a topic for someone's next 1:1, a commitment you just made, or both at once. Example: "/add I told Casey I'll send the bonus structure Friday, add it to our next 1:1" creates your action, owed Friday, and drops the topic in Casey's Doc, in one line.

**`/owe [person]`.** What's still open. Say "/owe" for everything across all six people, or "/owe casey" for just Casey. Add "history" and a reference, like "/owe history A-0012", to see how many times something's moved and when.

**`/morning`.** Your first check of the day, chat only, nothing gets emailed. Just type "/morning". It shows whether NAME is actually running, what's due today or overdue, what's still sitting in Needs Your Input, and what got written into your Docs yesterday.

**`/boi`.** For when NAME just suggested something and you agree with it. Instead of repeating the request, say "boi" and it does the specific thing it just proposed, nothing more, nothing it hasn't already told you about.

## What it writes, and what it leaves alone

NAME writes to one place: the Next 1:1 section of your six running Docs, either a new topic (yours or theirs), a new row in the Action Items table, or a Status update when something's done. That's all. It never deletes a line, a completed item stays visible, just marked done, so the Doc still reads the way it always has when you open it yourself.

In Phase 1 it does not send an email, on your behalf or to anyone else. It does not change anything on Calendar, it only reads the time of your next meeting so it knows which Doc section is "next". It does not read a transcript. Those are later phases. Each one switches on only once you've approved it, not automatically.

## Two signals that mean something's broken

Neither one means you did anything wrong. Both mean tell Mike.

- `/morning` shows LAST TICK in red. The background check that keeps your Docs and the register in sync hasn't run in a while, something's stopped.
- After a capture (an `/add`, or anything through `/NAME` that writes), the bottom of the screen names the team: `TEAM  |  REED -> PAGE -> WREN  (3 dispatched)`. A read-only command like `/owe` or `/morning` shows `TEAM  |  read only, nothing written` instead, that's normal, nothing got written so there's nothing to name. Watch for a framed block headed `TEAM: NONE - THIS TURN RAN SOLO`: if that appears after a capture, something got written without the team, tell Mike.

## Talk to it the way you'd talk to a person

- **Done.** Say so ("mark the Casey bonus item done") or type Done in its Status cell yourself. NAME picks up either one.
- **Move it.** Give the new date ("push Casey's bonus structure to Friday October 9"). The old date stays in history, ask `/owe history <ref>` to see how many times it's moved.
- **Wrong person.** Correct it the way you'd correct a person ("that one's Kaed, not Cade"). It fixes the one you meant. It does not create a second Kaed.
- **Change a rule.** Say `architecture change ok` plus the change itself. It updates and adds a dated line to your Architecture Change Log. Ask "show me all architecture changes" anytime to see it.

## Your team

NAME never does the work itself. It hands every job to the right specialist, thirteen of them in all. You don't need to track any of this to use the five commands above, it's here for when you want to know who's actually doing the work, or when NAME tells you someone isn't on yet.

**On now.** REED keeps the Action Register honest and never invents an owner or a deadline. PAGE reads your running Docs and works out where something belongs. WREN is the only one that actually writes into them, and reads every write back before calling it done. HUGO gets things unstuck when a token expires or something looks wrong. SAGE is the privacy check: it only steps in when something personal is headed for a Doc your managers can read, things like health, family, leave, discipline, or one person's pay, and when it does, it can hold the item and offer to keep it in your private notes instead. LARK answers "prep me for Kaed" (or anyone else on your six) with a short, read-only briefing: what you owe Kaed, what Kaed owes you, what's queued for your next 1:1. The 7am version that lands without asking is Phase 3 and isn't on yet.

**Waiting on a phase.** MILO (meetings and transcripts) and RUTH (professional documentation, drafted privately, you decide if it's coaching or discipline, not RUTH) are both Phase 2. ATLAS (projects and company knowledge) is Phase 4. CLEO (reservation and corporate-event replies) is Phase 5. JUNE (calendar) is Phase 7.

**Needs your say.** PENN (sales and events: Tania's commission, promoter and event ROI, stale leads with Moreen) sits outside your architecture as it stands. TALLY (reporting) is Phase 6, the one you deferred.

A switched-off agent costs nothing to ask for. Nothing runs and nothing gets billed, you're told instantly what it needs:

- **Before a phase is on.** `NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.` `To switch it on: say "architecture change ok: switch on Phase 2", and Mike builds it.`
- **After you say the phrase, before Mike finishes building.** `APPROVED, NOT BUILT YET: MILO (meetings and transcripts), Phase 2.` `Mike is building it; nothing to do on your side.`
- **PENN, outside the architecture.** `NOT SWITCHED ON: PENN (sales and events pipeline) is outside your architecture.` `To switch it on: say "architecture change ok: add PENN", then Mike builds it.`
- **TALLY, the phase you deferred.** `NOT SWITCHED ON: TALLY (reporting) is Phase 6, which you deferred.` `To switch it on: say "architecture change ok: resume Phase 6", then Mike builds it.`

Switching a phase on, or adding PENN, is your call, the same phase gate as everything else in your blueprint. Say the phrase and it's logged in your Architecture Change Log the same day. It goes live once Mike has actually built and tested it, not the moment you say it.

## Where the register lives

Everything NAME tracks sits in one small file on this machine, not a spreadsheet you maintain and not a second task list. The Doc is what you and your managers actually read. The register underneath remembers what the Doc can't: how many times a deadline moved, or who owned something before it got reassigned.

## The honest privacy note

One note, because a stronger promise than the truth isn't worth much. Keeping everything on this machine is not the same as keeping it private. When NAME reads one of your Docs, or works on something you've asked it to capture, that content goes into a conversation with Claude, on Anthropic's systems, under Greta's Enterprise agreement. Enterprise means your data isn't used to train their models, and that there's an audit trail of what ran. It does not mean none of it ever leaves this laptop. `docs/PRIVACY.md` has the exact detail of what that does and doesn't cover.
