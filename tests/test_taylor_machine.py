"""Part 2, building on Taylor's machine: the overlay, a pull that never fights him, build mode, lessons, prep.

Each test drives the real code the way it runs on the laptop: scripts and hooks as
subprocesses in a throwaway copy or git clone, judged by exit codes and by the files left
behind. Modules Part 2 added are imported inside the tests that need them, so on the commit
before it each test fails on its own item rather than the whole file failing to import.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tests.test_hardening import env_for, err, payload, repo_copy, run_hook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

import ea_db  # noqa: E402
import register  # noqa: E402

CLAUDE_VARS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")
GIT_ID = ("-c", "user.name=EA test", "-c", "user.email=ea-test@example.invalid", "-c", "commit.gpgsign=false")
RULE = "- [2026-10-01] | Lead every answer with what I owe."
LESSON = "Answer first, then the detail"
UPSTREAM_LINE = "Upstream change from Mike, shipped after Taylor decided things."


def run(argv, cwd=None, env=None, input_bytes=b"", check=False) -> subprocess.CompletedProcess:
    done = subprocess.run([str(a) for a in argv], cwd=str(cwd) if cwd else None, env=env, input=input_bytes,
                          capture_output=True, timeout=300)
    if check and done.returncode != 0:
        raise AssertionError(f"{argv} exited {done.returncode}: {err(done)[-800:]}")
    return done


def out(done: subprocess.CompletedProcess) -> str:
    return done.stdout.decode("utf-8", errors="replace")


def clean_env(root: Path, **extra: str) -> dict:
    """env_for() with nothing pointing the overlay elsewhere, and no Claude Code session markers."""
    env = env_for(root)
    for key in ("EA_OVERLAY", *CLAUDE_VARS):
        env.pop(key, None)
    env.update(extra)
    return env


def own_overlay():
    """os.environ without EA_OVERLAY or fixture mode, so overlay.* reads <base>/state/taylor."""
    kept = {k: v for k, v in os.environ.items() if k not in ("EA_OVERLAY", "EA_FIXTURE_MODE")}
    return mock.patch.dict(os.environ, kept, clear=True)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=cwd, check=check)


def digest_tree(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        h.update(path.relative_to(folder).as_posix().encode("utf-8") + b"\0" + path.read_bytes())
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))


def seed_overlay(root: Path, env: dict) -> Path:
    run([sys.executable, root / "scripts" / "overlay.py", "init"], cwd=root, env=env, check=True)
    return root / "state" / "taylor"


def decide_as_taylor(mine: Path) -> None:
    """What the orchestrator writes when Taylor's own message says `architecture change ok`."""
    phases = json.loads(mine.joinpath("phases.json").read_bytes())
    phases["phases"]["2"] = {"approved": True, "approved_at": "2026-10-01",
                             "said": "architecture change ok: switch on Phase 2"}
    write_json(mine / "phases.json", phases)
    deviations = json.loads(mine.joinpath("deviations.json").read_bytes())
    deviations["deviations"]["D-1"] = {"status": "approved", "decided_at": "2026-10-01"}
    write_json(mine / "deviations.json", deviations)
    rules = mine.joinpath("rules.md").read_bytes().decode("utf-8").replace("No rules yet.", RULE)
    mine.joinpath("rules.md").write_bytes(rules.encode("utf-8"))


# ---------------------------------------------------------------------------
# 1. Taylor's overlay: seeding, naming, migrating what was decided before it
# ---------------------------------------------------------------------------

class OverlaySeedNameMigrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = repo_copy(self.tmp.name)
        shutil.copy2(ROOT / ".gitattributes", self.root / ".gitattributes")
        self.env = clean_env(self.root)

    def overlay(self, *args: str) -> subprocess.CompletedProcess:
        return run([sys.executable, self.root / "scripts" / "overlay.py", *args], cwd=self.root, env=self.env)

    def test_init_seeds_every_file_as_private_and_never_overwrites_one(self):
        tracked = digest_tree(self.root / "context")
        done = self.overlay("init")
        self.assertEqual(done.returncode, 0, err(done))
        mine = self.root / "state" / "taylor"
        for name in ("phases.json", "deviations.json", "identity.json", "lessons.json"):
            self.assertEqual(json.loads(mine.joinpath(name).read_bytes())["ea-class"], "private", name)
        for name in ("CHANGE-LOG.md", "rules.md", "blueprint.md", "proposals.md"):
            self.assertTrue(mine.joinpath(name).read_bytes().startswith(b"<!-- ea-class: private -->"), name)
        baseline = (self.root / "context" / "architecture" / "blueprint.md").read_bytes()
        self.assertTrue(mine.joinpath("blueprint.md").read_bytes().endswith(baseline),
                        "his living blueprint starts as the v1 baseline")
        identity = json.loads(mine.joinpath("identity.json").read_bytes())
        self.assertEqual(Path(identity["repo_root"]).resolve(), self.root.resolve(),
                         "a copy in another folder records where it is")

        mine.joinpath("rules.md").write_bytes(b"<!-- ea-class: private -->\n# Taylor's rules\n" + RULE.encode() + b"\n")
        again = self.overlay("init")
        self.assertEqual(again.returncode, 0, err(again))
        self.assertIn(RULE.encode(), mine.joinpath("rules.md").read_bytes(), "init overwrote his rules")
        self.assertEqual(digest_tree(self.root / "context"), tracked, "init changed a tracked file")

    def test_naming_the_system_changes_no_tracked_file(self):
        command = (self.root / ".claude" / "commands" / "NAME.md").read_bytes()
        done = self.overlay("name", "Max")
        self.assertEqual(done.returncode, 0, err(done))
        identity = json.loads((self.root / "state" / "taylor" / "identity.json").read_bytes())
        self.assertEqual(identity["system_name"], "Max")
        door = (self.root / ".claude" / "skills" / "taylor-front-door" / "SKILL.md").read_bytes().decode("utf-8")
        self.assertIn("\nname: max\n", door)
        body = door.split("-->", 1)[1]
        self.assertNotRegex(body, r"\bNAME\b")
        self.assertIn("--agent <AGENT>", body, "an agent placeholder is not the system's name")
        self.assertEqual((self.root / ".claude" / "commands" / "NAME.md").read_bytes(), command)
        label = run([sys.executable, "-c", "import _health; print(_health.system_label())"],
                    cwd=self.root / ".claude" / "hooks", env=self.env)
        self.assertEqual(out(label).strip(), "Max", err(label))
        self.assertNotEqual(self.overlay("name", "Max Power").returncode, 0, "a name with a space is refused")

    def test_migrate_moves_every_legacy_decision_and_restores_the_tracked_files(self):
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, *GIT_ID, "commit", "-q", "-m", "upstream")
        arch = self.root / "context" / "architecture"
        gate = json.loads(arch.joinpath("phases.json").read_bytes())
        gate["phases"]["2"]["approved"] = True
        gate["phases"]["6"].update(approved=True, deferred=False)
        write_json(arch / "phases.json", gate)
        register_file = json.loads(arch.joinpath("deviations.json").read_bytes())
        register_file["deviations"]["D-1"]["status"] = "approved"
        write_json(arch / "deviations.json", register_file)
        entry = "- [2026-10-01] | Approved D-1 | live Doc writes | Taylor"
        arch.joinpath("CHANGE-LOG.md").write_bytes(arch.joinpath("CHANGE-LOG.md").read_bytes() + f"\n{entry}\n".encode())

        done = self.overlay("migrate", "--restore")
        self.assertEqual(done.returncode, 0, err(done))
        self.assertEqual(out(git(self.root, "status", "--porcelain", "--untracked-files=no")), "",
                         "the tracked files are back to upstream, so the next pull is clean")
        import overlay
        with own_overlay():
            self.assertEqual(overlay.legacy_decisions(self.root), [])
            phases = overlay.phases(self.root)["phases"]
            self.assertTrue(phases["2"]["approved"])
            self.assertTrue(phases["6"]["approved"])
            self.assertFalse(phases["6"]["deferred"], "Phase 6 carried two decisions; both moved")
            self.assertEqual(overlay.deviations(self.root)["deviations"]["D-1"]["status"], "approved")
        self.assertIn(entry.encode(), (self.root / "state" / "taylor" / "CHANGE-LOG.md").read_bytes())

    def test_a_legacy_decision_is_honoured_until_it_is_migrated(self):
        arch = self.root / "context" / "architecture"
        gate = json.loads(arch.joinpath("phases.json").read_bytes())
        gate["phases"]["2"]["approved"] = True
        write_json(arch / "phases.json", gate)
        milo = run([sys.executable, self.root / "scripts" / "team.py", "--agent", "MILO"], cwd=self.root, env=self.env)
        self.assertIn("APPROVED, NOT BUILT YET: MILO", out(milo), err(milo))


# ---------------------------------------------------------------------------
# 1. The proof: two clones, Taylor decides, upstream changes the defaults, he pulls
# ---------------------------------------------------------------------------

class PullNeverFightsTaylor(unittest.TestCase):
    """Clone A is Taylor's laptop, deciding through his overlay. Clone C makes the same decisions
    the way they were made before the overlay, as edits to tracked files: the negative control.
    Clone B is Mike, shipping new defaults to the same three files those edits touch."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        listed = run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, check=True)
        src = base / "src"
        for rel in filter(None, listed.stdout.decode("utf-8").split("\0")):
            if (ROOT / rel).is_file():
                (src / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, src / rel)
        git(src, "init", "-q")
        git(src, "add", "-A")
        git(src, *GIT_ID, "commit", "-q", "-m", "upstream v1")
        git(base, "clone", "-q", "--bare", str(src), "upstream.git")
        cls.taylor, cls.old_way, mike = base / "taylor", base / "old-way", base / "mike"
        for clone in (cls.taylor, cls.old_way, mike):
            git(base, "clone", "-q", "upstream.git", clone.name)

        # A: Taylor approves Phase 2 and D-1, adds a rule, and teaches a preference.
        env = clean_env(cls.taylor)
        decide_as_taylor(seed_overlay(cls.taylor, env))
        cls.lesson = run([sys.executable, cls.taylor / "scripts" / "lessons.py", "record", "--kind", "preference",
                          "--text", LESSON, "--said", "answer first, then the detail"], cwd=cls.taylor, env=env)

        # C: the same approval and rule as edits to the tracked files, uncommitted, as a session left them.
        arch = cls.old_way / "context" / "architecture"
        gate = json.loads(arch.joinpath("phases.json").read_bytes())
        gate["phases"]["2"]["approved"] = True
        write_json(arch / "phases.json", gate)
        claude_md = cls.old_way / "CLAUDE.md"
        claude_md.write_bytes(claude_md.read_bytes() + f"\n{RULE}\n".encode())

        # B: Mike ships new defaults to phases.json, deviations.json and CLAUDE.md, and pushes.
        arch = mike / "context" / "architecture"
        gate = json.loads(arch.joinpath("phases.json").read_bytes())
        gate["phases"]["2"]["name"] = "Meeting capture, processing and filing"
        write_json(arch / "phases.json", gate)
        register_file = json.loads(arch.joinpath("deviations.json").read_bytes())
        register_file["deviations"]["D-9"] = {"status": "proposed", "title": "A deviation Mike proposes later"}
        write_json(arch / "deviations.json", register_file)
        claude_md = mike / "CLAUDE.md"
        claude_md.write_bytes(claude_md.read_bytes() + f"\n{UPSTREAM_LINE}\n".encode())
        git(mike, "add", "-A")
        git(mike, *GIT_ID, "commit", "-q", "-m", "new defaults")
        git(mike, "push", "-q", "origin", "HEAD")

        cls.pull_taylor = git(cls.taylor, "pull", "-q", check=False)
        cls.pull_old_way = git(cls.old_way, "pull", "-q", check=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_taylors_pull_succeeds_and_brings_the_new_defaults(self):
        self.assertEqual(self.lesson.returncode, 0, err(self.lesson))
        self.assertEqual(self.pull_taylor.returncode, 0, err(self.pull_taylor))
        self.assertEqual(out(git(self.taylor, "status", "--porcelain", "--untracked-files=no")), "")
        self.assertIn(UPSTREAM_LINE, (self.taylor / "CLAUDE.md").read_bytes().decode("utf-8"))

    def test_his_approvals_are_still_in_effect_over_the_new_defaults(self):
        milo = run([sys.executable, self.taylor / "scripts" / "team.py", "--agent", "MILO"], cwd=self.taylor,
                   env=clean_env(self.taylor))
        self.assertIn("APPROVED, NOT BUILT YET: MILO", out(milo), err(milo))
        import overlay
        with own_overlay():
            phase = overlay.phases(self.taylor)["phases"]["2"]
            deviations = overlay.deviations(self.taylor)["deviations"]
        self.assertTrue(phase["approved"])
        self.assertEqual(phase["name"], "Meeting capture, processing and filing", "upstream's change arrived too")
        self.assertEqual(deviations["D-1"]["status"], "approved")
        self.assertEqual(deviations["D-9"]["status"], "proposed")

    def test_his_rule_and_his_lesson_load_in_the_next_session(self):
        start = run([sys.executable, self.taylor / ".claude" / "hooks" / "session-start.py"], cwd=self.taylor,
                    env=clean_env(self.taylor), input_bytes=b'{"source": "startup"}')
        self.assertEqual(start.returncode, 0, err(start))
        self.assertIn(RULE, out(start))
        self.assertIn(LESSON, out(start))

    def test_the_old_way_fights_the_same_pull(self):
        self.assertNotEqual(self.pull_old_way.returncode, 0, "negative control: edits to tracked files must collide")
        self.assertIn("would be overwritten", err(self.pull_old_way))


# ---------------------------------------------------------------------------
# 3. Build mode
# ---------------------------------------------------------------------------

def powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


class BuildMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = repo_copy(cls.tmp.name)
        cls.marker = cls.root / "state" / "BUILD_MODE"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        for name in ("BUILD_MODE", "BUILD_MACHINE"):
            (self.root / "state" / name).unlink(missing_ok=True)

    def mark(self, hours: float, host: str | None = None) -> None:
        until = datetime.now(timezone.utc) + timedelta(hours=hours)
        self.marker.write_bytes(f"{host or socket.gethostname()}\n{until:%Y-%m-%dT%H:%M:%SZ}\n".encode("utf-8"))

    def hook(self, name: str, tool: str, tool_input: dict) -> subprocess.CompletedProcess:
        return run_hook(self.root, name, payload(self.root, tool, tool_input), env=clean_env(self.root))

    def switch(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        return run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    self.root / "scripts" / "build_mode.ps1", *args], env=clean_env(self.root, **extra))

    def test_the_switch_refuses_inside_a_claude_session(self):
        if powershell() is None:
            self.skipTest("PowerShell is not installed here")
        for variable in CLAUDE_VARS:
            done = self.switch("on", "-Hours", "2", **{variable: "1"})
            self.assertEqual(done.returncode, 2, f"{variable}: {out(done)}")
            self.assertIn("REFUSED", out(done))
            self.assertFalse(self.marker.exists())

    def test_from_a_terminal_it_switches_on_for_at_most_24_hours_and_off_again(self):
        if powershell() is None:
            self.skipTest("PowerShell is not installed here")
        too_long = self.switch("on", "-Hours", "30")
        self.assertEqual(too_long.returncode, 2, out(too_long))
        self.assertFalse(self.marker.exists())

        on = self.switch("on", "-Hours", "2")
        self.assertEqual(on.returncode, 0, out(on) + err(on))
        raw = self.marker.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "a BOM would make the host name never match")
        host, stamp = raw.decode("utf-8").splitlines()[:2]
        self.assertEqual(host.lower(), socket.gethostname().lower())
        until = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        self.assertLess(abs((until - datetime.now(timezone.utc) - timedelta(hours=2)).total_seconds()), 300)
        import _health
        with mock.patch.object(_health, "REPO_ROOT", str(self.root)):
            mode = _health.build_mode()
        self.assertEqual((mode.on, mode.source), (True, "timed"))
        self.assertIn("BUILD MODE ON until", out(self.switch("status")))

        off = self.switch("off")
        self.assertEqual(off.returncode, 0, out(off))
        self.assertFalse(self.marker.exists())

    def test_in_build_mode_code_and_dev_agents_open_and_nothing_of_taylors(self):
        self.mark(2)
        for name, tool, tool_input, want in [
            ("protect-architecture.py", "Write", {"file_path": str(self.root / "scripts" / "x.py"), "content": "x"}, 0),
            ("protect-architecture.py", "Write", {"file_path": str(self.root / "CLAUDE.md"), "content": "x"}, 0),
            ("protect-architecture.py", "Write",
             {"file_path": str(self.root / "state" / "taylor" / "rules.md"), "content": "x"}, 2),
            ("protect-architecture.py", "Write",
             {"file_path": str(self.root / "context" / "architecture" / "blueprint.md"), "content": "x"}, 2),
            ("protect-architecture.py", "Write", {"file_path": str(self.marker), "content": "x"}, 2),
            ("protect-architecture.py", "Bash", {"command": "powershell -File scripts\\build_mode.ps1 on -Hours 24"}, 2),
            ("require-active-agent.py", "Agent", {"subagent_type": "Explore", "prompt": "map it"}, 0),
            ("require-active-agent.py", "Agent", {"subagent_type": "pr-review-toolkit:code-reviewer", "prompt": "x"}, 0),
            ("require-active-agent.py", "Agent", {"subagent_type": "milo", "prompt": "x"}, 2),
            ("require-active-agent.py", "Workflow", {"name": "deep-research"}, 2),
            ("no-cloud.py", "Bash", {"command": "git push origin master"}, 2),
        ]:
            with self.subTest(hook=name, call=tool_input):
                done = self.hook(name, tool, tool_input)
                self.assertEqual(done.returncode, want, err(done)[-400:])

    def test_off_and_expired_and_another_hosts_marker_open_nothing(self):
        for label, setup in [("no marker", lambda: None), ("expired", lambda: self.mark(-0.1)),
                             ("another host", lambda: self.mark(2, host="SOME-OTHER-LAPTOP"))]:
            self.setUp()
            setup()
            for name, tool, tool_input in [
                ("require-active-agent.py", "Agent", {"subagent_type": "Explore", "prompt": "map it"}),
                ("protect-architecture.py", "Write", {"file_path": str(self.root / "scripts" / "x.py"), "content": "x"}),
                ("protect-architecture.py", "Write", {"file_path": str(self.root / "CLAUDE.md"), "content": "x"}),
            ]:
                with self.subTest(marker=label, hook=name, call=tool_input):
                    self.assertEqual(self.hook(name, tool, tool_input).returncode, 2)

    def test_the_roll_call_the_status_line_and_the_doctor_all_say_so(self):
        import _health
        import ea_doctor

        self.mark(2)
        roll = run([sys.executable, self.root / ".claude" / "hooks" / "team-rollcall.py"], input_bytes=b"{}",
                   env=clean_env(self.root))
        self.assertTrue(json.loads(out(roll))["systemMessage"].startswith("=" * 60 + "\nBUILD MODE until "), out(roll))
        bar = run([sys.executable, self.root / ".claude" / "hooks" / "statusline-ea.py"], input_bytes=b"{}",
                  env=clean_env(self.root))
        self.assertIn("BUILD MODE until ", out(bar))
        report = ea_doctor.Report()
        with mock.patch.object(_health, "REPO_ROOT", str(self.root)):
            ea_doctor.check_location(report)
        self.assertIn(("WARN", "build mode"), [(v, n) for v, n, _ in report.lines])

        self.mark(-0.1)
        roll = run([sys.executable, self.root / ".claude" / "hooks" / "team-rollcall.py"], input_bytes=b"{}",
                   env=clean_env(self.root))
        self.assertNotIn("BUILD", json.loads(out(roll))["systemMessage"])


# ---------------------------------------------------------------------------
# 4. Lessons
# ---------------------------------------------------------------------------

class Lessons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = repo_copy(self.tmp.name)
        self.env = clean_env(self.root)
        seed_overlay(self.root, self.env)
        run([sys.executable, self.root / "scripts" / "register.py", "seed", "--roster"], cwd=self.root, env=self.env,
            check=True)

    def lessons(self, *args: str) -> subprocess.CompletedProcess:
        return run([sys.executable, self.root / "scripts" / "lessons.py", *args], cwd=self.root, env=self.env)

    def record(self, kind: str, text: str, said: str = "", *extra: str) -> dict:
        done = self.lessons("record", "--kind", kind, "--text", text, "--said", said or text, *extra)
        self.assertEqual(done.returncode, 0, err(done))
        return json.loads(out(done))

    def next_session(self) -> str:
        done = run([sys.executable, self.root / ".claude" / "hooks" / "session-start.py"], cwd=self.root,
                   env=self.env, input_bytes=b'{"source": "startup"}')
        self.assertEqual(done.returncode, 0, err(done))
        return out(done)

    def questions(self) -> int:
        conn = ea_db.connect(self.root / "state" / "ea.db", read_only=True)
        try:
            return conn.execute("SELECT COUNT(*) FROM needs_input WHERE source_kind = 'lesson' AND status = 'open'"
                                ).fetchone()[0]
        finally:
            conn.close()

    def test_a_preference_is_in_effect_from_the_next_session(self):
        self.assertNotIn(LESSON, self.next_session())
        got = self.record("preference", LESSON, "answer first, then the detail")
        self.assertEqual((got["status"], got["active"]), ("active", True))
        self.assertIn(LESSON, self.next_session())

    def test_a_price_becomes_one_question_and_never_a_lesson_in_effect(self):
        said = "the corporate package is $45 now"
        first = self.record("preference", "The corporate package is $45 now", said)
        self.assertEqual((first["kind"], first["active"], first["status"]), ("rule-candidate", False, "asked"))
        self.assertEqual(self.questions(), 1)
        again = self.record("preference", "The corporate package is $45 now", said)
        self.assertEqual(again["ref"], first["ref"])
        self.assertEqual(self.questions(), 1, "a repeat asks nothing more")
        loaded = self.next_session()
        self.assertNotIn("$45", loaded)
        self.assertIn("NOT in effect", loaded)
        self.assertIn("Waiting for your answer", out(self.lessons("list")))

    def test_his_yes_adopts_it_and_his_no_keeps_another_out(self):
        price = self.record("rule-candidate", "Corporate package is $45 per guest", "it is $45 now",
                            "--about", "corporate package price")
        policy = self.record("preference", "Deposit is 25 percent for buyouts", "deposit is 25 percent")
        self.assertEqual(self.lessons("answer", price["ref"], "--yes").returncode, 0)
        self.assertEqual(self.lessons("answer", policy["ref"], "--no").returncode, 0)
        loaded = self.next_session()
        self.assertIn("Corporate package is $45 per guest", loaded)
        self.assertIn("rule, adopted", loaded)
        self.assertNotIn("Deposit is 25 percent", loaded)
        self.assertEqual(self.questions(), 0, "both questions are resolved")
        self.assertIn("Kept out (you said no)", out(self.lessons("list")))

    def test_a_rule_only_inferred_from_his_edits_asks_on_the_second_instance(self):
        first = self.record("rule-candidate", "Minimum spend for the patio is 2000", "", "--source", "edit",
                            "--about", "patio minimum spend")
        self.assertEqual((first["status"], self.questions()), ("candidate", 0))
        second = self.record("rule-candidate", "Patio minimum spend is 2000", "", "--source", "edit",
                             "--about", "patio minimum spend")
        self.assertEqual((second["ref"], second["status"], self.questions()), (first["ref"], "asked", 1))

    def test_forget_retires_a_lesson(self):
        got = self.record("preference", LESSON)
        self.assertEqual(self.lessons("forget", got["ref"]).returncode, 0)
        self.assertNotIn(LESSON, self.next_session())

    def test_forgetting_a_waiting_rule_withdraws_its_question(self):
        held = self.record("preference", "The corporate package is $45 now")
        self.assertEqual(self.questions(), 1)
        done = self.lessons("forget", held["ref"])
        self.assertEqual(done.returncode, 0, err(done))
        self.assertEqual(self.questions(), 0, "a forgotten rule must not still be asked in /morning")

    def test_the_register_will_not_close_a_lesson_question_and_lose_the_answer(self):
        held = self.record("preference", "The corporate package is $45 now")
        done = run([sys.executable, self.root / "scripts" / "register.py", "needs-input", "resolve", held["question"],
                    "--answer", "yes"], cwd=self.root, env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(f"lessons.py answer {held['ref']}", err(done))
        self.assertEqual(self.questions(), 1, "the question stays open for lessons.py answer")

    def test_an_identity_lesson_is_a_register_alias(self):
        got = self.record("identity", "", "that one's Kaed", "--person", "kaed", "--alias", "Cade")
        self.assertTrue(got["active"])
        resolved = run([sys.executable, self.root / "scripts" / "register.py", "resolve-person", "Cade"],
                       cwd=self.root, env=self.env)
        self.assertIn("kaed", out(resolved))

    def test_only_reed_records_and_anyone_reads(self):
        record = 'python scripts/lessons.py record --kind preference --text "x"'
        for body, want in [
            (payload(self.root, "Bash", {"command": record}), 2),
            (payload(self.root, "PowerShell", {"command": record}, agent_id="a1", agent_type="page"), 2),
            (payload(self.root, "Bash", {"command": record}, agent_id="a2", agent_type="reed"), 0),
            (payload(self.root, "Bash", {"command": "python scripts/lessons.py list"}), 0),
        ]:
            with self.subTest(body=body):
                done = run_hook(self.root, "require-lessons-agent.py", body, env=self.env)
                self.assertEqual(done.returncode, want, err(done)[-300:])

    def test_the_session_context_stays_inside_its_limit(self):
        import lessons
        with own_overlay(), mock.patch.dict(os.environ, {"EA_OVERLAY": str(self.root / "state" / "taylor")}):
            data = lessons.load()
            for n in range(150):
                data["lessons"].append({"ref": f"L-{n + 1:04d}", "kind": "preference", "status": "active",
                                        "text": f"Preference number {n} about how the brief reads, kept a little long",
                                        "created_at": f"2026-10-01T00:{n % 60:02d}:00+00:00", "count": 1,
                                        "said": [], "history": []})
            lessons.save(data)
        loaded = self.next_session()
        self.assertLess(len(loaded), 9100)
        self.assertIn("more in effect", loaded)


# ---------------------------------------------------------------------------
# 6. require-approval never creates an empty register
# ---------------------------------------------------------------------------

class ApprovalNeverCreatesTheRegister(unittest.TestCase):
    def test_a_send_with_no_register_is_refused_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            done = run_hook(root, "require-approval.py",
                            payload(root, "mcp__gmail__send_message", {"to": ["casey@gretabar.com"], "body": "x"}),
                            env=clean_env(root))
            self.assertEqual(done.returncode, 2, err(done)[-300:])
            self.assertFalse((root / "state" / "ea.db").exists(), "the gate created an empty register")


# ---------------------------------------------------------------------------
# 2. Prep: blueprint s.10's order, from the register and the stored Doc snapshot
# ---------------------------------------------------------------------------

class DeepPrep(unittest.TestCase):
    def setUp(self):
        import docs_read

        live = own_overlay()  # a live register's Doc, so not fixture mode, whoever runs the suite
        live.start()
        self.addCleanup(live.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "prep.db"
        fixtures = ROOT / "tests" / "fixtures"
        self.smap = json.loads((fixtures / "kaed_section_map.json").read_bytes())
        self.body, self.sha = docs_read.snapshot(docs_read.parse(
            json.loads((fixtures / "kaed_fixture_document.json").read_bytes()), self.smap))
        conn = ea_db.connect(self.db)
        try:
            ea_db.migrate(conn)
            register.seed_roster(conn)
            add = lambda **kw: register.add_action(conn, counterpart="kaed", instruction_date="2026-10-01", **kw)  # noqa: E731
            self.mine = add(text="Send Kaed the patio staffing numbers", owner="taylor", due="2026-10-06")["ref"]
            self.theirs = add(text="Bring the bar inventory variance", owner="kaed", due="2026-10-07")["ref"]
            self.question = add(text="Draft the weekend rota", owner="kaed", due="unresolved")["needs_input"]
            register.add_topic(conn, person_key="kaed", text="Patio heaters", instruction_date="2026-10-01")
            kaed = conn.execute("SELECT id FROM people WHERE key = 'kaed'").fetchone()["id"]
            with conn:
                conn.execute("INSERT INTO docs (doc_id, person_id, title, url, fixture, section_map_json, map_confirmed,"
                             " role, created_at) VALUES ('DOC1', ?, 'Kaed x Taylor', 'https://docs.google.com/document/d/DOC1',"
                             " 0, ?, 1, 'running_1on1', ?)", (kaed, json.dumps(self.smap), ea_db.now_iso()))
        finally:
            conn.close()

    def snapshot(self, body: str, taken_at: str) -> None:
        conn = ea_db.connect(self.db)
        try:
            with conn:
                conn.execute("INSERT INTO doc_snapshots (doc_id, revision_id, parsed_json, sha256, taken_at)"
                             " VALUES ('DOC1', 'R1', ?, ?, ?)", (body, self.sha, taken_at))
        finally:
            conn.close()

    def brief(self) -> str:
        import prep

        conn = ea_db.connect(self.db, read_only=True)
        try:
            return prep.render(prep.build(conn, "Kaed"))
        finally:
            conn.close()

    def test_taylors_part_first_then_theirs_topics_the_doc_the_next_1on1_and_the_link(self):
        self.snapshot(self.body, ea_db.now_iso())
        shown = self.brief()
        order = ["You owe Kaed", "You need to answer or decide", "Kaed owes you", "Topics for the next 1:1",
                 "Carried forward in the Doc", "Last 1:1", "Next 1:1:", "Doc: https://docs.google.com/document/d/DOC1"]
        lines = shown.splitlines()
        at = [next((i for i, line in enumerate(lines) if line.startswith(heading)), -1) for heading in order]
        self.assertNotIn(-1, at, shown)
        self.assertEqual(at, sorted(at), shown)
        self.assertLess(shown.find(self.mine), shown.find("Kaed owes you"))
        self.assertGreater(shown.find(self.theirs), shown.find("Kaed owes you"))
        self.assertIn("Seed fixture action", shown, "a row the Doc carries that the register does not list")
        self.assertIn("Done: Past fixture action", shown, "what the last 1:1 recorded")

    def test_with_no_snapshot_it_says_the_doc_is_not_read_yet(self):
        self.assertIn("From the Doc: not read yet", self.brief())

    def test_an_unreadable_snapshot_is_reported_never_shown_as_nothing(self):
        self.snapshot("{", ea_db.now_iso())
        self.assertIn("could not be read", self.brief())

    def test_the_read_date_is_taylors_local_date(self):
        self.snapshot(self.body, "2026-10-02T02:30:00+00:00")  # 22:30 on Thursday in Toronto
        with mock.patch.object(register, "identity", lambda: {"timezone": "America/Toronto"}):
            shown = self.brief()
        self.assertIn("as last read Thu 2026-10-01", shown)


if __name__ == "__main__":
    unittest.main()
