#!/usr/bin/env python3
"""Tell Bing and Yandex which URLs changed, via IndexNow.

Why this exists. Search Console reported a deep code section as "URL is unknown
to Google" -- never discovered, not crawled and declined. Measured at the same
time: Googlebot made ~9 requests in 24 hours and had never once fetched
/sitemap.xml, so none of the 15,238 URLs had entered its queue, and
link-following discovery stalls at depth 1. Discovery, not crawl budget, is the
binding constraint.

IndexNow fixes that for the engine that is actually crawling. Measured in the
same window: bingbot made 167 requests against Googlebot's 9. Bing also feeds
Copilot, which serves this project's citation goal.

IT DOES NOT HELP GOOGLE. Google is not an IndexNow participant, so the Google
half of the discovery problem stays with the sitemap and internal linking. Do
not let a green run here be read as "search engines have been notified".

THE KEY HAS ONE SOURCE OF TRUTH. IndexNow authenticates by fetching
https://<host>/<key>.txt and checking the body equals the key. Rather than hold
the key in a secret that can drift out of step with the published file, this
script discovers it from site/public/: the file whose name stem equals its own
contents IS the key. Two copies cannot disagree because there is only one.
verify-build.mjs asserts the file survives into dist/.

    SITE_URL=https://www.gwindex.net python3 scripts/indexnow.py --since 2026-10-06
    SITE_URL=https://www.gwindex.net python3 scripts/indexnow.py --all --dry-run

--since submits only URLs whose sitemap <lastmod> is on or after that date,
which is what a deploy should send: IndexNow's guidance is to submit changed
URLs, not to re-announce a whole site on every run. --all is for the one-time
seed, and batches because the per-request ceiling is 10,000 URLs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10_000  # IndexNow's documented per-request ceiling
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ROOT = Path(__file__).resolve().parent.parent

# What the endpoint's status codes actually mean. 403 is the one to expect first:
# it means the key file is not reachable yet, which is the normal state until the
# commit carrying it has been deployed.
STATUS = {
    200: "OK — URLs submitted",
    202: "Accepted — received, key validation still pending",
    400: "Bad request — malformed submission",
    403: "Forbidden — key not valid; is the key file deployed and readable?",
    422: "Unprocessable — URLs do not belong to the host, or the key is malformed",
    429: "Too many requests — throttled; submit changed URLs only, not everything",
}


def find_key() -> tuple[str, Path]:
    """The key is whichever file in site/public/ contains its own name stem."""
    pub = ROOT / "site" / "public"
    for f in sorted(pub.glob("*.txt")):
        try:
            if f.read_text(encoding="utf-8").strip() == f.stem:
                return f.stem, f
        except OSError:
            continue
    sys.exit(
        "no IndexNow key file found in site/public/.\n"
        "Create one as <key>.txt whose contents are exactly <key> "
        "(8-128 chars of a-z A-Z 0-9 and dashes)."
    )


def load_sitemap(site: str) -> list[tuple[str, str]]:
    """Prefer the built sitemap on disk; fall back to the live one.

    Reading dist/ keeps a CI run deterministic and tied to the artifact just
    built, rather than to whatever happens to be live at that moment.
    """
    local = ROOT / "site" / "dist" / "sitemap.xml"
    if local.exists():
        root = ET.parse(local).getroot()
        src = str(local)
    else:
        req = urllib.request.Request(
            f"{site}/sitemap.xml",
            headers={"user-agent": "gwindex-indexnow/1.0 (+https://www.gwindex.net)"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            root = ET.fromstring(r.read())
        src = f"{site}/sitemap.xml"
    out = []
    for u in root.findall("s:url", NS):
        loc = u.find("s:loc", NS)
        mod = u.find("s:lastmod", NS)
        if loc is not None and loc.text:
            out.append((loc.text.strip(), (mod.text or "").strip() if mod is not None else ""))
    print(f"sitemap: {src} — {len(out)} URLs")
    return out


def submit(host: str, key: str, key_url: str, urls: list[str]) -> int:
    payload = json.dumps(
        {"host": host, "key": key, "keyLocation": key_url, "urlList": urls}
    ).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"content-type": "application/json; charset=utf-8",
                 "user-agent": "gwindex-indexnow/1.0 (+https://www.gwindex.net)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        print(f"::error::IndexNow request failed: {type(e).__name__}: {e}")
        return 1
    note = STATUS.get(code, "unrecognised status")
    stream = print
    if code in (200, 202):
        stream(f"  {code} {note} ({len(urls)} URLs)")
        return 0
    stream(f"::error::IndexNow returned {code} — {note}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--since", metavar="YYYY-MM-DD",
                   help="submit URLs whose sitemap lastmod is >= this date")
    g.add_argument("--all", action="store_true",
                   help="submit every URL (one-time seed; batched)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be sent and exit without submitting")
    a = ap.parse_args()

    site = os.environ.get("SITE_URL", "").strip().rstrip("/")
    if not site:
        return int(bool(print("::error::SITE_URL is required")))
    host = site.split("//", 1)[-1]

    key, key_path = find_key()
    key_url = f"{site}/{key}.txt"
    print(f"host {host}\nkey  {key} (from {key_path.relative_to(ROOT)})\nkeyLocation {key_url}")

    rows = load_sitemap(site)
    if a.all:
        urls = [u for u, _ in rows]
        why = "all URLs"
    else:
        urls = [u for u, m in rows if m and m >= a.since]  # ISO dates sort lexically
        why = f"lastmod >= {a.since}"

    # A fixture-mode or local build writes http://localhost:4321 into the
    # sitemap, and nothing else here would notice: IndexNow would answer 422
    # ("URLs do not belong to the host") and the real cause -- a build made with
    # a different SITE_URL than the one being submitted for -- would be two
    # steps removed from the error. Caught here, it names itself. Found by
    # running --dry-run against a fixture build, which cheerfully selected 53
    # localhost URLs.
    foreign = [u for u in urls if not u.startswith(site + "/")]
    if foreign:
        print(f"::error::{len(foreign)} of {len(urls)} selected URLs do not match "
              f"SITE_URL ({site}) — the built sitemap was made with a different "
              f"SITE_URL. First: {foreign[0]}")
        return 1

    print(f"selected: {len(urls)} URLs ({why})")
    if not urls:
        # Not an error. A deploy that changed no dated records has nothing to
        # announce, and inventing a submission would just burn the rate limit.
        print("nothing to submit")
        return 0
    for u in urls[:5]:
        print(f"  e.g. {u}")

    if a.dry_run:
        batches = (len(urls) + BATCH - 1) // BATCH
        print(f"dry run — would send {batches} request(s) of up to {BATCH} URLs")
        return 0

    rc = 0
    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        print(f"submitting {i + 1}-{i + len(chunk)} of {len(urls)}")
        rc |= submit(host, key, key_url, chunk)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
