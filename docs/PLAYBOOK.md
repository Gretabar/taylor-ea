# NAME: Playbook

Eight habits for working with NAME well. None of them are complicated, most of them just mean typing less than you're used to.

**1. Never paste the architecture.**
NAME already knows your rules: the shipped ones live in `CLAUDE.md`, your own live in `state/taylor/rules.md`, and both load at the start of every session. It opens the relevant section of your architecture only when a task needs it. (It is deliberately NOT loaded whole every session.)
Why this matters: every Claude seat at Greta draws on one company-wide monthly budget. Anthropic's notices show it ran out on September 23 and, after it was raised, hit 90% again by September 30. Everything in a chat gets re-read on every reply, so a pasted 277-paragraph document multiplies in cost with every message that follows it.
Before: "Read the complete architecture and audit every GRETA bot, workflow and data store."
After: "/NAME run the Phase 1 audit"

**2. One task per chat.**
A chat asked to audit, decide, build and report all at once gives you a shallower answer on all four, and costs more than four short chats would.
Before: "Audit everything, tell me what's reusable, start building Phase 1, and give me a timeline."
After: "/NAME audit what Phase 1 needs" (then a fresh chat once that's back)

**3. Commands, not essays.**
NAME parses a direct instruction more reliably than a paragraph explaining the thinking behind it.
Before: "I was thinking it might help if, when I mention something to Casey, it got tracked somewhere so I don't lose it before our next 1:1."
After: "/add I told Casey I'll send the bonus structure Friday, add it to our next 1:1"

**4. Clear command, not exploratory question.**
Your own rule: a command executes, a question gets options. Phrase it the way you actually mean it.
Before: "Should I add manager accountability to Kaed's next 1:1?"
After: "Add manager accountability to Kaed's next 1:1."

**5. When it asks you one question, answer just that one.**
A clarifying question means NAME is checking before it writes something wrong. Answering it plus two unrelated asks turns one quick check into three tasks it now has to untangle.
NAME asks: "Which Friday, October 2 or October 9?"
Before: "the 9th, and also add the hiring plan to Mark's next 1:1 and what do I owe Anya"
After: "October 9" (then the other two as their own commands)

**6. A refusal names a rule. Know which kind.**
Two different things can say no, and each takes a different fix.
(a) One of your own architecture rules: you're the authority. Say `architecture change ok` plus the change, and it applies and logs a dated line in your Architecture Change Log. Reword it without that phrase and you get the same refusal, on purpose, that's your own G1 test.
(b) A purely mechanical gate, like only WREN ever writing to your Docs, or it only writing to the Docs you've linked: rewording won't help, and neither will the phrase. Send Mike the exact gate it named and what you asked for.
Before: "Add the Christmas lights item to the YYZ weekly meeting Doc." (refused, that Doc isn't one of your linked Docs yet, weekly meetings are a Phase 2 item)
After: send Mike the exact refusal, it's a Phase 2 gap, not a wording problem

**7. A preference and a rule are not the same thing.**
A preference, how you like things presented or routed, just needs saying in one plain sentence: it's learned from your next session, no phrase required.
Before: "From now on, answer me first, then give the detail."
After: nothing extra to type, say it plainly and it applies from next session
A rule is different: anything that would set a price, package, discount, minimum spend, policy or sending permission gets asked about once, and only your yes adopts it (a change to the system's own behaviour instead takes the architecture change ok phrase from rule 6).
Before: "The corporate package is $45 now."
After: noted as a rule-candidate, one question raised, your yes adopts it

**8. Default model is fine for `/add` and `/owe`.**
Routine captures and lookups don't need the strongest model available. Save that for anything touching the architecture itself.
Before: switching to the top model before a routine /owe check
After: leave it on default, it's built for exactly this
