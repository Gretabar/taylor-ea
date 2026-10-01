# Deviations from the blueprint, for Taylor to approve or reject

Your blueprint (section 11) says a material change from the approved architecture is explained and
approved by you before it is built. Each entry below says what the blueprint asks for, what was
built instead, why, and what changes if you say no. The current status of each one is kept in
`context/architecture/deviations.json`, which only changes when you approve or reject in your own
words.

New proposals land here too. When you ask for something that would change how the system works,
it writes the proposal here and changes nothing until you approve.

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
- It is the same pattern the HR assistant (PIPER) already uses.

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
