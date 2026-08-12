CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS jurisdiction (
  id             serial PRIMARY KEY,
  slug           text UNIQUE NOT NULL,
  name           text NOT NULL,
  kind           text NOT NULL CHECK (kind IN ('county','municipality','unincorporated')),
  state          text NOT NULL DEFAULT 'GA',
  fips_place     text,
  fips_county    text,
  boundary       geometry(MultiPolygon, 4326),
  code_citation  text,
  code_url       text,
  boundary_source text,
  boundary_vintage text,
  notes          text,
  created_at     timestamptz DEFAULT now(),
  last_verified  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jurisdiction_boundary_gix ON jurisdiction USING GIST (boundary);
CREATE INDEX IF NOT EXISTS jurisdiction_slug_idx ON jurisdiction (slug);

-- many-to-many: Braselton spans 4 counties, Loganville 2, Auburn 2, Rest Haven 2
CREATE TABLE IF NOT EXISTS jurisdiction_county (
  jurisdiction_id int REFERENCES jurisdiction(id) ON DELETE CASCADE,
  county_fips     text NOT NULL,
  county_name     text,
  is_primary      boolean DEFAULT false,
  PRIMARY KEY (jurisdiction_id, county_fips)
);
