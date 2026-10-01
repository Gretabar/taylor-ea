"""Build the installable kit for Taylor's machine, and prove it carries no data and no credential.

PORTED FROM PIPER's build_piper_kit.py (itself from STEVIE's build_starter_kit.py). Two rules, kept:

1. ALLOWLIST, NEVER DENYLIST. Nothing ships unless it is named below. state/, logs/ and output/
   are not "excluded"; they are simply not on the list, and neither is anything added to them later.

2. THE VERIFICATION GATE IS THE POINT. Every selected file is scanned for credential and secret
   shapes; one hit fails the build and NOTHING is written.

WHAT CHANGED. The framework lives under .claude/ (agents, commands, skills, hooks, settings) so
the VS Code extension finds it by opening the folder. NEVER_COPY adds the Google OAuth client and
token by name, the build-machine marker (a kit that carried it would unlock code and permission
edits on Taylor's machine), and the fixture database. The gate also looks for Google's own secret
shapes: a GOCSPX- client secret and a ya29. access token. docs/acceptance/ stays behind: it is this
machine's evidence, and Taylor's machine produces its own.

Usage:
    python scripts/build_ea_kit.py --out D:\\EA-KIT            dry run: select and verify
    python scripts/build_ea_kit.py --out D:\\EA-KIT --apply    write the kit
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])

DIRECTORIES = [
    ".claude/hooks",
    ".claude/agents",
    ".claude/commands",
    ".claude/skills",
    "context",
    "scripts",
    "docs",
    "tests",
]

TOP_LEVEL_FILES = [
    "CLAUDE.md",
    "README.md",
    "INSTALL.md",
    "VENDORED-FROM.md",
    "requirements.txt",
    ".gitignore",
    ".gitattributes",
    ".env.example",
    ".claude/settings.json",
]

EMPTY_DIRECTORIES = ["state/proposals", "state/private", "state/records", "logs", "output/drafts"]

# Never copied, matched on the file name wherever it sits.
NEVER_COPY = re.compile(
    r"(^\.env$|\.env\.[^.]*$|^credentials\.json$|^token.*\.json$|^google-client\.json$|"
    r"^google-token\.json$|^BUILD_MACHINE$|\.key$|\.pem$|\.db$|\.db-wal$|\.db-shm$|\.lock$|"
    r"\.jsonl$|\.log$|\.pyc$|\.tmp$)",
    re.I,
)
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache"}
SKIP_PREFIXES = ("docs/acceptance/",)

BANNED = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r'"refresh_token"\s*:\s*"[^"]{10,}'), "an OAuth refresh token"),
    (re.compile(r'"client_secret"\s*:\s*"[^"]{10,}'), "an OAuth client secret"),
    (re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{10,}"), "a Google OAuth client secret"),
    (re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}"), "a Google access token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "an API key"),
    (re.compile(r"\bey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\."), "a JWT"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
]
DATA_ROOTS = ("state/", "output/", "logs/")
DESCRIBES_NOT_CONTAINS = {"scripts/build_ea_kit.py"}


def scan(text: str, rel: str) -> list[str]:
    hits = []
    if any(rel.startswith(root) for root in DATA_ROOTS):
        hits.append(f"it lives under {rel.split('/')[0]}/, which holds data, not framework")
    if rel not in DESCRIBES_NOT_CONTAINS:
        hits += [label for pattern, label in BANNED if pattern.search(text)]
    return hits


def gather() -> list[tuple[Path, str]]:
    selected: list[tuple[Path, str]] = []
    for name in TOP_LEVEL_FILES:
        path = REPO_ROOT / name
        if path.is_file() and not NEVER_COPY.search(path.name):
            selected.append((path, name))
    for directory in DIRECTORIES:
        root = REPO_ROOT / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            if NEVER_COPY.search(path.name) or rel.startswith(SKIP_PREFIXES):
                continue
            selected.append((path, rel))
    seen: dict[str, tuple[Path, str]] = {}
    for source, rel in selected:
        seen.setdefault(rel, (source, rel))
    return list(seen.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    print(f"Building the kit -> {out}   [{'APPLY' if args.apply else 'DRY RUN'}]\n")

    selected = gather()
    if not selected:
        print("FAIL: nothing matched the allowlist.", file=sys.stderr)
        return 2
    failures: dict[str, list[str]] = {}
    payload: list[tuple[str, bytes]] = []
    for source, rel in selected:
        data = source.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            failures[rel] = ["not text, and the kit ships no binaries"]
            continue
        hits = scan(text, rel)
        if hits:
            failures[rel] = hits
        payload.append((rel, data))

    print(f"{len(selected)} file(s) selected")
    for directory in DIRECTORIES:
        print(f"  {directory:<20} {sum(1 for _, rel in selected if rel.startswith(directory + '/'))}")
    excluded = sorted(p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "state").glob("*")
                      if p.is_file()) if (REPO_ROOT / "state").is_dir() else []
    print(f"  state/ files left behind: {', '.join(excluded) or 'none'}")

    print("\n=== VERIFICATION GATE ===")
    if failures:
        print(f"FAIL: {len(failures)} file(s) carry something that must not leave this machine:\n")
        for rel, hits in sorted(failures.items()):
            print(f"  {rel}\n      {', '.join(sorted(set(hits)))}")
        print("\nNOTHING was written.")
        return 1
    print(f"PASS: no credential or secret shape in any of the {len(payload)} files; the OAuth client, "
          f"the token, the build marker and every database stay behind.")
    if not args.apply:
        print("\nDry run. Re-run with --apply to write.")
        return 0
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for rel, data in payload:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for directory in EMPTY_DIRECTORIES:
        (out / directory).mkdir(parents=True, exist_ok=True)
        (out / directory / ".gitkeep").write_bytes(b"")
    print(f"\nWrote {len(payload)} file(s) and {len(EMPTY_DIRECTORIES)} empty directories to {out}.")
    print("On Taylor's machine, in that folder: see INSTALL.md, step by step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
