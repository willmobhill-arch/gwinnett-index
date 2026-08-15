# Session handoff — 2026-08-15

Supersedes `docs/plans/2026-08-14-session-handoff.md`.

Repo: **`willmobhill-arch/gwinnett-index`** · Supabase `losmnziukaqptxhqnhjh`
Site: https://www.gwindex.net · MCP: `net.gwindex/gwinnett-index`
Branch: `claude/buildout-process-continuation-tfh56r` · PR #1 (draft)

---

## What this session did

Two things: integrated the incoming UDC verification bundle and fixed what enforcing
it exposed, then rebuilt the table extractor on the ruled grid and reloaded every
table's cells.

### The bundle exposed a routing bug that hid the previous session's work

Every UDC table exists **twice** in the corpus: a `code_section` row holding the prose
printed around it, and a `code_table` row holding the structured header and cells. They
share a citation. On top of that, the UDC prints "Table 2-C" twice — residential
districts on p56, commercial on p70.

Routing on citation alone made four records collide, and a de-dup guard resolved each
collision by keeping whichever came first. `/code/duluth/table-2-b` was a real,
well-formed, correctly-rendered page that **did not contain Table 2-B**. The
hand-verified 20-row table was on no page at all. Nothing 404'd and nothing warned.

Sections and tables now merge onto one page per item (`codeItems()` in
`site/src/lib/routes.ts`); fragments carry a title discriminator; `site/public/_redirects`
covers the two published URLs that moved.

**The first version of the route gate passed while all of that was true**, because it
checked that the page existed rather than what was on it. It asserts content now.

### The extractor now reads the ruled grid

Every row-count defect in the corpus came from the markdown path mistaking something
else for a data row:

| Table | Was | Is | Cause |
|---|---|---|---|
| 4-A | 16 | 6 | the page carries a worked **example** with the same column count |
| 9-A | 13 | 8 | three rows are single ruled cells holding three text lines each |
| 3-A, 7-A, 9-B | +1 each | ok | spanning label taken as the header, header became data |
| 4-C | 1 col | 2 | the column rule is not drawn |
| 12-A | 3 fragments | 1 | title reprinted as a page header on 363, 364, 365 |
| 2-B | 28 | 20 | header band ×2 pages, plus in-cell divisions read as rows |

`ingest/pdf/extract_cells.py` takes cells from `find_tables()`, with the hand-verified
fixture supplying header, `n_cols` and `spanning_header`. That inversion is deliberate:
pass B tried to score a geometry header against a markdown one and pick a winner, and
it still picks wrong on 2-C, yielding `'RA-200 Parking, 2022'` over a correct header.
No scoring function beats a person looking at the page.

**Result:** all 20 tables reproduce the fixture's column count, header and asserted row
count; 2-B's twenty row labels come out in the fixture's order; and against the seven
independently hand-transcribed tables the extractor agrees on **492 of 493 cells** —
the one disagreement being its own.

### Database state

```sql
SELECT quality, count(*) FROM code_table GROUP BY 1;
-- verified 9 | unverified 11 | defective 0
```

`verified` (published): 2-B, 3-A, 3-B, 4-A, 4-C, 7-A, 7-B, 9-A, 9-B.
3-B and 9-A were added this session, each compared cell-by-cell against its rendered
page. Nothing is `defective` any more: that flag asserted the stored values were *known
wrong*, which stopped being true when they were re-extracted. Every table now satisfies
`n_rows = jsonb_array_length(rows)`.

---

## What's next, in order

1. **Read the 11 unverified tables' cells against their rendered pages.** Smallest
   first: 5-A (5 rows), 6-E (12), 7-C (11), 6-A (13), 12-A (17), 6-B (22), 4-B (53),
   2-D ×2 (55 each), 2-C ×2 (333, 332). Promote by adding the table to
   `VERIFIED_AGAINST_RENDER` in `ingest/pdf/publish_cells.py` — that dict is the only
   thing that promotes a table, and adding a line to it is a claim that a person read
   the page. Then re-publish and re-run the loader.
2. **Minutes parser round two** — ~23 of 110 Duluth cases still have no outcome, and
   the votes are in text already in the database.
3. **Peachtree Corners / Norcross.** The real test of the adapter-reuse claim: if
   either needs new *code* in `ingest/adapters/pdf_code.py` rather than a new entry in
   `SOURCES`, the adapter layer is leaking and that comes before adding more cities.
4. **262 applicant merge candidates** await human review.

## Still outstanding from before

- ~~**Rotate the Cloudflare API token**~~ — **done 2026-08-15.** The replacement was
  injected into a fresh session's environment, verified against all four scopes
  without printing it (`/user/tokens/verify` → active; account `6a35dc55…`; script
  `gwinnett-index`; zone `gwindex.net` routes and DNS — DNS:**Edit** confirmed by an
  empty `POST /dns_records` returning a validation error rather than an auth one, which
  creates nothing), and the old token deleted in the dashboard. The token is now a
  repository Actions secret and CI deploys with it — see below. It does **not** touch
  the `net.gwindex` registry keypair, which is a separate credential.
- ~~**Move the `net.gwindex` keypair out of the scratchpad**~~ — **done 2026-08-15**, in a
  separate session. It is in durable storage; the registry entry can be republished.
  **This is independent of the token rotation above** — the Cloudflare API token and the
  `net.gwindex` keypair have nothing to do with each other, and rotating one does not
  invalidate the other. Nobody should redo the keypair work thinking the rotation voided it.
- **Do not reconcile apex DNS against this repo.** Two records live only in the
  dashboard, are declared nowhere in `wrangler.toml`, and each has a dependent:
  `AAAA @ → 100::` proxied (the apex→www Redirect Rule fires only on proxied traffic —
  delete it and the redirect dies silently while the rule still reads "Active") and
  `TXT @ → v=MCPv1; …` (the registry's proof of domain ownership). Only `www` is
  wrangler-managed. Detail in `docs/DEPLOY.md` → *Apex records wrangler does not own*.
- ~~**Redeploy**~~ — **done 2026-08-15, and the live site is now current.** PR #1 merged to
  `main`, which fired the new CI deploy job. Verified on production afterwards:
  `/code/duluth/table-2-b.md` has its one `| RA-200` row, `/code/duluth/table-2-c-residential`
  returns 200, `table-9-a.md` names `Local Street` 8 times, `/mcp` answers `tools/list`,
  the sitemap serves 15,238 URLs, and GPTBot and ClaudeBot both get 200. **Deploy from CI
  from now on** — merge to `main` and it happens. The by-hand path below is kept only for
  the case where CI is unavailable.

---

## Running it

```bash
pip install pymupdf pymupdf4llm pytest
python3 -m ingest.adapters.pdf_code --discover duluth   # what the document announces
python3 -m ingest.pdf.extract_cells                     # -> var/extracted_cells.json
python3 -m ingest.pdf.publish_cells                     # -> data/udc_table_cells.jsonl
python3 -m pytest tests/test_udc_tables.py -q           # 22 assertions
python3 -m ingest.adapters.pdf_code --plan duluth       # the SQL to run
```

The loader is in-database and fetches the repo's own raw URL, so the file must be
**committed and pushed before the load**, and `GWINDEX_REF` picks the branch.

## Deploying — CI does it; this section is the fallback

**This branch is merged and deployed.** Deploys now happen automatically on push to
`main` via the `deploy` job in `.github/workflows/site.yml`, which exports the corpus,
refuses to ship the fixture sample, asserts wrangler >= 4.34.0, deploys, and then
compares the live sitemap against the build it just made. Prefer that path: it keeps
the Cloudflare token out of every container and transcript, which is why the previous
one had to be rotated.

The commands below remain correct for a local deploy when CI is unavailable. They are
no longer the normal route, and the state they describe ("the live site still serves
the pre-fix table pages") is **no longer true** — that was fixed by the deploy above.

Needs `CLOUDFLARE_API_TOKEN` in the environment. **Environment variables are injected
at container start**, so a variable added to the environment config mid-session is not
visible to that session — start a fresh session and it will be there. Do not paste the
token into the transcript; that is what put the previous one on the rotate list.

Token permissions: Account → Workers Scripts → Edit; Account → Account Settings →
Read; Zone → Workers Routes → Edit **and Zone → DNS → Edit** on `gwindex.net`.

**That fourth scope was missing from this list and matters.** `custom_domain = true`
makes wrangler manage the `www` record, so a token scoped to only the first three
cannot complete a deploy. `docs/DEPLOY.md` had it right; this list did not. The
rotated token was verified to carry it.

```bash
cd /home/user/gwinnett-index
SUPABASE_URL=https://losmnziukaqptxhqnhjh.supabase.co \
SUPABASE_ANON_KEY=sb_publishable_zTtQd-fucarE5INRi3ANSw_xNUqO1gO \
  python3 scripts/export_snapshot_rest.py

cd site && npm ci && SITE_URL=https://www.gwindex.net npm run ci    # 22 gates must pass
cd ../worker && npx wrangler deploy                                 # needs >= 4.34.0
```

`SUPABASE_ANON_KEY` is a publishable key and safe to hand around — RLS is on and
SELECT-only, and the same key gets 401 on a write. `SUPABASE_ANON_KEY` on the Worker is
a `wrangler secret`, which `deploy` preserves; the API and MCP survive a redeploy.

Verify afterwards, and do not skip this — a deploy that uploads and serves the previous
build looks identical to a successful one:

```bash
curl -s https://www.gwindex.net/code/duluth/table-2-b.md | grep -c '^| RA-200'   # want 1
curl -so /dev/null -w '%{http_code}\n' https://www.gwindex.net/code/duluth/table-2-c-residential   # want 200
curl -s https://www.gwindex.net/code/duluth/table-9-a.md | grep -c 'Local Street'            # want >= 1
curl -sX POST https://www.gwindex.net/mcp -H 'content-type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 80                        # MCP alive
```

**The durable fix is CI — now built.** `.github/workflows/site.yml` carries a real
`deploy` job: it deploys on push to `main`, reading `CLOUDFLARE_API_TOKEN` from a
repository Actions secret, so the credential need never enter a transcript or a
container again. **It will not run until the secret and variables exist** — see
`docs/DEPLOY.md` → Credentials. The preflight step names what is missing and stops.

Uncommenting the old block would not have been enough, and the reason is the
recurring failure shape again — a job that succeeds while doing nothing:

- The `build` job's snapshot export was gated on `if: env.DATABASE_URL != ''`, but a
  step's own `env:` block is **not** in scope for that same step's `if:`. The name read
  empty, the condition was always false, and the export never ran. Every CI build was
  the ten-record `site/fixtures` sample — and `verify-build.mjs` *downgrades its gates
  to warnings* in fixture mode, so CI was green the whole time. Both jobs now set the
  export inputs at job level, where a step `if:` can actually see them.
- So a deploy job stacked on that would have shipped the sample over the real index and
  exited 0. The deploy job now hard-fails if the snapshot has fewer than 1,000 cases or
  fewer than 20 code tables, instead of trusting the build's exit code.
- It rebuilds rather than reusing the `site-dist` artifact, because `SITE_URL` is baked
  in at build time — an artifact is only deployable to the host it was built for.
- It asserts the installed wrangler is >= 4.34.0 (this repo has already shipped a
  lockfile resolving 3.114.17 against a declared `^4.34.0`).
- Afterwards it compares the **live** sitemap's `<loc>` count against the one just
  built, because a deploy that uploads and then serves the previous build looks
  identical to a successful one. Exercised against production both ways before commit:
  matching counts pass (15,236 URLs, `/j/duluth`, `/j/duluth.md`, `/llms.txt`,
  `/robots.txt` all 200, `/mcp` answering `tools/list`), mismatched counts exit 1.

## Method notes — do not skip these

- **Verify against the rendered page image, cell by cell.** `page.get_pixmap(dpi=200,
  clip=...)` and actually look at it. Every finding here came that way; none came from
  internal consistency.
- **Snapping matters.** The UDC draws thick double borders, so one column edge is two
  ruled lines: 9-B reads as 28 columns wide. `snap_x_tolerance=8`, calibrated against
  seven hand-verified counts — 6 and 10 also work, 2 fails everything, 14 collapses
  9-B to 11.
- **A rule that does not span the table is not a row boundary.** Real boundaries span
  0.75–1.00 of the width, in-cell divisions 0.11–0.34. The UDC draws no full-width
  lines, so coverage must be the *union* of per-cell segments.
- **Stage order fails silently both ways.** Decide empty columns before stripping the
  header (or 2-D loses its NAICS column); strip the header before folding in-cell
  divisions (or 3-A's `0.5` arrives with its column heading glued on top).
- **`n_rows` counts RULED rows.** The fixture said 19 for 3-B, which is printed *lines*
  in the label column; the table has 9 ruled rows. Corrected, and the convention is now
  written into the fixture — a DB CHECK ties `n_rows` to the stored count, so two
  conventions cannot both be right.
- **The recurring failure shape is a job that succeeds while doing nothing.** This
  session added three: a gate that checked a file existed rather than its contents; a
  note overwrite that deleted the Table 6-D ordinance-defect finding; and
  `python3 -m pkg.mod` running a module twice under two names, so a registry populated
  in one copy reads empty in the other without erroring.

## Source state

`https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf`
8,646,771 bytes · 426 pages · SHA-256 `2311ae98…a48c0` — **unchanged**, re-verified
this session and pinned in `tests/test_udc_tables.py`, which voids its own assertions
when the hash moves. The filename encodes the amendment date and is the
change-detection signal: scrape the link, never hardcode it.
