"""Prove every gate still goes red on its fixture and green on its near-miss.

PORTED FROM PIPER. GREEN ON A CLEAN REPO PROVES NOTHING. Every rule here ships:

  a BLOCK case   input that MUST be refused. If it stops being refused, the gate
                 has been loosened and nobody noticed.
  a PASS case    a near-miss that MUST go through. If it starts being refused, the
                 gate has become the thing somebody switches off.

GATES COVERED (the plan's list, plus the ones that keep them honest):

  delivery-agent        scripts/docs_edit.py runs only inside WREN
  doc-allowlist         docs_edit.py refuses unregistered Docs, live Docs in fixture
                        mode, live Docs before D-1 is approved, and any Doc whose
                        documents.get returned no revisionId
  protect-architecture  layer A (rules text needs Taylor's phrase) and layer B (code
                        and permissions only on the build machine), the marker, and
                        the override's turn boundary
  no-cloud              push commands, hosts off the allowlist, sync roots
  classify-and-place    declarations, including the JSON key form, and placement
  approval              what is egress (and that docs_edit.py is NOT), the
                        self-draft exemption, and the hash binding
  content               em dash in Doc- or Taylor-bound text, emoji anywhere
  wiring                every gate is wired, shell gates match PowerShell too
  watchdog              the out-of-band liveness check fires and never raises
  rollcall              the roll call's four outcomes: a read-only solo turn gets the
                        quiet line, a solo write gets the SOLO block, a dispatch gets
                        the TEAM line, an unreadable turn gets UNVERIFIED; the status
                        line and docs/FOR-TAYLOR.md agree with it; a dispatch a gate
                        refused is not counted as one
  active-agent          only a switched-on agent is dispatched; every switched-off one
                        answers with exactly the lines docs/FOR-TAYLOR.md quotes;
                        non-roster agents, workflows and the claude CLI are refused
  privacy-screen        every personal-sensitivity category is flagged, and the
                        near-misses ("manager bonus structure", "Christmas lights") pass
  privacy-stamp         docs_edit.py refuses a flagged proposal without SAGE's approval
                        of those exact bytes
  privacy-agent         scripts/privacy_review.py runs only inside SAGE

WHAT IS NOT COVERED, stated: this drives the pure decision function inside each
gate. It does not prove Claude Code invokes the hook (wiring proves it is
configured, not that it fires) and it cannot test a model. The by-hand session
table in INSTALL.md is the live half.

--mutation-test breaks each gate on purpose and asserts this self-test then reports
failures for that gate. For most gates the break is "always allow". The roll call
gets one break per outcome, each naming the case that must go red, because a roll
call that says the wrong reassuring thing is not caught by any single mutation. A
self-test that stays green when the gate is removed is not a test.

Usage:
    python scripts/validate_guardrails.py --self-test [--verbose] [--only GATE ...]
    python scripts/validate_guardrails.py --mutation-test
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import itertools
import json
import os
import socket
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
HOOKS = REPO_ROOT / ".claude" / "hooks"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

EM = chr(0x2014)
VERBOSE = False


def load_hook(filename: str):
    """Import a hook module whose filename is not a legal Python identifier."""
    path = HOOKS / filename
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_")[:-3], path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Problem:
    def __init__(self, rule: str, label: str, expected: str, got: str, detail: str = ""):
        self.rule, self.label, self.expected, self.got, self.detail = rule, label, expected, got, detail

    def __str__(self) -> str:
        line = f"{self.rule}: {self.label}\n      expected {self.expected}, got {self.got}"
        return line + (f"\n      {self.detail}" if self.detail else "")


def expect(problems: list, rule: str, label: str, want_block: bool, blocked: bool, detail: str = "") -> int:
    """Record one BLOCK or PASS case. Returns 1 so callers can sum cases."""
    ok = want_block == blocked
    if VERBOSE:
        verdict = "BLOCKED" if blocked else "allowed"
        print(f"    {'ok  ' if ok else 'FAIL'} {verdict:8} {rule}: {label}")
    if not ok:
        problems.append(Problem(rule, label, "blocked" if want_block else "allowed",
                                "blocked" if blocked else "allowed", detail))
    return 1


def expect_equal(problems: list, rule: str, label: str, want, got, detail: str = "") -> int:
    ok = want == got
    if VERBOSE:
        print(f"    {'ok  ' if ok else 'FAIL'} {str(got)[:8]:8} {rule}: {label}")
    if not ok:
        problems.append(Problem(rule, label, str(want), str(got), detail))
    return 1


# --------------------------------------------------------------------------
# delivery-agent
# --------------------------------------------------------------------------

def check_delivery_agent(problems: list) -> int:
    hook = load_hook("require-delivery-agent.py")
    gate = load_hook("_gate.py")
    cases = 0
    edit = "python scripts/docs_edit.py add-topic --doc FIXTURE --proposal state/proposals/x.json"
    for label, command, caller, want_block in [
        ("block: PAGE runs the writer", edit, "PAGE", True),
        ("block: REED runs the writer", edit, "REED", True),
        ("block: the orchestrator runs the writer on the main thread", edit, "MAIN", True),
        ("block: a subagent the payload does not identify", edit, None, True),
        ("block: HUGO through PowerShell with a full interpreter path",
         "& C:\\Python311\\python.exe scripts\\docs_edit.py mark-done --doc X", "HUGO", True),
        ("block: the source piped into an interpreter", "cat scripts/docs_edit.py | python -", "MAIN", True),
        ("block: imported inline", 'python -c "import docs_edit"', "PAGE", True),
        ("block: wrapped in powershell -Command",
         'powershell -Command "python scripts/docs_edit.py add-action --doc X"', "MAIN", True),
        ("pass: WREN runs the writer", edit, "WREN", False),
        ("pass: PAGE writes a proposal (a different script)",
         "python scripts/docs_propose.py add-topic --doc X --ref T-0001", "PAGE", False),
        ("pass: reading the writer's source is not running it",
         "grep -n writeControl scripts/docs_edit.py", "MAIN", False),
        ("pass: git history of the writer", "git log --oneline -- scripts/docs_edit.py", "MAIN", False),
        ("pass: the orchestrator reads a Doc", "python scripts/docs_read.py --doc X", "MAIN", False),
    ]:
        allowed, rule = hook.decide(command, caller)
        cases += expect(problems, "delivery-agent", label, want_block, not allowed, rule)

    # Caller identity comes from Claude Code's payload, never from inference.
    for label, payload, want in [
        ("subagent payload naming wren", {"agent_id": "a1", "agent_type": "wren"}, "WREN"),
        ("plugin-qualified agent type", {"agent_id": "a1", "agent_type": "ea:wren"}, "WREN"),
        ("agent_type without agent_id is the main thread", {"agent_type": "wren"}, "MAIN"),
        ("no agent fields at all is the main thread", {}, "MAIN"),
        ("subagent payload naming nobody on the roster", {"agent_id": "a1", "agent_type": "Explore"}, None),
    ]:
        cases += expect_equal(problems, "delivery-agent", f"caller: {label}", want, gate.caller_agent(payload))

    roster = json.loads((REPO_ROOT / "context" / "roster-agents.json").read_text(encoding="utf-8"))
    delivery = [a["name"].upper() for a in roster["agents"] if a.get("delivery")]
    cases += expect_equal(problems, "delivery-agent",
                          "roster-agents.json and the hook name the same delivery agent",
                          [hook.DELIVERY_AGENT], delivery)
    return cases


# --------------------------------------------------------------------------
# doc-allowlist (docs_edit.py)
# --------------------------------------------------------------------------

def check_doc_allowlist(problems: list) -> int:
    import docs_edit
    import ea_db

    cases = 0
    approved = {"D-1": {"status": "approved", "gates": ["live_doc_writes"]}}
    proposed = {"D-1": {"status": "proposed", "gates": ["live_doc_writes"]}}
    with tempfile.TemporaryDirectory() as tmp:
        conn = ea_db.connect(Path(tmp) / "allow.db")
        try:
            ea_db.migrate(conn)
            now = ea_db.now_iso()
            conn.execute("INSERT INTO docs (doc_id, title, fixture, created_at) VALUES ('FIX1','[FIXTURE] x',1,?)", (now,))
            conn.execute("INSERT INTO docs (doc_id, title, fixture, map_confirmed, created_at)"
                         " VALUES ('LIVE1','Kaed x Taylor',0,1,?)", (now,))
            conn.execute("INSERT INTO docs (doc_id, title, fixture, map_confirmed, created_at)"
                         " VALUES ('LIVE2','Casey x Taylor',0,0,?)", (now,))
            conn.commit()

            def refused(doc_id: str, fixture_mode: bool, deviations: dict) -> tuple[bool, str]:
                try:
                    docs_edit.check_allowlist(conn, doc_id, fixture_mode=fixture_mode, deviations=deviations)
                    return False, ""
                except docs_edit.Refused as exc:
                    return True, str(exc)[:120]

            for label, doc_id, fixture_mode, deviations, want_block in [
                ("block: a Doc that is not registered at all", "NOT-REGISTERED", True, approved, True),
                ("block: a registered LIVE Doc while EA_FIXTURE_MODE=1", "LIVE1", True, approved, True),
                ("block: a live Doc before D-1 is approved", "LIVE1", False, proposed, True),
                ("block: a live Doc when the deviations file is unreadable", "LIVE1", False, {}, True),
                ("block: a live Doc whose section map Taylor has not confirmed", "LIVE2", False, approved, True),
                ("pass: a registered fixture Doc in fixture mode", "FIX1", True, proposed, False),
                ("pass: a live Doc once D-1 is approved (fixture mode off)", "LIVE1", False, approved, False),
            ]:
                blocked, why = refused(doc_id, fixture_mode, deviations)
                cases += expect(problems, "doc-allowlist", label, want_block, blocked, why)
        finally:
            conn.close()

    # revisionId is only returned to editors. Its absence is a loud refusal.
    for label, document, want_block in [
        ("block: documents.get returned no revisionId (view-only token)", {"documentId": "X"}, True),
        ("block: an empty revisionId", {"documentId": "X", "revisionId": ""}, True),
        ("pass: an editor's read carries a revisionId", {"documentId": "X", "revisionId": "ALm37..."}, False),
    ]:
        try:
            docs_edit.require_revision(document)
            blocked = False
        except docs_edit.Refused:
            blocked = True
        cases += expect(problems, "doc-allowlist", label, want_block, blocked)
    return cases


# --------------------------------------------------------------------------
# protect-architecture, both layers
# --------------------------------------------------------------------------

def _transcript(rows: list) -> str:
    """A transcript file. A str row is written as it is, so a fixture can hold a broken line."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    with handle:
        for row in rows:
            handle.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
    return handle.name


def _user(text: str, **extra) -> dict:
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}, **extra}


def check_protect_architecture(problems: list) -> int:
    hook = load_hook("protect-architecture.py")
    gate = load_hook("_gate.py")
    cases = 0
    phrase = "architecture change ok"

    # Layer A: rules text, Taylor's phrase.
    for label, target, typed, build, want_block in [
        ("block: edit the blueprint with no approval", "context/architecture/blueprint.md",
         "remove the reservation send approval", False, True),
        ("block: edit CLAUDE.md with no approval", "CLAUDE.md", "tidy up the rules", False, True),
        ("block: approve D-1 by editing deviations.json without the phrase",
         "context/architecture/deviations.json", "D-1 looks fine", False, True),
        ("block: the build machine does not exempt rules text", "CLAUDE.md", "tidy up", True, True),
        ("block: rules text when the latest message could not be read", "CLAUDE.md", None, False, True),
        ("pass: Taylor typed the phrase", "context/architecture/blueprint.md",
         f"{phrase}: remove the reservation send approval", False, False),
        ("pass: the phrase is case-insensitive", "CLAUDE.md", "Architecture Change OK, do it", False, False),
        ("pass: docs/DEVIATIONS.md is where a proposal goes", "docs/DEVIATIONS.md", "anything", False, False),
        ("pass: README.md is not protected", "README.md", "anything", False, False),
    ]:
        allowed, rule, _ = hook.decide([target], typed, build)
        cases += expect(problems, "protect-architecture", f"A {label}", want_block, not allowed, rule)

    # Layer B: code and permissions, build machine only, phrase irrelevant.
    for label, target, typed, build, want_block in [
        ("block: edit require-approval.py on Taylor's machine", ".claude/hooks/require-approval.py", phrase, False, True),
        ("block: edit settings.json on Taylor's machine", ".claude/settings.json", phrase, False, True),
        ("block: edit a script on Taylor's machine", "scripts/docs_edit.py", phrase, False, True),
        ("block: grant an agent a tool on Taylor's machine", ".claude/agents/reed.md", phrase, False, True),
        ("block: widen the network allowlist on Taylor's machine", "context/systems.json", phrase, False, True),
        ("block: `git pull` rewrites the tree on Taylor's machine", "*", phrase, False, True),
        ("pass: edit require-approval.py on the build machine", ".claude/hooks/require-approval.py", "", True, False),
        ("pass: edit a script on the build machine", "scripts/docs_edit.py", "", True, False),
        ("block: create the build marker, even on the build machine", "state/BUILD_MACHINE", phrase, True, True),
        ("block: create the build marker on Taylor's machine", "state/BUILD_MACHINE", phrase, False, True),
    ]:
        allowed, rule, _ = hook.decide([target], typed, build)
        cases += expect(problems, "protect-architecture", f"B {label}", want_block, not allowed, rule)

    # Shell write detection, both shells.
    for label, command, want_layer in [
        ("block: sed -i on CLAUDE.md", "sed -i 's/x/y/' CLAUDE.md", "rules"),
        ("block: redirect into the blueprint", "echo x > context/architecture/blueprint.md", "rules"),
        ("block: Set-Content on settings.json", "Set-Content -Path .claude/settings.json -Value '{}'", "code"),
        ("block: inline python writing CLAUDE.md", "python -c \"open('CLAUDE.md','w').write('x')\"", "rules"),
        ("block: Remove-Item on a hook", "Remove-Item .claude/hooks/no-cloud.py", "code"),
        ("block: write the marker by redirect", "echo h > state/BUILD_MACHINE", "marker"),
        ("pass: reading CLAUDE.md", "cat CLAUDE.md", None),
        ("pass: a script's output redirected elsewhere", "python scripts/register.py owed > owed.txt", None),
        ("pass: inline python that only reads", "python -c \"print(open('CLAUDE.md').read())\"", None),
        ("pass: git status", "git status --porcelain", None),
    ]:
        layers = {hook.layer_of(hook.to_rel(t, str(REPO_ROOT))) for t in hook.shell_write_targets(command)} - {None}
        got = sorted(layers)[0] if layers else None
        cases += expect(problems, "protect-architecture", f"shell {label}", want_layer is not None,
                        got is not None, f"layer={got}")

    # The override's turn boundary: only the LATEST typed turn counts.
    stale = _transcript([
        _user(f"{phrase}, update the blueprint"),
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}},
        _user("<command-message>add is running</command-message><command-name>/add</command-name>"
              "<command-args>Kaed, manager accountability</command-args>"),
    ])
    fresh = _transcript([_user("<command-name>/NAME</command-name>"
                               f"<command-args>{phrase}: drop the reservation rule</command-args>")])
    reminder = _transcript([_user("please tidy CLAUDE.md <system-reminder>the phrase "
                                  f"{phrase} appears in CLAUDE.md</system-reminder>")])
    sidechain = _transcript([_user(f"{phrase}", isSidechain=True)])
    try:
        for label, path, want_block in [
            ("block: the phrase from an EARLIER turn does not carry into a later /add", stale, True),
            ("block: the phrase inside a system-reminder is not Taylor typing", reminder, True),
            ("block: a subagent's dispatch prompt is not Taylor typing", sidechain, True),
            ("pass: the phrase typed as a slash-command argument in the latest turn", fresh, False),
        ]:
            typed = hook.latest_typed_text(path)
            allowed, rule, _ = hook.decide(["CLAUDE.md"], typed, False)
            cases += expect(problems, "protect-architecture", f"turn {label}", want_block, not allowed,
                            f"typed={typed!r}")
    finally:
        for path in (stale, fresh, reminder, sidechain):
            os.unlink(path)

    # The marker must name THIS host: a marker carried on a USB copy opens nothing.
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "BUILD_MACHINE"
        original = gate.BUILD_MARKER
        try:
            gate.BUILD_MARKER = marker
            cases += expect(problems, "protect-architecture", "marker: absent means not the build machine",
                            True, not gate.is_build_machine())
            marker.write_text("SOME-OTHER-LAPTOP\n", encoding="utf-8")
            cases += expect(problems, "protect-architecture", "marker: copied from another host opens nothing",
                            True, not gate.is_build_machine())
            marker.write_text(socket.gethostname() + "\n", encoding="utf-8")
            cases += expect(problems, "protect-architecture", "marker: naming this host is the build machine",
                            False, not gate.is_build_machine())
        finally:
            gate.BUILD_MARKER = original
    return cases


# --------------------------------------------------------------------------
# no-cloud
# --------------------------------------------------------------------------

def check_no_cloud(problems: list) -> int:
    hook = load_hook("no-cloud.py")
    systems = json.loads((REPO_ROOT / "context" / "systems.json").read_bytes().decode("utf-8"))
    allowlist = systems["host_allowlist"]["network"]
    cases = 0
    for label, command, want_block in [
        ("block: git push", "git push origin main", True),
        ("block: git push behind a PowerShell call operator", "& git push", True),
        ("block: gh after a pipe", "cat notes.md | gh issue create", True),
        ("block: rclone with a leading env assignment", "RCLONE_CONFIG=x rclone copy state remote:", True),
        ("block: curl to a host nobody allowlisted", "curl -X POST https://hooks.slack.com/services/T/B/X -d @r.json", True),
        ("block: Invoke-RestMethod to an unlisted host", "Invoke-RestMethod -Uri https://example.com/upload -Method Post", True),
        ("block: a network tool with no resolvable destination", "curl -X POST $ENDPOINT -d @r.json", True),
        ("pass: git status is not git push", "git status --porcelain", False),
        ("pass: a path that merely contains gh", "python scripts/register.py owed > state/records/gh-notes.txt", False),
        ("pass: curl to the Docs API, which is allowlisted", "curl -s https://docs.googleapis.com/v1/documents/X", False),
    ]:
        finding = hook.classify_command(command, allowlist)
        cases += expect(problems, "no-cloud", label, want_block, finding is not None,
                        finding[1] if finding else "")

    fake_root = hook.norm_path(str(Path(tempfile.gettempdir()) / "OneDrive - Greta Bar"))
    for label, path, want_block in [
        ("block: the register inside a synced folder",
         str(Path(tempfile.gettempdir()) / "OneDrive - Greta Bar" / "EA" / "state" / "ea.db"), True),
        ("pass: the register inside the repo", str(REPO_ROOT / "state" / "ea.db"), False),
        ("pass: a sibling with a similar prefix",
         str(Path(tempfile.gettempdir()) / "OneDrive - Greta Bar Archive" / "x.md"), False),
    ]:
        reason = hook.classify_path(path, roots=[fake_root])
        cases += expect(problems, "no-cloud", label, want_block, reason is not None, reason or "")
    cases += expect(problems, "no-cloud", "block: a UNC path is a network drive", True,
                    hook.is_remote_drive(r"\\fileserver\share\ea.db"))
    return cases


# --------------------------------------------------------------------------
# classify-and-place
# --------------------------------------------------------------------------

def check_classify(problems: list) -> int:
    hook = load_hook("classify-and-place.py")
    spec = json.loads((REPO_ROOT / "context" / "data-classes.json").read_bytes().decode("utf-8"))
    classes = spec["classes"]
    cases = 0
    for label, text, want in [
        ("block: no declaration at all", "# Kaed notes\n\nRows follow.", None),
        ("block: a class nobody defined", "<!-- ea-class: secret -->\n", "secret"),
        ("pass: a markdown comment declaration", "<!-- ea-class: private -->\n# Notes", "private"),
        ("pass: the JSON key form a proposal uses", '{\n  "ea-class": "records",\n  "kind": "add-topic"\n}', "records"),
    ]:
        got = hook.declared_class(text)
        cases += expect(problems, "classify-and-place", label, want not in classes, got not in classes,
                        f"declared={got!r}")
        if want is not None:
            cases += expect_equal(problems, "classify-and-place", f"{label} (value)", want, got)

    buried = "\n".join(["filler"] * 60 + ["ea-class: private"])
    cases += expect(problems, "classify-and-place", "block: a declaration buried past line 40",
                    True, hook.declared_class(buried) is None)

    for label, rel, name, want_ok in [
        ("pass: records into state/proposals/", "state/proposals/2026-10-01-x.json", "records", True),
        ("pass: records into state/records/", "state/records/snapshots/x.json", "records", True),
        ("block: records into output/", "output/drafts/x.json", "records", False),
        ("block: records into state/private/", "state/private/x.json", "records", False),
        ("pass: private into state/private/", "state/private/notes.md", "private", True),
        ("block: private into state/proposals/", "state/proposals/x.json", "private", False),
        ("block: private into output/drafts/", "output/drafts/x.md", "private", False),
        ("pass: shareable into output/drafts/", "output/drafts/x.md", "shareable", True),
        ("block: shareable into state/private/", "state/private/x.md", "shareable", False),
    ]:
        ok = hook.placement_ok(rel, hook.roots_for(classes, name), hook.forbidden_for(classes, name))
        cases += expect(problems, "classify-and-place", label, not want_ok, not ok)

    for label, rel, want_exempt in [
        ("pass: the OAuth token needs no declaration", "state/google-token.json", True),
        ("pass: the OAuth client needs no declaration", "state/google-client.json", True),
        ("pass: the database needs no declaration", "state/ea.db", True),
        ("pass: the build marker needs no declaration", "state/BUILD_MACHINE", True),
        ("block: a proposal still needs one", "state/proposals/2026-10-01-x.json", False),
    ]:
        exempt = bool(hook.MACHINE_MANAGED.search(rel))
        cases += expect(problems, "classify-and-place", label, not want_exempt, not exempt)
    return cases


# --------------------------------------------------------------------------
# approval (cold in Phase 1, proven anyway)
# --------------------------------------------------------------------------

def check_approval(problems: list) -> int:
    hook = load_hook("require-approval.py")
    import approvals
    import ea_db

    cases = 0
    for label, tool, payload, want_block in [
        ("block: a Gmail send is egress", "mcp__gmail__send_message", {}, True),
        ("block: a Docs MCP batch update is egress", "mcp__gdocs__docs_batch_update", {}, True),
        ("block: a future send script through PowerShell", "PowerShell",
         {"command": "python scripts/gmail_send.py --to a@gretabar.com"}, True),
        ("block: creating a draft is egress too", "mcp__gmail__create_draft", {}, True),
        ("pass: docs_edit.py is NOT egress (a reversible established operation, blueprint s.1)",
         "Bash", {"command": "python scripts/docs_edit.py add-topic --doc X --proposal p.json"}, False),
        ("pass: reading the register is not egress", "Bash", {"command": "python scripts/register.py owed"}, False),
        ("pass: a Gmail search is not a send", "mcp__gmail__search_messages", {}, False),
    ]:
        gated, _ = hook.is_egress(tool, {"tool_input": payload})
        cases += expect(problems, "approval", label, want_block, gated)

    owner = hook.OWNER_MAILBOX
    cases += expect_equal(problems, "approval", "the exempt mailbox is Taylor's", "t.iwaasa@gretabar.com", owner)
    for label, payload, want_exempt in [
        ("pass: a draft to Taylor alone", {"to": [owner], "subject": "x"}, True),
        ("block: a draft to Taylor with a second recipient", {"to": [owner, "someone@gretabar.com"]}, False),
        ("block: a second recipient hidden in bcc", {"to": [owner], "bcc": ["someone@gretabar.com"]}, False),
        ("block: a draft naming no recipient", {"to": []}, False),
    ]:
        exempt, _ = hook.self_draft_exempt("mcp__gmail__create_draft", {"tool_input": payload})
        cases += expect(problems, "approval", label, not want_exempt, not exempt)

    with tempfile.TemporaryDirectory() as tmp:
        conn = ea_db.connect(Path(tmp) / "approvals.db")
        try:
            ea_db.migrate(conn)
            payload = {"to": ["a@gretabar.com"], "subject": "x"}
            row, _ = approvals.consume(conn, approvals.payload_hash("Bash", payload))
            cases += expect(problems, "approval", "block: no approval row exists", True, row is None)
            approval_id, digest = approvals.create(conn, kind="send_email", target="1", summary="t",
                                                   tool_name="Bash", tool_input=payload, record_count=1)
            row, _ = approvals.consume(conn, digest)
            cases += expect(problems, "approval", "block: approval exists but is pending", True, row is None)
            approvals.approve(conn, approval_id, "test")
            row, _ = approvals.consume(conn, approvals.payload_hash("Bash", dict(payload, subject="x ")))
            cases += expect(problems, "approval", "block: one character of the payload changed", True, row is None)
            row, _ = approvals.consume(conn, digest)
            cases += expect(problems, "approval", "pass: approved, unspent, unexpired", False, row is None)
            row, _ = approvals.consume(conn, digest)
            cases += expect(problems, "approval", "block: a spent approval cannot be replayed", True, row is None)
        finally:
            conn.close()
    return cases


# --------------------------------------------------------------------------
# content rules
# --------------------------------------------------------------------------

def check_content(problems: list) -> int:
    import validate_content_rules as rules

    cases = 0
    for label, text, path, want_rule in [
        ("block: an em dash in a Doc edit proposal", f"Manager accountability {EM} pricing", "state/proposals/x.json", "em-dash"),
        ("block: an em dash in a doc Taylor reads", f"Run it {EM} then check", "docs/DEVIATIONS.md", "em-dash"),
        ("block: an em dash in README.md", f"NAME {EM} the assistant", "README.md", "em-dash"),
        ("pass: an em dash in a code comment", f"# reason {EM} kept for history", "scripts/x.py", None),
        ("block: an emoji anywhere, even code", "done " + chr(0x2705), "scripts/x.py", "emoji"),
        ("pass: an arrow is not an emoji", "REED -> PAGE -> WREN", "docs/x.md", None),
        ("pass: an inline allow escape", f"content-lint: allow-em-dash -- quoting Taylor\nA {EM} B", "docs/x.md", None),
    ]:
        found = {f.rule for f in rules.check_text(text, path)}
        blocked = want_rule in found if want_rule else bool(found)
        cases += expect(problems, "content", label, want_rule is not None, blocked, ", ".join(sorted(found)))

    for label, text, want_block in [
        ("block: Doc-bound text with an em dash (the API path no hook sees)", f"Bonus {EM} Friday", True),
        ("block: Doc-bound text with an emoji", "Bonus " + chr(0x1F44D), True),
        ("pass: plain Doc-bound text", "Send Casey the manager bonus structure [A-0001]", False),
    ]:
        cases += expect(problems, "content", label, want_block, bool(rules.check_doc_bound(text)))
    return cases


# --------------------------------------------------------------------------
# wiring
# --------------------------------------------------------------------------

def check_wiring(problems: list) -> int:
    cases = 1
    try:
        settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(Problem("wiring", "settings.json parses", "parsed", str(exc)))
        return cases

    groups = settings.get("hooks", {}).get("PreToolUse", [])

    def matcher_for(filename: str) -> str | None:
        for group in groups:
            for entry in group.get("hooks", []):
                if filename in entry.get("command", ""):
                    return group.get("matcher", "")
        return None

    for filename, must_match in [
        ("protect-architecture.py", ("Write", "Edit", "Bash", "PowerShell")),
        ("no-cloud.py", ("Write", "Bash", "PowerShell")),
        ("require-delivery-agent.py", ("Bash", "PowerShell")),
        ("classify-and-place.py", ("Write", "Edit")),
        ("require-dispatch.py", ("Write", "Edit")),
        ("validate_content_rules.py", ("Write", "Edit")),
        ("require-approval.py", ("Bash", "PowerShell", "mcp__")),
        ("announce-dispatch.py", ("Agent",)),
        ("require-active-agent.py", ("Agent", "Task", "Workflow", "Bash", "PowerShell")),
        ("require-privacy-agent.py", ("Bash", "PowerShell")),
    ]:
        matcher = matcher_for(filename)
        cases += expect(problems, "wiring", f"{filename} is wired", True, matcher is not None)
        if matcher is not None:
            missing = [m for m in must_match if m not in matcher]
            cases += expect(problems, "wiring", f"{filename} matches {', '.join(must_match)}",
                            True, not missing, f"matcher={matcher!r} missing={missing}")

    commands = json.dumps(settings.get("hooks", {}))
    for filename in ("team-rollcall.py", "validate-on-edit.sh"):
        cases += expect(problems, "wiring", f"{filename} is wired", True, filename in commands)
    cases += expect(problems, "wiring", "the status line is wired", True,
                    "statusline-ea.py" in json.dumps(settings.get("statusLine", {})))
    return cases


# --------------------------------------------------------------------------
# watchdog
# --------------------------------------------------------------------------

def check_watchdog(problems: list) -> int:
    import ea_db
    import notify_owner

    cases = 0
    original = ea_db.DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        ea_db.DB_PATH = Path(tmp) / "watch.db"
        try:
            conn = ea_db.connect()
            ea_db.migrate(conn)

            def set_tick(days_ago: float | None) -> None:
                conn.execute("DELETE FROM job_ticks WHERE job='ea_tick'")
                if days_ago is not None:
                    stamp = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
                    conn.execute("INSERT INTO job_ticks (job, ts, status) VALUES ('ea_tick', ?, 'ok')", (stamp,))
                conn.commit()

            for label, days, threshold, want_fire in [
                ("pass: a fresh tick is silence", 0.1, 3, False),
                ("block: a tick dead five days fires", 5, 3, True),
                ("pass: five days inside a seven-day threshold", 5, 7, False),
                ("block: no tick ever recorded fires", None, 3, True),
            ]:
                set_tick(days)
                reasons, handle = notify_owner._staleness(threshold)
                if handle is not None:
                    handle.close()
                cases += expect(problems, "watchdog", label, want_fire, bool(reasons), "; ".join(reasons))
            conn.close()
        finally:
            ea_db.DB_PATH = original

    with mock.patch.object(notify_owner.subprocess, "run", side_effect=OSError("no powershell")):
        try:
            result = notify_owner.toast("self-test", "")
            raised = False
        except Exception:  # noqa: BLE001
            # swallow: converted into the finding below. A notifier that raises is the
            # silence the alert path exists to prevent.
            result, raised = None, True
    cases += expect(problems, "watchdog", "pass: toast returns a reason, never raises, when PowerShell fails",
                    False, raised or not isinstance(result, str))
    return cases


# --------------------------------------------------------------------------
# rollcall (team-rollcall.py, with _activity.py and statusline-ea.py)
# --------------------------------------------------------------------------

def _command(name: str, args: str = "") -> list[dict]:
    """A slash command as Claude Code records it: the typed row, then its expansion as an isMeta row."""
    typed = (f"<command-message>{name} is running</command-message>\n"
             f"<command-name>/{name}</command-name>\n<command-args>{args}</command-args>")
    return [{"type": "user", "message": {"role": "user", "content": typed}},
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": [
                {"type": "text", "text": f"# /{name}\n\nRun the script and report it.\n\n{args}"}]}}]


_CALL_IDS = itertools.count(1)


def _tool(name: str, tool_input) -> list[dict]:
    """One main-thread tool call and the row that carries its result back."""
    call_id = f"toolu_{next(_CALL_IDS):04d}"
    return [{"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]}}]


def _bash(command: str) -> list[dict]:
    return _tool("Bash", {"command": command})


def _refused(name: str, tool_input, message: str, denial_kind: str | None = "permission-rule",
             is_error: bool = True) -> list[dict]:
    """A tool call that never ran, recorded the way a live VS Code session records it (v2.1.222)."""
    call_id = f"toolu_{next(_CALL_IDS):04d}"
    result = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "is_error": is_error, "content": message}]}}
    if denial_kind:
        result["toolDenialKind"] = denial_kind
    return [{"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}]}}, result]


MILO_REFUSAL = ('PreToolUse:Agent hook error: [python "$CLAUDE_PROJECT_DIR/.claude/hooks/require-active-agent.py"]: '
                "NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.\n"
                'To switch it on: say "architecture change ok: switch on Phase 2", and Mike builds it.')


def _say(text: str) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def check_rollcall(problems: list) -> int:
    hook = load_hook("team-rollcall.py")
    bar = load_hook("statusline-ea.py")
    import _activity

    cases = 0
    team = "TEAM  |  REED -> PAGE -> WREN  (3 dispatched)"
    add_action = ('python scripts/register.py add-action --text "Send Casey the bonus structure"'
                  " --owner kaed --due 2026-10-02 --counterpart kaed")
    capture = [*_command("add", "Kaed: send Casey the bonus structure by Friday"),
               *_tool("Agent", {"subagent_type": "reed", "prompt": "capture it"}),
               *_tool("Agent", {"subagent_type": "page", "prompt": "propose it"}),
               *_tool("Agent", {"subagent_type": "wren", "prompt": "deliver it"}),
               _say("Captured A-0001; WREN wrote it to Kaed's Doc.")]
    owe = [*_command("owe"), *_bash("python scripts/docs_reconcile.py"),
           *_bash("python scripts/register.py owed"), _say("You owe Casey one thing.")]
    morning = [*_command("morning"), *_bash("python scripts/docs_reconcile.py"),
               *_bash("python scripts/register.py morning"), _say("Ticks OK. One thing due Friday.")]
    unreadable_use = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_x", "name": "Bash", "input": "python scripts/register.py owed"}]}}

    tokens = {hook.SOLO: "SOLO", hook.READ_ONLY_LINE: "QUIET", hook.UNVERIFIED: "UNVERIF", team: "TEAM"}
    shows = {"SOLO": "-- SOLO --", "QUIET": "read only", "UNVERIF": "team ?", "TEAM": "REED>PAGE>WREN  (3)"}
    fixtures = [
        ("read-only solo turn (/owe: reconcile, register.py owed) -> quiet line", owe, "QUIET"),
        ("read-only solo turn after a dispatched /add (/morning) -> quiet line, not the /add's team",
         capture + morning, "QUIET"),
        ("a chat-only answer, no tool at all -> quiet line", [_user("what does /owe do?"), _say("It lists...")], "QUIET"),
        ("solo turn with a register add-action -> SOLO block",
         [_user("Kaed owes me the bonus structure by Friday"), *_bash(add_action), _say("Captured.")], "SOLO"),
        ("solo turn with a Write -> SOLO block",
         [_user("note that down"), *_tool("Write", {"file_path": "C:/EA/state/records/n.json", "content": "{}"}),
          _say("Noted.")], "SOLO"),
        ("a compaction in the middle of a turn does not hide the write before it -> SOLO block",
         [_user("Kaed owes me the bonus structure by Friday"), *_bash(add_action),
          {"type": "system", "subtype": "compact_boundary"},
          {"type": "user", "isCompactSummary": True, "isVisibleInTranscriptOnly": True,
           "message": {"role": "user", "content": "This session is being continued from a previous conversation."}},
          *_bash("python scripts/register.py owed"), _say("Captured, and here is what you owe.")], "SOLO"),
        ("solo turn whose write a gate refused (docs_edit.py on the main thread) -> SOLO block, attempts count",
         [_user("put it in Kaed's Doc"), *_bash("python scripts/docs_edit.py add-action --doc X --proposal p.json"),
          _say("Blocked.")], "SOLO"),
        ("dispatched turn -> TEAM line", capture, "TEAM"),
        ("dispatched turn where the orchestrator also ran add-action -> TEAM line, unchanged",
         capture[:-1] + _bash(add_action) + [_say("done")], "TEAM"),
        ("a background agent's completion notification is not a new turn -> TEAM line",
         capture + [_user("<task-notification>wren finished</task-notification>"), _say("WREN is done.")], "TEAM"),
        ("unreadable transcript (no such file) -> UNVERIFIED", None, "UNVERIF"),
        ("unreadable transcript (no line parses) -> UNVERIFIED", ["{not json", "also not json"], "UNVERIF"),
        ("a solo tool use that cannot be read -> UNVERIFIED, never the quiet line",
         [_user("what do I owe?"), unreadable_use, _say("...")], "UNVERIF"),
        ("a line in this turn that does not parse -> UNVERIFIED, never the quiet line",
         [*_command("owe"), '{"type": "assistant", "message": {"content": [{"type": "tool_u', _say("...")], "UNVERIF"),
        ("a broken line in an EARLIER turn does not taint this one -> quiet line",
         ['{"type": "assistant", "trunc', _say("earlier"), *owe], "QUIET"),
        ("a dispatch the gate refused (MILO) is not a dispatch -> quiet line",
         [*_command("NAME", "process my 1:1 transcript with Kaed"),
          *_refused("Agent", {"subagent_type": "milo", "description": "process transcript",
                              "run_in_background": False, "prompt": "process it"}, MILO_REFUSAL),
          _say("NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.")], "QUIET"),
        ("a refusal read from the hook's own message, with no toolDenialKind -> quiet line",
         [_user("prep TALLY"), *_refused("Agent", {"subagent_type": "tally", "prompt": "x"},
                                         "PreToolUse:Agent hook error: [x]: NOT SWITCHED ON", denial_kind=None),
          _say("relayed")], "QUIET"),
        ("an agent that ran and then failed is still a dispatch -> TEAM line",
         [*_command("add", "Kaed: send Casey the bonus structure by Friday"),
          *_tool("Agent", {"subagent_type": "reed", "prompt": "capture it"}),
          *_tool("Agent", {"subagent_type": "page", "prompt": "propose it"}),
          *_refused("Agent", {"subagent_type": "wren", "prompt": "deliver it"},
                    "WREN stopped: the API returned 500", denial_kind=None),
          _say("WREN failed.")], "TEAM"),
        ("a Workflow nobody refused ran agents the roll call cannot see -> UNVERIFIED",
         [_user("audit everything"), *_tool("Workflow", {"script": "export const meta = {}"}), _say("done")],
         "UNVERIF"),
        ("a Workflow the gate refused ran nothing -> quiet line",
         [_user("audit everything"), *_refused("Workflow", {"script": "export const meta = {}"},
                                               "PreToolUse:Workflow hook error: [x]: NOT USED HERE"),
          _say("Not used here.")], "QUIET"),
    ]
    missing = str(Path(tempfile.gettempdir()) / "ea-guardrails-no-such-transcript.jsonl")
    written = []
    try:
        for label, rows, want in fixtures:
            path = missing if rows is None else _transcript(rows)
            if rows is not None:
                written.append(path)
            got = tokens.get(hook.team_block(path), "OTHER")
            cases += expect_equal(problems, "rollcall", label, want, got,
                                  f"why: {_activity.verdict_for(path).why or '-'}")
            # The status line must say the same thing about the same turn.
            kind, names = bar._verdict_uncached(path)
            rendered = bar.render("EA", kind, names, 1.0, False)
            shown = shows[want] if rendered.endswith("  " + shows[want]) else rendered
            cases += expect_equal(problems, "rollcall", f"status line shows {shows[want]!r}: {label.split(' -> ')[0]}",
                                  shows[want], shown)
    finally:
        for path in written:
            os.unlink(path)

    # What counts as writing, command by command. "write" means the SOLO block.
    for label, command, want in [
        ("register.py add-action", add_action, "write"),
        ("register.py complete, after a global flag", "python scripts/register.py --json complete A-0012 --via chat", "write"),
        ("register.py update-action through PowerShell's call operator",
         "& C:\\Python311\\python.exe scripts\\register.py update-action A-1 --field due --value x --actor t", "write"),
        ("register.py add-topic wrapped in powershell -Command",
         'powershell -Command "python scripts/register.py add-topic --person kaed --text x"', "write"),
        ("register.py needs-input resolve", "python scripts/register.py needs-input resolve Q-0003 --answer kaed", "write"),
        ("register.py seed", "python scripts/register.py seed --roster", "write"),
        ("register.py alias (it changes who a name resolves to)", "python scripts/register.py alias --person kaed --add K", "write"),
        ("register.py needs-input add (it opens a question)",
         'python scripts/register.py needs-input add --question "who?"', "write"),
        ("a register subcommand nobody classified counts as a write", "python scripts/register.py purge A-0001", "write"),
        ("docs_propose.py after a cd", "cd C:\\EA; python scripts\\docs_propose.py add-topic --ref T-0001", "write"),
        ("docs_edit.py", "python scripts/docs_edit.py mark-done --doc X --proposal p.json", "write"),
        ("link_docs.py --add", "python scripts/link_docs.py --add 1AbC --person kaed", "write"),
        ("link_docs.py --confirm (it unlocks live writes to that Doc)", "python scripts/link_docs.py --confirm --doc 1AbC", "write"),
        ("calendar_next.py --link-series", "python scripts/calendar_next.py --link-series abc --person kaed", "write"),
        ("the register imported inline", 'python -c "import register; register.add_action(None)"', "write"),
        ("a SQL delete against the register", "sqlite3 state/ea.db \"DELETE FROM actions WHERE ref='A-0013'\"", "write"),
        ("an env prefix in front of add-action", "EA_FIXTURE_MODE=1 python scripts/register.py complete A-1 --via chat", "write"),
        ("privacy_review.py --approve (SAGE's stamp)",
         'python scripts/privacy_review.py --approve state/proposals/p.json --reason "work relevant"', "write"),
        ("privacy_review.py --hold through PowerShell",
         '& python scripts\\privacy_review.py --hold state\\proposals\\p.json --reason "stays private"', "write"),
        ("privacy_review imported inline", 'python -c "import privacy_review"', "write"),
        ("register.py keep-private (Taylor's private notes)", "python scripts/register.py keep-private T-0007", "write"),
        ("prep.py (LARK's read-only prep)", "python scripts/prep.py --person Kaed --deep", "read"),
        ("team.py --agent (what a switched-off agent answers)", "python scripts/team.py --agent MILO", "read"),
        ("privacy_screen.py --text (a wording check)", 'python scripts/privacy_screen.py --text "Kaed raise"', "read"),
        ("register.py owed", "python scripts/register.py owed --person casey", "read"),
        ("register.py owed history", "python scripts/register.py owed history A-0012", "read"),
        ("register.py history", "python scripts/register.py history A-0012", "read"),
        ("register.py morning", "python scripts/register.py morning", "read"),
        ("register.py resolve-date", 'python scripts/register.py resolve-date "Friday" --from 2026-10-01', "read"),
        ("register.py resolve-person", 'python scripts/register.py resolve-person "Kaed"', "read"),
        ("register.py needs-input list", "python scripts/register.py needs-input list", "read"),
        ("register.py --self-test (its own temporary database)", "python scripts/register.py --self-test", "read"),
        ("docs_reconcile.py then register.py morning (what /morning runs)",
         "python scripts/docs_reconcile.py && python scripts/register.py morning", "read"),
        ("link_docs.py --status", "python scripts/link_docs.py --status", "read"),
        ("calendar_next.py --refresh (a sync, like the reconcile)", "python scripts/calendar_next.py --refresh", "read"),
        ("ea_doctor.py", "python scripts/ea_doctor.py", "read"),
        ("grep naming a writer subcommand", "grep -n add-action scripts/register.py", "read"),
        ("reading the writer's source in PowerShell", "Get-Content scripts\\docs_edit.py | Select-String writeControl", "read"),
        ("a SELECT against the register", 'sqlite3 state/ea.db "SELECT ref, updated_at FROM actions"', "read"),
        ("owed redirected to a file", "python scripts/register.py owed > owed.txt", "read"),
    ]:
        got = "write" if _activity.shell_writes(command) else "read"
        cases += expect_equal(problems, "rollcall", f"{want}: {label}", want, got)

    # A refused dispatch beside a real one: the TEAM line names only the agent that ran.
    mixed = _transcript([_user("capture it, and process the transcript"),
                         *_tool("Agent", {"subagent_type": "reed", "prompt": "capture it"}),
                         *_refused("Agent", {"subagent_type": "milo", "prompt": "process it"}, MILO_REFUSAL),
                         _say("REED captured it; MILO is not switched on.")])
    try:
        cases += expect_equal(problems, "rollcall", "a refused MILO beside a dispatched REED: the TEAM line names REED only",
                              "TEAM  |  REED  (1 dispatched)", hook.team_block(mixed))
    finally:
        os.unlink(mixed)

    # Taylor's guide quotes the roll call. If either side changes alone, he is told to
    # look for a line that never appears.
    guide = (REPO_ROOT / "docs" / "FOR-TAYLOR.md").read_bytes().decode("utf-8")
    cases += expect_equal(problems, "rollcall", "docs/FOR-TAYLOR.md quotes the quiet line word for word",
                          True, hook.READ_ONLY_LINE in guide)
    cases += expect_equal(problems, "rollcall", "docs/FOR-TAYLOR.md quotes the SOLO heading word for word",
                          True, hook.SOLO.splitlines()[1] in guide)
    return cases


# --------------------------------------------------------------------------
# active-agent (require-active-agent.py, with scripts/team.py)
# --------------------------------------------------------------------------

# The spec, as Mike's brief wrote it and docs/FOR-TAYLOR.md quotes it. Hardcoded here
# on purpose: compared against what team.py renders, so a drift on either side is red.
SWITCH_ON_SPEC = {
    "MILO, not switched on": (
        "NOT SWITCHED ON YET: MILO (meetings and transcripts), Phase 2.",
        'To switch it on: say "architecture change ok: switch on Phase 2", and Mike builds it.'),
    "MILO, approved and not built": (
        "APPROVED, NOT BUILT YET: MILO (meetings and transcripts), Phase 2.",
        "Mike is building it; nothing to do on your side."),
    "PENN": (
        "NOT SWITCHED ON: PENN (sales and events pipeline) is outside your architecture.",
        'To switch it on: say "architecture change ok: add PENN", then Mike builds it.'),
    "TALLY": (
        "NOT SWITCHED ON: TALLY (reporting) is Phase 6, which you deferred.",
        'To switch it on: say "architecture change ok: resume Phase 6", then Mike builds it.'),
}
SAME_TEMPLATE = {"RUTH": ("professional documentation", 2), "ATLAS": ("projects and company knowledge", 4),
                 "CLEO": ("reservation replies", 5), "JUNE": ("calendar", 7)}


def _team_variant(*, phases: dict | None = None, deviations: dict | None = None, builds: dict | None = None):
    """The shipped team with some of Taylor's or Mike's switches flipped, in memory only."""
    import team

    roster = json.loads((REPO_ROOT / "context" / "roster-agents.json").read_bytes().decode("utf-8"))
    phase_file = json.loads((REPO_ROOT / "context" / "architecture" / "phases.json").read_bytes().decode("utf-8"))
    deviation_file = json.loads((REPO_ROOT / "context" / "architecture" / "deviations.json").read_bytes().decode("utf-8"))
    for key, change in (phases or {}).items():
        phase_file["phases"][key] = {**phase_file["phases"][key], **change}
    for key, change in (deviations or {}).items():
        deviation_file["deviations"][key] = {**deviation_file["deviations"][key], **change}
    roster["build_record"] = {**roster.get("build_record", {}), **(builds or {})}
    return team.Team(roster, phase_file, deviation_file)


def check_active_agent(problems: list) -> int:
    hook = load_hook("require-active-agent.py")
    import team

    cases = 0
    shipped = team.load(REPO_ROOT)

    def lines_for(tool: str, given: dict, which=shipped) -> tuple:
        return tuple(hook.decide(tool, given, which)[2])

    # The exact words, from the team as shipped and with Taylor's approval flipped.
    approved = _team_variant(phases={"2": {"approved": True}})
    for label, tool, given, which, want in [
        ("MILO", "Agent", {"subagent_type": "milo"}, shipped, SWITCH_ON_SPEC["MILO, not switched on"]),
        ("MILO, approved and not built", "Agent", {"subagent_type": "milo"}, approved,
         SWITCH_ON_SPEC["MILO, approved and not built"]),
        ("PENN", "Agent", {"subagent_type": "penn"}, shipped, SWITCH_ON_SPEC["PENN"]),
        ("TALLY", "Agent", {"subagent_type": "tally"}, shipped, SWITCH_ON_SPEC["TALLY"]),
    ] + [(name, "Agent", {"subagent_type": name.lower()}, shipped,
          (f"NOT SWITCHED ON YET: {name} ({lane}), Phase {phase}.",
           f'To switch it on: say "architecture change ok: switch on Phase {phase}", and Mike builds it.'))
         for name, (lane, phase) in SAME_TEMPLATE.items()]:
        cases += expect_equal(problems, "active-agent", f"exact text: {label}", want, lines_for(tool, given, which))

    # Who is refused, and who goes through, on the team as shipped.
    for label, tool, given, want_block in [
        ("block: MILO, Phase 2 not switched on", "Agent", {"subagent_type": "milo", "run_in_background": False}, True),
        ("block: RUTH", "Agent", {"subagent_type": "ruth"}, True),
        ("block: ATLAS", "Agent", {"subagent_type": "atlas"}, True),
        ("block: CLEO", "Agent", {"subagent_type": "cleo"}, True),
        ("block: JUNE", "Agent", {"subagent_type": "june"}, True),
        ("block: PENN, outside the blueprint", "Agent", {"subagent_type": "penn"}, True),
        ("block: TALLY, Phase 6 deferred", "Agent", {"subagent_type": "tally"}, True),
        ("block: a plugin-qualified switched-off agent", "Agent", {"subagent_type": "ea:milo"}, True),
        ("block: the older tool name Task", "Task", {"subagent_type": "milo"}, True),
        ("block: Explore, not on this team", "Agent", {"subagent_type": "Explore"}, True),
        ("block: general-purpose, not on this team", "Agent", {"subagent_type": "general-purpose"}, True),
        ("block: no subagent_type at all", "Agent", {"prompt": "do it"}, True),
        ("block: a fork", "Agent", {"subagent_type": "fork"}, True),
        ("block: a Workflow", "Workflow", {"name": "deep-research"}, True),
        ("block: claude -p from Bash", "Bash", {"command": 'claude -p "summarise the transcript"'}, True),
        ("block: claude --agent milo from PowerShell", "PowerShell", {"command": "& claude.exe --agent milo -p x"}, True),
        ("block: claude --agent reed is still a hidden session", "Bash", {"command": "claude --agent reed -p hi"}, True),
        ("block: claude inside powershell -Command", "Bash", {"command": 'powershell -Command "claude --agent tally"'}, True),
        ("block: npx claude-code --print", "Bash", {"command": "npx @anthropic-ai/claude-code --print hi"}, True),
        ("block: Start-Process with the flags in one quoted argument", "PowerShell",
         {"command": "Start-Process claude -ArgumentList '-p summarise it'"}, True),
        ("block: Invoke-Expression around claude", "PowerShell", {"command": 'iex "claude --agent milo"'}, True),
        ("pass: REED", "Agent", {"subagent_type": "reed"}, False),
        ("pass: PAGE", "Agent", {"subagent_type": "page"}, False),
        ("pass: WREN", "Agent", {"subagent_type": "wren"}, False),
        ("pass: HUGO", "Agent", {"subagent_type": "hugo"}, False),
        ("pass: SAGE", "Agent", {"subagent_type": "sage"}, False),
        ("pass: LARK, on via D-3", "Agent", {"subagent_type": "lark"}, False),
        ("pass: claude --version is not a dispatch", "Bash", {"command": "claude --version"}, False),
        ("pass: grep for claude -p is not a dispatch", "Bash", {"command": "grep -n 'claude -p' docs/x.md"}, False),
        ("pass: echo of a claude command", "PowerShell", {"command": "echo claude --agent milo"}, False),
        ("pass: an ordinary script", "Bash", {"command": "python scripts/register.py owed"}, False),
        ("pass: a Write is not a dispatch", "Write", {"file_path": "x"}, False),
    ]:
        allowed, rule, _ = hook.decide(tool, given, shipped)
        cases += expect(problems, "active-agent", label, want_block, not allowed, rule)
    cases += expect_equal(problems, "active-agent", "a named switched-off agent from the CLI gets its own lines",
                          SWITCH_ON_SPEC["TALLY"], lines_for("Bash", {"command": "claude --agent tally"}))

    # The switches themselves: Taylor's approval and Mike's build, each alone and together.
    for label, which, name, want_block in [
        ("block: Taylor approved Phase 2 but Mike has not built it",
         _team_variant(phases={"2": {"approved": True}}), "milo", True),
        ("block: Mike built Phase 2 but Taylor has not approved it",
         _team_variant(builds={"phase 2": {"accepted": "2026-11-01"}}), "milo", True),
        ("pass: Phase 2 approved and built", _team_variant(
            phases={"2": {"approved": True}}, builds={"phase 2": {"accepted": "2026-11-01"}}), "milo", False),
        ("block: LARK once Taylor rejects D-3", _team_variant(deviations={"D-3": {"status": "rejected"}}),
         "lark", True),
        ("pass: LARK once Taylor approves D-3", _team_variant(deviations={"D-3": {"status": "approved"}}),
         "lark", False),
        ("block: PENN added by Taylor, not built yet", _team_variant(deviations={"D-4": {"status": "approved"}}),
         "penn", True),
        ("pass: TALLY once Phase 6 is resumed and built", _team_variant(
            phases={"6": {"approved": True, "deferred": False}},
            builds={"phase 6": {"accepted": "2026-11-01"}}), "tally", False),
    ]:
        allowed, rule, _ = hook.decide("Agent", {"subagent_type": name}, which)
        cases += expect(problems, "active-agent", label, want_block, not allowed, rule)

    # Unreadable is never "off": a broken team file is an exception the hook turns into a refusal.
    for label, roster, phases in [
        ("a roster with no agents", {"agents": []}, {"phases": {str(n): {"approved": False} for n in range(1, 8)}}),
        ("a phase gate missing Phase 7", {"agents": [{"name": "REED", "phase": 1, "lane": "x"}]},
         {"phases": {str(n): {"approved": False} for n in range(1, 7)}}),
        ("an approval that is not true or false", {"agents": [{"name": "REED", "phase": 1, "lane": "x"}]},
         {"phases": {**{str(n): {"approved": False} for n in range(1, 8)}, "1": {"approved": "yes"}}}),
    ]:
        try:
            team.Team(roster, phases, {"deviations": {}})
            raised = False
        except team.TeamUnreadable:
            raised = True
        cases += expect(problems, "active-agent", f"block: {label} is unreadable, never read as off", True, raised)

    # Taylor's guide quotes the lines. If either side changes alone, he is told to expect
    # words he will never see.
    guide = (REPO_ROOT / "docs" / "FOR-TAYLOR.md").read_bytes().decode("utf-8")
    for label, lines in SWITCH_ON_SPEC.items():
        for i, line in enumerate(lines, 1):
            cases += expect_equal(problems, "active-agent",
                                  f"docs/FOR-TAYLOR.md quotes {label}, line {i}, word for word", True, line in guide)
    return cases


# --------------------------------------------------------------------------
# privacy-screen, privacy-stamp, privacy-agent (SAGE)
# --------------------------------------------------------------------------

def check_privacy_screen(problems: list) -> int:
    import privacy_screen

    cases = 0
    for label, text, want in [
        ("block: health", "Shift swap to cover a medical appointment", "health"),
        ("block: family", "Family matter Kaed raised after the meeting", "family"),
        ("block: mental health", "Signs of burnout on the closing shift", "mental health"),
        ("block: addiction", "Possible substance abuse concern", "addiction"),
        ("block: leave of absence", "Return-to-work plan after medical leave", "leave of absence"),
        ("block: discipline", "Written warning for the cash shortage", "discipline"),
        ("block: harassment or complaint", "Harassment complaint from a server", "harassment or complaint"),
        ("block: legal or immigration", "Work permit renewal", "legal or immigration"),
        ("block: one person's pay", "Kaed's raise", "individual pay"),
        ("block: a raise for a named person", "Raise for Casey", "individual pay"),
        ("pass: manager bonus structure", "manager bonus structure", None),
        ("pass: manager accountability", "Manager accountability", None),
        ("pass: leadership-structure feedback", "leadership-structure feedback", None),
        ("pass: Christmas lights", "Need to organize Christmas lights", None),
        ("pass: holiday party bookings", "holiday party bookings", None),
        ("pass: the health inspection", "Prep for the health inspection", None),
        ("pass: a guest complaint", "Guest complaint about the wait", None),
        ("pass: family meal", "Family meal at 4", None),
        ("pass: raise prices", "Raise prices on the patio", None),
        ("pass: a structure-level bonus", "Casey's bonus structure", None),
    ]:
        flag = privacy_screen.screen(text)
        cases += expect(problems, "privacy-screen", label, want is not None, flag is not None,
                        f"matched {flag.matched!r}" if flag else "")
        if want and flag:
            cases += expect_equal(problems, "privacy-screen", f"{label} (category)", want, flag.category)
    # Only the words the proposal would write are screened, and the field is not trusted alone.
    for label, proposal, want_block in [
        ("block: a flagged action title", {"cells": {"title": "Kaed's raise [A-0001]", "assignee": "Taylor"}}, True),
        ("block: the field says required", {"text": "anything", "privacy_review": "required"}, True),
        ("block: the field says not_required, the words say otherwise",
         {"text": "Kaed's medical leave", "privacy_review": "not_required"}, True),
        ("pass: a clean topic", {"text": "Christmas lights for the patio"}, False),
        ("pass: a completion writes only Done and a date", {"status_text": "Done 2026-10-01"}, False),
    ]:
        cases += expect(problems, "privacy-screen", label, want_block, privacy_screen.review_required(proposal)[0])
    return cases


def check_privacy_stamp(problems: list) -> int:
    import docs_edit
    import ea_db

    cases = 0
    flagged = {"kind": "add-topic", "text": "Shift swap to cover a medical appointment", "item_ref": "T-0001",
               "privacy_review": "required", "privacy_category": "health", "_sha256": "a" * 64}
    clean = {"kind": "add-topic", "text": "Christmas lights for the patio", "item_ref": "T-0002",
             "privacy_review": "not_required", "_sha256": "b" * 64}
    mislabelled = {**flagged, "privacy_review": "not_required", "_sha256": "c" * 64}
    with tempfile.TemporaryDirectory() as tmp:
        conn = ea_db.connect(Path(tmp) / "stamp.db")
        try:
            ea_db.migrate(conn)

            def stamp(sha: str, verdict: str, reviewer: str = "SAGE") -> None:
                with conn:
                    conn.execute("INSERT INTO privacy_reviews (proposal_path, proposal_sha256, item_ref, verdict,"
                                 " category, reason, reviewer, ts) VALUES ('p', ?, 'T-0001', ?, 'health', 'r', ?, ?)",
                                 (sha, verdict, reviewer, ea_db.now_iso()))

            def refused(proposal: dict) -> tuple[bool, str]:
                try:
                    docs_edit.check_privacy(conn, proposal)
                    return False, ""
                except docs_edit.Refused as exc:
                    return True, str(exc)[:100]

            for label, setup, proposal, want_block in [
                ("block: a flagged proposal SAGE never reviewed", None, flagged, True),
                ("pass: a clean proposal needs no stamp at all", None, clean, False),
                ("block: a proposal labelled not_required whose words are flagged", None, mislabelled, True),
                ("block: SAGE approved different words (another sha256)", ("d" * 64, "approve"), flagged, True),
                ("block: a stamp recorded by someone other than SAGE", ("a" * 64, "approve", "WREN"), flagged, True),
                ("block: SAGE is holding it", ("a" * 64, "hold"), flagged, True),
                ("pass: SAGE approved these exact bytes", ("a" * 64, "approve"), flagged, False),
                ("block: a hold after the approval wins (newest stamp)", ("a" * 64, "hold"), flagged, True),
                ("pass: an approval after the hold wins (newest stamp)", ("a" * 64, "approve"), flagged, False),
            ]:
                if setup:
                    stamp(*setup)
                blocked, why = refused(proposal)
                cases += expect(problems, "privacy-stamp", label, want_block, blocked, why)
        finally:
            conn.close()
    return cases


def check_privacy_agent(problems: list) -> int:
    hook = load_hook("require-privacy-agent.py")
    cases = 0
    review = 'python scripts/privacy_review.py --approve state/proposals/x.json --reason "work relevant"'
    for label, command, caller, want_block in [
        ("block: WREN runs the reviewer", review, "WREN", True),
        ("block: PAGE approves its own proposal", review, "PAGE", True),
        ("block: REED", review, "REED", True),
        ("block: the orchestrator on the main thread", review, "MAIN", True),
        ("block: a subagent the payload does not identify", review, None, True),
        ("block: HUGO through PowerShell with a full interpreter path",
         "& C:\\Python311\\python.exe scripts\\privacy_review.py --hold x.json --reason r", "HUGO", True),
        ("block: imported inline", 'python -c "import privacy_review"', "MAIN", True),
        ("block: wrapped in powershell -Command", 'powershell -Command "python scripts/privacy_review.py --hold x"',
         "MAIN", True),
        ("pass: SAGE records a verdict", review, "SAGE", False),
        ("pass: reading the script is not running it", "grep -n verdict scripts/privacy_review.py", "MAIN", False),
        ("pass: the screen is a different script", 'python scripts/privacy_screen.py --text "x"', "PAGE", False),
        ("pass: WREN's own writer is not this gate's business",
         "python scripts/docs_edit.py add-topic --doc X --proposal p.json", "WREN", False),
    ]:
        allowed, rule = hook.decide(command, caller)
        cases += expect(problems, "privacy-agent", label, want_block, not allowed, rule)
    roster = json.loads((REPO_ROOT / "context" / "roster-agents.json").read_text(encoding="utf-8"))
    privacy = [a["name"].upper() for a in roster["agents"] if a.get("privacy")]
    cases += expect_equal(problems, "privacy-agent", "roster-agents.json and the hook name the same privacy agent",
                          [hook.PRIVACY_AGENT], privacy)
    return cases


CHECKS = {
    "delivery-agent": check_delivery_agent,
    "doc-allowlist": check_doc_allowlist,
    "protect-architecture": check_protect_architecture,
    "no-cloud": check_no_cloud,
    "classify-and-place": check_classify,
    "approval": check_approval,
    "content": check_content,
    "wiring": check_wiring,
    "watchdog": check_watchdog,
    "rollcall": check_rollcall,
    "active-agent": check_active_agent,
    "privacy-screen": check_privacy_screen,
    "privacy-stamp": check_privacy_stamp,
    "privacy-agent": check_privacy_agent,
}


@dataclass(frozen=True)
class Mutation:
    """One deliberate break. `where` is "hook" (patched as the file loads) or "module" (patched in place).

    With `wraps`, `replacement` is called with the real attribute and returns the broken one.
    `must_fail` names a case that has to go red; empty means any failing case will do.
    """

    gate: str
    what: str
    where: str
    target: str
    attr: str
    replacement: object
    must_fail: str = ""
    wraps: bool = False


def _inherited_rule(ctx):
    """The roll call before the fix: every turn without a dispatch is the SOLO block."""
    import _activity as a
    names = a.roster(ctx.dispatches)
    return a.Verdict(a.DISPATCHED, tuple(names)) if names else a.Verdict(a.WROTE)


def _blind_to_unreadable(real):
    """turn_context with "could not look" collapsed into "found nothing"."""
    import _transcript

    def turn_context(path):
        try:
            return real(path)
        except _transcript.TranscriptUnreadable:
            return _transcript.TurnContext()
    return turn_context


def _drifted_wording(name: str, lane: str, phase: int) -> tuple[str, str]:
    """The switched-off lines with "then" where Taylor's docs say "and": a one-word drift."""
    return (f"NOT SWITCHED ON YET: {name} ({lane}), Phase {phase}.",
            f'To switch it on: say "architecture change ok: switch on Phase {phase}", then Mike builds it.')


def _pre_port_typed(message: dict) -> tuple[bool, str]:
    """_transcript._typed before the port: a slash-command row is not a turn of its own."""
    import _transcript as t
    text = t.COMMAND_BLOCK.sub(" ", t.HARNESS_BLOCK.sub(" ", t._text_of(message))).strip()
    return bool(text), text


# Most gates get one mutation: the decision function forced to "allow everything".
# The roll call gets one per outcome, each aimed at the case it must turn red.
MUTATIONS = [
    Mutation("delivery-agent", "forced to allow", "hook", "require-delivery-agent.py", "decide",
             lambda *a, **k: (True, "mutated")),
    Mutation("protect-architecture", "forced to allow", "hook", "protect-architecture.py", "decide",
             lambda *a, **k: (True, "mutated", "")),
    Mutation("no-cloud", "forced to allow", "hook", "no-cloud.py", "classify_command", lambda *a, **k: None),
    Mutation("classify-and-place", "forced to allow", "hook", "classify-and-place.py", "placement_ok",
             lambda *a, **k: True),
    Mutation("approval", "forced to allow", "hook", "require-approval.py", "is_egress", lambda *a, **k: (False, "")),
    Mutation("doc-allowlist", "forced to allow", "module", "docs_edit", "check_allowlist", lambda *a, **k: None),
    Mutation("content", "forced to allow", "module", "validate_content_rules", "check_doc_bound", lambda *a, **k: []),
    Mutation("watchdog", "forced to allow", "module", "notify_owner", "_staleness", lambda *a, **k: ([], None)),
    Mutation("rollcall", "reverted to the inherited rule (no dispatch means SOLO)", "module", "_activity",
             "classify", _inherited_rule, must_fail="read-only solo turn (/owe"),
    Mutation("rollcall", "blind to shell commands", "module", "_activity", "shell_writes", lambda command: False,
             must_fail="solo turn with a register add-action"),
    Mutation("rollcall", "blind to the Write tool", "module", "_activity", "WRITE_TOOLS", frozenset(),
             must_fail="solo turn with a Write"),
    Mutation("rollcall", "blind to the roster", "module", "_activity", "roster", lambda dispatches: [],
             must_fail="dispatched turn -> TEAM line"),
    Mutation("rollcall", "treats an unreadable transcript as an empty turn", "module", "_activity", "turn_context",
             _blind_to_unreadable, must_fail="unreadable transcript (no such file)", wraps=True),
    Mutation("rollcall", "treats a tool use it cannot read as a read", "module", "_activity", "tool_use_writes",
             lambda real: (lambda use: bool(real(use))), must_fail="a solo tool use that cannot be read",
             wraps=True),
    Mutation("rollcall", "does not end a turn at a slash command", "module", "_transcript", "_typed",
             _pre_port_typed, must_fail="after a dispatched /add"),
    Mutation("rollcall", "ends a turn at a compaction summary", "module", "_transcript", "_is_real_user_turn",
             lambda real: (lambda event: True if event.get("isCompactSummary") else real(event)),
             must_fail="a compaction in the middle of a turn", wraps=True),
    Mutation("rollcall", "counts a refused dispatch as a dispatch", "module", "_transcript", "_denied_ids",
             lambda event: set(), must_fail="a dispatch the gate refused (MILO)"),
    Mutation("active-agent", "forced to allow", "hook", "require-active-agent.py", "decide",
             lambda *a, **k: (True, "mutated", ()), must_fail="block: MILO"),
    Mutation("active-agent", "says 'then' where Taylor's docs say 'and'", "module", "team", "not_switched_on",
             _drifted_wording, must_fail="exact text: MILO"),
    Mutation("privacy-screen", "passes everything", "module", "privacy_screen", "screen", lambda text: None,
             must_fail="block: health"),
    Mutation("privacy-stamp", "forced to allow", "module", "docs_edit", "check_privacy", lambda *a, **k: None,
             must_fail="block: a flagged proposal SAGE never reviewed"),
    Mutation("privacy-agent", "forced to allow", "hook", "require-privacy-agent.py", "decide",
             lambda *a, **k: (True, "mutated"), must_fail="block: WREN runs the reviewer"),
]


def self_test(names: list[str]) -> int:
    problems: list[Problem] = []
    total = 0
    for name in names:
        if VERBOSE:
            print(f"  [{name}]")
        try:
            count = CHECKS[name](problems)
        except Exception as exc:  # noqa: BLE001
            # swallow: turned into a reported failure. A check that crashed has not
            # passed, and letting the traceback escape would stop the rest running.
            problems.append(Problem(name, "the check itself crashed", "a verdict",
                                    f"{exc.__class__.__name__}: {exc}"))
            count = 0
        total += count
        if VERBOSE:
            print(f"  {name:<22} {count} case(s)\n")

    if problems:
        print(f"\nSELF-TEST FAIL -- {len(problems)} of {total} case(s) do not behave as documented:\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nA gate that no longer blocks its fixture is not a gate. A gate that now")
        print("blocks its near-miss is the one somebody switches off.")
        return 1
    print(f"SELF-TEST OK -- {total} cases across {len(names)} gates: every rule blocks its "
          f"fixture and passes its near-miss")
    return 0


def mutation_test() -> int:
    """Break each gate on purpose and prove the self-test notices, on the case it targets."""
    global VERBOSE
    VERBOSE = False
    undetected = []
    for m in MUTATIONS:
        real_loader = load_hook

        def mutated_loader(name, _m=m):
            module = real_loader(name)
            if name == _m.target:
                setattr(module, _m.attr, _m.replacement(getattr(module, _m.attr)) if _m.wraps else _m.replacement)
            return module

        problems: list[Problem] = []
        if m.where == "hook":
            patcher = mock.patch(f"{__name__}.load_hook", side_effect=mutated_loader)
        else:
            module = importlib.import_module(m.target)
            replacement = m.replacement(getattr(module, m.attr)) if m.wraps else m.replacement
            patcher = mock.patch.object(module, m.attr, replacement)
        with patcher, contextlib.redirect_stdout(open(os.devnull, "w")):
            try:
                CHECKS[m.gate](problems)
            except Exception as exc:  # noqa: BLE001
                # swallow: a crash under mutation still counts as "detected"
                problems.append(Problem(m.gate, f"crashed under mutation ({m.must_fail})", "", str(exc)))
        aimed = [p for p in problems if m.must_fail in p.label] if m.must_fail else problems
        print(f"  mutation: {m.gate:<22} {m.target}:{m.attr} {m.what} -> self-test reports "
              f"{len(problems)} failing case(s)" + ("" if aimed else "   UNDETECTED"))
        if m.must_fail:
            for problem in aimed[:1]:
                print(f"      red: {problem.label}")
                print(f"           expected {problem.expected}, got {problem.got}")
        if not aimed:
            undetected.append(f"{m.gate} ({m.what})")
    if undetected:
        print(f"\nMUTATION TEST FAIL -- the self-test stayed green under: {'; '.join(undetected)}.")
        return 1
    gates = len({m.gate for m in MUTATIONS})
    print(f"\nMUTATION TEST OK -- all {len(MUTATIONS)} mutations across {gates} gates turn the self-test red, "
          f"the aimed ones on the case they target.")
    return 0


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true", help="run every fixture")
    parser.add_argument("--mutation-test", action="store_true", help="prove the self-test can fail")
    parser.add_argument("--verbose", action="store_true", help="print every case and its observed verdict")
    parser.add_argument("--only", nargs="*", choices=sorted(CHECKS), help="run only these gates")
    args = parser.parse_args()
    VERBOSE = args.verbose
    if args.mutation_test:
        return mutation_test()
    if not args.self_test:
        parser.print_help()
        return 2
    return self_test(args.only or list(CHECKS))


if __name__ == "__main__":
    sys.exit(main())
