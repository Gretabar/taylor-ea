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
| `.claude/hooks/_transcript.py` | `PIPER:.claude/hooks/_transcript.py` | `untracked` | `727531fd2915fefcfa58a0ccc6980debd88350e1918a7706ca2631eda5c9646b` | `ba55e2d5249cc5590cc3bafae75b5e7d31d19f3ae745a5206ef4b6037f59f57b` | PORT |
| `.claude/hooks/_lib.sh` | `PIPER:.claude/hooks/_lib.sh` | `untracked` | `19e325f96a7904e4acf853be2b901c3de165c0ffe5fdcf992e190c3106368797` | `f4ef2af318a3e08878af557dd6ce0cdf4d574b02869e70022ba8b0d27fdb2453` | PORT |
| `scripts/job_lock.py` | `PIPER:scripts/job_lock.py` | `untracked` | `e81ceffd6c0d3811a5d4567c0241fc0cdde83ab940836caeacf37694375b067a` | `0b2eb2aba9ae413723a119b83c4bda4c21f63abde35fbb05933cf991e8970227` | PORT |
| `scripts/runs_log.py` | `PIPER:scripts/runs_log.py` | `untracked` | `03412631208eedacd5cf2649a602fbfaafaf652359ea4d34a527c22eb4f90936` | `6c6cb9466f2894c13300123ba808a95de6c6950d342395716e8c25406389e43b` | PORT |
| `.claude/hooks/_gate.py` | `PIPER:.claude/hooks/_gate.py` | `untracked` | `27f386c1a3b7ab9ebeba0d21baf6f26b3f5bfbf3be64b4fbdd96140b522f1dac` | `ee5e94c4fa1b001b59da35c15ddefcdfce4e6485e0f74b0367b96a692bd8f6e0` | PORT |
| `.claude/hooks/_audit.py` | `PIPER:.claude/hooks/_audit.py` | `untracked` | `f53c94b79c114c443ca3fa903417ab651d4508378c70cc754d0b9856dbaf62ed` | `0685d94f736e3b2e2d6abebf81d3f49fd986d52c4c407b665c0a5fe2fb7c76c2` | PORT |
| `.claude/hooks/require-dispatch.py` | `PIPER:.claude/hooks/require-dispatch.py` | `untracked` | `e0fe3e67171149bdc77e9184127350a2e62748feff9ab4b0234df4178568ae8e` | `b7826b321f964098abd05d2bc204ef922d4cc91311eff45d22656e1b3adb693a` | PORT |
| `.claude/hooks/no-cloud.py` | `PIPER:.claude/hooks/no-cloud.py` | `untracked` | `a9b74363b4ebdc909575c6beae03f17c80e43d8fd6fff4864e46890a5503633b` | `bf48b7d05a9b114a72689129a83a8336a05d69df4e4343a1d36e98f677e7d8b9` | PORT |
| `.claude/hooks/classify-and-place.py` | `PIPER:.claude/hooks/classify-and-place.py` | `untracked` | `48115417f63102f1248a85477c23c3a8417aad0d2a65734a2241484dcd32f313` | `fa1a5d1842221be67f1524142cce5d77c3e5988fcb70053fa4a087d14418de29` | PORT |
| `.claude/hooks/require-approval.py` | `PIPER:.claude/hooks/require-approval.py` | `untracked` | `543e4c7c545a6964daf846f902766686a54c871b0e79183408e65648912104d1` | `8837fe841f93bd125ced94cd78e5b32797fe70979e3815c23d080ad2fcecfe51` | PORT |
| `.claude/hooks/announce-dispatch.py` | `PIPER:.claude/hooks/announce-dispatch.py` | `untracked` | `9a4b32733759f90684d0689a925979642114229548ff31a6313895977adcfe37` | `eb2ad87072a5e33df154f0892881d84298be1ea6eb4c84773143814804991d6d` | PORT |
| `.claude/hooks/team-rollcall.py` | `PIPER:.claude/hooks/team-rollcall.py` | `untracked` | `f6800761b72db78b1c556001a3f1866741b08570ab21242f25909bc8b81b5bf5` | `430dbb32bd986edbcbcac441bb7fa9e38ac27a106c53f76aec4f0978d2960554` | PORT |
| `.claude/hooks/statusline-ea.py` | `PIPER:.claude/hooks/statusline-piper.py` | `untracked` | `5066cb7556b7837c58906721d1466c41efe8331455e019fe402c1ce3a26ac1b5` | `7b0efd3cb606d04c620505a3471cb2d17d44249afe74197ff0c4d87baeeda570` | PORT |
| `.claude/hooks/validate-on-edit.sh` | `PIPER:.claude/hooks/validate-on-edit.sh` | `untracked` | `915b7a11e81718da9e18d03a07b742e66ed1a16096b9081d2523d7601d537acd` | `a35db937286d9229d50a45be2312a0058884944d49efe40cee9e5dfaeb67db12` | PORT |
| `.claude/settings.json` | `PIPER:.claude/settings.json` | `untracked` | `4a0f8f1882659f951beecdc9437be412b95be38ae32cee4cfd677e6553bffe77` | `136f7c1fa12123307a7cb2f3c8ebab0cae152c318da94b706f6eee8732a88959` | PORT |
| `scripts/ea_db.py` | `PIPER:scripts/piper_db.py` | `untracked` | `1f0a2aa94a78366de4408268bf08dd46e0bd6f4a9c2bf1caa5f6e42029af50cd` | `36375f65b7aa74c13533abeb084198436825dd14849442298a0e8de971b2890d` | PORT |
| `scripts/approvals.py` | `PIPER:scripts/approvals.py` | `untracked` | `6ae22201b737e5723240777a3ac75de183ddaf116b14f97f398324232f5d4214` | `dabda1cc9a0c988f5005862986eedda71924b7657dd8fea385e6972e0681d4f5` | PORT |
| `scripts/notify_owner.py` | `PIPER:scripts/notify_cass.py` | `untracked` | `661fb20f4e154868d699ab00732c632aa8536740ac484f411328956febf37847` | `4a65dda3021544c337da7a26e5f1a957ab4909430ad6004588bbe17e7cea27f4` | PORT |
| `scripts/validate_agent_contracts.py` | `PIPER:scripts/validate_agent_contracts.py` | `untracked` | `fb2892cca02a78f2495ccb78ac1645432ec0e4ced23a1220c6e2bd1c154ae896` | `2c5a5a9d6b554a17b532ed689ae5c1ef0a00ce1a4bb8d95df1d06977ceb1217e` | PORT |
| `scripts/validate_content_rules.py` | `PIPER:scripts/validate_content_rules.py` | `untracked` | `310ad7f6afa5f38be5c18dc27d580fd37005dffdd5551114b15587c3e98fbdc0` | `756c4d9da6f77f4c6f2f3c0ef0739bcba6e1affdc13e9563ab547a6acfc1b873` | PORT |
| `scripts/validate_guardrails.py` | `PIPER:scripts/validate_guardrails.py` | `untracked` | `704b4700e07cc3c26e3650507b73bd7660eb9d01db2216b973fedeaa54c7dfe7` | `f0829963e15b4c86a99c57bf2eacaf168934f6f79675ebcc8beac13fdd25926e` | PORT |
| `scripts/check_vendored.py` | `PIPER:scripts/check_vendored.py` | `untracked` | `3e9ab0c1894a70989998c8e536331bacb6f722d40ffc0ac0abadd84d5ce646ef` | `d2811042a9205d770509fad36ead46f34d7d23fb53e4d6b42db87820a0c84356` | PORT |
| `.claude/hooks/_health.py` | `-` | `-` | `-` | `e4fc9b9dd837b45f2cce473c6f9657f81cc3fad5cdce7f0c7bb3e0ecd3c0f926` | NEW |
| `.claude/hooks/require-delivery-agent.py` | `-` | `-` | `-` | `5d19e0644a0ba7d8c312ac73038c69a68beb448f77cb3d1171eff1d4307ba24a` | NEW |
| `.claude/hooks/protect-architecture.py` | `-` | `-` | `-` | `ecd0c5c04f4cf63f65ea3a3cdf9f2c7181c28e8432e1374553723dce7da972d4` | NEW |
| `scripts/register.py` | `-` | `-` | `-` | `caa01bdd12fea9fd53aa87753d31c0e7525eec001f470933ea5558aa112e7e2b` | NEW |
| `scripts/google_creds.py` | `STEVIE:scripts/upload_to_drive.py` | `untracked` | `8501f0e5e2c0f6c5e0b8220ae2a650eb7af453cb413b64666690889f6674f883` | `527c1777f3e86dfa65c4006d8e5a8cdae69427564c3dd1ce75fef66d8856542d` | PORT |
| `scripts/google_auth.py` | `STEVIE:scripts/marketing_report/google_auth.py` | `e3f42d2` | `92c3d715e28338de6aaef8b9c6241f8ac8c1abe14810b6ec3a841a5f1c272f8e` | `bc6115a7feb84c96743b96c71d1c4284ee80f65804f1dc59bd1ab494b03d84c5` | PORT |
| `scripts/docs_read.py` | `-` | `-` | `-` | `7d8a81a3b9a1ccb98a44180afbfb8eea72249b06b6765817bebe19ddfed6590e` | NEW |
| `scripts/link_docs.py` | `-` | `-` | `-` | `90855f7ecdfb52c43fdfa75b290b43f3728525cfdb3fd74549f69c73ec8d20c5` | NEW |
| `scripts/calendar_next.py` | `-` | `-` | `-` | `c3f4a9d7bd0108a926447d6d8297542bb1f3ddc2741243b5ad1b4dd5028c3114` | NEW |
| `scripts/make_fixtures.py` | `-` | `-` | `-` | `60760db39629dc49b9595294711dcb59b33a21b051e756184ba12d645a5b106d` | NEW |
| `tests/test_calendar_next.py` | `-` | `-` | `-` | `39b93a6afe224422e711ce8b14e1edb8c4ba08c99d0544ff214f8f42dce37c22` | NEW |
| `tests/test_docs_read.py` | `-` | `-` | `-` | `eaced801952ec08874cba7972d324fcf9e146dd957cb3541da9c05295e561242` | NEW |
| `scripts/docs_propose.py` | `-` | `-` | `-` | `5caf67bc93a6f62196cec58ef55c22ad0efcbe296291aab91f283b93b161b355` | NEW |
| `scripts/docs_edit.py` | `-` | `-` | `-` | `2918114b463df9c0a56192c2f846dadf027dc98b0e8b83a9c22c4679758d3603` | NEW |
| `scripts/docs_reconcile.py` | `-` | `-` | `-` | `8ae92c49a91167132497725c67a1d29f304c73eaad1f9b7a0bee4054362d74e7` | NEW |
| `scripts/acceptance.py` | `-` | `-` | `-` | `0135623d3b93b05ff41e024d6006bf8f77e0d930e209be776a3d1b24eef17086` | NEW |
| `scripts/ea_tick.py` | `PIPER:scripts/cadence_tick.py` | `untracked` | `6c0b9b48c339ac7da6cf9f3b9001182474f5da95106d0a122e522dc361c520f8` | `d48bbf97bb791f75ac304a1f124426889d59d49f36b156c9ce98f697830e000e` | PORT |
| `scripts/run_ea_tick.ps1` | `PIPER:scripts/run_cadence_tick.ps1` | `untracked` | `d7233a6d93db66768bebbb3ca61591de41356a88a56a0ad92ddbd621d6ddccb2` | `712efb60739d2511a96ce97a291504bd8f3828e8412d284a87d6e4ab2488de75` | PORT |
| `scripts/schedule_ea_tick.ps1` | `PIPER:scripts/schedule_cadence_tick.ps1` | `untracked` | `6189ca47717bb64d4bb7521b69f166330ddac8939e4a05dd57936f9d2e88ca7e` | `38035578522913ed67b347a8a52aee9f79ac874e46c3511debba4c61158415a0` | PORT |
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
| `scripts/ea_doctor.py` | `PIPER:scripts/piper_doctor.py` | `untracked` | `122f92ab171b0e98e6dbd438d864c030f450bc9eed9035eccb5a3d29a5b156df` | `4b6b83e424d8c051cc17dcea783e1f66f0ecf425066d1df1e630b4537cff6953` | PORT |
| `scripts/build_ea_kit.py` | `PIPER:scripts/build_piper_kit.py` | `untracked` | `0080c36bd42134f51a424dc84fa8b4a2054f56505b0648d858740edb1d6961a5` | `6bc50423697154d04667ee363e1a3bb9f4f87b22593ce2e66ac931e5bc8138c5` | PORT |
| `scripts/export_ledger.py` | `PIPER:scripts/export_ledger.py` | `untracked` | `7ec4a5b24c17a2acf3fca35b96d4a8f721d451948244a3623d0b1b00616b81cb` | `ec6cd3f362aa2b609cf5721f9e926d382e0b91a978322b1be06c641e98633bac` | PORT |
| `.gitignore` | `PIPER:.gitignore` | `untracked` | `367e93e20e9ac36fed36e3ac3b044098f0d339a4ea6c4fa955822304d3a8aff1` | `95ab1ca891c26fcdab3d8c6d197d166ada36adbd20b14556c5b987adf4e9be0d` | PORT |
| `.env.example` | `PIPER:.env.example` | `untracked` | `1e43694bb0ba53d1daeb0a8bb1874f29a5307e3148619fef2e150f1409ee4f2e` | `25e301fba8882b549f7bafa132f9da665a5eed13b3d88fe25d9c9726eba45dfd` | PORT |
| `requirements.txt` | `PIPER:requirements.txt` | `untracked` | `a0cb47cff08849bb572c4381836da9c07c71a4874d1646db622688b304ca47f4` | `15a2869787f5a6a48f9a7e0d7cf2ce26eb13876543e88889ea4a59c46ca4a4b2` | PORT |
| `context/data-classes.json` | `PIPER:context/data-classes.json` | `untracked` | `2ca484126dab62a834c7b813e8538970c9ad72734190542d8199e41e237f91a7` | `b12e8070e98fdeeac3f3150e9878d196ad7872abe57d8b99cef6bcfb08d535f7` | PORT |
| `context/systems.json` | `PIPER:context/systems.json` | `untracked` | `85e907222296390622572c0d1f32549f9e5af2e9586a92784f646d807a7bbaa6` | `eaa4656ff54a4d0eb2daa596701741d46865172263b94fa47d61add1111b5e17` | PORT |
| `.claude/agents/reed.md` | `-` | `-` | `-` | `44aaf9f4c85c7294f0d02cc5db2337ddb892997b5e7f151b03cb597ebcb3e7d7` | NEW |
| `.claude/agents/page.md` | `-` | `-` | `-` | `e1d1c514cf9e9cf0a02198cc50f585633631c4890767f04940c23e0ffc2fa98b` | NEW |
| `.claude/commands/add.md` | `-` | `-` | `-` | `732629e92a23544e3d6974520c5202e4b08cbd6ffaa8d7fb87005e28626c17a5` | NEW |
| `.claude/commands/owe.md` | `-` | `-` | `-` | `3e1bed7883e2a1986f55ad0fce98463f9fe348fb67d67a8d0bced59bb5d77fea` | NEW |
| `.claude/skills/capture-rules/SKILL.md` | `-` | `-` | `-` | `546cc0a9f5c7c0a0b062ad94b39343a699c52932586c566acf679cbab295ead3` | NEW |
| `.claude/skills/doc-editor/SKILL.md` | `-` | `-` | `-` | `e797d5fb9f90eaf5ba3004689c24e55ef3ff1a35b39a78bc330b3bc49572ec70` | NEW |
| `.claude/skills/delivery-gate/SKILL.md` | `-` | `-` | `-` | `8a2b0831dddc59e9320b5870cf626376a2b35ba7b8ddbb286b31596e84e8e131` | NEW |
| `docs/DEVIATIONS.md` | `-` | `-` | `-` | `8a7b951ce85d638e0bf0ac9916fc4afc98c574bba96a63dc0b7b20743a1bda7e` | NEW |
| `docs/OPEN-QUESTIONS.md` | `-` | `-` | `-` | `a09dddf36c17f847b1939babd30667488df56cdf12a52fbc33016dbfec9c471d` | NEW |
| `context/identity.json` | `-` | `-` | `-` | `6e21785ed016cec904e7943ceea081e43ff4e1d022decfee4825ad74f77e062f` | NEW |
| `context/roster.json` | `-` | `-` | `-` | `b673648ee3f958762e03c5d4a94efd7bc44c9f68737e03ee77b9e8b9be72f9ee` | NEW |
| `context/roster-agents.json` | `-` | `-` | `-` | `de25405f4b43a0b78cf7ed61ed012bba264890039d011d790609564466ea1e84` | NEW |
| `context/architecture/blueprint.md` | `-` | `-` | `-` | `937d367beb8214d42f564f4ae37e008e2acfa801fd8057d1074899fc34492977` | NEW |
| `context/architecture/CHANGE-LOG.md` | `-` | `-` | `-` | `b60339ca1f134dc56bd2a17e77cfd043a47c10b177a813946657029e010dd5d4` | NEW |
| `context/architecture/deviations.json` | `-` | `-` | `-` | `1e9b0a1e6ca83c9e66edc82b7e6a3fed1538eca7a285d85d2c3620ebd803cb76` | NEW |
| `.gitattributes` | `-` | `-` | `-` | `6e67dce113a6af1d153c10e29b26ee1915d8cd02cb17386a83a27b8a06d6f361` | NEW |
| `tests/__init__.py` | `-` | `-` | `-` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | NEW |
| `tests/fixtures/kaed_fixture_document.json` | `-` | `-` | `-` | `fda4a23a8e9d271dcf80684e2733c7d172f9609b66d1da558ada8f06a0af593b` | NEW |
| `tests/fixtures/kaed_section_map.json` | `-` | `-` | `-` | `f305c27b4e0bf26b947ec6b2864e7c4aa79b71de1e5016560e9cc85ebe1c0be4` | NEW |
| `.claude/hooks/_activity.py` | `-` | `-` | `-` | `893a304746e08c8a10bb606fb453c9d686b93967ed5e04b2cb4c080b38def88d` | NEW |
| `tests/test_acceptance_preflight.py` | `-` | `-` | `-` | `0b3e3976b433f02deaa37c2673fb4a349380688261182705b7e79e1674deff11` | NEW |
| `tests/test_acceptance_p16.py` | `-` | `-` | `-` | `fdb731ea4aa6be00c14ee38011a245958bb700e04d92176e4f3e6cc5764317d9` | NEW |
<!-- end of manifest table -->

## What changed, and why

**`.claude/hooks/_lib.sh`, `scripts/job_lock.py`, `scripts/runs_log.py`** (PORT since 2026-10-01; were VERBATIM; PIPER, origin STEVIE)
The hook-field helpers, the run lock and the lock primitive under it. The code is unchanged: the tick's lock must be the one already proven. Their header comments are rewritten in general terms, because the originals described the source system's own jobs, and job_lock's refusal message says "the same work" rather than "the same month".

**`.claude/hooks/_transcript.py`** (PORT since 2026-10-01; was VERBATIM) Three changes made here. (1) A slash-command row is a turn boundary. Claude Code records `/add ...` as a user row holding only command blocks, followed by an isMeta expansion; without this rule the walk finds nothing typed there and runs on to the last PLAIN message, so for someone who works in slash commands the roll call after `/morning` would name the previous `/add`'s agents, and require-dispatch.py would let a second `/add`'s solo write through because the first one had dispatched. (2) TurnContext also carries the turn's main-thread tool uses and its unparseable-line count, collected in the same backwards pass, so the roll call decides "did this turn write?" from the same walk that names its roster. (3) A compaction's summary row (`isCompactSummary`) is not a turn boundary: compaction appends to the same file, and ending the walk there would hide everything the turn did before it.

**`.claude/hooks/_gate.py`** (PORT) EA_* env vars; the roster is read from `context/roster-agents.json`; `caller_agent()` is new and reads Claude Code's own `agent_id`/`agent_type` payload fields, because transcript inference names the last agent DISPATCHED, which on the main thread is not the caller. `is_build_machine()` is new (the hostname-bound marker for layer B of protect-architecture). `invokes_script()` is the "does this command run scripts/x.py" rule, moved here out of require-delivery-agent.py unchanged so the SAGE-only gate shares it rather than copying it.

**`.claude/hooks/_audit.py`** (PORT) Database module and doctor renamed. Otherwise verbatim, including every swallow and the never-cleared-by-success AUDIT-DEGRADED marker.

**`.claude/hooks/require-dispatch.py`** (PORT) Gates `state/proposals`, `state/records`, `state/private` and `output/`, names this system's owners, and treats Claude Code's `agent_id` as proof a dispatch already happened.

**`.claude/hooks/no-cloud.py`** (PORT) Messages re-pointed at this system; the allowlist is `context/systems.json`.

**`.claude/hooks/classify-and-place.py`** (PORT) Classes `private / records / shareable`, key `ea-class`, a declaration pattern that accepts the JSON key form a proposal uses, OAuth files and the build marker treated as machine-managed. The named-list sniffer is kept but switched off in `context/data-classes.json` (six-person roster).

**`.claude/hooks/require-approval.py`** (PORT, cold) Owner mailbox `t.iwaasa@gretabar.com`; egress script names are Phase 3+ names. `docs_edit.py` is deliberately NOT an egress pattern: blueprint s.1 lists topic, commitment, deadline and completion edits as reversible established operations.

**`.claude/hooks/announce-dispatch.py`** (PORT) Agents under `.claude/agents/`; the separator class written with escapes.

**`.claude/hooks/team-rollcall.py`** (PORT) The solo-versus-dispatched asymmetry kept verbatim. Adds the tick-health line (the fallback if the VS Code extension does not render a statusLine) and the CHANGE-LOG banner. The SOLO block fires only when a solo turn wrote or changed something; a solo turn that only read gets the one line `TEAM  |  read only, nothing written`, because /owe and /morning are dispatch-free by design and an alarm on every morning screen trains Taylor to skip it. The verdict comes from the new `_activity.py`, and an unreadable turn is UNVERIFIED, never the quiet line.

**`.claude/hooks/statusline-ea.py`** (PORT, from PIPER's `statusline-piper.py`) Label from `context/identity.json`; tick read and rendering moved to `_health.py` so the bar and the roll call cannot disagree. Shows `read only` where the roll call shows the quiet line, from the same `_activity.py` verdict; cache format 2, keyed on both parser files.

**`.claude/hooks/validate-on-edit.sh`** (PORT) Routes `.claude/agents`, `.claude/skills` and `.claude/commands` to the contract validator, hooks and context to the guardrail self-test. Every cannot-check branch still exits 2.

**`.claude/settings.json`** (PORT) This system's wiring: every shell gate matches `Bash|PowerShell`, and the cold approval gate matches `Bash|PowerShell|mcp__.*`, the only tool names it can ever match. The source's domain-specific gates are not carried (none applies to a 1:1 register, and there is no browser in Phase 1).

**`scripts/ea_db.py`** (PORT, from `piper_db.py`) `connect(read_only)`, `migrate()` under `user_version`, WAL and the people-column allowlist kept. Schema replaced with the register's tables, plus a `proposals` index the plan implies (WREN verifies PAGE's hash against it). A second database, `state/fixtures.db`, is selected by `EA_FIXTURE_MODE=1`.

**`scripts/approvals.py`** (PORT) Names only. `canonical()` is also the hash for Doc edit proposals.

**`scripts/notify_owner.py`** (PORT, from `notify_cass.py`) Liveness only: the tick and the Docs' last successful read. No alarm about open employee work (blueprint s.4, s.6).

**`scripts/validate_agent_contracts.py`** (PORT) `.claude/` paths, roster from `context/roster-agents.json`, an `orchestrator` owner token that survives renaming, and a roster-to-files consistency check.

**`scripts/validate_content_rules.py`** (PORT) Emoji kept; the em-dash rule covers everything bound for a Doc or for Taylor; the source's domain-specific rules dropped; classes built from integer code points, so the file carries neither glyphs nor escapes.

**`scripts/validate_guardrails.py`** (PORT) New fixtures for this system's gates, every case's verdict printable, and `--mutation-test`, which removes each gate and proves the self-test notices. The roll call is a gate here too: one fixture per outcome, and one mutation per outcome, each required to turn its own fixture red.

**`scripts/check_vendored.py`** (PORT) Two upstreams, NEW rows, `--rehash`, `--add`.

**`scripts/google_creds.py`** (PORT, from STEVIE `scripts/upload_to_drive.py` `load_credentials`) One `load_credentials(scopes)`; paths from `EA_ROOT/state/` only; both token shapes; scopes checked before any network call; refreshed per process and never written back.

**`scripts/google_auth.py`** (PORT, from STEVIE `scripts/marketing_report/google_auth.py`) The installed-app consent kept; login hint from `context/identity.json`; granted scopes checked after consent; `--check` mode. Not run on the build machine.

**`scripts/ea_tick.py`** (PORT, from `cadence_tick.py`) The frame kept (lock across the run, heartbeat only when earned, exit codes, dry run on an in-memory copy); the body replaced with read-only reconciliation and Calendar refresh; fixture ticks on their own lock and job name.

**`scripts/run_ea_tick.ps1`, `scripts/schedule_ea_tick.ps1`** (PORT) The outside-the-process exit watch, the alarm, the append-not-truncate log and the battery flags kept; `-Live` dropped (no send path); task `EA-Tick` at 07:00.

**`scripts/ea_doctor.py`** (PORT, from `piper_doctor.py`) Google, Docs, Calendar, the build marker and D-1 instead of the source's own systems.

**`scripts/build_ea_kit.py`** (PORT, from `build_piper_kit.py`) `.claude/` layout; NEVER_COPY adds the Google client and token, the build marker and the fixture database; the gate adds Google's secret shapes; `docs/acceptance/` stays behind.

**`scripts/export_ledger.py`** (PORT) A register snapshot; names make it `records`, so it may only land under `state/records/`.

**`CLAUDE.md`, `INSTALL.md`** (PORT) PIPER's structure (rules first, enforcement named, the privacy paragraph) re-written for this system; CLAUDE.md is distilled and points at blueprint sections instead of importing them.

**`.claude/commands/NAME.md`, `boi.md`, `morning.md`; skills `reality-checker`, `morning-brief`; agents `hugo.md` (from OTIS), `wren.md` (from VERA's delivery role); `docs/PRIVACY.md`** (PORT) Lanes READ and CAPTURE replace PIPER's FAST/STANDARD/FULL; PRIVACY keeps "A Claude Enterprise seat is not a privacy control" verbatim.

**`.gitignore`, `.env.example`, `requirements.txt`, `context/data-classes.json`, `context/systems.json`** (PORT) Re-cut for this system: Google credentials by name, `tzdata` added, Playwright and requests dropped, three data classes, Google hosts only.

**Not recorded here:** `README.md`, `docs/FOR-TAYLOR.md`, `docs/PLAYBOOK.md` and `docs/FIRST-PROMPT.md` are ANNIE's, written in parallel and owned by her, so their hashes would go stale every time she edits. `docs/acceptance/` is generated evidence, regenerated by `scripts/acceptance.py`.
