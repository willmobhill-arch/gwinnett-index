#!/usr/bin/env python3
"""
Crawl City of Duluth meeting agendas, minutes, and agenda packets.

Duluth has no structured case tracker and its permit portal (GovBuilt) rejects
non-browser clients, so the public record of what the city actually decided
lives in these PDFs. This is the only path to Duluth land-use case data.

Two things make the filenames unusable as a source of truth:
  * date formats vary wildly -- "08-17-2026", "7-6-26", "03-26-25", "8-10-26"
  * document type is inconsistent -- "PC AGENDA", "SIGNED MINS PC",
    "DuluthAgendaBinder7-13-26", "wk sess notes"

The LINK LABEL, however, is reliable: the page renders each document under an
"Agenda" / "Minutes" / "Packet" anchor even when the filename says nothing.
So: type comes from the label, date from the filename with a pattern cascade,
and anything still undated is flagged rather than guessed at.
"""
from __future__ import annotations

import hashlib
import collections
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import httpx

HERE = Path(__file__).parent
RAW = HERE / "raw"
BASE = "https://www.duluthga.net/government/agendas___minutes/"
ROOT = "https://www.duluthga.net/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

BODIES = {
    "duluth-city-council":     ("Mayor & City Council",     "mayor___council_agendas___minutes.php"),
    "duluth-planning-commission": ("Planning Commission",   "planning_commission_agendas___minutes.php"),
    "duluth-zba":              ("Zoning Board of Appeals",  "zoning_board_of_appeals_agendas___minutes.php"),
}

SKIP = ("Document Center", "PROCLAMATION", "Calendar", "SAMPLE BALLOT", "BONDLIST")

# Ordered cascade. mm-dd-yyyy first so "08-17-2026" is not read as a 2-digit year.
#
# Leading boundary is (?<!\d) rather than \b: the date often follows a letter
# directly, as in "DuluthAgendaBinder8-10-26.pdf". \b needs a word/non-word
# transition, and "r"->"8" is word->word, so \b silently failed on all 80 agenda
# binders -- the single most valuable document type in the corpus.
DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(\d{1,2})[-._](\d{1,2})[-._](\d{4})(?!\d)"), "mdy4"),
    (re.compile(r"(?<!\d)(\d{4})[-._](\d{1,2})[-._](\d{1,2})(?!\d)"), "ymd"),
    (re.compile(r"(?<!\d)(\d{1,2})[-._](\d{1,2})[-._](\d{2})(?!\d)"), "mdy2"),
    # "SIGNED MINUTES 05222023" -- mmddyyyy, no separators.
    (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)"), "mmddyyyy"),
]
# NB: one file is literally "SIGNED MINUTES 04402023" -- month 04, day 40, a typo
# in the city's own filename. It fails validation and stays flagged, which is
# correct: the real date has to come from the document body, not a guess.

TYPE_FROM_LABEL = {
    "agenda": "agenda", "agendas": "agenda",
    "minutes": "minutes", "minute": "minutes",
    "packet": "packet", "agenda packet": "packet", "binder": "packet",
    "notice": "notice", "presentation": "presentation",
}


def parse_date(s: str):
    for rx, kind in DATE_PATTERNS:
        m = rx.search(s)
        if not m:
            continue
        a, b, c = m.groups()
        try:
            if kind == "ymd":
                y, mo, d = int(a), int(b), int(c)
            else:
                mo, d, y = int(a), int(b), int(c)
                if y < 100:
                    y += 2000
            if not (1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2100):
                continue
            return date(y, mo, d).isoformat(), kind
        except ValueError:
            continue
    return None, None


def classify(label: str, href: str) -> str:
    lab = re.sub(r"\s+", " ", label or "").strip().lower()
    if lab in TYPE_FROM_LABEL:
        return TYPE_FROM_LABEL[lab]
    for k, v in TYPE_FROM_LABEL.items():
        if k in lab:
            return v
    h = href.lower()
    if "binder" in h or "packet" in h:
        return "packet"
    if "min" in h:
        return "minutes"
    if "agenda" in h:
        return "agenda"
    return "unknown"


def discover(client: httpx.Client) -> list[dict]:
    rx = re.compile(
        r"<a\s[^>]*href=[\"']([^\"']+?\.(?:pdf|docx?))(\?[^\"']*)?[\"'][^>]*>(.*?)</a>",
        re.S | re.I)
    found = []
    for slug, (name, page) in BODIES.items():
        url = BASE + page
        r = client.get(url, timeout=60)
        r.raise_for_status()
        html = r.text
        n = 0
        for m in rx.finditer(html):
            href, _q, inner = m.group(1), m.group(2), m.group(3)
            if any(s in href for s in SKIP):
                continue
            label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
            meeting_date, how = parse_date(href)
            found.append({
                "body_slug": slug,
                "body_name": name,
                "index_url": url,
                "label": label,
                "filename": href,
                "url": urljoin(ROOT, quote(href, safe="/:")),
                "doc_type": classify(label, href),
                "meeting_date": meeting_date,
                "date_parsed_as": how,
            })
            n += 1
        print(f"  {name:26s} {n:>3} documents")
        time.sleep(1.0)
    return found


def fetch_all(client: httpx.Client, docs: list[dict]) -> list[dict]:
    RAW.mkdir(exist_ok=True)
    for i, d in enumerate(docs, 1):
        key = hashlib.sha1(d["url"].encode()).hexdigest()[:16]
        dest = RAW / f"{d['body_slug']}_{key}.pdf"
        d["local_path"] = str(dest)
        if dest.exists() and dest.stat().st_size > 0:
            d["bytes"] = dest.stat().st_size
            d["fetch_status"] = "cached"
            continue
        try:
            r = client.get(d["url"], timeout=120, follow_redirects=True)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                dest.write_bytes(r.content)
                d["bytes"] = len(r.content)
                d["fetch_status"] = "ok"
                d["sha256"] = hashlib.sha256(r.content).hexdigest()
            else:
                # Not a PDF. Usually an interstitial or an error page served with
                # a 200, so record where we actually ENDED UP -- the requested URL
                # is rarely where the bytes live.
                d["fetch_status"] = f"http_{r.status_code}_{r.headers.get('content-type','?').split(';')[0]}"
                d["fetch_host"] = urlparse(str(r.url)).netloc
                d["bytes"] = 0
        except Exception as e:
            d["fetch_status"] = f"error:{type(e).__name__}"
            d["bytes"] = 0
            # Duluth serves its PDFs off duluthga.net but 302s them to Revize's
            # CDN (cms4files.revize.com). An egress allowlist naming only the
            # site's own domain lets the redirect through and then blocks the
            # file, so the host that actually failed is NOT the host we asked
            # for. Chase the Location header to name it.
            d["fetch_host"] = redirect_host(client, d["url"]) or urlparse(d["url"]).netloc
        if i % 25 == 0:
            ok = sum(1 for x in docs[:i] if x.get("fetch_status") in ("ok", "cached"))
            print(f"    {i}/{len(docs)} attempted, {ok} downloaded")
        time.sleep(0.6)          # be a polite guest
    return docs


def redirect_host(client: httpx.Client, url: str) -> str | None:
    """Where does this URL actually point? One un-followed request, so a blocked
    CDN can be named rather than inferred."""
    try:
        r = client.get(url, timeout=30, follow_redirects=False)
        loc = r.headers.get("location")
        return urlparse(loc).netloc if loc else None
    except Exception:
        return None


def main() -> int:
    headers = {"User-Agent": UA, "Accept": "text/html,application/pdf,*/*"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        print("discovering:")
        docs = discover(client)
        print(f"\ntotal documents: {len(docs)}")
        undated = [d for d in docs if not d["meeting_date"]]
        print(f"undated (flagged, not guessed): {len(undated)}")
        for d in undated[:12]:
            print(f"    {d['body_slug'][:22]:24s} {d['filename'][:62]}")

        if "--fetch" in sys.argv:
            print("\nfetching PDFs...")
            docs = fetch_all(client, docs)
            ok = sum(1 for d in docs if d["fetch_status"] in ("ok", "cached"))
            mb = sum(d.get("bytes", 0) for d in docs) / 1e6
            print(f"\n  downloaded ok: {ok}/{len(docs)}  ({mb:.1f} MB)")

            # Report the failures. Writing a tidy JSONL of 356 records that point
            # at files which were never downloaded, and exiting 0, is how the
            # whole pipeline ends up looking finished while doing nothing.
            bad = [d for d in docs if d["fetch_status"] not in ("ok", "cached")]
            if bad:
                reasons = collections.Counter(d["fetch_status"] for d in bad)
                hosts = collections.Counter(d.get("fetch_host", "?") for d in bad)
                print(f"  FAILED: {len(bad)}")
                for reason, n in reasons.most_common(6):
                    print(f"    {n:>4}  {reason}")
                print("  hosts that actually failed:")
                for host, n in hosts.most_common(6):
                    print(f"    {n:>4}  {host}")
            if ok == 0:
                sys.exit(
                    "\nNothing downloaded. The document index was read fine, so this is "
                    "not a discovery problem.\nIf the failing host above is not the site's "
                    "own domain, it is the CMS's file CDN and needs egress access too -- "
                    "Duluth\nserves from duluthga.net but redirects every PDF to "
                    "cms4files.revize.com.\nRefusing to write a document index for files "
                    "that are not on disk."
                )

    out = HERE / "duluth_meeting_docs.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
