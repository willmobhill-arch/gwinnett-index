# Gwinnett Index

A machine-readable index of zoning, land-use, and development records for Gwinnett
County, Georgia and its 17 municipalities. Built for AI agents first, humans second.

## Why this exists

A "Duluth, GA" mailing address is usually **not** in the City of Duluth. It's in
unincorporated Gwinnett — a different code, a different board, a different permit
portal. Nothing on the internet resolves an address to its *governing* jurisdiction
before answering a zoning question, so every AI assistant answering "what's the
setback in Duluth GA" today is guessing.

Unincorporated Gwinnett is **67.3%** of the county's land area. Getting this wrong
is the default, not the edge case.

## What's here

| Dataset | Records | Source |
|---|---|---|
| Jurisdiction boundaries | 19 (county + unincorporated + 17 cities) | US Census TIGER — public domain |
| County zoning cases | 11,739 (1970–2026) | Gwinnett `GC_Planning` ArcGIS |
| Resolved applicants | 7,369 (from 8,246 raw spellings) | derived |
| Duluth UDC | 860 sections, 18 tables | city PDF, 426 pp |
| Duluth meeting documents | 356 (7,878 pp, 2023–2026) | duluthga.net |
| Duluth land-use cases | 109 distinct, 64 with vote records | agenda mining |

## Setup — one time

The repo already has a starter README, so clone first and copy in — that avoids a
push conflict:

```bash
git clone https://github.com/willmobhill-arch/gwinnett-index.git
tar -xzf gwinnett-index-repo.tar.gz -C gwinnett-index      # overwrites the stub README
cd gwinnett-index
git add -A && git commit -m "Gwinnett Index: pipeline, schema, and extracted corpora"
git push
```

Then, with the repo **public**, load the corpora. Postgres fetches them itself —
you don't run anything locally, and no credential is involved:

```sql
-- set to your repo's raw base
-- https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index/main/data/

SELECT load_udc_sections_from_url(
  'https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index/main/data/udc_sections.jsonl');

SELECT * FROM load_duluth_cases_from_url(
  'https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index/main/data/duluth_cases.jsonl');

SELECT load_meeting_docs_from_url(
  'https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index/main/data/duluth_meeting_docs.jsonl');
```

Expected: 860 sections, 228 case rows (109 distinct), 356 meeting documents.

## Architecture

Ingestion runs **inside Postgres** via the `http` extension — it fetches the
county's ArcGIS REST services, Census TIGERweb, and this repo's own raw URLs
directly. No external worker, no credentials in transit, and the whole 11,739-case
county load moves zero bytes through a client.

```
ingest/
  duluth/          UDC PDF -> 860 sections + 18 tables (extract_udc, extract_tables)
  duluth_agendas/  crawl -> OCR -> parse case items from agendas/minutes/packets
scripts/           standalone loaders for environments with direct PG access
data/              extracted corpora, fetched by the SQL loaders above
docs/plans/        design doc, build plan, status
```

### The adapter pattern

17 jurisdictions cannot be 17 hand-written scrapers. The vendor landscape
consolidates hard — Municode, ArcGIS REST, CivicPlus, CivicClerk, BS&A, Accela —
so roughly six adapters cover ~90% of them, and adding a city is a config file.
Health metric: **if a new city needs new code rather than a new config, the
adapter layer is leaking.**

## Data quality, stated honestly

- **Jurisdiction resolver**: scored on 1,915 probe points from the county's own
  zoning layers. At `confidence='high'` it is correct **1,546/1,546 — 100%**.
  Every error falls inside the low-confidence band. All 22 disagreements were
  within 141 m of a boundary (annexation lag; Census updates yearly).
- **Duluth UDC**: 97.3% raw text coverage; the gap is stripped heading lines,
  leaving 591 unexplained characters across 426 pages.
- **UDC Table 2-B** (dimensional standards) is verified cell-for-cell against the
  rendered source page. The other 17 tables are extracted but **not spot-checked**,
  and Table 2-B's merged PUD/CBD rows remain unreliable. Flags are in the data.
- **Duluth minutes**: 57–69% are scanned with no text layer (printed, signed,
  re-scanned). OCR text is stored separately with `text_source='ocr'` and is a
  reconstruction, never a quotation of the record.
- **Applicant resolution**: 271 variants merged on tight edit distance; **262
  lower-confidence pairs are queued for human review rather than merged on a
  guess.** A split entity is visibly wrong; a wrongly merged one looks
  authoritative and is invisible.

## Legal posture

| Content | Posture | Basis |
|---|---|---|
| Ordinance / plan text | Mirror in full | *Georgia v. Public.Resource.Org* (2020) — edicts of government |
| Case records | Mirror in full | Facts; Georgia Open Records Act |
| County parcel/zoning geometry | **Proxy only, never rehost** | Gwinnett GIS licence forbids redistribution |
| Jurisdiction boundaries | Host | US Census TIGER — public domain |
| IBC/IRC base text | **Never** | ICC copyright; index Georgia amendments only |

This index is a mirror and derived analysis, not the system of record. Every
record carries `source_url` and `last_verified`.

Published under CC0.
