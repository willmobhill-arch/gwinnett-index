-- Placeholder rows for the two county-level jurisdictions. Boundaries are
-- backfilled from Census TIGERweb once its rate limit clears; cases can load now.
INSERT INTO jurisdiction (slug, name, kind, fips_county, code_citation, code_url, boundary_source, boundary_vintage)
VALUES
  ('gwinnett-county','Gwinnett County','county','135',
   'Gwinnett County Unified Development Ordinance',
   'https://library.municode.com/ga/gwinnett_county/codes/code_of_ordinances?nodeId=APXAUNDEOR',
   'US Census TIGERweb (pending)','2025'),
  ('unincorporated-gwinnett','Unincorporated Gwinnett County','unincorporated','135',
   'Gwinnett County Unified Development Ordinance',
   'https://library.municode.com/ga/gwinnett_county/codes/code_of_ordinances?nodeId=APXAUNDEOR',
   'Derived: Gwinnett County minus 17 municipalities (pending)','2025')
ON CONFLICT (slug) DO NOTHING;

CREATE TABLE IF NOT EXISTS land_use_case (
  id                 bigserial PRIMARY KEY,
  jurisdiction_id    int REFERENCES jurisdiction(id),
  case_number        text NOT NULL,
  case_type          text,
  year               int,
  pending            text,
  status             text,
  applicant_raw      text,
  applicant_id       int,
  proposed_use       text,
  existing_zone      text,
  proposed_zone      text,
  approved_zone      text,
  acres              numeric,
  comm_district      text,
  staff_rec          text,
  pc_date            date,
  pc_rec             text,
  decision_date      date,
  boc_hearing_date   date,
  decision           text,
  comments           text,
  related_cases      text,
  conditions_text    text,
  location_text      text,
  pins               text[],
  res_units          int,
  nonres_sqft        numeric,
  rooms              int,
  nonres_units       int,
  mixed_res_units    int,
  multifamily_units  int,
  townhome_units     int,
  sfd_units          int,
  gcid_number        text,
  source_url         text,
  source_system      text NOT NULL,
  source_layer       text,
  source_objectid    bigint,
  first_seen         timestamptz DEFAULT now(),
  last_verified      timestamptz DEFAULT now(),
  UNIQUE (jurisdiction_id, case_number)
);

CREATE INDEX IF NOT EXISTS luc_jurisdiction_idx ON land_use_case (jurisdiction_id);
CREATE INDEX IF NOT EXISTS luc_year_idx         ON land_use_case (year);
CREATE INDEX IF NOT EXISTS luc_type_idx         ON land_use_case (case_type);
CREATE INDEX IF NOT EXISTS luc_applicant_trgm   ON land_use_case USING GIN (applicant_raw gin_trgm_ops);
CREATE INDEX IF NOT EXISTS luc_pins_idx         ON land_use_case USING GIN (pins);
CREATE INDEX IF NOT EXISTS luc_fts_idx          ON land_use_case USING GIN (
  to_tsvector('english',
    coalesce(applicant_raw,'') || ' ' || coalesce(proposed_use,'') || ' ' ||
    coalesce(location_text,'') || ' ' || coalesce(comments,''))
);
