"""The security hardening review of 0c3fe45..13fdd94, one test per finding, against the real hooks.

Each test drives the hooks the way Claude Code does (a subprocess, the payload on stdin,
judged by the exit code: Claude Code blocks only on exit 2) in a throwaway copy of the
repo, with the reviewers' own reproduction payloads. Modules this review added are
imported inside the tests that need them, so on the commit before it each test fails on
its own finding rather than the whole file failing to import.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

LONE = "\ud83d"  # a lone high surrogate; json.dumps writes it as the escape \ud83d
GATES = ("protect-architecture.py", "no-cloud.py", "require-delivery-agent.py", "require-privacy-agent.py",
         "require-active-agent.py", "confine-read-only-agent.py", "classify-and-place.py", "require-dispatch.py",
         "require-approval.py")


def repo_copy(tmp: str, name: str = "ea") -> Path:
    root = Path(tmp) / name
    for part in (".claude", "context", "scripts", "tests"):
        shutil.copytree(ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "state").mkdir()
    return root


def env_for(root: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("EA_DB", "EA_FIXTURE_MODE", "EA_AGENT")}
    env.update(EA_ROOT=str(root), CLAUDE_PROJECT_DIR=str(root), PYTHONIOENCODING="utf-8",
               PYTHONDONTWRITEBYTECODE="1", **extra)
    return env


def payload(root: Path, tool: str, tool_input: dict, **extra) -> dict:
    """Shaped like a live PreToolUse payload. No agent_id: the main thread, unless extra says otherwise."""
    return {"session_id": "hardening", "transcript_path": str(root / "none.jsonl"), "cwd": str(root),
            "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, **extra}


def run_hook(root: Path, name: str, body, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run one hook as Claude Code does. `body` is a payload dict, or raw text for a malformed one."""
    text = body if isinstance(body, str) else json.dumps(body)
    return subprocess.run([sys.executable, str(root / ".claude" / "hooks" / name)], input=text.encode("utf-8"),
                          capture_output=True, env=env or env_for(root), cwd=str(root), timeout=120)


def err(done: subprocess.CompletedProcess) -> str:
    return done.stderr.decode("utf-8", errors="replace")


def transcript(root: Path, rows: list, name: str) -> str:
    """A transcript file; a str row is written as it is, so a test can hold a broken line."""
    path = root / f"{name}.jsonl"
    path.write_bytes(("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n").encode("utf-8"))
    return str(path)


def git_bash() -> str | None:
    for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(candidate).exists():
            return candidate
    found = shutil.which("bash")
    return found if found and "system32" not in found.lower() else None


class CopyPerClass(unittest.TestCase):
    """One throwaway repo for the class: the hooks' audit rows land there, never in the live register."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = repo_copy(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


# ---------------------------------------------------------------------------
# A. Fail closed: Claude Code blocks only on exit 2
# ---------------------------------------------------------------------------

class FailClosed(CopyPerClass):
    def test_a_lone_surrogate_in_a_refused_command_still_refuses(self):
        # The reviewers' drive_hooks.py: the refusal itself raised UnicodeEncodeError, the hook
        # exited 1, and the command it was refusing ran and stamped reviewer SAGE.
        review = 'python scripts/privacy_review.py --approve state/proposals/x.json --reason "ok" # ' + LONE
        for name, body in [
            ("require-privacy-agent.py", payload(self.root, "Bash", {"command": review})),
            ("require-privacy-agent.py", payload(self.root, "PowerShell", {"command": review},
                                                 agent_id="a1", agent_type="wren")),
            ("require-delivery-agent.py", payload(self.root, "Bash", {
                "command": "python scripts/docs_edit.py add-topic --doc D --proposal p.json # " + LONE})),
        ]:
            done = run_hook(self.root, name, body)
            self.assertEqual(done.returncode, 2, f"{name}: {err(done)[-300:]}")
            self.assertIn("BLOCKED", err(done))

    def test_input_nested_thousands_deep_is_unreadable_not_a_crash(self):
        nested = '{"tool_name": "Bash", "tool_input": {"command": "x"}, "x": ' + "[" * 100000 + "]" * 100000 + "}"
        for name in ("require-delivery-agent.py", "require-privacy-agent.py", "require-dispatch.py"):
            done = run_hook(self.root, name, nested)
            self.assertEqual(done.returncode, 2, f"{name}: {err(done)[-300:]}")

    def test_every_gate_refuses_when_its_helpers_cannot_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            (root / ".claude" / "hooks" / "_gate.py").write_bytes(b"def broken(:\n")
            for name in GATES:
                done = run_hook(root, name, payload(root, "Bash", {"command": "echo hi"}))
                self.assertEqual(done.returncode, 2, f"{name} let the call through: exit {done.returncode}")

    def test_a_broken_team_file_does_not_refuse_the_doctor(self):
        # A.4: team.py imported for every shell call made a broken team.py refuse
        # `python scripts/ea_doctor.py`, the command every refusal tells Taylor to run.
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            (root / "scripts" / "team.py").write_bytes(b"def broken(:\n")
            doctor = run_hook(root, "require-active-agent.py",
                              payload(root, "Bash", {"command": "python scripts/ea_doctor.py"}))
            dispatch = run_hook(root, "require-active-agent.py", payload(root, "Agent", {"subagent_type": "reed"}))
        self.assertEqual(doctor.returncode, 0, err(doctor))
        self.assertEqual(dispatch.returncode, 2, "a dispatch that cannot be checked must still be refused")

    def test_the_settings_turn_any_other_exit_into_a_block(self):
        # A.2, belt and braces: whatever a gate's process does (a crash before its own catch-all,
        # a missing interpreter), the command in settings.json can only end in 0 or 2.
        bash = git_bash()
        if bash is None:
            self.skipTest("Git Bash is not installed here; Claude Code on Windows runs hooks with it")
        settings = json.loads((ROOT / ".claude" / "settings.json").read_bytes().decode("utf-8"))
        commands = [entry["command"] for group in settings["hooks"]["PreToolUse"] for entry in group["hooks"]
                    if "announce-dispatch.py" not in entry["command"]]
        self.assertEqual(len(commands), 10)
        with tempfile.TemporaryDirectory() as tmp:
            stub_root = Path(tmp)
            for folder in (".claude/hooks", "scripts"):
                (stub_root / folder).mkdir(parents=True)
            for code, want in ((0, 0), (1, 2), (2, 2), (3, 2), (127, 2)):
                for path in [*(stub_root / ".claude" / "hooks" / g for g in GATES),
                             stub_root / "scripts" / "validate_content_rules.py"]:
                    path.write_bytes(f"import sys\nsys.stderr.write('stub\\n')\nsys.exit({code})\n".encode("utf-8"))
                for command in commands:
                    done = subprocess.run([bash, "-c", command], input=b"{}", capture_output=True,
                                          env={**os.environ, "CLAUDE_PROJECT_DIR": stub_root.as_posix()}, timeout=60)
                    self.assertEqual(done.returncode, want, f"exit {code} -> {done.returncode}: {command[:70]}")
                    lines = err(done).strip().splitlines()
                    if code in (0, 2):
                        self.assertEqual(lines, ["stub"], "a gate's own 0 or 2 passes through untouched")
                    else:
                        self.assertIn("could not run", lines[-1])


# ---------------------------------------------------------------------------
# B. A dispatch counts only on positive evidence that the agent ran
# ---------------------------------------------------------------------------

REFUSAL = "PreToolUse:Agent hook error: [python require-active-agent.py]: NOT SWITCHED ON YET: MILO"


def _rows():
    user = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "process my 1:1 with Kaed"}]}}
    earlier = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "earlier request"}]}}
    earlier_dispatch = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t0", "name": "Agent", "input": {"subagent_type": "reed"}}]}}
    earlier_answer = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t0", "content": [{"type": "text", "text": "done"}]}]}}
    call = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "milo"}}]}}

    def refusal(text):
        return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                                                         "content": [{"type": "text", "text": text}]}]}}

    # The reviewers' drive_transcript.py, A to H.
    return {
        "A refusal row parsed": [user, call, refusal(REFUSAL)],
        "B refusal row truncated mid-flush": [user, call, json.dumps(refusal(REFUSAL))[:60]],
        "C refusal text wrapped in a tag": [user, call, refusal("<tool_use_error>" + REFUSAL + "</tool_use_error>")],
        "D refusal row not written yet": [user, call],
        "E user row unparseable, earlier dispatch": [earlier, earlier_dispatch, earlier_answer,
                                                     json.dumps(user)[:40], call, refusal(REFUSAL)],
        "F errored result with text null": [user, {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t9", "is_error": True, "content": [{"type": "text", "text": None}]}]}}],
        "G assistant row with message null": [user, {"type": "assistant", "message": None}],
        "H one deeply nested line": [user, '{"type":"assistant","x":' + "[" * 100000 + "]" * 100000 + "}"],
    }


class PositiveEvidence(CopyPerClass):
    def write_payload(self, path: str) -> dict:
        return payload(self.root, "Write", {"file_path": str(self.root / "output" / "x.md"), "content": "x"},
                       transcript_path=path)

    def test_the_reviewers_transcripts_all_block_the_solo_write(self):
        for label, rows in _rows().items():
            path = transcript(self.root, rows, label[0])
            done = run_hook(self.root, "require-dispatch.py", self.write_payload(path))
            self.assertEqual(done.returncode, 2, f"{label}: exit {done.returncode} {err(done)[-200:]}")

    def test_a_dispatch_that_answered_lets_the_write_through(self):
        rows = [{"type": "user", "message": {"content": [{"type": "text", "text": "capture it"}]}},
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "reed"}}]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "Captured."}]}]}}]
        done = run_hook(self.root, "require-dispatch.py", self.write_payload(transcript(self.root, rows, "answered")))
        self.assertEqual(done.returncode, 0, err(done))

    def test_the_roll_call_does_not_report_a_dispatch_it_cannot_prove(self):
        for label in ("B refusal row truncated mid-flush", "C refusal text wrapped in a tag",
                      "E user row unparseable, earlier dispatch"):
            path = transcript(self.root, _rows()[label], "rollcall-" + label[0])
            done = subprocess.run([sys.executable, str(self.root / ".claude" / "hooks" / "team-rollcall.py")],
                                  input=json.dumps({"transcript_path": path}).encode("utf-8"), capture_output=True,
                                  env=env_for(self.root), timeout=60)
            message = json.loads(done.stdout.decode("utf-8"))["systemMessage"]
            self.assertEqual(done.returncode, 0)
            self.assertNotIn("dispatched)", message, f"{label}: {message}")
            self.assertIn("TEAM: UNVERIFIED", message, label)


# ---------------------------------------------------------------------------
# C. Namespaces: only a bare name or this repo's ea: prefix is one of ours
# ---------------------------------------------------------------------------

class Namespaces(CopyPerClass):
    def test_another_plugins_agents_are_not_ours(self):
        review = 'python scripts/privacy_review.py --approve state/proposals/x.json --reason "ok"'
        edit = "python scripts/docs_edit.py add-topic --doc D --proposal p.json"
        for name, body in [
            ("require-privacy-agent.py", payload(self.root, "Bash", {"command": review},
                                                 agent_id="a1", agent_type="otherplugin:sage")),
            ("require-delivery-agent.py", payload(self.root, "Bash", {"command": edit}, agent_id="a1", agent_type="x:wren")),
        ]:
            done = run_hook(self.root, name, body)
            self.assertEqual(done.returncode, 2, f"{name} let another plugin's agent through")
        dispatch = run_hook(self.root, "require-active-agent.py",
                            payload(self.root, "Agent", {"subagent_type": "otherplugin:sage"}))
        self.assertEqual(dispatch.returncode, 2)
        self.assertIn("NOT ON THIS TEAM", err(dispatch))
        ours = run_hook(self.root, "require-active-agent.py", payload(self.root, "Agent", {"subagent_type": "ea:reed"}))
        self.assertEqual(ours.returncode, 0, err(ours))


# ---------------------------------------------------------------------------
# D. One shared parser: what a shell command runs
# ---------------------------------------------------------------------------

CLAUDE_FORMS = [
    '$out = claude -p "summarize"', 'cmd /c "claude -p hi"', 'Start-Process -FilePath claude -ArgumentList "-p hi"',
    "env claude -p hi", "timeout 600 claude -p hi", "powershell -c claude -p hi", "x=$(claude -p hi)", "(claude -p hi)",
    "sleep 1 & claude -p hi", '"claude -p hi" | iex', "npx -y @anthropic-ai/claude-code -p hi",
]


class SharedParser(CopyPerClass):
    def test_every_reviewed_way_to_start_claude_is_refused(self):
        for command in CLAUDE_FORMS:
            done = run_hook(self.root, "require-active-agent.py", payload(self.root, "PowerShell", {"command": command}))
            self.assertEqual(done.returncode, 2, f"not refused: {command}")
        for command in ("claude --version", 'python scripts/register.py add-topic --person kaed --text "Claude -p rota"'):
            done = run_hook(self.root, "require-active-agent.py", payload(self.root, "Bash", {"command": command}))
            self.assertEqual(done.returncode, 0, f"refused a near-miss: {command}")

    def test_the_parser_survives_noise_in_bounded_time(self):
        # A parser that raises makes every gate built on it refuse that command; one that is
        # slow runs the hook into Claude Code's timeout, which lets the call through.
        import random
        import time

        import _shell
        rng = random.Random(7)
        alphabet = "ab $()`'\"\\;|&<>{}#\n-=:/.@^%*!cmdpythonclaude\u2018\u201c\u2013"
        for _ in range(3000):
            noise = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
            _shell.invocations(noise)
            _shell.runs_script(noise, "docs_edit")
            _shell.writes_by_redirect(noise)
        for hostile in ("$(" * 50000, "`" * 50000, "(" * 50000, "a;" * 50000, "powershell -c " * 3000,
                        "x=$(" * 20000 + "claude -p hi"):
            start = time.monotonic()
            _shell.invocations(hostile)
            _shell.runs_script(hostile, "docs_edit")
            self.assertLess(time.monotonic() - start, 10, f"too slow on {hostile[:12]!r}")

    def test_the_script_is_matched_and_not_a_table_that_contains_its_name(self):
        read = ('python -c "import sqlite3; c=sqlite3.connect(\'state/ea.db\'); '
                'print(c.execute(\'SELECT * FROM privacy_reviews\').fetchall())"')
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            done = run_hook(root, "require-privacy-agent.py",
                            payload(root, "Bash", {"command": read}, agent_id="a1", agent_type="hugo"))
            logs = [line for p in (root / "logs").glob("audit-*.jsonl") for line in p.read_text("utf-8").splitlines()]
        self.assertEqual(done.returncode, 0, err(done))
        self.assertFalse([line for line in logs if "require-privacy-agent" in line],
                         "a command that runs no review must leave no audit row, least of all an allow")
        for command in ("$r = python scripts/privacy_review.py --hold x.json --reason r",
                        'cmd /c "python scripts\\privacy_review.py --hold x.json --reason r"',
                        "python3.14 scripts/privacy_review.py --hold x.json --reason r",
                        "uv run scripts/privacy_review.py --hold x.json --reason r"):
            done = run_hook(self.root, "require-privacy-agent.py",
                            payload(self.root, "Bash", {"command": command}, agent_id="a1", agent_type="hugo"))
            self.assertEqual(done.returncode, 2, f"not refused: {command}")


# ---------------------------------------------------------------------------
# E. The team switch: accepted is a date, a deferral is lifted explicitly
# ---------------------------------------------------------------------------

def _team(phases: dict | None = None, builds: dict | None = None):
    import team
    roster = json.loads((ROOT / "context" / "roster-agents.json").read_bytes().decode("utf-8"))
    phase_file = json.loads((ROOT / "context" / "architecture" / "phases.json").read_bytes().decode("utf-8"))
    deviations = json.loads((ROOT / "context" / "architecture" / "deviations.json").read_bytes().decode("utf-8"))
    for key, change in (phases or {}).items():
        phase_file["phases"][key] = {**phase_file["phases"][key], **change}
    roster["build_record"] = {**roster.get("build_record", {}), **(builds or {})}
    return team.Team(roster, phase_file, deviations)


class TeamSwitch(unittest.TestCase):
    def test_accepted_must_be_a_date(self):
        import team
        for value in ("no", "pending", "false", "TBD"):
            with self.assertRaises(team.TeamUnreadable, msg=f"accepted {value!r} switched Phase 2 on"):
                _team(phases={"2": {"approved": True}}, builds={"phase 2": {"accepted": value}}).status("milo")
        self.assertTrue(_team(phases={"2": {"approved": True}},
                              builds={"phase 2": {"accepted": "2026-11-01"}}).status("milo").active)

    def test_a_deferred_phase_stays_off_while_the_deferral_stands(self):
        held = _team(phases={"6": {"approved": True, "deferred": True}}, builds={"phase 6": {"accepted": "2026-11-01"}})
        self.assertFalse(held.status("tally").active)
        lifted = _team(phases={"6": {"approved": True, "deferred": False}}, builds={"phase 6": {"accepted": "2026-11-01"}})
        self.assertTrue(lifted.status("tally").active)


# ---------------------------------------------------------------------------
# F. The privacy screen reads words as a person sees them
# ---------------------------------------------------------------------------

class PrivacyScreen(unittest.TestCase):
    def test_unicode_names_and_invisible_characters(self):
        import privacy_screen
        for text in ("Zo\u00eb's raise", "\u00c9ric's salary", "give Zo\u00e9 a raise", "raise for Zo\u00eb",
                     "med\u00adical leave", "medi\u200bcal leave"):
            self.assertIsNotNone(privacy_screen.screen(text), text)
        for text in ("manager bonus structure", "Christmas lights", "holiday party bookings",
                     "Zo\u00eb's bonus structure", "Raise prices on the patio"):
            self.assertIsNone(privacy_screen.screen(text), text)


# ---------------------------------------------------------------------------
# G. SAGE's verdict is read again at the moment of the write
# ---------------------------------------------------------------------------

class StampAtTheWrite(unittest.TestCase):
    def test_a_hold_recorded_while_the_doc_is_read_stops_the_write(self):
        import docs_edit
        import ea_db

        sha = "e" * 64
        proposal = {"kind": "add-topic", "text": "Shift swap to cover a medical appointment", "item_ref": "T-0001",
                    "privacy_review": "required", "privacy_category": "health", "doc_id": "FIXTURE_DOC",
                    "section": "agenda", "_index_id": None, "_sha256": sha}
        writes = []
        with tempfile.TemporaryDirectory() as tmp:
            conn = ea_db.connect(Path(tmp) / "r.db")
            try:
                ea_db.migrate(conn)

                def stamp(verdict):
                    with conn:
                        conn.execute("INSERT INTO privacy_reviews (proposal_path, proposal_sha256, item_ref, verdict,"
                                     " category, reason, reviewer, ts) VALUES ('p', ?, 'T-0001', ?, 'health', 'r',"
                                     " 'SAGE', ?)", (sha, verdict, ea_db.now_iso()))

                def fetch(service, doc_id):
                    stamp("hold")  # SAGE's hold lands while WREN is reading the Doc
                    return {"revisionId": "R1"}

                stamp("approve")
                with mock.patch.object(docs_edit, "check_proposal", return_value=proposal), \
                        mock.patch.object(docs_edit, "check_allowlist",
                                          return_value={"section_map_json": "{}", "title": "t"}), \
                        mock.patch.object(docs_edit.docs_read, "fetch", side_effect=fetch), \
                        mock.patch.object(docs_edit.docs_read, "parse", return_value={}), \
                        mock.patch.object(docs_edit, "plan", return_value=[{"insertText": {"text": "x"}}]), \
                        mock.patch.object(docs_edit, "_batch", side_effect=lambda *a, **k: writes.append(a) or {}), \
                        mock.patch.object(docs_edit._audit, "record"):
                    try:
                        outcome = docs_edit.apply("add-topic", Path(tmp) / "p.json", doc_arg=None,
                                                  simulate_stale=False, service=object(), conn=conn)
                    except Exception as exc:  # noqa: BLE001
                        outcome = {"exit": f"raised {exc.__class__.__name__}"}  # the write is what is judged
            finally:
                conn.close()
        self.assertEqual(writes, [], "the Doc was written after SAGE recorded a hold")
        self.assertEqual(outcome.get("exit"), docs_edit.EXIT_REFUSED)


# ---------------------------------------------------------------------------
# H. LARK is read only by mechanism, not by prose
# ---------------------------------------------------------------------------

class LarkConfined(CopyPerClass):
    def lark(self, tool: str, tool_input: dict) -> subprocess.CompletedProcess:
        return run_hook(self.root, "confine-read-only-agent.py",
                        payload(self.root, tool, tool_input, agent_id="a7", agent_type="lark"))

    def test_lark_runs_its_list_and_nothing_else(self):
        self.assertEqual(self.lark("Bash", {"command": "python scripts/prep.py --person Kaed"}).returncode, 0)
        self.assertEqual(self.lark("Bash", {"command": "python scripts/register.py owed --person kaed"}).returncode, 0)
        for tool, tool_input in [
            ("Bash", {"command": "python scripts/register.py add-action --text x --owner kaed --due 2026-10-02"}),
            ("Bash", {"command": "python scripts/prep.py --person Kaed > notes.txt"}),
            ("Bash", {"command": 'python -c "import register"'}),
            ("Bash", {"command": "python scripts/docs_edit.py add-topic --doc D --proposal p.json"}),
            ("WebFetch", {"url": "https://example.com"}),
        ]:
            done = self.lark(tool, tool_input)
            self.assertEqual(done.returncode, 2, f"LARK ran {tool_input}")
            self.assertIn("is read only", err(done))
        other = run_hook(self.root, "confine-read-only-agent.py", payload(self.root, "Bash", {
            "command": "python scripts/register.py add-action --text x --owner kaed --due 2026-10-02"},
            agent_id="a8", agent_type="reed"))
        self.assertEqual(other.returncode, 0, "only a read-only agent is confined")

    def test_the_confinement_is_wired(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_bytes().decode("utf-8"))
        wired = [group["matcher"] for group in settings["hooks"]["PreToolUse"] for entry in group["hooks"]
                 if "confine-read-only-agent.py" in entry["command"]]
        self.assertTrue(wired and "Bash" in wired[0] and "Write" in wired[0])


# ---------------------------------------------------------------------------
# I. prep.py writes no data, says so precisely, and refuses what it cannot read
# ---------------------------------------------------------------------------

class PrepSideEffects(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def prep(self, db: Path, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k not in ("EA_FIXTURE_MODE", "EA_ROOT")}
        env.update(EA_DB=str(db), PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "prep.py"), "--person", "kaed", *args],
                              capture_output=True, env=env, timeout=60)

    def register(self, folder: Path, migrated: bool = True) -> Path:
        import ea_db
        import register
        folder.mkdir(parents=True, exist_ok=True)
        db = folder / "ea.db"
        conn = ea_db.connect(db)
        try:
            if migrated:
                ea_db.migrate(conn)
                register.seed_roster(conn)
        finally:
            conn.close()
        return db

    def test_an_unmigrated_register_is_refused_with_its_own_exit_code(self):
        db = self.register(Path(self.tmp.name) / "fresh", migrated=False)
        done = self.prep(db)
        self.assertEqual(done.returncode, 3, err(done))
        self.assertIn("not set up", err(done))

    def test_a_hash_in_the_folder_name_cannot_drop_read_only(self):
        parent = Path(self.tmp.name)
        db = self.register(parent / "a #b")
        before = sorted(p.name for p in parent.iterdir())
        digest = hashlib.sha256(db.read_bytes()).hexdigest()
        done = self.prep(db)
        self.assertEqual(done.returncode, 0, err(done))
        self.assertEqual(sorted(p.name for p in parent.iterdir()), before, "prep created a file outside the register")
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), digest)

    def test_prep_writes_no_data(self):
        db = self.register(Path(self.tmp.name) / "plain")
        digest = hashlib.sha256(db.read_bytes()).hexdigest()
        done = self.prep(db, "--deep")
        self.assertEqual(done.returncode, 0, err(done))
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), digest, "the database file's bytes changed")
        wal = Path(str(db) + "-wal")
        self.assertTrue(not wal.exists() or wal.stat().st_size == 0, "prep wrote to the WAL")

    def test_an_audit_row_does_not_create_an_empty_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            done = run_hook(root, "require-privacy-agent.py", payload(root, "Bash", {
                "command": 'python scripts/privacy_review.py --approve x.json --reason "ok"'}))
            self.assertEqual(done.returncode, 2)
            self.assertFalse((root / "state" / "ea.db").exists(), "the audit writer created an empty register")
            self.assertTrue(list((root / "logs").glob("audit-*.jsonl")), "the refusal was not recorded at all")


if __name__ == "__main__":
    unittest.main()
