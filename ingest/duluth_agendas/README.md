# Duluth agenda mining

The City of Duluth publishes no case tracker. These four scripts derive land-use
cases from the public record instead: crawl the meeting index, extract text,
OCR what was scanned, then parse case-shaped items out of the result.

```
crawl_duluth.py    index pages -> 356 PDFs into ./raw/, + duluth_meeting_docs.jsonl
                   NOTE: downloads ONLY with --fetch; without it you get metadata
extract_text.py    PDF text layer  -> duluth_meeting_text.jsonl
ocr_scanned.py     the 91 scanned  -> duluth_meeting_text_ocr.jsonl
parse_cases.py     case-shaped items -> duluth_cases.jsonl
publish.py         both of the above -> ../../data/, where the SQL loaders fetch them
```

Each script reads the previous one's output from this directory. `parse_cases.py`
prefers `duluth_meeting_text_ocr.jsonl` and falls back to the non-OCR file, so
running the OCR pass changes the cases automatically — but **only if you then run
`publish.py`**. Without it the results never leave this directory.

## Run the OCR pass

This is the highest-value data work outstanding. **83 of 138 minutes have no text
layer at all**, and minutes are where decisions and vote records live — only 54 of
109 Duluth cases currently carry an outcome.

```bash
# In a Claude Code web container, this one line does the whole install
# (verified: tesseract 5.3.4 + pymupdf 1.28.2). Locally, use brew/apt directly.
bash scripts/setup_ocr_env.sh
# equivalently: apt-get install -y tesseract-ocr && pip install pymupdf httpx

cd ingest/duluth_agendas
python3 crawl_duluth.py --fetch        # 356 PDFs -> ./raw/ (~10 min, skips cached)
python3 extract_text.py
python3 ocr_scanned.py --jobs 8        # the long one
python3 parse_cases.py
python3 publish.py                     # -> ../../data/   <-- do not skip this
```

`ocr_scanned.py` finds the PDFs through the `local_path` that `crawl_duluth.py`
records, so `--pdf-dir` is only needed if you moved them. Note the crawler saves
files as `<body_slug>_<sha1(url)[:16]>.pdf`, not under their published names — those
collide and contain spaces.

The queue is **91 documents / 1,059 scanned pages** — roughly an hour
single-threaded, a few minutes across cores. It was never the size that stopped
this finishing. Progress is checkpointed per document to
`duluth_meeting_text_ocr.progress.jsonl`, so an interrupted run resumes rather
than restarting.

Then commit `data/` and reload. The loaders fetch over HTTP from the repo's own raw
URLs, so the files must be pushed first:

```bash
git add data/ && git commit -m "Duluth: OCR'd meeting text and regenerated cases" && git push
```

```sql
SELECT load_meeting_docs_from_url(
  'https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index/main/data/duluth_meeting_docs.jsonl');
SELECT * FROM load_duluth_cases_from_url(
  'https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index/main/data/duluth_cases.jsonl');
```

## What OCR text is, and is not

OCR output is a **reconstruction**, never a quotation of the record. It lives in
its own field, and `text_source` says which half of a document you are reading:

| `text_source` | meaning |
|---|---|
| `embedded` | the publisher's own text layer — quotable |
| `ocr` | wholly reconstructed — never quote as the record |
| `mixed` | both; `ocr_page_numbers` lists the reconstructed pages |
| `none` | no text recovered |

`publish.py` keeps `text` and `text_ocr` in the published file. That is deliberate and
it makes the file much larger — roughly 13 MB against the 200 KB it was — because the
previous hand-assembled version carried metadata only, which is why 12.5 M characters
of extracted meeting text had never reached the database. Use `--no-text` to go back
to metadata-only if the file size becomes a problem.

`mixed` exists because seven of the scanned documents are packets that already
carry real publisher text — one is a 382-page binder with 154 scanned pages and
449,287 characters of genuine text. Marking that document `ocr` would throw away
the ability to quote any of it; marking it `embedded` would pass OCR guesses off
as the record. Both are wrong, so the schema says what is actually true.

## Traps in here, already paid for

- **`\b` in a date regex fails after a letter.** `DuluthAgendaBinder8-10-26.pdf` —
  "r" and "8" are both word characters, so there is no boundary. This dropped the
  date on all 80 agenda binders. Use `(?<!\d)`.
- **Case-number punctuation varies by body.** Planning Commission writes
  `Case: TA2026-007,`; the ZBA writes `Case V2026-001`; council packets write
  `CASE Z2026-004`. An early-exit guard on the literal `"Case:"` skipped every
  packet — that is, every decision.
- **Bound every capture group.** An unbounded `.+?` between `Case:` and `Request:`
  ran across a whole staff report and produced one record with 67,553 characters
  in its `address` field.
- **`crawl_duluth.py` downloads nothing without `--fetch`.** The default run does
  discovery, writes a metadata-only `duluth_meeting_docs.jsonl`, prints a cheerful
  document count and exits 0. Every downstream script then finds no PDFs. Same
  family as the bug below: the flag gates the side effect, not the exit code.
- **A queue of zero is a bug, not a result.** The previous OCR script required
  `local_path` on every row, which nothing in the published corpus has. It printed
  `OCR queue: 0`, wrote an output file identical to its input, and exited 0. That
  is almost certainly why this pass looked like it had "never completed". It now
  refuses to write anything if it found no PDFs.

## Known weakness in the current output

The 109 extracted cases are **a finding aid, not a dataset**. Measured:

| | of 109 |
|---|---|
| "Location" with no street number in it | 67 |
| …of which plainly not addresses (`as presented.`, `{J}`) | 17 |
| "Request" that is just the word `ORDINANCE` | 57 |
| Applicant field that ran on into a mailing address | 23 |
| Carries a zoning district | 13 |
| Carries an outcome | 54 |

Each row links to the PDF it came from. **The document is the record; the fields
point at it.** Running the OCR pass is what makes the minutes parseable and turns
these into records — the field extraction in `parse_cases.py` should be revisited
against the OCR'd minutes rather than tuned further against agendas alone.
