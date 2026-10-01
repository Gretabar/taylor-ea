"""PreToolUse (Write|Edit): every file under output/ or state/ declares its class.

PORTED FROM PIPER. CLASSIFICATION IS A POSITIVE DECLARATION, NOT A SNIFF. Every
write under output/ or state/ carries

    ea-class: private | records | shareable

in its first 40 lines, in whatever comment or frontmatter form the format allows,
and UNDECLARED IS BLOCKED. JSON carries it as a key, "ea-class": "records", which
is why the pattern below tolerates quotes around the key and the value: a Doc edit
proposal is JSON, and a declaration convention that JSON cannot satisfy is one the
proposals would all fail.

WHAT CHANGED FROM PIPER. Three classes re-cut for this system (private, records,
shareable); the declaration key; machine-managed files now include the OAuth client
and token and the build-machine marker, which no human writes as prose. The
named-list sniffer is still here but switched OFF in context/data-classes.json
(applies_to is empty): with a six-manager roster every legitimate 1:1 record names
one of them, and a sniffer that fires on every legitimate record gets switched off
anyway, just less honestly.
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
        ContextUnreadable,
        PayloadUnreadable,
        block,
        deny_environment,
        first_field,
        load_context,
        read_payload,
        repo_relative,
        resolve_agent,
    )
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

HOOK = "classify-and-place"
DECLARATION_LINES = 40
DECLARATION = re.compile(r"""["']?ea-class["']?\s*:\s*["']?([a-z]+)""", re.I)

# Files under state/ that no human writes as prose. Blocking a lock file for want of
# a frontmatter comment is exactly the false positive that gets a gate switched off.
MACHINE_MANAGED = re.compile(
    r"(^|/)(AUDIT-DEGRADED|ALERTS\.jsonl|\.gitignore|BUILD_MACHINE"
    r"|google-client\.json|google-token\.json)$"
    r"|\.(db|db-wal|db-shm|lock|tmp)$",
    re.I,
)


def declared_class(text: str) -> str | None:
    """The declared class from the first DECLARATION_LINES lines, or None."""
    head = "\n".join(text.splitlines()[:DECLARATION_LINES])
    match = DECLARATION.search(head)
    return match.group(1).lower() if match else None


def existing_head(file_path: str) -> str:
    """The head of the file already on disk, for Edit calls that do not restate it."""
    try:
        raw = Path(file_path).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""  # swallow: an absent file is a create, and a create must declare
    return "\n".join(raw.splitlines()[:DECLARATION_LINES])


def roots_for(classes: dict, name: str) -> list[str]:
    return list((classes.get(name) or {}).get("allowed_roots") or [])


def forbidden_for(classes: dict, name: str) -> list[str]:
    return list((classes.get(name) or {}).get("forbidden_roots") or [])


def _under_root(rel: str, root: str) -> bool:
    root = root.rstrip("/")
    return rel == root or rel.startswith(root + "/")


def placement_ok(rel: str, allowed_roots: list[str], forbidden_roots: list[str] = ()) -> bool:
    """Allowed by one of its roots, and not caught by a forbidden one."""
    if any(_under_root(rel, root) for root in forbidden_roots):
        return False
    return any(_under_root(rel, root) for root in allowed_roots)


def roster_names() -> list[str] | None:
    """Distinct full names from `people`, or None when the roster cannot be read."""
    try:
        scripts = str(REPO_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import ea_db  # noqa: PLC0415

        conn = ea_db.connect(read_only=True)
        try:
            rows = conn.execute(
                "SELECT full_name FROM people WHERE full_name IS NOT NULL AND full_name != ''"
            ).fetchall()
        finally:
            conn.close()
        return [str(row[0]) for row in rows]
    except Exception:  # noqa: BLE001
        # swallow: reported by the caller as sniffer_unavailable, never silently.
        return None


def names_present(text: str, roster: list[str]) -> list[str]:
    """Distinct roster names appearing in `text`, matched on the full name only."""
    hits: list[str] = []
    for name in dict.fromkeys(roster):
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in name.split()) + r"(?!\w)"
        if re.search(pattern, text, re.I):
            hits.append(name)
    return hits


def deny_undeclared(rel: str, classes: dict) -> int:
    lines = [
        "BLOCKED: this write carries no data-class declaration.",
        "",
        f"  file: {rel}",
        "",
        "Everything written under output/ or state/ declares what it holds, on one",
        "line in the first 40 lines, in whatever form the format allows. In JSON,",
        'as a key: "ea-class": "records".',
        "",
        "  ea-class: private     Taylor's private material  -> state/private/",
        "  ea-class: records     proposals, Doc snapshots   -> state/proposals/, state/records/",
        "  ea-class: shareable   text for Taylor to read    -> output/drafts/",
        "",
    ]
    for name in ("private", "records", "shareable"):
        spec = classes.get(name) or {}
        lines.append(f"  {name:10} {spec.get('definition', '')}")
    lines += [
        "",
        "This is a positive declaration on purpose. Declare it and write again.",
    ]
    return block(lines)


def deny_placement(rel: str, name: str, allowed: list[str], forbidden: list[str]) -> int:
    return block([
        f"BLOCKED: a file declared `{name}` cannot land here.",
        "",
        f"  file:      {rel}",
        f"  allowed:   {', '.join(allowed) or '(nowhere -- check context/data-classes.json)'}",
        f"  forbidden: {', '.join(forbidden) or '(nothing)'}",
        "",
        "The class decides the location. Move the file or change the declaration,",
        "but they have to agree.",
        "",
        "Rephrasing the content will not change this. It is a path check.",
    ])


def deny_named_list(rel: str, name: str, hits: list[str], threshold: int) -> int:
    return block([
        f"BLOCKED: declared {name}, reads as a named list.",
        "",
        f"  file:  {rel}",
        f"  found: {len(hits)} distinct roster names (threshold {threshold})",
        "",
        "Rewording the names will not change this check.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    file_path = first_field(payload, "file_path")
    rel = repo_relative(file_path)
    if not rel or not (rel.startswith("output/") or rel.startswith("state/")):
        return 0
    if MACHINE_MANAGED.search(rel):
        return 0

    try:
        spec = load_context("data-classes")
    except ContextUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "data-class rules", str(exc))

    classes = spec.get("classes") or {}
    body = first_field(payload, "content", "new_string")
    name = declared_class(body) or declared_class(existing_head(file_path))

    agent = resolve_agent(payload) or ""
    session = str(payload.get("session_id") or "")
    tool = str(payload.get("tool_name") or "")

    if name not in classes:
        _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny", rule_id="undeclared",
                      target=rel, detail=f"declared={name!r}", session_id=session)
        return deny_undeclared(rel, classes)

    allowed = roots_for(classes, name)
    forbidden = forbidden_for(classes, name)
    if not placement_ok(rel, allowed, forbidden):
        _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny",
                      rule_id=f"placement:{name}", target=rel,
                      detail=f"allowed={allowed} forbidden={forbidden}", session_id=session)
        return deny_placement(rel, name, allowed, forbidden)

    sniffer = spec.get("named_list_sniffer") or {}
    if name in (sniffer.get("applies_to") or []):
        threshold = int(sniffer.get("threshold") or 5)
        roster = roster_names()
        if roster is None:
            print(f"{HOOK}: the roster could not be read, so the named-list check did NOT "
                  f"run on {rel}. The declaration was accepted on its own.", file=sys.stderr)
            _audit.record(hook=HOOK, agent=agent, decision="sniffer_unavailable",
                          rule_id="named-list", target=rel, session_id=session)
            return 0
        hits = names_present(body, roster)
        if len(hits) >= threshold:
            _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny",
                          rule_id="named-list", target=rel, record_count=len(hits),
                          session_id=session)
            return deny_named_list(rel, name, hits, threshold)

    _audit.record(hook=HOOK, tool=tool, agent=agent, decision="allow",
                  rule_id=f"class:{name}", target=rel, session_id=session)
    return 0


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
