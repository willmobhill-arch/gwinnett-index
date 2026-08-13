# Deploying

**Live at https://www.gwindex.net** since 2026-08-13. Worker `gwinnett-index`,
30,498 static assets, MCP listed in the official registry as
`net.gwindex/gwinnett-index`.

**Domain:** `www.gwindex.net` — canonical host, set as `SITE_URL` and as the
Worker's custom domain.

## ⚠️ Namespace keypair — move it somewhere durable

Publishing updates to the MCP registry entry requires the keypair that proves
control of the `net.gwindex` namespace (`key.pem` / `private_key.hex`). It was
generated in a **session-temporary scratchpad**, which does not survive. Without
it you cannot republish — not a new version, not a description fix, nothing —
without re-doing DNS verification from scratch.

Move it to a password manager or an encrypted store, and **leave the verification
TXT record on the apex in place**; it is used for re-authentication, not just the
initial claim.


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

Verified against `developers.cloudflare.com/workers/platform/limits/#static-assets`
and the 2025-09-02 changelog:

| | Free | Workers Paid |
|---|---|---|
| Files per Worker version | 20,000 | **100,000** |
| Individual file size | 25 MiB | 25 MiB |
| `_headers` rules | 100 | 100 |
| `_redirects` total | 2,100 | 2,100 |

Requests to static assets are free and unlimited, with no storage cost for the
assets themselves.

Current build: **30,496 files, largest asset 3.8 MiB** — comfortably inside paid,
and roughly 3× over free. Two files per record, so it grows with the corpus.

**`wrangler deploy` reports a larger number than this and it is not a discrepancy.**
A dry run prints `Read 45735 files from the assets directory`; that figure counts
directories as well as files (30,496 files + 15,240 directories, less the root).
The number that counts against the 100,000 limit is the file count. Do not "fix"
the build in response to the wrangler message.

**Trap 1 — wrangler version.** Below 4.34.0, wrangler enforces the 20,000-file cap
*whatever your plan says*. The failure reads like a billing problem and isn't.

Pinning it in `package.json` is not sufficient on its own: this repo had
`^4.34.0` declared while `package-lock.json` still resolved 3.114.17, and a plain
`npm install` left it there. wrangler 4.x also requires
`@cloudflare/workers-types@^5`, so bumping one without the other fails to resolve.
**Check the installed version, not the declared one:**

```bash
npx wrangler --version        # must print >= 4.34.0
```

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

### Deploy in two phases

The custom domain needs `gwindex.net` to be an **active zone** in the same
Cloudflare account — `custom_domain = true` fails against a zone Cloudflare does
not control, and nameserver propagation can take hours. There is no reason to wait
for that before proving the deploy works.

**Phase 1 — workers.dev, no DNS needed.** Comment out the `[[routes]]` block in
`wrangler.toml` and deploy. The site comes up at
`gwinnett-index.<your-subdomain>.workers.dev`, and everything except the hostname
is identical: same assets, same run_worker_first scoping, same Worker.

That is enough to check the things worth checking early:

```bash
S=https://gwinnett-index.<your-subdomain>.workers.dev
curl -sI "$S/j/duluth" | head -1                       # static asset, no Worker
curl -s  "$S/v1/jurisdictions" | head -c 200           # Worker route
curl -s  "$S/j/duluth.md" | head -12                   # the .md twin
curl -sI -A "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)" \
     "$S/j/duluth" | head -1                           # Bot Fight Mode check
curl -s -X POST "$S/mcp" -H 'content-type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 300
```

Build with `SITE_URL` set to the workers.dev host for this phase, or the absolute
URLs in the sitemap and llms.txt will point at a domain that does not resolve yet.

**Phase 2 — the custom domain.** Once the zone is active, restore `[[routes]]`,
rebuild with `SITE_URL=https://www.gwindex.net`, and deploy again. Do not skip the
rebuild: `SITE_URL` is baked into every absolute URL at build time.

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


## Live configuration, as deployed

### Apex redirect

`gwindex.net` had no DNS records at all, so the apex needed a proxied record for a
Redirect Rule to fire against:

| | |
|---|---|
| DNS | `AAAA @ → 100::`, **proxied** (the documented discard address for redirect-only apexes) |
| Rule | `Apex to www`, active |
| If | `http.host eq "gwindex.net"` |
| Then | Dynamic redirect → `concat("https://www.gwindex.net", http.request.uri.path)`, **301**, preserve query string |

Verified: `https://gwindex.net/j/duluth?a=1` → `301` →
`https://www.gwindex.net/j/duluth?a=1`, on both http and https, root and deep paths.

The `www` record is **wrangler-managed** via `custom_domain = true`. Never create
or edit it by hand — a manual record conflicts with the Worker binding.

### Trailing slashes

`html_handling = "drop-trailing-slash"`. Astro emits `/j/duluth/index.html`, and
Cloudflare's default (`auto-trailing-slash`) served that at `/j/duluth/` while
307-ing `/j/duluth` — but the sitemap and every `<link rel="canonical">` use the
no-slash form. The default meant all 15,232 HTML routes cost a redirect and served
at a URL other than the one they declared canonical. Now the canonical form serves
directly and the slashed form redirects to it.

### MCP registry

Published as `net.gwindex/gwinnett-index`, `streamable-http`,
`https://www.gwindex.net/mcp`, namespace verified by DNS TXT on the apex.

Three constraints worth knowing before republishing:

- **`description` has `maxLength: 100`.** A longer one is rejected outright. The
  published text is 91 characters. This is fine: the jurisdiction trap and the
  67.3% figure live in the server's own `instructions` from `initialize`, which is
  where a model actually reads them, and that field has no such limit.
- Current manifest schema is **`2025-12-11`**; include `$schema`, and `title`,
  `websiteUrl` and `repository` are accepted alongside it.
- The `mcp-publisher` CLI is available as a release binary. Installing via
  Homebrew may demand `sudo chown -R` on the Homebrew prefix — use the release
  binary instead rather than changing system permissions.
