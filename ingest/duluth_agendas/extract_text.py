#!/usr/bin/env python3
"""
Extract text from the crawled Duluth meeting documents.

Also detects scanned pages. A minutes PDF that was printed, signed, and
re-scanned yields zero extractable text -- if that goes unflagged it silently
looks like "this meeting decided nothing", which is far worse than a visible gap.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

# A damaged font encoding makes pymupdf emit control characters that look like
# nothing in a PDF reader and abort a Postgres load on the first U+0000.
RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

HERE = Path(__file__).parent
IN = HERE / "duluth_meeting_docs.jsonl"
OUT = HERE / "duluth_meeting_text.jsonl"

# Duluth land-use case numbers seen in the corpus, e.g. RZ-2024-03, V-2025-11,
# SUP-2023-02. Kept deliberately loose; validated by eye below.
RE_CASE = re.compile(
    r"\b((?:RZ|REZ|V|VAR|SUP|SUE|CU|ANX|ANNEX|TA|LDP|SP|PP|FP|CE)[- ]?\d{2,4}[- ]?\d{1,3})\b",
    re.I)
RE_MEETING_DATE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d\d)",
    re.I)
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def main() -> int:
    docs = [json.loads(l) for l in IN.open()]
    out = []
    scanned = partial = 0

    for i, d in enumerate(docs, 1):
        p = Path(d.get("local_path", ""))
        rec = dict(d)
        if not p.exists():
            rec.update(pages=0, text="", text_chars=0, scanned_pages=0, quality="missing")
            out.append(rec)
            continue
        try:
            doc = pymupdf.open(p)
            pages, blank = [], 0
            for pg in doc:
                t = pg.get_text()
                if len(t.strip()) < 20:
                    blank += 1
                pages.append(t)
            text = "\n".join(pages)
            text = RE_CONTROL.sub(" ", text)   # before whitespace collapsing
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            npages = doc.page_count

            if npages and blank == npages:
                quality = "scanned_no_text"; scanned += 1
            elif npages and blank / npages > 0.35:
                quality = "partially_scanned"; partial += 1
            else:
                quality = "text_ok"

            # Recover a meeting date from the document body when the filename had none.
            body_date = None
            m = RE_MEETING_DATE.search(text[:4000])
            if m:
                mo = MONTHS.get(m.group(1).lower())
                if mo:
                    body_date = f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"

            cases = sorted({re.sub(r"\s+", "-", c.upper()) for c in RE_CASE.findall(text)})

            rec.update(
                pages=npages, text=text, text_chars=len(text),
                scanned_pages=blank, quality=quality,
                meeting_date_from_body=body_date,
                meeting_date_final=d.get("meeting_date") or body_date,
                case_refs=cases[:60], n_case_refs=len(cases),
            )
        except Exception as e:
            rec.update(pages=0, text="", text_chars=0, quality=f"error:{type(e).__name__}")
        out.append(rec)
        if i % 50 == 0:
            print(f"  {i}/{len(docs)}")

    with OUT.open("w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    import collections
    print("\nquality:", dict(collections.Counter(r["quality"] for r in out)))
    print("by type :", dict(collections.Counter(r["doc_type"] for r in out)))
    dated = sum(1 for r in out if r.get("meeting_date_final"))
    recovered = sum(1 for r in out if not r.get("meeting_date") and r.get("meeting_date_from_body"))
    print(f"dated   : {dated}/{len(out)}  (recovered from body: {recovered})")
    print(f"pages   : {sum(r.get('pages',0) for r in out):,}")
    print(f"chars   : {sum(r.get('text_chars',0) for r in out):,}")
    print(f"docs with case refs: {sum(1 for r in out if r.get('n_case_refs'))}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
