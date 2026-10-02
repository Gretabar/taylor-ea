"""SessionStart: load what is Taylor's into every session. His name, build mode, his rules, his lessons.

NEW in this repo. CLAUDE.md is an upstream default that every `git pull` replaces, so it
cannot carry Taylor's own changes (scripts/overlay.py). This hook carries them instead.
Claude Code adds a SessionStart hook's plain stdout to the session's context, at every
startup, resume, /clear and compaction, capped at 10,000 characters (hooks reference):

  1. His name for the system, once he has named it (`overlay.py name`).
  2. BUILD MODE, while it is on.
  3. His own rules, state/taylor/rules.md. Where one conflicts with CLAUDE.md, his wins.
  4. Where his living blueprint is: state/taylor/blueprint.md, not the v1 baseline.
  5. What the system has learned (scripts/lessons.py context): the lessons in effect, capped,
     and the rule-candidates only as a count, so nothing he has not adopted is applied.

Kept under 9,000 characters, and what does not fit is named, never dropped silently. In
fixture mode the overlay is state/taylor-fixtures/, so a fixture session never loads his
real rules.

NEVER BLOCKS (SessionStart cannot), and never fails silent: a part that cannot be read
prints one line saying so, and the rest still loads.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

BUDGET = 9000
RULES_BUDGET = 3500
SEED_MARK = "No rules yet."


def _root() -> Path:
    env = os.environ.get("EA_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else HERE.parents[1]


def sections() -> list[str]:
    """Each part of what this session loads, in order. Empty parts are left out."""
    root = _root()
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    out: list[str] = []
    try:
        import overlay  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [f"TAYLOR'S OVERLAY COULD NOT BE LOADED ({exc.__class__.__name__}: {exc}). His own rules and "
                f"lessons are NOT in this session. Run python scripts/ea_doctor.py and tell Mike."]

    try:
        name = (overlay.identity(root).get("system_name") or "").strip()
        if name and name != "NAME":
            out.append(f"This system's name is {name}: Taylor named it. Where the files say NAME, it means "
                       f"{name}. His front door is /{name.lower()}.")
    except Exception as exc:  # noqa: BLE001
        out.append(f"Taylor's identity overrides could not be read ({exc}); the defaults apply.")  # swallow: said

    try:
        import _health  # noqa: PLC0415

        build = _health.build_mode_text(_health.build_mode())
        if build:
            out.append(f"{build}. Mike is building on this machine: code may change and dev agents may be "
                       f"dispatched. Taylor's switched-off agents stay off, and nothing is pushed from here.")
    except Exception as exc:  # noqa: BLE001
        out.append(f"Build mode could not be read ({exc.__class__.__name__}); treat it as off.")  # swallow: said

    if not overlay.overlay_dir(root).exists():
        out.append("Taylor's overlay (state/taylor/) is not seeded on this machine: run "
                   "python scripts/overlay.py init. His own rules and lessons load once it is.")
        return out

    rules_file = overlay.path("rules.md", root)
    try:
        rules = rules_file.read_bytes().decode("utf-8", errors="replace").strip()
        if rules and SEED_MARK not in rules:
            if len(rules) > RULES_BUDGET:
                rules = rules[:RULES_BUDGET].rsplit("\n", 1)[0] + (
                    f"\n[... more in {rules_file}: read it before acting on a rule question]")
            out.append("TAYLOR'S OWN RULES (state/taylor/rules.md). They are his; where one conflicts with "
                       "CLAUDE.md, his wins.\n" + rules)
    except FileNotFoundError:
        pass  # swallow: no rules file is the same as no rules of his own
    except OSError as exc:
        out.append(f"TAYLOR'S OWN RULES COULD NOT BE READ ({exc}). Tell Mike before changing anything.")

    if overlay.path("blueprint.md", root).exists():
        out.append("Read a blueprint section from Taylor's living copy, state/taylor/blueprint.md. "
                   "context/architecture/blueprint.md is the v1 baseline it was seeded from.")

    try:
        import lessons  # noqa: PLC0415

        learned = lessons.context()
        if learned:
            out.append(learned)
    except Exception as exc:  # noqa: BLE001
        out.append(f"WHAT THE SYSTEM HAS LEARNED COULD NOT BE LOADED ({exc}). Tell Mike.")  # swallow: said
    return out


def render() -> str:
    text = "\n\n".join(sections())
    if len(text) > BUDGET:
        text = text[:BUDGET - 160].rsplit("\n", 1)[0] + (
            "\n[... cut to fit the session's limit; state/taylor/rules.md and "
            "`python scripts/lessons.py list` have the rest]")
    return text


def main() -> int:
    try:
        sys.stdin.buffer.read()  # the payload says why the session started; the content is the same for each
    except Exception:  # noqa: BLE001
        pass  # swallow: nothing in it changes what is loaded
    try:
        text = render()
    except Exception as exc:  # noqa: BLE001
        text = f"TAYLOR'S SESSION CONTEXT FAILED TO LOAD ({exc.__class__.__name__}: {exc}). Tell Mike."  # swallow: said
    if text:
        try:
            sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            return 0  # swallow: a closed stdout is not worth a failed session start
    return 0


if __name__ == "__main__":
    sys.exit(main())
