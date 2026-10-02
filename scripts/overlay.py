"""Taylor's overlay: what he decides and what the system learns on his laptop, kept outside git.

NEW in this repo. From Phase 2 on, Mike builds on Taylor's laptop and Taylor updates with
`git pull`. Anything Taylor decides that lived in a tracked file (a phase approval in
context/architecture/phases.json, a rule edited into CLAUDE.md) would then be a local change
to a file Mike also changes upstream, and every pull would conflict with Taylor's own
decision, or silently undo it. So tracked files hold upstream defaults only, and everything
that is Taylor's lives here, untracked like the rest of state/:

  state/taylor/phases.json      his phase decisions: approved, deferred
  state/taylor/deviations.json  his deviation decisions: status
  state/taylor/CHANGE-LOG.md    his Architecture Change Log (blueprint s.13)
  state/taylor/rules.md         his own rule changes, loaded at the start of every session
  state/taylor/blueprint.md     his living copy of the blueprint; the tracked one is the v1
                                baseline, which upstream never edits
  state/taylor/identity.json    his overrides: system_name, timezone, and this machine's
                                repo_root
  state/taylor/lessons.json     what the system has learned (scripts/lessons.py, REED only)
  state/taylor/proposals.md     proposals written for Taylor on this machine (docs/DEVIATIONS.md is
                                Mike's upstream list); writing one changes nothing, so it needs no
                                phrase

Every file declares `ea-class: private` (context/data-classes.json), so the orchestrator can
edit one with the Write or Edit tool once Taylor's phrase allows it.

The first six change only when his own latest message says `architecture change ok`
(protect-architecture.py, layer A, exactly as the tracked files were guarded). In fixture
mode (EA_FIXTURE_MODE=1) the overlay is state/taylor-fixtures/, so a fixture run never reads
or writes his real decisions; EA_OVERLAY points it anywhere (tests).

THE MERGE. A decision present in the overlay wins; otherwise the tracked default stands. Only
decisions are overlaid (a phase's approved and deferred, a deviation's status, three identity
fields): descriptions, lanes and new entries keep arriving from upstream.

UPSTREAM DECIDES NOTHING FOR TAYLOR. The shipped defaults approve Phase 1 and nothing else,
defer Phase 6, and leave every deviation proposed or undecided. Anything beyond that in a
tracked file is a LEGACY decision, from before the overlay existed: it is honoured (the
tracked value stands when the overlay holds no decision for that key), reported by the doctor,
and moved here once by `python scripts/overlay.py migrate`. The guardrail self-test fails if
the shipped files decide anything, so a legacy decision can only come from Taylor's machine.

Usage:
    python scripts/overlay.py status          where every decision comes from
    python scripts/overlay.py init            seed the overlay (idempotent; run after each pull)
    python scripts/overlay.py migrate [--restore]
                                              copy legacy tracked decisions here, then with
                                              --restore put the tracked files back to upstream
    python scripts/overlay.py name <Name>     Taylor's name for the system, pull-safe
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("EA_ROOT") or Path(__file__).resolve().parents[1])

PHASES = tuple(str(n) for n in range(1, 8))
PHASE_DECISIONS = ("approved", "deferred")
DEVIATION_STATUSES = ("approved", "rejected", "proposed", "undecided")
IDENTITY_OVERRIDES = ("system_name", "timezone", "repo_root")
# What upstream ships, and so what is NOT a decision of Taylor's.
BASELINE_APPROVED = frozenset({"1"})
BASELINE_DEFERRED = frozenset({"6"})
BASELINE_STATUSES = frozenset({"proposed", "undecided"})

FRONT_DOOR = Path(".claude") / "skills" / "taylor-front-door" / "SKILL.md"
NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]{1,19}")


class OverlayUnreadable(Exception):
    """An overlay or tracked decision file is malformed. Never read as "no decision"."""


# --------------------------------------------------------------------------
# where things are
# --------------------------------------------------------------------------

def overlay_dir(base: Path | str | None = None) -> Path:
    """state/taylor/, state/taylor-fixtures/ in fixture mode, or EA_OVERLAY."""
    if os.environ.get("EA_OVERLAY"):
        return Path(os.environ["EA_OVERLAY"])
    root = Path(base) if base else REPO_ROOT
    return root / "state" / ("taylor-fixtures" if os.environ.get("EA_FIXTURE_MODE") == "1" else "taylor")


def path(name: str, base: Path | str | None = None) -> Path:
    """One overlay file: phases.json, deviations.json, CHANGE-LOG.md, rules.md, blueprint.md, identity.json, lessons.json."""
    return overlay_dir(base) / name


def tracked(name: str, base: Path | str | None = None) -> Path:
    root = Path(base) if base else REPO_ROOT
    return root / "context" / ("architecture" if name in ("phases.json", "deviations.json", "CHANGE-LOG.md",
                                                          "blueprint.md") else "") / name


def blueprint_path(base: Path | str | None = None) -> Path:
    """Taylor's living copy when it has been seeded, else the v1 baseline."""
    living = path("blueprint.md", base)
    return living if living.exists() else tracked("blueprint.md", base)


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def _read_json(file: Path, *, required: bool) -> dict | None:
    try:
        raw = file.read_bytes()
    except FileNotFoundError:
        if required:
            raise OverlayUnreadable(f"{file} is missing") from None
        return None
    except OSError as exc:
        raise OverlayUnreadable(f"{file}: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise OverlayUnreadable(f"{file}: {exc.__class__.__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise OverlayUnreadable(f"{file}: top level is not an object")
    return data


def _section(data: dict | None, key: str, file: Path) -> dict:
    if data is None:
        return {}
    section = data.get(key, {})
    if not isinstance(section, dict):
        raise OverlayUnreadable(f"{file}: `{key}` is not an object")
    return section


def phases(base: Path | str | None = None) -> dict:
    """The phase gate in effect: the tracked defaults with Taylor's decisions laid over them."""
    defaults = _read_json(tracked("phases.json", base), required=True)
    mine_file = path("phases.json", base)
    mine = _section(_read_json(mine_file, required=False), "phases", mine_file)
    merged = copy.deepcopy(defaults)
    table = merged.get("phases")
    if not isinstance(table, dict):
        raise OverlayUnreadable(f"{tracked('phases.json', base)}: no `phases` object")
    for key, decision in mine.items():
        if key not in PHASES or not isinstance(decision, dict) or not isinstance(table.get(key), dict):
            raise OverlayUnreadable(f"{mine_file}: phase {key!r} is not one of the blueprint's phases 1 to 7")
        for field in PHASE_DECISIONS:
            if field in decision:
                if not isinstance(decision[field], bool):
                    raise OverlayUnreadable(f"{mine_file}: phase {key} has {field} {decision[field]!r}; "
                                            f"it must be true or false")
                table[key][field] = decision[field]
        table[key]["decided_by_taylor"] = {k: v for k, v in decision.items() if k not in PHASE_DECISIONS}
    return merged


def deviations(base: Path | str | None = None) -> dict:
    """The deviation register in effect. A decision about a deviation upstream no longer
    defines is kept out of the merge and reported by `status` and the doctor, not guessed at."""
    defaults = _read_json(tracked("deviations.json", base), required=True)
    mine_file = path("deviations.json", base)
    mine = _section(_read_json(mine_file, required=False), "deviations", mine_file)
    merged = copy.deepcopy(defaults)
    table = merged.get("deviations")
    if not isinstance(table, dict):
        raise OverlayUnreadable(f"{tracked('deviations.json', base)}: no `deviations` object")
    for key, decision in mine.items():
        if not isinstance(decision, dict):
            raise OverlayUnreadable(f"{mine_file}: {key} is not an object")
        status = decision.get("status")
        if status not in DEVIATION_STATUSES:
            raise OverlayUnreadable(f"{mine_file}: {key} has status {status!r}; it must be one of "
                                    f"{', '.join(DEVIATION_STATUSES)}")
        if not isinstance(table.get(key), dict):
            continue  # upstream no longer defines it: reported by orphaned_decisions()
        table[key]["status"] = status
        table[key]["decided_by_taylor"] = {k: v for k, v in decision.items() if k != "status"}
    return merged


def identity(base: Path | str | None = None) -> dict:
    """context/identity.json with Taylor's three overrides laid over it."""
    merged = _read_json(tracked("identity.json", base), required=True)
    mine_file = path("identity.json", base)
    mine = _read_json(mine_file, required=False) or {}
    for field in IDENTITY_OVERRIDES:
        value = mine.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise OverlayUnreadable(f"{mine_file}: {field} must be a non-empty string")
        merged[field] = value.strip()
        merged[f"{field}_status"] = "set on this machine (state/taylor/identity.json)"
    return merged


def orphaned_decisions(base: Path | str | None = None) -> list[str]:
    """Taylor's deviation decisions about deviations upstream no longer defines."""
    mine_file = path("deviations.json", base)
    mine = _section(_read_json(mine_file, required=False), "deviations", mine_file)
    known = _section(_read_json(tracked("deviations.json", base), required=True), "deviations",
                     tracked("deviations.json", base))
    return sorted(key for key in mine if key not in known)


def legacy_decisions(base: Path | str | None = None) -> list[tuple[str, str, object]]:
    """(file, key, value) for every decision a TRACKED file makes beyond the shipped baseline."""
    found: list[tuple[str, str, object]] = []
    phase_table = _section(_read_json(tracked("phases.json", base), required=True), "phases",
                           tracked("phases.json", base))
    for key, entry in phase_table.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("approved") is True and key not in BASELINE_APPROVED:
            found.append(("phases.json", key, {"approved": True}))
        if isinstance(entry.get("deferred"), bool) and entry["deferred"] != (key in BASELINE_DEFERRED):
            found.append(("phases.json", key, {"deferred": entry["deferred"]}))
    deviation_table = _section(_read_json(tracked("deviations.json", base), required=True), "deviations",
                               tracked("deviations.json", base))
    for key, entry in deviation_table.items():
        if isinstance(entry, dict) and entry.get("status") not in BASELINE_STATUSES:
            found.append(("deviations.json", key, {"status": entry.get("status")}))
    for line in _change_log_entries(tracked("CHANGE-LOG.md", base)):
        found.append(("CHANGE-LOG.md", line, None))
    return found


def _change_log_entries(file: Path) -> list[str]:
    try:
        text = file.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if re.match(r"- \[?\d{4}-\d{2}-\d{2}", line.strip())]


# --------------------------------------------------------------------------
# writing: seeding, migration, naming (scripts run from a terminal, never by a session)
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(file: Path, text: str) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(file.name + ".tmp")
    temp.write_bytes(text.encode("utf-8"))
    os.replace(temp, file)


def _write_json(file: Path, data: dict) -> None:
    _write(file, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


DECLARATION = "<!-- ea-class: private -->\n"

ABOUT = {
    "phases.json": [
        "Taylor's own phase decisions. A key here wins over context/architecture/phases.json, which holds",
        "upstream defaults only. Changed only when his own message says `architecture change ok` (switch on",
        "Phase <n>: approved true; resume Phase 6: approved true and deferred false), with one bullet in",
        "state/taylor/CHANGE-LOG.md in the same turn. Untracked: `git pull` never touches it.",
    ],
    "deviations.json": [
        "Taylor's own deviation decisions (`status`: approved or rejected). A key here wins over",
        "context/architecture/deviations.json, which holds upstream defaults only. Same rule as phases.json.",
    ],
    "identity.json": [
        "Overrides of context/identity.json for this machine: system_name (Taylor's name for the system,",
        "set by `python scripts/overlay.py name <Name>`), timezone, and repo_root. Nothing else is read here.",
    ],
}

RULES_SEED = """<!-- ea-class: private -->
# Taylor's rules

His own changes to how this system works. One bullet each, added only when his own latest message
says `architecture change ok`, with the matching bullet in CHANGE-LOG.md in the same turn. Loaded at
the start of every session; where a rule here conflicts with CLAUDE.md, this one wins.

Format: `- [YYYY-MM-DD] | [the rule, in his words]`

No rules yet.
"""

LESSONS_SEED = {"ea-class": "private", "version": 1, "next": 1, "lessons": []}

PROPOSALS_SEED = """<!-- ea-class: private -->
# Proposals for Taylor

What the system proposes on this machine instead of changing it: a change to a rule, a phase or a
deviation that Taylor has not approved, or anything that needs code. One section each: the change,
why it helps, what it affects, and what Taylor would say to approve it. Writing here changes
nothing. Mike reads this file when he builds on this machine; docs/DEVIATIONS.md is his list.

No proposals yet.
"""


def init(base: Path | str | None = None) -> list[str]:
    """Seed every missing overlay file. Never overwrites one that exists. Returns what was created."""
    created: list[str] = []
    root = Path(base) if base else REPO_ROOT
    for name in ("phases.json", "deviations.json"):
        file = path(name, base)
        if not file.exists():
            _write_json(file, {"ea-class": "private", "about": ABOUT[name], name.split(".")[0]: {}})
            created.append(name)
    file = path("identity.json", base)
    if not file.exists():
        seeded: dict = {"ea-class": "private", "about": ABOUT["identity.json"]}
        upstream = _read_json(tracked("identity.json", base), required=True)
        here = str(root.resolve())
        if os.path.normcase(str(Path(upstream.get("repo_root") or "").resolve())) != os.path.normcase(here):
            seeded["repo_root"] = here  # a fact about this machine, not a decision
        _write_json(file, seeded)
        created.append("identity.json")
    file = path("CHANGE-LOG.md", base)
    if not file.exists():
        template = tracked("CHANGE-LOG.md", base).read_bytes().decode("utf-8", errors="replace")
        _write(file, DECLARATION + template.split("No entries yet.")[0].rstrip() + "\n\nNo entries yet.\n")
        created.append("CHANGE-LOG.md")
    file = path("rules.md", base)
    if not file.exists():
        _write(file, RULES_SEED)
        created.append("rules.md")
    file = path("blueprint.md", base)
    if not file.exists():
        baseline = tracked("blueprint.md", base).read_bytes().decode("utf-8")
        _write(file, DECLARATION + f"<!-- Taylor's living copy, seeded {_now()[:10]} from the v1 baseline "
                     f"context/architecture/blueprint.md. Changes here need his own `architecture change ok`. -->\n"
                     + baseline)
        created.append("blueprint.md")
    file = path("lessons.json", base)
    if not file.exists():
        _write_json(file, dict(LESSONS_SEED))
        created.append("lessons.json")
    file = path("proposals.md", base)
    if not file.exists():
        _write(file, PROPOSALS_SEED)
        created.append("proposals.md")
    name = (identity(base).get("system_name") or "").strip()
    if name and name != "NAME" and front_door(base, name):
        created.append(f"{FRONT_DOOR.as_posix()} (/{name.lower()})")
    return created


def migrate(base: Path | str | None = None, restore: bool = False) -> list[str]:
    """Copy every legacy tracked decision into the overlay, once. With restore, then put the
    tracked files back to the committed upstream version so the next `git pull` is clean."""
    init(base)
    moved: list[str] = []
    # Keys Taylor already decided in the overlay stand; a tracked value never overwrites one.
    # (One key can carry two legacy decisions, Phase 6 approved AND no longer deferred, so
    # what was decided before this run is what counts, not what this run has added.)
    decided = {name: set(_section(_read_json(path(name, base), required=False), name.split(".")[0],
                                  path(name, base)))
               for name in ("phases.json", "deviations.json")}
    for name, key, value in legacy_decisions(base):
        if name == "CHANGE-LOG.md":
            file = path("CHANGE-LOG.md", base)
            text = file.read_bytes().decode("utf-8", errors="replace")
            if key not in text:
                _write(file, text.replace("No entries yet.\n", "").rstrip() + "\n" + key + "\n")
                moved.append(f"CHANGE-LOG.md: {key}")
            continue
        if key in decided[name]:
            continue
        file = path(name, base)
        data = _read_json(file, required=False) or {"ea-class": "private", "about": ABOUT[name],
                                                    name.split(".")[0]: {}}
        entry = data.setdefault(name.split(".")[0], {}).setdefault(
            key, {"migrated_from": f"context/architecture/{name}", "migrated_at": _now()})
        entry.update(value)
        _write_json(file, data)
        moved.append(f"{name}: {key} {value}")
    if restore:
        root = Path(base) if base else REPO_ROOT
        files = sorted({f"context/architecture/{name}" for name, _, _ in legacy_decisions(base)})
        if files:
            subprocess.run(["git", "checkout", "--", *files], cwd=str(root), check=True)
            moved.append("restored to upstream: " + ", ".join(files))
    return moved


def front_door(base: Path | str | None, name: str) -> bool:
    """Write Taylor's front door, /<name>, as a gitignored skill generated from .claude/commands/NAME.md.

    The command file keeps its placeholder name so it can keep changing upstream; this copy
    is regenerated by every `init`, so it follows. Returns True when it wrote the file.
    """
    root = Path(base) if base else REPO_ROOT
    source = (root / ".claude" / "commands" / "NAME.md").read_bytes().decode("utf-8")
    body = source.split("---", 2)[2] if source.startswith("---") else source
    description = re.search(r'^description:\s*"(.*)"\s*$', source, re.M)
    text = ("---\n"
            f"name: {name.lower()}\n"
            f"description: \"{name}: {description.group(1) if description else 'the front door'}\"\n"
            "argument-hint: <what you need, in your own words>\n"
            "---\n"
            f"<!-- Generated by scripts/overlay.py from .claude/commands/NAME.md for the name {name}. "
            f"Gitignored; regenerated by every `python scripts/overlay.py init`. Do not edit. -->\n"
            + re.sub(r"\bNAME\b", name, body))
    target = root / FRONT_DOOR
    if target.exists() and target.read_bytes().decode("utf-8", errors="replace") == text:
        return False
    _write(target, text)
    return True


def name(base: Path | str | None, display: str) -> str:
    """Record Taylor's name for the system in the overlay and write /<name>. Nothing tracked changes."""
    if not NAME_PATTERN.fullmatch(display):
        raise OverlayUnreadable(f"{display!r} is not a usable name: letters and digits, 2 to 20, starting with a letter")
    init(base)
    file = path("identity.json", base)
    data = _read_json(file, required=False) or {"ea-class": "private", "about": ABOUT["identity.json"]}
    data["system_name"] = display
    _write_json(file, data)
    front_door(base, display)
    return f"/{display.lower()}"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def status_lines(base: Path | str | None = None) -> list[str]:
    lines = [f"overlay: {overlay_dir(base)}" + ("" if overlay_dir(base).exists() else " (not seeded: run init)")]
    for name in ("phases.json", "deviations.json", "identity.json", "CHANGE-LOG.md", "rules.md", "blueprint.md",
                 "lessons.json", "proposals.md"):
        lines.append(f"  {name:<16} {'present' if path(name, base).exists() else 'missing'}")
    for key, entry in sorted(phases(base)["phases"].items()):
        mark = "Taylor" if "decided_by_taylor" in entry else "default"
        lines.append(f"  phase {key}: approved={entry.get('approved')} deferred={entry.get('deferred', False)} ({mark})")
    for key, entry in sorted(deviations(base)["deviations"].items()):
        if isinstance(entry, dict):
            mark = "Taylor" if "decided_by_taylor" in entry else "default"
            lines.append(f"  {key}: {entry.get('status')} ({mark})")
    for key in orphaned_decisions(base):
        lines.append(f"  {key}: Taylor decided it, but upstream no longer defines it (kept, not applied)")
    for name_, key, value in legacy_decisions(base):
        lines.append(f"  LEGACY in context/architecture/{name_}: {key} {value or ''} (run: overlay.py migrate)")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("init")
    m = sub.add_parser("migrate")
    m.add_argument("--restore", action="store_true", help="then git checkout the tracked files that held them")
    n = sub.add_parser("name")
    n.add_argument("display_name")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # swallow: a stream that cannot be reconfigured needs no fix
    try:
        if args.cmd == "status":
            print("\n".join(status_lines()))
        elif args.cmd == "init":
            created = init()
            print("seeded: " + ", ".join(created) if created else "the overlay is complete; nothing to seed")
        elif args.cmd == "migrate":
            moved = migrate(restore=args.restore)
            print("\n".join(moved) if moved else "no legacy decisions in the tracked files")
        else:
            print(f"named: {args.display_name}; Taylor's front door is {name(None, args.display_name)} "
                  f"(reload the VS Code window to see it)")
    except (OverlayUnreadable, subprocess.CalledProcessError, OSError) as exc:
        print(f"OVERLAY ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
