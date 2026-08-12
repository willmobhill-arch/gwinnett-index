#!/usr/bin/env python3
"""
Extract the City of Duluth Unified Development Code into structured sections.

The UDC is published only as a single 426-page PDF -- there is no HTML version,
no Municode entry (Part III of Duluth's Municode is a stub that links out to this
file), and no API. Structuring it is the reason this project exists.

The PDF is digital-born (Acrobat PDFMaker from Word) and carries a 923-entry
bookmark tree, so section hierarchy comes from the document itself rather than
from regex heading detection. Bookmark destinations include y-coordinates, which
lets us split several subsections that share a single page.

Output: JSONL, one object per section, with citation, hierarchy, body text,
extracted tables, and page range.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

PDF = Path(__file__).parent / "udc.pdf"
OUT = Path(__file__).parent / "udc_sections.jsonl"

SOURCE_URL = "https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf"
ADOPTED = "2025-09-08"
AMENDED_THROUGH = "2026-07-13"

# Section numbers are 3 digits in Articles 1-9 and FOUR digits from Article 10 on
# ("1004.01"), so every pattern has to accept \d{3,4}. Matching only \d{3} silently
# dropped 298 subsections -- the whole of Articles 10 through 14.
RE_SUBSEC = re.compile(r"^(?:Section\s+)?(\d{3,4}\.\d{2})\.?\s+(.*)$", re.I)
RE_SECTION = re.compile(r"^Section\s+(\d{3,4})\.?\s+(.*)$", re.I)
RE_TABLE = re.compile(r"^(TABLE\s+[\w\-]+)\s*[:.]?\s*(.*)$", re.I)
RE_ARTICLE = re.compile(r"^Article\s+([A-Za-z]+)\.?\s*(.*)$", re.I)
RE_DIVISION = re.compile(r"^Division\s+([IVXL]+)\.?\s*(.*)$", re.I)
# Bookmark titles that are wrapped continuations of the previous heading, or
# inline notes -- not headings at all.
RE_FRAGMENT = re.compile(r"^(\(|[a-z]|and\s|See\s+Article)", )

ORDINALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
}


def classify(title: str):
    """-> (kind, identifier, clean_title)"""
    t = re.sub(r"\s+", " ", title.strip())
    if RE_FRAGMENT.match(t):
        return "fragment", None, t
    if m := RE_TABLE.match(t):
        ident = re.sub(r"\s+", " ", m.group(1)).title().replace("Table", "Table")
        return "table", ident, m.group(2).strip()
    if m := RE_SUBSEC.match(t):
        return "subsection", m.group(1), m.group(2).strip().rstrip(".")
    if m := RE_SECTION.match(t):
        return "section", m.group(1), m.group(2).strip().rstrip(".")
    if m := RE_DIVISION.match(t):
        return "division", m.group(1).upper(), m.group(2).strip().rstrip(".")
    if m := RE_ARTICLE.match(t):
        word = m.group(1).lower()
        return "article", str(ORDINALS.get(word, word)), m.group(2).strip().rstrip(".")
    # Article 14 splits its glossary into single-letter groups.
    if re.fullmatch(r"[A-Z]", t):
        return "definitions_group", t, f"Definitions — {t}"
    # Appendix exhibits are ALL-CAPS form titles.
    if t.isupper() and len(t) > 8:
        return "form", None, t.title()
    return "other", None, t


def main() -> int:
    doc = pymupdf.open(PDF)
    toc = doc.get_toc(simple=False)

    # Anchor every bookmark to (page_index, y). Bookmark y is top-left origin.
    anchors = []
    for level, title, _page1, dest in toc:
        pno = dest.get("page", 0)
        pt = dest.get("to")
        y = float(pt.y) if pt is not None else 0.0
        anchors.append({"level": level, "title": title.strip(), "page": pno, "y": y})

    anchors.sort(key=lambda a: (a["page"], a["y"]))

    # Cache text blocks per page once.
    page_blocks: dict[int, list] = {}

    def blocks(pno: int):
        if pno not in page_blocks:
            b = doc[pno].get_text("blocks")           # (x0,y0,x1,y1,text,bno,btype)
            b = [x for x in b if x[6] == 0 and x[4].strip()]
            b.sort(key=lambda x: (round(x[1], 1), x[0]))
            page_blocks[pno] = b
        return page_blocks[pno]

    def text_between(start, end) -> tuple[str, int, int]:
        sp, sy = start["page"], start["y"]
        ep, ey = (end["page"], end["y"]) if end else (doc.page_count - 1, 1e9)
        out = []
        for pno in range(sp, min(ep, doc.page_count - 1) + 1):
            for b in blocks(pno):
                y0 = b[1]
                if pno == sp and y0 < sy - 2:
                    continue
                if pno == ep and y0 >= ey - 2:
                    continue
                out.append(b[4])
        raw = "\n".join(out)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip(), sp, ep

    # Track the article/section a subsection belongs to.
    cur_article = cur_article_title = None
    cur_section = cur_section_title = None
    records = []

    for i, a in enumerate(anchors):
        nxt = anchors[i + 1] if i + 1 < len(anchors) else None
        kind, ident, clean = classify(a["title"])

        if kind == "article" and a["level"] == 1:
            cur_article, cur_article_title = ident, clean
            cur_section = cur_section_title = None
        elif kind == "section":
            cur_section, cur_section_title = ident, clean

        # Skip the front-matter outline ("Organization of the Code" and its children)
        if a["page"] < 30:
            continue

        body, p_from, p_to = text_between(a, nxt)
        if not body:
            continue

        # Strip the heading line itself off the top of the body.
        first_nl = body.find("\n")
        if first_nl > 0 and body[:first_nl].strip().lower().startswith(
            a["title"][:18].strip().lower()[:18]
        ):
            body = body[first_nl + 1:].strip()

        # A fragment is a wrapped continuation of the previous bookmark's heading,
        # not a section of its own -- fold its text into the previous record so no
        # code text is lost, rather than emitting a phantom section.
        if kind == "fragment" and records:
            records[-1]["body"] = (records[-1]["body"] + "\n" + body).strip()
            records[-1]["page_to"] = max(records[-1]["page_to"], p_to + 1)
            records[-1]["char_len"] = len(records[-1]["body"])
            continue

        if kind in ("table",):
            citation = f"Duluth UDC {ident}"
        elif kind in ("subsection", "section"):
            citation = f"Duluth UDC § {ident}"
        elif kind == "article":
            citation = f"Duluth UDC art. {ident}"
        elif kind == "division":
            citation = f"Duluth UDC art. {cur_article} div. {ident}" if cur_article else None
        else:
            citation = None

        records.append({
            "citation": citation,
            "kind": kind,
            "identifier": ident,
            "title": clean,
            "article": cur_article,
            "article_title": cur_article_title,
            "section": cur_section,
            "section_title": cur_section_title,
            "level": a["level"],
            "body": body,
            "page_from": p_from + 1,
            "page_to": p_to + 1,
            "char_len": len(body),
            "source_url": SOURCE_URL,
            "adopted": ADOPTED,
            "amended_through": AMENDED_THROUGH,
        })

    with OUT.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    print(f"pages           : {doc.page_count}")
    print(f"bookmarks       : {len(toc)}")
    print(f"records written : {len(records)}")
    print(f"by kind         : {dict(Counter(r['kind'] for r in records))}")
    print(f"empty bodies    : {sum(1 for r in records if not r['body'])}")
    print(f"total chars     : {sum(r['char_len'] for r in records):,}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
