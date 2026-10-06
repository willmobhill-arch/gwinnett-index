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
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ENDPOINT = "https://api.indexnow.org/indexnow"
UA = "gwindex-indexnow/1.0 (+https://www.gwindex.net)"
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


def verify_key(key_url: str, key: str, attempts: int = 6, delay: int = 20) -> bool:
    """Confirm the key file is actually being served before submitting.

    This exists because of how 403 presents. IndexNow's 403 means "the key file
    could not be fetched, or its body did not match" -- one code for both halves,
    so it tells you nothing about which. The first real submission got exactly
    that, on a key file that was verifiably live, 200, text/plain, 32 bytes, body
    matching, with zero requests to it in the zone's logs. The documented cause of
    a first-submission 403 is submitting before the CDN is serving the new key
    file; the documented remedy is to poll the key URL first and retry once.

    So: prove the key is readable from outside, then submit. A failure here names
    the actual problem instead of handing back an ambiguous 403.
    """
    for i in range(1, attempts + 1):
        try:
            req = urllib.request.Request(key_url, headers={"user-agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(200).decode("utf-8", "replace").strip()
            if r.status == 200 and body == key:
                print(f"  key file verified at {key_url} (attempt {i})")
                return True
            print(f"  attempt {i}: {r.status}, body {body[:40]!r} — want 200 and {key[:12]}…")
        except Exception as e:
            print(f"  attempt {i}: {type(e).__name__}: {e}")
        if i < attempts:
            time.sleep(delay)
    print(f"::error::key file at {key_url} never served the key. "
          "IndexNow would answer 403 and blame the key; the real cause is that "
          "this file is not readable yet.")
    return False


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
            headers={"user-agent": UA},
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


def submit(host: str, key: str, key_url: str, urls: list[str], retry: bool = True) -> int:
    payload = json.dumps(
        {"host": host, "key": key, "keyLocation": key_url, "urlList": urls}
    ).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"content-type": "application/json; charset=utf-8",
                 "user-agent": UA},
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
    if code in (200, 202):
        print(f"  {code} {note} ({len(urls)} URLs)")
        return 0
    # 403 and 429 are the two the documented remedy covers: a key file the far
    # side has not managed to read yet, and throttling. Both are worth exactly
    # one more try after a pause. Anything else is not a waiting problem.
    if retry and code in (403, 429):
        print(f"  {code} {note} — retrying once in 45s")
        time.sleep(45)
        return submit(host, key, key_url, urls, retry=False)
    print(f"::error::IndexNow returned {code} — {note}")
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

    if not verify_key(key_url, key):
        return 1

    rc = 0
    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        print(f"submitting {i + 1}-{i + len(chunk)} of {len(urls)}")
        rc |= submit(host, key, key_url, chunk)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
