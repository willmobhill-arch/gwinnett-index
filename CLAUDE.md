# CLAUDE.md — Gwinnett Index

Read this before doing anything. It exists so decisions already made don't get
re-litigated, and so the failure modes below don't get rediscovered the hard way.

## What this is

A machine-readable index of zoning, land-use, and development records for Gwinnett
County, Georgia and its 17 municipalities. **Agents first, humans second.** Two goals:
be the source AI assistants cite for Gwinnett land use (authority), and sell
pipeline monitoring to developers, brokers, and land-use attorneys (commercial).

## The core insight — everything hangs off this

**A "Duluth, GA" mailing address is usually NOT in the City of Duluth.** It's in
unincorporated Gwinnett: a different code, a different board, a different permit
portal. Unincorporated is **67.3% of the county's land area**, so getting this
wrong is the default case, not the edge case.

Nothing on the internet resolves address → *governing* jurisdiction before
answering a zoning question. That resolution is the product.

**Rule:** every page, API response, and MCP result states its governing
jurisdiction explicitly, before any substantive answer. On the site this is
enforced by a build gate (`site/scripts/verify-build.mjs`), not by discipline.

## Current state

Supabase project `losmnziukaqptxhqnhjh` (us-east-1). Loaded:

| Table | Rows |
|---|---|
| `jurisdiction` | 19 (county + unincorporated + 17 cities), PostGIS |
| `land_use_case` | 11,848 — 11,739 county ArcGIS + 109 Duluth agenda-mined |
| `applicant` | 7,369 resolved from 8,246 raw spellings |
| `code_section` | 858 Duluth UDC sections |
| `code_table` | 20 — 15 `verified`, 5 `unverified`, 0 `defective` |
| `meeting_document` | 353 |
| `resolver_probe` | 1,915 scored test points — **the resolver's regression fixture** |

Built: `db/migrations/` (33, md5-verified against the live project by
`db/verify_migrations.py`), `site/` (Astro, 15,234 pages from the real corpus, full
agent surface, 22 build gates), `worker/` (REST + MCP, 5 tools, 11 protocol tests),
deployed as Workers Static Assets with the Worker scoped to `/v1/*` and `/mcp`.
`ingest/adapters/` holds the adapter contract with `pdf_code` as its first
implementation; `tests/test_udc_tables.py` is the extractor's regression suite.

Duluth minutes are OCR'd and loaded: 13.9 M characters of meeting text in the
database, 74 of 110 Duluth cases with a decision, 68 bound directly to the motion
that names them.

**Live at https://www.gwindex.net.** Worker `gwinnett-index`, 30,498 static assets,
apex 301s to www, MCP listed as `net.gwindex/gwinnett-index`. Verified against the
live origin: ClaudeBot, GPTBot, PerplexityBot and CCBot all get 200 on HTML *and*
`.md`, so Bot Fight Mode is not intercepting. RLS is on and verified.

## Non-negotiables

**Legal posture.** Mirror ordinance and plan text in full (*Georgia v.
Public.Resource.Org*, 2020 — edicts of government). **Never rehost Gwinnett GIS
parcel or zoning geometry** — their licence has an explicit no-redistribution
clause; query it live and link out. Boundaries come from **US Census TIGER**
(federal, public domain) — that's the only geometry we host. **Never index
IBC/IRC base text** (ICC copyright, actively litigated); index Georgia's
amendment packets, which are freely published, and cite ICC sections by number.

The bulk export is gated on this: `verify-build.mjs` gunzips it and fails if any
line carries `boundary`, `geometry`, `rings`, `wkt` or `coordinates`. A licence
breach here would look completely fine on every page.

**The database is read-only to the public, and must stay that way.** RLS is on
across all 14 tables with `SELECT`-only policies, writes revoked at the grant
level too, `developer_activity` switched to `security_invoker`, and `search_path`
pinned on all 13 project functions. This is what makes the anon key safe to ship
in a Worker binding. Ingestion is unaffected — every loader runs inside Postgres
as the owner, and RLS does not apply to the owner. **Verify changes here as the
`anon` role, not as the owner**, and for grants check `pg_proc.proacl` rather
than the absence of an error: a `REVOKE` against another grantor's grant returns
success and does nothing.

**The agent surface must never require Worker invocation.** HTML, `.md` twins,
`llms.txt`, sitemaps and the bulk export are served as **Workers Static Assets** —
by the platform, not by our script. `run_worker_first` is scoped to `/v1/*`,
`/mcp` and `/openapi.json` only, so the API and MCP can fail without taking the
corpus offline. Agents are the primary audience; putting the thing they read
behind our own code is the one dependency this project cannot justify. A build
gate asserts the surface is fully static.

Not Pages: the Pages 100,000-file ceiling is tied to the **zone** plan (Pro,
$20/mo per domain), not to Workers Paid — buying Workers Paid does not lift the
Pages 20,000 cap. Workers Static Assets gives the same ceiling for $5/mo
account-wide, in one deployment. **Requires wrangler ≥ 4.34.0**: older versions
silently enforce 20,000 whatever the plan says, and fail a 30,000-file deploy with
an error that reads like a billing problem. On the free plan, `run_worker_first`
requests that exceed limits return 429 instead of falling back to asset serving —
don't evaluate the config on free and draw conclusions.

**County case layers are unincorporated-only.** Every record in `GC_Planning`
layers 1/2/15 is a Board of Commissioners decision. City cases are NOT in there.
Addresses reading "DULUTH HIGHWAY" are street names in unincorporated territory,
not the City of Duluth. Never attribute these to a municipality.

**Uncertainty gets flagged, never guessed.** This principle produced the
resolver's confidence band, the applicant review queue, the table quality flags,
and `stats.duluth_extraction`. A visible gap is recoverable; a confident wrong
answer is not.

**Don't expand codes the source doesn't define.** `APC`, `DEN`, `REC` and friends
ship with no data dictionary anywhere in the county's GIS. The site and the API
reproduce them verbatim and link to the record. Guessing at the meaning of a
legal outcome and presenting the guess as fact is exactly the failure mode this
project is built against.

## Architecture decisions and why

**Ingestion runs inside Postgres** via the `http` extension, fetching ArcGIS,
Census TIGERweb, and the repo's own raw URLs. This started as a workaround —
the Cowork sandbox blocked outbound Postgres — but it's genuinely good: no
worker, no credentials in transit. **Locally you have a direct connection, so
prefer psycopg for new work**; keep the in-database loaders for scheduled jobs.

**The site builds from a snapshot, not from the database.** `scripts/export_snapshot.py`
writes `data/snapshot/*.json` (gitignored); the site reads that. Deterministic,
offline-capable, and *diffable* — for a legal-reference index, seeing exactly what
changed between two deploys is worth more than build-time freshness.
`site/fixtures/` is a small committed sample with identical shapes so the site
builds with no database at all, and it says so loudly on every page when it does.

**One implementation behind two surfaces.** `worker/src/tools.ts` holds all five
operations; the REST router and the MCP server both call it. They cannot drift
apart and answer the same question differently.

**Five MCP tools, and adding a sixth needs an argument.** Every tool description
is permanent context tax in every connected client, paid on every turn whether
the tool is called or not.

**Adapter pattern, not per-city scrapers.** 17 jurisdictions can't be 17
hand-written scrapers. Vendors consolidate hard — Municode, ArcGIS REST,
CivicPlus, CivicClerk, BS&A, Accela — so ~6 adapters cover ~90%, and adding a
city is a config file. **Health metric: if a new city needs new *code* rather
than a new *config*, the adapter layer is leaking. Fix it before adding more.**

## Failure modes already hit — do not repeat

These were all *silent*. Each was found by checking something that didn't add up,
not by an error.

- **`\b` in a date regex fails after a letter.** `DuluthAgendaBinder8-10-26.pdf` —
  "r" and "8" are both word chars, so no boundary. Dropped the date on all 80
  agenda binders. Use `(?<!\d)`.
- **Section numbers are 3 digits in UDC Articles 1–9 and 4 digits from Article 10
  on** (`1004.01`). Matching `\d{3}` silently dropped 298 subsections.
- **Case-sensitivity and punctuation vary by body.** Planning Commission writes
  `Case: TA2026-007,`; ZBA writes `Case V2026-001` (no colon); council packets
  write `CASE Z2026-004` in caps. An early-exit guard on the literal `"Case:"`
  skipped every packet — i.e. every decision.
- **Always bound regex capture groups.** An unbounded `.+?` between `Case:` and
  `Request:` ran across a whole staff report: one record came out at 777 KB with
  67,553 chars in the `address` field.
- **pdfplumber's per-row cell lists are not column-stable.** Lot size landed at
  index 1 for RA-200 and index 2 for R-100. Derive columns from clustered
  x-edges, and **rows from each table row's own bbox** — clustering y-edges
  invents extra bands inside multi-line cells and bleeds values between rows.
- **Classify on the principal, not the raw string.** `"PARAN HOMES, LLC C/O
  MAHAFFEY PICKENS TUCKER, LLP"` classified as `law_firm`. Split on `C/O` first,
  or the land-use firm looks like the county's biggest developer.
- **Trigram similarity alone will false-merge.** "CKK DEVELOPMENT SERVICES" and
  "SCI DEVELOPMENT SERVICES" score 0.75 on a shared industry phrase. Auto-merge
  only on tight edit distance; queue the rest.
- **A queue of zero is a bug, not a result.** The OCR pass required `local_path`
  on every row; nothing in the published corpus has that field, so it printed
  `OCR queue: 0`, wrote an output identical to its input, and exited 0. It looked
  for two sessions like a job that was slow. It was a job that never started.
- **Don't relabel a document by its worst page.** OCRing a partially-scanned
  382-page packet and stamping `text_source='ocr'` on it would have recast 449,287
  characters of real publisher text as a reconstruction. Provenance is per-page;
  `mixed` + `ocr_page_numbers` is the honest shape.
- **A silent cap is a silent deletion.** `MAX_PAGES=60` would have dropped 417 of
  the OCR queue's 1,059 pages. Caps default to off and name what they drop.
- **For grants, check the ACL, not the exit code.** `REVOKE` against a grant made
  by another role returns success and changes nothing. Read `pg_proc.proacl`.
- **`cmd && heredoc` swallows the heredoc when `cmd` fails.** A `cd x && cat > f`
  chain silently skipped one migration file. Caught only because every file was
  md5-checked against the database. Write files with absolute paths.
- **Filtering `''` out of an array of markdown lines removes the blank lines.**
  It glued every heading to the paragraph above it. Filter `null` and let `''`
  mean what it says.
- **Measure the claim before printing it.** The "11× token reduction" for `.md`
  twins is really **5.7× on bytes** (median; 3.3–8.7 range). The build now prints
  the measured ratio so the copy can't drift from what ships.
- **"Nearest preceding X" is a guess wearing a fact's clothes.** 431 of 521 motion
  blocks in Duluth minutes are adjournments and budget items with no case at all;
  attaching each vote to the nearest case above it would have stapled them to
  whatever case was last mentioned. The minutes name their own case inside the
  motion — bind to that.
- **A decision without its verb is misleading.** SU2025-001 carried a motion to
  *postpone*; stored as `decision='Motion carried'` that reads as approved. 8 of 68
  extracted actions are not approvals. Keep `motion_action` beside the outcome.
- **When one row must represent many hearings, precedence is a design decision.**
  `coalesce(EXCLUDED, existing)` means "whichever line came last in the file".
  SU2025-004 was approved by the PC and DENIED by Council, and was recorded as
  approved. Rank by evidence quality first (a motion that names its case beats a
  vote merely near one), then recency, and move all decision fields as a set.
- **A citation is not a unique key.** The UDC prints "Table 2-C" twice — residential
  districts on p56, commercial on p70 — and every table also exists a second time as
  a `code_section` row holding the prose around it. Routing on citation alone made
  four records collide; a de-dup guard resolved each collision by keeping whichever
  came first, so `/code/duluth/table-2-b` was a real, well-formed page that did not
  contain Table 2-B. The hand-verified 20-row table was on no page at all.
- **A gate that checks a file exists is not checking the file.** The gate above
  passed while that was true, because the page existed — built by the *other* record.
  Assert the content, not the path.
- **A title that wraps loses its second line.** Table 7-C is "Minimum Distances in
  Feet Required between Trees" *and Structures or Infrastructure by Tree Canopy Size
  Category*. Truncated at the line break it is still grammatical, still plausible,
  and has lost the subject of the table.
- **Two surfaces, one corpus, opposite answers.** The site withheld unverified cell
  values; `worker/src/tools.ts` spread the row and served them — over the surface
  agents actually call. Withholding has to happen once, where the data is shaped.
- **Migrations applied but never committed.** Three of them (`resolver_score_function`,
  `resolver_score_cache`, `duluth_loader_latest_decision_wins`) lived only in the
  database for days. Nothing broke, because production already had them; the damage
  waits for a rebuild. Worse, repo filename order did not match apply order, so
  replaying `db/migrations/` would have applied the date-only decision precedence
  *after* the evidence-ranked one and quietly restored SU2025-004 to "approved".
  `db/verify_migrations.py` now diffs files against the ledger by name and md5.
- **Markdown tables lose the ruling, and the ruling is the data.** Every row-count
  defect in the UDC corpus came from the markdown path mistaking something else for a
  row: a worked *example* below Table 4-A with the same column count (16 rows for a
  6-row table), text lines inside one ruled cell (9-A, 13 for 8), a spanning label
  taken as the header so the header became data (3-A, 7-A, 9-B). `find_tables()` on
  the drawn grid gets all of them right.
- **The UDC draws double borders, so every column counts twice.** 9-B reads as 28
  columns wide for a 14-column table. `snap_x_tolerance=8` — calibrated against seven
  hand-verified counts, where 6 and 10 also work, 2 fails everything, and 14 collapses
  9-B to 11.
- **A rule that does not span the table is not a row boundary.** 2-B's CBD row stacks
  Single-family / Townhouse / Apartment inside its setback columns. Measured, real row
  boundaries span 0.75–1.00 of the table width and in-cell divisions span 0.11–0.34.
  And the UDC draws no full-width lines at all — coverage has to be the *union* of the
  per-cell segments, or every boundary looks like nothing.
- **Pipeline stage order fails silently, in both directions.** Decide empty columns
  before stripping the header or 2-D loses its NAICS column; strip the header before
  folding in-cell divisions or Table 3-A's `0.5` arrives as
  `"Measured in Horizontal\nFootcandles\n0.5"` — a real value with its own column
  heading glued on top.
- **`n_rows` has to mean one thing.** The fixture said 19 for Table 3-B, counting
  printed *lines* in the label column; the table has 9 ruled rows. Every other entry
  counted ruled rows. A DB CHECK ties `n_rows` to the stored row count, so two
  conventions cannot both be right — the convention is now written into the fixture.
- **Overwriting a note deletes the findings in it.** Reloading cells replaced Table
  6-E's `verification_note` and took the Table 6-D ordinance defect with it. Caught by
  the gate that asserts the corpus names the tables the UDC cites but does not
  contain; findings that are not about extraction quality are now preserved explicitly.
- **`python3 -m pkg.mod` runs the module twice under two names.** Once as `pkg.mod`
  via the package `__init__`, once as `__main__`, each with its own module-level
  state. A registry populated by one is empty in the other, and reports empty without
  erroring.
- **Check the "other"/unclassified bucket.** Nearly every silent bug above was
  found by looking at what failed to classify.
- **A file size that doesn't add up is a bug signal.** 3.3 MB for 274 records of
  capped text is how the 777 KB record surfaced.

## Verification habits that paid off

- **Verify against the rendered source, not internal consistency.** Table 2-B
  looked right until I rendered page 52 as an image and compared cell by cell —
  which is how the multi-line bleed showed up after I'd already called it verified.
- **Write the gate before you look at the output.** Both markdown bugs above were
  caught by checks written in advance, on output I'd have skimmed past.
- **Diff the repo against the live schema, not against your memory of it.**
  `code_table.quality` and `land_use_case.applicant_norm` existed only in
  production; a rebuild from `db/migrations` alone produced a loader that errored
  on first use.
- **Keep a regression fixture.** `resolver_probe` scores the resolver against the
  county's own zoning layers. Expected: `confidence='high'` → **100% correct**
  (1,546/1,546). `export_snapshot.py` refuses to write a snapshot if it isn't:

```sql
SELECT coalesce(r.confidence,'unresolved') AS confidence, count(*) probes,
       count(*) FILTER (WHERE r.slug = p.expected_slug) correct
FROM resolver_probe p
LEFT JOIN LATERAL resolve_jurisdiction(ST_X(p.pt), ST_Y(p.pt), 150) r ON true
GROUP BY 1;
```

- **Provenance on every record.** `source_url` + `last_verified`, always. OCR text
  lives in its own field with `text_source='ocr'` because it's a *reconstruction*,
  never a quotation of the record.

## Known gaps

- **5 of 20 UDC tables have unread cells** — 4-B (53 rows), 2-D ×2 (55 each) and
  2-C ×2 (333 and 332). Those five are 828 of the corpus's 997 table rows, so most
  of the *volume* is still unread even though most of the *tables* are done.
  Fifteen tables have been read cell by cell against a rendered page. Every table's column count, header,
  page range and row count now matches `tests/fixtures/duluth_udc_tables.json`, and
  the cells come from the ruled grid rather than markdown. Nothing is `defective`
  any more — that flag asserted the stored values were *known wrong*, which stopped
  being true when they were re-extracted. What is outstanding is that **nobody has
  read most of the cells against the rendered page**, so they stay `unverified` and
  their values are withheld from snapshot, site and API alike.

  The extractor is worth trusting more than the flag suggests: it reproduces
  **492 of 493 cells** of the seven independently hand-transcribed tables, and the
  one disagreement is its own (a stray `(` trailing 2-B's `---(9)`). But agreement on
  seven tables is not evidence about the other eleven, and 2-C alone is 333 rows.
  The worklist is simply:

```sql
SELECT citation, n_rows FROM code_table WHERE quality <> 'verified' ORDER BY n_rows;
```

  Verify against the rendered page, then add the table to `VERIFIED_AGAINST_RENDER`
  in `ingest/pdf/publish_cells.py` — that dict is the only thing that promotes a
  table, and adding a line to it is a claim that a person read the page.
- **A correct extraction can still mislead, and the note is where that gets said.**
  Table 5-A's stacked cells pair from the bottom (six label lines against three
  values, so `40,000 sf` belongs to `RA-200 District`, not to `Minimum Lot Size:`).
  6-B rows 3 and 5 sit under a label cell merged across two ruled rows and are
  meaningless read alone. 7-C rows 2–4 are printed indented beneath a section band and
  the subordination is visual only, so the distances read as unqualified. Superscript
  footnote markers flatten to trailing digits everywhere, so `No minimum lot size3`
  ends in a footnote number rather than a measurement. None of these are extraction
  errors; all of them would mislead a reader who cannot see the page.
- **262 applicant merge candidates await human review** in
  `applicant_merge_candidate` (`decision='pending'`). Developer counts are lower
  bounds.
- **Duluth's 109 cases are a finding aid, not a dataset.** Measured: 67 have a
  "location" with no street number (17 aren't addresses at all — `as presented.`,
  `{J}`), 57 have a "request" that is just the word `ORDINANCE`, 23 have an
  applicant field that ran on into a mailing address, only 13 carry a zoning
  district. Published as `stats.duluth_extraction` and flagged on every affected
  page. The linked PDF is the record; the fields point at it.
- **Duluth minutes are 57–69% scanned** with no text layer — precisely, **83 of
  138 minutes**. The OCR pass (`ingest/duluth_agendas/ocr_scanned.py`) is fixed and
  tested but **has still never been run**: this container has no tesseract and
  cannot reach duluthga.net. Run it locally, then regenerate `duluth_cases.jsonl`.
  Queue is 91 documents / 714 scanned pages — an hour single-threaded, minutes across
  cores. **This is the single highest-value data task left**: it is what turns
  those 109 index entries into records with vote counts.
- **`developer_activity` includes engineering/planning consultants** (Carter
  Engineering, Ridgeline Land Planning) that file as agents without a `C/O`
  marker. The `kind` classifier can't catch that from the name alone — needs a
  manual pass on the top 50.
- **Meeting body text isn't loaded** (12.5 M chars). Only metadata is in
  `meeting_document`.
- **16 municipalities have boundaries but no corpus.** They resolve correctly.

## Next phase

Deployment, the crawler check and the registry listing are all done. What remains:

1. **Move the `net.gwindex` namespace keypair somewhere durable** — it was created
   in a session-temporary scratchpad. Without it the registry entry cannot be
   republished. Keep the apex TXT record; it is used for re-auth.
2. **Redeploy on every data change.** `export_snapshot_rest.py` then `npm run ci`
   then `wrangler deploy`. `SITE_URL` is baked in at build time, so a rebuild is
   not optional. The snapshot went a day stale once and would have published an
   older corpus with every page rendering perfectly.
3. Minutes parser round two: ~36 of 110 Duluth cases still have no outcome, and the
   votes are in text that is now in the database.
4. Read the 11 `unverified` tables' cells against their rendered pages, smallest
   first (5-A is 5 rows, 6-E is 12, 2-C is 333). `ingest/pdf/extract_cells.py`
   produced them and `publish_cells.py` promotes them; the render is the authority.
5. Only then widen: Peachtree Corners and Norcross are mostly config.

## Style

Match the existing code: module docstrings explain *why* a non-obvious approach
was chosen, comments mark the traps above. Don't add ceremony. When something is
uncertain, say so in the data — a `quality` column, a confidence band, a review
queue, a measured counter — rather than in a comment nobody reads.
