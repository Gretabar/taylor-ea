---
name: reality-checker
description: "The orchestrator's pre-dispatch sanity gate (Step 1.5). Runs after a request is read and before any agent is dispatched: is the premise right, is the build over-sized, does the record already exist, which source is canonical, and does the request change a protected requirement. Owner: orchestrator. Ported from PIPER's reality-checker with every anchor re-pointed at this repo."
---

# Reality Checker

Owner: orchestrator. Ported near-verbatim from `C:\PIPER\skills\reality-checker\SKILL.md` (which
adapted STEVIE's): the four checks and the two output shapes are unchanged; the anchors are this
repo's files, plus a fifth check for protected requirements.

## When to run

Every `/NAME` request that would capture, change or build something. Skip for one-line
acknowledgements, plain lookups (`/owe`, `/morning`), and `/boi`.

## The posture

Terse: 6 to 10 lines. A gate, not a planner. Cite the file behind a flag.

## The five checks

1. **Premise.** Is the framing right? A topic phrased as a task ("add manager accountability")
   is still a topic. "Everyone" means the six people in `context/roster.json` with a 1:1, not
   Moreen. A relative date said on that same weekday is ambiguous (`register.py resolve-date`).
2. **Over-build.** Does the scope exceed the request? Phase 1 is the register and the six running
   Docs. Email, transcripts, the daily email brief, calendar changes, projects and reservations
   are later phases (blueprint section 11, "Build sequence"). Flag, do not improvise.
3. **Existing record.** Is it already captured? `python scripts/register.py owed`,
   `python scripts/register.py topics --person <key>`. A replayed `/add` returns the existing ref
   by itself; a reworded one may not, so look.
4. **Source of truth.** The register (`state/ea.db`) for what is owed; the Doc itself for what a
   Doc says (`python scripts/docs_read.py --doc <id>`); the Calendar for when a meeting is
   (`python scripts/calendar_next.py --status`). Never a summary from earlier in the chat.
5. **Protected requirement.** Would this change a rule in `CLAUDE.md`, the blueprint, a permission,
   or how the system works? Then the only action is a proposal in `docs/DEVIATIONS.md` and a
   question to Taylor. Anchor: blueprint section 1 ("One master architecture").

## Output

```
GATE: PASS
Premise: OK | Scope: Phase 1 | Existing: none | Source: register
Dispatch: REED -> PAGE -> WREN
```

```
GATE: FLAG (premise | scope | existing | source | protected)
Issue: one sentence
Anchor: the file and section
Recommended: one sentence
Holding until Taylor confirms.
```

A flag pauses; Taylor can override it, except a protected-requirement flag, which only his
approval of a written proposal clears.
