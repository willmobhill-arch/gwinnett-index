# Session handoff — 2026-08-14

Supersedes `docs/plans/2026-08-13-session-handoff.md`.

Repo: **`willmobhill-arch/gwinnett-index`** (an earlier doc named a different owner — that
was wrong and cost two sessions of repo access).
Supabase: `losmnziukaqptxhqnhjh` · Site: https://www.gwindex.net · MCP: `net.gwindex/gwinnett-index`

---

## What this session did

Verified the Duluth UDC tables against **rendered source page images** and repaired
`code_table`. The task was "verify the 17 unverified tables." None of them could be marked
verified, the corpus was missing tables, and the one table already flagged `verified` was
itself wrong.

### Findings

| Finding | Detail |
|---|---|
| **2-C and 2-D Residential held the wrong table's data** | Fragment page ranges overlapped by one page, and each fragment took its header and rows from the **last** page of its range instead of the first. 2-C Residential had commercial district columns (`CBD, C-1, C-2…` rather than `R-TH, RA-200, R-100…`) and 10 rows — all of them from the commercial table. Source has ~337. This is the table that answers "can I put this use in R-100?" |
| **Two tables were never extracted** | 4-C (Handicap Accessible Spaces, p142) and 12-A (Special Exceptions, pp363–365). Discovery required `Table 4-C:` with punctuation; the document writes `TABLE 7-B Tree Canopy…` in caps with no colon. Same case/punctuation trap already documented for agenda case numbers. |
| **Nine tables had structurally broken headers** | Spanning labels smeared across the columns they overlapped (`"1. Provid" / "e a buffer on the l" / "ot of this use"` in 7-A), or the table *title* captured as the header row (9-B). |
| **2-B — the only `verified` table — was wrong** | Source has 20 district rows across pp52–53; the DB held 15, which is exactly the rows on page 52. The extractor stopped at the page boundary. Missing: PUD, CBD (Residential uses), CBD (Commercial uses), RD, R-TH. Re-transcribed cell-by-cell and corrected. |
| **The UDC cites a table that does not exist** | §605.05 and §605.06 both reference **Table 6-D**. There is no 6-D and no 6-C — the sign tables run 6-A, 6-B, 6-E. A stale cross-reference after renumbering; the content is in 6-E. This is an ordinance defect, not ours, and is recorded in 6-E's `verification_note`. Worth surfacing on the site so an agent asking about 6-D is told it doesn't exist. |

### Database state

`code_table` now holds **20 tables** (was 18):

```sql
SELECT quality, count(*) FROM code_table GROUP BY 1;
-- verified 7 | defective 12 | unverified 1
```

`verified` (safe to publish): 2-B, 3-A, 4-A, 4-C, 7-A, 7-B, 9-B.
`defective`: header, column count and page range corrected and verified, but **cell values
are known wrong and must not be published**.

Migrations applied:

- `code_table.spanning_header` — a label spanning several columns is distinct meaning and
  was previously smeared into the columns it overlapped. Populated for 3-A, 3-B, 4-A, 6-B,
  6-E, 7-A, 7-C, 9-B.
- `code_table.header_source` — `rendered-image` / `geometry` / `markdown` / `legacy`.
- `CHECK (quality <> 'verified' OR n_rows = jsonb_array_length(rows))` — makes 2-B's old
  state unrepresentable. A `verified` flag asserting a check that never happened is worse
  than no flag, because it stops anyone looking again.
- `CHECK (n_cols = array_length(header, 1))`.

**`n_rows` on defective tables is the true source count while `rows` still holds the old
wrong data.** That discrepancy is a live worklist:

```sql
SELECT citation, n_rows AS should_have, jsonb_array_length(rows) AS actually_has
FROM code_table
WHERE quality = 'defective' AND n_rows IS DISTINCT FROM jsonb_array_length(rows);
```

---

## What's next, in order

1. **Wire `ingest/pdf/` into the adapter layer** as the `pdf_code` adapter. The two modules
   are standalone right now and don't follow the discover/fetch/parse/normalize/upsert
   contract in `ingest/adapters/base.py`.
2. **Make extraction reproduce `tests/fixtures/duluth_udc_tables.json` exactly** — n_cols,
   header and n_rows for all 20 tables — then reload the 12 defective tables' cell values.
3. **Add two build gates**: the fixture comparison, and an assertion that the count of
   discovered `Table N-X` title lines equals the count of extracted tables. That second
   assertion alone would have caught 4-C and 12-A on day one.
4. **Transcribe Table 12-A's 17 prose rows** (currently header-only, `unverified`).
5. Then: OCR pass on scanned Duluth minutes, and the 262-row applicant merge queue.

## Still outstanding from before

- **Rotate the Cloudflare API token** — it was pasted into a transcript. Roll it at
  dash.cloudflare.com/profile/api-tokens, store as `CLOUDFLARE_API_TOKEN` in Actions
  secrets, and confirm Bot Fight Mode is still OFF for gwindex.net.
- **Move the `net.gwindex` keypair out of the scratchpad.** Without the private key the MCP
  registry entry can never be republished, and it can't be regenerated without changing the
  DNS TXT record that proves domain ownership. Password manager + Actions secret
  `MCP_REGISTRY_PRIVATE_KEY`. Public key only in the repo.

---

## Running the extractor

```bash
pip install pymupdf pymupdf4llm
mkdir -p var && curl -sL "$(python -c 'print(open("var/udc_url.txt").read().strip())')" -o var/duluth_udc.pdf
python -m ingest.pdf.extract_tables      # pass A: discovery + rows      -> var/extracted_tables.json
python -m ingest.pdf.resolve_headers     # pass B: geometry headers      -> merges in place
```

Paths come from `UDC_PDF` / `UDC_OUT`, defaulting to `var/` at the repo root.

## Method notes — do not skip these

- **Verify against the rendered page image, cell by cell.** Every defect above was found
  this way; none were found by internal consistency. `page.get_pixmap(dpi=200, clip=...)`
  and actually look at it.
- **`find_tables()` segfaults on page 175.** Pass B runs one subprocess per page for
  exactly this reason — an in-process call takes the whole run down and leaves an output
  file that looks complete.
- **`use_ocr=False` on `pymupdf4llm.to_markdown`** — the UDC is digital-born; the OCR path
  adds nothing and is slow.
- **Geometry headers beat markdown for spanning labels and are worse for the tightly-packed
  rotated headers in 2-B/2-C.** Don't apply either blindly. Where they disagree, the
  rendered image decides — that's what the fixture is for. An earlier attempt to auto-pick
  by a heuristic score picked wrong on both 3-A and 2-C.
- **Assert discovery counts.** Count `Table N-X` title lines in the body; require equality
  with extracted tables.
- **The recurring failure shape is a job that succeeds while doing nothing.** An OCR queue
  of zero. A crawler that downloads nothing without `--fetch`. A dedup key that discarded
  51 decisions. An exporter `select` that dropped `motion_action` and published a denial as
  "Motion carried". An extractor reporting 18 tables when the PDF has 21. A `verified` flag
  on a table missing a quarter of its rows. None raised an error; every one was found by
  checking a number that didn't add up.

## Source state

`https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf`
8,646,771 bytes · `Last-Modified: 2026-07-16` · 426 pages
SHA-256 `2311ae985c3f1e46cb84844fdb09bfe92b89917572e112c29b78cb9fe94a48c0`

The filename encodes the amendment date and changes on every amendment — **never hardcode
it**, scrape the link; the changing filename is the change-detection signal. A changed hash
means re-verify every table against the new render.
