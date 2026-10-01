"""Read a running 1:1 Doc into a flat, section-mapped structure. Read only, always.

NEW in this repo. What the live Docs actually look like was established by a
read-only inspection on 2026-10-01 (plan, "RESOLVED 2026-10-01"), and this parser
is built to THAT, not to a guess:

  TABS. A Doc has a live working tab ("RUNNING AGENDA"), a "Template" tab and
  others. Every read uses includeTabsContent and walks tabs[]; the legacy top-level
  `body` is only the first tab and is never relied on.

  SECTIONS ARE LABELS, NOT HEADINGS. The only heading is "RUNNING AGENDA:",
  repeated once per meeting; a meeting BLOCK runs from one to the next. Inside a
  block the agenda sections are bold numbered list items ("Wins + Challenges from
  the week (personal + professional)", "Follow-Ups: Updates + Action Items",
  "Feedback", "Strategic Priorities") and plain labels ("Top Focuses", "<Name>
  Notes"). So a section is found by its LABEL TEXT from the Doc's section map
  (docs.section_map_json), never by heading level. A logical section the map names
  but this Doc does not contain is UNMAPPED, and scripts/docs_edit.py refuses to
  write into an unmapped section rather than guessing a place.

  OPEN ACTIONS ARE A TABLE: a title row "Action Items", a header row "Assignee |
  Title | Date | Status", then one row per action. Date cells hold SMART CHIPS,
  which arrive as dateElement / person / richLink paragraph elements, not as
  textRun. Reading only textRun would see an empty Date cell. A chip the API does
  not expose shows up as the U+E907 placeholder; it is recorded as an unknown chip,
  and a Status cell holding one is classified ambiguous, never done.

  COMPLETION = THE STATUS CELL. The live Docs have no strikethrough and no
  checkboxes. Strikethrough is still read, as a secondary signal for checklist
  Docs (see docs/OPEN-QUESTIONS.md for what the checkbox experiment showed).

  revisionId IS RETURNED ONLY TO EDITORS. It is recorded when present and its
  absence is reported (editable = False). A read never needs it; a write does, and
  docs_edit.py refuses loudly without it.

Indices are UTF-16 code units, as the API counts them.

Usage:
    python scripts/docs_read.py --doc <id>                    summary, map from the register
    python scripts/docs_read.py --doc <id> --map-file m.json  summary, explicit map
    python scripts/docs_read.py --doc <id> --dump             full parsed JSON
    python scripts/docs_read.py --doc <id> --checkbox-probe   every list item's list properties
    python scripts/docs_read.py --doc <id> --save-raw PATH    the raw API response, for evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REF_TOKEN = re.compile(r"\[([ATQ]-\d{4})\]")
CHIP_PLACEHOLDER = chr(0xE907)
CHECK_MARKS = (chr(0x2713), chr(0x2714), chr(0x2611))
NUMBERED_GLYPHS = ("DECIMAL", "ZERO_DECIMAL", "UPPER_ALPHA", "ALPHA", "UPPER_ROMAN", "ROMAN")


class DocReadError(RuntimeError):
    """The Doc could not be read. `status` is the HTTP status when there was one."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def u16(text: str) -> int:
    """Length in UTF-16 code units: the unit every Docs API index is counted in."""
    return len(text.encode("utf-16-le")) // 2


def norm(text: str) -> str:
    """Comparison form of a label: no chips, single spaces, case-folded, no trailing colon."""
    text = (text or "").replace(CHIP_PLACEHOLDER, " ")
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text.rstrip(":").strip()


def strip_ref(text: str) -> str:
    return re.sub(r"\s*" + REF_TOKEN.pattern, "", text or "").strip()


def text_hash(text: str) -> str:
    """Third-tier identity of a placed line: its normalised text without the ref token."""
    return hashlib.sha256(norm(strip_ref(text)).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

def docs_service():
    import google_creds  # noqa: PLC0415

    return google_creds.service("docs", "v1", [google_creds.DOCUMENTS])


def fetch(service, doc_id: str) -> dict:
    """documents.get with every tab's content. Raises DocReadError with the HTTP status."""
    from googleapiclient.errors import HttpError  # noqa: PLC0415

    try:
        return service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    except HttpError as exc:
        status = int(getattr(exc.resp, "status", 0) or 0)
        meaning = {404: "not found (deleted, or the id is wrong)",
                   403: "forbidden (this account cannot open it)"}.get(status, "refused")
        raise DocReadError(f"documents.get {doc_id}: HTTP {status}, {meaning}", status) from exc
    except OSError as exc:
        raise DocReadError(f"documents.get {doc_id}: network error {exc}") from exc


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def _element(el: dict) -> tuple[str, dict | None, dict]:
    """(display text, chip or None, text style) for one paragraph element."""
    if "textRun" in el:
        run = el["textRun"]
        content = run.get("content", "")
        chip = {"type": "unknown", "start": el.get("startIndex")} if CHIP_PLACEHOLDER in content else None
        return content, chip, run.get("textStyle") or {}
    if "dateElement" in el:
        props = el["dateElement"].get("dateElementProperties") or {}
        shown = props.get("displayText") or (props.get("timestamp") or "")[:10]
        return shown, {"type": "date", "timestamp": props.get("timestamp"), "display": props.get("displayText"),
                       "time_zone": props.get("timeZoneId"), "start": el.get("startIndex")}, \
            el["dateElement"].get("textStyle") or {}
    if "person" in el:
        props = el["person"].get("personProperties") or {}
        return props.get("name") or props.get("email") or "", \
            {"type": "person", "email": props.get("email"), "name": props.get("name"),
             "start": el.get("startIndex")}, el["person"].get("textStyle") or {}
    if "richLink" in el:
        props = el["richLink"].get("richLinkProperties") or {}
        return props.get("title") or props.get("uri") or "", \
            {"type": "richLink", "uri": props.get("uri"), "title": props.get("title"),
             "start": el.get("startIndex")}, el["richLink"].get("textStyle") or {}
    return "", None, {}


def _paragraph(block: dict, lists: dict, in_table: bool) -> dict:
    para = block["paragraph"]
    pieces, chips, styled = [], [], []
    for el in para.get("elements") or []:
        text, chip, style = _element(el)
        pieces.append(text)
        if chip:
            chips.append(chip)
        visible = text.replace("\n", "")
        if visible.strip():
            styled.append(style)
    text = "".join(pieces)
    if text.endswith("\n"):
        text = text[:-1]
    bullet = para.get("bullet")
    glyph = None
    if bullet:
        level = int(bullet.get("nestingLevel") or 0)
        levels = (((lists.get(bullet.get("listId")) or {}).get("listProperties") or {}).get("nestingLevels") or [])
        glyph = levels[level] if level < len(levels) else None
        bullet = {"list_id": bullet.get("listId"), "level": level}
    style = (para.get("paragraphStyle") or {}).get("namedStyleType") or "NORMAL_TEXT"
    return {
        "kind": "paragraph", "start": block.get("startIndex", 0), "end": block.get("endIndex", 0),
        "text": text, "style": style, "bullet": bullet,
        "numbered": bool(glyph and glyph.get("glyphType") in NUMBERED_GLYPHS),
        "glyph": glyph,
        "bold": bool(styled) and all(s.get("bold") for s in styled),
        "struck": bool(styled) and all(s.get("strikethrough") for s in styled),
        "any_struck": any(s.get("strikethrough") for s in styled),
        "chips": chips, "in_table": in_table,
    }


def _table(block: dict, lists: dict) -> dict:
    rows = []
    for row in block["table"].get("tableRows") or []:
        cells = []
        for cell in row.get("tableCells") or []:
            paras = [_paragraph(c, lists, True) for c in cell.get("content") or [] if "paragraph" in c]
            cells.append({
                "start": cell.get("startIndex", 0), "end": cell.get("endIndex", 0),
                "text": "\n".join(p["text"] for p in paras).strip(),
                "chips": [chip for p in paras for chip in p["chips"]],
                "struck": bool(paras) and all(p["struck"] for p in paras if p["text"].strip()),
                "paragraphs": paras,
            })
        rows.append({"start": row.get("startIndex", 0), "end": row.get("endIndex", 0), "cells": cells})
    return {"kind": "table", "start": block.get("startIndex", 0), "end": block.get("endIndex", 0),
            "rows": rows, "columns": int(block["table"].get("columns") or 0)}


def _tab_items(content: list, lists: dict) -> list[dict]:
    items = []
    for block in content or []:
        if "paragraph" in block:
            items.append(_paragraph(block, lists, False))
        elif "table" in block:
            items.append(_table(block, lists))
    return items


def flatten_tabs(document: dict) -> list[dict]:
    """Every tab, depth first, with its parsed items and named ranges."""
    out = []

    def walk(tabs: list, depth: int) -> None:
        for tab in tabs or []:
            props = tab.get("tabProperties") or {}
            doc_tab = tab.get("documentTab") or {}
            lists = doc_tab.get("lists") or {}
            out.append({
                "tab_id": props.get("tabId"), "title": props.get("title") or "", "depth": depth,
                "items": _tab_items((doc_tab.get("body") or {}).get("content"), lists),
                "named_ranges": doc_tab.get("namedRanges") or {},
            })
            walk(tab.get("childTabs"), depth + 1)

    if document.get("tabs"):
        walk(document["tabs"], 0)
    else:
        out.append({"tab_id": None, "title": "", "depth": 0,
                    "items": _tab_items((document.get("body") or {}).get("content"), document.get("lists") or {}),
                    "named_ranges": document.get("namedRanges") or {}})
    return out


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------

def _is_anchor(item: dict, label: str) -> bool:
    """A paragraph IS this label: exact text, or a bold paragraph that starts with it."""
    if item["kind"] != "paragraph" or item["in_table"]:
        return False
    if item["bullet"] and item["bullet"]["level"] > 0:
        return False
    text = norm(item["text"])
    if not text:
        return False
    return text == label or (item["bold"] and text.startswith(label))


def _is_boundary(item: dict, labels: list[str]) -> bool:
    """Where a section ends: a heading, any known label, or a bold numbered agenda item."""
    if item["kind"] != "paragraph" or item["in_table"]:
        return False
    if item["style"].startswith("HEADING") or item["style"] in ("TITLE", "SUBTITLE"):
        return True
    if any(_is_anchor(item, label) for label in labels):
        return True
    return bool(item["bold"] and item["numbered"] and item["bullet"] and item["bullet"]["level"] == 0
                and norm(item["text"]))


def _header_row(table: dict, header: list[str]) -> int | None:
    want = [norm(h) for h in header]
    for index, row in enumerate(table["rows"]):
        if [norm(c["text"]) for c in row["cells"]][:len(want)] == want:
            return index
    return None


def parse(document: dict, section_map: dict | None) -> dict:
    """The Doc as items, blocks and logical sections. Unmapped sections are listed, not guessed."""
    section_map = section_map or {}
    tabs = flatten_tabs(document)
    parsed = {
        "doc_id": document.get("documentId"), "title": document.get("title"),
        "revision_id": document.get("revisionId") or None,
        "editable": bool(document.get("revisionId")),
        "tabs": tabs, "target_tab": None, "blocks": [], "newest_block": None,
        "sections": {}, "unmapped": [], "warnings": [],
    }
    want_title = norm(section_map.get("tab_title") or "")
    target = None
    if want_title:
        target = next((i for i, t in enumerate(tabs) if norm(t["title"]) == want_title), None)
        if target is None:
            parsed["warnings"].append(f"no tab titled {section_map.get('tab_title')!r}")
    elif tabs:
        target = 0
    parsed["target_tab"] = target
    if target is None:
        parsed["unmapped"] = sorted((section_map.get("sections") or {}).keys())
        return parsed

    items = tabs[target]["items"]
    heading = norm(section_map.get("block_heading") or "")
    if heading:
        starts = [i for i, it in enumerate(items) if it["kind"] == "paragraph"
                  and it["style"].startswith("HEADING") and norm(it["text"]) == heading]
    else:
        starts = [0] if items else []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(items)
        parsed["blocks"].append({"first_item": start, "end_item": end,
                                 "start": items[start]["start"], "end": items[end - 1]["end"]})
    if not parsed["blocks"]:
        parsed["warnings"].append(f"no meeting block heading {section_map.get('block_heading')!r} in the tab")
        parsed["unmapped"] = sorted((section_map.get("sections") or {}).keys())
        return parsed
    newest = 0 if (section_map.get("block_order") or "newest_first") == "newest_first" else len(parsed["blocks"]) - 1
    parsed["newest_block"] = newest
    block = parsed["blocks"][newest]

    specs = section_map.get("sections") or {}
    labels = [norm(x) for x in (section_map.get("labels") or [])]
    labels += [norm(spec.get("anchor") or "") for spec in specs.values() if spec.get("kind") != "table"]
    labels = [label for label in dict.fromkeys(labels) if label]

    for key, spec in specs.items():
        kind = spec.get("kind") or "list"
        if kind == "table":
            found = None
            for i in range(block["first_item"], block["end_item"]):
                it = items[i]
                if it["kind"] != "table" or not it["rows"]:
                    continue
                first = norm(it["rows"][0]["cells"][0]["text"]) if it["rows"][0]["cells"] else ""
                header = _header_row(it, spec.get("header") or [])
                if first == norm(spec.get("anchor") or "") or header is not None:
                    found = (i, header)
                    break
            if found is None or found[1] is None:
                parsed["unmapped"].append(key)
                continue
            parsed["sections"][key] = {"kind": "table", "anchor": spec.get("anchor"), "table_item": found[0],
                                       "header_row": found[1], "columns": spec.get("columns") or {}}
            continue
        label = norm(spec.get("anchor") or "")
        anchor = next((i for i in range(block["first_item"], block["end_item"]) if _is_anchor(items[i], label)), None)
        if anchor is None:
            parsed["unmapped"].append(key)
            continue
        members = []
        for i in range(anchor + 1, block["end_item"]):
            if _is_boundary(items[i], labels):
                break
            if items[i]["kind"] == "paragraph" and items[i]["text"].strip():
                members.append(i)
        parsed["sections"][key] = {"kind": kind, "anchor": spec.get("anchor"), "anchor_item": anchor,
                                   "items": members}
    return parsed


# ---------------------------------------------------------------------------
# items and completion
# ---------------------------------------------------------------------------

DONE_WORD = re.compile(r"^(done|complete|completed|finished|closed|x|\[x\])\b", re.I)
DONE_ANYWHERE = re.compile(r"\b(done|complete|completed|finished)\b", re.I)
HEDGE = re.compile(r"\b(not|isn'?t|almost|nearly|partly|partially|mostly|half|pending|wip)\b", re.I)
TEXT_DONE = re.compile(r"(^\s*\[x\]|\(\s*done\b|\bdone\s*$|\(\s*complete\b|\bcomplete\s*$)", re.I)


def classify_status(text: str, chips: list | None = None) -> str:
    """A Status cell or a checklist line: open, checked, or ambiguous. Never guesses done."""
    raw = (text or "").replace(CHIP_PLACEHOLDER, " ").strip()
    if any((chip or {}).get("type") == "unknown" for chip in chips or []):
        return "ambiguous"
    if not raw:
        return "open"
    if raw in CHECK_MARKS:
        return "checked"
    if HEDGE.search(raw) and DONE_ANYWHERE.search(raw):
        return "ambiguous"
    if DONE_WORD.match(raw):
        return "checked"
    if DONE_ANYWHERE.search(raw):
        return "ambiguous"
    return "open"


def _ranges(parsed: dict, name: str) -> list[dict]:
    tab = parsed["tabs"][parsed["target_tab"]] if parsed["target_tab"] is not None else None
    if not tab or not name:
        return []
    entry = tab["named_ranges"].get(name) or {}
    return [r for nr in entry.get("namedRanges") or [] for r in nr.get("ranges") or []]


def _section_rows(parsed: dict, key: str) -> list[tuple[int, dict]]:
    section = parsed["sections"].get(key) or {}
    if section.get("kind") != "table":
        return []
    table = parsed["tabs"][parsed["target_tab"]]["items"][section["table_item"]]
    return [(i, row) for i, row in enumerate(table["rows"]) if i > section["header_row"]]


def all_table_rows(parsed: dict) -> list[dict]:
    """Every row of every action-shaped table in the target tab, across all blocks."""
    if parsed["target_tab"] is None:
        return []
    rows = []
    for item in parsed["tabs"][parsed["target_tab"]]["items"]:
        if item["kind"] == "table":
            rows.extend(item["rows"])
    return rows


def locate(parsed: dict, *, item_kind: str, item_ref: str, named_range: str | None,
           stored_hash: str | None, columns: dict | None) -> dict:
    """Find a placed register item in the Doc and say what state it is in.

    Three signals, strongest first: the named range ea:<kind>:<ref>, the visible ref
    token [A-0007], and the text hash recorded at placement. A row found by none of
    them is `missing`, which is reported and NEVER treated as cancelled.
    """
    if parsed["target_tab"] is None:
        return {"state": "missing", "via": None, "reason": "target tab not found"}
    items = parsed["tabs"][parsed["target_tab"]]["items"]
    cols = {"assignee": 0, "title": 1, "date": 2, "status": 3, **(columns or {})}
    rows = all_table_rows(parsed)
    paragraphs = [it for it in items if it["kind"] == "paragraph"]

    def describe_row(row: dict, via: str) -> dict:
        cells = row["cells"]
        status_cell = cells[cols["status"]] if cols["status"] < len(cells) else {"text": "", "chips": []}
        title_cell = cells[cols["title"]] if cols["title"] < len(cells) else {"text": "", "struck": False}
        state = classify_status(status_cell["text"], status_cell.get("chips"))
        if state == "open" and title_cell.get("struck"):
            state = "checked"
        date_cell = cells[cols["date"]] if cols["date"] < len(cells) else {"chips": []}
        dates = [c for c in date_cell.get("chips") or [] if c.get("type") == "date"]
        return {"state": state, "via": via, "shape": "row", "text": title_cell["text"],
                "status_text": status_cell["text"], "row_start": row["start"], "row_end": row["end"],
                "date_chip": dates[0] if dates else None,
                "date_text": date_cell.get("text", "") if isinstance(date_cell, dict) else ""}

    def describe_para(para: dict, via: str) -> dict:
        state = "checked" if para["struck"] else classify_status_line(para["text"])
        return {"state": state, "via": via, "shape": "paragraph", "text": para["text"],
                "status_text": "", "para_start": para["start"], "para_end": para["end"],
                "checkbox": is_checkbox(para)}

    for rng in _ranges(parsed, named_range or ""):
        start = int(rng.get("startIndex", -1))
        for row in rows:
            if row["start"] <= start < row["end"]:
                return describe_row(row, "named_range")
        for para in paragraphs:
            if para["start"] <= start < para["end"]:
                return describe_para(para, "named_range")

    token = f"[{item_ref}]"
    for row in rows:
        if any(token in c["text"] for c in row["cells"]):
            return describe_row(row, "ref_token")
    for para in paragraphs:
        if token in para["text"]:
            return describe_para(para, "ref_token")

    if stored_hash:
        for row in rows:
            cells = row["cells"]
            if cols["title"] < len(cells) and text_hash(cells[cols["title"]]["text"]) == stored_hash:
                return describe_row(row, "text_hash")
        for para in paragraphs:
            if text_hash(para["text"]) == stored_hash:
                return describe_para(para, "text_hash")
    return {"state": "missing", "via": None, "reason": "no named range, ref token or text match"}


def is_checkbox(para: dict) -> bool:
    """A BULLET_CHECKBOX list item, as the API actually reports one (observed 2026-10-01):
    glyphType GLYPH_TYPE_UNSPECIFIED, glyphFormat "%0", no glyphSymbol. There is NO
    field for checked or unchecked, and no request that sets it."""
    glyph = para.get("glyph") or {}
    return bool(para.get("bullet")) and glyph.get("glyphType") == "GLYPH_TYPE_UNSPECIFIED" \
        and not glyph.get("glyphSymbol")


def classify_status_line(text: str) -> str:
    """A checklist or bullet line: done markers at either end, else open."""
    if TEXT_DONE.search(text or ""):
        stripped = strip_ref(text)
        return "ambiguous" if HEDGE.search(stripped) else "checked"
    return "open"


# ---------------------------------------------------------------------------
# snapshots and diffs
# ---------------------------------------------------------------------------

def lines_of(parsed: dict) -> list[str]:
    """The target tab as comparable lines, for a before/after diff."""
    if parsed["target_tab"] is None:
        return []
    out = []
    for item in parsed["tabs"][parsed["target_tab"]]["items"]:
        if item["kind"] == "paragraph":
            out.append(f"P|{item['style']}|{item['text']}")
        else:
            for row in item["rows"]:
                out.append("R|" + " | ".join(c["text"] + "".join(
                    f"<{ch.get('type')}:{(ch.get('timestamp') or ch.get('email') or ch.get('uri') or '')[:10]}>"
                    for ch in c["chips"]) for c in row["cells"]))
    return out


def snapshot(parsed: dict) -> tuple[str, str]:
    """(canonical JSON, sha256) of the parsed Doc, for doc_snapshots."""
    body = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def revision_key(parsed: dict) -> str:
    """The revision a snapshot or replay guard is keyed on. Editors get revisionId;
    a view-only token gets a content hash, labelled so nobody mistakes it for one."""
    if parsed["revision_id"]:
        return parsed["revision_id"]
    return "content:" + snapshot(parsed)[1][:24]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _map_for(doc_id: str, map_file: str | None) -> dict | None:
    if map_file:
        return json.loads(Path(map_file).read_bytes().decode("utf-8"))
    import ea_db  # noqa: PLC0415

    if not ea_db.DB_PATH.exists():
        return None
    conn = ea_db.connect(read_only=True)
    try:
        row = conn.execute("SELECT section_map_json FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["section_map_json"]) if row and row["section_map_json"] else None


def summary(parsed: dict) -> str:
    lines = [f"{parsed['title']}  ({parsed['doc_id']})",
             f"  revision: {parsed['revision_id'] or 'NOT RETURNED (this account cannot edit this Doc)'}",
             "  tabs: " + ", ".join(f"{t['title']!r}" for t in parsed["tabs"])]
    if parsed["target_tab"] is not None:
        tab = parsed["tabs"][parsed["target_tab"]]
        lines.append(f"  working tab: {tab['title']!r} ({tab['tab_id']}), {len(tab['items'])} items, "
                     f"{len(parsed['blocks'])} meeting block(s), newest = block {parsed['newest_block']}")
        for key, section in parsed["sections"].items():
            if section["kind"] == "table":
                table = tab["items"][section["table_item"]]
                lines.append(f"  {key:15} table under {section['anchor']!r}: {len(table['rows']) - section['header_row'] - 1} row(s)")
            else:
                texts = [tab["items"][i]["text"][:50] for i in section["items"]]
                lines.append(f"  {key:15} {section['anchor']!r}: {len(texts)} item(s) {texts}")
    for key in parsed["unmapped"]:
        lines.append(f"  {key:15} UNMAPPED (label not found; writes into it will refuse)")
    for warning in parsed["warnings"]:
        lines.append(f"  WARNING: {warning}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--doc", required=True)
    parser.add_argument("--map-file")
    parser.add_argument("--dump", action="store_true")
    parser.add_argument("--checkbox-probe", action="store_true")
    parser.add_argument("--save-raw")
    args = parser.parse_args()

    try:
        document = fetch(docs_service(), args.doc)
    except DocReadError as exc:
        print(f"READ FAILED: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        # swallow: converted to a named failure; a read script that crashes with a
        # traceback reads to Taylor as "the system is broken", which it may not be.
        print(f"READ FAILED: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 3

    if args.save_raw:
        Path(args.save_raw).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_raw).write_text(json.dumps(document, indent=1, ensure_ascii=False), encoding="utf-8")
    parsed = parse(document, _map_for(args.doc, args.map_file))

    if args.checkbox_probe:
        for tab in parsed["tabs"]:
            for item in tab["items"]:
                if item["kind"] == "paragraph" and item["bullet"]:
                    print(json.dumps({"tab": tab["title"], "text": item["text"][:60], "level": item["bullet"]["level"],
                                      "struck": item["struck"], "glyph": item["glyph"]}, ensure_ascii=False))
        return 0
    if args.dump:
        sys.stdout.buffer.write((json.dumps(parsed, indent=1, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
        return 0
    sys.stdout.buffer.write((summary(parsed) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
