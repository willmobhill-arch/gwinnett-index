# Gwinnett Index — Build Plan

**Date:** 2026-08-12
**Test case:** Unincorporated Gwinnett County + City of Duluth
**Companion doc:** `2026-08-12-gwinnett-index-design.md`

Work top to bottom. Each phase ends with something checkable. Do not start a phase
until the previous phase's exit criteria pass.

---

## Phase 0 — Foundations (½ day)

### 0.1 Accounts and repo

- [ ] Register a domain. Suggestions: `gwinnettindex.com`, `gwinnettindex.org`.
      Buy at Cloudflare Registrar (at-cost, no markup) — this also puts DNS where
      the hosting will be.
- [ ] Create Cloudflare account (free tier).
- [ ] Create GitHub repo `gwinnett-index`, private for now.
- [ ] Create Supabase project, region `us-east-1`. Save the connection string and
      the `service_role` key into GitHub Actions secrets, never into the repo.

### 0.2 Repo skeleton

```
gwinnett-index/
├── ingest/
│   ├── adapters/            # one module per VENDOR, not per city
│   │   ├── __init__.py      # ADAPTER_REGISTRY
│   │   ├── base.py          # discover/fetch/parse/normalize/upsert contract
│   │   ├── arcgis.py
│   │   ├── municode.py
│   │   ├── pdf_code.py
│   │   ├── agenda_revize.py
│   │   ├── agenda_liferay_bac.py
│   │   └── accela.py
│   ├── jurisdictions/       # one YAML per jurisdiction — the config layer
│   │   ├── gwinnett-county.yaml
│   │   └── duluth.yaml
│   ├── models.py            # pydantic schemas, shared by all adapters
│   ├── provenance.py        # source_url / first_seen / last_verified stamping
│   └── run.py               # CLI: python -m ingest.run --jurisdiction duluth
├── db/migrations/           # numbered .sql files
├── site/                    # Astro
├── worker/                  # Cloudflare Worker: REST API + MCP server
├── tests/fixtures/          # recorded HTTP responses — adapters test offline
└── .github/workflows/
```

- [ ] `pyproject.toml` with: `httpx`, `pydantic`, `pyyaml`, `psycopg[binary]`,
      `pymupdf` (PDF text + layout), `shapely`, `tenacity` (retries),
      `structlog`. Use `uv` for speed.

**Exit criteria:** repo pushed, Supabase reachable from a local script.

---

## Phase 1 — Jurisdiction resolver (1 day)

This is the product's spine. Build it first, before any case data.

### 1.1 Boundaries from Census TIGER

- [ ] Download TIGER/Line 2025 Places for Georgia:
      `https://www2.census.gov/geo/tiger/TIGER2025/PLACE/tl_2025_13_place.zip`
- [ ] Download TIGER County subdivisions / county boundary for Gwinnett (FIPS 13135).
- [ ] Load into PostGIS. **Public domain — this is the only geometry we host.**

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE jurisdiction (
  id            serial PRIMARY KEY,
  slug          text UNIQUE NOT NULL,
  name          text NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('county','municipality','unincorporated')),
  fips_place    text,
  boundary      geometry(MultiPolygon, 4326),
  code_citation text,
  created_at    timestamptz DEFAULT now()
);
CREATE INDEX ON jurisdiction USING GIST (boundary);

-- many-to-many: Braselton spans 4 counties, Loganville 2, Auburn 2, Rest Haven 2
CREATE TABLE jurisdiction_county (
  jurisdiction_id int REFERENCES jurisdiction(id),
  county_fips     text NOT NULL,
  PRIMARY KEY (jurisdiction_id, county_fips)
);
```

- [ ] Derive **unincorporated Gwinnett** as a real geometry:
      `ST_Difference(gwinnett_county_boundary, ST_Union(all 17 city boundaries))`.
      Store it as a first-class jurisdiction row. This is what makes the resolver
      able to say "unincorporated" affirmatively rather than by elimination.

### 1.2 The resolver

```sql
CREATE FUNCTION resolve_jurisdiction(lon float8, lat float8)
RETURNS TABLE (slug text, name text, kind text, code_citation text) AS $$
  SELECT j.slug, j.name, j.kind, j.code_citation
  FROM jurisdiction j
  WHERE ST_Contains(j.boundary, ST_SetSRID(ST_Point(lon, lat), 4326))
  ORDER BY (j.kind = 'municipality') DESC   -- city wins over county
  LIMIT 1;
$$ LANGUAGE sql STABLE;
```

- [ ] Geocoding: use the county's own public geocoder
      (`gis3.gwinnettcounty.com/.../GC_AddressLocationService`) with Census Geocoder
      as fallback. Cache every result — never geocode the same string twice.
- [ ] PIN lookup path: PIN → parcel centroid (proxied live from county GIS) → resolver.

### 1.3 Prove it

- [ ] Build a test set of **20 known addresses**: 10 inside Duluth city limits, 10 with
      a Duluth mailing address but in unincorporated county. Source them from the
      county's own zoning layers, which already carry the correct answer.
- [ ] Assert 20/20 correct. Commit as `tests/test_resolver.py`.

**Exit criteria:** given any Gwinnett address, you return the correct governing
jurisdiction with a citation to the boundary source. 20/20 on the test set.

---

## Phase 2 — Unincorporated Gwinnett cases (1–2 days)

The highest-value dataset in the project, and the easiest to get.

### 2.1 Schema

```sql
CREATE TABLE land_use_case (
  id                 bigserial PRIMARY KEY,
  jurisdiction_id    int REFERENCES jurisdiction(id),
  case_number        text NOT NULL,
  case_type          text,          -- REZ | RZM | SUP | VAR | CIC ...
  year               int,
  status             text,
  applicant_raw      text,
  applicant_id       int,           -- FK, populated in Phase 6
  existing_zone      text,
  proposed_zone      text,
  approved_zone      text,
  acres              numeric,
  proposed_use       text,
  res_units          int,
  nonres_sqft        numeric,
  staff_rec          text,
  pc_date            date,
  pc_rec             text,
  decision_date      date,
  decision           text,
  conditions_text    text,          -- Phase 6, from agenda packets
  location_text      text,
  pins               text[],
  source_url         text NOT NULL,
  source_system      text NOT NULL,
  first_seen         timestamptz DEFAULT now(),
  last_verified      timestamptz DEFAULT now(),
  UNIQUE (jurisdiction_id, case_number)
);
CREATE INDEX ON land_use_case USING GIN (to_tsvector('english',
  coalesce(applicant_raw,'') || ' ' || coalesce(proposed_use,'') || ' ' || coalesce(location_text,'')));
```

### 2.2 The ArcGIS adapter

Verified endpoints — all anonymous, no auth:

```
BASE = https://gis3.gwinnettcounty.com/mapvis/rest/services/GISDataBrowser/GC_Planning/MapServer

  /2   Historical Zoning Cases   11,728 records   ← the prize
  /1   Current Zoning Cases          15 records
  /15  Active Variance Cases         10 records
  /5   Unincorporated Zoning      7,322 polygons
  /12  Municipal Zoning           5,268 polygons (all 17 cities)
  /0   Zoning Overlay Districts
  /6   2045 Daily Communities
  /7   2045 Future Development
```

- [ ] Write `adapters/arcgis.py`. Must handle `maxRecordCount: 2000` — paginate with
      `resultOffset` + `resultRecordCount`, ordered by `OBJECTID`. Do **not** request
      geometry on the bulk pull (`returnGeometry=false`); it is 5× the payload and we
      don't host it anyway.
- [ ] Map the verified field names straight through:
      `CASENUM, YEAR, PENDING, STATUS, APPLICANT, PROPOSED_USE, EXISTING_ZONE,
      PROPOSED_ZONE, APPROVED_ZONE, ACRES, STAFF_REC, PC_REC, PC_DATE, BOC_DEC,
      BOC_DATE, BOC_HEARING_DATE, LOCATION_1..3, PIN..PIN_5, RES_UNITS,
      NONRES_SQFEET, GCIDNUM, PDF_APPLICATION`
- [ ] `PDF_APPLICATION` (alias "ACA Link") is a **direct deep-link into Accela**.
      Store it verbatim as `source_url`. This is what makes every case citable.
- [ ] Collapse `PIN` … `PIN_5` into the `pins[]` array; `LOCATION_1..3` into
      `location_text`.
- [ ] ArcGIS dates are epoch **milliseconds**. Convert, and watch for nulls and
      sentinel zeros.

### 2.3 Correctness guards

- [ ] **Every record in layers 1/2/15 is a Board of Commissioners decision — these are
      unincorporated county only.** Do not tag them with a city jurisdiction. Verified:
      searching `LOCATION_1` for "DULUTH" returns 91 hits, all of which are street
      names (`DULUTH HIGHWAY`, `OLD DULUTH ROAD`), not City of Duluth cases.
- [ ] Assert the pull lands at 11,728 ± natural growth. A large drop means the source
      changed shape — fail the job loudly rather than writing a truncated table.

**Exit criteria:** 11,728 cases in Postgres, each with a working Accela URL, correctly
attributed to unincorporated Gwinnett. Spot-check 10 against the live portal.

---

## Phase 3 — Duluth (2–3 days)

The hard one, and the differentiator. No structured case source exists.

### 3.1 UDC text

- [ ] Scrape the index page for the link pattern `UDC_ADOPTED_.*\.pdf` — **never
      hardcode the URL**. The filename encodes adoption and amendment dates
      (currently `UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf`, 8.6 MB) and changes on
      every amendment. The changing filename *is* your change-detection signal.
- [ ] Parse with PyMuPDF. Digital-born, so text extraction works — no OCR needed.
- [ ] Split into sections on the article/section heading pattern. Preserve tables
      (setbacks and dimensional standards live in tables and are the most-queried
      content in the whole corpus).
- [ ] Store each section with `citation`, `adopted_date`, `amended_through`,
      `source_url`, `page_range`.

```sql
CREATE TABLE code_section (
  id              bigserial PRIMARY KEY,
  jurisdiction_id int REFERENCES jurisdiction(id),
  citation        text NOT NULL,       -- "Duluth UDC § 4.2.1"
  title           text,
  body_md         text,
  parent_citation text,
  adopted_date    date,
  amended_through date,
  source_url      text NOT NULL,
  page_range      int4range,
  last_verified   timestamptz DEFAULT now(),
  UNIQUE (jurisdiction_id, citation)
);
```

- [ ] Also pull Duluth's non-zoning Code of Ordinances via the Municode adapter
      (client `1976`, product `12344`). Skip node `PTIIIUNDECO` — Part III is a stub
      that just links out to the PDF.

### 3.2 Duluth cases via agenda mining

No case tracker exists. GovBuilt 403s non-browser clients. So derive cases from the
public record instead:

- [ ] Scrape Planning Commission and Mayor & Council agendas/minutes from
      `duluthga.net` (Revize CMS). Filenames are inconsistent — match on the linked
      text and date, not the filename.
- [ ] Extract case-shaped items with an LLM pass over each agenda: case number,
      applicant, address/PIN, request, recommendation, action. Structured output,
      one row per item.
- [ ] **Always keep the source PDF URL and page number.** Every extracted field must
      be traceable to a document a human can open.
- [ ] Flag low-confidence extractions for review rather than publishing them silently.

### 3.3 Duluth zoning

- [ ] Proxy Duluth's own layer (`services7.arcgis.com/ZTAeUzNBWlnSi6by/.../FeatureServer/150`,
      9,873 parcels, field `UDC_Zoning`, layer is actually named `Zoning2026`).
- [ ] Fallback to the county's harmonized view (`GC_Planning/12` where
      `JURISDICTION='DULUTH'`, 415 polygons) when Duluth's is down.
- [ ] **Query live, cache briefly, never mirror.**

**Exit criteria:** Duluth UDC queryable by citation with correct dates; ≥2 years of
Duluth cases extracted from agendas with source links; zoning lookup working for a
Duluth address.

---

## Phase 4 — The site (3–4 days)

### 4.1 Astro build

- [ ] `npm create astro@latest site -- --template minimal`. No UI framework — this is
      a content site. Astro ships zero JS by default, which is exactly right.
- [ ] Pull from Supabase at build time. Generate:
      - `/` — one search box: *type an address*
      - `/j/{slug}/` — jurisdiction page (code, plan, boards, vendor links, freshness)
      - `/case/{jurisdiction}/{case_number}/`
      - `/parcel/{pin}/`
      - `/code/{jurisdiction}/{citation}/`
      - `/feed/` — the weekly pipeline feed
- [ ] **Markdown twins.** For every route, emit a `.md` sibling with YAML frontmatter
      (`title, jurisdiction, effective_date, source_url, as_of`). This is the single
      highest-leverage agent feature — an 11× token reduction on the same content.
- [ ] Search: Pagefind (static, no server) for the site; Postgres FTS behind the API.

### 4.2 Design

Quiet and typographic. System font stack or one variable serif. Generous whitespace.
No hero image, no gradient, no card grid. The county already has six ArcGIS viewers —
do not build a seventh. Every page answers its question above the fold.

Jurisdiction is always stated first, in a bordered callout, before any substance:

> **Governing jurisdiction: Unincorporated Gwinnett County**
> This address has a Duluth mailing address but is **not** in the City of Duluth.
> It is governed by the Gwinnett County UDO, heard by the County Planning Commission.

### 4.3 Agent surface

- [ ] `/robots.txt` — affirmative `Content-Signal: search=yes, ai-input=yes, ai-train=yes`,
      explicit `Allow: /` for GPTBot, ClaudeBot, OAI-SearchBot, Claude-SearchBot,
      PerplexityBot, Google-Extended, CCBot. Sitemap declared.
- [ ] `/llms.txt` at root + per-jurisdiction. Include an `## Instructions` section
      that states the jurisdiction trap and requires citing `effective_date`.
- [ ] Sitemap index, sharded by jurisdiction and year. Accurate `lastmod`; omit
      `changefreq` and `priority` (ignored by every consumer, and noise).
- [ ] JSON-LD: `Legislation` on code sections, `Dataset`/`DataCatalog` on collections,
      `sdPublisher` + `isBasedOn` to declare mirror status honestly.
- [ ] `/catalog.jsonld` (DCAT-US 3) **and** `/data.json` (Project Open Data 1.1).
- [ ] `/bulk/corpus.jsonl.gz` — full corpus, one object per line.
- [ ] Headers: `Access-Control-Allow-Origin: *`, `ETag`, `Last-Modified`, honor
      conditional requests and return 304.

### 4.4 The check that everyone forgets

- [ ] **Verify Cloudflare Bot Fight Mode is OFF for content paths.** It silently 403s
      AI crawlers regardless of what robots.txt says. Test and assert 200:

```bash
curl -sI -A "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.4; +https://openai.com/gptbot" https://YOURDOMAIN/j/duluth/
curl -sI -A "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)" https://YOURDOMAIN/j/duluth/
```

Make this a CI check, not a one-time manual step.

**Exit criteria:** site live; a GPTBot-UA request returns 200; every page has a working
`.md` twin; bulk export downloads and parses.

---

## Phase 5 — API and MCP server (2 days)

- [ ] Cloudflare Worker, Streamable HTTP transport. **No auth** — every auth
      requirement is a client that won't connect.
- [ ] Five tools only. Every tool description is permanent context tax in every client:

```
resolve_jurisdiction(address | pin)   → governing jurisdiction + boundary source
                                        ALWAYS CALL FIRST
search_cases(query, jurisdiction?, case_type?, date_range?, zone?)
get_case(case_number)
get_code_section(jurisdiction, citation)
list_jurisdictions()
```

- [ ] Use the `instructions` field on `initialize` — it's free, always-loaded guidance.
      Put the jurisdiction trap and the dating requirement there.
- [ ] Every response carries `source_url`, `effective_date`, `as_of`.
- [ ] REST API mirrors the same five operations. Publish `/openapi.json`, advertise it
      with `Link: </openapi.json>; rel="service-desc"`.
- [ ] Publish to `registry.modelcontextprotocol.io` as `org.<yourdomain>/gwinnett-index`.

**Exit criteria:** MCP `initialize` handshake succeeds from a clean client with no
credentials; all five tools return correct data; listed in the registry.

---

## Phase 6 — Automation and depth (ongoing)

### 6.1 Scheduled ingestion

- [ ] GitHub Actions cron:
      - Daily 06:00 ET — county current cases + variances (layers 1, 15). Small, cheap.
      - Weekly Mon — full historical resync, Municode supplements, code PDF hash check.
      - Weekly Sun — Duluth agenda scrape.
- [ ] Rebuild the site on data change (Cloudflare Pages deploy hook).
- [ ] **Freshness dashboard** at `/status` — per-source last-success, record counts,
      and staleness. Publish failures openly. A civic index that hides staleness is
      worse than one that admits it.

### 6.2 The moat

- [ ] **Applicant entity resolution.** Normalize and cluster `APPLICANT` across 11,728
      records ("Pulte Home Company LLC" / "Pulte Homes" / "PULTE HOME CO" → one entity).
      Start with normalization + trigram similarity, then hand-review the top 200 by
      case count. Ship `/developer/{slug}` profile pages.
- [ ] **Conditions extraction.** County agenda packets live at the verified pattern
      `gwinnettcounty.com/static/upload/bac/{bodyId}/{YYYYMMDD}/ap_{docId}_{name}.pdf`
      (body `52` = Board of Commissioners). The actual conditions of zoning approval
      are in these PDFs and in no database anywhere. Extract them into
      `land_use_case.conditions_text`. **This is the moat.**

### 6.3 Rollout to the other 16

Only after the Duluth + unincorporated pair is stable. Order by effort, not by size:

1. **Peachtree Corners** — Municode UDO + live `Zoning_Cases` ArcGIS layer (151) +
   CivicPlus AgendaCenter + BS&A. Easiest city in the county; mostly config.
2. **Norcross** — Municode UDO + `Public_Hearing_Cases` layer + CivicClerk.
3. **Lawrenceville, Sugar Hill, Snellville** — largest remaining; vendor stacks need research.
4. **Suwanee** — needs a headless-browser adapter (Akamai) or an open-records request.
5. **Buford** — 18 zoning PDFs, no case tracker. Agenda mining only.
6. **Mulberry** — new city; track its code as it is written.
7. **Lilburn, Dacula, Grayson, Berkeley Lake, Rest Haven** — thin pages, county-sourced zoning.
8. **Braselton, Auburn, Loganville** — cross-county. These pull you into Barrow, Hall,
   Jackson, and Walton, which is the natural expansion path beyond Gwinnett.

Track adapter reuse as the health metric. If a new city needs new *code* rather than a
new *config file*, the adapter layer is leaking and should be fixed before continuing.

---

## Verification gates

Do not skip these. They are what separate an index people trust from one they don't.

| Gate | Check |
|---|---|
| Resolver accuracy | 20/20 on the Duluth-vs-unincorporated address test set |
| Case integrity | Count matches source ± growth; 10 random Accela links resolve |
| Code freshness | PDF hash + filename compared weekly; alert on change |
| Agent access | GPTBot and ClaudeBot user-agents both return 200 in CI |
| Markdown twins | Every route in the sitemap has a `.md` returning 200 |
| Provenance | No published record lacks `source_url` and `last_verified` |
| Legal | No county-sourced parcel/zoning geometry in any hosted table or export |
| Link rot | Weekly crawl of all `source_url` values; report, don't silently drop |

---

## Effort estimate

| Phase | Effort |
|---|---|
| 0 — Foundations | ½ day |
| 1 — Jurisdiction resolver | 1 day |
| 2 — County cases | 1–2 days |
| 3 — Duluth | 2–3 days |
| 4 — Site | 3–4 days |
| 5 — API + MCP | 2 days |
| **To public launch** | **~2 weeks of focused work** |
| 6 — Automation + moat | Ongoing |

Running cost at this scale: domain (~$10/yr) plus $0 — Cloudflare Pages/Workers,
Supabase, and GitHub Actions all sit inside free tiers.
