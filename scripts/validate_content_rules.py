"""Enforce the content rules at the moment text is written.

PORTED FROM PIPER (which ported it from STEVIE). Two design decisions carry over:

1. THIS LINTS THE WRITE, NOT THE REPO. The hook path reads a PreToolUse payload and
   inspects only the text about to land. A tree sweep of an established repo is red
   on its first run, and a check red from its first run gets switched off.

2. THE EMOJI PATTERN IS DELIBERATELY TIGHT. An arrow is not an emoji.

WHY THE CHARACTER CLASSES ARE BUILT FROM INTEGERS. PIPER wrote them as backslash-u
escapes so the file carried no literal glyphs, and still noted it "was blocked by
its own rule, twice". The reason, observed on this build: the hook payload arrives
with those escape sequences already decoded, so a file that merely SPELLS an emoji
as an escape reads as containing one. Building the classes from code point integers
keeps the source free of both glyphs and escapes, so editing this file can never
trip the hook it powers.

WHAT CHANGED FROM PIPER. The emoji rule is unchanged: zero tolerance, everywhere.
The em-dash rule is WIDENED from PIPER's staff-facing directories to everything
bound for a running Doc or for Taylor: Doc edit proposals (state/proposals/, which
is exactly the text WREN writes into a Doc), drafts (output/drafts/), the docs
Taylor reads (docs/) and README.md. PIPER's two HR rules (jurisdiction, personal
email) are dropped; neither applies to a 1:1 register.

THE COVERAGE HOLE, STATED: text a Python script writes through an API never passes
a Write payload. So scripts/docs_propose.py and scripts/docs_edit.py import
check_doc_bound() and refuse Doc-bound text that fails it. That is the gate for
what actually reaches a Doc; the hook is the gate for files.

Usage:
    python scripts/validate_content_rules.py --stdin-payload   # hook mode
    python scripts/validate_content_rules.py --path FILE ...
    python scripts/validate_content_rules.py --text "string"

Exits 2 on findings in hook mode (blocking), 1 in audit modes, 0 when clean.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys


def _cls(*items: int | tuple[int, int]) -> str:
    """A regex character class from code points and (low, high) ranges."""
    parts = []
    for item in items:
        if isinstance(item, tuple):
            parts.append(re.escape(chr(item[0])) + "-" + re.escape(chr(item[1])))
        else:
            parts.append(re.escape(chr(item)))
    return "[" + "".join(parts) + "]"


_VS16 = re.escape(chr(0xFE0F))

# Astral pictographs and regional-indicator flags; any BMP symbol carrying an
# explicit emoji-presentation selector; and the BMP code points that render as
# emoji by default. Arrows, box drawing and typographic marks are excluded.
EMOJI = re.compile(
    _cls((0x1F000, 0x1FAFF))
    + "|" + _cls((0x2190, 0x2BFF), 0x2122, 0x2139, 0x3030, 0x303D, 0x00A9, 0x00AE) + _VS16
    + "|" + _cls(0x2705, 0x274C, 0x274E, (0x2753, 0x2755), 0x2757, (0x2795, 0x2797),
                 0x27B0, 0x27BF, 0x2B1B, 0x2B1C, 0x2B50, 0x2B55, 0x203C, 0x2049, 0x26A0,
                 0x2764, 0x2611, 0x26D4, 0x2728)
)

EM_DASH = re.compile(re.escape(chr(0x2014)) + "|&mdash;|&#8212;|&#x2014;", re.I)

# Where the em-dash rule applies: text bound for a Doc, or for Taylor to read.
DOC_OR_TAYLOR_BOUND = (
    "state/proposals/",
    "output/drafts/",
    "docs/",
    "README.md",
)
DOC_BOUND_PATH = "state/proposals/doc-bound-text"

ALLOW = re.compile(r"content-lint:\s*allow-(emoji|em-dash)\b", re.I)


class Finding:
    def __init__(self, path: str, line: int, rule: str, detail: str):
        self.path, self.line, self.rule, self.detail = path, line, rule, detail

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.path else f"line {self.line}"
        return f"{where}: {self.rule} -- {self.detail}"


def _codepoints(text: str) -> str:
    """Name offenders by code point, never by glyph: a cp1252 console cannot print one."""
    return ", ".join(sorted({f"U+{ord(c):04X}" for c in text}))


def _allowed(lines: list[str], index: int, rule: str) -> bool:
    for probe in (index, index - 1):
        if 0 <= probe < len(lines):
            match = ALLOW.search(lines[probe])
            if match and match.group(1).lower() == rule:
                return True
    return False


def _scoped(path: str) -> bool:
    normalised = path.replace("\\", "/")
    return any(seg in normalised or normalised.endswith(seg) for seg in DOC_OR_TAYLOR_BOUND)


def check_text(text: str, path: str = "") -> list[Finding]:
    """Check a block of text. Importable so scripts can gate what they write."""
    findings: list[Finding] = []
    em_dash_scoped = _scoped(path)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        hits = EMOJI.findall(line)
        if hits and not _allowed(lines, i, "emoji"):
            findings.append(Finding(path, i + 1, "emoji",
                                    f"{_codepoints(''.join(hits))} (zero tolerance, any output)"))
        if em_dash_scoped and EM_DASH.search(line) and not _allowed(lines, i, "em-dash"):
            findings.append(Finding(path, i + 1, "em-dash",
                                    "em dash in text bound for a Doc or for Taylor. Use a comma, "
                                    "a colon, or rewrite the sentence."))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def check_doc_bound(text: str) -> list[Finding]:
    """The rules for text that will be written into a running Doc. No escapes honoured."""
    findings = []
    if EMOJI.search(text):
        findings.append(Finding(DOC_BOUND_PATH, 1, "emoji",
                                f"{_codepoints(''.join(EMOJI.findall(text)))} in Doc-bound text"))
    if EM_DASH.search(text):
        findings.append(Finding(DOC_BOUND_PATH, 1, "em-dash", "em dash in Doc-bound text"))
    return findings


def _report(findings: list[Finding], *, blocking: bool) -> int:
    if not findings:
        return 0
    label = "BLOCKED" if blocking else "FAIL"
    print(f"{label} -- {len(findings)} content-rule issue(s):\n", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    return 2 if blocking else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--stdin-payload", action="store_true",
                        help="read a PreToolUse hook payload from stdin (blocking mode)")
    parser.add_argument("--path", nargs="*", default=[], help="check specific files")
    parser.add_argument("--text", help="check one string as Doc-bound text")
    args = parser.parse_args()

    if args.stdin_payload:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            # Content quality, not safety: every safety gate already fails closed on
            # the same payload. Say so and allow; silence here would be the bug.
            print("validate_content_rules.py: hook payload unreadable; content rules "
                  "were NOT checked for this write.", file=sys.stderr)
            return 0
        tool_input = payload.get("tool_input") or {}
        path = tool_input.get("file_path") or ""
        text = tool_input.get("content")
        if text is None:
            text = tool_input.get("new_string")
        if text is None:
            return 0
        return _report(check_text(str(text), path), blocking=True)

    if args.text is not None:
        code = _report(check_doc_bound(args.text), blocking=False)
        if code == 0:
            print("OK -- Doc-bound text passes")
        return code

    targets = [t for t in dict.fromkeys(args.path) if os.path.isfile(t)]
    if not targets:
        print("No files to check. Pass --path or --text.", file=sys.stderr)
        return 2
    findings: list[Finding] = []
    for path in targets:
        findings.extend(check_text(io.open(path, encoding="utf-8-sig", errors="replace").read(), path))
    code = _report(findings, blocking=False)
    if code == 0:
        print(f"OK -- {len(targets)} file(s), no content-rule issues")
    return code


if __name__ == "__main__":
    sys.exit(main())
