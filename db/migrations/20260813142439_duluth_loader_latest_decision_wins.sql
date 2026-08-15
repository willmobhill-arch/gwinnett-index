-- A case is heard more than once: Planning Commission recommends, Council decides,
-- and the ZBA may table then rule. land_use_case holds ONE row per case, so the
-- loader has to choose which hearing's outcome survives -- and it was choosing by
-- file order, via coalesce(EXCLUDED, existing), which is arbitrary.
--
-- That is not a cosmetic ordering issue. SU2025-004 was approved by the Planning
-- Commission on 2025-09-15 and DENIED by Mayor and Council on 2025-10-13. Loading
-- the recommendation last records the case as approved. Of five denials in the
-- corpus, four were being overwritten by an earlier-stage approval -- a confident,
-- invisible, and legally wrong answer about what a government decided.
--
-- The decision now moves as a SET (decision, date, votes, action, mover) and only
-- when the incoming hearing is at least as recent as the one already stored. A row
-- with no date never displaces a dated one.
CREATE OR REPLACE FUNCTION load_duluth_cases_from_url(p_url text)
RETURNS TABLE (loaded int, distinct_cases int) LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
DECLARE v_jid int; v_body text; v_line text; j jsonb; n int := 0;
BEGIN
  SELECT id INTO v_jid FROM jurisdiction WHERE slug = 'duluth';
  PERFORM extensions.http_set_curlopt('CURLOPT_TIMEOUT','300');
  SELECT content INTO v_body FROM extensions.http_get(p_url);

  FOR v_line IN SELECT unnest(string_to_array(v_body, E'\n')) LOOP
    CONTINUE WHEN btrim(v_line) = '';
    j := v_line::jsonb;
    INSERT INTO land_use_case (
      jurisdiction_id, case_number, case_type, year, applicant_raw,
      existing_zone, proposed_zone, location_text, request_text,
      decision, decision_date, voted_for, voted_against, hearing_body,
      motion_action, moved_by, seconded_by,
      source_url, source_system, source_layer, extraction_method, last_verified)
    VALUES (
      v_jid, j->>'case_number', j->>'case_prefix', (j->>'case_year')::int,
      nullif(j->>'applicant',''), j->>'zone_from', j->>'zone_to',
      nullif(j->>'address',''), nullif(j->>'request',''),
      nullif(j->>'outcome',''),
      CASE WHEN j->>'record_kind' = 'decision'
           THEN nullif(j->>'meeting_date','')::date END,
      nullif(j->>'voted_for',''), nullif(j->>'voted_against',''),
      j->>'body_name',
      nullif(j->>'motion_action',''), nullif(j->>'moved_by',''), nullif(j->>'seconded_by',''),
      j->>'source_url', 'duluth-agenda-mining', j->>'doc_type',
      j->>'extraction', now())
    ON CONFLICT (jurisdiction_id, case_number) DO UPDATE SET
      -- one predicate, applied to every decision field, so the stored outcome is
      -- always internally consistent: the votes belong to the decision they were
      -- cast on, and the mover moved the motion that is recorded.
      decision = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.decision ELSE land_use_case.decision END,
      decision_date = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.decision_date ELSE land_use_case.decision_date END,
      voted_for = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.voted_for ELSE land_use_case.voted_for END,
      voted_against = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.voted_against ELSE land_use_case.voted_against END,
      motion_action = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.motion_action ELSE land_use_case.motion_action END,
      moved_by = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.moved_by ELSE land_use_case.moved_by END,
      seconded_by = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.seconded_by ELSE land_use_case.seconded_by END,
      hearing_body = CASE WHEN EXCLUDED.decision IS NOT NULL
                       AND (land_use_case.decision_date IS NULL
                            OR (EXCLUDED.decision_date IS NOT NULL
                                AND EXCLUDED.decision_date >= land_use_case.decision_date))
                      THEN EXCLUDED.hearing_body ELSE land_use_case.hearing_body END,
      -- descriptive fields: first non-null wins, they do not change by hearing
      applicant_raw  = coalesce(land_use_case.applicant_raw, EXCLUDED.applicant_raw),
      request_text   = coalesce(land_use_case.request_text,  EXCLUDED.request_text),
      existing_zone  = coalesce(land_use_case.existing_zone, EXCLUDED.existing_zone),
      proposed_zone  = coalesce(land_use_case.proposed_zone, EXCLUDED.proposed_zone),
      location_text  = coalesce(land_use_case.location_text, EXCLUDED.location_text),
      extraction_method = coalesce(EXCLUDED.extraction_method, land_use_case.extraction_method),
      last_verified  = now();
    n := n + 1;
  END LOOP;

  loaded := n;
  SELECT count(*)::int INTO distinct_cases
    FROM land_use_case WHERE jurisdiction_id = v_jid;
  RETURN NEXT;
END $$;

-- Clear the decision fields so the corrected precedence is applied from scratch
-- rather than layered on top of the wrong winners.
UPDATE land_use_case
   SET decision = NULL, decision_date = NULL, voted_for = NULL, voted_against = NULL,
       motion_action = NULL, moved_by = NULL, seconded_by = NULL, hearing_body = NULL
 WHERE source_system = 'duluth-agenda-mining';
