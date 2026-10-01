"""The deterministic personal-sensitivity screen every Doc edit proposal passes through.

NEW in this repo. Blueprint s.2: personal conversation, family matters and incidental
discussion must not automatically become permanent management documentation;
sensitive context is captured only when genuinely work relevant, with the right
audience. A running 1:1 Doc is read by the manager it is about, so a line written
there is a disclosure to that manager.

THIS FILE DOES NOT JUDGE. It only decides which proposals SAGE must look at.
docs_propose.py records the verdict in the proposal (`privacy_review: required` and
the category), docs_edit.py refuses a required proposal unless SAGE stamped THOSE
bytes with an approval, and SAGE alone decides whether a flagged line is work
relevant and audience appropriate (scripts/privacy_review.py).

DETECT AGGRESSIVELY, BUT NOT BLINDLY. Every flag costs a SAGE review on opus, and a
screen that fires on "Christmas lights" gets switched off. So each category is a
phrase list, tuned against the near-misses this system actually sees: "manager bonus
structure", "manager accountability", "leadership-structure feedback", "Christmas
lights" and "holiday party bookings" all pass. A guest complaint, a fire inspection,
the health inspector and a family-style menu pass too; one person's raise, a write-up,
sick leave or a family matter does not.

WHAT IT CANNOT DO, stated: it reads words, not meaning. A sensitive matter phrased
without any of these words passes, which is why SAGE's prose also tells PAGE and the
orchestrator to route anything personal through SAGE when in doubt, and why the
register and the Doc are both covered in docs/PRIVACY.md.

Categories, in the order they are checked (the first match names the category):
harassment or complaint, discipline, legal or immigration, leave of absence, mental
health, addiction, family, health, individual pay.

Usage:
    python scripts/privacy_screen.py --text "Return-to-work plan after medical leave"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass


def _words(*alternatives: str) -> re.Pattern[str]:
    """One case-insensitive pattern: any alternative, as whole words."""
    return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b", re.I)


# A person's name, possessive: a capital letter, matched case-SENSITIVELY even though
# the patterns around it are not, so "the bar's pay" and "staff's pay" do not count.
_NAMED = r"(?-i:[A-Z][a-z]+)(?:'s|’s)"
_PAY_WORD = (r"(?:raise|salary|wages?|pay(?![\s-]*(?:roll|cut-?off|period|run|day))(?:\s+rate)?|hourly\s+rate"
             r"|rate\s+of\s+pay|compensation|bonus(?![\s-]+(?:structure|plan|program|pool|scheme|policy|criteria)))")

CATEGORIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("harassment or complaint", _words(
        r"harass\w*", r"bull(?:y|ying|ied)", r"discriminat\w*", r"misconduct", r"grievances?",
        r"(?:formal|hr|staff|employee|workplace|harassment)\s+complaints?",
        r"complaints?\s+against", r"(?:filed|made|lodged|raised)\s+a\s+complaint",
        r"investigation", r"retaliat\w*", r"hostile\s+work(?:place|\s+environment)",
        r"sexual\s+(?:comments?|advances?|misconduct|harassment)",
    )),
    ("discipline", _words(
        r"disciplin\w*", r"write-?ups?", r"written\s+up", r"wrote\s+(?:him|her|them)\s+up",
        r"(?:written|verbal|final|formal|first|second|last)\s+warnings?", r"warning\s+letters?",
        r"(?:give|gave|giving|issue|issued|issuing)\s+(?:him|her|them)\s+a\s+warning",
        r"terminat(?:e|ed|es|ing|ion)", r"dismiss(?:al|ed)",
        r"(?:get|got|gets|be|been|being|was|were|is)\s+fired", r"fire\s+(?:him|her|them)",
        r"let\s+(?:him|her|them)\s+go", r"(?:be|been|being|was|were|is)\s+let\s+go",
        r"performance\s+improvement\s+plan", r"pip", r"suspen(?:ded|sion)\s+(?:without|for)",
    )),
    ("legal or immigration", _words(
        r"lawsuits?", r"suing", r"sued", r"lawyers?", r"attorneys?",
        r"legal\s+(?:action|matter|issue|trouble|proceedings?|advice|counsel|case)",
        r"court\s+(?:date|case|order|appearance)", r"criminal", r"charged\s+with", r"arrest(?:ed)?",
        r"police\s+(?:record|check)", r"immigration", r"work\s+permits?", r"work\s+visas?",
        r"visa\s+(?:status|application|renewal|expir\w*)", r"permanent\s+residen\w*", r"pr\s+card",
        r"citizenship", r"deport\w*", r"lmia",
    )),
    ("leave of absence", _words(
        r"leave\s+of\s+absence", r"loa", r"on\s+leave",
        r"(?:medical|stress|sick|parental|maternity|paternity|compassionate|bereavement|personal"
        r"|unpaid|disability|family)\s+leave",
        r"return(?:ing)?[\s-]+to[\s-]+work",
    )),
    ("mental health", _words(
        r"mental\s+health", r"anxiety", r"depression", r"burn-?out", r"burn(?:ed|t)\s+out",
        r"panic\s+attacks?", r"therap(?:y|ist)", r"counsell?(?:ing|or)", r"psychiatr\w*",
        r"psycholog\w*", r"grief", r"suicid\w*", r"self-?harm",
    )),
    ("addiction", _words(
        r"addict\w*", r"substance\s+(?:use|abuse|issues?|problems?)", r"alcoholism", r"sober\w*",
        r"sobriety", r"rehab", r"relaps\w*", r"overdos\w*",
        r"drug\s+(?:use|test\w*|abuse|problems?|issues?)",
        r"(?:drunk|intoxicated|impaired|high)\s+(?:on|at)\s+(?:shift|work)",
    )),
    ("family", _words(
        r"family(?![\s-]+(?:meal|day|style|size|friendly|pack|dinner))", r"pregnan\w*",
        r"maternity", r"paternity", r"child\s*care", r"day\s*care", r"nanny", r"bereave\w*",
        r"funeral", r"passed\s+away", r"death\s+in\s+the\s+family", r"divorc\w*", r"custody",
        r"miscarriage", r"expecting\s+a\s+(?:baby|child)",
        r"(?:his|her|their)\s+(?:wife|husband|partner|spouse|kids?|children|son|daughter|mother"
        r"|father|mom|dad|parents?)",
    )),
    ("health", _words(
        r"health(?![\s-]+(?:and[\s-]+safety|inspect\w*|code|department|unit|check\s+on\s+the))",
        r"medical", r"medication", r"doctor(?:'?s)?", r"surgery", r"surgical", r"hospital\w*",
        r"sick(?:ness)?(?!\s+of\b)", r"illness", r"injur(?:y|ies|ed)", r"diagnos\w*", r"symptoms?",
        r"chronic", r"disabilit(?:y|ies)", r"physio\w*", r"concussion", r"cancer", r"covid", r"flu",
    )),
    ("individual pay", re.compile(
        r"\b(?:his|her|their)\s+" + _PAY_WORD + r"\b"
        r"|" + _NAMED + r"\s+" + _PAY_WORD + r"\b"
        r"|\b(?:raise|pay\s+(?:rise|increase|bump)|salary\s+increase|bonus)\s+for\s+"
        r"(?:him|her|them|(?-i:[A-Z][a-z]+))\b"
        r"|\b(?:give|gave|giving|get|got|getting|ask(?:ed|ing)?\s+for)\s+(?:(?:him|her|them|(?-i:[A-Z][a-z]+))\s+)?a\s+raise\b"
        r"|\bpay\s+cuts?\b(?![\s-]*off)"
        r"|\bsalary\s+(?:review|bump|cut|adjustment|negotiation|discussion|increase)\b"
        r"|\b(?:cut|reduce|increase|adjust|raise)\s+(?:his|her|their|" + _NAMED + r")\s+"
        r"(?:pay|salary|wages?|hours|rate)\b",
        re.I)),
)


@dataclass(frozen=True)
class Flag:
    """Why a text needs SAGE: the category and the exact words that matched."""

    category: str
    matched: str


def screen(text: str) -> Flag | None:
    """The first category whose words appear in `text`, or None."""
    for category, pattern in CATEGORIES:
        found = pattern.search(text or "")
        if found:
            return Flag(category, found.group(0))
    return None


def screen_all(*texts: str | None) -> Flag | None:
    for text in texts:
        flag = screen(text or "")
        if flag:
            return flag
    return None


def doc_bound_texts(proposal: dict) -> list[str]:
    """Every string this proposal would write into a Doc. Nothing else is screened."""
    cells = proposal.get("cells") or {}
    texts = [proposal.get("text"), proposal.get("status_text"),
             *(cells.get(k) for k in ("assignee", "title", "date_text", "status"))]
    return [t for t in texts if isinstance(t, str) and t]


def review_required(proposal: dict) -> tuple[bool, str]:
    """(SAGE must review it, the category). The proposal's own field, or the screen re-run.

    Re-run on purpose: a proposal written before the screen existed has no field, and
    the field is not trusted to stand alone any more than PAGE's indices are.
    """
    if proposal.get("privacy_review") == "required":
        return True, str(proposal.get("privacy_category") or "personal")
    flag = screen_all(*doc_bound_texts(proposal))
    return (True, flag.category) if flag else (False, "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    flag = screen(args.text)
    if flag is None:
        print("not_required: no personal-sensitivity words found")
        return 0
    print(f"required: {flag.category} ({flag.matched!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
