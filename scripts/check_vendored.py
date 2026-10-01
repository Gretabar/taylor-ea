"""Diff this repo's vendored copies against the files they came from.

PORTED FROM PIPER. STANDALONE MEANS IT DRIFTS. This system runs on Taylor's
machine and is maintained on Mike's; PIPER and STEVIE keep evolving. The moment a
fix lands in a shared file, one copy has it and the other does not, and nothing
anywhere says so. Copies are fine. UNDOCUMENTED copies are how one parser ended up
in four places in STEVIE, three of them subtly different.

So VENDORED-FROM.md is a machine-readable table, and this reads it back:

  VERBATIM  must stay byte-identical to the source. If it is not, somebody edited a
            vendored file in place. Fix it upstream and re-vendor.
  PORT      adapted deliberately and EXPECTED to differ. What is checked is whether
            the SOURCE has moved since the port, reported as drift to review.
  NEW       no upstream. Recorded so the manifest is a complete inventory; checked
            only for "the file changed since the manifest was written".

WHAT CHANGED FROM PIPER. Two upstreams instead of one: the source column carries
an upstream prefix (`PIPER:scripts/job_lock.py`, `STEVIE:scripts/upload_to_drive.py`)
and --upstream takes NAME=PATH, repeatable. A bare path means PIPER, which matches
the plan's `check_vendored.py --upstream C:\\PIPER`. --rehash refreshes the local
hash of PORT and NEW rows after a deliberate edit, and refuses to touch a VERBATIM
row, because "the manifest now agrees with the edit" is exactly the lie VERBATIM
exists to prevent.

    python scripts/check_vendored.py                             local integrity
    python scripts/check_vendored.py --upstream C:\\PIPER         plus PIPER rows
    python scripts/check_vendored.py --upstream PIPER=C:\\PIPER --upstream STEVIE=C:\\Users\\kells\\STEVIE
    python scripts/check_vendored.py --rehash                    after editing a PORT/NEW file

Exit 0 clean, 1 when a VERBATIM file was edited or anything drifted, 2 when the
manifest itself cannot be read.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])
MANIFEST = REPO_ROOT / "VENDORED-FROM.md"

# | `local` | `UPSTREAM:source` or `-` | `git` | `source sha256` or `-` | `local sha256` | MODE |
ROW = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|"
    r"\s*`([0-9a-f]{64}|-)`\s*\|\s*`([0-9a-f]{64})`\s*\|\s*(VERBATIM|PORT|NEW)\s*\|",
    re.I | re.M,
)


class Entry:
    def __init__(self, match: re.Match):
        self.local, source, self.git_sha, source_hash, local_hash, mode = match.groups()
        self.mode = mode.upper()
        self.upstream, _, self.source = source.partition(":") if ":" in source else ("", "", source)
        self.source_hash = source_hash.lower()
        self.local_hash = local_hash.lower()
        self.span = match.span(5)


def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None  # swallow: an absent file is a finding the caller reports


def load_manifest() -> tuple[str, list[Entry]]:
    text = MANIFEST.read_bytes().decode("utf-8", errors="replace")
    entries = [Entry(m) for m in ROW.finditer(text)]
    if not entries:
        raise ValueError(f"{MANIFEST} holds no parseable rows")
    return text, entries


def parse_upstreams(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        name, sep, path = value.partition("=")
        if not sep:
            name, path = "PIPER", value
        roots[name.strip().upper()] = Path(path.strip())
    return roots


def rehash(text: str, entries: list[Entry]) -> tuple[str, list[str], list[str]]:
    """Rewrite local sha256 cells of PORT and NEW rows. Returns (text, changed, refused)."""
    changed, refused = [], []
    for entry in sorted(entries, key=lambda e: e.span[0], reverse=True):
        actual = sha256(REPO_ROOT / entry.local)
        if actual is None or actual == entry.local_hash:
            continue
        if entry.mode == "VERBATIM":
            refused.append(entry.local)
            continue
        text = text[:entry.span[0]] + actual + text[entry.span[1]:]
        changed.append(entry.local)
    return text, changed, refused


TABLE_END = "\n<!-- end of manifest table -->"


def git_sha(root: Path, rel: str) -> str:
    """Short commit of the source file, "untracked" when there is none to name."""
    import subprocess  # noqa: PLC0415

    try:
        done = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%h", "--", rel],
                              capture_output=True, text=True, timeout=20)
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", rel],
                               capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return "untracked"
    sha = (done.stdout or "").strip()
    if done.returncode != 0 or not sha or (dirty.stdout or "").strip():
        return "untracked"  # not a repo, never committed, or modified since the commit
    return sha


def add_row(local: str, source: str, mode: str, roots: dict[str, Path]) -> str:
    """Append one manifest row, computing both hashes. Returns the row."""
    mode = mode.upper()
    local_hash = sha256(REPO_ROOT / local)
    if local_hash is None:
        raise ValueError(f"{local} does not exist")
    if mode == "NEW":
        row = f"| `{local}` | `-` | `-` | `-` | `{local_hash}` | NEW |"
    else:
        upstream, _, rel = source.partition(":")
        root = roots.get(upstream.upper())
        if root is None:
            raise ValueError(f"no --upstream given for {upstream}")
        source_hash = sha256(root / rel)
        if source_hash is None:
            raise ValueError(f"{upstream}:{rel} does not exist under {root}")
        if mode == "VERBATIM" and source_hash != local_hash:
            raise ValueError(f"{local} is not byte-identical to {upstream}:{rel}; it cannot be VERBATIM")
        row = (f"| `{local}` | `{upstream.upper()}:{rel}` | `{git_sha(root, rel)}` | "
               f"`{source_hash}` | `{local_hash}` | {mode} |")
    text = MANIFEST.read_bytes().decode("utf-8")
    if f"| `{local}` |" in text:
        raise ValueError(f"{local} already has a row")
    if TABLE_END not in text:
        raise ValueError(f"{MANIFEST} has no '{TABLE_END.strip()}' marker to append before")
    MANIFEST.write_bytes(text.replace(TABLE_END, "\n" + row + TABLE_END, 1).encode("utf-8"))
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--upstream", action="append", default=[],
                        help="NAME=PATH (repeatable), or a bare PATH meaning PIPER")
    parser.add_argument("--rehash", action="store_true",
                        help="refresh local sha256 of PORT and NEW rows, never VERBATIM")
    parser.add_argument("--add", nargs=3, metavar=("LOCAL", "SOURCE", "MODE"),
                        help="record a row: LOCAL path, UPSTREAM:source (or -), VERBATIM|PORT|NEW")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.add:
        try:
            print(add_row(*args.add, parse_upstreams(args.upstream)))
            return 0
        except (OSError, ValueError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    try:
        text, entries = load_manifest()
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        print("Without the manifest this check has verified nothing.", file=sys.stderr)
        return 2

    if args.rehash:
        new_text, changed, refused = rehash(text, entries)
        if changed:
            MANIFEST.write_bytes(new_text.encode("utf-8"))
        for local in changed:
            print(f"  rehashed {local}")
        for local in refused:
            print(f"  REFUSED  {local}: VERBATIM and edited in place. Revert it, or fix "
                  f"upstream and re-vendor.", file=sys.stderr)
        print(f"rehash: {len(changed)} row(s) updated, {len(refused)} refused")
        return 1 if refused else 0

    roots = parse_upstreams(args.upstream)
    failures: list[str] = []
    drift: list[str] = []
    counted = {"VERBATIM": 0, "PORT": 0, "NEW": 0}

    for entry in entries:
        counted[entry.mode] += 1
        actual = sha256(REPO_ROOT / entry.local)
        if actual is None:
            failures.append(f"{entry.local}: recorded in the manifest but not on disk")
            continue
        if entry.mode == "VERBATIM" and actual != entry.local_hash:
            failures.append(f"{entry.local}: VERBATIM copy edited in place "
                            f"(recorded {entry.local_hash[:16]}, on disk {actual[:16]})")
        elif entry.mode in ("PORT", "NEW") and actual != entry.local_hash:
            drift.append(f"{entry.local}: changed since the manifest was written. "
                         f"Run `python scripts/check_vendored.py --rehash`.")

        if entry.mode == "NEW" or entry.upstream.upper() not in roots:
            continue
        source_actual = sha256(roots[entry.upstream.upper()] / entry.source)
        if source_actual is None:
            drift.append(f"{entry.upstream}:{entry.source}: not present upstream. Moved or renamed?")
            continue
        if source_actual != entry.source_hash:
            drift.append(f"{entry.upstream}:{entry.source}: the SOURCE has moved since it was "
                         f"vendored (recorded {entry.source_hash[:16]}, now {source_actual[:16]}). "
                         f"Review the change and decide whether this repo wants it.")
        elif entry.mode == "VERBATIM" and actual != source_actual:
            failures.append(f"{entry.local}: VERBATIM but differs from the current source.")

    if failures:
        print(f"FAIL -- {len(failures)} vendored file(s) are wrong:\n")
        for line in failures:
            print(f"  {line}")
    if drift:
        print(("\n" if failures else "") + f"DRIFT -- {len(drift)} file(s) to review:\n")
        for line in drift:
            print(f"  {line}")
    if failures or drift:
        return 1
    if not args.quiet:
        scope = ", ".join(f"{k}={v}" for k, v in roots.items()) or "local integrity only"
        print(f"OK -- {sum(counted.values())} manifest rows ({counted['VERBATIM']} VERBATIM, "
              f"{counted['PORT']} PORT, {counted['NEW']} NEW), checked against {scope}, no drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
