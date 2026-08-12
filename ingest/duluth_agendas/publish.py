#!/usr/bin/env python3
"""
Publish the mined Duluth corpus into data/, where the SQL loaders fetch it.

This step did not exist. The files in data/ were assembled by hand, which is why
data/duluth_meeting_docs.jsonl carries metadata but no text: 12.5 M characters of
meeting text were extracted, and none of it ever reached the database. Running the
OCR pass without this step recovers the scanned minutes into a local file and stops
there.

    ingest/duluth_agendas/                      data/                    Postgres
      duluth_meeting_text_ocr.jsonl  --------->  duluth_meeting_docs  --> load_meeting_docs_from_url()
      duluth_cases.jsonl             --------->  duluth_cases         --> load_duluth_cases_from_url()

Two things this does that a `cp` would not:

  - strips local_path. It is an absolute path on whoever's laptop ran the crawler,
    and these files are published to a public repository.
  - keeps the text. That is the entire point of the OCR pass, and the reason the
    published file gets much larger.

Usage:
    python3 ingest/duluth_agendas/publish.py
    python3 ingest/duluth_agendas/publish.py --no-text     # metadata only, as before
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent
DATA = REPO / "data"

DOC_SOURCES = ["duluth_meeting_text_ocr.jsonl", "duluth_meeting_text.jsonl"]
CASE_SOURCE = "duluth_cases.jsonl"

# Never published: an absolute path from the machine that ran the crawler, plus
# transient crawler bookkeeping that means nothing outside that run.
STRIP = {"local_path", "fetch_status"}
TEXT_FIELDS = {"text", "text_ocr"}


def size(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB" if n > 1_048_576 else f"{n / 1024:.0f} KB"


def publish_docs(src: Path, dest: Path, with_text: bool) -> dict:
    rows = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]
    out = []
    for r in rows:
        clean = {k: v for k, v in r.items()
                 if k not in STRIP and (with_text or k not in TEXT_FIELDS)}
        out.append(clean)

    # A published record that still carries someone's home directory is a bug we
    # would only notice by reading the file, so check rather than trust.
    leaked = [r for r in out
              if any(isinstance(v, str) and (v.startswith("/") or v.startswith("C:\\"))
                     for k, v in r.items() if k != "url")]
    if leaked:
        sys.exit(f"refusing to publish: {len(leaked)} rows still carry a local filesystem path")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    chars = sum(len(r.get("text") or "") + len(r.get("text_ocr") or "") for r in out)
    return {
        "rows": len(out),
        "chars": chars,
        "bytes": dest.stat().st_size,
        "ocr_docs": sum(1 for r in out if r.get("text_source") in ("ocr", "mixed")),
        "sources": {s: sum(1 for r in out if r.get("text_source") == s)
                    for s in ("embedded", "ocr", "mixed", "none")},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-text", action="store_true",
                    help="publish metadata only (what data/ held before)")
    a = ap.parse_args(argv)

    src = next((HERE / n for n in DOC_SOURCES if (HERE / n).exists()), None)
    if src is None:
        sys.exit(f"no extracted corpus found. Run extract_text.py (then ocr_scanned.py) first.\n"
                 f"Looked for: {', '.join(DOC_SOURCES)}")
    if src.name != DOC_SOURCES[0]:
        print(f"  NOTE: publishing from {src.name} — the OCR pass has not been run,\n"
              f"        so the 91 scanned documents will carry no text.")

    dest = DATA / "duluth_meeting_docs.jsonl"
    before = dest.stat().st_size if dest.exists() else 0
    st = publish_docs(src, dest, with_text=not a.no_text)

    print(f"  {src.name} -> data/duluth_meeting_docs.jsonl")
    print(f"    {st['rows']} documents, {st['chars']:,} characters of text")
    print(f"    text_source: {st['sources']}")
    print(f"    {size(before)} -> {size(st['bytes'])}")

    cases = HERE / CASE_SOURCE
    if cases.exists():
        out = DATA / CASE_SOURCE
        rows = [json.loads(l) for l in cases.open(encoding="utf-8") if l.strip()]
        with out.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({k: v for k, v in r.items() if k not in STRIP},
                                    ensure_ascii=False) + "\n")
        distinct = len({r.get("case_number") for r in rows})
        outcomes = sum(1 for r in rows if r.get("outcome"))
        print(f"  {CASE_SOURCE} -> data/{CASE_SOURCE}")
        print(f"    {len(rows)} rows, {distinct} distinct cases, {outcomes} with an outcome")
    else:
        print(f"  {CASE_SOURCE} not found — run parse_cases.py to regenerate it")

    if st["bytes"] > 50 * 1_048_576:
        print(f"\n  WARNING: {size(st['bytes'])} exceeds GitHub's 50 MB soft limit for a "
              "single file.\n  Consider splitting by body or year before committing.")

    print("\nNext:")
    print("  git add data/ && git commit && git push        # the loaders fetch by raw URL")
    print("  SELECT load_meeting_docs_from_url('https://raw.githubusercontent.com/"
          "willmobhill-arch/gwinnett-index/main/data/duluth_meeting_docs.jsonl');")
    print("  SELECT * FROM load_duluth_cases_from_url('https://raw.githubusercontent.com/"
          "willmobhill-arch/gwinnett-index/main/data/duluth_cases.jsonl');")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
