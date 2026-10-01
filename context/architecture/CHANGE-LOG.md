# Architecture Change Log

Blueprint section 13: once the initial architecture is approved and implemented, each architecture
change Taylor asks for is recorded here as one simple bullet with the date, the time, and what Taylor
asked to change. Nothing else: no change IDs, approval columns, dependency maps, rollback framework
or drift detection.

Entry format (the source's separator did not survive extraction, so a pipe stands in):

`- [YYYY-MM-DD] | [HH:MM] | [requested change]`

How an entry gets here: Taylor's own latest message contains the approval phrase documented in
CLAUDE.md; the orchestrator makes the change and, in the same turn, appends exactly one bullet below.
If the change needs code, the bullet says it was requested from Mike, not that it is live.

No entries yet. Nothing has been changed since the baseline, and no hypothetical examples are recorded.
