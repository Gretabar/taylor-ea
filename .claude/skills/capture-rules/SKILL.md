---
name: capture-rules
description: "REED's rules for turning Taylor's words into register records: topic versus commitment versus completion versus unresolved, how owners and dates are resolved, and when to ask. Owner: REED. Distilled from blueprint sections 1, 3 and 4 so the blueprint is not re-read on every capture."
---

# Capture rules

Owner: REED. The source is Taylor's living blueprint (`state/taylor/blueprint.md`, else the v1 baseline in `context/architecture/`), sections 1, 3 and 4; this is the
working distillation. If they ever disagree, the blueprint wins and this file is wrong.

## What a clause is

| Taylor says | It is | Record |
| --- | --- | --- |
| "Add manager accountability to Kaed's next 1:1" | a TOPIC for Kaed's next 1:1 | `add-topic --person kaed --side taylor` |
| "Kaed wants to talk about the patio" | a TOPIC, the manager's side | `add-topic --person kaed --side theirs` |
| "I told Casey I'll send the bonus structure Friday" | a Taylor COMMITMENT, owed to Casey, due Friday | `add-action --owner taylor --counterpart casey --due <Friday>` |
| "...add it to our next 1:1" in the same sentence | ALSO a Casey topic | `add-topic --person casey` |
| "Kaed will bring a closing process next week" | Kaed's COMMITMENT, if Taylor states the assignment | `add-action --owner kaed --due unresolved --due-note "next week"` |
| "We need to improve closing follow-through" | an OBSERVATION, not a task | nothing, or a topic if Taylor asks |
| "I sent Casey the bonus structure" | a COMPLETION | `complete <ref> --via chat` |
| "Push it to next Friday" | a CHANGE to the existing action | `update-action <ref> --field due_date` |
| "Someone should follow up; we haven't chosen a date" | a commitment with NO owner and NO date | `add-action --owner unresolved --due unresolved` |
| "Add leadership-structure feedback to everyone's next 1:1" | SIX topics, one per person with a 1:1 | `add-topic` six times |

A topic never gets an owner or a date. An action never invents one. One action per commitment,
ever: a change is an update to the same ref, never a second action. Check `owed` and `topics`
before creating anything that might already exist.

## Owners

- Resolve every name: `python scripts/register.py resolve-person "<name as heard>"`.
- "I", "me", "Taylor" is `taylor`. A person merely mentioned is not the owner.
- `unresolved` and `ambiguous` are answers, never failures. Record `--owner unresolved`; an
  unresolved owner opens one Needs Your Input row by itself.
- A corrected transcription variant ("that one's Kaed") is an alias:
  `python scripts/register.py alias --person kaed --add "<variant>"`. Never a new person.

## Dates

- Resolve against the INSTRUCTION date in Taylor's timezone (`context/identity.json`, or his override in `state/taylor/identity.json`):
  `python scripts/register.py resolve-date "<phrase>" --from <YYYY-MM-DD>`.
- `ambiguous` (a weekday said on that weekday; "next Friday") is asked about or recorded as
  `--due unresolved --due-note "<Taylor's words>"`. Never pick one.
- "Next week", "soon", "EOW" do not name a day: unresolved, with the words kept as the note.

## When to ask

One targeted question, only when the answer matters now and cannot be recorded as unresolved: two
people answer to the same name, or Taylor asked for something to happen on a date that is
ambiguous. Otherwise record what is known and let the Needs Your Input row carry the question.
Never "are you sure?" after a clear instruction (blueprint section 1).

## Words

The register text is what lands in the Doc. Write it as Taylor would read it in his Doc: short,
plain, his words where possible. No em dashes and no emojis: `docs_propose.py` refuses them.
