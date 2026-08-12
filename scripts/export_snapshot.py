#!/usr/bin/env python3
"""Export the Supabase corpus to the JSON snapshot the site builds from.

The site does not query the database during its build. It reads a snapshot from
disk, which means the build is deterministic, works offline, and can be diffed:
you can see exactly what changed in a legal-reference index between two deploys.
This script is the only thing that talks to Postgres.

Run it wherever a direct connection is available (locally, or in CI):

    DATABASE_URL=postgresql://... python3 scripts/export_snapshot.py

Output lands in data/snapshot/ and is gitignored -- it is derived, and the
11,848-case corpus has no business in git history. site/fixtures/ holds a small
committed sample with identical shapes so the site still builds with no
database at all.

NOTE ON GEOMETRY: boundaries are deliberately NOT exported. The site never needs
them (the resolver runs in Postgres, behind the API), and keeping geometry out of
the export makes it structurally impossible to leak Gwinnett County GIS data that
their licence forbids redistributing. The only geometry derived here is a scalar
area in square miles, from Census TIGER polygons, which is public domain anyway.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    sys.exit("psycopg is required:  pip install 'psycopg[binary]'")

OUT = Path(__file__).resolve().parent.parent / "data" / "snapshot"

# Ordered so unincorporated leads: it is the default answer for most of the county
# and should be the first row a human or an agent sees.
JURISDICTIONS = """
SELECT j.slug, j.name, j.kind, j.state, j.fips_place, j.fips_county,
       j.code_citation, j.code_url, j.boundary_source, j.boundary_vintage, j.notes,
       round((ST_Area(j.boundary::geography) / 2589988.110336)::numeric, 1) AS sq_mi,
       (SELECT count(*) FROM land_use_case c WHERE c.jurisdiction_id = j.id) AS cases,
       (SELECT min(year)  FROM land_use_case c WHERE c.jurisdiction_id = j.id) AS first_year,
       (SELECT max(year)  FROM land_use_case c WHERE c.jurisdiction_id = j.id) AS last_year,
       (SELECT count(*) FROM code_section s WHERE s.jurisdiction_id = j.id) AS code_sections,
       (SELECT count(*) FROM code_table  t WHERE t.jurisdiction_id = j.id) AS code_tables
FROM jurisdiction j
ORDER BY CASE j.kind WHEN 'unincorporated' THEN 0 WHEN 'county' THEN 1 ELSE 2 END, j.name
"""

CASES = """
SELECT c.case_number, j.slug AS jurisdiction, c.case_type, c.year, c.status,
       c.applicant_raw, c.applicant_norm, c.existing_zone, c.proposed_zone, c.approved_zone,
       c.acres, c.res_units, c.nonres_sqft, c.proposed_use, c.location_text, c.pins,
       c.staff_rec, c.pc_date, c.pc_rec, c.decision, c.decision_date, c.hearing_body,
       c.request_text, c.voted_for, c.voted_against, c.source_url, c.source_system,
       c.extraction_method, c.last_verified
FROM land_use_case c JOIN jurisdiction j ON j.id = c.jurisdiction_id
ORDER BY j.slug, c.case_number
"""

CODE_SECTIONS = """
SELECT s.citation, s.identifier, j.slug AS jurisdiction, s.kind, s.title,
       s.article, s.article_title, s.section, s.section_title, s.level, s.body_md,
       s.page_from, s.page_to, s.adopted_date, s.amended_through, s.source_url
FROM code_section s JOIN jurisdiction j ON j.id = s.jurisdiction_id
ORDER BY j.slug, s.page_from, s.citation
"""

# Unverified tables ship their metadata but NOT their cell values. An extraction
# that has never been checked against the rendered page can put a value in the
# wrong column and still look completely plausible -- for Table 2-B that turned
# RA-200's 75 ft front setback into 20 ft. Publishing those numbers unlabelled
# would be worse than publishing nothing.
CODE_TABLES = """
SELECT t.citation, j.slug AS jurisdiction, t.title, t.header,
       CASE WHEN t.quality = 'verified' THEN t.rows ELSE '[]'::jsonb END AS rows,
       t.n_cols, t.n_rows, t.page_from, t.page_to, t.quality, t.verification_note, t.source_url
FROM code_table t JOIN jurisdiction j ON j.id = t.jurisdiction_id
ORDER BY j.slug, t.page_from, t.citation
"""

DEVELOPERS = """
SELECT display_name, norm_name, total_cases, first_year, last_year, span_years,
       name_variants, res_units, acres, nonres_sqft, cases_since_2020, approved, denied
FROM developer_activity
ORDER BY total_cases DESC, display_name
"""

STATS = """
SELECT json_build_object(
  'total_cases',   (SELECT count(*) FROM land_use_case),
  'county_cases',  (SELECT count(*) FROM land_use_case WHERE source_system = 'gwinnett-arcgis'),
  'duluth_cases',  (SELECT count(*) FROM land_use_case WHERE source_system = 'duluth-agenda-mining'),
  'first_year',    (SELECT min(year) FROM land_use_case),
  'last_year',     (SELECT max(year) FROM land_use_case),
  'with_source_url',(SELECT count(*) FROM land_use_case WHERE source_url IS NOT NULL),
  'with_pins',     (SELECT count(*) FROM land_use_case WHERE pins IS NOT NULL AND cardinality(pins) > 0),
  'res_units',     (SELECT sum(res_units) FROM land_use_case),
  'acres',         (SELECT round(sum(acres)) FROM land_use_case),
  'applicants',    (SELECT count(*) FROM applicant),
  'applicant_variants',(SELECT count(*) FROM applicant_variant),
  'merge_pending', (SELECT count(*) FROM applicant_merge_candidate WHERE decision = 'pending'),
  'code_sections', (SELECT count(*) FROM code_section),
  'code_tables',   (SELECT count(*) FROM code_table),
  'code_tables_verified',(SELECT count(*) FROM code_table WHERE quality = 'verified'),
  'meeting_docs',  (SELECT count(*) FROM meeting_document),
  'meeting_pages', (SELECT sum(pages) FROM meeting_document),
  'probes',        (SELECT count(*) FROM resolver_probe),
  'case_types',    (SELECT json_agg(t) FROM (SELECT case_type, count(*) n FROM land_use_case
                     WHERE case_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 12) t),
  'by_decade',     (SELECT json_agg(t) FROM (SELECT (year/10)*10 AS decade, count(*) n
                     FROM land_use_case WHERE year IS NOT NULL GROUP BY 1 ORDER BY 1) t),
  -- Agenda mining is not a database read. Measuring how often it produced a
  -- field that is obviously not what it claims to be is the only way anyone
  -- downstream can tell how far to trust these rows -- and the only way we
  -- notice if a parser change makes it worse.
  'duluth_extraction', (SELECT json_build_object(
      'cases',        count(*),
      'with_outcome', count(*) FILTER (WHERE decision IS NOT NULL),
      'with_zoning',  count(*) FILTER (WHERE existing_zone IS NOT NULL),
      'location_without_street_number',
                      count(*) FILTER (WHERE location_text IS NULL OR location_text !~ '[0-9]'),
      'location_is_junk',
                      count(*) FILTER (WHERE location_text ~* '^(as presented|\{|approved|the |a )'),
      'applicant_missing', count(*) FILTER (WHERE applicant_raw IS NULL),
      'applicant_overran', count(*) FILTER (WHERE length(applicant_raw) > 40),
      'request_is_boilerplate',
                      count(*) FILTER (WHERE upper(request_text) IN ('ORDINANCE','ORDINANCE OF REZONING')))
    FROM land_use_case WHERE source_system = 'duluth-agenda-mining')
) AS j
"""

# The resolver's regression fixture, re-scored on every export. If 'high' ever
# drops below 100% correct something has regressed, and shipping a build that
# quietly claims a worse resolver is exactly the failure this project cannot have.
RESOLVER = """
SELECT coalesce(r.confidence, 'unresolved') AS confidence,
       count(*) AS probes,
       count(*) FILTER (WHERE r.slug = p.expected_slug) AS correct
FROM resolver_probe p
LEFT JOIN LATERAL resolve_jurisdiction(ST_X(p.pt), ST_Y(p.pt), 150) r ON true
GROUP BY 1
"""


def default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "quantize"):  # Decimal
        return float(o)
    raise TypeError(f"cannot serialise {type(o).__name__}")


def write(name: str, payload) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, default=default, ensure_ascii=False, indent=1))
    n = len(payload) if isinstance(payload, list) else 1
    print(f"  {name:16s} {n:>7,}  {path.stat().st_size / 1024:>8,.0f} KB")
    return n


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("set DATABASE_URL to the Supabase Postgres connection string")

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731

        print("exporting to", OUT)
        write("jurisdictions", q(JURISDICTIONS))
        write("cases", q(CASES))
        write("code_sections", q(CODE_SECTIONS))
        tables = q(CODE_TABLES)
        write("code_tables", tables)
        write("developers", q(DEVELOPERS))

        stats = q(STATS)[0]["j"]
        resolver = {r["confidence"]: {"probes": r["probes"], "correct": r["correct"]}
                    for r in q(RESOLVER)}
        stats["resolver"] = resolver
        stats["generated_from"] = "supabase"
        stats["generated_at"] = datetime.now(timezone.utc).isoformat()
        write("stats", stats)

    high = resolver.get("high")
    if not high:
        sys.exit("FAIL: resolver returned no high-confidence probes — the fixture did not run")
    if high["correct"] != high["probes"]:
        sys.exit(
            f"FAIL: resolver regression — high confidence is {high['correct']}/{high['probes']}, "
            "expected 100%. Do not ship this build; something changed the boundaries or the "
            "resolver. See db/migrations/README.md."
        )
    print(f"\n  resolver: high confidence {high['correct']:,}/{high['probes']:,} — 100%, as expected")

    unverified = sum(1 for t in tables if t["quality"] != "verified")
    if unverified:
        print(f"  note: {unverified} of {len(tables)} code tables are unverified; "
              "their cell values are withheld from the snapshot by design")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
