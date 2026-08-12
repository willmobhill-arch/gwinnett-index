#!/usr/bin/env python3
"""
OCR the scanned Duluth meeting documents.

Duluth's minutes are printed, signed by the clerk, and re-scanned, so 57-69% of
minutes across the three bodies carry no extractable text at all. Agendas and
packets say what was PROPOSED; minutes say what was DECIDED and under what
conditions. Without OCR the corpus can tell you a rezoning was heard but not
whether it passed -- which is worse than useless for a land-use index.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
IN = HERE / "duluth_meeting_text.jsonl"
OUT = HERE / "duluth_meeting_text_ocr.jsonl"
DPI = 220          # enough for clerk-signed minutes; higher just costs time
MAX_PAGES = 60     # the 382-page outlier is a scanned packet, not minutes


def ocr_pdf(path: Path, max_pages: int = MAX_PAGES) -> tuple[str, int]:
    doc = pymupdf.open(path)
    n = min(doc.page_count, max_pages)
    chunks = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            pix = doc[i].get_pixmap(dpi=DPI)
            img = Path(td) / f"p{i}.png"
            pix.save(img)
            try:
                r = subprocess.run(
                    ["tesseract", str(img), "stdout", "--psm", "6", "-l", "eng"],
                    capture_output=True, text=True, timeout=120)
                chunks.append(r.stdout)
            except subprocess.TimeoutExpired:
                chunks.append("")
            img.unlink(missing_ok=True)
    txt = "\n".join(chunks)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt, n


def main() -> int:
    rows = [json.loads(l) for l in IN.open()]
    todo = [r for r in rows
            if r["quality"] in ("scanned_no_text", "partially_scanned")
            and Path(r.get("local_path", "")).exists()]
    print(f"OCR queue: {len(todo)} documents")

    done = 0
    for r in rows:
        if r not in todo:
            continue
        p = Path(r["local_path"])
        try:
            txt, n = ocr_pdf(p)
        except Exception as e:
            r["ocr_status"] = f"error:{type(e).__name__}"
            continue
        r["ocr_pages"] = n
        r["ocr_chars"] = len(txt)
        r["ocr_status"] = "ok" if len(txt) > 200 else "low_yield"
        r["ocr_truncated"] = r.get("pages", 0) > n
        # OCR text is a RECONSTRUCTION, never the authoritative record. Keep it in
        # its own field so nothing downstream can mistake it for publisher text.
        r["text_ocr"] = txt
        r["text_source"] = "ocr"
        if not r.get("text"):
            r["text_chars"] = len(txt)
        done += 1
        if done % 10 == 0:
            print(f"  {done}/{len(todo)}")

    for r in rows:
        r.setdefault("text_source", "embedded" if r.get("text") else "none")

    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    import collections
    print("\nocr_status:", dict(collections.Counter(
        r.get("ocr_status") for r in rows if r.get("ocr_status"))))
    got = sum(1 for r in rows if r.get("ocr_chars", 0) > 200)
    print(f"documents recovered by OCR: {got}")
    print(f"OCR chars added: {sum(r.get('ocr_chars',0) for r in rows):,}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
