# Session log — credential rotation and CI deploy

**2026-08-15** · Repo `willmobhill-arch/gwinnett-index` · Site https://www.gwindex.net
PRs [#2](https://github.com/willmobhill-arch/gwinnett-index/pull/2) and
[#1](https://github.com/willmobhill-arch/gwinnett-index/pull/1), both merged.

Status-update companion to `docs/plans/2026-08-15-session-handoff.md`, which remains
the working handoff. This log records what changed and what it cost to find.

---

## Headline

The Cloudflare API token was rotated, and deploys moved into CI so the replacement
never enters a container or a transcript again. The site was then deployed **by that
CI job**, not by hand — closing the last outstanding item from the previous session.

The live site had been serving the pre-fix table pages, including a routing bug that
put a well-formed, correctly-rendered page at `/code/duluth/table-2-b` that **did not
contain Table 2-B**. It now serves the corrected corpus.

## Done

| Item | State |
|---|---|
| Rotate the leaked Cloudflare API token | ✅ replacement verified, old one deleted |
| Deploy from CI rather than by hand | ✅ `deploy` job live in `.github/workflows/site.yml` |
| Deploy the corrected corpus to production | ✅ via that job, verified afterwards |
| `net.gwindex` keypair out of the scratchpad | ✅ done in a parallel session |

## Verified on production after the deploy

| Check | Want | Got |
|---|---|---|
| `table-2-b.md` rows starting `\| RA-200` | 1 | 1 |
| `/code/duluth/table-2-c-residential` | 200 | 200 |
| `table-9-a.md` contains `Local Street` | ≥ 1 | 8 |
| `/mcp` answers `tools/list` | alive | answers |
| Live sitemap `<loc>` count | matches build | 15,238 |
| GPTBot / ClaudeBot on `/j/duluth` | 200 | 200 / 200 |
| Apex `gwindex.net/j/duluth` | 301 → www | 301 → www |

The two dashboard-only apex DNS records were confirmed intact after the deploy, since
the deploy token carries DNS:Edit and could in principle have removed them:
`AAAA @ → 100::` (the apex→www Redirect Rule fires only on proxied traffic) and
`TXT @ → v=MCPv1; …` (the MCP registry's proof of domain ownership).

## The token

Verified across all four scopes without the value ever being printed:

| Scope | How |
|---|---|
| active | `/user/tokens/verify` → id `638f2243…0053` |
| Account Settings → Read | lists the account |
| Workers Scripts → Edit | sees script `gwinnett-index` |
| Zone → Workers Routes | zone `gwindex.net` |
| Zone → DNS → **Edit** | empty `POST /dns_records` → validation error `9000`, not auth error `10000` |

That last probe distinguishes DNS:Edit from DNS:Read, which a list call cannot, and an
empty body cannot create a record. The DNS scope is the easy one to omit — it is not in
the stock "Edit Cloudflare Workers" template, and the previous handoff's permission list
had only three of the four. It is required because `custom_domain = true` makes wrangler
manage the `www` record.

**The Cloudflare token and the `net.gwindex` registry keypair are unrelated.** Rotating
one does not invalidate the other.

## Four things that were failing silently

This is the substance of the session. Every one of them was green, or looked like
something else entirely, while being wrong.

**1. Every CI build was the ten-record sample.** The snapshot export was gated on
`if: env.DATABASE_URL != ''`, but a step's own `env:` block is not in scope for that
same step's `if:`. The name read empty, the condition was always false, the export never
ran — and `verify-build.mjs` *downgrades its gates to warnings* when it falls back to
`site/fixtures`. Green throughout. Uncommenting the pre-existing deploy block would have
shipped 10 cases over an 11,849-case index and exited 0.

**2. The AI-crawler check had never once run.** `agent-access` asserts that GPTBot,
ClaudeBot, PerplexityBot and CCBot get a 200 — the premise of the whole project, since
Cloudflare Bot Fight Mode 403s them while every page still looks perfect in a browser.
It was gated by a job-level `if: vars.SITE_URL != ''`, and a skipped job reads as "fine"
in the checks list. `docs/DEPLOY.md` described it as running on every push and weekly.
Its first real execution — this session — passed all seven assertions.

**3. Variables and Secrets are separate namespaces.** Config placed in the wrong one
reads as *empty*, not as an error, so the symptom is a step that skips.

**4. A trailing space in a settings field.** Invisible in the UI, survives to the
runner, and surfaced as two errors resembling neither each other nor their cause:

```
python -> http.client.InvalidURL: URL can't contain control characters.
          'losmnziukaqptxhqnhjh.supabase.co ' (found at least ' ')
curl   -> (3) URL rejected: Malformed input to a URL function
```

The curl one reads as *the live site is refusing AI crawlers* — the single most alarming
thing this repo checks for. It was a typo in a text box.

## What the deploy job does about that

It does not trust the build's exit code:

- **Refuses the fixture sample** — hard-fails below 1,000 cases or 20 code tables.
- **Rebuilds rather than reusing the artifact** — `SITE_URL` is baked in at build time,
  so an artifact is only deployable to the host it was built for.
- **Asserts installed wrangler ≥ 4.34.0** — not the same claim as the declared range;
  this repo has shipped a lockfile resolving `3.114.17` against `^4.34.0`, and below
  4.34.0 wrangler caps assets at 20,000 files with an error that reads like a billing
  problem. The build is ~30,500 files.
- **Compares the live sitemap against the build just made** — a deploy that uploads and
  then serves the previous build looks identical to a successful one.
- **Preflights all four required names**, reporting by name only. Nothing echoes a value.
- **Strips whitespace from URLs** and warns when it had to. Secrets are deliberately not
  trimmed and re-exported: a modified copy stops matching the registered value, so
  GitHub would stop masking it in logs.

## Required repository configuration

| Name | Kind |
|---|---|
| `CLOUDFLARE_API_TOKEN` | secret |
| `SUPABASE_ANON_KEY` | secret |
| `SITE_URL` | variable |
| `SUPABASE_URL` | variable |

All four are set, and `SITE_URL` and `SUPABASE_URL` now live **only** as Variables — the
duplicate secret copies were removed, so the deploy's own verification output prints real
URLs instead of `***`. The workflow still reads them as `vars.X || secrets.X`, which costs
nothing and means a value put in the wrong namespace keeps working rather than reading as
empty. Prefer Variables for anything non-secret: a secret is masked wherever it appears.

`DATABASE_URL` is no longer used. Both jobs use `scripts/export_snapshot_rest.py`, which
is stdlib-only over HTTPS and needs no direct Postgres access.

## Still open

Unchanged from the handoff, and none of it blocked by this session:

1. **Read the 11 unverified tables' cells against their rendered pages.** Smallest
   first: 5-A (5 rows), 6-E (12), 7-C (11), 6-A (13), 12-A (17), 6-B (22), 4-B (53),
   2-D ×2 (55 each), 2-C ×2 (333, 332).
2. **Minutes parser round two** — ~23 of 110 Duluth cases still have no outcome.
3. **Peachtree Corners / Norcross** — the real test of the adapter-reuse claim.
4. **262 applicant merge candidates** await human review.
5. **Do not reconcile apex DNS against this repo** — two records live only in the
   dashboard and each has a dependent. See `docs/DEPLOY.md`.

## Method note

The pattern worth carrying forward is the one this session kept hitting: **a job that
succeeds while doing nothing.** A skipped step, a skipped job, a gate that degrades to a
warning, a condition that can never be true, and an empty string that reads as "not
configured" all present as success. The countermeasure used here was to assert on
*content* rather than on completion — compare the live sitemap to the built one, count
the cases in the snapshot, and print what the data source actually was.
