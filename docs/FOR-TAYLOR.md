# NAME, for Taylor

NAME is the executive-assistant system Mike built for you, the same kind of system he runs for himself (STEVIE), scoped to exactly what Phase 1 of your own blueprint asks for: a running document for each of your six 1:1s and one canonical Action Register, kept straight without you having to hold all of it in your head. You'll see REED, PAGE, WREN and HUGO named in what it does. You don't need to track which does what to use it, it's here so you know what's actually happening when something runs.

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
- After a capture (an `/add`, or anything through `/NAME` that writes), the line at the bottom should name REED, PAGE and WREN. If it reads TEAM: NONE instead, nothing actually got dispatched to write it, even if the chat reads like it worked.

## Talk to it the way you'd talk to a person

- **Done.** Say so ("mark the Casey bonus item done") or type Done in its Status cell yourself. NAME picks up either one.
- **Move it.** Give the new date ("push Casey's bonus structure to Friday October 9"). The old date stays in history, ask `/owe history <ref>` to see how many times it's moved.
- **Wrong person.** Correct it the way you'd correct a person ("that one's Kaed, not Cade"). It fixes the one you meant. It does not create a second Kaed.
- **Change a rule.** Say `architecture change ok` plus the change itself. It updates and adds a dated line to your Architecture Change Log. Ask "show me all architecture changes" anytime to see it.

## Where the register lives

Everything NAME tracks sits in one small file on this machine, not a spreadsheet you maintain and not a second task list. The Doc is what you and your managers actually read. The register underneath remembers what the Doc can't: how many times a deadline moved, or who owned something before it got reassigned.

## The honest privacy note

One note, because a stronger promise than the truth isn't worth much. Keeping everything on this machine is not the same as keeping it private. When NAME reads one of your Docs, or works on something you've asked it to capture, that content goes into a conversation with Claude, on Anthropic's systems, under Greta's Enterprise agreement. Enterprise means your data isn't used to train their models, and that there's an audit trail of what ran. It does not mean none of it ever leaves this laptop. `docs/PRIVACY.md` has the exact detail of what that does and doesn't cover.
