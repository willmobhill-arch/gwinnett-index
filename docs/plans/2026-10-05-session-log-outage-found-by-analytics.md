# Session log: a month-long outage found by building an analytics script

**Date:** 2026-10-05
**What happened:** a request for website analytics turned into finding that the
API and MCP server had been down since **2026-09-07** — the Supabase project had
auto-paused and every data request had been answering `upstream 530: error code
1016` for a month. Restored, root-caused, and fixed with a daily keep-alive.
Shipped `scripts/analytics.py` and `scripts/keepalive.py`, merged (#7), and
deployed — the first deploy to `main` since 2026-08-17.

---

## How it was found, and why that order matters

The outage was not found by looking for it. It surfaced because each layer of
measurement contradicted the one below it:

1. **Web Analytics said ~3,120 pageloads in 30 days.** That read as "nobody has
   found the site".
2. **Zone analytics said 194,825.** RUM is a JavaScript beacon, so it cannot see
   the crawler population this project exists for — a ~60x undercount that hides
   exactly the audience that matters. The zone-analytics token permission was the
   whole picture; without it every conclusion was wrong.
3. **The Worker reported 1,180 requests/day and 0 errors.** That read as healthy
   demand.
4. **Subrequests were ~0.** No cache layer exists in the Worker, so every data
   route fetches Supabase and a real tool call always costs a subrequest. 1,180
   requests against 4 subrequests in 17 days meant nothing was retrieving data.
5. **The `/mcp` user agents explained it**: `SentinelOracle/0.1 (liveness-only,
   never invokes tools)`, `mcpbeat/0.1 (liveness check)`, `rokmcp-collector`,
   `GolemreachTrustBot`. MCP *registry uptime monitors*. One declares in its UA
   that it never calls a tool.
6. **Then subrequests started rising** — 65 over 30 days, every day, 9 on the
   last. That read as demand finally arriving. It was the opposite: every one of
   them was failing.

## Why nothing caught the outage — the real lesson

Four independent metrics all looked healthy during a total outage, and each for
a structural reason:

- **The Worker's `errors` counts uncaught exceptions.** It catches the upstream
  failure and returns a JSON error, so `errors: 0` held while 100% of data
  requests failed. "Zero errors" was true and meant nothing.
- **MCP transports failures inside a successful response** — a failed
  `tools/call` is HTTP 200 with `isError: true`. `edgeResponseStatus` cannot
  distinguish it from a good one.
- **`originResponseStatus` is 0 for every `/mcp` request**, because the Worker
  *is* the origin. There is no upstream status to read.
- **Subrequests count attempts, not answers.** A rising count during a complete
  outage is indistinguishable from growing demand.

**No Cloudflare-side metric can detect this.** Only an active probe can, which
is why `analytics.py` now leads with one and `keepalive.py` exists.

The weekly `site` workflow *did* catch it — red for five consecutive runs
(Sep 7/14/21/28, Oct 5), failing in `export_snapshot_rest.py` on
`URLError: [Errno -2] Name or service not known`, in about 15 seconds each. A
gate that fires into a channel nobody reads is not a gate. It also explains the
sitemap `lastmod` stuck at `2026-08-17`: the export had not succeeded since.

## Root cause

The only thing touching the database was `site.yml`'s weekly cron. The Supabase
free plan pauses after a 7-day low-activity window, and their guidance is "a few
user requests to the database each day over the previous week". **A weekly
heartbeat against a 7-day threshold was always going to lose that race** — the
pause was structural, not bad luck. The live API's own traffic was ~2 failing
requests/day, which does not count as activity.

Restore took ~3 minutes and moved through a sequence worth knowing:
`1016` (no DNS) → `521` (origin refusing) → `404` → `PGRST002` (PostgREST
schema cache warming) → healthy.

There is a **90-day window** to restore a paused project; this one was used on
day 28 of it.

## What the architecture got right

The corpus never went down. 231,000+ pageviews, 15,238 pages, the `.md` twins
and `llms.txt` all served normally through a month-long database outage, because
`run_worker_first` is scoped to `/v1/*`, `/mcp` and `/openapi.json` and
everything else comes off the asset store. That decision did precisely what
CLAUDE.md says it was for.

## Traps hit in my own code, while writing the thing that detects traps

- **A silent cap is a silent deletion, again.** The probe capped its read at 2000
  bytes and then `json.loads()`'d it, so a healthy 19-jurisdiction response
  truncated mid-string and the probe reported `DATA PATH *** DOWN ***` — a cap
  turning a success into a failure, inside the one function whose entire job is
  to not do that.
- **urllib's default UA is signature-banned by this zone** (`403 error_1010
  browser_signature_banned`). The first probe reported that as the site being
  down. A probe that cannot tell *blocked* from *broken* is worse than no probe,
  so a Cloudflare 101x/102x block is now UNKNOWN, not DOWN. Side finding:
  signature-based blocking is live on the zone, which is what the weekly cron was
  written to watch for.
- **A heredoc inside a YAML block scalar silently terminates it.** The keep-alive
  began as inline Python in `run: |`; the body sat at column 0 and ended the
  scalar, and the `<<'PY' <<<"$body"` double redirect would have discarded the
  heredoc anyway. Logic that needs quoting belongs in a file that can be run by
  hand — which is how both bugs above were caught.
- **One unauthorized GraphQL field nulls the entire response**, not just its own
  alias. An Enterprise-only dimension (`botScoreSrcName`,
  `clientASNDescription`) in a batched query zeroes every other number in it.
- **`httpRequestsAdaptiveGroups` is capped at a 1-day span** on this plan, so
  per-agent figures cannot trend; only the daily series can.
- **Bytespider does not name itself.** Its tell is `(HTML, like Gecko)` —
  missing the K that every honest UA carries.
- **A user agent is a claim, not an identity.** 26 requests carried the Googlebot
  UA; Cloudflare verified 9. The gap is the spoofing, so both get reported.

## What the traffic actually is

Measured 24h, 13,894 requests:

| Category | Share |
|---|---|
| SEO backlink crawlers (SemrushBot alone 5,472 = 38%) | ~41% |
| Unclassified, rotating Chrome UAs | ~40% |
| MCP registry liveness monitors (`/mcp`, 1,438 hits) | ~10% |
| Named frontier-lab agents (ClaudeBot 23, GPTBot 4, ChatGPT-User 4, PerplexityBot 6, OAI-SearchBot 5, CCBot 1) | ~0.3% |

**2,390 `.md` twin fetches in 24h, and 2,077 of them come from the unclassified
rotating-UA cluster.** That actor found the `.md` convention and is harvesting
the corpus while cycling user agents to avoid classification. Bytespider takes
another 266. The agent surface is being consumed — mostly by someone who will
not say who they are.

Googlebot: **9 verified hits/day** against bingbot's 167. Checked and ruled out
as a technical fault — `robots.txt` allows it explicitly, canonicals are
self-referential and match the sitemap, `meta robots` is `index, follow`, there
is no `X-Robots-Tag`, and Googlebot's UA gets 200 on `/`, `/sitemap.xml`, a deep
page and a `.md` twin in 0.24s. It is an authority problem, not a crawlability
one.

## Deliberately not done

**`/.well-known/agent-card.json` was not created**, despite ~100 404s/day there.
An A2A agent card declares A2A interfaces at a declared endpoint; this is an MCP
server plus a static corpus, and MCP is not an A2A protocol binding. A
well-formed card pointing at `/mcp` would tell every reader this is an A2A agent
when it is not — a confident wrong answer wearing a standard's clothes. The 404
is the correct answer, as is the one at
`/.well-known/oauth-protected-resource` for an MCP server that needs no auth.
(The normative A2A spec host is blocked by this container's egress proxy, which
is a second reason not to publish a machine-readable contract built from
secondary sources.)

## Open

- **Search Console.** Unreachable from here; needs the property verified and the
  sitemap submitted. Highest-leverage item for the authority goal.
- **The harvester.** ~2,000 `.md` pages/day to an unidentified actor. Strategic
  question, not a nuisance: an anonymous bulk copy is the opposite of a citation.
- **`cache-control: public, max-age=0, must-revalidate` on HTML**, so the edge
  revalidates every request (41% cache hit). Deliberately not changed — for a
  legal-reference corpus the right shape is `s-maxage` plus a purge on deploy,
  which is a decision, not a tweak.
- **Second deploy caveat:** the merge published a regenerated corpus without
  anyone diffing the snapshot first. Gates passed and live spot-checks are
  correct, but the Aug 17 → Oct 5 snapshot diff has not been reviewed.
- 262 applicant merge candidates, Duluth OCR, meeting body text — all unchanged.
