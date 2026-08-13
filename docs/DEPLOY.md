# Deploying

**Domain:** `www.gwindex.net` — canonical host, set as `SITE_URL` and as the
Worker's custom domain.


One `wrangler deploy` ships everything: the built site as **Workers Static Assets**
and the API/MCP Worker alongside it.

```bash
# 1. build the corpus snapshot, then the site
SUPABASE_URL=https://losmnziukaqptxhqnhjh.supabase.co \
SUPABASE_ANON_KEY=sb_publishable_... \
  python3 scripts/export_snapshot_rest.py

cd site && SITE_URL=https://www.gwindex.net npm run ci   # build + 18 gates

# 2. deploy
cd ../worker
npx wrangler --version          # MUST be >= 4.34.0, see below
npx wrangler secret put SUPABASE_ANON_KEY
npx wrangler deploy
```

## Why Workers Static Assets and not Pages

The Pages 100,000-file ceiling is tied to the **zone** plan — Cloudflare Pro, $20/mo
**per domain**. Buying Workers Paid does not lift the Pages 20,000-file cap. Workers
Static Assets reaches the same 100,000 ceiling on **Workers Paid, $5/mo
account-wide**, and deploys the site and the Worker as one unit.

The more important reason is architectural. From Cloudflare's docs:

> By default, if a requested URL matches a file in the static assets directory,
> that file will be served — without invoking Worker code.

So the corpus, the `.md` twins, `llms.txt`, the sitemaps and the bulk export are
served by the platform. **A bug in our Worker cannot take the agent surface
offline.** `run_worker_first` is scoped to `/v1/*`, `/mcp` and `/openapi.json`; a
build gate asserts nothing in the agent surface falls inside that scope.

## Limits, and the two traps

| | |
|---|---|
| Files, free | 20,000 |
| Files, Workers Paid | 100,000 |
| Per asset | 25 MiB |
| Requests to static assets | free, unlimited; no storage cost |

Current build: **30,496 files, largest asset 3.8 MiB** — comfortably inside paid,
and roughly 3× over free. Two files per record, so it grows with the corpus.

**Trap 1 — wrangler version.** Below 4.34.0, wrangler enforces the 20,000-file cap
*whatever your plan says*, and ignores an array-valued `run_worker_first`. The
failure reads like a billing problem and isn't. Pinned to `^4.34.0` in
`worker/package.json`.

**Trap 2 — don't evaluate on free.** On the free plan, `run_worker_first` requests
that exceed limits return **429 instead of falling back to asset serving**. Testing
the routing config on free and concluding it behaves correctly under load is a
mistake waiting to happen.

To model the free tier deliberately:

```bash
MAX_DEPLOY_FILES=20000 node site/scripts/verify-build.mjs site/dist   # expect FAIL
```

## After the first deploy

Verify AI crawlers are actually served — this is the premise of the project, and
Cloudflare Bot Fight Mode silently 403s them regardless of `robots.txt` while every
page still looks perfect in a browser:

```bash
curl -sI -A "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.4; +https://openai.com/gptbot" https://www.gwindex.net/j/duluth
```

CI (`.github/workflows/site.yml`) asserts a 200 for GPTBot, ClaudeBot, PerplexityBot
and CCBot on push **and weekly**, because Bot Fight Mode can be switched on from a
dashboard with no commit anywhere.


## Credentials, and where each one comes from

| Name | Where it goes | How to get it |
|---|---|---|
| `SUPABASE_ANON_KEY` | `wrangler secret put` (Worker), and env for the exporter | Supabase dashboard → Project Settings → API Keys → **publishable** key. Already known; safe to hand around because RLS is SELECT-only — the same key gets `401` on a write. |
| `CLOUDFLARE_API_TOKEN` | GitHub Actions secret (CI deploy only) | Cloudflare dashboard → My Profile → API Tokens → Create Token. Permissions below. |
| `CLOUDFLARE_ACCOUNT_ID` | GitHub Actions secret, if the token spans several accounts | Cloudflare dashboard → Workers & Pages → right-hand sidebar |
| `SITE_URL` | GitHub Actions **variable** (not a secret) | `https://www.gwindex.net` |
| `DATABASE_URL` | Optional | Only needed for `export_snapshot.py` (psycopg). `export_snapshot_rest.py` uses HTTPS and needs no direct Postgres access. |

### The Cloudflare API token

The stock **"Edit Cloudflare Workers"** template is *not quite* enough, because
`custom_domain = true` makes wrangler manage the DNS record. Create a custom token
with:

| Scope | Permission | Why |
|---|---|---|
| Account | Workers Scripts → **Edit** | upload the Worker and its static assets |
| Account | Account Settings → **Read** | resolve the account |
| Zone (`gwindex.net`) | Workers Routes → **Edit** | bind the custom domain |
| Zone (`gwindex.net`) | DNS → **Edit** | create the `www` record |

Nothing else. Do not use a Global API Key — it is account-wide and cannot be
scoped or rotated independently.

Local `wrangler deploy` does **not** need this token: `wrangler login` uses OAuth
in the browser. The token exists for CI.

### Deploying by hand, first time

```bash
cd worker
npx wrangler login                       # browser OAuth, no token needed
npx wrangler --version                   # must be >= 4.34.0
npx wrangler secret put SUPABASE_ANON_KEY
npx wrangler deploy
```

### Prerequisites on the Cloudflare side

1. `gwindex.net` added as a zone and **active** (nameservers moved to Cloudflare).
   `custom_domain = true` fails against a zone Cloudflare does not control.
2. **Workers Paid** enabled ($5/mo, account-wide). Without it the asset cap is
   20,000 files and this build is 30,496.
3. **Bot Fight Mode OFF** — Security → Bots. It 403s AI crawlers regardless of
   `robots.txt` and would defeat the whole premise while every page looks perfect
   in a browser. CI checks this on every push and weekly.
4. Decide the apex: a Redirect Rule sending `gwindex.net/*` → `https://www.gwindex.net/$1`
   (301). Serving both hosts means every page exists twice and the sitemap only
   names one.
