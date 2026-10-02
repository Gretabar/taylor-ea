"""Validate agent, skill and command files under .claude/ in this repo.

PORTED FROM PIPER. Agents, skills and commands live under .claude/ here so the VS
Code extension finds them by opening the folder. The roster is read from
context/roster-agents.json, the same file the hooks read, so the validator and
the gates cannot disagree about who exists. Skills owned by the orchestrator
declare "Owner: orchestrator", a token that survives renaming the system.

PORTED FROM STEVIE. The comments below keep, for each rule, the class of defect
that produced it, written generically, because a rule whose reason has been
sanitised away is a rule the next person deletes.

Two classes of defect this catches, both of which fail silently at runtime:

1. Invalid YAML frontmatter. An unquoted `description:` containing a colon-space
   is not valid YAML, so a strict parser rejects the whole block and the agent or
   skill never loads. Nothing errors; the agent is simply absent.

2. Tool-contract drift. An agent's prose describes a capability its `tools:` list
   never granted -- a skill that shells out to Python without Bash, or one that
   drives a browser without Playwright. The agent works around the gap instead of
   failing, which is worse: it produces output that looks complete and was never
   actually measured. A skill declares no `tools:` of its own, so it is checked
   against the tools of the agent that owns it (see OWNER_FORMS).

   Here it matters because the tool grants are the first layer of the delivery
   boundary: WREN is meant to be the only agent that writes to a Doc, and PAGE and
   REED produce proposals and register rows only. An agent whose prose claims work
   its frontmatter never granted is an agent that will improvise past a boundary
   somebody drew on purpose.

Run from the repo root:

    python scripts/validate_agent_contracts.py
    python scripts/validate_agent_contracts.py --self-test

Exits non-zero if anything fails, so it is safe to wire into a hook.

The self-test exists because of this file's own history: the `Write` signal below
was documented, hooked, and structurally incapable of matching for as long as it
shipped. Green here proves the repo is clean; green from `--self-test` proves the
checks can still go red. The self-test runs against a FIXED roster constant
rather than against agents/*.md, so it still proves the checks work on a machine
where the agent files have not been written yet.
"""

from __future__ import annotations

import glob
import os
import re
import sys

import yaml

ROOT = os.environ.get("EA_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import team  # noqa: E402


def _load_roster() -> tuple[str, ...]:
    """NAME of every agent in context/roster-agents.json."""
    import json  # noqa: PLC0415

    with open(os.path.join(ROOT, "context", "roster-agents.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    return tuple(str(a["name"]).upper() for a in data["agents"])


ROSTER = _load_roster()
ORCHESTRATOR = "ORCHESTRATOR"

# What an agent that is not switched on may hold. If a dispatch ever slipped past
# require-active-agent.py, an agent with these tools can read and nothing else.
READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep"})

# Signals in an agent's body that imply a tool it must hold in frontmatter.
# Keyed by the required tool; each value is a list of regexes.
#
# A note on the `Write` entry, because it is the reason this file is worth
# re-reading. A pattern like `\*\*Output\*\*:\s*[cC]:` cannot match, because the
# line is written as ``**Output**: `c:\...` `` with a backtick after the space.
# A rule that is documented and wired but can never match has never once fired.
# A check nobody has watched fail is a check nobody has tested.
TOOL_SIGNALS: dict[str, list[str]] = {
    "Bash": [
        r"\bpython3?\s+[\w./\\-]+\.py",   # was `python\s+scripts/`: missed bare paths and python3
        r"\bpy\s+-3\s+[\w./\\-]+\.py",
        r"\.ps1\b",
        r"\bpwsh\b",
        r"\breportlab\b",
        r"\bopenpyxl\b",
        r"\bnpx\b",
    ],
    "Write": [
        r"\*\*Output\*\*:\s*[`'\"]?\s*[a-zA-Z]:[\\/]",  # absolute path, backticked or not
        r"\*\*Output\*\*:\s*[`'\"]?\s*output/",         # repo-relative form
    ],
    # Not a bare `\bPlaywright\b`. That also matches a `.playwright-mcp/`
    # cookie-jar path, which a skill can cite while its owner drives no browser
    # at all (the pipeline runs a downloader under Bash). A tool name inside a
    # path is a citation, not a claim, the same distinction INVOCATION draws
    # further down.
    "mcp__playwright__browser_navigate": [
        r"(?<![./\w-])Playwright(?!-mcp)\b",
        r"\bbrowser_navigate\b",
    ],
}

# Browser sub-capabilities, checked only where the document drives a web UI by
# hand (see UI_VOCABULARY below).
#
# The signal above maps every browser claim onto `browser_navigate`, so an agent
# holding navigate and nothing else passes while being unable to upload a file,
# open a dropdown, click, type, or capture what it saw. An agent can then own a
# skill whose core step is putting a photo through a web app's file dialog while
# holding five Playwright tools, none of them `browser_file_upload`. At runtime
# it clicks "Add photos", meets a file dialog it cannot drive, works around the
# gap, and reports an upload that never happened, and the validator says OK.
#
# Every pattern here was matched against real skill text. Two candidates were
# tried and cut rather than shipped unproven: `\bwait (for|until)\b` only ever
# matched planning prose ("build it now or wait until it ships"), and `\bhover\b`
# only matched CSS hover states in a design skill whose owner needs no
# `browser_hover`.
BROWSER_SIGNALS: dict[str, list[str]] = {
    "mcp__playwright__browser_file_upload": [
        r"\bbrowser_file_upload\b",
        r"\bupload\w*",
        r"\badd photos?\b",          # a web app's button label, and the defect itself
    ],
    "mcp__playwright__browser_select_option": [
        r"\bbrowser_select_option\b",
        r"\bdrop-?downs?\b",
    ],
    "mcp__playwright__browser_click": [
        r"\bbrowser_click\b",
        r"\bclick(?:s|ing|ed)? (?:the|on|every|into|\*\*|\"|`|>)",  # imperative, not "one-click approval"
        r"\bcheckbox\b",
        r"\bUncheck\b",
    ],
    "mcp__playwright__browser_type": [
        r"\bbrowser_type\b",
        # Not `\btype (?:in|the)\b`: "the source type in use" in audit-policy
        # matches that and means nothing of the kind.
        r"\btype (?:the|into|in the)\b",
    ],
    "mcp__playwright__browser_take_screenshot": [
        r"\bbrowser_take_screenshot\b",
        r"\bscreenshots?\b",
    ],
}

# BROWSER_SIGNALS apply only to documents that actually drive a UI by hand.
# Ungated, `\bupload\w*` alone produced five findings and all five were wrong: a
# `"uploader"` JSON key, "file uploads" as a governance event category, an upload
# to a speech API through its SDK, a knowledge-file upload, and a re-encode step.
# None of them is a browser.
#
# A document qualifies if it names Playwright or the browser tools, or if it
# shows TWO independent kinds of UI vocabulary. Two, not one: at one, a reference
# document qualifies on a single menu path inside a paragraph about a site
# builder's editor, or on a single "log in", and nobody clicks through those. At
# two, a skill with seven menu paths and four widget words qualifies without ever
# naming Playwright, which is exactly the case that motivated all of this.
#
# Compiled with explicit flags rather than matched with a blanket re.I. The
# signal patterns above are all matched case-insensitively, and quietly gating
# them behind case-SENSITIVE vocabulary meant a sentence-initial "Click the
# **Create** button" -- the commonest form there is -- did not count as UI
# vocabulary at all. The self-test caught that; nothing in the repo would have.
UI_VOCABULARY: dict[str, re.Pattern[str]] = {
    "playwright": re.compile(
        r"(?<![./\w-])Playwright(?!-mcp)\b|\bmcp__playwright__|\bbrowser_[a-z_]+\b", re.I
    ),
    # The one deliberate exception: a UI menu path is Title Case ("Account
    # Settings > Special days"). Case-folded it would also match a markdown
    # blockquote and any `a > b` in a code sample.
    "menu path": re.compile(r"\*?\*?[A-Z][A-Za-z]+(?: [A-Za-z]+){0,2}\*?\*? > \*?\*?[A-Z][A-Za-z]+"),
    "click": re.compile(r"\bclick(?:s|ing|ed)? (?:the|on|every|into|\*\*|\"|`|>)", re.I),
    "widget": re.compile(r"\bcheckbox\b|\bdrop-?down\b|\bthe wizard\b|\bmodal\b|\bsecond tab\b", re.I),
    "login": re.compile(r"\blog(?:ged)? in(?:to| to)\b|\bsign in\b", re.I),
}

# A browser driven from inside a Python script needs Bash, not MCP browser
# tools. A skill can document a web app's DOM in forensic detail (checkbox
# quirks, `a.dropdown-toggle`, which clicks the modal backdrop swallows) while
# every operation runs through a Python script inside `open_session(...)`.
# Charging it MCP browser tools would be four wrong findings.
SCRIPT_DRIVEN_BROWSER = re.compile(
    r"sync_playwright|async_playwright|\bopen_session\(|\bpage\.[a-z_]+\("
)


def drives_ui_by_hand(text: str) -> bool:
    """True when a document clicks through a web UI itself, rather than shelling out."""
    if SCRIPT_DRIVEN_BROWSER.search(text):
        return False
    families = [name for name, pattern in UI_VOCABULARY.items() if pattern.search(text)]
    return "playwright" in families or len(families) >= 2


FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---", re.S)


def load_frontmatter(path: str) -> tuple[dict | None, str, str]:
    """Return (parsed_frontmatter, body, error). frontmatter is None on failure."""
    text = open(path, encoding="utf-8").read()
    match = FRONTMATTER.match(text)
    if not match:
        return None, text, "no frontmatter block"
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return None, text, str(exc).splitlines()[0]
    if not isinstance(data, dict):
        return None, text, "frontmatter is not a mapping"
    return data, text[match.end():], ""


def check_parses(paths: list[str], failures: list[str]) -> dict[str, tuple[dict, str]]:
    """Parse every file, recording failures. Returns the ones that parsed."""
    parsed = {}
    for path in paths:
        data, body, error = load_frontmatter(path)
        if data is None:
            failures.append(f"{path}: {error}")
        else:
            parsed[path] = (data, body)
    return parsed


# Skill ownership, so a skill body can be checked against the tools its owner
# actually holds. Skills declare no `tools:` of their own, so a check that skips
# any file without `tools:` skips every skill, and skills are where the
# operational prose lives ("upload the photo", "open the settings page"). It
# would be structurally blind to most of the files it reports OK on.
#
# Ownership is declared informally. Six live forms turn up in practice:
#
#   Owner: REED.                          the plain form
#   Owner - WREN, with PAGE for the proposal
#   Owners - REED (register), PAGE (proposal)
#   Owner HUGO (diagnosis) with WREN
#   WREN owns this. / **WREN** owns the script
#   - Owned by REED (register)            a body bullet
#
# One regex family covers all of them, in description first then body, taking the
# FIRST agent named. First, not all: "Owner - WREN, with PAGE for the proposal and
# REED for the row" is one owner and two helpers, and charging PAGE with WREN's
# tools is how a check earns its reputation for crying wolf.
OWNER_FORMS = (
    r"\bOwners?\b[\s:*—–-]*({names})\b",
    r"\bOwned by\s+\**({names})\b",
    r"\**({names})\**\s+owns\s+(?:this|it|the)\b",
)

# Weaker, description-only forms, used when no explicit Owner line exists. Both
# are load-bearing where two agents list the same skill: the agent-side fallback
# below refuses to guess between two claimants, and then a description form is
# the only thing that resolves the owner.
DESCRIPTION_OWNER_FORMS = (
    r"^\**({names})\**'s\b",        # "PAGE's section map. Anchors on label text."
    r"\bwhen ({names}) needs\b",    # "Use when PAGE needs the structure"
)

# Last resort: the agent side of the same claim. Agents list what they own as
# `- **skill-name** -- ...` under "Key skills". The bullet must LEAD with the
# bolded slug; "- Also reaches for **some-skill**" is a use, not a claim, and
# deliberately does not match. Two agents claiming the
# same slug resolves to nobody rather than to a guess.
AGENT_SKILL_CLAIM = re.compile(r"^\s*[-*+]\s+\*\*([a-z0-9-]+)\*\*", re.M)


def agent_roster(agent_paths: list[str]) -> dict[str, str]:
    """Map AGENTNAME -> file path, from agents/*.md."""
    return {os.path.basename(p)[: -len(".md")].upper(): p for p in agent_paths}


def resolve_skill_owner(
    description: str, body: str, slug: str, roster: dict[str, str], claims: dict[str, set[str]]
) -> str | None:
    """Return the primary owning agent of a skill, or None if it is unattributable."""
    # The orchestrator is in the alternation on purpose. It owns reality-checker,
    # capture-rules and morning-brief, runs on the main thread with no `tools:`
    # contract of its own, and resolving to it means "deliberately unchecked"
    # rather than falling through to a weaker guess. Matched case-insensitively
    # because skills write "Owner: orchestrator".
    names = "|".join(sorted(list(roster) + [ORCHESTRATOR]))
    # `.replace`, not `.format`: these are regexes, and a `{0,2}` quantifier
    # added to one later would make str.format raise on a valid pattern.
    for forms, haystacks in ((OWNER_FORMS, (description, body)), (DESCRIPTION_OWNER_FORMS, (description,))):
        for haystack in haystacks:
            for form in forms:
                match = re.search(form.replace("{names}", names), haystack.strip(), re.I)
                if match:
                    return match.group(1).upper()
    owners = claims.get(slug, set())
    return next(iter(owners)) if len(owners) == 1 else None


def resolve_tool_holders(
    agents: dict[str, tuple[dict, str]],
    skills: dict[str, tuple[dict, str]],
    agent_paths: list[str],
    failures: list[str],
) -> tuple[dict[str, tuple[str, str, set[str], str]], list[str]]:
    """Map each doc to the tool set it is checked against.

    Returns ({path: (text, body, held, grant_source)}, unattributed_skill_paths).
    `text` is what the signal patterns read; `body` is what the line-numbered MCP
    check reads, so its line numbers stay true.
    """
    roster = agent_roster(agent_paths)
    holders: dict[str, tuple[str, str, set[str], str]] = {}

    def own_tools(path: str, data: dict) -> set[str] | None:
        tools = data.get("tools")
        if tools is None:
            return None  # omitted `tools:` means inherit everything -- nothing to check
        if not isinstance(tools, list):
            failures.append(f"{path}: `tools:` is not a list")
            return None
        return set(tools)

    for path, (data, body) in agents.items():
        held = own_tools(path, data)
        if held is not None:
            holders[path] = (body, body, held, "frontmatter")

    claims: dict[str, set[str]] = {}
    for name, path in roster.items():
        for slug in AGENT_SKILL_CLAIM.findall(open(path, encoding="utf-8").read()):
            claims.setdefault(slug, set()).add(name)

    unattributed: list[str] = []
    for path, (data, body) in skills.items():
        held = own_tools(path, data)
        description = str(data.get("description", ""))
        if held is not None:
            holders[path] = (f"{description}\n{body}", body, held, "frontmatter")
            continue
        # A `skills/_proposed/` draft is staged for review, not wired to anyone.
        # Such drafts are typically machine-generated stubs whose own frontmatter
        # says "review before enabling". Holding a draft to a runtime contract is
        # the definition of crying wolf.
        if path.replace("\\", "/").startswith(".claude/skills/_proposed/"):
            continue
        slug = os.path.basename(os.path.dirname(path))
        owner = resolve_skill_owner(description, body, slug, roster, claims)
        if owner not in roster:
            # Unowned, or owned by the orchestrator. Reported as a NOTE, never as a
            # failure: who owns a skill is a judgment call, and a validator that
            # fails on a documentation gap it cannot fix gets switched off.
            reason = (
                "owned by the orchestrator, which runs on the main thread and declares no tools"
                if owner == ORCHESTRATOR
                else "no owner declared"
            )
            unattributed.append(f"{path} -- {reason}")
            continue
        owner_path = roster[owner]
        if owner_path not in agents:
            continue  # the owner's own frontmatter failed to parse; already reported
        holders[path] = (
            f"{description}\n{body}",
            body,
            set(agents[owner_path][0].get("tools") or []),
            f"its owner {owner} ({owner_path})",
        )
    return holders, unattributed


def check_tool_contracts(
    holders: dict[str, tuple[str, str, set[str], str]], failures: list[str]
) -> None:
    """Flag agents or skills whose prose implies a tool the granting frontmatter omits."""
    for path, (text, _body, held, grant_source) in sorted(holders.items()):
        signals = dict(TOOL_SIGNALS)
        if drives_ui_by_hand(text):
            signals.update(BROWSER_SIGNALS)
        for required, patterns in signals.items():
            if required in held:
                continue
            hit = next((p for p in patterns if re.search(p, text, re.I)), None)
            if hit:
                failures.append(
                    f"{path}: body matches /{hit}/ but {grant_source} omits {required}"
                )


# MCP capability claims. Keyed by a regex for the capability name; the value is
# the tool-name prefix the agent must hold, and a human label.
#
# Matched by PREFIX, not exact tool name -- an agent may hold
# mcp__claude_ai_Supabase__execute_sql, and demanding one specific tool would be
# brittle for no gain.
MCP_SIGNALS: dict[str, tuple[str, str]] = {
    # Deliberately short. Signals for systems that do not exist in this system's
    # world are signals that can never fire, and nobody maintains those.
    #
    # Two Gmail servers are live and either satisfies the claim, so the prefixes
    # are `|`-separated alternatives. Prefer the local USER-scope server for
    # agents: interactively-authenticated connectors can be absent in headless
    # and scheduled runs, and an agent that loses its draft tool at 09:00 on a
    # schedule fails silently.
    r"\bGmail\b": ("mcp__gmail__|mcp__claude_ai_Gmail__", "Gmail"),
    r"\bGoogle Drive\b|\bGoogle Sheets\b": (
        "mcp__claude_ai_Google_Drive__|mcp__gdrive__", "Google Drive"),
    r"\bSupabase\b": ("mcp__claude_ai_Supabase__|mcp__supabase__", "Supabase"),
}

# A capability claim is a STRUCTURAL POSITION, not a keyword occurrence. Only
# three positions count, so prose, table cells and code blocks are excluded by
# construction. An agent file that lists systems inside a sentence about blast
# radius mentions them; it does not claim them, and the positions keep it that
# way.
CLAIM_POSITIONS = (
    re.compile(r"^\s*[-*+]\s+\*\*([^*]+)\*\*"),   # bolded list-item label
    re.compile(r"^#{2,4}\s+(.+)$"),               # section heading
    re.compile(r"^\s*[-*+]?\s*(\*\*Output\*\*:.*)$"),  # deliverable destination
)


def body_line_offset(path: str) -> int:
    """File line number of the body's first line, so reports cite real lines."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return 0
    match = FRONTMATTER.match(text)
    return text[: match.end()].count("\n") + 1 if match else 0


def check_mcp_contracts(
    holders: dict[str, tuple[str, str, set[str], str]], failures: list[str]
) -> None:
    """Flag a claimed MCP capability the granting frontmatter never granted."""
    for path, (_text, body, tools, grant_source) in sorted(holders.items()):
        held = " ".join(sorted(tools))
        offset = body_line_offset(path)
        for lineno, line in enumerate(body.splitlines(), 1):
            # ALL matching positions, not the first. A `- **Output**: ... Notion`
            # line matches the bolded-label pattern too, and taking only the
            # first match let the bold span ("Output") shadow the destination
            # text -- so a deliverable declared as landing in Notion went
            # unflagged by a check written to catch exactly that.
            claims = [m.group(1) for m in (p.match(line) for p in CLAIM_POSITIONS) if m]
            for claim in claims:
                for pattern, (prefix, label) in MCP_SIGNALS.items():
                    # A `|`-separated prefix means "any of these satisfies the
                    # claim" -- see the Gmail entry, where two servers are live.
                    accepted = prefix.split("|")
                    if re.search(pattern, claim, re.I) and not any(p in held for p in accepted):
                        wanted = " or ".join(f"{p}*" for p in accepted)
                        failures.append(
                            f"{path}:{offset + lineno - 1}: claims {label} "
                            f"({claim.strip()[:60]!r}) but {grant_source} grants no "
                            f"{wanted} tool"
                        )


# A script named in an execution position -- `python x.py`, `run x.py`. A
# backticked filename inside a sentence is a citation, not an instruction, and
# citing another repo's file is legitimate.
INVOCATION = re.compile(
    r"(?:python3?|py\s+-3|\brun\b)\s+[`'\"]?([A-Za-z0-9_./\\:<>\[\]{}*+-]+\.py)",
    re.I,
)

# Pruned during the walk: vendored reference trees can hold thousands of files,
# and this runs on a hook.
WALK_SKIP = {"node_modules", ".git", ".venv", "reference", ".playwright-mcp", "__pycache__"}


def repo_python_files() -> tuple[set[str], set[str]]:
    """Return (all basenames, all repo-relative paths) for .py files in the tree."""
    basenames, relpaths = set(), set()
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in WALK_SKIP]
        for name in files:
            if name.endswith(".py"):
                basenames.add(name)
                rel = os.path.join(root, name).replace("\\", "/").removeprefix("./")
                relpaths.add(rel)
    return basenames, relpaths


def check_referenced_scripts(paths: list[str], failures: list[str]) -> None:
    """Flag a script an agent or skill tells itself to run that does not exist.

    The contract check passes when an agent holds `Bash` -- it never asks whether
    the thing it is told to run is actually there. An agent told to run a
    script that does not exist anywhere in the repo, and holding Bash, passes
    validation and improvises the output instead.
    """
    basenames, relpaths = repo_python_files()
    repo_root = os.path.abspath(".")
    top_level = {d for d in os.listdir(".") if os.path.isdir(d)}

    for path in paths:
        try:
            text = open(path, encoding="utf-8").read()
        except OSError as exc:
            failures.append(f"{path}: unreadable, so it was never checked -- {exc}")
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            for token in INVOCATION.findall(line):
                # 1. Filename templates are not references to a real file.
                if any(c in token for c in "<>[]{}*") or "YYYY" in token:
                    continue

                norm = token.replace("\\", "/")
                is_abs = norm.startswith("/") or re.match(r"^[A-Za-z]:/", norm)

                # 2. Anything resolving outside this repo belongs to another
                #    project and is not ours to validate.
                if is_abs:
                    absolute = os.path.abspath(norm)
                    try:
                        common = os.path.commonpath([absolute, repo_root])
                    except ValueError:
                        continue  # different drive: definitely not ours
                    # normcase on both sides: on Windows commonpath preserves the
                    # casing of its first argument, so a `c:/...` reference against
                    # a `C:\...` root compares unequal and an in-repo path gets
                    # silently waved through as external.
                    if os.path.normcase(common) != os.path.normcase(repo_root):
                        continue
                    rel = os.path.relpath(absolute, repo_root).replace("\\", "/")
                elif "/" in norm:
                    if norm.split("/", 1)[0] not in top_level:
                        continue
                    rel = norm
                else:
                    rel = None  # bare basename

                if rel is not None:
                    if rel.startswith("output/"):
                        failures.append(
                            f"{path}:{lineno}: references `{token}` under gitignored "
                            f"output/ -- a script an agent depends on cannot live "
                            f"outside version control. Move it to scripts/."
                        )
                    elif rel not in relpaths:
                        failures.append(
                            f"{path}:{lineno}: references `{token}`, which does not "
                            f"exist. The agent holds Bash, so nothing errors -- it "
                            f"improvises and the output looks measured."
                        )
                elif os.path.basename(norm) not in basenames:
                    failures.append(
                        f"{path}:{lineno}: references `{token}`, which does not exist "
                        f"anywhere in the repo. The agent holds Bash, so nothing "
                        f"errors -- it improvises and the output looks measured."
                    )


# Each case is (label, tools held, document text, tool expected in the finding).
# A `None` expectation means the case MUST produce nothing -- those are the
# false positives that were observed while writing the browser signals, kept as
# fixtures so a later loosening of a regex reintroduces them loudly.
SELF_TEST_SIGNALS: list[tuple[str, set[str], str, str | None]] = [
    (
        "a photo upload through a web app, the defect this was built for",
        {"mcp__playwright__browser_click", "mcp__playwright__browser_navigate"},
        "Open **Account Settings > Gallery**. The **checkbox** stays off.\n"
        "Verify dimensions yourself before uploading.",
        "mcp__playwright__browser_file_upload",
    ),
    (
        "dropdown in a hand-driven UI",
        {"mcp__playwright__browser_click", "mcp__playwright__browser_navigate"},
        "Open **Marketing > Campaigns**, then pick the shift from the dropdown.",
        "mcp__playwright__browser_select_option",
    ),
    (
        "imperative click",
        {"mcp__playwright__browser_navigate"},
        "Open **Account Settings > Special days**. Click the **Create** button.",
        "mcp__playwright__browser_click",
    ),
    (
        "typing into a field",
        {"mcp__playwright__browser_navigate", "mcp__playwright__browser_click"},
        "Drive it with Playwright. Type the title into the description field.",
        "mcp__playwright__browser_type",
    ),
    (
        "screenshot",
        {"mcp__playwright__browser_navigate"},
        "Drive it with Playwright and take screenshots at three widths.",
        "mcp__playwright__browser_take_screenshot",
    ),
    (
        "shelling out to Python",
        set(),
        "Run `python scripts/_verify_counts.py` and read the count.",
        "Bash",
    ),
    (
        "noise: an `uploader` JSON key outside any UI",
        set(),
        'The record is `{"id": "...", "title": "...", "uploader": "..."}`.',
        None,
    ),
    (
        "noise: file uploads as a governance event category",
        set(),
        "Governance events: SSO changes, data exports, membership changes, file uploads.",
        None,
    ),
    (
        "noise: one UI family only, so it is a reference doc",
        set(),
        "Wix's editor hides it under **Settings > Domains**; clients upload their own logo.",
        None,
    ),
    (
        "noise: a browser driven from inside a script needs Bash, not MCP tools",
        {"Bash"},
        "With open_session(headless=True) as (browser, page): row checkboxes are\n"
        "`input.select-on-check`, and each row's actions hang off `a.dropdown-toggle`.",
        None,
    ),
    (
        "noise: a `.playwright-mcp/` cookie jar is a path, not a browser claim",
        {"Bash"},
        "The site needs a logged-in session; `.playwright-mcp/session/cookies.txt` is it.",
        None,
    ),
]

# (label, description, body, expected owner). Every declaration form the skill
# authors are likely to reach for, plus the two near-misses that must resolve to
# nobody.
SELF_TEST_OWNERS: list[tuple[str, str, str, str | None]] = [
    ("primary owner, helpers ignored", "... Owner - WREN, with PAGE for the proposal and REED for the row.", "", "WREN"),
    ("colon form", "... Owner: PAGE (structure), orchestrated by the orchestrator.", "", "PAGE"),
    ("plural form", "... Owners - REED (register), PAGE (proposal), WREN (delivery).", "", "REED"),
    ("bare form", "... Owner HUGO (diagnosis) with WREN (delivery).", "", "HUGO"),
    ("verb form in the body", "A skill.", "Routing lives elsewhere. **WREN** owns this script.", "WREN"),
    ("owned-by bullet in the body", "A skill.", "- Owned by REED (register); drafting: PAGE", "REED"),
    ("possessive description", "PAGE's section map. Anchors on label text.", "", "PAGE"),
    ("use-when description", "Read a Doc. Use when PAGE needs the structure.", "", "PAGE"),
    ("the orchestrator, lower case", "Owner: orchestrator (main thread).", "", "ORCHESTRATOR"),
    ("humans named as owners are not agents", "Owners: Taylor Iwaasa (policy), Mike Kelly (build).", "", None),
    ("a mention of an owner is not a declaration", "A skill.", "The verification is the owner's to complete.", None),
]


def check_roster_files(agents: dict[str, tuple[dict, str]], roster_team) -> list[str]:
    """Each roster agent's file against the roster and its standing (scripts/team.py).

    The model in the frontmatter is the roster's model. An agent that is not switched
    on holds only Read, Glob and Grep, the second layer behind the dispatch gate, and
    its file quotes the two lines it answers with while nothing is approved for it.
    Those dormant lines, not today's: on Taylor's machine a phase can be approved
    before Mike has built it, and a code file there cannot change to match.
    """
    failures: list[str] = []
    by_name = {os.path.basename(path)[:-3].upper(): (path, data, body) for path, (data, body) in agents.items()}
    for name, agent in roster_team.agents.items():
        if name not in by_name:
            continue  # a missing file is reported by the caller, with the roster's wording
        path, data, body = by_name[name]
        want = str(agent.get("model") or "")
        if want and str(data.get("model") or "") != want:
            failures.append(f"{path}: model {data.get('model')!r}, but context/roster-agents.json says {want!r}")
        if agent.get("read_only") is True:
            # confine-read-only-agent.py limits its Bash to a list; every other tool must be absent here,
            # so the hook is never the only thing between a read-only agent and a write.
            tools = data.get("tools")
            extra = (sorted(set(tools) - READ_ONLY_TOOLS - {"Bash"}) if isinstance(tools, list)
                     else ["every tool (no tools: list)"])
            if extra:
                failures.append(f"{path}: {name} is read only (context/roster-agents.json) but holds "
                                f"{', '.join(extra)}; it may hold only {', '.join(sorted(READ_ONLY_TOOLS))} and Bash")
        status = roster_team.status(name)
        if status is None or status.active:
            continue
        tools = data.get("tools")
        extra = sorted(set(tools) - READ_ONLY_TOOLS) if isinstance(tools, list) else ["every tool (no tools: list)"]
        if extra:
            failures.append(f"{path}: {name} is not switched on but holds {', '.join(extra)}; an agent "
                            f"that is off may hold only {', '.join(sorted(READ_ONLY_TOOLS))}")
        for line in roster_team.dormant_lines(name):
            if line not in body:
                failures.append(f"{path}: {name} is not switched on, and its file does not quote the line "
                                f"it must answer with: {line}")
    return failures


def _self_test_team():
    """A three-agent team, fixed here, so the roster checks are proven without the repo's own files."""
    phases = {"phases": {str(n): {"approved": n == 1} for n in range(1, 8)}}
    roster = {"agents": [{"name": "REED", "phase": 1, "model": "opus", "lane": "Action Register"},
                         {"name": "MILO", "phase": 2, "model": "opus", "lane": "meetings and transcripts"},
                         {"name": "LARK", "phase": 1, "model": "sonnet", "lane": "prep", "read_only": True}],
              "build_record": {"phase 1": {"accepted": "2026-10-01"}}}
    return team.Team(roster, phases, {"deviations": {}})


def self_test() -> int:
    """Prove every signal can still fail, and every documented suppression still suppresses."""
    problems: list[str] = []

    for label, held, text, expected in SELF_TEST_SIGNALS:
        found: list[str] = []
        check_tool_contracts({"<case>": (text, text, held | {"Write"}, "the test")}, found)
        if expected is None and found:
            problems.append(f"{label}: expected silence, got {found}")
        elif expected is not None and not any(expected in f for f in found):
            problems.append(f"{label}: expected a {expected} finding, got {found or 'nothing'}")

    # The FIXED roster, not agents/*.md. A self-test that cannot run until the
    # agent files exist cannot be used to prove the checks work BEFORE they are
    # written, which is exactly when somebody wants to know.
    roster = {name: f".claude/agents/{name.lower()}.md" for name in ROSTER}
    for label, description, body, expected in SELF_TEST_OWNERS:
        got = resolve_skill_owner(description, body, "unclaimed-slug", roster, {})
        if got != expected:
            problems.append(f"{label}: resolved to {got}, expected {expected}")

    # The agent-side fallback, and its refusal to guess between two claimants.
    for label, claims, expected in [
        ("single claimant", {"a-skill": {"REED"}}, "REED"),
        ("two claimants resolve to nobody", {"a-skill": {"REED", "PAGE"}}, None),
    ]:
        got = resolve_skill_owner("A skill.", "", "a-skill", roster, claims)
        if got != expected:
            problems.append(f"{label}: resolved to {got}, expected {expected}")

    # The roster checks. A switched-off agent that can act, or that does not know what
    # to answer, is the case the dispatch gate's second layer exists for.
    fixed = _self_test_team()
    quoted = "\n".join(fixed.dormant_lines("MILO"))
    roster_cases = [
        ("a switched-off agent holding Bash is a failure", {"model": "opus", "tools": ["Read", "Bash"]}, quoted, "holds Bash"),
        ("a switched-off agent with no tools: list inherits everything", {"model": "opus"}, quoted, "every tool"),
        ("a switched-off agent that does not quote its lines is a failure",
         {"model": "opus", "tools": ["Read"]}, "Not on yet.", "does not quote"),
        ("a model that differs from the roster is a failure",
         {"model": "sonnet", "tools": ["Read", "Grep", "Glob"]}, quoted, "model 'sonnet'"),
        ("a switched-off agent done right passes", {"model": "opus", "tools": ["Read", "Grep", "Glob"]}, quoted, None),
    ]
    for label, frontmatter, body, expected in roster_cases:
        found = check_roster_files({".claude/agents/milo.md": (frontmatter, body)}, fixed)
        if expected is None and found:
            problems.append(f"{label}: expected silence, got {found}")
        elif expected is not None and not any(expected in f for f in found):
            problems.append(f"{label}: expected a finding with {expected!r}, got {found or 'nothing'}")
    found = check_roster_files({".claude/agents/reed.md": ({"model": "opus", "tools": ["Read", "Bash"]}, "")}, fixed)
    if found:
        problems.append(f"a switched-on agent may hold Bash: expected silence, got {found}")
    read_only_cases = [
        ("a read-only agent holding Write is a failure", {"model": "sonnet", "tools": ["Read", "Bash", "Write"]},
         "is read only"),
        ("a read-only agent with no tools: list inherits everything", {"model": "sonnet"}, "every tool"),
        ("a read-only agent holding Read, Grep, Glob and Bash passes",
         {"model": "sonnet", "tools": ["Read", "Grep", "Glob", "Bash"]}, None),
    ]
    for label, frontmatter, expected in read_only_cases:
        found = check_roster_files({".claude/agents/lark.md": (frontmatter, "")}, fixed)
        if expected is None and found:
            problems.append(f"{label}: expected silence, got {found}")
        elif expected is not None and not any(expected in f for f in found):
            problems.append(f"{label}: expected a finding with {expected!r}, got {found or 'nothing'}")

    if problems:
        print(f"SELF-TEST FAIL -- {len(problems)} check(s) no longer behave as documented:\n")
        for problem in problems:
            print(f"  {problem}")
        return 1
    cases = len(SELF_TEST_SIGNALS) + len(SELF_TEST_OWNERS) + 2 + len(roster_cases) + 1 + len(read_only_cases)
    print(f"SELF-TEST OK -- {cases} cases: every signal fires, every suppression holds")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    os.chdir(ROOT)
    agent_paths = sorted(p.replace("\\", "/") for p in glob.glob(".claude/agents/*.md"))
    # taylor-front-door is generated on Taylor's machine from .claude/commands/NAME.md (scripts/overlay.py
    # name), gitignored, and checked as that command; a copy is not a second contract.
    skill_paths = sorted(p.replace("\\", "/") for p in
                         set(glob.glob(".claude/skills/*/SKILL.md")) | set(glob.glob(".claude/skills/*/*/SKILL.md"))
                         if "taylor-front-door" not in p.replace("\\", "/"))
    command_paths = sorted(p.replace("\\", "/") for p in glob.glob(".claude/commands/*.md"))
    if not agent_paths:
        print("No agents found under .claude/agents/.")
        return 2

    failures: list[str] = []
    # The roster file and the agent files must agree, or the gates and the agents
    # disagree about who exists. Every agent has a file, switched on or not: a
    # switched-off agent's file is what it answers with if a dispatch slips through.
    on_disk = {os.path.basename(p)[:-3].upper() for p in agent_paths}
    for name in ROSTER:
        if name not in on_disk:
            failures.append(f"context/roster-agents.json lists {name} but "
                            f".claude/agents/{name.lower()}.md does not exist")
    for name in sorted(on_disk - set(ROSTER)):
        failures.append(f".claude/agents/{name.lower()}.md is not in context/roster-agents.json")
    agents = check_parses(agent_paths, failures)
    try:
        failures += check_roster_files(agents, team.load(ROOT))
    except team.TeamUnreadable as exc:
        failures.append(f"the team cannot be read, so no switched-off agent was checked: {exc}")
    skills = check_parses(skill_paths, failures)
    # Skills carry no `tools:` of their own, so both contract checks read them
    # against the tools their owning agent holds. Before this they were parsed
    # and then dropped, and 36 of 54 files were reported OK without ever being
    # checked.
    holders, unattributed = resolve_tool_holders(agents, skills, agent_paths, failures)
    check_tool_contracts(holders, failures)
    check_mcp_contracts(holders, failures)
    check_referenced_scripts(agent_paths + skill_paths + command_paths, failures)
    for path in command_paths:
        _data, _body, error = load_frontmatter(path)
        if error:
            failures.append(f"{path}: {error}")

    # Printed on both paths. A skill nobody owns is checked against nobody's
    # tools, and the whole point of this exercise was that a silent blind spot
    # reads exactly like a pass.
    if unattributed:
        print(
            f"NOTE -- {len(unattributed)} skill(s) resolve to no agent, so no tool "
            f"contract was applied to them:"
        )
        for path in sorted(unattributed):
            print(f"  {path}")
        print()

    checked = len(agent_paths) + len(skill_paths) + len(command_paths)
    if failures:
        print(f"FAIL -- {len(failures)} issue(s) across {checked} files:\n")
        for line in failures:
            print(f"  {line}")
        return 1

    print(f"OK -- {checked} files ({len(agent_paths)} agents, {len(skill_paths)} skills, "
          f"{len(command_paths)} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
