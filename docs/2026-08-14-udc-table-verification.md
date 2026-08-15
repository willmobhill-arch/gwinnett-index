# Duluth UDC Tables — Verification Findings & Fix Status

**Date:** 2026-08-14 (revised)
**Source:** `https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf`
**Source state:** 8,646,771 bytes · `Last-Modified: 2026-07-16` · SHA-256 `2311ae98…4a48c0` · 426 pages
**Verified against:** rendered page images + a rewritten extractor (`extract_tables.py`)

The source PDF is unchanged since the snapshot, so every defect is in our extraction,
not in the ordinance — with one exception, noted in §2.

**Nothing wrong is published.** Cell values for unverified tables are withheld from the
live snapshot. The exposure is latent, not live.

---

## Corrections to the first version of this document

Two claims in the first draft were wrong. Both came from a discovery regex that was
itself buggy — the same bug being investigated.

- **Table 6-D is NOT a missing table.** It does not exist in the UDC. Both mentions on
  page 175 are cross-references in body text. See §2 — this is a defect in the
  ordinance, not in our pipeline.
- **The count of missing tables is 2, not 3** — 4-C and 12-A.

---

## 1. True table inventory: 20 tables, we had 18

Discovery had to be rewritten before anything else could be trusted. The old pattern
required `Table 7-B:` with punctuation and matching case. The document writes:

```
TABLE 7-B Tree Canopy Cover Requirements by Zoning District
```

All caps, no colon. **This is the same case-and-punctuation trap already documented in
CLAUDE.md for agenda case numbers**, recurring in table discovery. It is why 4-C and
12-A were never extracted, and why 7-B was only ever found by accident.

| | |
|---|---|
| Real tables in the document | **20** |
| Previously in `code_table` | 18 |
| Never extracted | **4-C** (Handicap Accessible Spaces Required, p142), **12-A** (Special Exceptions, pp363–365) |

---

## 2. A defect in the ordinance itself — worth surfacing on the site

Section 605.05 and 605.06 both direct the reader to **Table 6-D**:

> "…a project entrance sign for the subdivision in accordance with the provisions for
> such signs on **Table 6-D**."

**There is no Table 6-D in the UDC.** There is no Table 6-C either — the sign tables run
6-A, 6-B, then jump to 6-E. The content those sections describe (project entrance signs
by land use) is in **Table 6-E**, so the cross-references are almost certainly stale
after a renumbering.

This is exactly the kind of thing the index should say out loud: an agent asked "what
does Table 6-D require?" should be told it does not exist and pointed at 6-E, not left
to hallucinate. Recommend a `code_note` record against §605.05/§605.06.

---

## 3. The root cause of the worst data defect — fixed

Table 2-C and 2-D each split across a district-group boundary. The old splitter recorded
**overlapping page ranges** and populated each fragment from the **last** page of its
range instead of the first.

| Fragment | Old range | Page that supplied data | Result |
|---|---|---|---|
| 2-C Residential | 56–**70** | 70 — the *commercial* table's first page | wrong header, wrong rows |
| 2-D Residential | 85–**89** | 89 — the *commercial* table's first page | wrong header, wrong rows |

Verified cell-for-cell against the rendered image of page 57:

| | Columns |
|---|---|
| **Source (true)** | `R-TH · RA-200 · R-100 · R-75 · R-50 · RM · MH · HRD` |
| **Old database** | `CBD · C-1 · C-2 · HC-Retail · HC-Auto · O-I · O-N · M-1 · M-2 · RD` |

Not one residential district column was present, and the 10 stored rows were the first
10 rows of the *commercial* table.

**Why this one mattered most:** 2-C Residential answers "can I put this use in R-100?"
Published as-is it would have returned commercial-district answers under residential
labels — a confidently wrong answer, the exact failure mode the project exists to avoid.

### After the fix

| Fragment | Cols | Rows | Districts |
|---|---|---|---|
| 2-C Residential | **12** | **368** | R-TH, RA-200, R-100, R-75, R-50, RM, MH, HRD ✅ |
| 2-C Commercial | 14 | 353 | CBD, C-1, C-2, HC-Retail, HC-Auto, O-I, O-N, M-1, M-2, RD ✅ |
| 2-D Residential | **11** | **54** | R-TH … HRD ✅ |
| 2-D Commercial | 13 | 56 | CBD … RD ✅ |

Was 10 rows on the residential half. Now 368, with the correct districts.

---

## 4. Fix status by table

> **Sections 4 and 5 record the mid-fix state and are superseded by §6.** The headers
> listed as "still broken" below have since been resolved from rendered images and
> written to the database; §6 is the current truth.

Extraction now runs through `pymupdf4llm` rather than raw `find_tables()`, because it
resolves merged cells to a stable column count — which is what broke the old
row-index-based approach.

### Fixed and structurally correct (needs final cell-by-cell render check)

| Table | Cols | Rows | Note |
|---|---|---|---|
| 2-C Residential | 12 | 368 | root-cause fix; minor header bleed on cols 0–1 to clean up |
| 2-C Commercial | 14 | 353 | same minor header bleed |
| 2-D Residential | 11 | 54 | ✅ clean |
| 2-D Commercial | 13 | 56 | ✅ clean |
| 4-B Minimum Parking Spaces | 3 | 59 | ✅ clean |
| 7-B Tree Canopy Cover | 3 | 18 | ✅ clean; newly discoverable |
| 7-C Distances Between Trees | 5 | 11 | ✅ spanning header resolved to Large/Medium/Small/Very Small |
| 9-A Right-of-Way Widths | 3 | 13 | ✅ clean |
| 12-A Special Exceptions | 2 | 19 | ✅ newly extracted; 3 page-fragments to merge |

### Still broken — need the x-edge header resolver

These have a spanning label smeared horizontally across the columns it overlaps. The
fix is the method CLAUDE.md already prescribes for rows — derive columns from clustered
x-edges of the drawn grid, then assign header words by x-midpoint — applied to the
header band.

| Table | Current header | Problem |
|---|---|---|
| 3-A Illuminance Levels | `Maximum Maintained Illumin Line (A` / `ance Level Allowed at Property t Grade` | two header cells interleaved character-wise |
| 3-B Allowed Building Materials | `Zoning C-2 HC-Retail HC-` / `District` | "Zoning District" spanning label split into data columns |
| 4-A Parking by Time Period | `Week` / `days` / `Week` / `ends` | words split across columns |
| 6-B Signs — Nonresidential | `All Other Nonresid` / `ential Properties` | label cut mid-word |
| 6-E Project Entrance Signs | `Residen` / `tial Use` | label cut mid-word |
| 7-A Situations Where Buffer Required | `1. Provid` / `e a buffer on the l` / `ot of this use` | sentence split across four columns |
| 9-B Maximum Pipe Invert Depth | `Maxi` / `mum Pip` / `e Inve` / `rt Dept` | the table **title** captured as the header row |
| 4-C Handicap Accessible Spaces | 1 column | grid not detected at all; needs a non-ruled-table path |

---

## 5. What remains

1. **Write the x-edge header resolver** — fixes the 7 tables in §4 and the 4-C detection.
2. **Clean the 2-C header bleed** (cols 0–1 pick up the first data row).
3. **Merge the three 12-A page-fragments** into one table.
4. **Cell-by-cell verify every table against rendered pages** — the step that caught the
   original 2-B bleed. Nothing gets `quality='verified'` without it.
5. **Repair `code_table`** in Supabase from the corrected extraction.
6. **Add a regression fixture**: expected header vector + row count per table, plus an
   assertion that discovered-title-count equals extracted-table-count. That single
   assertion would have caught 4-C and 12-A on day one.
7. **Land the fix in the repo** — `extract_tables.py` here is standalone and needs to
   become the pdf_code adapter. Blocked on repo access.

## Suggested interim data-integrity step

Mark the still-broken ids `quality='defective'` with a `verification_note` pointing at
this report, rather than leaving them `unverified`. "Unverified" reads as "not yet
checked"; these have been checked and are known wrong. A visible gap is recoverable; a
confident wrong answer is not.

---

## 6. Database state after the 2026-08-14 repair

`code_table` now holds **20 tables** (was 18) and every row carries an honest quality flag.

| Quality | Tables | Meaning |
|---|---|---|
| `verified` | **7** | Checked cell-by-cell against the rendered source page. Safe to publish. |
| `defective` | **12** | Header/columns/page range corrected and verified, but **cell values are known wrong** and must not be published. Awaiting re-extraction. |
| `unverified` | 1 | Table 12-A — header and row count verified, prose cells not yet transcribed. |

**Verified:** 2-B, 3-A, 4-A, 4-C, 7-A, 7-B, 9-B.

### Schema changes

- `code_table.spanning_header` — a label spanning several columns is a distinct piece of
  meaning and was previously smeared into the columns it overlapped. Now stored separately.
  Populated for 3-A, 3-B, 4-A, 6-B, 6-E, 7-A, 7-C, 9-B.
- `code_table.header_source` — `rendered-image` / `geometry` / `markdown` / `legacy`, so a
  later run can tell a hand-checked value from a parser guess.
- **`code_table_verified_rows_match`** — `CHECK (quality <> 'verified' OR n_rows =
  jsonb_array_length(rows))`. Table 2-B was flagged `verified` while holding 15 of its 20
  rows; this makes that state unrepresentable.
- **`code_table_ncols_match`** — `n_cols` must equal the length of `header`.

### The 2-B finding, which was the sharpest one

2-B was the *only* table previously marked `verified`, and it was wrong. The source has
**20 zoning district rows across pages 52–53**; the database held **15 — exactly the rows
on page 52**. The extractor stopped at the page boundary and dropped PUD, CBD
(Residential uses), CBD (Commercial uses), RD and R-TH. No error was raised.

This is the same failure shape as the rest, with an extra twist: a `verified` flag
asserting a check that had not actually happened is worse than no flag, because it stops
anyone looking again. Hence the CHECK constraint above.

`n_rows` on defective tables is now the **true source count**, while the stored `rows`
array still holds the old wrong data — so `n_rows <> jsonb_array_length(rows)` is itself
a live to-do list:

```sql
SELECT citation, n_rows AS should_have, jsonb_array_length(rows) AS actually_has
FROM code_table WHERE quality = 'defective'
  AND n_rows IS DISTINCT FROM jsonb_array_length(rows);
```

### Still to do

1. Finish the extractor so it reproduces `table_fixture.json` exactly, then reload the
   12 defective tables' cell values.
2. Transcribe Table 12-A's prose cells (17 rows).
3. Land `extract_tables.py` + `resolve_headers.py` in the repo as the pdf_code adapter,
   and wire `table_fixture.json` in as a build gate.
4. Surface the Table 6-D dangling cross-reference on the site — recorded for now in
   Table 6-E's `verification_note`.
