# Privacy

Ported from PIPER's PRIVACY.md. The first section is kept as written there, because it is the
sentence people most want to be stronger than it is.

## The single most important thing in this document

**A Claude Enterprise seat is not a privacy control.**

Enterprise means two specific things: Anthropic does not train on Taylor's conversations, and audit
logs of his sessions exist. It does not mean the content stays on his machine. Every time an agent
reads a running Doc, a register row or a Needs Your Input question to help him, that content is
sent into a conversation running on Anthropic's infrastructure to produce the answer. The
local-only rules in this repo govern FILES, not CONTEXT.

So: "the register lives on Taylor's laptop" is true. "His 1:1 notes never leave his laptop" is
false: the Docs already live in Greta's Google Workspace, and anything an agent reads during a
session goes to the model. The accurate sentence is "the register and its files stay on this
machine; the model that reads them to help him runs on Anthropic's infrastructure under Greta's
Enterprise agreement, with no training and with audit logs".

## What stays on this machine, and what does not

| Thing | Where it lives | Leaves the machine when |
| --- | --- | --- |
| The register (`state/ea.db`) | this laptop only; never synced, never in git, never in the kit | an agent reads part of it during a session |
| The OAuth token and client (`state/`) | this laptop only | never; only used to call Google |
| Proposals and snapshots (`state/proposals`, `state/records`) | this laptop only | an agent reads one during a session |
| Taylor's private notes (`state/private/notes.md`) | this laptop only; never synced, never in git or the kit | an agent reads them during a session |
| Taylor's overlay (`state/taylor/`): his decisions, rules, living blueprint and the lessons he taught | this laptop only; never synced, never in git or the kit | every session: the session-start hook loads his rules and the lessons in effect |
| The running 1:1 Docs | Greta's Google Workspace (they always were) | already in Google; read into a session when needed |
| Fixture Docs | Taylor's own Drive, titled [FIXTURE] | they contain placeholder text only |
| The audit log (`logs/`, the audit table) | this laptop only | never, unless someone sends it |

`no-cloud.py` blocks writes into OneDrive, Dropbox, Google Drive for desktop and network drives, and
blocks `git push` and the cloud command-line tools. The repo sits at the root of C: because
Documents and Desktop are redirected to OneDrive on a corporate laptop.

## Practically

- Read what a task needs. `/owe` reads the register, not every Doc; a capture reads one Doc.
- Managers' notes in a Doc are theirs. The writer adds lines and table rows and sets Status and Date
  cells for the system's own actions; it never rewrites or deletes their content.
- Person chips are not written into Docs (Assignee is plain text), so a capture cannot notify a
  manager by mentioning them.
- Phase 2 (transcripts) has stricter rules in blueprint section 2: raw transcripts are private
  Taylor data and never go into a shared Doc. Nothing in Phase 1 reads a transcript.

## Personal context in a Doc a manager reads

A running 1:1 Doc is read by the manager it is about, so a line written there is a disclosure to
that person. Every Doc edit proposal is screened for personal words: health, family, leave, mental
health, addiction, discipline, harassment or a complaint, legal or immigration matters, and one
person's pay. A flagged proposal waits for SAGE, who approves it only when the words are what the
manager needs for the work, and holds it otherwise. A hold writes nothing to the Doc; Taylor is told
why and offered his private notes instead, which stay on this laptop.

What this does not cover: the screen reads words, not meaning, so a personal matter phrased without
any of them passes (`docs/OPEN-QUESTIONS.md`, item 12). The register on this laptop keeps the words
Taylor captured either way; the screen decides what reaches a Doc, not what the register holds.

## The law, stated so the right questions get asked

Not legal advice. YYZ is in Ontario, which has no private-sector employee-information statute like
Alberta's or British Columbia's PIPA; Greta's handling of employee personal information there sits
mainly under PIPEDA where it applies, the Employment Standards Act and common law. A tool that reads
managers' 1:1 notes is the kind of thing worth confirming with counsel: what, if anything, managers
should be told about it. Greta remains responsible for the data either way.

## What this system does not claim

No compliance certification. Not that local storage means no third party ever sees the content (see
the first section). Not that Anthropic's retention matches Greta's; that is the Enterprise
agreement's to say.
