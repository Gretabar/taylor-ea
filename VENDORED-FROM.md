# Vendored from PIPER and STEVIE

Every file in this repo that came from `C:\PIPER` or `C:\Users\kells\STEVIE`, what
was done to it, and the exact bytes it came from. Files written new for this
system are listed too, as NEW, so the table is a complete inventory of the
framework.

**Why this file exists.** Standalone means it drifts. The moment a fix lands in a
shared file on one machine, the other machine does not have it and nothing says
so. Copies are fine; UNDOCUMENTED copies are how one parser ends up in four
places, three of them subtly different.

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
| `.claude/hooks/_transcript.py` | `PIPER:.claude/hooks/_transcript.py` | `untracked` | `727531fd2915fefcfa58a0ccc6980debd88350e1918a7706ca2631eda5c9646b` | `2937bbfcb7fb983546c56e2be1c014cbfc4eed8d62d3361803bb17ade034a2c8` | PORT |
| `.claude/hooks/_lib.sh` | `PIPER:.claude/hooks/_lib.sh` | `untracked` | `19e325f96a7904e4acf853be2b901c3de165c0ffe5fdcf992e190c3106368797` | `f4ef2af318a3e08878af557dd6ce0cdf4d574b02869e70022ba8b0d27fdb2453` | PORT |
| `scripts/job_lock.py` | `PIPER:scripts/job_lock.py` | `untracked` | `e81ceffd6c0d3811a5d4567c0241fc0cdde83ab940836caeacf37694375b067a` | `0b2eb2aba9ae413723a119b83c4bda4c21f63abde35fbb05933cf991e8970227` | PORT |
| `scripts/runs_log.py` | `PIPER:scripts/runs_log.py` | `untracked` | `03412631208eedacd5cf2649a602fbfaafaf652359ea4d34a527c22eb4f90936` | `6c6cb9466f2894c13300123ba808a95de6c6950d342395716e8c25406389e43b` | PORT |
| `.claude/hooks/_gate.py` | `PIPER:.claude/hooks/_gate.py` | `untracked` | `27f386c1a3b7ab9ebeba0d21baf6f26b3f5bfbf3be64b4fbdd96140b522f1dac` | `4a33af705952d7514f8efa70703afc31426d9658fe6fd45a8205fc828ad518a1` | PORT |
| `.claude/hooks/_audit.py` | `PIPER:.claude/hooks/_audit.py` | `untracked` | `f53c94b79c114c443ca3fa903417ab651d4508378c70cc754d0b9856dbaf62ed` | `8ec6c878a8b2899f82834a8b25e05f6fb6d5291ac82df44601fd0a822e626a96` | PORT |
| `.claude/hooks/require-dispatch.py` | `PIPER:.claude/hooks/require-dispatch.py` | `untracked` | `e0fe3e67171149bdc77e9184127350a2e62748feff9ab4b0234df4178568ae8e` | `34bf7563b94443b67b95d833606c9ac348f472e589530219418e18fe34b33128` | PORT |
| `.claude/hooks/no-cloud.py` | `PIPER:.claude/hooks/no-cloud.py` | `untracked` | `a9b74363b4ebdc909575c6beae03f17c80e43d8fd6fff4864e46890a5503633b` | `fd386870c9a39cd5a58551b2c828eae4a73c433a26505a70e91f85ecfb381d98` | PORT |
| `.claude/hooks/classify-and-place.py` | `PIPER:.claude/hooks/classify-and-place.py` | `untracked` | `48115417f63102f1248a85477c23c3a8417aad0d2a65734a2241484dcd32f313` | `4dc538e7908e328d1a33dd3199a78efdd4a7c1cf1b5a0136a708a3797d2c6699` | PORT |
| `.claude/hooks/require-approval.py` | `PIPER:.claude/hooks/require-approval.py` | `untracked` | `543e4c7c545a6964daf846f902766686a54c871b0e79183408e65648912104d1` | `a39007cb0d916f53f4ce41d80aa266924ab343214dc44818b84de40f375db8c1` | PORT |
| `.claude/hooks/announce-dispatch.py` | `PIPER:.claude/hooks/announce-dispatch.py` | `untracked` | `9a4b32733759f90684d0689a925979642114229548ff31a6313895977adcfe37` | `3580aa921a4c77dae93b77e2fab04ab40562e0569cc1a6784208e101f8ddfc9f` | PORT |
| `.claude/hooks/team-rollcall.py` | `PIPER:.claude/hooks/team-rollcall.py` | `untracked` | `f6800761b72db78b1c556001a3f1866741b08570ab21242f25909bc8b81b5bf5` | `23c2bf5baba961074176c4a1edebf568ab0ddd4c0f812c0cee63da8acca28440` | PORT |
| `.claude/hooks/statusline-ea.py` | `PIPER:.claude/hooks/statusline-piper.py` | `untracked` | `5066cb7556b7837c58906721d1466c41efe8331455e019fe402c1ce3a26ac1b5` | `0bc88cab2524c8221d0862a1ec3e845c5bfa8e65e2b0ba3e6ef70ec61fc71370` | PORT |
| `.claude/hooks/validate-on-edit.sh` | `PIPER:.claude/hooks/validate-on-edit.sh` | `untracked` | `915b7a11e81718da9e18d03a07b742e66ed1a16096b9081d2523d7601d537acd` | `a35db937286d9229d50a45be2312a0058884944d49efe40cee9e5dfaeb67db12` | PORT |
| `.claude/settings.json` | `PIPER:.claude/settings.json` | `untracked` | `4a0f8f1882659f951beecdc9437be412b95be38ae32cee4cfd677e6553bffe77` | `4f0feeea8841d8de1ec378705f9841be4b5287f376ed1009c376212e3827cdc0` | PORT |
| `scripts/ea_db.py` | `PIPER:scripts/piper_db.py` | `untracked` | `1f0a2aa94a78366de4408268bf08dd46e0bd6f4a9c2bf1caa5f6e42029af50cd` | `752eb1f26663bf025156955d61c499cdae0adef1d185095f706b4308b5b571e1` | PORT |
| `scripts/approvals.py` | `PIPER:scripts/approvals.py` | `untracked` | `6ae22201b737e5723240777a3ac75de183ddaf116b14f97f398324232f5d4214` | `dabda1cc9a0c988f5005862986eedda71924b7657dd8fea385e6972e0681d4f5` | PORT |
| `scripts/notify_owner.py` | `PIPER:scripts/notify_cass.py` | `untracked` | `661fb20f4e154868d699ab00732c632aa8536740ac484f411328956febf37847` | `4a65dda3021544c337da7a26e5f1a957ab4909430ad6004588bbe17e7cea27f4` | PORT |
| `scripts/validate_agent_contracts.py` | `PIPER:scripts/validate_agent_contracts.py` | `untracked` | `fb2892cca02a78f2495ccb78ac1645432ec0e4ced23a1220c6e2bd1c154ae896` | `2828074c6a378b5b1a338ecd61c93962d9626efbafc0d3d5bfccd86e8570a2a2` | PORT |
| `scripts/validate_content_rules.py` | `PIPER:scripts/validate_content_rules.py` | `untracked` | `310ad7f6afa5f38be5c18dc27d580fd37005dffdd5551114b15587c3e98fbdc0` | `f35be2d0ec52e5e74dbc42df00b32705c8af60915e587c053d3bff0ff7c48bdb` | PORT |
| `scripts/validate_guardrails.py` | `PIPER:scripts/validate_guardrails.py` | `untracked` | `704b4700e07cc3c26e3650507b73bd7660eb9d01db2216b973fedeaa54c7dfe7` | `6ceaac59e159ae18d88e4b0f62e80b37971e6f44fec23d36587ba5898100be60` | PORT |
| `scripts/check_vendored.py` | `PIPER:scripts/check_vendored.py` | `untracked` | `3e9ab0c1894a70989998c8e536331bacb6f722d40ffc0ac0abadd84d5ce646ef` | `d2811042a9205d770509fad36ead46f34d7d23fb53e4d6b42db87820a0c84356` | PORT |
| `.claude/hooks/_health.py` | `-` | `-` | `-` | `b2cb721f186ec9044928b1615d051e80002fd7ae5e179b8a0c2222a473360462` | NEW |
| `.claude/hooks/require-delivery-agent.py` | `-` | `-` | `-` | `6ce4d5ed64fd38d2d9c59bcc9d002d05ce19a3c93b19f8de075d71e903c7d311` | NEW |
| `.claude/hooks/protect-architecture.py` | `-` | `-` | `-` | `43c86739c47b8a87852d441866c86d7dd9068bc95349cae3062f67ad69d44125` | NEW |
| `scripts/register.py` | `-` | `-` | `-` | `70bb408943226093ef2c25f06d2bb09ee2d2fdad5535ee143acbc7dd1da25702` | NEW |
| `scripts/google_creds.py` | `STEVIE:scripts/upload_to_drive.py` | `untracked` | `8501f0e5e2c0f6c5e0b8220ae2a650eb7af453cb413b64666690889f6674f883` | `527c1777f3e86dfa65c4006d8e5a8cdae69427564c3dd1ce75fef66d8856542d` | PORT |
| `scripts/google_auth.py` | `STEVIE:scripts/marketing_report/google_auth.py` | `e3f42d2` | `92c3d715e28338de6aaef8b9c6241f8ac8c1abe14810b6ec3a841a5f1c272f8e` | `bc6115a7feb84c96743b96c71d1c4284ee80f65804f1dc59bd1ab494b03d84c5` | PORT |
| `scripts/docs_read.py` | `-` | `-` | `-` | `7d8a81a3b9a1ccb98a44180afbfb8eea72249b06b6765817bebe19ddfed6590e` | NEW |
| `scripts/link_docs.py` | `-` | `-` | `-` | `90855f7ecdfb52c43fdfa75b290b43f3728525cfdb3fd74549f69c73ec8d20c5` | NEW |
| `scripts/calendar_next.py` | `-` | `-` | `-` | `c3f4a9d7bd0108a926447d6d8297542bb1f3ddc2741243b5ad1b4dd5028c3114` | NEW |
| `scripts/make_fixtures.py` | `-` | `-` | `-` | `60760db39629dc49b9595294711dcb59b33a21b051e756184ba12d645a5b106d` | NEW |
| `tests/test_calendar_next.py` | `-` | `-` | `-` | `39b93a6afe224422e711ce8b14e1edb8c4ba08c99d0544ff214f8f42dce37c22` | NEW |
| `tests/test_docs_read.py` | `-` | `-` | `-` | `eaced801952ec08874cba7972d324fcf9e146dd957cb3541da9c05295e561242` | NEW |
| `scripts/docs_propose.py` | `-` | `-` | `-` | `d8c65a8a6179340d3865c0afe855e4f36b3e095eed3ad49f2d315c2822ff2d98` | NEW |
| `scripts/docs_edit.py` | `-` | `-` | `-` | `61c53a700a24f2d467da2056457ca0175d79a8e4506c60ca05ccb87f93ed4cce` | NEW |
| `scripts/docs_reconcile.py` | `-` | `-` | `-` | `8ae92c49a91167132497725c67a1d29f304c73eaad1f9b7a0bee4054362d74e7` | NEW |
| `scripts/acceptance.py` | `-` | `-` | `-` | `eceb85613a87ea335eb0dfa3d0153ffac206a9b336c853c8c890282d83d842a7` | NEW |
| `scripts/ea_tick.py` | `PIPER:scripts/cadence_tick.py` | `untracked` | `6c0b9b48c339ac7da6cf9f3b9001182474f5da95106d0a122e522dc361c520f8` | `d48bbf97bb791f75ac304a1f124426889d59d49f36b156c9ce98f697830e000e` | PORT |
| `scripts/run_ea_tick.ps1` | `PIPER:scripts/run_cadence_tick.ps1` | `untracked` | `d7233a6d93db66768bebbb3ca61591de41356a88a56a0ad92ddbd621d6ddccb2` | `712efb60739d2511a96ce97a291504bd8f3828e8412d284a87d6e4ab2488de75` | PORT |
| `scripts/schedule_ea_tick.ps1` | `PIPER:scripts/schedule_cadence_tick.ps1` | `untracked` | `6189ca47717bb64d4bb7521b69f166330ddac8939e4a05dd57936f9d2e88ca7e` | `38035578522913ed67b347a8a52aee9f79ac874e46c3511debba4c61158415a0` | PORT |
| `tests/test_review_regressions.py` | `-` | `-` | `-` | `29a18ae6c2d0661c9738e5a7048340e0fb5e2c2ebbfdcb0a97042c7275af1f4b` | NEW |
| `CLAUDE.md` | `PIPER:CLAUDE.md` | `untracked` | `69509762462f6260b6c304ec5d961f08d31b2f470cbfe510528ad2338b4e1110` | `eeb911155a0ae4cd7a42332a23877971f34e10a18fcaf082060be7002b610807` | PORT |
| `INSTALL.md` | `PIPER:INSTALL.md` | `untracked` | `71494b8f86647305929d26d53569b0a363f6c7dfccb378b744964707821284d1` | `2b42b2605748fc95e52b8d704068ea00e8cb7af353deb72c42f68a6833d67a63` | PORT |
| `.claude/commands/NAME.md` | `PIPER:commands/piper.md` | `untracked` | `4179aeadf432a83d0059901d3e41f644f6b0046b191e14fe6982a326d0b007a8` | `7d754be107982fa5fe61843a862b9022b13ab789d592cd30eeb5a084a25ff9f7` | PORT |
| `.claude/commands/boi.md` | `PIPER:commands/boi.md` | `untracked` | `d11a8b7ddf7f017122bf5306b4e6af5012bb235953f9279ef83651d3595851f1` | `1dc9c68c6710eb109cffda37e8d0f0ed51f44f83a59f0314a4759095e7c95d6f` | PORT |
| `.claude/commands/morning.md` | `PIPER:commands/morning.md` | `untracked` | `c0d593c9f1932adb00b2d7b2b13c31e58721febbd901a1ae22c515ee1de63762` | `186ccb388079a976b27fd387382e1367dd41858ad1753e6278d5a6fb6401e10c` | PORT |
| `.claude/skills/reality-checker/SKILL.md` | `PIPER:skills/reality-checker/SKILL.md` | `untracked` | `0ff3480d2a25fa7bbb04d75411d4f1c72cb702f3a4ed5fb1ec4c894467199c13` | `db51cde8af1e0ce7165f6f09da98d896e9dbf324add26b801942326c513649a3` | PORT |
| `.claude/skills/morning-brief/SKILL.md` | `PIPER:skills/morning-brief/SKILL.md` | `untracked` | `64e40682763462be7e357b3cde785fd8d6b8b4ddc7691780c872a9107b238517` | `fac0801066b9a79b5d421039041bc60a8526b5f2ad35b830d6a9ee9c8b721014` | PORT |
| `.claude/agents/hugo.md` | `PIPER:agents/otis.md` | `untracked` | `2dd4fffbefa433f9b353563625416c2212656186b125357e993d8ad5f3d7730d` | `43c4a6aeeb2a0231fe78e537ddbcd2bfaa9756530ac7ddee21a0d030b010a4d8` | PORT |
| `.claude/agents/wren.md` | `PIPER:agents/vera.md` | `untracked` | `cfc9ac81fb6b823efdf42c7163b4b445e8afa2a6d0b5e56f330967b380a5c3e7` | `e719b1e58e591804b28713ddd8c2a9067368c82f586398d9f8a5775b69d80ec2` | PORT |
| `docs/PRIVACY.md` | `PIPER:docs/PRIVACY.md` | `untracked` | `88a7f85fbcd43959f21459ae65f5d64eddccd197e5c5f36f3d85f94ef68d7d91` | `c5ee100f2ba7ecdb7fe26c482765c0deec3ba149cfe7d5d35b01fd33a013ec3c` | PORT |
| `scripts/ea_doctor.py` | `PIPER:scripts/piper_doctor.py` | `untracked` | `122f92ab171b0e98e6dbd438d864c030f450bc9eed9035eccb5a3d29a5b156df` | `5f122fbd1aeab160ac21f6949f459c5fa3f021170678be033e528ec63f4cddaf` | PORT |
| `scripts/build_ea_kit.py` | `PIPER:scripts/build_piper_kit.py` | `untracked` | `0080c36bd42134f51a424dc84fa8b4a2054f56505b0648d858740edb1d6961a5` | `6bc50423697154d04667ee363e1a3bb9f4f87b22593ce2e66ac931e5bc8138c5` | PORT |
| `scripts/export_ledger.py` | `PIPER:scripts/export_ledger.py` | `untracked` | `7ec4a5b24c17a2acf3fca35b96d4a8f721d451948244a3623d0b1b00616b81cb` | `ec6cd3f362aa2b609cf5721f9e926d382e0b91a978322b1be06c641e98633bac` | PORT |
| `.gitignore` | `PIPER:.gitignore` | `untracked` | `367e93e20e9ac36fed36e3ac3b044098f0d339a4ea6c4fa955822304d3a8aff1` | `d4dc70d812a7f8b80ec7f0548739ff03d95580e247c40e7172efcc0cda16872c` | PORT |
| `.env.example` | `PIPER:.env.example` | `untracked` | `1e43694bb0ba53d1daeb0a8bb1874f29a5307e3148619fef2e150f1409ee4f2e` | `25e301fba8882b549f7bafa132f9da665a5eed13b3d88fe25d9c9726eba45dfd` | PORT |
| `requirements.txt` | `PIPER:requirements.txt` | `untracked` | `a0cb47cff08849bb572c4381836da9c07c71a4874d1646db622688b304ca47f4` | `15a2869787f5a6a48f9a7e0d7cf2ce26eb13876543e88889ea4a59c46ca4a4b2` | PORT |
| `context/data-classes.json` | `PIPER:context/data-classes.json` | `untracked` | `2ca484126dab62a834c7b813e8538970c9ad72734190542d8199e41e237f91a7` | `2b46bb15dc8ba5b3800a52fb980cc615001da042b2cfde5c0f81dbe540ea498c` | PORT |
| `context/systems.json` | `PIPER:context/systems.json` | `untracked` | `85e907222296390622572c0d1f32549f9e5af2e9586a92784f646d807a7bbaa6` | `eaa4656ff54a4d0eb2daa596701741d46865172263b94fa47d61add1111b5e17` | PORT |
| `.claude/agents/reed.md` | `-` | `-` | `-` | `3e6656b57e57555820e370ff2220ee24f82b9a7827549ef561dc786075a66fdc` | NEW |
| `.claude/agents/page.md` | `-` | `-` | `-` | `e72606654e7efb69309f29fab3673293b53d7cf69c1a6c49a199f5d6bf62a1f5` | NEW |
| `.claude/commands/add.md` | `-` | `-` | `-` | `532d2ed48c7bd0aa81bb03b8cf4f1aea54e2d0c3f54eb9dd698b877626d1739e` | NEW |
| `.claude/commands/owe.md` | `-` | `-` | `-` | `3e1bed7883e2a1986f55ad0fce98463f9fe348fb67d67a8d0bced59bb5d77fea` | NEW |
| `.claude/skills/capture-rules/SKILL.md` | `-` | `-` | `-` | `a99ca173584ec5abf156c76e76a07d54688e5319dec4e9d57c95e574a1ce3b26` | NEW |
| `.claude/skills/doc-editor/SKILL.md` | `-` | `-` | `-` | `8df61650309505d149e77e8ce656a05f1ca1d0e708d9961f7217c8285c15418e` | NEW |
| `.claude/skills/delivery-gate/SKILL.md` | `-` | `-` | `-` | `968d00aebdd6e018dfb46cc1d5bc901042e9b077cf83d33083c99aa4dd4cbbf3` | NEW |
| `docs/DEVIATIONS.md` | `-` | `-` | `-` | `c2b903e64871dc0f89cd60232a112d71c73ab1fd45598ecac496a5848459167d` | NEW |
| `docs/OPEN-QUESTIONS.md` | `-` | `-` | `-` | `2a9521db55e8a42441e807b09f617628eef30185463b28b963a05e6dfcc245e5` | NEW |
| `context/identity.json` | `-` | `-` | `-` | `6e21785ed016cec904e7943ceea081e43ff4e1d022decfee4825ad74f77e062f` | NEW |
| `context/roster.json` | `-` | `-` | `-` | `b673648ee3f958762e03c5d4a94efd7bc44c9f68737e03ee77b9e8b9be72f9ee` | NEW |
| `context/roster-agents.json` | `-` | `-` | `-` | `adb89a2052049476200100ca683e96cd736535b0b6d779e9a6ca568ea78b5ab7` | NEW |
| `context/architecture/blueprint.md` | `-` | `-` | `-` | `937d367beb8214d42f564f4ae37e008e2acfa801fd8057d1074899fc34492977` | NEW |
| `context/architecture/CHANGE-LOG.md` | `-` | `-` | `-` | `b60339ca1f134dc56bd2a17e77cfd043a47c10b177a813946657029e010dd5d4` | NEW |
| `context/architecture/deviations.json` | `-` | `-` | `-` | `4cff6d6cc5119bc7b37eb0454a041513c866072c8911b4f43bbc15f12ad7d4c0` | NEW |
| `.gitattributes` | `-` | `-` | `-` | `6e67dce113a6af1d153c10e29b26ee1915d8cd02cb17386a83a27b8a06d6f361` | NEW |
| `tests/__init__.py` | `-` | `-` | `-` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | NEW |
| `tests/fixtures/kaed_fixture_document.json` | `-` | `-` | `-` | `fda4a23a8e9d271dcf80684e2733c7d172f9609b66d1da558ada8f06a0af593b` | NEW |
| `tests/fixtures/kaed_section_map.json` | `-` | `-` | `-` | `f305c27b4e0bf26b947ec6b2864e7c4aa79b71de1e5016560e9cc85ebe1c0be4` | NEW |
| `.claude/hooks/_activity.py` | `-` | `-` | `-` | `9f0c1df2dd6bd6f7721f6036b097f6c7208ccd0f0d0cf44a1fb4440ed71f30cd` | NEW |
| `tests/test_acceptance_preflight.py` | `-` | `-` | `-` | `0b3e3976b433f02deaa37c2673fb4a349380688261182705b7e79e1674deff11` | NEW |
| `tests/test_acceptance_p16.py` | `-` | `-` | `-` | `fdb731ea4aa6be00c14ee38011a245958bb700e04d92176e4f3e6cc5764317d9` | NEW |
| `.claude/hooks/require-active-agent.py` | `-` | `-` | `-` | `610ee6180e44fe27126eaf14ddae5ec7d90f3fd247db96a3a9d8132708226675` | NEW |
| `.claude/hooks/require-privacy-agent.py` | `-` | `-` | `-` | `fc8e187abf7cb1693a1194e66d988ac81b5a39dbb6723dced3ed309237cd7a9e` | NEW |
| `scripts/team.py` | `-` | `-` | `-` | `96dd33f35a644759cfc4c62fe805d04c85ac477c3aff70e0f74f8993761964d4` | NEW |
| `scripts/privacy_screen.py` | `-` | `-` | `-` | `b708b20785a423931b14e0cdd82d1f49dd8aa9d13168f0ea95a4678eb6f4b01d` | NEW |
| `scripts/privacy_review.py` | `-` | `-` | `-` | `11e48d70f90d2d2c51eedce09fd4cd8dbdc2731e48e5774d5e89dd3e58fbf5f1` | NEW |
| `scripts/prep.py` | `-` | `-` | `-` | `407d3b03e19c210a064a332178f3832c11a9552ef8e4ff2a564fd91642fc49be` | NEW |
| `context/architecture/phases.json` | `-` | `-` | `-` | `eaf63f2224a33f2c485b8e9048af99ce0bb0165e7576b87fae7732b4f7896b94` | NEW |
| `.claude/agents/sage.md` | `-` | `-` | `-` | `5cdce1b282ee6090886ffbcb3a88c71c85fa77514c0edc0a657dc900c7d45549` | NEW |
| `.claude/agents/lark.md` | `-` | `-` | `-` | `1afc5f9af599fc3d9cb0f7e86b163ae91cebca5376f5473df673fa80248d1c4f` | NEW |
| `.claude/agents/milo.md` | `-` | `-` | `-` | `f43e7be6e225c93b2ea9cc4393cd6c9e50a464ae6486eb50508c668de9596f0a` | NEW |
| `.claude/agents/ruth.md` | `-` | `-` | `-` | `3a927e2c8adeb46d8aec1ca640e9824265f772e0b528f721a1eddecbe9f97856` | NEW |
| `.claude/agents/atlas.md` | `-` | `-` | `-` | `3a8b725fa4cc4c6a7dc9013dcde3787508bd5295d111cddda43ee62ba34908bb` | NEW |
| `.claude/agents/cleo.md` | `-` | `-` | `-` | `da97613e0b21e28f893684e6dd4fa9b725287409274a4cfc119b4f7c97818b1c` | NEW |
| `.claude/agents/june.md` | `-` | `-` | `-` | `4902f25f6bf65f53cdfbc22280b06d61a28447802c49893cbb5386f936f0aba8` | NEW |
| `.claude/agents/penn.md` | `-` | `-` | `-` | `4a8499e483789e6d1feb28eb2cdf5891a1b912d8ec059e715dbc90ecde429fbd` | NEW |
| `.claude/agents/tally.md` | `-` | `-` | `-` | `ae3b31f099e08a664d2679f7ce1e8979d29391a04ccf6293d688c5caf48a2763` | NEW |
| `tests/test_roster_expansion.py` | `-` | `-` | `-` | `25ce325871723bd6e49722cbaa2ab4ce4ffadbf3eb652568895cfa37119a7a62` | NEW |
| `.claude/hooks/_failsafe.py` | `-` | `-` | `-` | `7435926eef276650f558020894e29569fb1b051ebdffa5cb632b425f51c00371` | NEW |
| `.claude/hooks/_shell.py` | `-` | `-` | `-` | `f719b0acd7109d59c78671345538ea089e7489c9031ac85553c517857dc61426` | NEW |
| `.claude/hooks/confine-read-only-agent.py` | `-` | `-` | `-` | `230ebf4cbf6583fc8062d67207fc089e0c432b007e9cc0c3940b2dfbf80e890b` | NEW |
| `tests/test_hardening.py` | `-` | `-` | `-` | `26d187da344555a768ae6ed94484a0339ebff4e659b6d80c0743572ffa85875f` | NEW |
| `scripts/overlay.py` | `-` | `-` | `-` | `9dab4218942cf3ef8dc7b1529f158d86fa9c613f1575895d9f8a916ef9ec6e7a` | NEW |
| `scripts/lessons.py` | `-` | `-` | `-` | `1b2cf74cbcbdec4c8b803f75dc7fa790530003402cd5b10c8a5aac56ce1edb97` | NEW |
| `scripts/build_mode.ps1` | `-` | `-` | `-` | `2964580964ccd9d2c4e8f0075d6df3a3dab544fb1cdbfd1911e2fa48d1013191` | NEW |
| `.claude/hooks/session-start.py` | `-` | `-` | `-` | `e3cc566efd50af8c823dd87d50c0f29b85a7dd280798b7c0cc14152a21403daf` | NEW |
| `.claude/hooks/require-lessons-agent.py` | `-` | `-` | `-` | `7b918827bfb59d09d8930ec47e04f9ff9096f3ca374f6ac898c57342b6ad32c4` | NEW |
| `tests/test_taylor_machine.py` | `-` | `-` | `-` | `4bdbe99c06dbc8b1b095f2f779de6f36cf15faa67e82f0632ee28ebf444921f7` | NEW |
<!-- end of manifest table -->

## What changed, and why

**`.claude/hooks/_lib.sh`, `scripts/job_lock.py`, `scripts/runs_log.py`** (PORT since 2026-10-01; were VERBATIM; PIPER, origin STEVIE)
The hook-field helpers, the run lock and the lock primitive under it. The code is unchanged: the tick's lock must be the one already proven. Their header comments are rewritten in general terms, because the originals described the source system's own jobs, and job_lock's refusal message says "the same work" rather than "the same month".

**`.claude/hooks/_transcript.py`** (PORT since 2026-10-01; was VERBATIM) Five changes made here. (1) A slash-command row is a turn boundary. Claude Code records `/add ...` as a user row holding only command blocks, followed by an isMeta expansion; without this rule the walk finds nothing typed there and runs on to the last PLAIN message, so for someone who works in slash commands the roll call after `/morning` would name the previous `/add`'s agents, and require-dispatch.py would let a second `/add`'s solo write through because the first one had dispatched. (2) TurnContext also carries the turn's main-thread tool uses and its unparseable-line count, collected in the same backwards pass, so the roll call decides "did this turn write?" from the same walk that names its roster. (3) A compaction's summary row (`isCompactSummary`) is not a turn boundary: compaction appends to the same file, and ending the walk there would hide everything the turn did before it. (4) A refused call is not a dispatch: a tool_result with `is_error` and either `toolDenialKind` or a `PreToolUse:` hook message (both observed on a live VS Code session) marks its tool use `refused`, and a refused Agent call goes to `TurnContext.refused`, not `dispatches`. Otherwise a switched-off MILO refused by require-active-agent.py would read "TEAM | MILO (1 dispatched)", and require-dispatch.py would let a later solo write through. `Task`, the Agent tool's older name, counts as a dispatch too. (5) A dispatch counts only on positive evidence that the agent ran: its Agent call has a result in this turn that is not a refusal. A call with no result yet goes to `pending`, and an error result that is not a recognised refusal (a refusal wrapped in a `<tool_use_error>` tag) goes to `unclear`; neither is a dispatch. `doubts()` names a line that did not parse and a turn whose start was not found, and every caller weighs them before believing a dispatch. Rows with `"text": null`, `"message": null` or thousands of levels of nesting are read or counted as unparsed, never a crash. `roster()` keeps another plugin's prefix (`OTHERPLUGIN:SAGE`), dropping only this repo's own `ea:`.

**`.claude/hooks/_gate.py`** (PORT) EA_* env vars; the roster is read from `context/roster-agents.json`; `caller_agent()` is new and reads Claude Code's own `agent_id`/`agent_type` payload fields, because transcript inference names the last agent DISPATCHED, which on the main thread is not the caller. `is_build_machine()` is new: build mode as `_health.build_mode()` reads it (Mike's permanent `state/BUILD_MACHINE`, or Taylor's laptop's timed `state/BUILD_MODE`), which opens layer B of protect-architecture. `invokes_script()` is the "does this command run scripts/x.py" rule, shared by the WREN-only and SAGE-only gates; since the hardening review it delegates to `_shell.runs_script()`, the parser every shell gate uses. `agent_name()` is the namespace rule: a bare roster name or this repo's `ea:` prefix names one of ours, any other prefix names nobody here (keeping only the last `:` segment let `x:wren` pass the WREN-only gate). `block()` encodes with `errors="replace"`, so a refusal quoting a lone surrogate cannot raise and exit 1; `read_payload()`, `load_context()` and the roster read treat `RecursionError` as unreadable. The roster read also returns the agents marked `read_only`.

**`.claude/hooks/_audit.py`** (PORT) Database module and doctor renamed. Otherwise verbatim, including every swallow and the never-cleared-by-success AUDIT-DEGRADED marker, with two additions from the hardening review: string fields have lone surrogates replaced before either sink sees them (one character used to cost the row and raise the banner), and the table sink leaves a register that does not exist alone rather than creating an empty, unmigrated `state/ea.db`.

**`.claude/hooks/require-dispatch.py`** (PORT) Gates `state/proposals`, `state/records`, `state/private` and `output/`, names this system's owners, and treats Claude Code's `agent_id` as proof a dispatch already happened.

**`.claude/hooks/no-cloud.py`** (PORT) Messages re-pointed at this system; the allowlist is `context/systems.json`. `git push`, `send-pack` and `send-email` are found through `_shell`'s parser, past git's own options (`git -C <dir> push`), launchers and assignments, and through an alias that pushes, inline (`-c alias.x=push`) or stored (`git config alias.x push`). Build mode changes none of it.

**`.claude/hooks/classify-and-place.py`** (PORT) Classes `private / records / shareable`, key `ea-class`, a declaration pattern that accepts the JSON key form a proposal uses, OAuth files and the build marker treated as machine-managed. The named-list sniffer is kept but switched off in `context/data-classes.json` (six-person roster).

**`.claude/hooks/require-approval.py`** (PORT, cold) Owner mailbox `t.iwaasa@gretabar.com`; egress script names are Phase 3+ names. `docs_edit.py` is deliberately NOT an egress pattern: blueprint s.1 lists topic, commitment, deadline and completion edits as reversible established operations.

**`.claude/hooks/announce-dispatch.py`** (PORT) Agents under `.claude/agents/`; the separator class written with escapes. Silent for a dispatch require-active-agent.py refuses (it asks scripts/team.py the same question), so no ">> MILO dispatched" banner sits above "NOT SWITCHED ON YET: MILO".

**`.claude/hooks/team-rollcall.py`** (PORT) The solo-versus-dispatched asymmetry kept verbatim. Adds the tick-health line (the fallback if the VS Code extension does not render a statusLine), the CHANGE-LOG banner (reading Taylor's change log in his overlay), and a BUILD MODE banner that opens the roll call while build mode is on. The SOLO block fires only when a solo turn wrote or changed something; a solo turn that only read gets the one line `TEAM  |  read only, nothing written`, because /owe and /morning are dispatch-free by design and an alarm on every morning screen trains Taylor to skip it. The verdict comes from the new `_activity.py`, and an unreadable turn is UNVERIFIED, never the quiet line.

**`.claude/hooks/statusline-ea.py`** (PORT, from PIPER's `statusline-piper.py`) Label from the identity in effect (Taylor's overlay over `context/identity.json`), and BUILD MODE with its expiry closing the line while it is on; tick read and rendering moved to `_health.py` so the bar and the roll call cannot disagree. Shows `read only` where the roll call shows the quiet line, from the same `_activity.py` verdict, and `<NAME> running` while a dispatched agent's result is not written yet; cache format 3, keyed on both parser files.

**`.claude/hooks/validate-on-edit.sh`** (PORT) Routes `.claude/agents`, `.claude/skills` and `.claude/commands` to the contract validator, hooks and context to the guardrail self-test. Every cannot-check branch still exits 2.

**`.claude/settings.json`** (PORT) This system's wiring: every shell gate matches `Bash|PowerShell`, and the cold approval gate matches `Bash|PowerShell|mcp__.*`, the only tool names it can ever match. The source's domain-specific gates are not carried (none applies to a 1:1 register, and there is no browser in Phase 1). require-active-agent.py matches `Agent|Task|Workflow|Bash|PowerShell`, and require-privacy-agent.py sits beside require-delivery-agent.py on `Bash|PowerShell`. confine-read-only-agent.py matches every tool that can act, and require-lessons-agent.py sits on `Bash|PowerShell` too. One SessionStart hook, `session-start.py`, loads Taylor's name, build mode, his rules and his lessons, and is not wrapped: it cannot block. Every blocking PreToolUse command is wrapped (`...; s=$?; case $s in 0|2) exit $s;; esac; echo "BLOCKED: ..." >&2; exit 2`) because Claude Code blocks only on exit 2: a gate that crashes before its own catch-all, or a missing interpreter, still blocks. The banner, the roll call and the status line are not wrapped; they must never block.

**`scripts/ea_db.py`** (PORT, from `piper_db.py`) `connect(read_only)`, `migrate()` under `user_version`, WAL and the people-column allowlist kept. Schema replaced with the register's tables, plus a `proposals` index the plan implies (WREN verifies PAGE's hash against it). A second database, `state/fixtures.db`, is selected by `EA_FIXTURE_MODE=1`. Schema v3 adds `privacy_reviews`, SAGE's verdicts bound to a proposal's sha256.

**`scripts/approvals.py`** (PORT) Names only. `canonical()` is also the hash for Doc edit proposals.

**`scripts/notify_owner.py`** (PORT, from `notify_cass.py`) Liveness only: the tick and the Docs' last successful read. No alarm about open employee work (blueprint s.4, s.6).

**`scripts/validate_agent_contracts.py`** (PORT) `.claude/` paths, roster from `context/roster-agents.json`, an `orchestrator` owner token that survives renaming, and a roster-to-files consistency check: every roster agent has a file with the roster's model, and one that is not switched on (scripts/team.py) holds only Read, Glob and Grep and quotes the two lines it answers with.

**`scripts/validate_content_rules.py`** (PORT) Emoji kept; the em-dash rule covers everything bound for a Doc or for Taylor; the source's domain-specific rules dropped; classes built from integer code points, so the file carries neither glyphs nor escapes.

**`scripts/validate_guardrails.py`** (PORT) New fixtures for this system's gates, every case's verdict printable, and `--mutation-test`, which removes each gate and proves the self-test notices. The roll call is a gate here too: one fixture per outcome, and one mutation per outcome, each required to turn its own fixture red. The roster expansion adds active-agent (every refusal's exact lines, held to the brief's wording and to docs/FOR-TAYLOR.md), privacy-screen, privacy-stamp and privacy-agent, each with its own mutation. The hardening review adds dispatch (positive evidence, the reviewers' transcripts), read-only-agent and failsafe, a fixture and an aimed mutation for each rule it added to the other gates, and a fault-injection phase in `--mutation-test` that breaks each blocking gate in a throwaway copy and requires exit 2. Building on Taylor's machine adds lessons-agent, lessons-screen and overlay, cases for every layer of protect-architecture and for build mode in active-agent, the roll call and the status line, and an aimed mutation for each; every run pins the overlay to an empty folder, so Taylor's own decisions never change what a gate is expected to refuse.

**`scripts/check_vendored.py`** (PORT) Two upstreams, NEW rows, `--rehash`, `--add`.

**`scripts/google_creds.py`** (PORT, from STEVIE `scripts/upload_to_drive.py` `load_credentials`) One `load_credentials(scopes)`; paths from `EA_ROOT/state/` only; both token shapes; scopes checked before any network call; refreshed per process and never written back.

**`scripts/google_auth.py`** (PORT, from STEVIE `scripts/marketing_report/google_auth.py`) The installed-app consent kept; login hint from `context/identity.json`; granted scopes checked after consent; `--check` mode. Not run on the build machine.

**`scripts/ea_tick.py`** (PORT, from `cadence_tick.py`) The frame kept (lock across the run, heartbeat only when earned, exit codes, dry run on an in-memory copy); the body replaced with read-only reconciliation and Calendar refresh; fixture ticks on their own lock and job name.

**`scripts/run_ea_tick.ps1`, `scripts/schedule_ea_tick.ps1`** (PORT) The outside-the-process exit watch, the alarm, the append-not-truncate log and the battery flags kept; `-Live` dropped (no send path); task `EA-Tick` at 07:00.

**`scripts/ea_doctor.py`** (PORT, from `piper_doctor.py`) Google, Docs, Calendar, build mode, Taylor's overlay (seeded, readable, no legacy decision in a tracked file, no tracked file changed locally) and D-1 instead of the source's own systems. Reports the team's counts and warns on an agent that is on while its phase is not accepted (LARK under D-3).

**`scripts/build_ea_kit.py`** (PORT, from `build_piper_kit.py`) `.claude/` layout; NEVER_COPY adds the Google client and token, the build marker and the fixture database; the gate adds Google's secret shapes; `docs/acceptance/` stays behind.

**`scripts/export_ledger.py`** (PORT) A register snapshot; names make it `records`, so it may only land under `state/records/`.

**`CLAUDE.md`, `INSTALL.md`** (PORT) PIPER's structure (rules first, enforcement named, the privacy paragraph) re-written for this system; CLAUDE.md is distilled and points at blueprint sections instead of importing them.

**`.claude/commands/NAME.md`, `boi.md`, `morning.md`; skills `reality-checker`, `morning-brief`; agents `hugo.md` (from OTIS), `wren.md` (from VERA's delivery role); `docs/PRIVACY.md`** (PORT) Lanes READ and CAPTURE replace PIPER's FAST/STANDARD/FULL; PRIVACY keeps "A Claude Enterprise seat is not a privacy control" verbatim.

**`.gitignore`, `.env.example`, `requirements.txt`, `context/data-classes.json`, `context/systems.json`** (PORT) Re-cut for this system: Google credentials by name, `tzdata` added, Playwright and requests dropped, three data classes, Google hosts only.

**The roster expansion (NEW, 2026-10-01).** `context/architecture/phases.json` is Taylor's phase gate (rules text, his phrase only); `context/roster-agents.json` carries thirteen agents and Mike's `build_record` (code). `scripts/team.py` combines them, renders the exact switched-off lines, and is read by `.claude/hooks/require-active-agent.py` (refuses a switched-off, non-roster, workflow or CLI dispatch, failing closed), announce-dispatch, the doctor and the contract validator. SAGE: `scripts/privacy_screen.py` flags personal context in a proposal, `scripts/privacy_review.py` records SAGE's verdict, `.claude/hooks/require-privacy-agent.py` lets only SAGE run it, and docs_edit.py refuses a flagged proposal without SAGE's approval of those bytes; `register.py keep-private` carries out the private-notes offer. LARK: `scripts/prep.py`, read only, and confined to it and the register's read subcommands by `.claude/hooks/confine-read-only-agent.py` since the hardening review. Agents `sage.md` and `lark.md` are on; `milo`, `ruth`, `atlas`, `cleo`, `june`, `penn` and `tally` are switched-off files holding only Read, Glob and Grep. `tests/test_roster_expansion.py` drives all of it with no network.

**The hardening review (NEW, 2026-10-01).** Two independent reviews of 0c3fe45..13fdd94 found gates that failed open. `.claude/hooks/_failsafe.py` is every blocking gate's last line: `run_gate()` turns a failed import, a crash, a `sys.exit` or any return but 0 or 2 into a refusal, standard library only so it loads when the rest cannot. `.claude/hooks/_shell.py` is the one parser of what a Bash or PowerShell command runs (launchers unwrapped, both shells' quoting and escapes read, the union taken), shared by the dispatch, WREN-only, SAGE-only and read-only gates. `.claude/hooks/confine-read-only-agent.py` holds LARK's shell to prep.py and the register's read subcommands. `team.py` accepts only an ISO date as `accepted` and keeps a deferred phase off until the deferral is lifted; `privacy_screen.py` NFKC-normalises and strips invisible format characters, and reads a name in any alphabet; `docs_edit.py` reads SAGE's verdict again immediately before each write; `prep.py` states what SQLite itself may leave and refuses an unmigrated register with exit 3; read-only SQLite URIs are built with `Path.as_uri()`. `tests/test_hardening.py` drives the reviewers' reproductions against the real hooks, and `validate_guardrails.py --mutation-test` adds an aimed break per rule and a fault injected into each gate.

**Building on Taylor's machine (NEW, 2026-10-01).** From Phase 2 Mike builds on Taylor's laptop and Taylor updates with `git pull`, so nothing Taylor decides may live in a tracked file. `scripts/overlay.py` keeps his decisions and learning in `state/taylor/`, untracked: phase approvals, deviation decisions, his Architecture Change Log, his own rules, his living copy of the blueprint (the tracked one is the frozen v1 baseline), his identity overrides (the system's name, written as a gitignored generated skill `/<name>`), his lessons and the proposals written for him. `team.py`, `docs_edit.py`, `register.py`, the doctor and the status line read the tracked defaults with his overlay laid over them; a decision left in a tracked file from before is honoured, reported and moved once by `overlay.py migrate --restore`. `context/architecture/phases.json` and `deviations.json` now hold upstream defaults only, and the guardrail self-test fails if they decide anything. protect-architecture.py: layer A is his overlay (his phrase), layer B the upstream defaults and code (build mode only, and the phrase never opens them), the v1 baseline and the lessons store frozen, and both markers and `scripts/build_mode.ps1` out of a session's reach. `scripts/build_mode.ps1` switches build mode on for at most 24 hours from a terminal and refuses inside a Claude session; while it is on, non-roster dev agents may be dispatched (require-active-agent.py) and the roll call, the status line and the doctor say so. `scripts/lessons.py` is the learning loop (blueprint s.1): preferences and routing take effect next session through `.claude/hooks/session-start.py`; a price, package, minimum spend, discount, policy, sending permission or rule is held as a rule-candidate, asked once and never in effect without Taylor's yes; `.claude/hooks/require-lessons-agent.py` lets only REED write it. `prep.py` is the full s.10 briefing, Taylor's part first, with the Doc's carried-forward rows and last 1:1 from the stored snapshot. `tests/test_taylor_machine.py` proves it, including the two-clone pull: Taylor decides through his overlay, upstream changes the defaults in the same files, and his pull is clean with everything still in effect, while the same decisions made the old way make the pull refuse.

**Not recorded here:** `README.md`, `docs/FOR-TAYLOR.md`, `docs/PLAYBOOK.md` and `docs/FIRST-PROMPT.md` are ANNIE's, written in parallel and owned by her, so their hashes would go stale every time she edits. `docs/acceptance/` is generated evidence, regenerated by `scripts/acceptance.py`.
