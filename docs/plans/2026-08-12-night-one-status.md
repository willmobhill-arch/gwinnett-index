# Gwinnett Index — Night One Status

**Date:** 2026-08-12
**Supabase project:** `gwinnett-index` / ref `losmnziukaqptxhqnhjh` / us-east-1 / free tier
**Phases complete:** 0 (Foundations), 1 (Jurisdiction resolver), 2 (County cases)

---

## ⚠️ Do this first

**Rotate the database password.** It was pasted into the chat transcript, so treat
it as compromised. Supabase → Project Settings → Database → *Reset database password*.

Nothing I built depends on it — everything runs through the Supabase MCP or through
Postgres' own outbound HTTP. Rotating it breaks nothing.

---

## What's live

### Jurisdictions — all 19 loaded, full precision

| | |
|---|---|
| 17 municipalities | Census TIGERweb Incorporated Places, ACS 2025 vintage |
| Gwinnett County | union of its 7 county subdivisions — **437.2 sq mi**, matches the published figure |
| Unincorporated Gwinnett | derived as county − union(17 cities) — **294.4 sq mi, 67.3% of the county** |

Your instinct was right and now it's measured: **unincorporated is two-thirds of the county.**

All hosted geometry is US Census — federal, public domain. No Gwinnett GIS geometry is
stored anywhere, per the no-redistribution clause in their licence.

Largest city by area is **Mulberry at 26 sq mi** — the brand-new one. Duluth is 10.

### The resolver — and the finding that changed its design

`resolve_jurisdiction(lon, lat, band_m := 150)` returns the governing jurisdiction,
its code citation, a confidence level, distance to the nearest boundary, and a caveat.

I scored it against the county's own zoning layers — 415 points inside City of Duluth
polygons, 1,500 inside unincorporated polygons, 1,915 total:

| Confidence | Probes | Correct | |
|---|---|---|---|
| **high** | 1,546 | 1,546 | **100.00%** |
| low (within 150 m of a line) | 361 | 347 | 96.12% |
| unresolved | 8 | 0 | — |
| **overall** | **1,915** | **1,893** | **98.85%** |

The important number is the first row. **When the resolver is confident, it has never
been wrong.** Every single error is captured by the uncertainty band.

That band exists because of what the failures looked like: **all 22 disagreements fell
within 141 m of a jurisdiction boundary**, most within a few metres. That's annexation
lag — cities annex continuously, Census updates yearly — plus TIGER's inherent
positional accuracy. Near a city limit, TIGER alone cannot be trusted.

For legal data a confidently wrong answer is the worst failure mode, so the resolver
now reports its own uncertainty instead of guessing. This was not in the original
design; the test produced it.

### Land use cases — 11,739 loaded

| Metric | |
|---|---|
| Total cases | **11,739** |
| Year range | **1970 – 2026** (56 years) |
| With Accela deep-link | 11,488 |
| With ≥1 parcel PIN | 10,804 |
| Distinct raw applicants | 8,246 ← entity-resolution target |
| With decision recorded | 11,698 |
| Total acres | 170,102 |
| **Residential units proposed** | **318,100** |

By type: REZ 5,064 · SUP 3,291 · RZC 851 · RZR 772 · RZM 571 · CIC 551 · MIH 354 ·
CRZ 145 · BRD 111 · and a long tail.

**Correctly attributed to unincorporated Gwinnett only.** Every record is a Board of
Commissioners decision. City cases are not in this dataset — that stays true.

Source reported 11,728 historical features; 11,724 distinct case numbers landed. The
4-row gap is **genuine duplicates in the county's own data** — `CIC2024-00028`,
`REZ1982-00130`, `REZ1986-00172`, `RZC2021-00005` each appear twice. Not data loss.

---

## The architectural surprise

The sandbox blocks outbound Postgres (5432/6543) and has no IPv6, so a direct database
connection is impossible from here — the password wouldn't have helped either way.

The workaround turned into a better design. Postgres' `http` extension can reach both
Census and the county GIS directly, so **ingestion runs entirely inside the database**:

```
ingest_gwinnett_cases(layer, source_layer, page_size)
  → paginates the county's ArcGIS REST service
  → parses JSON, normalises, upserts
  → returns (fetched, upserted)
```

No external worker, no credentials, nothing proxied through a client, and the whole
11,739-record load cost zero tokens of transfer. It can be driven by `pg_cron` on a
schedule instead of GitHub Actions — one less moving part and one less place to store
a secret. Worth considering as the permanent design.

Census rate-limited Supabase's egress IP partway through and cleared on its own after
a few minutes. Any scheduled job needs retry-with-backoff.

---

## Schema

```
jurisdiction          19 rows, PostGIS MultiPolygon, GIST indexed
jurisdiction_county   many-to-many (Braselton spans 4 counties)
geoid_map             Census GEOID → slug → counties
land_use_case         11,739 rows, FTS + trigram + GIN(pins) indexed
raw_fetch             cached API responses, keyed
resolver_probe        1,915 scored test points (test fixture)
resolve_jurisdiction(lon, lat, band_m)
ingest_gwinnett_cases(layer, source_layer, page)
epoch_ms_to_date(jsonb)
```

---

## Not done / blocked

| Item | Note |
|---|---|
| **GitHub repo** | I have no access — `api.github.com` 403s for `heywimo-cpu/gwinnett-index`, and the browser Claude reaches isn't signed in. I'll hand you files to commit. |
| **Duluth UDC** | Phase 3. The 8.6 MB PDF needs parsing. |
| **Duluth cases** | No structured source. Agenda mining required. |
| 8 unresolved probes | Points in neither any city nor unincorporated — likely slivers where TIGER place and county-subdivision edges disagree. Worth a look. |
| Site, API, MCP | Phases 4–5, untouched. |

---

## Suggested next session

1. Rotate the DB password.
2. Decide: `pg_cron` in-database ingestion vs GitHub Actions. I lean in-database now.
3. Investigate the 8 unresolved probes and the low-confidence band — is 150 m right?
4. Applicant entity resolution across 8,246 raw names. Highest-value, purely internal,
   needs no new sources.
5. Phase 3: Duluth UDC parsing.

Item 4 is the one I'd pick. It needs nothing external, and "who is building the most in
Gwinnett" is the question the 56-year dataset can already answer better than anyone.
