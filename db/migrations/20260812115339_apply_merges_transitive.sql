-- Merges chain: A->B can be queued while B has already been merged into C.
-- Resolve each target to its current root before applying, and skip candidates
-- whose source no longer exists.
CREATE OR REPLACE FUNCTION apply_applicant_merges()
RETURNS int LANGUAGE plpgsql AS $$
DECLARE r record; n int := 0; v_keep int; v_guard int;
BEGIN
  FOR r IN
    SELECT keep_id, merge_id FROM applicant_merge_candidate
    WHERE decision = 'pending' AND auto ORDER BY keep_id
  LOOP
    -- source already gone (merged earlier)?
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM applicant WHERE id = r.merge_id);

    -- walk the target to its surviving root
    v_keep := r.keep_id; v_guard := 0;
    WHILE NOT EXISTS (SELECT 1 FROM applicant WHERE id = v_keep) AND v_guard < 20 LOOP
      SELECT keep_id INTO v_keep FROM applicant_merge_candidate
       WHERE merge_id = v_keep AND decision = 'merged' LIMIT 1;
      EXIT WHEN v_keep IS NULL;
      v_guard := v_guard + 1;
    END LOOP;
    CONTINUE WHEN v_keep IS NULL OR v_keep = r.merge_id;
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM applicant WHERE id = v_keep);

    UPDATE land_use_case    SET applicant_id = v_keep WHERE applicant_id = r.merge_id;
    UPDATE applicant_variant SET applicant_id = v_keep WHERE applicant_id = r.merge_id;
    DELETE FROM applicant_variant av
      WHERE av.applicant_id = v_keep
        AND EXISTS (SELECT 1 FROM applicant_variant b
                    WHERE b.applicant_id = v_keep AND b.raw_name = av.raw_name
                    AND b.ctid <> av.ctid);
    UPDATE applicant_merge_candidate SET decision = 'merged'
      WHERE keep_id = r.keep_id AND merge_id = r.merge_id;
    DELETE FROM applicant WHERE id = r.merge_id;
    n := n + 1;
  END LOOP;

  UPDATE applicant a SET case_count = s.n, first_year = s.mn,
                         last_year = s.mx, variant_count = s.v
  FROM (SELECT applicant_id, count(*) n, min(year) mn, max(year) mx,
               count(DISTINCT applicant_raw) v
        FROM land_use_case WHERE applicant_id IS NOT NULL GROUP BY 1) s
  WHERE a.id = s.applicant_id;
  RETURN n;
END $$;
