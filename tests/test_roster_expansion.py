"""The roster expansion: the team switch, SAGE's privacy review, LARK's read-only prep.

Each test is one promise from the brief, run against real code with no network. Where
a test drives a hook as a subprocess it does so in a throwaway copy of the repo, so its
audit rows land in the copy and never in the live register or logs/.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
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

import _transcript  # noqa: E402
import docs_edit  # noqa: E402
import docs_propose  # noqa: E402
import ea_db  # noqa: E402
import prep  # noqa: E402
import privacy_review  # noqa: E402
import privacy_screen  # noqa: E402
import register  # noqa: E402
import team  # noqa: E402
from tests.test_review_regressions import DOC, MAP  # noqa: E402

MILO = ("NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.",
        'To switch it on: say "architecture change ok: switch on Phase 2", and Mike builds it.')


def repo_copy(tmp: str) -> Path:
    """The parts of the repo a hook needs, in a throwaway root."""
    root = Path(tmp) / "ea"
    for part in (".claude", "context", "scripts"):
        shutil.copytree(ROOT / part, root / part, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "state").mkdir()
    return root


def run_hook(root: Path, name: str, payload: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("EA_DB", "EA_FIXTURE_MODE")}
    env.update(EA_ROOT=str(root), CLAUDE_PROJECT_DIR=str(root), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(root / ".claude" / "hooks" / name)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)


def agent_payload(agent: str, root: Path) -> dict:
    """Shaped like a live main-thread dispatch (claude-vscode v2.1.222): no agent_id."""
    return {"session_id": "test", "transcript_path": str(root / "t.jsonl"), "cwd": str(root),
            "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": agent, "description": "d", "run_in_background": False, "prompt": "p"},
            "tool_use_id": "toolu_test"}


class TeamSwitch(unittest.TestCase):
    def test_the_shipped_team(self):
        shipped = team.load(ROOT)
        on = sorted(s.name for s in shipped.all() if s.active)
        self.assertEqual(on, ["HUGO", "LARK", "PAGE", "REED", "SAGE", "WREN"])
        self.assertEqual(shipped.status("milo").lines, MILO)
        self.assertEqual(shipped.status("LARK").route, "D-3")
        self.assertEqual(team.counts(shipped.all()),
                         "6 on, 5 not switched on yet, 1 outside the blueprint, 1 deferred")

    def test_dormant_lines_do_not_move_when_taylor_approves(self):
        shipped = team.load(ROOT)
        shipped.phases["2"] = {**shipped.phases["2"], "approved": True}
        self.assertTrue(shipped.status("MILO").lines[0].startswith("APPROVED, NOT BUILT YET"))
        self.assertEqual(shipped.dormant_lines("MILO"), MILO)

    def test_a_deviation_that_names_nothing_is_unreadable(self):
        roster = {"agents": [{"name": "LARK", "phase": 3, "lane": "x", "via": "D-9"}]}
        phases = {"phases": {str(n): {"approved": False} for n in range(1, 8)}}
        with self.assertRaises(team.TeamUnreadable):
            team.Team(roster, phases, {"deviations": {}})


class ActiveAgentHook(unittest.TestCase):
    """The real hook, as Claude Code runs it, in a throwaway copy of the repo."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = repo_copy(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_milo_is_refused_with_exactly_two_lines(self):
        done = run_hook(self.root, "require-active-agent.py", agent_payload("milo", self.root))
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stderr, "\n".join(MILO) + "\n")
        self.assertEqual(done.stdout, "")

    def test_reed_goes_through_silently(self):
        done = run_hook(self.root, "require-active-agent.py", agent_payload("reed", self.root))
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    def test_a_broken_phase_gate_refuses_everyone_as_an_environment_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            (root / "context" / "architecture" / "phases.json").write_text("{not json", encoding="utf-8")
            done = run_hook(root, "require-active-agent.py", agent_payload("reed", root))
        self.assertEqual(done.returncode, 2)
        self.assertIn("ENVIRONMENT fault", done.stderr)

    def test_a_hook_that_cannot_even_import_still_refuses(self):
        # Python exits 1 on an uncaught ImportError, which Claude Code treats as non-blocking.
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_copy(tmp)
            (root / ".claude" / "hooks" / "_gate.py").write_text("def broken(:\n", encoding="utf-8")
            done = run_hook(root, "require-active-agent.py", agent_payload("reed", root))
        self.assertEqual(done.returncode, 2)
        self.assertIn("require-active-agent could not finish checking this call (it could not load its own code, "
                      "SyntaxError", done.stderr)

    def test_no_banner_announces_a_refused_dispatch(self):
        refused = run_hook(self.root, "announce-dispatch.py", agent_payload("milo", self.root))
        allowed = run_hook(self.root, "announce-dispatch.py", agent_payload("reed", self.root))
        self.assertEqual(refused.stdout.strip(), "")
        self.assertIn(">> REED dispatched", allowed.stdout)


class RefusalsInTheTranscript(unittest.TestCase):
    def transcript(self, rows: list) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        with handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_a_refused_dispatch_does_not_open_require_dispatch(self):
        path = self.transcript([
            {"type": "user", "message": {"role": "user", "content": "process the transcript"}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"subagent_type": "milo"}}]}},
            {"type": "user", "toolDenialKind": "permission-rule", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                 "content": "PreToolUse:Agent hook error: [x]: NOT SWITCHED ON YET: MILO"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t2", "name": "Write", "input": {"file_path": "state/records/x.json"}}]}},
        ])
        ctx = _transcript.turn_context(path)
        self.assertEqual(ctx.dispatches, [], "require-dispatch would wave the solo Write through")
        self.assertEqual(ctx.refused, ["milo"])
        self.assertEqual([u["refused"] for u in ctx.tool_uses], [True, False])


class _Unclosed:
    """The test's connection, handed to code that closes what it opens, without being closed."""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)


class PrivacyReview(unittest.TestCase):
    """docs_propose screens, privacy_review stamps PAGE's bytes, docs_edit obeys the newest stamp."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(ea_db, "REPO_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        audit = mock.patch.object(privacy_review._audit, "record")
        audit.start()
        self.addCleanup(audit.stop)
        self.conn = ea_db.connect(self.root / "r.db")
        self.addCleanup(self.conn.close)
        ea_db.migrate(self.conn)
        register.seed_roster(self.conn)
        kaed = self.conn.execute("SELECT id FROM people WHERE key = 'kaed'").fetchone()["id"]
        with self.conn:
            self.conn.execute("INSERT INTO docs (doc_id, person_id, title, fixture, section_map_json, map_confirmed,"
                              " role, created_at) VALUES ('FIXTURE_DOC_ID', ?, '[FIXTURE] Kaed', 1, ?, 1,"
                              " 'running_1on1', ?)", (kaed, json.dumps(MAP), ea_db.now_iso()))

    def propose(self, text: str) -> tuple[dict, Path]:
        ref = register.add_topic(self.conn, person_key="kaed", text=text, instruction_date="2026-10-01")["ref"]
        proposal = docs_propose.build(self.conn, "add-topic", ref, doc_id=None, section=None, document=DOC)
        path = self.root / "state" / "proposals" / f"{ref}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(proposal, indent=2) + "\n").encode("utf-8"))
        digest = docs_propose.proposal_sha(json.loads(path.read_bytes()))
        with self.conn:
            self.conn.execute("INSERT INTO proposals (path, sha256, kind, doc_id, item_ref, created_by, created_at)"
                              " VALUES (?,?,?,?,?,'PAGE',?)", (path.relative_to(self.root).as_posix(), digest,
                                                                 "add-topic", proposal["doc_id"], ref, ea_db.now_iso()))
        return proposal, path

    def delivery_refusal(self, path: Path) -> str:
        proposal = docs_edit.check_proposal(self.conn, path, "add-topic", None)
        try:
            docs_edit.check_privacy(self.conn, proposal)
        except docs_edit.Refused as exc:
            return str(exc)
        return ""

    def review(self, path: Path, verdict: str, reason: str) -> dict:
        proposal, digest, rel = privacy_review.load_flagged(self.conn, path)
        return privacy_review.record(self.conn, proposal, digest, rel, verdict, reason)

    def test_the_brief_near_misses_are_not_flagged(self):
        for text in ("manager bonus structure", "manager accountability", "leadership-structure feedback",
                     "Christmas lights", "holiday party bookings"):
            self.assertIsNone(privacy_screen.screen(text), text)

    def test_a_flagged_proposal_waits_for_sage_and_obeys_the_newest_verdict(self):
        proposal, path = self.propose("Family matter Kaed raised after the meeting")
        self.assertEqual((proposal["privacy_review"], proposal["privacy_category"]), ("required", "family"))
        self.assertIn("SAGE has not reviewed it", self.delivery_refusal(path))
        self.review(path, "hold", "Personal family context stays in Taylor's private notes.")
        self.assertIn("SAGE is holding", self.delivery_refusal(path))
        self.review(path, "approve", "Taylor explained why Kaed needs to see it.")
        self.assertEqual(self.delivery_refusal(path), "")

    def test_a_clean_proposal_needs_no_sage_and_cannot_be_stamped(self):
        proposal, path = self.propose("Christmas lights for the patio")
        self.assertEqual(proposal["privacy_review"], "not_required")
        self.assertEqual(self.delivery_refusal(path), "")
        with self.assertRaises(privacy_review.ReviewRefused):
            self.review(path, "approve", "nothing to review")

    def test_a_stamp_does_not_survive_an_edit_to_the_words(self):
        # A second, properly indexed PAGE proposal for the SAME item with new words: check_proposal
        # passes it, so only check_privacy stands between it and the Doc. The old approval was of
        # the first wording's bytes and must not cover the second.
        _, first = self.propose("Shift swap to cover a medical appointment")
        self.review(first, "approve", "The shift swap is the work.")
        self.assertEqual(self.delivery_refusal(first), "", "the approved words themselves go through")
        reworded = {**json.loads(first.read_bytes()), "text": "Shift swap to cover a medical appointment, details inside"}
        second = first.with_name(first.stem + "-v2.json")
        second.write_bytes((json.dumps(reworded, indent=2) + "\n").encode("utf-8"))
        with self.conn:
            self.conn.execute("INSERT INTO proposals (path, sha256, kind, doc_id, item_ref, created_by, created_at)"
                              " VALUES (?,?,?,?,?,'PAGE',?)",
                              (second.relative_to(self.root).as_posix(), docs_propose.proposal_sha(reworded),
                               "add-topic", reworded["doc_id"], reworded["item_ref"], ea_db.now_iso()))
        self.assertIn("SAGE has not reviewed it", self.delivery_refusal(second))

    def test_the_review_prints_the_words_its_verdict_covers(self):
        proposal, path = self.propose("Family matter Kaed raised after the meeting")
        out = io.StringIO()
        argv = ["privacy_review.py", "--hold", str(path), "--reason", "Personal family context stays private."]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(privacy_review.ea_db, "connect",
                                                                      return_value=_Unclosed(self.conn)), \
                contextlib.redirect_stdout(out):
            self.assertEqual(privacy_review.main(), 0)
        printed = out.getvalue()
        self.assertIn("This verdict covers exactly these words", printed)
        self.assertIn("  Family matter Kaed raised after the meeting", printed)

    def test_keep_private_withdraws_the_waiting_proposal(self):
        _, path = self.propose("Family matter Kaed raised after the meeting")
        ref = json.loads(path.read_bytes())["item_ref"]
        self.review(path, "hold", "Personal family context stays private.")
        notes = self.root / "notes.md"
        result = register.keep_private(self.conn, ref, notes_path=notes)
        self.assertEqual(result["proposals_withdrawn"], 1)
        self.assertIn("SAGE held it (family)", notes.read_text(encoding="utf-8"))
        with self.assertRaises(docs_edit.Refused):
            docs_edit.check_proposal(self.conn, path, "add-topic", None)

    def test_keep_private_refuses_an_item_already_in_a_doc(self):
        ref = register.add_topic(self.conn, person_key="kaed", text="Weekend coverage plan",
                                 instruction_date="2026-10-01")["ref"]
        with self.conn:
            self.conn.execute("UPDATE topics SET status = 'placed' WHERE ref = ?", (ref,))
        with self.assertRaises(register.RegisterError):
            register.keep_private(self.conn, ref, notes_path=self.root / "notes.md")


class LarkPrep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "prep.db"
        conn = ea_db.connect(self.db)
        try:
            ea_db.migrate(conn)
            register.seed_roster(conn)
            self.mine = register.add_action(conn, text="Send Kaed the patio staffing numbers", owner="taylor",
                                            due="2026-10-06", counterpart="kaed", instruction_date="2026-10-01")["ref"]
            self.theirs = register.add_action(conn, text="Bring the bar inventory variance", owner="kaed",
                                              due="2026-10-07", counterpart="kaed", instruction_date="2026-10-01")["ref"]
            self.question = register.add_action(conn, text="Draft the weekend rota", owner="kaed", due="unresolved",
                                                counterpart="kaed", instruction_date="2026-10-01")["needs_input"]
        finally:
            conn.close()

    def run_prep(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "EA_FIXTURE_MODE"}
        env.update(EA_DB=str(self.db), PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "prep.py"), *args], capture_output=True,
                              text=True, encoding="utf-8", env=env, timeout=60)

    def digest(self) -> str:
        conn = sqlite3.connect(ea_db.read_only_uri(self.db), uri=True)
        try:
            return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()
        finally:
            conn.close()

    def test_the_brief_puts_taylors_part_first_and_writes_nothing(self):
        # Blueprint s.10: prep IS the deeper briefing. Taylor's part leads; what Kaed owes follows.
        before = self.digest()
        brief = self.run_prep("--person", "Kaed")
        deep = self.run_prep("--person", "kaed", "--deep")
        self.assertEqual(self.digest(), before)
        self.assertEqual((brief.returncode, deep.returncode), (0, 0), brief.stderr + deep.stderr)
        self.assertEqual(brief.stdout, deep.stdout, "--deep is still accepted and changes nothing")
        theirs_at = brief.stdout.index("Kaed owes you")
        self.assertLess(brief.stdout.index(self.mine), theirs_at)
        self.assertLess(brief.stdout.index(self.question), theirs_at)
        self.assertGreater(brief.stdout.index(self.theirs), theirs_at)

    def test_nothing_owed_says_so(self):
        conn = ea_db.connect(self.db, read_only=True)
        try:
            shown = prep.render(prep.build(conn, "Tania"))
        finally:
            conn.close()
        self.assertIn("No outstanding prep.", shown)

    def test_a_name_that_is_not_one_person_is_refused(self):
        done = self.run_prep("--person", "Kade")
        self.assertEqual(done.returncode, 1)
        self.assertIn("NO PREP", done.stderr)


if __name__ == "__main__":
    unittest.main()
