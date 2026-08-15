CREATE EXTENSION IF NOT EXISTS http WITH SCHEMA extensions;

-- Census GEOID -> our slug, plus the counties each municipality actually spans.
-- Cross-county cities (Braselton, Auburn, Loganville, Rest Haven) are the
-- expansion path outward into Barrow, Hall, Jackson and Walton.
CREATE TABLE IF NOT EXISTS geoid_map (
  geoid    text PRIMARY KEY,
  slug     text NOT NULL,
  name     text NOT NULL,
  counties text[] NOT NULL
);

INSERT INTO geoid_map (geoid, slug, name, counties) VALUES
  ('1304140','auburn','Auburn',                        ARRAY['13013','13135']),
  ('1307248','berkeley-lake','Berkeley Lake',          ARRAY['13135']),
  ('1310076','braselton','Braselton',                  ARRAY['13013','13135','13139','13157']),
  ('1311784','buford','Buford',                        ARRAY['13135','13139']),
  ('1321184','dacula','Dacula',                        ARRAY['13135']),
  ('1324600','duluth','Duluth',                        ARRAY['13135']),
  ('1334596','grayson','Grayson',                      ARRAY['13135']),
  ('1345488','lawrenceville','Lawrenceville',          ARRAY['13135']),
  ('1346356','lilburn','Lilburn',                      ARRAY['13135']),
  ('1347196','loganville','Loganville',                ARRAY['13135','13297']),
  ('1353706','mulberry','Mulberry',                    ARRAY['13135']),
  ('1355776','norcross','Norcross',                    ARRAY['13135']),
  ('1359735','peachtree-corners','Peachtree Corners',  ARRAY['13135']),
  ('1364792','rest-haven','Rest Haven',                ARRAY['13135','13139']),
  ('1371604','snellville','Snellville',                ARRAY['13135']),
  ('1374180','sugar-hill','Sugar Hill',                ARRAY['13135']),
  ('1374936','suwanee','Suwanee',                      ARRAY['13135'])
ON CONFLICT (geoid) DO NOTHING;
