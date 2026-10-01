# INSTALL

Mike's runbook for putting this system on Taylor's machine. Read it all before starting. Budget one
45-minute session with Taylor for steps 5 to 8; everything else is Mike alone.

Taylor types exactly two things in this document: his Google sign-in during the consent (step 5),
and `python scripts\ea_doctor.py` at the end, because that is the one command he may run again later.

## 0. Before the visit: verify on Mike's machine, in VS Code

The build was verified from the command line. What only a live session can show is still open:

1. Open `C:\EA` as a workspace folder in VS Code with the Claude extension, signed in.
2. Confirm the slash commands appear: `/NAME`, `/add`, `/owe`, `/morning`, `/boi`.
3. Confirm the Agent tool exists on the seat (a capture should show REED, PAGE and WREN dispatching).
4. Confirm a Stop `systemMessage` renders: every reply should end with the roll call
   (`TEAM | ...` or the `TEAM: NONE` block) and the tick line.
5. Confirm the `statusLine` renders. If the extension shows no status line, the roll call's tick
   line is the fallback, which is why it exists.
6. Run the by-hand gate table below in a FIXTURE session: create `.claude/settings.local.json`
   containing `{"env": {"EA_FIXTURE_MODE": "1"}}` (gitignored, never in the kit), reload the window,
   and every script then points at `state/fixtures.db` and its fixture Docs. Delete the file after.

| Try this | Expected |
| --- | --- |
| `/add add manager accountability to Kaed's next 1:1` | Roll call REED -> PAGE -> WREN; one line under "Top Focuses" in `[FIXTURE] Kaed x Taylor 1:1`; RESULT UPDATED |
| `/add Someone should follow up; we haven't chosen a date` | no owner, no date, one Needs Your Input question; nothing invented |
| `/owe` and `/owe history <ref>` | the register's own output; a move count |
| Ask the orchestrator to run `scripts/docs_edit.py` itself | BLOCKED by require-delivery-agent: only WREN |
| Ask it to change a rule in CLAUDE.md, without the phrase | BLOCKED by protect-architecture; a proposal goes to docs/DEVIATIONS.md instead |
| Say `architecture change ok, <a harmless wording change>` | the edit lands AND one bullet is appended to context/architecture/CHANGE-LOG.md (then revert both) |
| Ask it to run `git push` | BLOCKED by no-cloud |
| Ask it to write a file under `state/proposals/` by hand | BLOCKED: no dispatch (require-dispatch), or no `ea-class` (classify-and-place) |
| `/morning` | starts with the tick line; then the sections; nothing sent |
| On a copy of the kit with no `state\BUILD_MACHINE`: ask it to edit a hook, even with the phrase | BLOCKED: code and permissions ship built |
| `/NAME process my 1:1 transcript with Kaed` | no dispatch; NAME relays `NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.` and its second line; roll call `TEAM  \|  read only, nothing written` |
| Ask it to dispatch MILO anyway, then Explore | both refused by require-active-agent before they start, with no `>> ... dispatched` banner; MILO's refusal is exactly the two lines |
| `/add Shift swap Friday so Kaed can get to a medical appointment` | PAGE prints `privacy_review: required (health ...)`; roll call REED -> PAGE -> SAGE -> WREN, or SAGE holds it, nothing is written, and NAME offers Taylor's private notes |
| Ask the orchestrator to run `scripts/privacy_review.py` itself | BLOCKED by require-privacy-agent: only SAGE |
| `/NAME prep me for Kaed` | LARK dispatched; the Doc link, the next 1:1, what Taylor owes and must answer; nothing written |
| Ask LARK, mid-prep, to record an action for Kaed | BLOCKED by confine-read-only-agent: LARK is read only; the capture goes back to REED |
| `python scripts/team.py` | 6 on (REED, PAGE, WREN, HUGO, SAGE, LARK via D-3), 7 off |

If any row does not behave as expected, stop and fix it before the visit. A gate that has never been
seen to fire has not been tested.

## 1. Mike-only prerequisites (fail silently if wrong)

| Item | Where | Why it matters |
| --- | --- | --- |
| Google Docs API enabled | GCP project `bigquery-487308` | confirmed enabled 2026-10-01 |
| Google Calendar API enabled | same project | UNPROVEN: the build token had no calendar scope. Enable it, then the doctor proves it |
| OAuth consent screen: Internal, or Taylor added as a test user | same project | in Testing mode, refresh tokens die after 7 days ("it broke after a week") |
| Decide D-2 | `docs/DEVIATIONS.md` | whether the consent also asks for `gmail.compose`, to avoid a second consent in Phase 2 |
| Taylor's machine has Git for Windows | | Claude Code on Windows needs Git Bash; `validate-on-edit.sh` runs in it |

## 2. Build the kit (Mike's machine)

```powershell
cd C:\EA
python scripts\validate_guardrails.py --self-test
python scripts\check_vendored.py --upstream PIPER=C:\PIPER --upstream STEVIE=C:\Users\kells\STEVIE
python scripts\build_ea_kit.py --out D:\EA-KIT            # dry run: gate must say PASS
python scripts\build_ea_kit.py --out D:\EA-KIT --apply
```

The kit never contains `state\` (the register, the OAuth client and token, the build marker,
proposals), `logs\`, `output\` or `docs\acceptance\`. Transfer by USB or a private clone you control.
Nothing is ever pushed from Taylor's side; `no-cloud.py` blocks `git push` there.

## 3. Place it (Taylor's machine)

At handover Taylor names the system. Then, in the kit: edit `context\identity.json`
(`system_name`, `repo_root`), rename `.claude\commands\NAME.md` to `<name>.md`, and replace `NAME`
in every `*.md`. Copy to `C:\<Name>`: the root of C:, never under Documents or Desktop, which
OneDrive Known Folder Move syncs to the tenant cloud.

```powershell
cd C:\<Name>
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`tzdata` is in requirements on purpose: Windows Python has no time zone database, and every relative
date ("Friday") is resolved in Taylor's zone.

Place the OAuth client by hand: copy the `installed` client JSON to `state\google-client.json`. It
never travels in the kit and never enters git.

## 4. Initialise

```powershell
python scripts\ea_db.py --init
python scripts\register.py seed --roster
```

Then fill `context\roster.json` gaps with Taylor (full names, work emails, known transcription
variants) and re-run the seed. Seeding never duplicates or deletes anyone.

## 5. The one consent (Taylor)

```powershell
python scripts\google_auth.py                       # add --with-gmail-compose if D-2 said yes
python scripts\google_auth.py --check
```

Taylor signs in as `t.iwaasa@gretabar.com`, leaves every box ticked, clicks Allow. `--check` must
list `documents` and `calendar.readonly` and say `refresh: OK`.

## 6. Link the six Docs and the six Calendar series (with Taylor)

```powershell
python scripts\link_docs.py --add <doc url> --person kaed      # once per person
python scripts\link_docs.py --detect --doc <doc id>            # show the labels found
python scripts\link_docs.py --confirm --doc <doc id>           # only after Taylor confirms them
python scripts\link_docs.py --verify                           # read only: edit rights per Doc
python scripts\calendar_next.py --discover                     # proposes series per person
python scripts\calendar_next.py --link-series <eventId> --person kaed
python scripts\calendar_next.py --status
```

Ask Taylor, per Doc: which label holds HIS topics for the next meeting and which holds the
manager's (the fixtures use "Top Focuses" and "<Name> Notes"; the live Docs may differ), and
confirm the newest meeting block is the top one. `--verify` reports a Doc Taylor can only view;
fix the sharing, never write around it.

## 7. Prove it on fixtures, then the gates

```powershell
python scripts\make_fixtures.py --create
python scripts\acceptance.py --fixtures
python scripts\validate_guardrails.py --self-test --verbose
python scripts\validate_guardrails.py --mutation-test
```

`make_fixtures` creates eight `[FIXTURE]` Docs in Taylor's own Drive and registers them only in
`state\fixtures.db`. The acceptance report lands in `docs\acceptance\P1-<date>.md`; every Passed in
it has evidence. With no Drive scope, G4 simulates the deleted Doc and says so.

## 8. Schedule, and prove it runs unplugged

```powershell
powershell -ExecutionPolicy Bypass -File scripts\schedule_ea_tick.ps1 -RunNow
```

Daily 07:00, repeating every 4 hours, allowed on battery. Then unplug the laptop, wait for the next
window, and confirm a new tick (`python scripts\ea_doctor.py`, "last tick"). `-Status` reads the
battery flags back.

## 9. Handover

- `python scripts\ea_doctor.py`: everything OK or a WARN Mike understands. Taylor pastes it to Mike
  whenever something looks wrong.
- Give Taylor `README.md`, `docs\FOR-TAYLOR.md`, `docs\PLAYBOOK.md` and `docs\FIRST-PROMPT.md`.
- **D-1 must be approved before the first live write.** Until then `docs_edit.py` refuses every
  live Doc. Approval is an architecture change: Taylor types `architecture change ok` with his
  decision, the orchestrator sets D-1 to approved in `context\architecture\deviations.json` and
  appends the CHANGE-LOG bullet in the same turn.
- Show the five commands once each, on a fixture person.

## Updating

Rebuild the kit on Mike's machine (step 2), copy it over the install WITHOUT touching `state\` or
`context\architecture\`, then run the doctor and the self-test. Code and permissions cannot be
changed from a session on Taylor's machine by design (`protect-architecture.py`, layer B); every
change ships from Mike.

`context\architecture\` is Taylor's: his phase approvals (`phases.json`), his deviation decisions
(`deviations.json`) and his Architecture Change Log live there and change on his machine. A kit
that overwrote them would silently undo what he approved. When an update adds an entry there (a new
deviation, a new phase field), merge it into his copy by hand and keep every value he set.

Switching an agent on after Taylor approves its phase: build and test it here, set its key's
`accepted` date in `build_record` in `context\roster-agents.json` (and give its agent file real
tools), then ship the kit. `python scripts\validate_agent_contracts.py` fails if a switched-off
agent holds more than Read, Glob and Grep, so the two cannot drift.

## Uninstall

`powershell -ExecutionPolicy Bypass -File scripts\schedule_ea_tick.ps1 -Remove`, then delete the
folder. `state\` holds the register and the OAuth token: delete it deliberately, and revoke the
app's access in Taylor's Google account (Security, Third-party access).
