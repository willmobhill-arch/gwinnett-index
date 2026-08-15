# Deploying

**Live at https://www.gwindex.net** since 2026-08-13. Worker `gwinnett-index`,
30,498 static assets, MCP listed in the official registry as
`net.gwindex/gwinnett-index`.

**Domain:** `www.gwindex.net` — canonical host, set as `SITE_URL` and as the
Worker's custom domain.

## Namespace keypair — stored, 2026-08-15

Publishing updates to the MCP registry entry requires the keypair that proves
control of the `net.gwindex` namespace (`key.pem` / `private_key.hex`). It was
generated in a session-temporary scratchpad and has since been **moved to durable
storage**. Without it you could not republish — not a new version, not a
description fix, nothing — without re-doing DNS verification from scratch.

**Leave the verification TXT record on the apex in place**; it is used for
re-authentication, not just the initial claim. See *Apex records wrangler does not
own* below.

**The registry keypair and the Cloudflare API token are unrelated.** Rotating the
token has no effect on the keypair and does not invalidate the namespace claim, so
a rotation is never a reason to redo the keypair work.


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
| `SUPABASE_ANON_KEY` | Actions **secret**; `wrangler secret put` (Worker); env for the exporter | Supabase dashboard → Project Settings → API Keys → **publishable** key. Already known; safe to hand around because RLS is SELECT-only — the same key gets `401` on a write. |
| `SUPABASE_URL` | Actions **variable** | `https://losmnziukaqptxhqnhjh.supabase.co` |
| `CLOUDFLARE_API_TOKEN` | Actions **secret** (CI deploy only) | Cloudflare dashboard → My Profile → API Tokens → Create Token. Permissions below. |
| `CLOUDFLARE_ACCOUNT_ID` | Actions **variable**, only if the token spans several accounts | Cloudflare dashboard → Workers & Pages → right-hand sidebar |
| `SITE_URL` | Actions **variable** (not a secret) | `https://www.gwindex.net` |
| `DATABASE_URL` | No longer used by CI | `export_snapshot.py` (psycopg) needs a direct connection on 5432. Both workflow jobs use `export_snapshot_rest.py`, which is stdlib-only over HTTPS. |

The `deploy` job refuses to start unless all four of `SITE_URL`, `SUPABASE_URL`,
`SUPABASE_ANON_KEY` and `CLOUDFLARE_API_TOKEN` are set, and reports which are
missing by **name only**. Nothing in the workflow ever echoes a value.

**Variables and Secrets are separate namespaces.** A value put in the wrong one
reads as *empty*, not as an error, so the symptom is a step that skips or a tool
that reports a missing setting. The two non-secret names are read as
`vars.X || secrets.X` so either works, but prefer **Variables**: a secret is
masked as `***` everywhere it appears, which makes a URL unreadable in logs.

**Trailing whitespace is the other one.** A space pasted into the Settings form is
invisible in the UI, survives to the runner, and surfaces as two errors that look
nothing alike and nothing like their cause:

```
python -> http.client.InvalidURL: URL can't contain control characters
curl   -> (3) URL rejected: Malformed input to a URL function
```

Both jobs now strip whitespace from `SITE_URL` and `SUPABASE_URL` and emit a
`::warning::` when they had to. Secrets are **not** trimmed and re-exported — a
modified copy stops matching the registered value, so GitHub would stop masking
it in logs. A secret with a stray space fails the run and must be fixed at source.

### Rotating the Cloudflare token

Rotated **2026-08-15** — the previous token had been pasted into a session
transcript. Create the replacement with the scopes below, add it as the
`CLOUDFLARE_API_TOKEN` Actions secret, then **delete the old token** in the
dashboard; a rotation is not finished until the old credential is dead.

Verify a replacement without printing it — each call needs one of the four scopes:

```bash
curl -s https://api.cloudflare.com/client/v4/user/tokens/verify \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"                    # active?
curl -s https://api.cloudflare.com/client/v4/accounts \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"                    # Account Settings:Read
curl -s https://api.cloudflare.com/client/v4/accounts/$ACC/workers/scripts \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"                    # Workers Scripts:Edit
curl -s https://api.cloudflare.com/client/v4/zones/$ZONE/workers/routes \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"                    # Workers Routes
curl -s https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"                    # DNS
```

A token missing a scope returns `success: false` with an authentication error on
that call alone, so the four together tell you which permission was forgotten.
The DNS one is the easy omission: it is not in the stock Workers template and is
only needed because `custom_domain = true` makes wrangler manage the `www` record.

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
in the browser. The token exists for CI, and CI is now where it should be used —
`.github/workflows/site.yml` deploys on push to `main`, so the credential need
never enter a container or a transcript again. That is what the by-hand commands
above cost you, and why the previous token had to be rotated.

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

### Apex records wrangler does not own

"wrangler owns DNS for this zone" is **not true at the apex**, and anything that
reconciles DNS against this repo is working from an incomplete picture. Two records
exist only in the dashboard, are declared nowhere in `wrangler.toml`, and each has
something depending on it:

| Record | Depended on by | What deleting it does |
|---|---|---|
| `AAAA @ → 100::`, **proxied** | the apex→www Redirect Rule | The rule only fires on proxied traffic, so the redirect silently stops working **while the rule still shows "Active"** — nothing anywhere reports a fault |
| `TXT @ → v=MCPv1; k=ed25519; p=1R6K…` | the `net.gwindex` registry claim | The keypair stops authenticating and the registry entry can no longer be republished |

Only `www` is wrangler's, and it should stay that way. Do not "clean up" the apex
to match the repo — the repo was never the source of truth for these two.

Note that the deploy token deliberately carries Zone → DNS on this zone, so it
*could* remove them. A token scoped to only Workers Scripts + Account Settings +
Workers Routes could not — but that narrower set is not sufficient for
`custom_domain = true` to manage the `www` record either, which is why DNS is in
the list. Verified 2026-08-15 on the rotated token: a deliberately empty
`POST /dns_records` came back with a **validation** error (`9000`), not an
authentication error (`10000`), which is what distinguishes DNS:Edit from DNS:Read
without creating anything.

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
