# Gwinnett Index — session handoff

**Date:** 2026-08-13
**Branch:** `claude/buildout-process-continuation-tfh56r` (14 commits, all pushed)
**Live:** https://www.gwindex.net — Worker `gwinnett-index`, version `dcec93ad`

---

## State

| | |
|---|---|
| Site | 15,237 pages, 30,498 static assets, 19 build gates passing |
| Database | Supabase `losmnziukaqptxhqnhjh`, 11,849 cases, RLS on and verified |
| API + MCP | `/v1/*` and `/mcp`, listed as `net.gwindex/gwinnett-index` |
| Duluth outcomes | **87 of 110** (was 54 at session start) |
| Meeting text | 13.9 M chars in Postgres, 89 documents OCR'd |
| Resolver fixture | 1,546/1,546 high-confidence, unchanged all session |

Verified against the live origin: ClaudeBot, GPTBot, PerplexityBot and CCBot all
get 200 on HTML *and* `.md`; apex 301s to www; MCP handshake and all five tools
respond.

---

## ⚠️ Do these first

1. **Rotate the Cloudflare API token.** It was pasted into the previous
   transcript. Deploys no longer need it.
2. **Move the `net.gwindex` namespace keypair somewhere durable.** `key.pem` /
   `private_key.hex` were generated in a session-temporary scratchpad. Without
   them the MCP registry entry cannot be republished at all. Keep the apex TXT
   record — it is used for re-auth, not just the initial claim.

---

## Next up: verify the UDC tables

**This is where the work was heading when the session ended.** 17 of 18 Duluth UDC
tables are unverified, and their cell values are deliberately withheld from the
published snapshot — `code_table.quality != 'verified'` means `rows` ships as `[]`.
Dimensional standards are the most-queried content in the corpus, so this is where
withholding costs the most.

Only `Table 2-B` (Area Regulations by Zoning District, pp. 52–54) is verified, and
even its merged PUD and CBD rows are flagged unreliable.

The method that worked for 2-B, and the reason it worked:

- **Render the source page as an image and compare cell by cell.** Table 2-B
  looked correct on internal consistency alone; the multi-line bleed only showed
  up against the rendered page, *after* it had already been called verified.
- **pdfplumber's per-row cell lists are not column-stable.** Lot size landed at
  index 1 for RA-200 and index 2 for R-100. Derive columns from clustered x-edges,
  and rows from each row's own bbox — clustering y-edges invents bands inside
  multi-line cells and bleeds values between rows.
- The source PDF is `UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf`; the filename
  encodes adoption and amendment dates and **is** the change-detection signal.

`ingest/duluth/extract_tables.py` is the extractor. `code_table.quality` and
`verification_note` are the flags. Set `quality='verified'` only after a cell-by-cell
comparison, and record what was checked in `verification_note` — Table 2-B's note
names the page and the date and says which rows remain unreliable.

Everything needed is reachable: `developers.cloudflare.com` is blocked but
`duluthga.net`, `cms4files.revize.com`, Supabase and the county GIS are all
allowlisted. tesseract 5.3.4 and pymupdf are installed but **the container is
ephemeral** — run `bash scripts/setup_ocr_env.sh` in a new session.

---

## Also outstanding

- **23 Duluth cases still have no outcome.** They need different evidence, not a
  better regex: 11 appear in a section with no motion, 8 in a section naming
  several cases, 5 have a motion opener with no completed vote, 2 are only ever in
  an agenda.
- **262 applicant merge candidates** await human review; developer counts are lower
  bounds until then.
- **`developer_activity` includes engineering and planning consultants** (Carter
  Engineering, Ridgeline Land Planning) that file as agents without a `C/O` marker.
  Needs a manual pass on the top 50; the `kind` classifier cannot catch it from the
  name alone.
- **Peachtree Corners** — the first real test of the adapter-reuse claim. If it
  needs new *code* rather than a new *config*, the adapter layer is leaking and that
  matters more than adding the city.

---

## The redeploy rule, which bit twice

Any data change needs the full chain, in order:

```bash
SUPABASE_URL=... SUPABASE_ANON_KEY=... python3 scripts/export_snapshot_rest.py
cd site && SITE_URL=https://www.gwindex.net npm run ci
cd ../worker && npx wrangler deploy        # wrangler must be >= 4.34.0
```

`SITE_URL` is baked in at build time, so the rebuild is never optional. The
snapshot went a day stale once and would have published an older corpus with every
page rendering perfectly.

---

## What this session changed, in one list

- Captured all 23 migrations into `db/migrations`, md5-verified against the live
  project; found two columns that existed only in production.
- Applied read-only RLS, verified as `anon` (401 on write against the live API);
  fixed a SECURITY DEFINER view and pinned `search_path` on 13 functions.
- Ran the Duluth OCR pass end to end: 1.34 M characters recovered, 89 documents,
  `text_source` of `embedded`/`ocr`/`mixed` matching the corpus's own labels.
- Minutes decision extraction, twice: bind each vote to the case its motion names,
  then fall back to the case its agenda item names. 54 → 87 outcomes.
- Deployed to Workers Static Assets with `run_worker_first` scoped to `/v1/*`,
  `/mcp` and `/openapi.json`, so the agent surface never needs Worker code.
- Built the site from the real corpus for the first time (it had only ever built
  from a 10-record fixture).

Failure modes worth carrying forward are all in `CLAUDE.md`. The recurring shape:
**a job that succeeds while doing nothing.** An OCR queue of zero, a crawler that
downloads nothing without `--fetch`, a dedup key that discards 51 decisions, a
header lookup that makes every count 0, a version pin that never installed. None
raised an error; each was found by checking a number that did not add up.
