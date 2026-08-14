#!/usr/bin/env python3
"""Export the corpus to data/snapshot/ over HTTPS, via PostgREST.

Same output as export_snapshot.py, different transport. That script needs a direct
Postgres connection on 5432, which is unavailable anywhere egress is an HTTP
CONNECT proxy -- this container, and most locked-down CI. Without an HTTPS path
the site could only ever be built from site/fixtures, which is a ten-record sample
that says so loudly on every page but is still not the index.

Reads only. It authenticates with the publishable anon key, which is safe to hand
around precisely because RLS is on and SELECT-only: the same key gets 401 on a
write. If that ever stops being true, this script is the least of the problems.

    SUPABASE_URL=https://<ref>.supabase.co \\
    SUPABASE_ANON_KEY=sb_publishable_... \\
    python3 scripts/export_snapshot_rest.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "snapshot"
PAGE = 1000                      # PostgREST caps a single response; paginate always

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_ANON_KEY", "")
if not URL or not KEY:
    sys.exit("set SUPABASE_URL and SUPABASE_ANON_KEY")


def request(path: str, headers: dict | None = None, method: str = "GET", body=None):
    req = urllib.request.Request(f"{URL}/rest/v1/{path}", method=method)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", f"Bearer {KEY}")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            # Lowercase the header names. HTTP headers are case-insensitive, but
            # urllib hands back the wire casing ("Content-Range"), so a lookup for
            # "content-range" silently missed and every count defaulted to 0 --
            # the status page reported 0 meeting documents against 353.
            return json.loads(r.read().decode()), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        # PostgREST puts the actual reason in the BODY. urllib throws it away by
        # default, leaving a bare "HTTP Error 400: Bad Request" that says nothing
        # about which column or relationship was wrong.
        detail = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"\n  {method} {path}\n  HTTP {e.code}: {detail}\n") from None


def fetch_all(table: str, select: str, order: str) -> list[dict]:
    """Page through a table. PostgREST truncates silently at its row limit, so the
    loop runs until a short page arrives rather than trusting a single request."""
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"select": select, "order": order,
                                    "limit": PAGE, "offset": offset})
        page, _ = request(f"{table}?{q}")
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        offset += PAGE


def rpc(fn: str, args: dict | None = None):
    data, _ = request(f"rpc/{fn}", method="POST", body=args or {})
    return data


def write(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    n = len(payload) if isinstance(payload, list) else 1
    print(f"  {name:16s} {n:>7,}  {p.stat().st_size/1024:>9,.0f} KB")


def main() -> int:
    print(f"exporting from {URL} -> {OUT}")

    jur = fetch_all("jurisdiction",
        "slug,name,kind,state,fips_place,fips_county,code_citation,code_url,"
        "boundary_source,boundary_vintage,notes", "kind.asc,name.asc")

    cases = fetch_all("land_use_case",
        "case_number,case_type,year,status,applicant_raw,applicant_norm,existing_zone,"
        "proposed_zone,approved_zone,acres,res_units,nonres_sqft,proposed_use,location_text,"
        "pins,staff_rec,pc_date,pc_rec,decision,decision_date,hearing_body,request_text,"
        "motion_action,moved_by,seconded_by,"
        "voted_for,voted_against,source_url,decision_source_url,source_system,extraction_method,last_verified,"
        "jurisdiction:jurisdiction_id(slug)", "case_number.asc")
    for c in cases:
        c["jurisdiction"] = (c.get("jurisdiction") or {}).get("slug")

    secs = fetch_all("code_section",
        "citation,identifier,kind,title,article,article_title,section,section_title,level,"
        "body_md,page_from,page_to,adopted_date,amended_through,source_url,"
        "jurisdiction:jurisdiction_id(slug)", "page_from.asc,citation.asc")
    for s in secs:
        s["jurisdiction"] = (s.get("jurisdiction") or {}).get("slug")

    tabs = fetch_all("code_table",
        "citation,title,header,rows,n_cols,n_rows,page_from,page_to,quality,"
        "verification_note,source_url,jurisdiction:jurisdiction_id(slug)",
        "page_from.asc,citation.asc")
    for t in tabs:
        t["jurisdiction"] = (t.get("jurisdiction") or {}).get("slug")
        # Unverified cell values never leave the database. An extraction nobody has
        # compared against the rendered page can put a number in the wrong column
        # and still look plausible -- for Table 2-B that turned a 75 ft setback
        # into 20 ft. Metadata ships; the numbers do not.
        if t.get("quality") != "verified":
            t["rows"] = []

    devs = fetch_all("developer_activity",
        "display_name,norm_name,total_cases,first_year,last_year,span_years,name_variants,"
        "res_units,acres,nonres_sqft,cases_since_2020,approved,denied",
        "total_cases.desc,display_name.asc")

    # counts per jurisdiction, computed here rather than in SQL
    from collections import Counter
    ccount = Counter(c["jurisdiction"] for c in cases if c.get("jurisdiction"))
    scount = Counter(s["jurisdiction"] for s in secs if s.get("jurisdiction"))
    tcount = Counter(t["jurisdiction"] for t in tabs if t.get("jurisdiction"))
    years: dict[str, list[int]] = {}
    for c in cases:
        if c.get("year") and c.get("jurisdiction"):
            years.setdefault(c["jurisdiction"], []).append(c["year"])
    for j in jur:
        s = j["slug"]
        j["cases"] = ccount.get(s, 0)
        j["code_sections"] = scount.get(s, 0)
        j["code_tables"] = tcount.get(s, 0)
        j["first_year"] = min(years[s]) if years.get(s) else None
        j["last_year"] = max(years[s]) if years.get(s) else None
        # sq_mi comes from PostGIS and is not exposed over REST; the psycopg
        # exporter fills it. Preserve whatever the committed fixture knows rather
        # than emitting null and silently blanking every jurisdiction page.
        j.setdefault("sq_mi", None)

    fx = Path(__file__).resolve().parent.parent / "site" / "fixtures" / "jurisdictions.json"
    if fx.exists():
        known = {r["slug"]: r.get("sq_mi") for r in json.loads(fx.read_text())}
        for j in jur:
            if j.get("sq_mi") is None:
                j["sq_mi"] = known.get(j["slug"])

    write("jurisdictions", jur)
    write("cases", cases)
    write("code_sections", secs)
    write("code_tables", tabs)
    write("developers", devs)

    # ---- stats + the regression gate ------------------------------------
    dul = [c for c in cases if c["source_system"] == "duluth-agenda-mining"]
    def n(pred, rows=cases): return sum(1 for r in rows if pred(r))
    ys = [c["year"] for c in cases if c.get("year")]
    stats = {
        "total_cases": len(cases),
        "county_cases": n(lambda c: c["source_system"] == "gwinnett-arcgis"),
        "duluth_cases": len(dul),
        "first_year": min(ys), "last_year": max(ys),
        "with_source_url": n(lambda c: c.get("source_url")),
        "with_pins": n(lambda c: c.get("pins")),
        "res_units": sum(c.get("res_units") or 0 for c in cases),
        "acres": round(sum(float(c.get("acres") or 0) for c in cases)),
        "code_sections": len(secs), "code_tables": len(tabs),
        "code_tables_verified": sum(1 for t in tabs if t.get("quality") == "verified"),
        "case_types": [{"case_type": k, "n": v} for k, v in
                       Counter(c["case_type"] for c in cases if c.get("case_type")).most_common(12)],
        "by_decade": [{"decade": k, "n": v} for k, v in
                      sorted(Counter((y // 10) * 10 for y in ys).items())],
        "duluth_extraction": {
            "cases": len(dul),
            "with_outcome": n(lambda c: c.get("decision"), dul),
            "with_zoning": n(lambda c: c.get("existing_zone"), dul),
            "location_without_street_number":
                n(lambda c: not c.get("location_text") or not any(ch.isdigit() for ch in c["location_text"]), dul),
            "location_is_junk":
                n(lambda c: (c.get("location_text") or "").lower().startswith(("as presented", "{", "approved")), dul),
            "applicant_missing": n(lambda c: not c.get("applicant_raw"), dul),
            "applicant_overran": n(lambda c: len(c.get("applicant_raw") or "") > 40, dul),
            "request_is_boilerplate":
                n(lambda c: (c.get("request_text") or "").upper() in ("ORDINANCE", "ORDINANCE OF REZONING"), dul),
        },
        "generated_from": "supabase (postgrest)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    for extra in ("applicant", "applicant_variant", "applicant_merge_candidate",
                  "meeting_document", "resolver_probe"):
        # select=* rather than select=id: applicant_variant has a composite primary
        # key and no id column at all, so assuming one 400s the whole export.
        _, h = request(f"{extra}?select=*&limit=1", {"Prefer": "count=exact", "Range": "0-0"})
        if "content-range" not in h:
            sys.exit(f"FAIL: no content-range for {extra}; counts would silently be 0")
        stats[{"applicant": "applicants", "applicant_variant": "applicant_variants",
               "applicant_merge_candidate": "merge_pending",
               "meeting_document": "meeting_docs", "resolver_probe": "probes"}[extra]] = \
            int(h.get("content-range", "0-0/0").split("/")[-1])

    # The regression gate. Scoring the fixture live takes 36 seconds and PostgREST
    # cancels it, so the score is read from resolver_score_cache -- and a cache is
    # only a gate if staleness is fatal. Refuse if it predates the most recent
    # boundary change, because that is exactly the edit that would invalidate it.
    # Total pages across the meeting corpus. Not derivable from a count header, so
    # it needs its own (small) fetch -- 353 integers.
    stats["meeting_pages"] = sum(
        (r.get("pages") or 0) for r in fetch_all("meeting_document", "pages", "id.asc"))

    score = fetch_all("resolver_score_cache",
                      "confidence,probes,correct,scored_at,boundary_as_of", "confidence.asc")
    if not score:
        sys.exit("FAIL: resolver_score_cache is empty. Run: SELECT refresh_resolver_score();")
    stats["resolver"] = {r["confidence"]: {"probes": r["probes"], "correct": r["correct"]}
                         for r in score}
    stats["resolver_scored_at"] = score[0]["scored_at"]
    write("stats", stats)

    scored_at = score[0]["scored_at"]
    boundary_as_of = score[0].get("boundary_as_of")
    if boundary_as_of and boundary_as_of > scored_at:
        sys.exit(f"FAIL: resolver score is stale -- boundaries changed at {boundary_as_of}, "
                 f"scored at {scored_at}. Run: SELECT refresh_resolver_score();")

    high = stats["resolver"].get("high")
    if not high:
        sys.exit("FAIL: resolver returned no high-confidence probes -- the fixture did not run")
    if high["correct"] != high["probes"]:
        sys.exit(f"FAIL: resolver regression -- high confidence is "
                 f"{high['correct']}/{high['probes']}, expected 100%. Do not ship this build.")
    print(f"\n  resolver: high confidence {high['correct']:,}/{high['probes']:,} -- 100%, "
          f"scored {scored_at[:19]}")

    unver = sum(1 for t in tabs if t.get("quality") != "verified")
    if unver:
        print(f"  note: {unver} of {len(tabs)} code tables unverified; cell values withheld")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
