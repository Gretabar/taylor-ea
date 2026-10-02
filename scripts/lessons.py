"""What the system has learned from Taylor, and the screen that keeps a rule from being learned by accident.

NEW in this repo. Blueprint s.1, "Learning and corrections": the assistant may learn
preferences (shorter emails, answer first, no dashes) and adapt presentation and operating
patterns within the approved architecture. It must not learn a new price, package, policy,
sending permission or fundamental rule from an isolated instance; when repeated signals
suggest a real rule change it may ask Taylor once whether to adopt it, and never once per
nuance. Test G2 is exactly that: style adapts, a price is not silently adopted.

KINDS

  preference      how Taylor likes things presented or done      active from the next session
  routing         where something goes, which section or lane     active from the next session
  identity        who someone is ("Kade" is Kaed): recorded as a  active now, in the register
                  register alias, exactly as `register.py alias`
                  does, and listed here
  rule-candidate  anything that would set a price, package,       NEVER active from one instance
                  minimum spend, discount, policy, sending
                  permission or fundamental rule

THE SCREEN DECIDES, NOT THE CALLER. Every lesson is screened (RULE_PATTERNS). One the screen
marks is a rule-candidate whatever kind was asked for, and nothing downgrades it. REED may mark
a rule-candidate the screen missed; when the orchestrator is unsure, SAGE gives a G2 judgement
first.

ASKED ONCE. A rule-candidate raises exactly one Needs Your Input question per subject, ever:
on the first instance when Taylor said it himself ("the corporate package is $45 now": his own
words are the signal, and a targeted question settles one-off or rule), on the second when it
was only inferred from his edits (one edited draft is not a rule). Repeats are counted and ask
nothing more. It becomes active only when Taylor answers yes (`answer L-0004 --yes`); no keeps
it out for good.

STORE: the overlay's lessons.json (scripts/overlay.py: state/taylor/, or state/taylor-fixtures/
in fixture mode), untracked, written atomically and only here. WHO WRITES: REED only
(.claude/hooks/require-lessons-agent.py). `list` and `context` are reads anyone may run. The
SessionStart hook loads `context`, capped, into every session.

Usage:
    python scripts/lessons.py record --kind preference --text "Answer first, then the detail" --said "<his words>"
    python scripts/lessons.py record --kind identity --person kaed --alias "Kade" --said "<his words>"
    python scripts/lessons.py record --kind rule-candidate --about "corporate package price" --text "..." --said "..."
                                    [--source said|edit]
    python scripts/lessons.py answer L-0004 --yes | --no
    python scripts/lessons.py forget L-0002       (or a few words that match exactly one lesson)
    python scripts/lessons.py list [--all] [--json]   "show me what you've learned"
    python scripts/lessons.py context                 what a new session loads

Exit 0 done; 1 refused, with the reason; 2 usage or an unreadable store.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ea_db  # noqa: E402
import overlay  # noqa: E402
import validate_content_rules  # noqa: E402

KINDS = ("preference", "routing", "identity", "rule-candidate")
ACTIVE = frozenset({"active", "adopted"})
STATUS_WORDS = {"active": "in effect", "adopted": "in effect (Taylor said yes)", "candidate": "noted, not in effect",
                "asked": "not in effect: Taylor has been asked", "declined": "not in effect: Taylor said no",
                "retired": "forgotten"}
CONTEXT_LIMIT = 4000
CONTEXT_LESSONS = 40


class LessonRefused(Exception):
    """Nothing was recorded, for the reason given."""


# --------------------------------------------------------------------------
# the screen: what would be a rule, not a preference
# --------------------------------------------------------------------------

def _words(*alternatives: str) -> re.Pattern[str]:
    return re.compile(r"(?:" + "|".join(alternatives) + r")", re.I)


RULE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sending permission", _words(
        r"\bsend\w*\b[^.;]{0,60}\b(?:without|automatically|on\s+your\s+own|straight\s+(?:to|out))\b",
        r"\bauto-?send\w*",
        r"\b(?:no\s+need|don'?t\s+need|do\s+not\s+need)\s+(?:to\s+)?(?:ask|check|run\s+it\s+by|my\s+(?:ok|okay|approval|review))\b",
        r"\bwithout\s+(?:asking|checking\s+with)\s+me\b",
        r"\bpermission\s+to\s+send\b", r"\bgo\s+ahead\s+and\s+send\b",
    )),
    ("price", _words(
        r"\$\s?\d", r"\b\d+(?:[.,]\d+)?\s?(?:dollars|bucks|cad|usd)\b", r"\bpric(?:e|es|ed|ing)\b",
        r"\bcosts?\b", r"\bper\s+(?:person|head|guest|pax|seat)\b", r"\bfees?\b",
        r"\brates?\s+(?:is|are|for|of|at|goes|went)\b",
    )),
    ("package", _words(r"\bpackages?\b")),
    ("minimum spend", _words(r"\bmin(?:imum)?\.?\s+spend\b", r"\bminimums?\b")),
    ("discount", _words(
        r"\bdiscount\w*", r"\b\d+\s?(?:%|percent)\s+off\b", r"\bcomp(?:s|ed|ing)?\b", r"\bwaiv(?:e|es|ed|ing)\b",
        r"\bfree\s+of\s+charge\b", r"\bno\s+charge\b",
    )),
    ("policy", _words(r"\bpolic(?:y|ies)\b", r"\bdeposits?\b", r"\bcancell?ations?\b", r"\brefunds?\b")),
    ("fundamental rule", _words(
        r"\brules?\b", r"\balways\s+(?:charge|offer|give|waive|comp|approve|book|accept)\b",
        r"\bnever\s+(?:charge|offer|give|waive|comp|approve|accept)\b",
    )),
)


def screen(text: str) -> tuple[str, str] | None:
    """(category, the words that matched) when `text` would set a rule, else None."""
    import privacy_screen  # noqa: PLC0415  -- the same normalisation the privacy screen uses

    seen = privacy_screen.readable(text or "")
    for category, pattern in RULE_PATTERNS:
        found = pattern.search(seen)
        if found:
            return category, found.group(0)
    return None


_STOP = frozenset("""a an and are as at be been but by for from has have he her his i if in into is it its me my
now of on or our please she so that the their them then there they this to us was we were will with you your
dollar dollars bucks cad usd percent""".split())


def subject_words(about: str | None, text: str) -> list[str]:
    """The content words of a rule-candidate's subject: its --about when REED gave one, else its text."""
    source = about if about and about.strip() else text
    return sorted({w for w in re.findall(r"[a-z]+", (source or "").lower()) if w not in _STOP and len(w) > 2})


def same_subject(lesson: dict, category: str, words: list[str]) -> bool:
    """A repeat: the same category and more than half the subject words shared (Jaccard), so a
    rewording is not a new question and two rooms' minimum spends are not one subject."""
    if lesson.get("category") != category or not words or not lesson.get("words"):
        return False
    mine, theirs = set(words), set(lesson["words"])
    return len(mine & theirs) / len(mine | theirs) > 0.5


# --------------------------------------------------------------------------
# the store
# --------------------------------------------------------------------------

def store_path() -> Path:
    return overlay.path("lessons.json")


def load() -> dict:
    """The store, or an empty one when it has not been written yet. Malformed is an error, never empty."""
    file = store_path()
    try:
        raw = file.read_bytes()
    except FileNotFoundError:
        return {"ea-class": "private", "version": 1, "next": 1, "lessons": []}
    except OSError as exc:
        raise LessonRefused(f"the lessons store {file} cannot be read: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise LessonRefused(f"the lessons store {file} is not readable JSON ({exc.__class__.__name__}); "
                            f"nothing was changed. Tell Mike.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("lessons"), list) or not isinstance(data.get("next"), int):
        raise LessonRefused(f"the lessons store {file} is not in the expected shape; nothing was changed. Tell Mike.")
    return data


def save(data: dict) -> None:
    file = store_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(file.name + ".tmp")
    temp.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    os.replace(temp, file)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new(data: dict, **fields) -> dict:
    ref = f"L-{data['next']:04d}"
    data["next"] += 1
    lesson = {"ref": ref, "count": 1, "said": [], "question": None, "category": None, "about": None,
              "created_at": _now(), "updated_at": _now(), "history": [], **fields}
    data["lessons"].append(lesson)
    return lesson


def _note(lesson: dict, event: str, detail: str = "") -> None:
    lesson["updated_at"] = _now()
    lesson["history"].append({"ts": lesson["updated_at"], "event": event, **({"detail": detail} if detail else {})})


def _clean_text(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        raise LessonRefused("a lesson needs its text, in words Taylor would recognise")
    findings = validate_content_rules.check_doc_bound(text)
    if findings:
        raise LessonRefused("the lesson's text breaks a content rule (" + ", ".join(f.rule for f in findings)
                            + "); rewrite it plainly")
    return text


# --------------------------------------------------------------------------
# operations
# --------------------------------------------------------------------------

def _ask(conn, lesson: dict) -> str:
    """Raise the one Needs Your Input question for a rule-candidate. Returns its ref."""
    import register  # noqa: PLC0415

    with conn:
        ref = register.next_ref(conn, "question")
        conn.execute("INSERT INTO needs_input (ref, question, context, source_kind, source_ref, asked_at, status)"
                     " VALUES (?,?,?,?,?,?,'open')",
                     (ref, f"Should this be the rule from now on, or was it a one-off: {lesson['text']}? "
                           f"Yes makes it the rule; no keeps it a one-off.",
                      f"{lesson['ref']}: the {lesson['category']} would change a rule (blueprint section 1), so it "
                      f"is not applied until you say yes. Asked once.", "lesson", lesson["ref"], ea_db.now_iso()))
    return ref


def _unask(conn, ref: str) -> None:
    with conn:
        conn.execute("DELETE FROM needs_input WHERE ref = ? AND status = 'open'", (ref,))


def record(conn, *, kind: str, text: str = "", said: str = "", about: str | None = None, source: str = "said",
           person: str | None = None, alias: str | None = None) -> dict:
    """Record one lesson. Returns what happened, for REED to relay."""
    if kind not in KINDS:
        raise LessonRefused(f"the kind must be one of {', '.join(KINDS)}")
    if source not in ("said", "edit"):
        raise LessonRefused("the source is `said` (Taylor's own words) or `edit` (inferred from his edits)")
    data = load()
    if kind == "identity":
        import register  # noqa: PLC0415

        if not person or not alias:
            raise LessonRefused("an identity correction needs --person (the key) and --alias (the name as heard)")
        try:
            result = register.add_alias(conn, person, alias)
        except register.RegisterError as exc:
            raise LessonRefused(str(exc)) from exc
        lesson = _new(data, kind="identity", status="active", source=source, text=f"\"{alias}\" is {result['key']}",
                      said=[said] if said else [])
        _note(lesson, "recorded", "register alias added" if result.get("added") else "register alias already known")
        save(data)
        return {"ref": lesson["ref"], "kind": "identity", "status": "active", "active": True, "question": None,
                "note": f"{alias!r} now resolves to {result['key']} in the register"}

    text = _clean_text(text)
    flagged = screen(f"{text} {said}")
    if flagged or kind == "rule-candidate":
        category = flagged[0] if flagged else "fundamental rule"
        words = subject_words(about, text)
        lesson = next((l for l in data["lessons"] if l["kind"] == "rule-candidate" and l["status"] != "retired"
                       and same_subject(l, category, words)), None)
        if lesson is None:
            lesson = _new(data, kind="rule-candidate", status="candidate", source=source, text=text,
                          about=(about or "").strip() or None, words=words, category=category,
                          said=[said] if said else [])
            _note(lesson, "recorded", f"screened: {category} ({flagged[1]!r})" if flagged else "marked by REED")
        else:
            lesson["count"] += 1
            if said:
                lesson["said"].append(said)
            if source == "said" and lesson.get("source") != "said":
                lesson["source"] = "said"
            _note(lesson, "repeated", f"instance {lesson['count']}")
        threshold = 1 if lesson.get("source") == "said" else 2
        asked = None
        if lesson["status"] == "candidate" and lesson["count"] >= threshold:
            asked = _ask(conn, lesson)
            lesson["status"], lesson["question"] = "asked", asked
            _note(lesson, "asked", asked)
        try:
            save(data)
        except OSError as exc:
            if asked:
                _unask(conn, asked)  # the question and the lesson land together, or neither does
            raise LessonRefused(f"the lessons store could not be written ({exc}); nothing was recorded") from exc
        note = ("asked Taylor once (" + asked + ")") if asked else (
            "already asked; not asked again" if lesson["question"] else "noted; asked only if it comes up again")
        return {"ref": lesson["ref"], "kind": "rule-candidate", "status": lesson["status"], "active": False,
                "category": category, "question": lesson["question"], "count": lesson["count"],
                "note": f"not in effect: {category} would change a rule. {note}",
                "screened": bool(flagged), "asked_for": kind}

    same = next((l for l in data["lessons"] if l["kind"] == kind and l["status"] == "active"
                 and l["text"].lower() == text.lower()), None)
    if same is not None:
        same["count"] += 1
        if said:
            same["said"].append(said)
        _note(same, "repeated", f"instance {same['count']}")
        save(data)
        return {"ref": same["ref"], "kind": kind, "status": "active", "active": True, "question": None,
                "note": "already known; counted again"}
    lesson = _new(data, kind=kind, status="active", source=source, text=text, said=[said] if said else [])
    _note(lesson, "recorded")
    save(data)
    return {"ref": lesson["ref"], "kind": kind, "status": "active", "active": True, "question": None,
            "note": "in effect from the next session"}


def answer(conn, ref: str, yes: bool, actor: str = "taylor") -> dict:
    """Taylor's answer to a rule-candidate: yes adopts it, no keeps it out for good."""
    data = load()
    lesson = next((l for l in data["lessons"] if l["ref"] == ref.upper()), None)
    if lesson is None or lesson["kind"] != "rule-candidate":
        raise LessonRefused(f"{ref} is not a rule-candidate lesson")
    if lesson["status"] not in ("candidate", "asked"):
        raise LessonRefused(f"{ref} is {lesson['status']}; only an open candidate takes an answer")
    lesson["status"] = "adopted" if yes else "declined"
    _note(lesson, "answered", f"{actor}: {'yes' if yes else 'no'}")
    save(data)
    if lesson["question"]:
        with conn:
            conn.execute("UPDATE needs_input SET status = 'resolved', resolved_at = ?, resolution = ? "
                         "WHERE ref = ? AND status = 'open'",
                         (ea_db.now_iso(), f"{actor}: {'yes' if yes else 'no'}", lesson["question"]))
    return {"ref": lesson["ref"], "status": lesson["status"], "active": yes, "question": lesson["question"]}


def forget(target: str, conn=None) -> dict:
    """Retire one lesson, by its ref or by words that match exactly one lesson in force or pending.

    A rule-candidate still waiting for Taylor's answer has an open question; it is withdrawn
    with the lesson, so /morning never asks about something he told the system to forget.
    """
    data = load()
    live = [l for l in data["lessons"] if l["status"] != "retired"]
    wanted = target.strip()
    matches = [l for l in live if l["ref"] == wanted.upper()] or [
        l for l in live if wanted and wanted.lower() in l["text"].lower()]
    if not matches:
        raise LessonRefused(f"nothing learned matches {target!r}; `lessons.py list` shows what there is")
    if len(matches) > 1:
        raise LessonRefused(f"{target!r} matches {len(matches)} lessons ("
                            + ", ".join(f"{l['ref']} {l['text'][:40]!r}" for l in matches)
                            + "); forget one by its ref")
    lesson = matches[0]
    waiting = lesson["question"] if lesson["status"] == "asked" else None
    if waiting and conn is None:
        raise LessonRefused(f"{lesson['ref']} has an open question ({waiting}); forgetting it needs the register")
    lesson["status"] = "retired"
    _note(lesson, "forgotten", target)
    save(data)
    if waiting:
        with conn:
            conn.execute("UPDATE needs_input SET status = 'resolved', resolved_at = ?, resolution = ? "
                         "WHERE ref = ? AND status = 'open'",
                         (ea_db.now_iso(), "withdrawn: Taylor asked to forget the lesson", waiting))
    note = " The register alias stays; REED removes it there if it was wrong." if lesson["kind"] == "identity" else ""
    return {"ref": lesson["ref"], "status": "retired", "text": lesson["text"], "note": f"forgotten.{note}"}


def listing(include_all: bool = False) -> list[dict]:
    lessons = load()["lessons"]
    return [l for l in lessons if include_all or l["status"] != "retired"]


def render_list(lessons: list[dict]) -> str:
    """'Show me what you've learned', in Taylor's terms."""
    if not lessons:
        return "Nothing learned yet."
    groups = (("In effect", lambda l: l["status"] in ACTIVE),
              ("Waiting for your answer, not in effect", lambda l: l["status"] in ("candidate", "asked")),
              ("Kept out (you said no)", lambda l: l["status"] == "declined"),
              ("Forgotten", lambda l: l["status"] == "retired"))
    lines = []
    for title, keep in groups:
        chosen = [l for l in lessons if keep(l)]
        if not chosen:
            continue
        lines.append(title)
        for l in chosen:
            extra = f", question {l['question']}" if l.get("question") and l["status"] == "asked" else ""
            lines.append(f"  {l['ref']}  {l['kind']}: {l['text']}  ({STATUS_WORDS[l['status']]}{extra})")
    return "\n".join(lines)


def context(limit: int = CONTEXT_LIMIT) -> str:
    """What a session loads: the lessons in effect, capped, and only a count of the rest."""
    lessons = load()["lessons"]
    active = [l for l in lessons if l["status"] in ACTIVE and l["kind"] != "identity"]
    waiting = sum(1 for l in lessons if l["status"] in ("candidate", "asked"))
    if not active and not waiting:
        return ""
    lines = ["WHAT TAYLOR HAS TAUGHT THIS SYSTEM (scripts/lessons.py). Apply these; they are his."]
    used, shown = len(lines[0]), 0
    for l in sorted(active, key=lambda l: l["created_at"], reverse=True):
        line = f"- {l['ref']} ({'rule, adopted' if l['status'] == 'adopted' else l['kind']}): {l['text']}"
        if shown >= CONTEXT_LESSONS or used + len(line) + 1 > limit:
            break
        lines.append(line)
        used, shown = used + len(line) + 1, shown + 1
    if shown < len(active):
        lines.append(f"- ... and {len(active) - shown} more in effect (python scripts/lessons.py list)")
    if waiting:
        lines.append(f"NOT in effect, do not apply: {waiting} possible rule(s) waiting for Taylor's answer.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--kind", required=True, choices=KINDS)
    r.add_argument("--text", default="")
    r.add_argument("--said", default="", help="Taylor's words, as he said them")
    r.add_argument("--about", help="for a rule-candidate: its subject in a few words, reused when it comes up again")
    r.add_argument("--source", default="said", choices=("said", "edit"))
    r.add_argument("--person")
    r.add_argument("--alias")
    a = sub.add_parser("answer")
    a.add_argument("ref")
    choice = a.add_mutually_exclusive_group(required=True)
    choice.add_argument("--yes", action="store_true")
    choice.add_argument("--no", action="store_true")
    a.add_argument("--actor", default="taylor")
    f = sub.add_parser("forget")
    f.add_argument("target", nargs="+")
    li = sub.add_parser("list")
    li.add_argument("--all", action="store_true")
    li.add_argument("--json", action="store_true")
    sub.add_parser("context")
    args = parser.parse_args()
    ea_db.console_utf8()
    try:
        if args.cmd == "list":
            lessons = listing(args.all)
            print(json.dumps(lessons, indent=2, ensure_ascii=False) if args.json else render_list(lessons))
            return 0
        if args.cmd == "context":
            print(context())
            return 0
        conn = ea_db.connect()
        ea_db.migrate(conn)
        try:
            if args.cmd == "forget":
                result = forget(" ".join(args.target), conn)
            elif args.cmd == "record":
                result = record(conn, kind=args.kind, text=args.text, said=args.said, about=args.about,
                                source=args.source, person=args.person, alias=args.alias)
            else:
                result = answer(conn, args.ref, args.yes, args.actor)
        finally:
            conn.close()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except LessonRefused as exc:
        print(f"NOT RECORDED: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"NOT RECORDED: the lessons store could not be written ({exc}). Tell Mike.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
