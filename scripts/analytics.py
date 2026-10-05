#!/usr/bin/env python3
"""Report who is actually reading the index, from the Cloudflare Analytics API.

Written because the obvious dashboards answer the wrong question. This project's
audience is crawlers and agents, and the two surfaces that are easiest to look at
are both structurally blind to them:

  * Web Analytics (RUM) is a JavaScript beacon. Anything that does not execute JS
    -- which is most of the audience -- never fires it. Measured 2026-10-05: RUM
    saw 3,120 pageloads over a window in which the zone served 194,825. Reading
    RUM as "traffic" undercounts by ~60x and systematically hides exactly the
    population that matters. RUM is therefore NOT queried here at all.
  * Worker analytics covers only what `run_worker_first` routes to the Worker
    (/v1/*, /mcp, /openapi.json). The 30,000-odd static assets -- the corpus, the
    .md twins, llms.txt, the bulk export -- are served by the platform without
    invoking Worker code, so they generate no Worker invocation. That is the
    architecture working as designed, not a gap to fix, but it means Worker
    request counts are not corpus traffic.

So the numbers worth tracking come from three different places, and this script
pulls all three and prints them side by side.

THE DEMAND METRIC IS SUBREQUESTS, NOT REQUESTS. There is no cache layer in the
Worker: every data route (/v1/resolve, /v1/cases, /v1/jurisdictions, and every
MCP tools/call) goes through worker/src/db.ts, which fetches Supabase. A fetch is
a subrequest. So subrequests ~= real tool calls, while `requests` is dominated by
MCP registry liveness monitors that probe /mcp and never invoke a tool -- one of
them says so in its own user agent string ("liveness-only, never invokes tools").
On 2026-09-05 the Worker served 1,164 requests and made 0 subrequests. Requests
measure discovery; subrequests measure use.

Usage:

    CLOUDFLARE_API_TOKEN=... python3 scripts/analytics.py
    CLOUDFLARE_API_TOKEN=... python3 scripts/analytics.py --json > var/analytics-$(date -u +%F).json

The token needs Zone:Read, Zone Analytics:Read and Account Analytics:Read. Without
Zone Analytics:Read the GraphQL endpoint returns an authz error naming the missing
permission 'com.cloudflare.api.account.zone.analytics.read' -- which is the whole
corpus-traffic picture, so the script fails loudly rather than reporting partial.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.cloudflare.com/client/v4"
GRAPHQL = API + "/graphql"
ZONE_NAME = os.environ.get("GWINDEX_ZONE", "gwindex.net")
WORKER = os.environ.get("GWINDEX_WORKER", "gwinnett-index")

# Crawlers we want, matched on user-agent substring. Bytespider is the trap here:
# it does not name itself. It ships a malformed desktop-mobile hybrid UA whose
# tell is "(HTML, like Gecko)" -- note the missing K, every honest UA says KHTML
# -- so a substring match on a product token finds everything except the single
# largest AI crawler hitting this zone. Match its signature, not its name.
AI_AGENTS = [
    ("ClaudeBot", "ClaudeBot"),
    ("Claude-User", "Claude-User"),
    ("Claude-SearchBot", "Claude-SearchBot"),
    ("GPTBot", "GPTBot"),
    ("ChatGPT-User", "ChatGPT-User"),
    ("OAI-SearchBot", "OAI-SearchBot"),
    ("PerplexityBot", "PerplexityBot"),
    ("Perplexity-User", "Perplexity-User"),
    ("CCBot", "CCBot"),
    ("Amazonbot", "Amazonbot"),
    ("Applebot", "Applebot"),
    ("meta-externalagent", "meta-externalagent"),
    ("Bytespider (ByteDance)", "(HTML, like Gecko)"),
]
SEARCH_AGENTS = [("Googlebot", "Googlebot"), ("bingbot", "bingbot")]


def _post(payload: dict, token: str) -> dict:
    req = urllib.request.Request(
        GRAPHQL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        msg = body["errors"][0].get("message", "")
        # A single field the plan does not cover nulls the ENTIRE response, not
        # just the offending alias -- so one Enterprise-only dimension smuggled
        # into a batch silently zeroes every other number in it. That is why each
        # dimension below gets its own request instead of one batched query.
        sys.exit(f"GraphQL error: {msg}")
    return body["data"]


def _get(path: str, token: str) -> dict:
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def zone_and_account(token: str) -> tuple[str, str]:
    for z in _get("/zones", token).get("result") or []:
        if z["name"] == ZONE_NAME:
            return z["id"], z["account"]["id"]
    sys.exit(f"zone {ZONE_NAME!r} not visible to this token")


def daily_zone(zone: str, token: str, days: int) -> list[dict]:
    """Zone-wide HTTP totals. httpRequests1dGroups has 30d retention on this plan."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    until = datetime.now(timezone.utc).date().isoformat()
    q = """query($z:String!,$since:Date!,$until:Date!){viewer{zones(filter:{zoneTag:$z}){
      httpRequests1dGroups(limit:60,filter:{date_geq:$since,date_leq:$until},orderBy:[date_ASC]){
        dimensions{date} sum{requests pageViews bytes cachedRequests} uniq{uniques}}}}}"""
    d = _post({"query": q, "variables": {"z": zone, "since": since, "until": until}}, token)
    return d["viewer"]["zones"][0]["httpRequests1dGroups"]


def daily_worker(account: str, token: str, days: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    until = datetime.now(timezone.utc).isoformat()
    q = """query($a:String!,$s:Time!,$u:Time!){viewer{accounts(filter:{accountTag:$a}){
      workersInvocationsAdaptive(limit:100,filter:{scriptName:$n,datetime_geq:$s,datetime_leq:$u},
        orderBy:[date_ASC]){dimensions{date status} sum{requests errors subrequests}}}}}"""
    q = q.replace("$n", json.dumps(WORKER))
    d = _post({"query": q, "variables": {"a": account, "s": since, "u": until}}, token)
    return d["viewer"]["accounts"][0]["workersInvocationsAdaptive"]


def adaptive(zone: str, token: str, dim: str, limit: int, extra: str = "") -> list[dict]:
    """Group the last 24h by one dimension.

    THE WINDOW IS NOT A CHOICE. httpRequestsAdaptiveGroups is capped at a 1-day
    span on this plan; ask for 30 days and the whole query is rejected with a
    quota error ("cannot request a time range wider than 1d"). Every per-agent
    number in this report is therefore a 24h snapshot, and only the zone/Worker
    daily series above can show a trend. Do not average these across months.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    since = (now - timedelta(hours=23)).isoformat()
    q = f"""query($z:String!,$s:Time!,$u:Time!){{viewer{{zones(filter:{{zoneTag:$z}}){{
      g: httpRequestsAdaptiveGroups(limit:{limit},
        filter:{{datetime_geq:$s,datetime_leq:$u{extra}}},orderBy:[count_DESC]){{
        dimensions{{{dim}}} count}}}}}}}}"""
    d = _post({"query": q, "variables": {"z": zone, "s": since, "u": now.isoformat()}}, token)
    return d["viewer"]["zones"][0]["g"]


def collect(token: str, days: int = 30) -> dict:
    zone, account = zone_and_account(token)
    zrows = daily_zone(zone, token, days)
    wrows = daily_worker(account, token, days)

    uas = adaptive(zone, token, "userAgent", 200)
    total = sum(r["count"] for r in uas)

    def match(table):
        out = {}
        for label, needle in table:
            n = sum(r["count"] for r in uas if needle in (r["dimensions"]["userAgent"] or ""))
            if n:
                out[label] = n
        return out

    md = adaptive(zone, token, "edgeResponseStatus", 10, ',clientRequestPath_like:"%.md"')
    md_by_cat = adaptive(zone, token, "verifiedBotCategory", 10, ',clientRequestPath_like:"%.md"')

    # A user agent is a claim, not an identity. Measured 2026-10-05: 26 requests
    # carried the Googlebot UA string and Cloudflare verified only 9 of them as
    # actually originating from Google. The UA counts above are therefore upper
    # bounds, and the gap between the two is the spoofing. Report both; never
    # quote the UA number alone as "Googlebot crawled us N times".
    verified = adaptive(zone, token, "verifiedBotCategory", 15)

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": days,
        "zone": {
            "requests": sum(r["sum"]["requests"] for r in zrows),
            "page_views": sum(r["sum"]["pageViews"] for r in zrows),
            "bytes": sum(r["sum"]["bytes"] for r in zrows),
            "cache_hit_pct": round(
                100 * sum(r["sum"]["cachedRequests"] for r in zrows)
                / max(sum(r["sum"]["requests"] for r in zrows), 1), 1),
            "daily": [{"date": r["dimensions"]["date"], "requests": r["sum"]["requests"],
                       "page_views": r["sum"]["pageViews"]} for r in zrows],
        },
        "worker": {
            "requests": sum(r["sum"]["requests"] for r in wrows),
            "errors": sum(r["sum"]["errors"] for r in wrows),
            # The headline. See the module docstring: this is real tool calls.
            "subrequests": sum(r["sum"]["subrequests"] for r in wrows),
            "subrequests_daily": [
                {"date": r["dimensions"]["date"], "n": r["sum"]["subrequests"]}
                for r in wrows if r["sum"]["subrequests"]
            ],
        },
        "last_24h": {
            "requests_sampled": total,
            "ai_agents": match(AI_AGENTS),
            "search_engines": match(SEARCH_AGENTS),
            # Cloudflare's own verification, independent of what the UA claims.
            "verified_categories": {
                (r["dimensions"]["verifiedBotCategory"] or "unclassified"): r["count"]
                for r in verified
            },
            "md_twin_fetches": sum(r["count"] for r in md),
            "md_twin_by_category": {
                (r["dimensions"]["verifiedBotCategory"] or "unclassified"): r["count"]
                for r in md_by_cat
            },
            "top_agents": [
                {"ua": (r["dimensions"]["userAgent"] or "")[:90], "count": r["count"]}
                for r in uas[:10]
            ],
        },
    }


def render(d: dict) -> None:
    z, w, h = d["zone"], d["worker"], d["last_24h"]
    print(f"Gwinnett Index — {d['generated']}  ({d['window_days']}d window)\n")
    print(f"  corpus      {z['requests']:>9,} requests   {z['page_views']:>9,} pageviews"
          f"   {z['bytes']/1e9:.2f} GB   {z['cache_hit_pct']}% cached")
    print(f"  worker      {w['requests']:>9,} invocations  {w['errors']} errors")
    print(f"  TOOL CALLS  {w['subrequests']:>9,} subrequests  "
          f"({len(w['subrequests_daily'])} of {d['window_days']} days non-zero)")
    if w["subrequests_daily"]:
        tail = w["subrequests_daily"][-7:]
        print("              last 7 active days: " + "  ".join(f"{r['date'][5:]}={r['n']}" for r in tail))

    print(f"\n  last 24h ({h['requests_sampled']:,} requests)")
    print(f"    .md twin fetches   {h['md_twin_fetches']:,}")
    for cat, n in sorted(h["md_twin_by_category"].items(), key=lambda kv: -kv[1]):
        print(f"        {n:>7,}  {cat}")
    print("    AI agents")
    if h["ai_agents"]:
        for k, n in sorted(h["ai_agents"].items(), key=lambda kv: -kv[1]):
            print(f"        {n:>7,}  {k}")
    else:
        print("            (none — check AI_AGENTS signatures against top_agents)")
    print("    search engines (UA claim — spoofable, see verified below)")
    for k, n in sorted(h["search_engines"].items(), key=lambda kv: -kv[1]):
        print(f"        {n:>7,}  {k}")
    print("    verified bot categories (Cloudflare-verified origin)")
    for k, n in sorted(h["verified_categories"].items(), key=lambda kv: -kv[1]):
        print(f"        {n:>7,}  {k}")
    print("    top user agents")
    for r in h["top_agents"]:
        print(f"        {r['count']:>7,}  {r['ua']}")


def main() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("CLOUDFLARE_API_TOKEN is required (Zone:Read + Zone Analytics:Read + Account Analytics:Read)")
    try:
        data = collect(token)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from Cloudflare: {e.read()[:300].decode('utf-8', 'replace')}")
    if "--json" in sys.argv:
        json.dump(data, sys.stdout, indent=2)
        print()
    else:
        render(data)


if __name__ == "__main__":
    main()
