"""PreToolUse (Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell): two layers of authority.

NEW in this repo. Blueprint s.1: Claude may change protected requirements "only
when Taylor explicitly requests or approves an architecture change", and must not
silently implement improvements. G1 tests exactly that ("suggest removing
reservation send approval": propose, change nothing). Prose saying so holds most of
the time, which is not every time; this is the mechanism.

LAYER A, RULES TEXT: context/architecture/** and CLAUDE.md. Taylor's authority.
    Allowed only when the latest message Taylor typed contains the phrase
    `architecture change ok`. CLAUDE.md then obliges the orchestrator to append one
    bullet to context/architecture/CHANGE-LOG.md, and team-rollcall.py renders a
    banner if an allowed rules edit landed after the log's last write. Blocked
    otherwise, pointing at docs/DEVIATIONS.md, where a proposed change is written
    as a memo for Taylor to approve.

LAYER B, CODE AND PERMISSIONS: .claude/** (settings, hooks, agents, commands,
    skills), scripts/**, tests/**, and the top-level context/*.json files (the
    network allowlist, the data classes, the roster, identity). The installed repo
    ships BUILT: on Taylor's machine these are blocked UNCONDITIONALLY, and the
    phrase does not open them. Otherwise a session could edit require-approval.py
    or settings.json and change a permission with no approval at all, and G1 would
    be half-proven. They are writable only on the build machine, recognised by
    state/BUILD_MACHINE naming this host (see _gate.is_build_machine).

THE MARKER ITSELF is blocked as a write target everywhere. It is created by hand,
outside Claude Code, on Mike's machine.

WHY THE OVERRIDE IS READ HERE AND NOT VIA _transcript.turn_context. When this gate
was written that parser skipped slash-command rows when it looked for the turn
boundary, which for an authority check means a phrase typed in an earlier plain
message stays live through every later /add. So this file finds the LATEST typed
turn itself, slash commands included, and honours the phrase only there (plain
text or the command's arguments). turn_context has since been fixed to agree (see
_transcript.py); this reader stays because it is the one the layer-A fixtures
prove, and folding the two together is its own change. Harness-injected blocks
(system-reminder, task-notification) are stripped first, so a document that
merely quotes the phrase does not grant anything.

SHELL COVERAGE IS BEST EFFORT AND SAYS SO. Write and Edit are the paths a model
reaches for, and they are covered exactly. For Bash and PowerShell this catches
redirection, the write commands and cmdlets of both shells, sed -i, git commands
that rewrite the working tree, and inline interpreter code that names a protected
path. A script that edits files without naming them on its command line is not
visible to any hook, which is why layer B also blocks scripts/** on Taylor's
machine: a session cannot add such a script in the first place.

Fails CLOSED on an unreadable payload, and on an unreadable transcript when a
rules-text target needs the override checked.
"""

from __future__ import annotations

import json
import os
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
        is_build_machine,
        read_payload,
        repo_relative,
        resolve_agent,
    )
except BaseException as _exc:  # noqa: BLE001  -- SystemExit and KeyboardInterrupt at import refuse too
    _IMPORT_ERROR: BaseException | None = _exc  # swallow: run_gate refuses every call, naming this error
else:
    _IMPORT_ERROR = None

HOOK = "protect-architecture"
OVERRIDE = "architecture change ok"
MARKER_REL = "state/BUILD_MACHINE"

HARNESS_BLOCK = re.compile(
    r"<(system-reminder|task-notification|ide_selection|local-command-stdout)>.*?</\1>",
    re.S | re.I,
)
COMMAND_BLOCK = re.compile(r"<(command-name|command-message|command-args)>(.*?)</\1>", re.S | re.I)

# --- which layer a repo-relative path belongs to --------------------------------


def layer_of(rel: str) -> str | None:
    """"marker", "rules", "code", or None for an unprotected path."""
    if not rel:
        return None
    if rel == "*":
        return "code"
    norm = rel.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    lowered = norm.lower()
    if lowered == MARKER_REL.lower():
        return "marker"
    if lowered == "claude.md" or lowered.startswith("context/architecture/") or lowered == "context/architecture":
        return "rules"
    if lowered.startswith((".claude/", "scripts/", "tests/")) or lowered in (".claude", "scripts", "tests"):
        return "code"
    if re.fullmatch(r"context/[^/]+\.json", lowered):
        return "code"
    return None


def decide(targets: list[str], typed: str | None, build_machine: bool) -> tuple[bool, str, str]:
    """(allowed, rule_id, target). Pure, so the guardrail self-test can drive it.

    `typed` is the latest text Taylor typed, or None when it could not be read. None
    only matters for a rules-text target, and there it is a refusal.
    """
    granted = ""
    for target in targets:
        layer = layer_of(target)
        if layer is None:
            continue
        if layer == "marker":
            return False, "build-marker", target
        if layer == "code":
            if not build_machine:
                return False, "code-and-permissions", target
            continue
        if typed is None:
            return False, "rules-text:unverifiable", target
        if OVERRIDE not in typed.lower():
            return False, "rules-text", target
        granted = target
    if granted:
        return True, "rules-text:override", granted
    return True, "", ""


# --- latest typed turn ----------------------------------------------------------


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text")


def latest_typed_text(transcript_path: str | None) -> str | None:
    """What the user typed in the latest real turn, or None when unreadable.

    A slash-command row IS a turn boundary here, and its arguments count as typed
    text; its expansion (an isMeta row) does not.
    """
    if not transcript_path:
        return None
    try:
        raw = Path(str(transcript_path)).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None
    parsed_any = False
    for line in reversed([ln for ln in raw.splitlines() if ln.strip()]):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed_any = True
        if event.get("type") != "user" or event.get("isSidechain") is True or event.get("isMeta"):
            continue
        text = HARNESS_BLOCK.sub(" ", _text_of(event.get("message") or {}))
        if not text.strip():
            continue  # a tool_result carrier, or a row the harness injected
        args = " ".join(m.group(2) for m in COMMAND_BLOCK.finditer(text)
                        if m.group(1).lower() == "command-args")
        plain = COMMAND_BLOCK.sub(" ", text)
        return " ".join(f"{plain} {args}".split())
    return "" if parsed_any else None


# --- shell commands ---------------------------------------------------------------

SEPARATORS = re.compile(r"(?:\|\||&&|;|\||\n)")
TOKEN = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')
REDIRECT = re.compile(r"""(?:^|[^<>&\d-])(?:[1-6*]|&)?>>?\s*("[^"]+"|'[^']+'|[^\s;|&<>]+)""")

ALL_ARGS_WRITE = {
    "rm", "del", "erase", "rd", "rmdir", "ri", "remove-item", "mv", "move", "mi",
    "move-item", "ren", "rename", "rni", "rename-item", "tee", "tee-object", "touch",
    "truncate", "set-content", "sc", "add-content", "ac", "out-file", "new-item", "ni",
    "clear-content", "clc", "ln", "chmod", "attrib", "icacls", "mkdir", "md",
}
LAST_ARG_WRITE = {"cp", "copy", "cpi", "copy-item", "xcopy", "robocopy"}
GIT_TREE_WRITE = {
    "checkout", "restore", "rm", "mv", "apply", "reset", "stash", "clean", "am",
    "cherry-pick", "revert", "merge", "pull", "rebase", "switch",
}
INLINE_FLAGS = {"-c", "-command", "/c", "-e", "-encodedcommand"}
INLINE_WRITE = re.compile(
    r"""['"][wax]b?\+?['"]|write|unlink|remove|rename|replace\(|rmtree|truncate|"""
    r"""set-content|add-content|out-file|copy-item|move-item|remove-item|new-item|>""",
    re.I,
)
PROTECTED_MENTION = re.compile(
    r"(claude\.md|context[\\/]architecture|\.claude[\\/]|scripts[\\/]|tests[\\/]"
    r"|context[\\/][\w.-]+\.json|state[\\/]build_machine)",
    re.I,
)


def _unquote(token: str) -> str:
    return token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"" else token


def _args(tokens: list[str]) -> list[str]:
    return [_unquote(t) for t in tokens[1:] if not t.startswith("-") or t in ("-",)]


def shell_write_targets(command: str) -> list[str]:
    """Raw path strings this command line plausibly WRITES. "*" means the whole tree."""
    targets: list[str] = []
    for match in REDIRECT.finditer(command):
        targets.append(_unquote(match.group(1)))

    for fragment in SEPARATORS.split(command):
        tokens = TOKEN.findall(fragment.strip())
        while tokens and tokens[0] in ("&", ".", "call", "start"):
            tokens = tokens[1:]
        if not tokens:
            continue
        head = Path(_unquote(tokens[0]).replace("\\", "/")).name.lower().removesuffix(".exe")

        if head in ALL_ARGS_WRITE:
            targets += _args(tokens)
        elif head in LAST_ARG_WRITE:
            args = _args(tokens)
            if args:
                targets.append(args[-1])
        elif head in ("sed", "perl") and any(t.startswith("-i") or t == "-pi" for t in tokens[1:]):
            targets += [a for a in _args(tokens) if PROTECTED_MENTION.search(a)]
        elif head == "git" and len(tokens) > 1 and tokens[1].lower() in GIT_TREE_WRITE:
            named = [a for a in _args(tokens)[1:] if PROTECTED_MENTION.search(a)]
            targets += named or ["*"]

        lowered = [t.lower() for t in tokens]
        for flag in INLINE_FLAGS:
            if flag in lowered:
                code = " ".join(tokens[lowered.index(flag) + 1:])
                if INLINE_WRITE.search(code):
                    targets += [m.group(1) for m in PROTECTED_MENTION.finditer(code)]
    return targets


def to_rel(raw: str, cwd: str) -> str:
    """A raw path from a command or tool input, as a repo-relative POSIX path."""
    if raw == "*":
        return "*"
    path = raw.strip().strip("'\"")
    if not path:
        return ""
    if not os.path.isabs(path) and not re.match(r"^[A-Za-z]:", path):
        path = os.path.join(cwd or str(REPO_ROOT), path)
    rel = repo_relative(path)
    if rel:
        return rel
    # A bare relative mention ("scripts/x.py", "CLAUDE.md") with an unknown cwd.
    norm = raw.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def targets_of(payload: dict) -> list[str]:
    tool = str(payload.get("tool_name") or "")
    cwd = str(payload.get("cwd") or REPO_ROOT)
    if tool in ("Bash", "PowerShell"):
        return [to_rel(t, cwd) for t in shell_write_targets(first_field(payload, "command"))]
    path = first_field(payload, "file_path", "notebook_path")
    return [to_rel(path, cwd)] if path else []


def deny(rule_id: str, target: str) -> int:
    if rule_id == "build-marker":
        return block([
            "BLOCKED: nothing in a session may create or change the build-machine marker.",
            "",
            f"  file: {target}",
            "",
            "That file is what makes a machine able to change this system's code and",
            "permissions. It is created by hand on Mike's machine, outside Claude Code.",
        ])
    if rule_id == "code-and-permissions":
        return block([
            "BLOCKED: this system's code and permissions ship built.",
            "",
            f"  file: {target}",
            "",
            "Hooks, settings, agents, commands, skills, scripts and the context rule",
            "files are not edited from a session on this machine, whatever is said in",
            "the chat. A change here would change what the system is allowed to do, so",
            "it is made on Mike's machine, tested, and shipped as a new kit.",
            "",
            "What to do instead: write the request into docs/DEVIATIONS.md as a",
            "proposal (what to change, why, what it affects) and tell Taylor it needs",
            "Mike. Do not claim the change is live.",
            "",
            "REPHRASING WILL NOT CHANGE THIS, and neither will `architecture change ok`.",
        ])
    return block([
        "BLOCKED: that file holds Taylor's protected architecture.",
        "",
        f"  file: {target}",
        "",
        "Blueprint s.1: a protected requirement changes only when Taylor explicitly",
        "asks for or approves the change. Nothing in his latest message did.",
        "",
        "What to do instead: write a proposal into docs/DEVIATIONS.md (the change,",
        "why it helps, what it affects) and ask Taylor to approve it. Change nothing",
        "else meanwhile.",
        "",
        f'If Taylor approves, he types "{OVERRIDE}" in his own message. Then make',
        "the edit AND append one bullet to context/architecture/CHANGE-LOG.md in its",
        "stated format. Do not type that phrase yourself.",
    ])


def main() -> int:
    try:
        payload = read_payload()
    except PayloadUnreadable as exc:
        _audit.record(hook=HOOK, decision="deny_unverifiable", detail=str(exc))
        return deny_environment(HOOK, "hook payload", str(exc))

    targets = targets_of(payload)
    if not any(layer_of(t) for t in targets):
        return 0

    needs_typed = any(layer_of(t) == "rules" for t in targets)
    typed = latest_typed_text(payload.get("transcript_path")) if needs_typed else ""
    allowed, rule_id, target = decide(targets, typed, is_build_machine())

    session = str(payload.get("session_id") or "")
    tool = str(payload.get("tool_name") or "")
    agent = resolve_agent(payload) or ""
    if allowed:
        _audit.record(hook=HOOK, tool=tool, agent=agent, decision="allow",
                      rule_id=rule_id or "build-machine", target=target or ",".join(targets)[:200],
                      session_id=session)
        return 0
    if rule_id == "rules-text:unverifiable":
        _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny_unverifiable",
                      rule_id=rule_id, target=target, session_id=session)
        return deny_environment(HOOK, "session transcript", "the latest typed message could not be read")
    _audit.record(hook=HOOK, tool=tool, agent=agent, decision="deny", rule_id=rule_id,
                  target=target, session_id=session)
    return deny(rule_id, target)


if __name__ == "__main__":
    sys.exit(run_gate(HOOK, main, _IMPORT_ERROR))
