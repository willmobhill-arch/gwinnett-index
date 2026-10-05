#!/usr/bin/env python3
"""Keep the Supabase project warm, and fail loudly the moment it is not.

Why this exists. The project is on the Supabase free plan, which pauses a
project after a 7-day low-activity window. On 2026-09-07 it did exactly that,
and the API and MCP server answered "upstream 530: error code 1016" for a month
before anyone noticed. Nothing looked wrong, because nothing that was being
watched could see it:

  * The Worker catches the upstream failure and returns a JSON error, so
    workersInvocationsAdaptive reported errors=0 throughout.
  * MCP transports failures in the JSON-RPC body, so a failed tools/call is
    HTTP 200 with isError:true -- indistinguishable at the edge from a good one.
  * Subrequests counted fetch attempts, which kept rising, so the outage looked
    like growing demand.

The only thing touching the database was site.yml's weekly cron. Supabase's
guidance is "a few user requests to the database each day over the previous
week", so a weekly heartbeat against a 7-day threshold was always going to lose
that race eventually.

So this does two jobs at once, and runs daily:

  1. Makes several real anon reads, which is what keeps the project unpaused.
  2. Asserts it got ROWS back, not just a 200. A 200 carrying an empty array is
     the failure shape this repo keeps rediscovering -- "a queue of zero is a
     bug, not a result" -- so zero rows is a hard failure here.

    SUPABASE_URL=... SUPABASE_ANON_KEY=... SITE_URL=... python3 scripts/keepalive.py

SITE_URL is optional; when set, the live data path is probed too, because a warm
database is not the same as a working product.

Lives in scripts/ rather than inline in the workflow on purpose: the first
version of this was a heredoc inside a YAML block scalar, where the Python body
sat at column 0 and silently terminated the scalar. Logic that needs quoting
belongs in a file that can be run by hand.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Identify ourselves. urllib's default "Python-urllib/3.x" is signature-banned
# by the gwindex.net zone (403, error_1010 browser_signature_banned), which a
# naive probe reports as the site being down.
UA = "gwindex-keepalive/1.0 (+https://www.gwindex.net)"

# (label, path, minimum rows). Several distinct reads, because the pause
# threshold is about activity across a week, not a single touch. The minimums
# are deliberately below the real counts -- this is a liveness check, not a
# corpus assertion, and tightening them here would make it fail for reasons
# that belong to tests/.
READS = [
    ("jurisdiction", "jurisdiction?select=slug,name&limit=25", 19),
    ("code_table", "code_table?select=citation&limit=25", 20),
    ("land_use_case", "land_use_case?select=case_number&limit=5", 5),
]

failures: list[str] = []


def fail(msg: str) -> None:
    # GitHub Actions renders ::error:: as an annotation on the run.
    print(f"::error::{msg}")
    failures.append(msg)


def _json(url: str, *, headers: dict, data: bytes | None = None) -> tuple[object, str]:
    req = urllib.request.Request(url, data=data, headers={"user-agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read(2000).decode("utf-8", "replace")
        return None, f"HTTP {e.code}: {raw[:300]}"
    except Exception as e:  # DNS, TLS, timeout -- a paused project is DNS
        return None, f"{type(e).__name__}: {e}"
    try:
        return json.loads(raw), ""
    except Exception:
        return None, f"response was not JSON: {raw[:300]}"


def supabase_headers(key: str) -> dict:
    return {"apikey": key, "authorization": f"Bearer {key}", "accept": "application/json"}


def check_reads(base: str, key: str) -> None:
    for label, path, minimum in READS:
        payload, err = _json(f"{base}/rest/v1/{path}", headers=supabase_headers(key))
        if err:
            fail(f"{label}: {err}")
            continue
        if isinstance(payload, dict) and payload.get("message"):
            fail(f"{label}: postgrest said {payload['message']!r}")
            continue
        if not isinstance(payload, list) or len(payload) < minimum:
            fail(f"{label}: expected >= {minimum} rows, got {json.dumps(payload)[:200]}")
            continue
        print(f"  ok  {label}: {len(payload)} rows")


def check_resolver(base: str, key: str) -> None:
    """The product's actual question, which also keeps PostGIS warm.

    Which jurisdiction comes back is tests/test_resolver.py's business, not
    this job's. Asserting geography here would make a liveness check go red for
    a correctness reason, so this asserts only that a row with a slug arrived.
    """
    body = json.dumps({"lon": -84.1446, "lat": 34.0029, "band_m": 150}).encode()
    payload, err = _json(
        f"{base}/rest/v1/rpc/resolve_jurisdiction",
        headers={**supabase_headers(key), "content-type": "application/json"},
        data=body,
    )
    if err:
        return fail(f"resolver: {err}")
    if isinstance(payload, dict) and payload.get("message"):
        return fail(f"resolver: postgrest said {payload['message']!r}")
    if not payload or not (payload[0] or {}).get("slug"):
        return fail(f"resolver returned no jurisdiction: {json.dumps(payload)[:200]}")
    row = payload[0]
    print(f"  ok  resolver: {row['slug']} (confidence={row.get('confidence')})")


def check_live_site(site: str) -> None:
    """A warm database is not a working product; this catches the Worker half."""
    payload, err = _json(f"{site}/v1/jurisdictions", headers={"accept": "application/json"})
    if err:
        return fail(f"live data path: {err}")
    # A 200 whose body is an error object still means the data path is down --
    # which is exactly how the month-long outage presented.
    if isinstance(payload, dict) and payload.get("error"):
        return fail(f"live data path answered 200 with an error: {payload['error']}")
    rows = payload if isinstance(payload, list) else (payload or {}).get("jurisdictions") or []
    if not rows:
        return fail(f"live data path returned nothing: {json.dumps(payload)[:200]}")
    print(f"  ok  live /v1/jurisdictions: {len(rows)} jurisdictions")


def main() -> int:
    base = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    site = os.environ.get("SITE_URL", "").strip().rstrip("/")
    if not base or not key:
        print("::error::set SUPABASE_URL and SUPABASE_ANON_KEY")
        return 2

    print(f"database {base}")
    check_reads(base, key)
    check_resolver(base, key)
    if site:
        print(f"site {site}")
        check_live_site(site)
    else:
        print("  --  SITE_URL unset, skipping the live data path probe")

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
