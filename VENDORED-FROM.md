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
| `.claude/hooks/_transcript.py` | `PIPER:.claude/hooks/_transcript.py` | `untracked` | `727531fd2915fefcfa58a0ccc6980debd88350e1918a7706ca2631eda5c9646b` | `6078e6e48cba5f5f0c5cb620383fc2d9e82ab03c7f3ceb32b04f2537e17a3cfd` | PORT |
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
| `.claude/hooks/team-rollcall.py` | `PIPER:.claude/hooks/team-rollcall.py` | `untracked` | `f6800761b72db78b1c556001a3f1866741b08570ab21242f25909bc8b81b5bf5` | `465efa8b52526af9a5df819ad8be21c27e09cbb1c83d3aa8d2e559826bf6a155` | PORT |
| `.claude/hooks/statusline-ea.py` | `PIPER:.claude/hooks/statusline-piper.py` | `untracked` | `5066cb7556b7837c58906721d1466c41efe8331455e019fe402c1ce3a26ac1b5` | `7b0efd3cb606d04c620505a3471cb2d17d44249afe74197ff0c4d87baeeda570` | PORT |
| `.claude/hooks/validate-on-edit.sh` | `PIPER:.claude/hooks/validate-on-edit.sh` | `untracked` | `915b7a11e81718da9e18d03a07b742e66ed1a16096b9081d2523d7601d537acd` | `3d3eb2b7bc77a1bbe20f30e978d5d324b91b53263c0931d8b4d149d7e034bffd` | PORT |
| `.claude/settings.json` | `PIPER:.claude/settings.json` | `untracked` | `4a0f8f1882659f951beecdc9437be412b95be38ae32cee4cfd677e6553bffe77` | `136f7c1fa12123307a7cb2f3c8ebab0cae152c318da94b706f6eee8732a88959` | PORT |
| `scripts/ea_db.py` | `PIPER:scripts/piper_db.py` | `untracked` | `1f0a2aa94a78366de4408268bf08dd46e0bd6f4a9c2bf1caa5f6e42029af50cd` | `36375f65b7aa74c13533abeb084198436825dd14849442298a0e8de971b2890d` | PORT |
| `scripts/approvals.py` | `PIPER:scripts/approvals.py` | `untracked` | `6ae22201b737e5723240777a3ac75de183ddaf116b14f97f398324232f5d4214` | `dabda1cc9a0c988f5005862986eedda71924b7657dd8fea385e6972e0681d4f5` | PORT |
| `scripts/notify_owner.py` | `PIPER:scripts/notify_cass.py` | `untracked` | `661fb20f4e154868d699ab00732c632aa8536740ac484f411328956febf37847` | `e91e5d61ea435602d3b96ba5687c36ca756093cd7d42d112f7683d33facc64f4` | PORT |
| `scripts/validate_agent_contracts.py` | `PIPER:scripts/validate_agent_contracts.py` | `untracked` | `fb2892cca02a78f2495ccb78ac1645432ec0e4ced23a1220c6e2bd1c154ae896` | `79e694a8ac597a412a7e4f0f65df63124b45bfcd1fa78ca7ab409422f1c6aa6e` | PORT |
| `scripts/validate_content_rules.py` | `PIPER:scripts/validate_content_rules.py` | `untracked` | `310ad7f6afa5f38be5c18dc27d580fd37005dffdd5551114b15587c3e98fbdc0` | `4ac1fde475bfb47ef9c7e687bf46ef0b2d4c9deb7e70dd8af212564dbc30723b` | PORT |
| `scripts/validate_guardrails.py` | `PIPER:scripts/validate_guardrails.py` | `untracked` | `704b4700e07cc3c26e3650507b73bd7660eb9d01db2216b973fedeaa54c7dfe7` | `3a01eee79cbd223dac0a84bc2a2ec9fc990da4ec870a30ba543da02f5258338c` | PORT |
| `scripts/check_vendored.py` | `PIPER:scripts/check_vendored.py` | `untracked` | `3e9ab0c1894a70989998c8e536331bacb6f722d40ffc0ac0abadd84d5ce646ef` | `38816c2bb00335002c4c93dccc39d95d6620b8b4935b6475adac03eab9f753f5` | PORT |
| `.claude/hooks/_health.py` | `-` | `-` | `-` | `2ab3ed936716efb6b290c479a5e8790e461fa14965ecd2165a81d22e8b7b19ac` | NEW |
| `.claude/hooks/require-delivery-agent.py` | `-` | `-` | `-` | `190205d929fbf92aea96e769fa90b13957a11e20fbb428b1fa00969fc9a68357` | NEW |
| `.claude/hooks/protect-architecture.py` | `-` | `-` | `-` | `d439090dd5f1eb3340c5b26383c401384663f2f78a9269d4aac1cd065c7948fd` | NEW |
| `scripts/register.py` | `-` | `-` | `-` | `caa01bdd12fea9fd53aa87753d31c0e7525eec001f470933ea5558aa112e7e2b` | NEW |
| `scripts/google_creds.py` | `STEVIE:scripts/upload_to_drive.py` | `untracked` | `8501f0e5e2c0f6c5e0b8220ae2a650eb7af453cb413b64666690889f6674f883` | `9edf8952c0912ac2a203685ee23ec5559974dcbb443678d562fe3bec37a3924b` | PORT |
| `scripts/google_auth.py` | `STEVIE:scripts/marketing_report/google_auth.py` | `e3f42d2` | `92c3d715e28338de6aaef8b9c6241f8ac8c1abe14810b6ec3a841a5f1c272f8e` | `bc6115a7feb84c96743b96c71d1c4284ee80f65804f1dc59bd1ab494b03d84c5` | PORT |
| `scripts/docs_read.py` | `-` | `-` | `-` | `7d8a81a3b9a1ccb98a44180afbfb8eea72249b06b6765817bebe19ddfed6590e` | NEW |
| `scripts/link_docs.py` | `-` | `-` | `-` | `90855f7ecdfb52c43fdfa75b290b43f3728525cfdb3fd74549f69c73ec8d20c5` | NEW |
| `scripts/calendar_next.py` | `-` | `-` | `-` | `c3f4a9d7bd0108a926447d6d8297542bb1f3ddc2741243b5ad1b4dd5028c3114` | NEW |
| `scripts/make_fixtures.py` | `-` | `-` | `-` | `756b456e36649fe3b357ff63638ab6480b1aaa64e6b2bb878923c86f26cc2b61` | NEW |
| `tests/test_calendar_next.py` | `-` | `-` | `-` | `39b93a6afe224422e711ce8b14e1edb8c4ba08c99d0544ff214f8f42dce37c22` | NEW |
| `tests/test_docs_read.py` | `-` | `-` | `-` | `eaced801952ec08874cba7972d324fcf9e146dd957cb3541da9c05295e561242` | NEW |
| `scripts/docs_propose.py` | `-` | `-` | `-` | `5caf67bc93a6f62196cec58ef55c22ad0efcbe296291aab91f283b93b161b355` | NEW |
| `scripts/docs_edit.py` | `-` | `-` | `-` | `2918114b463df9c0a56192c2f846dadf027dc98b0e8b83a9c22c4679758d3603` | NEW |
| `scripts/docs_reconcile.py` | `-` | `-` | `-` | `8ae92c49a91167132497725c67a1d29f304c73eaad1f9b7a0bee4054362d74e7` | NEW |
| `scripts/acceptance.py` | `-` | `-` | `-` | `540c99322acb3fa8ccb3e51e1e45f3b2c052c082d17b58074b3cde8c833ba8e4` | NEW |
| `scripts/ea_tick.py` | `PIPER:scripts/cadence_tick.py` | `untracked` | `6c0b9b48c339ac7da6cf9f3b9001182474f5da95106d0a122e522dc361c520f8` | `346d8159621e904f75c2156a1123fec232d3f1d7775ad27d82086bb5d558d5bc` | PORT |
| `scripts/run_ea_tick.ps1` | `PIPER:scripts/run_cadence_tick.ps1` | `untracked` | `d7233a6d93db66768bebbb3ca61591de41356a88a56a0ad92ddbd621d6ddccb2` | `5ec03f6aa2b6196c05ab6c4abaee5125de8c167fd1e17bc3f0457b16bad787fa` | PORT |
| `scripts/schedule_ea_tick.ps1` | `PIPER:scripts/schedule_cadence_tick.ps1` | `untracked` | `6189ca47717bb64d4bb7521b69f166330ddac8939e4a05dd57936f9d2e88ca7e` | `1124899fae5c81fbee7ed096a2a5b4d2de64096a42b947a665dae37e4f47fb79` | PORT |
| `tests/test_review_regressions.py` | `-` | `-` | `-` | `29a18ae6c2d0661c9738e5a7048340e0fb5e2c2ebbfdcb0a97042c7275af1f4b` | NEW |
| `CLAUDE.md` | `PIPER:CLAUDE.md` | `untracked` | `69509762462f6260b6c304ec5d961f08d31b2f470cbfe510528ad2338b4e1110` | `cc6cb6d9fde1c10581ccc65b9e3bfe74f50cc1350a0b81f642feca4c6ea0b412` | PORT |
| `INSTALL.md` | `PIPER:INSTALL.md` | `untracked` | `71494b8f86647305929d26d53569b0a363f6c7dfccb378b744964707821284d1` | `808b65b25ece18b63b50a383e78a35e28e939a60be6aebabd1d66240aba51a2b` | PORT |
| `.claude/commands/NAME.md` | `PIPER:commands/piper.md` | `untracked` | `4179aeadf432a83d0059901d3e41f644f6b0046b191e14fe6982a326d0b007a8` | `79c7f435d8e3ac650a8eb23f14219736202df87509e9585646d2288638d69edb` | PORT |
| `.claude/commands/boi.md` | `PIPER:commands/boi.md` | `untracked` | `d11a8b7ddf7f017122bf5306b4e6af5012bb235953f9279ef83651d3595851f1` | `1dc9c68c6710eb109cffda37e8d0f0ed51f44f83a59f0314a4759095e7c95d6f` | PORT |
| `.claude/commands/morning.md` | `PIPER:commands/morning.md` | `untracked` | `c0d593c9f1932adb00b2d7b2b13c31e58721febbd901a1ae22c515ee1de63762` | `186ccb388079a976b27fd387382e1367dd41858ad1753e6278d5a6fb6401e10c` | PORT |
| `.claude/skills/reality-checker/SKILL.md` | `PIPER:skills/reality-checker/SKILL.md` | `untracked` | `0ff3480d2a25fa7bbb04d75411d4f1c72cb702f3a4ed5fb1ec4c894467199c13` | `1d64153b24f6677d800738fbd6cdb19981f1d252328742dd956ced4a342981cd` | PORT |
| `.claude/skills/morning-brief/SKILL.md` | `PIPER:skills/morning-brief/SKILL.md` | `untracked` | `64e40682763462be7e357b3cde785fd8d6b8b4ddc7691780c872a9107b238517` | `3ecf105eb88cfe0480cca8d0db9844eaea808f9c4ff05a3261396f5a62d49c5b` | PORT |
| `.claude/agents/hugo.md` | `PIPER:agents/otis.md` | `untracked` | `2dd4fffbefa433f9b353563625416c2212656186b125357e993d8ad5f3d7730d` | `12393060ce224e4729fdfd1472ac37b833a9d8f55f6effc55a6fd371fffbd05d` | PORT |
| `.claude/agents/wren.md` | `PIPER:agents/vera.md` | `untracked` | `cfc9ac81fb6b823efdf42c7163b4b445e8afa2a6d0b5e56f330967b380a5c3e7` | `18f6d1d7e03d8860ba09ca9ea3c5eb882c1c4a0c96339d68a4e3868a6bfbc5ee` | PORT |
| `docs/PRIVACY.md` | `PIPER:docs/PRIVACY.md` | `untracked` | `88a7f85fbcd43959f21459ae65f5d64eddccd197e5c5f36f3d85f94ef68d7d91` | `a82f4333385659ed8775434959056fc283263fa74a0ce92585995cff08b9695e` | PORT |
| `scripts/ea_doctor.py` | `PIPER:scripts/piper_doctor.py` | `untracked` | `122f92ab171b0e98e6dbd438d864c030f450bc9eed9035eccb5a3d29a5b156df` | `0a419f2cfa75f4f04f8025a11b94e5a9fe50c30eecc096c7499ccca11389fcc9` | PORT |
| `scripts/build_ea_kit.py` | `PIPER:scripts/build_piper_kit.py` | `untracked` | `0080c36bd42134f51a424dc84fa8b4a2054f56505b0648d858740edb1d6961a5` | `6bc50423697154d04667ee363e1a3bb9f4f87b22593ce2e66ac931e5bc8138c5` | PORT |
| `scripts/export_ledger.py` | `PIPER:scripts/export_ledger.py` | `untracked` | `7ec4a5b24c17a2acf3fca35b96d4a8f721d451948244a3623d0b1b00616b81cb` | `ec6cd3f362aa2b609cf5721f9e926d382e0b91a978322b1be06c641e98633bac` | PORT |
| `.gitignore` | `PIPER:.gitignore` | `untracked` | `367e93e20e9ac36fed36e3ac3b044098f0d339a4ea6c4fa955822304d3a8aff1` | `6efcb252c9193a56ce951df6daed0ef43a8b79d766631c0420ca3182070dcd28` | PORT |
| `.env.example` | `PIPER:.env.example` | `untracked` | `1e43694bb0ba53d1daeb0a8bb1874f29a5307e3148619fef2e150f1409ee4f2e` | `25e301fba8882b549f7bafa132f9da665a5eed13b3d88fe25d9c9726eba45dfd` | PORT |
| `requirements.txt` | `PIPER:requirements.txt` | `untracked` | `a0cb47cff08849bb572c4381836da9c07c71a4874d1646db622688b304ca47f4` | `15a2869787f5a6a48f9a7e0d7cf2ce26eb13876543e88889ea4a59c46ca4a4b2` | PORT |
| `context/data-classes.json` | `PIPER:context/data-classes.json` | `untracked` | `2ca484126dab62a834c7b813e8538970c9ad72734190542d8199e41e237f91a7` | `e1b337310f6f003bd8872b7c15d8371a9e1a0c36efd3ed073e5998e50049215a` | PORT |
| `context/systems.json` | `PIPER:context/systems.json` | `untracked` | `85e907222296390622572c0d1f32549f9e5af2e9586a92784f646d807a7bbaa6` | `d8afc99f011c67cefc920e64fa80fc31a75996c39c2e0f9286865468d91a7dfd` | PORT |
| `.claude/agents/reed.md` | `-` | `-` | `-` | `44aaf9f4c85c7294f0d02cc5db2337ddb892997b5e7f151b03cb597ebcb3e7d7` | NEW |
| `.claude/agents/page.md` | `-` | `-` | `-` | `e1d1c514cf9e9cf0a02198cc50f585633631c4890767f04940c23e0ffc2fa98b` | NEW |
| `.claude/commands/add.md` | `-` | `-` | `-` | `732629e92a23544e3d6974520c5202e4b08cbd6ffaa8d7fb87005e28626c17a5` | NEW |
| `.claude/commands/owe.md` | `-` | `-` | `-` | `3e1bed7883e2a1986f55ad0fce98463f9fe348fb67d67a8d0bced59bb5d77fea` | NEW |
| `.claude/skills/capture-rules/SKILL.md` | `-` | `-` | `-` | `546cc0a9f5c7c0a0b062ad94b39343a699c52932586c566acf679cbab295ead3` | NEW |
| `.claude/skills/doc-editor/SKILL.md` | `-` | `-` | `-` | `e797d5fb9f90eaf5ba3004689c24e55ef3ff1a35b39a78bc330b3bc49572ec70` | NEW |
| `.claude/skills/delivery-gate/SKILL.md` | `-` | `-` | `-` | `7eab9d5ccd6b0ec3a31245ac510f6b31f053fcf8039d7957b694cdaa976af575` | NEW |
| `docs/DEVIATIONS.md` | `-` | `-` | `-` | `37e72205c8f1ee8973e0609797dcb52571f78723f8f69021eebb7b7242cffc68` | NEW |
| `docs/OPEN-QUESTIONS.md` | `-` | `-` | `-` | `1b814c433b1db13bb6f1629423bc20bbe4494a4631d28abec23a587ed8d2df00` | NEW |
| `context/identity.json` | `-` | `-` | `-` | `6e21785ed016cec904e7943ceea081e43ff4e1d022decfee4825ad74f77e062f` | NEW |
| `context/roster.json` | `-` | `-` | `-` | `b673648ee3f958762e03c5d4a94efd7bc44c9f68737e03ee77b9e8b9be72f9ee` | NEW |
| `context/roster-agents.json` | `-` | `-` | `-` | `de25405f4b43a0b78cf7ed61ed012bba264890039d011d790609564466ea1e84` | NEW |
| `context/architecture/blueprint.md` | `-` | `-` | `-` | `937d367beb8214d42f564f4ae37e008e2acfa801fd8057d1074899fc34492977` | NEW |
| `context/architecture/CHANGE-LOG.md` | `-` | `-` | `-` | `b60339ca1f134dc56bd2a17e77cfd043a47c10b177a813946657029e010dd5d4` | NEW |
| `context/architecture/deviations.json` | `-` | `-` | `-` | `1e9b0a1e6ca83c9e66edc82b7e6a3fed1538eca7a285d85d2c3620ebd803cb76` | NEW |
| `.gitattributes` | `-` | `-` | `-` | `efc2b1dbd43d2b07680511836c9869bd99e450910cda0a4fe257954271f1c246` | NEW |
| `tests/__init__.py` | `-` | `-` | `-` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | NEW |
| `tests/fixtures/kaed_fixture_document.json` | `-` | `-` | `-` | `23699f79c4dd951d76cf44b9872f4d3faa2b0eb45b151b4e4d9fe941342f642b` | NEW |
| `tests/fixtures/kaed_section_map.json` | `-` | `-` | `-` | `74b916c5d60e1705d12313182af5df84d2921196dd17d6019865b0fb4782a110` | NEW |
| `.claude/hooks/_activity.py` | `-` | `-` | `-` | `597f775c8500fd6a2cc47a28dcd706390f4c6f59549b7b29c37869d54b4b9940` | NEW |
| `tests/test_acceptance_preflight.py` | `-` | `-` | `-` | `cd37e0cc22207cbdac6763ce7f63dfcd1e3bf5c0532e8099c51e5faf1e5b9a46` | NEW |
<!-- end of manifest table -->

## What changed, and why

**VERBATIM: `.claude/hooks/_lib.sh`, `scripts/job_lock.py`, `scripts/runs_log.py`** (PIPER, origin STEVIE)
The hook-field helpers, the run lock and the lock primitive under it. Unchanged: the tick's lock must be the one already proven.

**`.claude/hooks/_transcript.py`** (PORT since 2026-10-01; was VERBATIM) Three changes, all worth taking upstream, because STEVIE and PIPER carry the identical file (same sha256) and the same defects. (1) A slash-command row is a turn boundary. Claude Code records `/add ...` as a user row holding only command blocks, followed by an isMeta expansion; the vendored parser stripped those blocks, found nothing typed, and walked on to the last PLAIN message. So for someone who works in slash commands, the roll call after `/morning` named the previous `/add`'s agents, and require-dispatch.py let a second `/add`'s solo write through because the first one had dispatched (both observed against the committed code). (2) TurnContext also carries the turn's main-thread tool uses and its unparseable-line count, collected in the same backwards pass, so the roll call decides "did this turn write?" from the same walk that names its roster. (3) A compaction's summary row (`isCompactSummary`) is not a turn boundary: compaction appends to the same file, and a mid-turn compaction used to hide everything the turn did before it.

**`.claude/hooks/_gate.py`** (PORT) EA_* env vars; the roster is read from `context/roster-agents.json`; `caller_agent()` is new and reads Claude Code's own `agent_id`/`agent_type` payload fields, because PIPER's transcript inference names the last agent DISPATCHED, which on the main thread is not the caller. `is_build_machine()` is new (the hostname-bound marker for layer B of protect-architecture).

**`.claude/hooks/_audit.py`** (PORT) Database module and doctor renamed. Otherwise verbatim, including every swallow and the never-cleared-by-success AUDIT-DEGRADED marker.

**`.claude/hooks/require-dispatch.py`** (PORT) Gates `state/proposals`, `state/records`, `state/private` and `output/`, names this system's owners, and treats Claude Code's `agent_id` as proof a dispatch already happened.

**`.claude/hooks/no-cloud.py`** (PORT) Messages re-pointed; strips PowerShell and cmd call operators (`& git push`) before reading the first token, because on Windows the PowerShell tool is the primary shell.

**`.claude/hooks/classify-and-place.py`** (PORT) Classes `private / records / shareable`, key `ea-class`, a declaration pattern that accepts the JSON key form a proposal uses, OAuth files and the build marker treated as machine-managed. The named-list sniffer is kept but switched off in `context/data-classes.json` (six-person roster).

**`.claude/hooks/require-approval.py`** (PORT, cold) Owner mailbox `t.iwaasa@gretabar.com`; egress script names are Phase 3+ names; reads PowerShell commands as well as Bash. `docs_edit.py` is deliberately NOT an egress pattern: blueprint s.1 lists topic, commitment, deadline and completion edits as reversible established operations.

**`.claude/hooks/announce-dispatch.py`** (PORT) Agents under `.claude/agents/`; the separator class written with escapes.

**`.claude/hooks/team-rollcall.py`** (PORT) The solo-versus-dispatched asymmetry kept verbatim. Adds the tick-health line (the fallback if the VS Code extension does not render a statusLine) and the CHANGE-LOG banner. The SOLO block fires only when a solo turn wrote or changed something; a solo turn that only read gets the one line `TEAM  |  read only, nothing written`, because /owe and /morning are dispatch-free by design and an alarm on every morning screen trains Taylor to skip it. The verdict comes from the new `_activity.py`, and an unreadable turn is UNVERIFIED, never the quiet line.

**`.claude/hooks/statusline-ea.py`** (PORT, from PIPER's `statusline-piper.py`) Label from `context/identity.json`; tick read and rendering moved to `_health.py` so the bar and the roll call cannot disagree. Shows `read only` where the roll call shows the quiet line, from the same `_activity.py` verdict; cache format 2, keyed on both parser files.

**`.claude/hooks/validate-on-edit.sh`** (PORT) Routes `.claude/agents`, `.claude/skills` and `.claude/commands` to the contract validator, hooks and context to the guardrail self-test. Every cannot-check branch still exits 2.

**`.claude/settings.json`** (PORT) Every shell gate matches `Bash|PowerShell`; the cold approval gate is narrowed from `.*` to `Bash|PowerShell|mcp__.*`, the only tool names it can ever match. Carve-out gate, browser gate and the prompt-type Agent hook dropped (no HR carve-out, no browser in Phase 1).

**`scripts/ea_db.py`** (PORT, from `piper_db.py`) `connect(read_only)`, `migrate()` under `user_version`, WAL and the people-column allowlist kept. Schema replaced with the register's tables, plus a `proposals` index the plan implies (WREN verifies PAGE's hash against it). A second database, `state/fixtures.db`, is selected by `EA_FIXTURE_MODE=1`.

**`scripts/approvals.py`** (PORT) Names only. `canonical()` is also the hash for Doc edit proposals.

**`scripts/notify_owner.py`** (PORT, from `notify_cass.py`) Liveness only: the tick and the Docs' last successful read. No alarm about open employee work (blueprint s.4, s.6).

**`scripts/validate_agent_contracts.py`** (PORT) `.claude/` paths, roster from `context/roster-agents.json`, an `orchestrator` owner token that survives renaming, and a roster-to-files consistency check.

**`scripts/validate_content_rules.py`** (PORT) Emoji kept; em-dash widened to everything bound for a Doc or for Taylor; HR rules dropped; classes built from integer code points so the file cannot trip its own hook.

**`scripts/validate_guardrails.py`** (PORT) New fixtures for this system's gates, every case's verdict printable, and `--mutation-test`, which removes each gate and proves the self-test notices. The roll call is a gate here too: one fixture per outcome, and one mutation per outcome, each required to turn its own fixture red.

**`scripts/check_vendored.py`** (PORT) Two upstreams, NEW rows, `--rehash`, `--add`.

**`scripts/google_creds.py`** (PORT, from STEVIE `scripts/upload_to_drive.py` `load_credentials`) One `load_credentials(scopes)`; paths from `EA_ROOT/state/` only; both token shapes; scopes checked before any network call; refreshed per process and never written back.

**`scripts/google_auth.py`** (PORT, from STEVIE `scripts/marketing_report/google_auth.py`) The installed-app consent kept; login hint from `context/identity.json`; granted scopes checked after consent; `--check` mode. Not run on the build machine.

**`scripts/ea_tick.py`** (PORT, from `cadence_tick.py`) The frame kept (lock across the run, heartbeat only when earned, exit codes, dry run on an in-memory copy); the body replaced with read-only reconciliation and Calendar refresh; fixture ticks on their own lock and job name.

**`scripts/run_ea_tick.ps1`, `scripts/schedule_ea_tick.ps1`** (PORT) The outside-the-process exit watch, the alarm, the append-not-truncate log and the battery flags kept; `-Live` dropped (no send path); task `EA-Tick` at 07:00.

**`scripts/ea_doctor.py`** (PORT, from `piper_doctor.py`) Google, Docs, Calendar, the build marker and D-1 instead of Docebo and PUSH.

**`scripts/build_ea_kit.py`** (PORT, from `build_piper_kit.py`) `.claude/` layout; NEVER_COPY adds the Google client and token, the build marker and the fixture database; the gate adds Google's secret shapes; `docs/acceptance/` stays behind.

**`scripts/export_ledger.py`** (PORT) A register snapshot; names make it `records`, so it may only land under `state/records/`.

**`CLAUDE.md`, `INSTALL.md`** (PORT) PIPER's structure (rules first, enforcement named, the privacy paragraph) re-written for this system; CLAUDE.md is distilled and points at blueprint sections instead of importing them.

**`.claude/commands/NAME.md`, `boi.md`, `morning.md`; skills `reality-checker`, `morning-brief`; agents `hugo.md` (from OTIS), `wren.md` (from VERA's delivery role); `docs/PRIVACY.md`** (PORT) Lanes READ and CAPTURE replace PIPER's FAST/STANDARD/FULL; PRIVACY keeps "A Claude Enterprise seat is not a privacy control" verbatim.

**`.gitignore`, `.env.example`, `requirements.txt`, `context/data-classes.json`, `context/systems.json`** (PORT) Re-cut for this system: Google credentials by name, `tzdata` added, Playwright and requests dropped, three data classes, Google hosts only.

**Not recorded here:** `README.md`, `docs/FOR-TAYLOR.md`, `docs/PLAYBOOK.md` and `docs/FIRST-PROMPT.md` are ANNIE's, written in parallel and owned by her, so their hashes would go stale every time she edits. `docs/acceptance/` is generated evidence, regenerated by `scripts/acceptance.py`.
