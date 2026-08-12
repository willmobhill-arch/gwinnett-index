-- Resolve a point to its GOVERNING jurisdiction.
-- Municipality wins over county: a point inside Duluth city limits is governed by
-- Duluth, not by Gwinnett County, even though it sits within the county boundary.
CREATE OR REPLACE FUNCTION resolve_jurisdiction(lon double precision, lat double precision)
RETURNS TABLE (
  slug text,
  name text,
  kind text,
  code_citation text,
  code_url text,
  boundary_source text
)
LANGUAGE sql
STABLE
AS $$
  SELECT j.slug, j.name, j.kind, j.code_citation, j.code_url, j.boundary_source
  FROM jurisdiction j
  WHERE j.kind <> 'county'
    AND ST_Contains(j.boundary, ST_SetSRID(ST_Point(lon, lat), 4326))
  ORDER BY (j.kind = 'municipality') DESC
  LIMIT 1;
$$;

COMMENT ON FUNCTION resolve_jurisdiction IS
  'Point -> governing jurisdiction. Excludes the county container row so that
   unincorporated territory resolves to the derived unincorporated polygon and
   incorporated territory resolves to its city. Never returns both.';
