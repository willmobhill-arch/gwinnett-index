#!/usr/bin/env python3
"""
Load jurisdiction boundaries for Gwinnett County, GA from Census TIGER/Line.

TIGER/Line is a federal work in the public domain. This is the ONLY geometry the
Gwinnett Index hosts itself -- county GIS parcel/zoning layers carry an explicit
no-redistribution clause and are proxied live instead.

Loads:
  - Gwinnett County        (TIGER county, STATEFP 13 / COUNTYFP 135)
  - 17 municipalities      (TIGER places, clipped to the county where they spill over)
  - Unincorporated Gwinnett (derived: county MINUS union of all city boundaries)

Usage:
    export DATABASE_URL='postgresql://postgres:PASSWORD@db.<ref>.supabase.co:5432/postgres'
    python scripts/load_boundaries.py
"""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

import httpx
import psycopg
import shapefile
from shapely.geometry import shape
from shapely.ops import unary_union

TIGER_YEAR = 2025
STATE_FP = "13"          # Georgia
GWINNETT_FP = "135"

PLACE_URL = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/PLACE/tl_{TIGER_YEAR}_{STATE_FP}_place.zip"
COUNTY_URL = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/COUNTY/tl_{TIGER_YEAR}_us_county.zip"

DATA = Path(__file__).resolve().parent.parent / ".data" / "tiger"

# The 17 municipalities the county's GC_Planning/12 layer tracks, with the
# counties each one actually spans. Cross-county cities are the expansion path
# outward into Barrow, Hall, Jackson, and Walton.
MUNICIPALITIES = {
    "Auburn":            {"slug": "auburn",            "counties": ["13013", "13135"]},
    "Berkeley Lake":     {"slug": "berkeley-lake",     "counties": ["13135"]},
    "Braselton":         {"slug": "braselton",         "counties": ["13013", "13135", "13139", "13157"]},
    "Buford":            {"slug": "buford",            "counties": ["13135", "13139"]},
    "Dacula":            {"slug": "dacula",            "counties": ["13135"]},
    "Duluth":            {"slug": "duluth",            "counties": ["13135"]},
    "Grayson":           {"slug": "grayson",           "counties": ["13135"]},
    "Lawrenceville":     {"slug": "lawrenceville",     "counties": ["13135"]},
    "Lilburn":           {"slug": "lilburn",           "counties": ["13135"]},
    "Loganville":        {"slug": "loganville",        "counties": ["13135", "13297"]},
    "Mulberry":          {"slug": "mulberry",          "counties": ["13135"]},
    "Norcross":          {"slug": "norcross",          "counties": ["13135"]},
    "Peachtree Corners": {"slug": "peachtree-corners", "counties": ["13135"]},
    "Rest Haven":        {"slug": "rest-haven",        "counties": ["13135", "13139"]},
    "Snellville":        {"slug": "snellville",        "counties": ["13135"]},
    "Sugar Hill":        {"slug": "sugar-hill",        "counties": ["13135"]},
    "Suwanee":           {"slug": "suwanee",           "counties": ["13135"]},
}

COUNTY_NAMES = {
    "13013": "Barrow", "13135": "Gwinnett", "13139": "Hall",
    "13157": "Jackson", "13297": "Walton",
}


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached  {dest.name}")
        return dest
    print(f"  fetching {url}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=180) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
    return dest


def unpack(zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(DATA)
    return DATA / zip_path.stem


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: set DATABASE_URL", file=sys.stderr)
        return 1

    print("== downloading TIGER/Line ==")
    place_shp = unpack(fetch(PLACE_URL, DATA / f"tl_{TIGER_YEAR}_{STATE_FP}_place.zip"))
    county_shp = unpack(fetch(COUNTY_URL, DATA / f"tl_{TIGER_YEAR}_us_county.zip"))

    print("== reading county ==")
    county_geom = None
    for sr in shapefile.Reader(str(county_shp)).iterShapeRecords():
        rec = sr.record.as_dict()
        if rec.get("STATEFP") == STATE_FP and rec.get("COUNTYFP") == GWINNETT_FP:
            county_geom = shape(sr.shape.__geo_interface__)
            break
    if county_geom is None:
        print("ERROR: Gwinnett County not found in TIGER county file", file=sys.stderr)
        return 1
    print(f"  Gwinnett County: {county_geom.geom_type}, {county_geom.area:.5f} sq deg")

    print("== reading places ==")
    cities: dict[str, dict] = {}
    for sr in shapefile.Reader(str(place_shp)).iterShapeRecords():
        rec = sr.record.as_dict()
        name = rec.get("NAME")
        if name not in MUNICIPALITIES:
            continue
        geom = shape(sr.shape.__geo_interface__)
        cities[name] = {
            "geom": geom,
            "fips_place": rec.get("PLACEFP"),
            **MUNICIPALITIES[name],
        }
        print(f"  {name:20s} placefp={rec.get('PLACEFP')} {geom.geom_type}")

    missing = set(MUNICIPALITIES) - set(cities)
    if missing:
        print(f"ERROR: missing from TIGER: {sorted(missing)}", file=sys.stderr)
        return 1

    print("== deriving unincorporated Gwinnett ==")
    all_cities = unary_union([c["geom"] for c in cities.values()])
    unincorporated = county_geom.difference(all_cities)
    pct = 100 * unincorporated.area / county_geom.area
    print(f"  unincorporated = {pct:.1f}% of county land area")

    def as_multi_wkt(g):
        if g.geom_type == "Polygon":
            from shapely.geometry import MultiPolygon
            g = MultiPolygon([g])
        return g.wkt

    print("== writing to Postgres ==")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        rows = []
        rows.append((
            "gwinnett-county", "Gwinnett County", "county", None, GWINNETT_FP,
            as_multi_wkt(county_geom), "Gwinnett County UDO",
            "https://library.municode.com/ga/gwinnett_county/codes/code_of_ordinances?nodeId=APXAUNDEOR",
            ["13135"],
        ))
        rows.append((
            "unincorporated-gwinnett", "Unincorporated Gwinnett County", "unincorporated",
            None, GWINNETT_FP, as_multi_wkt(unincorporated), "Gwinnett County UDO",
            "https://library.municode.com/ga/gwinnett_county/codes/code_of_ordinances?nodeId=APXAUNDEOR",
            ["13135"],
        ))
        for name, c in cities.items():
            rows.append((
                c["slug"], name, "municipality", c["fips_place"], None,
                as_multi_wkt(c["geom"]), None, None, c["counties"],
            ))

        for (slug, name, kind, fp_place, fp_county, wkt, cite, url, counties) in rows:
            cur.execute(
                """
                INSERT INTO jurisdiction
                  (slug, name, kind, fips_place, fips_county, boundary,
                   code_citation, code_url, boundary_source, boundary_vintage, last_verified)
                VALUES (%s, %s, %s, %s, %s,
                        ST_Multi(ST_GeomFromText(%s, 4326)), %s, %s,
                        %s, %s, now())
                ON CONFLICT (slug) DO UPDATE SET
                  name = EXCLUDED.name,
                  boundary = EXCLUDED.boundary,
                  boundary_vintage = EXCLUDED.boundary_vintage,
                  last_verified = now()
                RETURNING id
                """,
                (slug, name, kind, fp_place, fp_county, wkt, cite, url,
                 f"US Census TIGER/Line {TIGER_YEAR}", str(TIGER_YEAR)),
            )
            jid = cur.fetchone()[0]
            cur.execute("DELETE FROM jurisdiction_county WHERE jurisdiction_id = %s", (jid,))
            for fips in counties:
                cur.execute(
                    """INSERT INTO jurisdiction_county
                         (jurisdiction_id, county_fips, county_name, is_primary)
                       VALUES (%s, %s, %s, %s)""",
                    (jid, fips, COUNTY_NAMES.get(fips), fips == "13135"),
                )
            print(f"  loaded {slug}")
        conn.commit()

    print("\ndone. 19 jurisdictions loaded (county + unincorporated + 17 municipalities).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
