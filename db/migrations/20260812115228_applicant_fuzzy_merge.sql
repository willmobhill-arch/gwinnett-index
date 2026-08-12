CREATE EXTENSION IF NOT EXISTS fuzzystrmatch WITH SCHEMA extensions;

-- Trigram similarity alone is NOT safe here. "CKK DEVELOPMENT SERVICES" and
-- "SCI DEVELOPMENT SERVICES" score 0.75 similar because they share a common
-- industry phrase, but they are unrelated companies. Merging them would
-- silently corrupt the leaderboard and there would be no way to notice.
--
-- So: auto-merge ONLY tight edit-distance typos (Levenshtein <= 2 on names of
-- reasonable length). Everything else goes to a review queue. Being wrong here
-- is worse than being incomplete -- an unmerged entity is visibly split, a
-- wrongly merged one looks authoritative and is invisible.

CREATE TABLE IF NOT EXISTS applicant_merge_candidate (
  keep_id    int REFERENCES applicant(id) ON DELETE CASCADE,
  merge_id   int REFERENCES applicant(id) ON DELETE CASCADE,
  keep_name  text, merge_name text,
  similarity numeric, edit_distance int,
  auto       boolean DEFAULT false,
  decision   text DEFAULT 'pending',   -- pending | merged | rejected
  PRIMARY KEY (keep_id, merge_id)
);

CREATE OR REPLACE FUNCTION build_merge_candidates(min_sim real DEFAULT 0.70)
RETURNS int LANGUAGE plpgsql AS $$
DECLARE n int;
BEGIN
  EXECUTE format('SET pg_trgm.similarity_threshold = %s', min_sim);
  INSERT INTO applicant_merge_candidate
    (keep_id, merge_id, keep_name, merge_name, similarity, edit_distance, auto)
  SELECT
    CASE WHEN a.case_count >= b.case_count THEN a.id   ELSE b.id   END,
    CASE WHEN a.case_count >= b.case_count THEN b.id   ELSE a.id   END,
    CASE WHEN a.case_count >= b.case_count THEN a.norm_name ELSE b.norm_name END,
    CASE WHEN a.case_count >= b.case_count THEN b.norm_name ELSE a.norm_name END,
    round(similarity(a.norm_name, b.norm_name)::numeric, 3),
    extensions.levenshtein(a.norm_name, b.norm_name),
    (extensions.levenshtein(a.norm_name, b.norm_name) <= 2
     AND least(length(a.norm_name), length(b.norm_name)) >= 10)
  FROM applicant a
  JOIN applicant b ON a.id < b.id AND a.norm_name % b.norm_name
  WHERE a.kind = b.kind AND a.kind <> 'unknown'
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- Apply only rows explicitly marked auto or approved.
CREATE OR REPLACE FUNCTION apply_applicant_merges()
RETURNS int LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN
    SELECT keep_id, merge_id FROM applicant_merge_candidate
    WHERE decision = 'pending' AND auto
    ORDER BY keep_id
  LOOP
    CONTINUE WHEN r.keep_id = r.merge_id;
    UPDATE land_use_case SET applicant_id = r.keep_id WHERE applicant_id = r.merge_id;
    UPDATE applicant_variant SET applicant_id = r.keep_id WHERE applicant_id = r.merge_id;
    UPDATE applicant_merge_candidate SET decision = 'merged'
      WHERE keep_id = r.keep_id AND merge_id = r.merge_id;
    DELETE FROM applicant WHERE id = r.merge_id;
    n := n + 1;
  END LOOP;

  UPDATE applicant a SET
    case_count    = s.n, first_year = s.mn, last_year = s.mx,
    variant_count = s.v
  FROM (SELECT applicant_id, count(*) n, min(year) mn, max(year) mx,
               count(DISTINCT applicant_raw) v
        FROM land_use_case WHERE applicant_id IS NOT NULL GROUP BY 1) s
  WHERE a.id = s.applicant_id;

  RETURN n;
END $$;
