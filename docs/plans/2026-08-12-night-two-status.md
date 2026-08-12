# Gwinnett Index — Night Two Status

**Date:** 2026-08-12
**Phases complete:** 0–2 (previously), 3 (previously), **4 (site + agent surface)**, **5 (API + MCP)**
**Branch:** `claude/buildout-process-continuation-tfh56r`

---

## ⚠️ One decision needed from you

**Row Level Security is off, and that is not a theoretical problem now that there is
an API.** With RLS disabled, PostgREST exposes `INSERT`, `UPDATE` and `DELETE` on every
table in the `public` schema to the `anon` role. The Worker and the site both
authenticate with the anon key, which is *publishable by design* — it lives in a Worker
binding and ends up in anyone's network tab.

So today, anyone with the project URL and that key can rewrite the 11,848-case corpus,
and nothing about the site would look different afterwards.

The fix is not to hide the key; it is to make the key harmless. A migration is written
and **not applied**:

```
db/migrations/20260812170000_public_read_only_rls.sql
```

It enables RLS on all 14 project tables, grants `SELECT` to `anon` and `authenticated`,
and revokes writes at the grant level as well as the policy level. Ingestion is
unaffected — every loader runs *inside* Postgres as the table owner, and RLS does not
apply to the owner. `spatial_ref_sys` is deliberately left alone (extension-owned).

Nothing else in this session depends on it. Say the word and I will apply it.

---

## What was built

### Phase 4 — the site (`site/`)

Astro, static output, 52 routes on the sample fixture and one route per record on a real
snapshot. Quiet and typographic; no map, because the county already publishes six ArcGIS
viewers and a seventh is not the gap.

Routes: `/`, `/j`, `/j/{slug}`, `/case/{jurisdiction}/{case}`, `/code/{jurisdiction}`,
`/code/{jurisdiction}/{citation}`, `/developer`, `/developer/{slug}`, `/status`.

**Every page states its governing jurisdiction in a bordered callout before any
substance.** That is enforced by a build gate, not by discipline.

**Data flow changed, deliberately.** The site does *not* query Supabase during the build.
`scripts/export_snapshot.py` writes `data/snapshot/*.json`; the site reads that. The build
is therefore deterministic, works offline, and is diffable — for a legal-reference index,
being able to see exactly what changed between two deploys is worth more than build-time
freshness. `site/fixtures/` holds a small committed sample with identical shapes so the
site builds with no database at all, and says loudly on every page when it is doing so.

### Agent surface

- `.md` twin for every route, with YAML frontmatter (`jurisdiction`, `source_url`,
  `effective_date`, `as_of`, `canonical`, `licence`).
- `/llms.txt` at root and per jurisdiction, both leading with the jurisdiction rule.
- `robots.txt` naming 15 crawlers explicitly with `Content-Signal: ai-input=yes`.
- `schema.org` JSON-LD: `Legislation` on code, `Dataset`/`DataCatalog` on collections.
- `/data.json` (Project Open Data 1.1) and `/catalog.jsonld` (DCAT-US 3).
- `/bulk/corpus.jsonl.gz`, one object per line, each carrying a `record` discriminator.
- `/sitemap.xml` with `lastmod` from each record's own verification date. No `changefreq`,
  no `priority` — every consumer ignores them and a guess about how often a 1991 case
  changes is noise pretending to be metadata.

### Phase 5 — API + MCP (`worker/`)

One Cloudflare Worker, both surfaces, **one implementation** in `src/tools.ts` so the MCP
tool and the REST endpoint cannot drift apart and answer the same question differently.
Public, read-only, no auth.

Five tools, no more: `resolve_jurisdiction` (documented ALWAYS CALL FIRST),
`search_cases`, `get_case`, `get_code_section`, `list_jurisdictions`. Every tool
description is permanent context tax in every connected client, paid whether or not the
tool is ever called.

The jurisdiction rule is repeated in the MCP `initialize` `instructions` field — the only
place a rule still holds when the model decides not to call a tool at all, which is
precisely the failure this index exists to prevent.

Tool failures return as `isError` tool results, not JSON-RPC errors, so a model reads "no
parcel found for that PIN" and adapts instead of hitting a transport failure.

`npm test` in `worker/` runs 10 protocol tests against a stubbed upstream: handshake,
tool surface, structured + text content, the unincorporated-only warning, effective dates,
error posture, notifications, and REST/MCP agreement.

---

## Findings from this session

### The schema existed only inside Supabase

`db/migrations/` held nothing but a README. All 17 applied migrations are now checked in,
**each verified byte-for-byte against `supabase_migrations.schema_migrations` by md5** —
which is how I caught that one file had silently failed to write.

Reconciling the files against `information_schema` surfaced two columns applied
out-of-band and present in no migration:

| Column | Consequence |
|---|---|
| `code_table.quality`, `code_table.verification_note` | `load_udc_tables_from_url` reads `quality` in its `ON CONFLICT` arm, so a rebuild from migrations alone produced a loader that errored on first use |
| `land_use_case.applicant_norm` | cached normalisation key, silently absent |

Both are now in `20260812160000_code_table_quality_flags.sql`.

### Duluth agenda mining is much weaker than the case count suggests

109 cases sounds like coverage. Measured field by field, it is a finding aid, not a
dataset:

| Measure | Count | of 109 |
|---|---|---|
| “Location” with no street number in it | 67 | 61% |
| …of which plainly not an address (`as presented.`, `{J}`) | 17 | 16% |
| “Request” that is just the word `ORDINANCE` | 57 | 52% |
| Applicant field that ran on into a mailing address | 23 | 21% |
| No applicant at all | 10 | 9% |
| Carries a zoning district | 13 | 12% |
| Carries an outcome | 54 | 50% |

This was not previously written down. It is now measured on every export
(`stats.duluth_extraction`), published on `/status`, and flagged on every affected case
page and twin: *the linked PDF is the record; the extracted fields are a finding aid.*

The honest framing is that Duluth's 109 rows are an index into 353 meeting documents, and
the OCR pass that was never completed is what would turn them into records.

### The 11× token-reduction claim was wrong

Measured across the build, the `.md` twins are **5.7× smaller** than their HTML (median;
range 3.3–8.7×). The build now prints the real ratio every time and the site copy quotes
the measurement, so the claim cannot drift from what ships.

### Two bugs the build gates caught while being written

- The case `.md` twin filtered out its own blank lines, gluing every heading to the
  paragraph above it. Renders fine; reads badly everywhere.
- Frontmatter closed `---` immediately followed by `# Title`.

Both were found by gates written before the output was inspected, which is the argument
for writing the gate first.

---

## Verification

`site/scripts/verify-build.mjs` — 15 gates, run by `npm run ci`:

```
ok  sitemap lists N routes                     ok  bulk export carries no geometry
ok  every route has a built HTML page          ok  every exported record carries source_url
ok  every route has a .md twin                 ok  data.json parses
ok  every entry carries an ISO lastmod         ok  catalog.jsonld parses
ok  all record pages name jurisdiction first   ok  twins are 5.7x smaller than their HTML
ok  all twins state the jurisdiction           ok  twin markdown is well-formed
ok  twins carry as_of + canonical              ok  llms.txt states the trap and the rules
ok  robots.txt names every target crawler
```

The geometry gate is the legal one: it gunzips the bulk export and fails if any line
carries `boundary`, `geometry`, `rings`, `wkt` or `coordinates`. Gwinnett GIS forbids
redistribution, and nothing about the page would look wrong if we breached it.

`.github/workflows/site.yml` additionally asserts **200 for GPTBot, ClaudeBot,
PerplexityBot and CCBot** against the live origin, on push *and weekly* — Bot Fight Mode
can be flipped on from a dashboard with no commit anywhere.

`scripts/export_snapshot.py` **refuses to write a snapshot** if the resolver's
high-confidence band is not 100% correct on all 1,546 probes. Re-scored this session:
still 1,546/1,546.

---

## Not done

| Item | Note |
|---|---|
| **Apply the RLS migration** | Needs your call. See the top of this document. |
| **Register a domain** | Everything absolute is driven by `SITE_URL`; the build warns loudly when it is unset and CI skips the crawler check without it. |
| Deploy | Cloudflare Pages for `site/`, `wrangler deploy` for `worker/`. `SUPABASE_ANON_KEY` goes in as a Worker secret. |
| MCP registry listing | After deploy, as `org.<domain>/gwinnett-index`. |
| Duluth OCR pass | Still the highest-value data work. It is what turns 109 index entries into records with vote counts. |
| 262 applicant merge candidates | Still queued. |
| 17 unverified UDC tables | Still unverified. Their cell values are withheld from the snapshot by design. |
| `developer_activity` consultant misclassification | Carter Engineering and Ridgeline Land Planning still read as developers; needs the manual pass on the top 50. |

## Suggested next session

1. Apply RLS (one decision, two minutes).
2. Register the domain, deploy both, set `SITE_URL` and the `SUPABASE_ANON_KEY` secret,
   then watch the crawler-access job go green — that is the moment the premise is proven.
3. Run the Duluth OCR pass locally and regenerate `duluth_cases.jsonl`. Everything else
   is polish next to this.
4. Peachtree Corners as the first adapter-reuse test. If it needs new *code* rather than a
   new *config*, stop and fix the adapter layer before adding city three.
