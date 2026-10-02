# Deviations from the blueprint, for Taylor to approve or reject

Your blueprint (section 11) says a material change from the approved architecture is explained and
approved by you before it is built. Each entry below says what the blueprint asks for, what was
built instead, why, and what changes if you say no. Your decision on each one is kept on your
laptop in `state/taylor/deviations.json`, which only changes when you approve or reject in your own
words, and which updates never touch.

New proposals written on your laptop go to `state/taylor/proposals.md`. When you ask for something
that would change how the system works, it writes the proposal there and changes nothing until you
approve.

## D-1: the Action Register is a small database on this laptop

**Status: proposed. Every write to your live running Docs is switched off until you decide.**

What the blueprint says (section 3, "Proposed technical implementation"): reuse a suitable existing
Enterprise or GRETA data store first; Google Sheets is the fallback for the Action Register.

What was built: the register is a local SQLite file (`state/ea.db`) on this machine.

Why:
- It works without depending on Mike's Supabase or any other system you do not control.
- Every change is saved completely or not at all, and a real history table answers "how many times
  did this move?" without anyone maintaining it.
- Your running Docs stay the place you and your managers actually read, as the blueprint requires;
  the register sits underneath and is not a second thing you have to keep up.
- It is a pattern Mike already runs in another assistant he maintains.

What it affects: only the "proposed implementation" text in section 3, not a protected requirement.
The register is not visible in Drive; you see it through `/owe`, `/morning` and the Docs.

If you reject it: the register moves to a Google Sheet, which is a rebuild of the storage layer by
Mike, and nothing writes to your live Docs until that is done.

To approve: tell the system "architecture change ok: approve D-1". It records your approval and the
date in the change log, and live Doc writes switch on.

## D-2: ask for Gmail draft access in the first sign-in, or later

**Status: undecided. Mike's decision, not yours; listed so nothing is hidden.**

The Phase 1 sign-in asks Google for two things: your Docs, and read-only Calendar. Phase 2 will
need to create email drafts for you to review (never send). Asking for that now (`gmail.compose`)
saves a second sign-in later; asking later keeps Phase 1 to the minimum it needs.

Nothing in Phase 1 sends or drafts email either way.

## D-3: LARK preps you for a 1:1 now, read only, ahead of Phase 7

**Status: proposed. Switched on meanwhile, by Mike's decision; rejecting it switches it off.**

What the blueprint says: "Prep me for Kaed" is Phase 7 (section 10, "Preparation and
intelligence"), and the daily brief's meeting prep is Phase 3 (test P3.7: link the working Doc
and show only what you owe; a deeper briefing on request).

What was built: when you ask to be prepped for someone, LARK gives you the full briefing, your
part first: what you owe them and what you need to answer or decide, then what they owe you, the
topics for your next 1:1 (yours and theirs), what the Doc carries forward and what your last 1:1
recorded, and finally the time of your next 1:1 and the link to your running Doc. It reads the
register on this laptop and nothing else: no email, no Calendar call (the next 1:1 time is the one
the background check already keeps), and what it shows from the Doc is the copy that check last
read. It writes nothing. That is enforced: LARK can run only the prep command and the register's
read commands, and anything else it tries is refused before it runs.

Why: it is the part of Phase 7 that changes nothing, so it can run safely before the rest of the
phase, and it saves you assembling the same answer by hand before each 1:1.

What it affects: the order of your phases, not a protected requirement. The 7am brief (Phase 3)
and prep that reads your Calendar and email (Phase 7) stay off.

If you reject it: LARK switches off until Phase 3 or Phase 7 is approved and built. Nothing else
changes.

To approve: "architecture change ok: approve D-3". To reject: "architecture change ok: reject D-3".

## D-4: PENN, a sales and events pipeline, outside your blueprint

**Status: proposed. Not switched on.**

What the blueprint says: none of the seven phases has a sales or events pipeline. Phase 5 covers
reservation and corporate-event replies only, and says not to widen it into general inbox work.

What is proposed: PENN would track Tania's commission, promoter and event return on investment,
and stale leads followed up with Moreen.

What exists today: a name and a description. Nothing is built, and asking for PENN gets an
immediate answer that it is outside your architecture, at no cost.

What it affects: your architecture itself, because it adds a lane the blueprint does not have.
That is why it waits for you rather than for a phase.

To add it: "architecture change ok: add PENN". Mike then works out its rules with you (which
systems hold the numbers, what counts as a stale lead, who sees what) and builds it.

## D-5: TALLY is described while Phase 6 stays deferred

**Status: proposed. Not switched on, and Phase 6 stays deferred.**

What the blueprint says (section 9, "Protected deferral"): do not build broad reporting or a
separate KPI system in the initial build. After the initial system is implemented and tested, ask
you once whether to revisit Phase 6, and a No ends it.

What was done: TALLY (reporting, such as product and games mix and repeat guests) exists as a name
and a description only. No reporting is built, no KPI data is connected, and TALLY never asks you
about Phase 6. The single question at the end of the initial build stays the only time anyone asks.

Why it is written down here: an agent named for a deferred phase is something you should know
exists.

If you reject it: Mike removes TALLY's description. Nothing else changes.

To resume Phase 6 instead: "architecture change ok: resume Phase 6", then Mike builds it.
