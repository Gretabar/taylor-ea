# Vendored from PIPER and STEVIE

Every file in this repo that came from `C:\PIPER` or `C:\Users\kells\STEVIE`, what
was done to it, and the exact bytes it came from. Files written new for this
system are listed too, as NEW, so the table is a complete inventory of the
framework.

**Why this file exists.** Standalone means it drifts. The moment a fix lands in a
shared file on one machine, the other machine does not have it and nothing says
so. Copies are fine; UNDOCUMENTED copies are how STEVIE's dispatch parse ended up
in four places, three of them subtly different.

**How to use it.**

```
python scripts/check_vendored.py                                   local integrity
python scripts/check_vendored.py --upstream C:\PIPER                plus every PIPER row
python scripts/check_vendored.py --upstream PIPER=C:\PIPER --upstream STEVIE=C:\Users\kells\STEVIE
python scripts/check_vendored.py --rehash                          after a deliberate PORT or NEW edit
python scripts/check_vendored.py --add <local> <UPSTREAM:source> <MODE> --upstream ...
```

**VERBATIM** must stay byte-identical to the source. Edited in place, it is a fork
nobody declared: fix it upstream and re-vendor. `--rehash` refuses to touch one.

**PORT** was adapted deliberately and IS expected to differ. What gets checked is
whether the SOURCE has moved since, reported as drift to review, never as a
failure of the port itself.

**NEW** has no upstream. Checked only for "changed since the manifest was written".

**About the git column.** PIPER is not a git repository, so every PIPER row says
`untracked` and the source sha256 is the identity, as PIPER itself does for its
STEVIE rows. A STEVIE row carries the short commit of the source file, or
`untracked` when the file is uncommitted or modified in STEVIE's working tree.

Vendored 2026-10-01.

| local path | source path | git sha | source sha256 | local sha256 | mode |
| --- | --- | --- | --- | --- | --- |
| `.claude/hooks/_transcript.py` | `PIPER:.claude/hooks/_transcript.py` | `untracked` | `727531fd2915fefcfa58a0ccc6980debd88350e1918a7706ca2631eda5c9646b` | `727531fd2915fefcfa58a0ccc6980debd88350e1918a7706ca2631eda5c9646b` | VERBATIM |
| `.claude/hooks/_lib.sh` | `PIPER:.claude/hooks/_lib.sh` | `untracked` | `19e325f96a7904e4acf853be2b901c3de165c0ffe5fdcf992e190c3106368797` | `19e325f96a7904e4acf853be2b901c3de165c0ffe5fdcf992e190c3106368797` | VERBATIM |
| `scripts/job_lock.py` | `PIPER:scripts/job_lock.py` | `untracked` | `e81ceffd6c0d3811a5d4567c0241fc0cdde83ab940836caeacf37694375b067a` | `e81ceffd6c0d3811a5d4567c0241fc0cdde83ab940836caeacf37694375b067a` | VERBATIM |
| `scripts/runs_log.py` | `PIPER:scripts/runs_log.py` | `untracked` | `03412631208eedacd5cf2649a602fbfaafaf652359ea4d34a527c22eb4f90936` | `03412631208eedacd5cf2649a602fbfaafaf652359ea4d34a527c22eb4f90936` | VERBATIM |
| `.claude/hooks/_gate.py` | `PIPER:.claude/hooks/_gate.py` | `untracked` | `27f386c1a3b7ab9ebeba0d21baf6f26b3f5bfbf3be64b4fbdd96140b522f1dac` | `cd429f1dab647cc82f77e45121aa5e6563dec39bfc56a7e7025fdf28b9162e78` | PORT |
| `.claude/hooks/_audit.py` | `PIPER:.claude/hooks/_audit.py` | `untracked` | `f53c94b79c114c443ca3fa903417ab651d4508378c70cc754d0b9856dbaf62ed` | `d39ca6924696b4efe9a81b80ecfef81e1218f65a40027287c644a1a0ef6d52c6` | PORT |
| `.claude/hooks/require-dispatch.py` | `PIPER:.claude/hooks/require-dispatch.py` | `untracked` | `e0fe3e67171149bdc77e9184127350a2e62748feff9ab4b0234df4178568ae8e` | `5b098243660dee0a34a44a7041d9331e4787cddf788a44da230bd3eeb0a342c1` | PORT |
| `.claude/hooks/no-cloud.py` | `PIPER:.claude/hooks/no-cloud.py` | `untracked` | `a9b74363b4ebdc909575c6beae03f17c80e43d8fd6fff4864e46890a5503633b` | `c30aa4eba7961307e8108aed9c4f5a20f89203e7e9d0db4dddd0531366d46f18` | PORT |
| `.claude/hooks/classify-and-place.py` | `PIPER:.claude/hooks/classify-and-place.py` | `untracked` | `48115417f63102f1248a85477c23c3a8417aad0d2a65734a2241484dcd32f313` | `fa1a5d1842221be67f1524142cce5d77c3e5988fcb70053fa4a087d14418de29` | PORT |
| `.claude/hooks/require-approval.py` | `PIPER:.claude/hooks/require-approval.py` | `untracked` | `543e4c7c545a6964daf846f902766686a54c871b0e79183408e65648912104d1` | `8837fe841f93bd125ced94cd78e5b32797fe70979e3815c23d080ad2fcecfe51` | PORT |
| `.claude/hooks/announce-dispatch.py` | `PIPER:.claude/hooks/announce-dispatch.py` | `untracked` | `9a4b32733759f90684d0689a925979642114229548ff31a6313895977adcfe37` | `eb2ad87072a5e33df154f0892881d84298be1ea6eb4c84773143814804991d6d` | PORT |
| `.claude/hooks/team-rollcall.py` | `PIPER:.claude/hooks/team-rollcall.py` | `untracked` | `f6800761b72db78b1c556001a3f1866741b08570ab21242f25909bc8b81b5bf5` | `ccbe84e933cb105796bfefebb339152297a37beb9e6d7cfa4afdf7f121fc5499` | PORT |
| `.claude/hooks/statusline-ea.py` | `PIPER:.claude/hooks/statusline-piper.py` | `untracked` | `5066cb7556b7837c58906721d1466c41efe8331455e019fe402c1ce3a26ac1b5` | `c4d82805672c2ef2e5e5429e8ba54ef9591f579ec5c1ae124e2d642a57006457` | PORT |
| `.claude/hooks/validate-on-edit.sh` | `PIPER:.claude/hooks/validate-on-edit.sh` | `untracked` | `915b7a11e81718da9e18d03a07b742e66ed1a16096b9081d2523d7601d537acd` | `3d3eb2b7bc77a1bbe20f30e978d5d324b91b53263c0931d8b4d149d7e034bffd` | PORT |
| `.claude/settings.json` | `PIPER:.claude/settings.json` | `untracked` | `4a0f8f1882659f951beecdc9437be412b95be38ae32cee4cfd677e6553bffe77` | `136f7c1fa12123307a7cb2f3c8ebab0cae152c318da94b706f6eee8732a88959` | PORT |
| `scripts/ea_db.py` | `PIPER:scripts/piper_db.py` | `untracked` | `1f0a2aa94a78366de4408268bf08dd46e0bd6f4a9c2bf1caa5f6e42029af50cd` | `0b2b9def1dda06b13e7520198af2ad03c4d4e616eb1d81414ef8620ba2fa8482` | PORT |
| `scripts/approvals.py` | `PIPER:scripts/approvals.py` | `untracked` | `6ae22201b737e5723240777a3ac75de183ddaf116b14f97f398324232f5d4214` | `dabda1cc9a0c988f5005862986eedda71924b7657dd8fea385e6972e0681d4f5` | PORT |
| `scripts/notify_owner.py` | `PIPER:scripts/notify_cass.py` | `untracked` | `661fb20f4e154868d699ab00732c632aa8536740ac484f411328956febf37847` | `e91e5d61ea435602d3b96ba5687c36ca756093cd7d42d112f7683d33facc64f4` | PORT |
| `scripts/validate_agent_contracts.py` | `PIPER:scripts/validate_agent_contracts.py` | `untracked` | `fb2892cca02a78f2495ccb78ac1645432ec0e4ced23a1220c6e2bd1c154ae896` | `79e694a8ac597a412a7e4f0f65df63124b45bfcd1fa78ca7ab409422f1c6aa6e` | PORT |
| `scripts/validate_content_rules.py` | `PIPER:scripts/validate_content_rules.py` | `untracked` | `310ad7f6afa5f38be5c18dc27d580fd37005dffdd5551114b15587c3e98fbdc0` | `4ac1fde475bfb47ef9c7e687bf46ef0b2d4c9deb7e70dd8af212564dbc30723b` | PORT |
| `scripts/validate_guardrails.py` | `PIPER:scripts/validate_guardrails.py` | `untracked` | `704b4700e07cc3c26e3650507b73bd7660eb9d01db2216b973fedeaa54c7dfe7` | `cefcb2b21dcc13b8adb5a60aded7242f66058576b288193c7c387f3d74407fcd` | PORT |
| `scripts/check_vendored.py` | `PIPER:scripts/check_vendored.py` | `untracked` | `3e9ab0c1894a70989998c8e536331bacb6f722d40ffc0ac0abadd84d5ce646ef` | `38816c2bb00335002c4c93dccc39d95d6620b8b4935b6475adac03eab9f753f5` | PORT |
| `.claude/hooks/_health.py` | `-` | `-` | `-` | `2ab3ed936716efb6b290c479a5e8790e461fa14965ecd2165a81d22e8b7b19ac` | NEW |
| `.claude/hooks/require-delivery-agent.py` | `-` | `-` | `-` | `190205d929fbf92aea96e769fa90b13957a11e20fbb428b1fa00969fc9a68357` | NEW |
| `.claude/hooks/protect-architecture.py` | `-` | `-` | `-` | `e4643ed1eb8fee8f4deaf561ed6747ffe22dd7397f96daf75706376e05651da9` | NEW |
| `scripts/register.py` | `-` | `-` | `-` | `c6bd14f0bf119f03298d30a530417778a61bf49538bd284769b670d26cf88969` | NEW |
| `scripts/google_creds.py` | `STEVIE:scripts/upload_to_drive.py` | `untracked` | `8501f0e5e2c0f6c5e0b8220ae2a650eb7af453cb413b64666690889f6674f883` | `9edf8952c0912ac2a203685ee23ec5559974dcbb443678d562fe3bec37a3924b` | PORT |
| `scripts/google_auth.py` | `STEVIE:scripts/marketing_report/google_auth.py` | `e3f42d2` | `92c3d715e28338de6aaef8b9c6241f8ac8c1abe14810b6ec3a841a5f1c272f8e` | `bc6115a7feb84c96743b96c71d1c4284ee80f65804f1dc59bd1ab494b03d84c5` | PORT |
| `scripts/docs_read.py` | `-` | `-` | `-` | `4780fe9236bd6e9b165c6b2932196d7b333fb3e41d35f86111fe1c2027c3ba72` | NEW |
| `scripts/link_docs.py` | `-` | `-` | `-` | `9d32f6e2d9eb621758be491442c0497b0cffbe32f5bede9ab5eb84bdb82a49c7` | NEW |
| `scripts/calendar_next.py` | `-` | `-` | `-` | `d703104020d0751f994fd4c18168e7e81e0c821272187b79243abd1aa0ef8fe2` | NEW |
| `scripts/make_fixtures.py` | `-` | `-` | `-` | `133fc4b384b7c340b311f0f1c510fdc47220f5c999b64ae15c1b281990502374` | NEW |
| `tests/test_calendar_next.py` | `-` | `-` | `-` | `39b93a6afe224422e711ce8b14e1edb8c4ba08c99d0544ff214f8f42dce37c22` | NEW |
| `tests/test_docs_read.py` | `-` | `-` | `-` | `eaced801952ec08874cba7972d324fcf9e146dd957cb3541da9c05295e561242` | NEW |
| `scripts/docs_propose.py` | `-` | `-` | `-` | `8ba8feec1d3cd554091e88a76e7601b1046946216a415a915f7409ca65f2053f` | NEW |
| `scripts/docs_edit.py` | `-` | `-` | `-` | `214ccc990e9ef78ca722e4d2cf5bb7630fdf32d2be3ee1932efd5e9704affa3d` | NEW |
| `scripts/docs_reconcile.py` | `-` | `-` | `-` | `ec49c83eeb1389f4ccc51948be386659dbe83f54e7e1a24693dec08855235949` | NEW |
| `scripts/acceptance.py` | `-` | `-` | `-` | `1e8325250af5090ac26048270d96891722106d2c665307124606871f3312ecbc` | NEW |
| `scripts/ea_tick.py` | `PIPER:scripts/cadence_tick.py` | `untracked` | `6c0b9b48c339ac7da6cf9f3b9001182474f5da95106d0a122e522dc361c520f8` | `fc9e3d50711f89cd5923717e10350d9d4529b02b80698401bb72e3ab592bd347` | PORT |
<!-- end of manifest table -->

## What changed, and why

**VERBATIM: `.claude/hooks/_transcript.py`, `.claude/hooks/_lib.sh`, `scripts/job_lock.py`, `scripts/runs_log.py`** (PIPER, origin STEVIE)
Dispatch detection, the hook-field helpers, the run lock and the lock primitive under it. Unchanged: three hooks and the status line must agree on which agents ran, and the tick's lock must be the one already proven.

**`.claude/hooks/_gate.py`** (PORT) EA_* env vars; the roster is read from `context/roster-agents.json`; `caller_agent()` is new and reads Claude Code's own `agent_id`/`agent_type` payload fields, because PIPER's transcript inference names the last agent DISPATCHED, which on the main thread is not the caller. `is_build_machine()` is new (the hostname-bound marker for layer B of protect-architecture).

**`.claude/hooks/_audit.py`** (PORT) Database module and doctor renamed. Otherwise verbatim, including every swallow and the never-cleared-by-success AUDIT-DEGRADED marker.

**`.claude/hooks/require-dispatch.py`** (PORT) Gates `state/proposals`, `state/records`, `state/private` and `output/`, names this system's owners, and treats Claude Code's `agent_id` as proof a dispatch already happened.

**`.claude/hooks/no-cloud.py`** (PORT) Messages re-pointed; strips PowerShell and cmd call operators (`& git push`) before reading the first token, because on Windows the PowerShell tool is the primary shell.

**`.claude/hooks/classify-and-place.py`** (PORT) Classes `private / records / shareable`, key `ea-class`, a declaration pattern that accepts the JSON key form a proposal uses, OAuth files and the build marker treated as machine-managed. The named-list sniffer is kept but switched off in `context/data-classes.json` (six-person roster).

**`.claude/hooks/require-approval.py`** (PORT, cold) Owner mailbox `t.iwaasa@gretabar.com`; egress script names are Phase 3+ names; reads PowerShell commands as well as Bash. `docs_edit.py` is deliberately NOT an egress pattern: blueprint s.1 lists topic, commitment, deadline and completion edits as reversible established operations.

**`.claude/hooks/announce-dispatch.py`** (PORT) Agents under `.claude/agents/`; the separator class written with escapes.

**`.claude/hooks/team-rollcall.py`** (PORT) The solo-versus-dispatched asymmetry kept verbatim. Adds the tick-health line (the fallback if the VS Code extension does not render a statusLine) and the CHANGE-LOG banner.

**`.claude/hooks/statusline-ea.py`** (PORT, from PIPER's `statusline-piper.py`) Label from `context/identity.json`; tick read and rendering moved to `_health.py` so the bar and the roll call cannot disagree.

**`.claude/hooks/validate-on-edit.sh`** (PORT) Routes `.claude/agents`, `.claude/skills` and `.claude/commands` to the contract validator, hooks and context to the guardrail self-test. Every cannot-check branch still exits 2.

**`.claude/settings.json`** (PORT) Every shell gate matches `Bash|PowerShell`; the cold approval gate is narrowed from `.*` to `Bash|PowerShell|mcp__.*`, the only tool names it can ever match. Carve-out gate, browser gate and the prompt-type Agent hook dropped (no HR carve-out, no browser in Phase 1).

**`scripts/ea_db.py`** (PORT, from `piper_db.py`) `connect(read_only)`, `migrate()` under `user_version`, WAL and the people-column allowlist kept. Schema replaced with the register's tables, plus a `proposals` index the plan implies (WREN verifies PAGE's hash against it). A second database, `state/fixtures.db`, is selected by `EA_FIXTURE_MODE=1`.

**`scripts/approvals.py`** (PORT) Names only. `canonical()` is also the hash for Doc edit proposals.

**`scripts/notify_owner.py`** (PORT, from `notify_cass.py`) Liveness only: the tick and the Docs' last successful read. No alarm about open employee work (blueprint s.4, s.6).

**`scripts/validate_agent_contracts.py`** (PORT) `.claude/` paths, roster from `context/roster-agents.json`, an `orchestrator` owner token that survives renaming, and a roster-to-files consistency check.

**`scripts/validate_content_rules.py`** (PORT) Emoji kept; em-dash widened to everything bound for a Doc or for Taylor; HR rules dropped; classes built from integer code points so the file cannot trip its own hook.

**`scripts/validate_guardrails.py`** (PORT) New fixtures for this system's gates, every case's verdict printable, and `--mutation-test`, which removes each gate and proves the self-test notices.

**`scripts/check_vendored.py`** (PORT) Two upstreams, NEW rows, `--rehash`, `--add`.
