CREATE TABLE IF NOT EXISTS applicant (
  id            serial PRIMARY KEY,
  norm_name     text UNIQUE NOT NULL,
  display_name  text NOT NULL,
  kind          text NOT NULL,
  variant_count int,
  case_count    int,
  first_year    int,
  last_year     int,
  reviewed      boolean DEFAULT false,
  notes         text,
  created_at    timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS applicant_norm_trgm ON applicant USING GIN (norm_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS applicant_kind_idx  ON applicant (kind);

-- Keep every raw spelling we ever saw, so a resolved entity can always be traced
-- back to the exact strings the county published. Provenance is not optional.
CREATE TABLE IF NOT EXISTS applicant_variant (
  applicant_id int REFERENCES applicant(id) ON DELETE CASCADE,
  raw_name     text NOT NULL,
  cases        int,
  PRIMARY KEY (applicant_id, raw_name)
);

ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS agent_raw text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS applicant_kind text;
