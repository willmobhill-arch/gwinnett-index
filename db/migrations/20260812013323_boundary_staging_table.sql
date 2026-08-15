CREATE TABLE IF NOT EXISTS boundary_staging (
  slug        text PRIMARY KEY,
  name        text,
  kind        text,
  fips_place  text,
  fips_county text,
  wkt         text
);
