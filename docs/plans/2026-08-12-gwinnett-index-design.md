# Gwinnett Index — Design

**Date:** 2026-08-12
**Status:** Approved for build planning
**Scope:** Gwinnett County, GA + all 17 municipalities

---

## 1. What this is

A machine-readable index of zoning, land-use, and development records for Gwinnett
County, Georgia and every city inside it. Two audiences, one corpus:

- **Agents** — AI assistants, research agents, and automated pipelines that need
  correct, dated, citable answers about Gwinnett land use. Served via clean HTML,
  markdown twins, structured data, bulk export, and a public MCP server.
- **Humans** — developers, brokers, builders, civil engineers, land-use attorneys,
  and residents who want to know what is being filed, heard, and approved. Served
  via a fast, quiet, feed-shaped web portal.

The product is **the development pipeline**: who filed what, where, and what happened.
Code and plan text is the supporting reference layer, not the headline.

---

## 2. The core insight

**Jurisdiction resolution is the product.**

A "Duluth, GA" mailing address is usually *not* in the City of Duluth. The 30096/30097
ZIPs sprawl across unincorporated Gwinnett, which is governed by an entirely different
code, heard by a different board, and permitted through a different portal. Verified:

| | City of Duluth | Unincorporated Gwinnett |
|---|---|---|
| Governing law | Duluth UDC (single PDF, adopted 2025-09-08, amended 2026-07-13) | Gwinnett UDO (Municode Appendix A) |
| Rezoning path | Duluth Planning Commission → Mayor & Council | County Planning Commission → Board of Commissioners |
| Appeals | Duluth ZBA | County ZBA |
| Permits | GovBuilt + legacy iWorQ | Accela ZIP Portal |
| Zoning GIS | Duluth ArcGIS org, 9,873 parcels, field `UDC_Zoning` | County `GC_Planning/5`, 7,322 polygons |
| Agendas | Revize CMS | Liferay "BAC" portlet, body 52 |
| Comp plan | 2024 Duluth Comprehensive Plan | 2045 Gwinnett Unified Plan |

This holds for all 17 cities. Every AI assistant answering "what's the setback in
Duluth GA" today is guessing, because nothing on the internet resolves address →
*governing* jurisdiction before answering.

**Design rule:** every parcel, address, and case page states its governing jurisdiction
explicitly and prominently, before any substantive answer. The API and MCP server
refuse to answer a zoning question without first resolving jurisdiction.

Boundaries come from **Census TIGER/Line Places** — federal, public domain, zero
license encumbrance — not from county GIS. This sidesteps the Gwinnett redistribution
clause entirely for the one layer we genuinely must host ourselves.

---

## 3. Scope and tiering

**Test case: unincorporated Gwinnett + City of Duluth.** These two are the proving
pair, chosen deliberately. They sit adjacent, share a mailing address, and are governed
by completely separate systems — so they exercise every hard problem in the project at
once: jurisdiction resolution, a structured county pipeline, an unstructured city
pipeline, PDF code parsing, agenda mining, and the proxy-vs-mirror legal split. If the
adapter pattern handles this pair cleanly, the remaining 16 are configuration.

Full scope, 17 jurisdictions confirmed present in the county's `GC_Planning/12` layer,
with zoning polygon counts as a size proxy:

| Tier | Jurisdiction | Polygons | Why this tier |
|---|---|---|---|
| **0** | **Unincorporated Gwinnett** | 7,322 | 11,728 historical cases, Accela deep-links, Municode UDO, structured everything. More than half the total value. |
| **1** | Peachtree Corners | 489 | Municode UDO + own ArcGIS with a live `Zoning_Cases` layer (151) + CivicPlus AgendaCenter + BS&A + an open data hub. Easiest city in the county. |
| **1** | Norcross | 353 | Municode UDO + own ArcGIS + `Public_Hearing_Cases` layer + CivicClerk agendas. Second easiest. |
| **2** | Lawrenceville | 733 | Largest city, county seat. Vendor stack needs research. |
| **2** | Sugar Hill | 419 | Larger than Duluth. Not in original scope — should be. |
| **2** | Snellville | 417 | Mid-size, vendor stack needs research. |
| **2** | Duluth | 415 | Zoning law is one 8.6 MB PDF. High effort, high differentiation. |
| **2** | Suwanee | 401 | Akamai bot management blocks server-side clients entirely. Needs headless browser or open-records request. BS&A permits (same adapter as PTC). |
| **3** | Mulberry | 641 | **New city, approved May 2024.** Code being written now — index it as it forms. |
| **3** | Buford | 655 | 18 separate zoning PDFs with dates in filenames. No case tracker at all. |
| **3** | Lilburn | 208 | Small, needs research. |
| **3** | Dacula | 197 | Small, needs research. |
| **3** | Grayson | 112 | Small, needs research. |
| **3** | Braselton | 91 | **Spans 4 counties** (Barrow, Gwinnett, Hall, Jackson). |
| **3** | Loganville | 71 | **Spans Gwinnett + Walton.** |
| **3** | Berkeley Lake | 45 | Tiny. |
| **3** | Auburn | 10 | **Spans Barrow + Gwinnett.** Nearly all of it is outside Gwinnett. |
| **3** | Rest Haven | 10 | Tiny. Spans Gwinnett + Hall. |

Cross-county cities force `jurisdiction` ↔ `county` to be many-to-many in the schema
from day one. They are also the natural expansion path outward into Barrow, Hall,
Jackson, and Walton.

---

## 4. Architecture

**Static surface + edge database.** Chosen over static-only (no query layer, caps the
commercial half) and full dynamic app (server-rendered pages are what AI crawlers most
often fail to fetch, and it isn't low-touch).

```
  SOURCES                INGEST                  STORE              SERVE
  ────────               ──────                  ─────              ─────
  ArcGIS REST  ─┐
  Municode API ─┤    GitHub Actions          Supabase           Astro SSG
  Agenda vendors├──▶ (cron, Python)  ──────▶ Postgres   ──────▶ → Cloudflare Pages
  Permit portals┤    adapter registry         + PostGIS         (HTML + .md twins)
  DCA PDFs     ─┤    + jurisdiction YAML      + FTS                    │
  Census TIGER ─┘                             + Storage        Cloudflare Worker
                                                               → REST API
                                                               → MCP server
```

**Why each piece:**

- **Supabase Postgres** — you already have an account connected. PostGIS gives real
  point-in-polygon jurisdiction resolution; full-text search comes free; PostgREST
  gives an auto-generated API; auth and RLS are there when the paid tier arrives.
  Free tier is ample at this data volume.
- **Astro static build** — server-rendered HTML at build time is the single highest-impact
  thing for agent readability. No JS required to read a page.
- **Cloudflare Pages + Workers** — free static hosting, and Workers is where the MCP
  server and API live. Must verify Bot Fight Mode is **off** for content paths, or it
  will silently 403 GPTBot and ClaudeBot regardless of robots.txt.
- **GitHub Actions** — the entire scheduler. No servers to run.

---

## 5. The adapter pattern

This is the change the 17-jurisdiction scope forces, and the most important decision
in the design.

**You cannot hand-write and maintain 17 scrapers.** Instead: a small library of
*vendor* adapters plus one declarative YAML config per jurisdiction. Adding a city
becomes writing a config file, not writing code.

The vendor landscape consolidates hard — verified across the six researched jurisdictions:

| Vendor | Jurisdictions | Adapter effort |
|---|---|---|
| **ArcGIS REST** | All 17 (county publishes municipal zoning for every city) | One adapter, highest leverage |
| **Municode** (undocumented but open JSON API) | Duluth, Suwanee, Norcross, PTC, Buford, Gwinnett, + likely most others | One adapter, 6+ jurisdictions |
| **CivicPlus AgendaCenter** | Peachtree Corners, Norcross (legacy) | One adapter |
| **CivicClerk** | Norcross (current) | One adapter |
| **BS&A Online** | Suwanee (uid 2338), Peachtree Corners (uid 2417) | One adapter, 2+ |
| **Accela ACA** | Gwinnett County | One adapter, deep-linkable from GIS |
| **Generic PDF code** | Duluth (1 file), Buford (18 files) | One adapter, config-driven |
| **Granicus / Revize / Drupal / Liferay** | Suwanee / Duluth / Buford / County | Thin HTML scrapers |

Roughly **six adapters cover about 90% of seventeen jurisdictions.**

Example jurisdiction config (`ingest/jurisdictions/duluth.yaml`):

```yaml
slug: duluth
name: City of Duluth
type: municipality
counties: [gwinnett]
fips_place: "1324768"        # Census TIGER join key for boundary

code:
  adapter: pdf_code
  source_page: https://www.duluthga.net/services/planning___development/ordinances___regulations.php
  link_pattern: 'UDC_ADOPTED_.*\.pdf'
  citation_style: "Duluth UDC"
  adopted: 2025-09-08
  amended_through: 2026-07-13

ordinances:
  adapter: municode
  client_id: 1976
  product_id: 12344
  excludes: [PTIIIUNDECO]     # Part III is a stub; real UDC is the PDF

zoning_geometry:
  adapter: arcgis
  mode: proxy                 # query live, never mirror
  url: https://services7.arcgis.com/ZTAeUzNBWlnSi6by/arcgis/rest/services/Zoning2024/FeatureServer/150
  district_field: UDC_Zoning
  pin_field: PIN
  fallback:                   # county's harmonized view
    url: https://gis3.gwinnettcounty.com/mapvis/rest/services/GISDataBrowser/GC_Planning/MapServer/12
    where: "JURISDICTION='DULUTH'"

cases:
  adapter: agenda_mining      # no structured tracker exists
  bodies:
    - {name: Planning Commission, url: .../planning_commission_agendas___minutes.php}
    - {name: Mayor & Council,     url: .../mayor___council_agendas___minutes.php}

permits:
  adapter: govbuilt
  url: https://duluthga.govbuilt.com/
  notes: 403s non-browser user agents; needs headless or is deferred

comp_plan:
  adapter: dca_pdf
  url: https://dca.georgia.gov/document/plans/2024-duluth-comprehensive-plan/download
  adopted: 2024
```

Every adapter implements the same contract: `discover() → fetch() → parse() →
normalize() → upsert()`, emits provenance on every record, and is independently
testable against a recorded HTTP fixture.

---

## 6. Data model

The **case** is the atom. Everything hangs off it.

```
jurisdiction ──many-to-many── county
     │
     ├── boundary (Census TIGER, PostGIS geometry)  ← the only geometry we host
     ├── code_section ── plan
     │
parcel (PIN) ──── case ──── applicant   ← entity resolution across 11,728 records
                    │
                    ├── hearing (body, date, recommendation, decision)
                    └── document (staff report, site plan, conditions) → extracted text
```

Core `case` fields, mapped from the county's verified schema and generalized:

`case_number, jurisdiction_id, case_type, status, year, applicant_raw, applicant_id,
existing_zone, proposed_zone, approved_zone, acres, proposed_use, res_units,
nonres_sqft, filed_date, pc_date, pc_recommendation, staff_recommendation,
decision_date, decision, conditions_text, pins[], location_text, source_url,
source_system, first_seen, last_verified, geometry_ref`

Two fields carry disproportionate weight:

- **`applicant_id`** — resolving "Pulte Home Company LLC" / "Pulte Homes" / "PULTE
  HOME CO" into one entity across a decade of filings answers *who is building the
  most in Gwinnett and where they are moving next*. Nobody sells that for this county.
- **`conditions_text`** — the actual conditions of zoning approval live in council
  agenda packet PDFs, not in any database anywhere. Extracting them is the moat.

Every record carries `source_url`, `first_seen`, and `last_verified`. Non-negotiable.

---

## 7. Agent surface

| Surface | Detail |
|---|---|
| **Markdown twins** | Every URL + `.md` returns the same content as markdown with YAML frontmatter. Cloudflare measured this at 46,188 → 4,099 tokens for one page; that 11× is the whole argument. Also honor `Accept: text/markdown` with `Vary: Accept`. |
| **JSON-LD** | `schema.org/Legislation` on code sections with `legislationJurisdiction`, `legislationDate`, `legislationDateVersion`, `legislationLegalForce`. `Dataset` + `DataCatalog` on collections. `sdPublisher` / `isBasedOn` to declare honestly that we are a mirror. |
| **llms.txt** | Root file plus per-jurisdiction files at `/duluth/llms.txt`. Include an `## Instructions` section covering the jurisdiction trap and the citation requirement. |
| **Bulk export** | Gzipped JSONL of the full corpus. Many agents would rather grab one file than crawl 40,000 pages — and it cuts our load. |
| **Catalogs** | DCAT-US 3 at `/catalog.jsonld` **and** legacy Project Open Data `/data.json` — real harvesters (CKAN, data.gov, state portals) still expect the latter. |
| **MCP server** | Public, read-only, **no auth**. Streamable HTTP on Workers. 5 tools. Listed in `registry.modelcontextprotocol.io`. |
| **robots.txt** | Affirmative `Content-Signal: search=yes, ai-input=yes, ai-train=yes`. Explicitly welcome every named AI crawler. |

MCP tool surface — deliberately small, since every tool description is permanent
context tax in every client:

```
resolve_jurisdiction(address | pin)     → governing jurisdiction + boundary source
                                          ALWAYS CALL FIRST
search_cases(query, jurisdiction?, case_type?, date_range?, zone?)
get_case(case_number)                   → full record + documents + conditions
get_code_section(jurisdiction, citation)→ dated, cited text
list_jurisdictions()                    → all 17 + county, with code/plan/vendor status
```

Every result carries a resolvable URL, an `effective_date`, and an `as_of`. Undated
zoning data is a liability, not a feature.

**Note the irony worth exploiting:** Municode and gwinnettcounty.com both `Disallow: /`
ClaudeBot and GPTBot by name. The authoritative sources block the agents. This index
becomes the layer that doesn't.

---

## 8. Human portal

Not another ArcGIS viewer — the county already has six and they are all bad.

A **feed**: what got filed this week, what's on Tuesday's agenda, what was approved and
with what conditions. Fast, typographic, quiet. Case pages, parcel pages, jurisdiction
pages, developer profiles. A weekly email digest doubles as audience-building and the
on-ramp to the paid tier.

The homepage answers one question in one box: *type an address, get the governing
jurisdiction and what's happening near it.*

---

## 9. Legal posture

| Content | Posture | Basis |
|---|---|---|
| Ordinance / UDC / plan text | **Mirror in full** | *Georgia v. Public.Resource.Org* (2020) — edicts of Georgia government are outside copyright |
| Case records & metadata | **Mirror in full** | Facts; Georgia Open Records Act |
| County parcel / zoning geometry | **Proxy — never rehost** | Gwinnett GIS `licenseInfo` carries an explicit no-redistribution clause |
| Jurisdiction boundaries | **Host** | Census TIGER/Line — federal, public domain |
| IBC / IRC base text | **Never touch** | ICC copyright; ICC actively litigates |
| Georgia amendment packets | **Mirror in full** | State-authored, freely published by DCA (2024 editions, effective 2026-01-01) |

Every page states it is a mirror, names the system of record, and links to it.
Publish under CC0 with an explicit takedown contact.

---

## 10. Business model

Open data, paid workflow. Clean legally and clean ethically.

- **Free forever:** browsing, search, full agent access, MCP, bulk export.
  This is the authority play and it must never be gated.
- **Paid:** geographic alerts ("anything filed within 1 mile of this parcel"),
  API keys with higher limits, applicant intelligence, historical exports.

Never meter the public records themselves. Meter the convenience.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Cloudflare Bot Fight Mode silently 403s AI crawlers | Explicit verification step in Phase 1; test with a GPTBot user-agent and assert 200 |
| Suwanee's Akamai blocks all server-side clients | Headless browser adapter, or a formal open-records request |
| Duluth GovBuilt 403s non-browsers | Defer permits; derive cases from agenda mining first |
| Gwinnett asserts the GIS license clause | We never rehost their geometry; proxy + link only |
| Filename-based change detection (Duluth, Buford) breaks | Scrape the index page for the link pattern, never hardcode URLs |
| 17 jurisdictions of scraper rot | Adapter pattern + fixture tests + a public freshness dashboard that shows staleness rather than hiding it |
| Tier-3 cities have almost no data | Ship them as thin "jurisdiction + boundary + county-sourced zoning + code link" pages. Honest coverage beats fake completeness. |

---

## 12. Open questions

1. Domain name — not yet registered.
2. Whether to pursue an open-records request for Gwinnett's authenticated
   `mapvis/rest/services/Planning` service (returns `499 Token Required` — there is
   richer planning data behind it).
3. Vendor stacks for Lawrenceville, Snellville, Sugar Hill, Lilburn, Dacula, Grayson,
   Loganville, Berkeley Lake, Braselton, Auburn, Rest Haven, Mulberry — unresearched.
4. Whether Mulberry's incorporation litigation affects its status as a jurisdiction.
