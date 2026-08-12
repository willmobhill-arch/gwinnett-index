#!/usr/bin/env python3
"""
OCR the scanned Duluth meeting documents.

Duluth's minutes are printed, signed by the clerk, and re-scanned, so 83 of 138
minutes carry no extractable text at all. Agendas and packets say what was
PROPOSED; minutes say what was DECIDED and by what vote. Without OCR the corpus
can tell you a rezoning was heard but not whether it passed, which is worse than
useless for a land-use index. Today only 54 of 109 Duluth cases carry an outcome.

The queue is 91 documents / 714 scanned pages. That is an hour single-threaded and a few
minutes across cores -- it was never the size that stopped this finishing.

WHAT WENT WRONG IN THE FIRST VERSION, because all three are easy to repeat:

1. It required `local_path` on every row and skipped anything without one. No row
   in the published corpus has that field, so the queue came out EMPTY, the script
   printed "OCR queue: 0", wrote an output file identical to its input, and exited
   0. A job that silently succeeds having done nothing is indistinguishable from a
   job that was never run. Inputs are now checked up front and a queue of zero is
   an error, not a result.

2. It OCR'd whole documents and stamped text_source='ocr' on them. Seven of the
   documents are `partially_scanned` PACKETS that already carry real publisher
   text -- one of them 449,287 characters of it. Relabelling that as an OCR
   reconstruction would destroy the ability to quote the parts that ARE quotable,
   which is precisely the distinction this project exists to maintain. We now OCR
   only the pages that lack a text layer, keep the embedded text as it stands, and
   record text_source='mixed' plus the exact page numbers that are reconstructed.

3. MAX_PAGES=60 silently capped every document. Two packets exceed it, and the cap
   would have dropped 417 of the queue's 1,059 total document pages -- 39% of the corpus, 322 of
   them from a single 382-page binder whose 154 scanned pages are exactly the
   signed decision record. There is no cap now; --max-pages exists but defaults to
   unlimited and says loudly what it drops.

Resumable: every finished document is appended to a progress file keyed by sha256,
so an interrupted run picks up where it stopped instead of starting over. That
matters for a job measured in hours on someone's laptop.

Usage:
    python3 ingest/duluth_agendas/ocr_scanned.py --jobs 8
    python3 ingest/duluth_agendas/ocr_scanned.py --pdf-dir ingest/duluth_agendas/raw --limit 5

The PDFs come from crawl_duluth.py, which writes them to ingest/duluth_agendas/raw/
and records local_path on every row, so --pdf-dir is only needed if you moved them.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

HERE = Path(__file__).parent
REPO = HERE.parent.parent
DEFAULT_IN = HERE / "duluth_meeting_text.jsonl"
FALLBACK_IN = REPO / "data" / "duluth_meeting_docs.jsonl"
DEFAULT_OUT = HERE / "duluth_meeting_text_ocr.jsonl"

DPI = 220              # enough for clerk-signed minutes; higher only costs time
MIN_PAGE_CHARS = 40    # below this a page has no usable text layer
SCANNED_QUALITY = ("scanned_no_text", "partially_scanned")


# --------------------------------------------------------------------------
# PDF access is behind these two seams so the pipeline can be tested without
# pymupdf or tesseract installed -- neither is available in CI, and the logic
# that actually went wrong last time was never the OCR itself.
# --------------------------------------------------------------------------

def open_pdf(path: Path):
    import pymupdf
    return pymupdf.open(path)


def page_text(doc, i: int) -> str:
    return doc[i].get_text() or ""


def page_png(doc, i: int, dpi: int = DPI) -> bytes:
    return doc[i].get_pixmap(dpi=dpi).tobytes("png")


# Tesseract parallelises each page with OpenMP, and OpenMP threads BUSY-WAIT at
# barriers by default. Run N tesseract processes on an N-core box and you get N*N
# spinning threads fighting for N cores, which is catastrophically worse than
# linear rather than merely slower: a 2-page document that takes 2.3s on its own
# blew through a 180s per-page timeout with only four workers. Pinning each
# process to one thread and letting the process pool supply the parallelism is
# the documented way to batch tesseract, and it is not a small effect.
TESS_ENV = {**os.environ, "OMP_THREAD_LIMIT": "1"}
PAGE_TIMEOUT = 120


def tesseract(png: bytes) -> str:
    """One page through tesseract. PNG goes in on stdin; no temp file per page."""
    r = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "6", "-l", "eng"],
        input=png, capture_output=True, timeout=PAGE_TIMEOUT, env=TESS_ENV)
    return r.stdout.decode("utf-8", "replace")


def clean(txt: str) -> str:
    txt = re.sub(r"[ \t]+", " ", txt)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


# --------------------------------------------------------------------------

def scanned_page_indexes(doc, count: int) -> list[int]:
    """Which pages have no usable text layer. Per page, not per document."""
    return [i for i in range(count) if len(page_text(doc, i).strip()) < MIN_PAGE_CHARS]


def ocr_document(
    path: Path,
    max_pages: int | None = None,
    *,
    _open=open_pdf, _text=page_text, _png=page_png, _ocr=tesseract,
) -> dict:
    """OCR only the pages of one document that lack a text layer."""
    doc = _open(path)
    count = doc.page_count
    targets = [i for i in range(count) if len(_text(doc, i).strip()) < MIN_PAGE_CHARS]

    dropped: list[int] = []
    if max_pages is not None and len(targets) > max_pages:
        dropped = targets[max_pages:]
        targets = targets[:max_pages]

    parts, failed = [], []
    for i in targets:
        try:
            parts.append(f"[page {i + 1}]\n" + _ocr(_png(doc, i)))
        except Exception:
            # One unreadable page should cost one page, not the whole document.
            # Losing a 12-page binder because page 7 is a scanned map is how a
            # run ends up with 91 errors and nothing to show for an hour.
            failed.append(i + 1)
    txt = clean("\n\n".join(parts))

    embedded = sum(len(_text(doc, i).strip()) for i in range(count) if i not in targets)
    return {
        "pages_total": count,
        "ocr_page_numbers": [i + 1 for i in targets if i + 1 not in failed],
        "ocr_pages_dropped": [i + 1 for i in dropped],
        "ocr_pages_failed": failed,
        "ocr_chars": len(txt),
        "embedded_chars": embedded,
        "text_ocr": txt,
        # A document is only 'ocr' if NONE of it was readable. Any surviving
        # publisher text makes it 'mixed', and the page numbers above say which
        # half is which. Calling a 449k-character packet an OCR reconstruction
        # because 154 of its 382 pages were scanned throws away the quotable part.
        "text_source": "ocr" if embedded == 0 else ("mixed" if txt else "embedded"),
        "ocr_status": "ok" if len(txt) > 200 else ("low_yield" if targets else "nothing_to_do"),
    }


def _worker(job: tuple[str, str, int | None]) -> dict:
    sha, path, max_pages = job
    try:
        out = ocr_document(Path(path), max_pages)
    except Exception as e:              # noqa: BLE001 - reported, never swallowed
        out = {"ocr_status": f"error:{type(e).__name__}", "ocr_error": str(e)[:300]}
    out["sha256"] = sha
    return out


def crawl_filename(row: dict) -> str | None:
    """The name crawl_duluth.py actually writes.

    Not the source filename and not the sha256: it is
    <body_slug>_<sha1(url)[:16]>.pdf, because the published filenames collide and
    contain spaces. Reproduced here rather than imported so this script can run
    against a directory of PDFs without the crawler's state.
    """
    url, slug = row.get("url"), row.get("body_slug")
    if not url or not slug:
        return None
    return f"{slug}_{hashlib.sha1(url.encode()).hexdigest()[:16]}.pdf"


def resolve_pdf(row: dict, pdf_dir: Path | None) -> Path | None:
    """Find the local PDF for a row: local_path, then several names in --pdf-dir."""
    lp = row.get("local_path")
    if lp and Path(lp).exists():
        return Path(lp)
    if pdf_dir:
        for cand in (crawl_filename(row),
                     row.get("filename"),
                     (row.get("sha256") or "") + ".pdf"):
            if cand and (pdf_dir / cand).exists():
                return pdf_dir / cand
    return None


def load_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def doc_key(row: dict) -> str:
    """Stable identity for the checkpoint file.

    sha256 is the right key, but it is not guaranteed present: crawl_duluth.py used
    to skip hashing on a cache hit, so a warm re-run produced rows without one. A
    single malformed row must not be able to abort a 91-document job, so fall back
    to the URL, which is unique by construction (it is the table's UNIQUE key).
    """
    return row.get("sha256") or row.get("url") or row.get("filename") or ""


def build_queue(rows: list[dict], pdf_dir: Path | None, max_pages: int | None = None):
    """Split the scanned documents into (jobs, missing). Kept separate from main()
    because this is where the silent no-op lived: everything filtered out, nothing
    reported, exit 0."""
    candidates = [r for r in rows if r.get("quality") in SCANNED_QUALITY]
    jobs, missing = [], []
    for r in candidates:
        p = resolve_pdf(r, pdf_dir)
        (jobs.append((doc_key(r), str(p), max_pages)) if p else missing.append(r))
    return jobs, missing, candidates


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", type=Path, default=None)
    ap.add_argument("--out", dest="out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--pdf-dir", type=Path, default=None,
                    help="directory of downloaded PDFs (see crawl_duluth.py)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--limit", type=int, default=None, help="stop after N documents")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="cap OCR'd pages per document (default: no cap)")
    ap.add_argument("--restart", action="store_true", help="ignore the progress file")
    a = ap.parse_args(list(argv) if argv is not None else None)

    inp = a.inp or (DEFAULT_IN if DEFAULT_IN.exists() else FALLBACK_IN)
    progress = a.out.with_suffix(".progress.jsonl")

    # ---- fail loudly, before doing any work -------------------------------
    if not inp.exists():
        sys.exit(f"input not found: {inp}\nRun extract_text.py first, or pass --in.")
    if not shutil.which("tesseract"):
        sys.exit("tesseract is not installed.\n  macOS: brew install tesseract\n"
                 "  Debian/Ubuntu: apt-get install tesseract-ocr")
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        sys.exit("pymupdf is not installed:  pip install pymupdf")

    rows = load_rows(inp)
    by_sha = {doc_key(r): r for r in rows}

    jobs, missing, candidates = build_queue(rows, a.pdf_dir, a.max_pages)

    if missing:
        print(f"  {len(missing)} of {len(candidates)} scanned documents have no local PDF")
        for r in missing[:5]:
            print(f"    missing: {r.get('filename')}")
        if not jobs:
            sys.exit(
                f"\nNo local PDFs found for any of the {len(candidates)} scanned documents.\n"
                f"Pass --pdf-dir, or run crawl_duluth.py to download them first.\n"
                "Refusing to write an output file identical to the input: a silent no-op\n"
                "here is exactly why this pass appeared to have 'never completed'."
            )

    done: dict[str, dict] = {}
    if progress.exists() and not a.restart:
        # Only a SUCCESS counts as done. Treating a recorded failure as done means
        # a bad run poisons every retry after it -- the second attempt skips
        # exactly the documents that need attempting.
        all_prev = {d["sha256"]: d for d in load_rows(progress)}
        done = {k: v for k, v in all_prev.items()
                if not str(v.get("ocr_status", "")).startswith("error")}
        retry = len(all_prev) - len(done)
        jobs = [j for j in jobs if j[0] not in done]
        print(f"  resuming: {len(done)} done, {retry} previous failures to retry, "
              f"{len(jobs)} to process")

    if a.limit:
        jobs = jobs[: a.limit]

    total_pages = sum(by_sha[s].get("scanned_pages") or 0 for s, _, _ in jobs)
    print(f"OCR queue: {len(jobs)} documents, ~{total_pages} scanned pages, {a.jobs} workers")

    fh = progress.open("a", encoding="utf-8")
    try:
        with ProcessPoolExecutor(max_workers=a.jobs) as pool:
            futures = {pool.submit(_worker, j): j for j in jobs}
            for n, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                done[res["sha256"]] = res
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                fh.flush()          # checkpoint per document, not per run
                name = (by_sha.get(res["sha256"], {}).get("filename") or "?")[:44]
                status = res.get("ocr_status", "?")
                if status.startswith("error"):
                    print(f"  [{n}/{len(jobs)}] {status:<22} {name}  {res.get('ocr_error','')[:60]}")
                else:
                    print(f"  [{n}/{len(jobs)}] {status:<22} {name}  "
                          f"+{res.get('ocr_chars', 0):,} chars")
    finally:
        fh.close()

    # ---- merge and write ---------------------------------------------------
    for r in rows:
        d = done.get(doc_key(r))
        if not d or d.get("ocr_status", "").startswith("error"):
            r.setdefault("text_source", "embedded" if r.get("text") else "none")
            continue
        r["text_ocr"] = d["text_ocr"]
        r["ocr_chars"] = d["ocr_chars"]
        r["ocr_page_numbers"] = d["ocr_page_numbers"]
        r["ocr_truncated"] = bool(d.get("ocr_pages_dropped"))
        r["ocr_pages_dropped"] = d.get("ocr_pages_dropped") or []
        r["text_source"] = d["text_source"]
        if not r.get("text"):
            r["text_chars"] = d["ocr_chars"]

    with a.out.open("w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats = collections.Counter(d.get("ocr_status", "?") for d in done.values())
    added = sum(d.get("ocr_chars", 0) for d in done.values())
    dropped = sum(len(d.get("ocr_pages_dropped") or []) for d in done.values())
    pfailed = sum(len(d.get("ocr_pages_failed") or []) for d in done.values())
    print(f"\n  status: {dict(stats)}")
    print(f"  documents recovered: {sum(1 for d in done.values() if d.get('ocr_chars', 0) > 200)}")
    print(f"  OCR characters added: {added:,}")
    print(f"  text_source: {dict(collections.Counter(r.get('text_source') for r in rows))}")
    if pfailed:
        print(f"  WARNING: {pfailed} individual pages failed to OCR and are absent "
              "from the text")
    if dropped:
        print(f"  WARNING: {dropped} scanned pages were dropped by --max-pages "
              "and are NOT in the output")
    print(f"  -> {a.out}")
    print(f"\nNext: regenerate cases with parse_cases.py, then reload with "
          f"load_meeting_docs_from_url(). Minutes are where the vote records are.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
