"""PreToolUse (the egress set): nothing leaves without an approval bound to the bytes.

PORTED FROM PIPER, AND COLD IN PHASE 1. It is wired on every tool call, and nothing
Phase 1 does matches it: there is no send, no Drive write and no draft. Taylor
never sees an approval prompt in Phase 1. It is wired anyway so that Phase 3 and
Phase 5 add a pattern, not a gate.

scripts/docs_edit.py IS DELIBERATELY NOT AN EGRESS PATTERN. Blueprint s.1 lists
"adding an explicitly requested topic, recording a clear commitment, updating a
known deadline, marking an action done" as REVERSIBLE ESTABLISHED OPERATIONS that
execute on a clear command. Gating them behind an approval row would contradict a
protected requirement. Doc writes are held by different mechanisms instead: the
registered-Doc allowlist and fixture mode inside docs_edit.py, the WREN-only gate
in require-delivery-agent.py, writeControl, and the mandatory read-back.

THIS IS THE HARD BOUNDARY. Layer 0, the per-agent tool grants in frontmatter,
shapes what an agent attempts; it is a soft boundary and a model can talk its way
around a soft boundary. This gate does not care who is asking. It asks one
question: is there an approved, unspent, unexpired row whose payload_sha256
equals the SHA-256 of the tool input in front of me right now?

RECOMPUTED, NOT TRUSTED. The hash is computed here from the actual tool input,
using the same canonical encoding scripts/approvals.py used when the row was
created. That is the entire point. An approval for "send the vacation reminder"
that is not bound to the bytes lets the agent re-draft after approval and send
something else, with a perfectly valid approval row sitting behind it.

SPENT IN THE SAME TRANSACTION THAT SELECTS IT. Under BEGIN IMMEDIATE, so two
hooks racing on the same approval cannot both win, and an approved send cannot be
replayed tomorrow.

WHAT COUNTS AS EGRESS. Two families, both listed below: tool names that send or
write to a system of record, and Bash invocations of the send and write scripts.
Drafts to the owner's own mailbox are exempt by rule (self_draft_exempt below),
because drafting is free and making it expensive is how a system goes unused.

Fails closed on an unreadable payload and on an unreachable database. An egress
gate that cannot reach its ledger has not checked anything, and the correct
response to "I cannot tell whether this was approved" is not to send it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _failsafe import run_gate  # noqa: E402  -- standard library only, so it loads when the rest cannot

# A failed import must end in a refusal, never in Python's own exit 1, which lets the call through.
try:
    import _audit  # noqa: E402
    from _gate import (  # noqa: E402
        REPO_ROOT,
        PayloadUnreadable,
        block,
        deny_environment,
        first_field,
        read_payload,
        resolve_agent,
        tool_input,
    )
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

HOOK = "require-approval"

# Tool names that put bytes into somebody else's system. Matched case-insensitively
# as a substring of the tool name, because the same capability arrives under
# several MCP server prefixes.
EGRESS_TOOL_PATTERNS = (
    r"gmail[_a-z]*send",
    r"send[_a-z]*message",
    r"send[_a-z]*email",
    r"drive[_a-z]*(create|update|upload|write|delete)",
    r"sheets[_a-z]*(append|update|write|batch_update)",
    r"docs[_a-z]*(create|update|batch_update)",
    r"signnow",
    r"browser_file_upload",
)

# Creating a draft puts bytes into a mailbox, so it belongs in the egress set.
# It was previously ungated by OMISSION -- no pattern above happened to match a
# draft tool -- which is the worst of both worlds: the safe behaviour was an
# accident of the regex rather than a decision, and it would have changed the
# first time somebody added `draft` to the list above. It is now gated by rule
# and exempted by rule. See SELF_DRAFT below.
DRAFT_TOOL_PATTERNS = (
    r"gmail[_a-z]*draft",
    r"draft[_a-z]*create",
    r"create[_a-z]*draft",
)

# Bash invocations that do the same thing from a script.
# None of these exist in Phase 1. They are the names later phases will use, so the
# gate is already pointing at them the day they land.
EGRESS_SCRIPT_PATTERN = re.compile(
    r"\b(gmail_send|calendar_write|drive_write|sheets_write)[\w-]*\.py\b",
    re.I,
)
DRAFT_SCRIPT_PATTERN = re.compile(r"\bgmail_draft[\w-]*\.py\b", re.I)

# Taylor's own mailbox. HARDCODED, and no environment variable is consulted:
# this constant is the entire width of an exemption from the hard boundary, and
# an environment variable is something a process inherits rather than something a
# person decides.
OWNER_MAILBOX = "t.iwaasa@gretabar.com"

# Keys a draft's recipients could arrive under, across MCP servers.
RECIPIENT_KEYS = ("to", "cc", "bcc", "recipient", "recipients", "toRecipients")
RECIPIENT_FLAGS = re.compile(r"--(?:to|cc|bcc)[=\s]+(\S+)", re.I)
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def is_egress(tool_name: str, payload: dict) -> tuple[bool, str]:
    """(gated, why). why names the rule so the audit row and the message agree."""
    lowered = (tool_name or "").lower()
    for pattern in EGRESS_TOOL_PATTERNS + DRAFT_TOOL_PATTERNS:
        if re.search(pattern, lowered):
            return True, f"tool matches /{pattern}/"

    if lowered in ("bash", "powershell"):
        command = first_field(payload, "command")
        for pattern in (EGRESS_SCRIPT_PATTERN, DRAFT_SCRIPT_PATTERN):
            match = pattern.search(command)
            if match:
                return True, f"command invokes {match.group(0)}"
    return False, ""


def is_draft(tool_name: str, payload: dict) -> bool:
    """True when this call creates a DRAFT rather than sending or writing."""
    lowered = (tool_name or "").lower()
    if any(re.search(pattern, lowered) for pattern in DRAFT_TOOL_PATTERNS):
        return True
    if lowered in ("bash", "powershell"):
        command = first_field(payload, "command")
        # A command that invokes both is a send, not a draft. Order matters here.
        if EGRESS_SCRIPT_PATTERN.search(command):
            return False
        return bool(DRAFT_SCRIPT_PATTERN.search(command))
    return False


def _addresses_from(value: object) -> list[str]:
    """Every address inside a recipient value, whatever shape it arrived in."""
    if isinstance(value, str):
        return ADDRESS.findall(value)
    if isinstance(value, list):
        found: list[str] = []
        for item in value:
            found += _addresses_from(item)
        return found
    if isinstance(value, dict):
        found = []
        for key in ("email", "address", "emailAddress"):
            if key in value:
                found += _addresses_from(value[key])
        return found
    return []


def recipients_of(tool_name: str, payload: dict) -> list[str] | None:
    """Every address this call would reach, or None if they cannot be established.

    None is a real answer and the caller must treat it as "not exempt". An
    exemption granted because the recipient list could not be parsed is not an
    exemption, it is a hole -- the same short-circuit-to-pass the rest of this
    directory exists to stop.
    """
    data = tool_input(payload)
    if (tool_name or "").lower() in ("bash", "powershell"):
        command = first_field(payload, "command")
        if not command:
            return None
        flagged = RECIPIENT_FLAGS.findall(command)
        addresses = [a for value in flagged for a in _addresses_from(value)]
        # A --to that carried something this could not read as an address means
        # the list is not fully known, so it is not fully checkable.
        if len(addresses) != len(flagged):
            return None
        return [a.lower() for a in addresses]

    found: list[str] = []
    seen_key = False
    for scope in (data, data.get("message") if isinstance(data.get("message"), dict) else {}):
        for key in RECIPIENT_KEYS:
            if key in scope:
                seen_key = True
                found += _addresses_from(scope[key])
    if not seen_key:
        return None
    return [a.lower() for a in found]


def self_draft_exempt(tool_name: str, payload: dict) -> tuple[bool, str]:
    """(exempt, why). A draft that reaches Taylor's own mailbox and nobody else.

    WHY THIS EXEMPTION EXISTS. Blueprint s.1: routine private assistant email to
    Taylor is meant to run without ceremony. Making him approve bytes that reach
    nobody but him is how approval fatigue starts, and the moment approvals are
    clicked without reading, the hash binding is theatre.

    WHY IT IS THIS NARROW. The test is structural, not a `kind` label the caller
    supplies: the actual recipient list is parsed out of the actual tool input,
    and ONE address that is not his disqualifies the whole call. A draft is also
    not a send -- a send to his own mailbox still needs an approval, because the
    thing being gated is the send path, not the destination.
    """
    if not is_draft(tool_name, payload):
        return False, ""
    addresses = recipients_of(tool_name, payload)
    if addresses is None:
        return False, "the recipient list could not be parsed, so it could not be checked"
    if not addresses:
        return False, "the draft names no recipient this hook could find"
    others = sorted({a for a in addresses if a != OWNER_MAILBOX})
    if others:
        return False, f"it also reaches {', '.join(others)}"
    return True, f"draft to {OWNER_MAILBOX} only"


def deny(reason: str, digest: str, tool_name: str, why: str, not_exempt: str = "") -> int:
    head = [
        "BLOCKED: this call leaves the machine and has no approval bound to it.",
        "",
        f"  tool:   {tool_name}  ({why})",
        f"  sha256: {digest}",
        f"  reason: {reason}",
    ]
    if not_exempt:
        # A draft that ALMOST qualified for the self-draft exemption. Saying why
        # it did not is the difference between a gate somebody understands and a
        # gate somebody works around.
        head += [
            "  note:   this IS a draft, but it does not qualify for the self-draft",
            f"          exemption: {not_exempt}",
        ]
    return block(head + [
        "",
        "An approval here is a database row bound to the exact bytes, approved",
        "once by Taylor and spendable once. It is not a permission to do a kind of",
        "thing; it is a permission to do THIS thing, unchanged.",
        "",
        "To raise one, write the exact payload to a file and run:",
        "",
        "  python scripts/approvals.py create --kind <kind> --target <who> \\",
        f"      --summary \"<one line>\" --tool {tool_name} --input-file <file>",
        "",
        "then ask Taylor to approve it. He sees the summary, the recipient count and",
        "the hash before he does.",
        "",
        "IF THE BYTES CHANGED SINCE THE APPROVAL, THIS IS WORKING AS DESIGNED. Do",
        "not adjust the payload to make it match an old approval. Raise a new one.",
        "",
        "REPHRASING WILL NOT CHANGE THIS. It is a hash comparison.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    tool_name = str(payload.get("tool_name") or "")
    gated, why = is_egress(tool_name, payload)
    if not gated:
        return 0

    agent = resolve_agent(payload) or ""
    session = str(payload.get("session_id") or "")

    exempt, not_exempt = self_draft_exempt(tool_name, payload)
    if exempt:
        # Same audit row as any other gated decision. The exemption removes the
        # PROMPT, never the record: "what was drafted last Tuesday" has to
        # stay answerable, and an unlogged exemption would be a blind spot rather
        # than a convenience.
        _audit.record(hook=HOOK, tool=tool_name, agent=agent, decision="allow_self_draft",
                      rule_id="draft_create:self", target=OWNER_MAILBOX,
                      record_count=1, detail=not_exempt, session_id=session)
        return 0

    try:
        scripts = str(REPO_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import approvals  # noqa: PLC0415
        import ea_db  # noqa: PLC0415

        digest = approvals.payload_hash(tool_name, tool_input(payload))
        conn = ea_db.connect()
    except Exception as exc:  # noqa: BLE001
        # swallow: converted immediately into a blocking refusal. An egress gate
        # that cannot reach its ledger must not resolve to "allow".
        _audit.record(hook=HOOK, tool=tool_name, agent=agent, decision="deny_unverifiable",
                      detail=f"{exc.__class__.__name__}: {exc}", session_id=session)
        return deny_environment(HOOK, "approvals ledger", f"{exc.__class__.__name__}: {exc}")

    try:
        row, reason = approvals.consume(conn, digest)
    except Exception as exc:  # noqa: BLE001
        # swallow: same reasoning as above. A ledger error is a refusal, not a pass.
        _audit.record(hook=HOOK, tool=tool_name, agent=agent, decision="deny_unverifiable",
                      payload_sha256=digest, detail=f"{exc.__class__.__name__}: {exc}",
                      session_id=session)
        return deny_environment(HOOK, "approvals ledger", f"{exc.__class__.__name__}: {exc}")
    finally:
        conn.close()

    if row is None:
        _audit.record(hook=HOOK, tool=tool_name, agent=agent, decision="deny",
                      rule_id="no-approval", payload_sha256=digest,
                      target=first_field(payload, "command", "file_path")[:200],
                      detail=f"{reason}{'; ' + not_exempt if not_exempt else ''}",
                      session_id=session)
        return deny(reason, digest, tool_name, why, not_exempt)

    _audit.record(hook=HOOK, tool=tool_name, agent=agent, decision="allow",
                  rule_id=f"approval:{row['kind']}", payload_sha256=digest,
                  target=str(row["target"]), record_count=int(row["record_count"] or 0),
                  approval_id=int(row["id"]), detail=str(row["summary"]),
                  session_id=session)
    return 0


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
