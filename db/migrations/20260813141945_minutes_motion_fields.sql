-- Minutes decisions carry three things the agenda-derived records never could:
-- who moved, who seconded, and WHAT THE MOTION ASKED FOR.
--
-- That last one is not decoration. "Motion carried" on its own is actively
-- misleading: SU2025-001 carried a motion to POSTPONE, after a motion to approve
-- and a motion to deny had both died for lack of a second. Anyone reading
-- decision='Motion carried' against a special use permit will conclude it was
-- approved. Of the 90 extracted decisions, 76 carried an approval, 5 carried a
-- DENIAL, 3 a postponement, 2 a continuance, 2 a tabling, and one was a motion to
-- approve that FAILED -- a denial by another route. Thirteen of those ninety mean
-- something other than "approved", and nothing in the decision text says so.
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS motion_action text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS moved_by text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS seconded_by text;

COMMENT ON COLUMN land_use_case.motion_action IS
  'What the carried motion asked for: approve | deny | postpone | table | continue
   | defer | withdraw | remand | adopt | accept | reject. Read together with
   decision -- "Motion carried" + motion_action=''postpone'' is NOT an approval.';
COMMENT ON COLUMN land_use_case.moved_by IS
  'Council member who made the motion, as recorded in the minutes.';
COMMENT ON COLUMN land_use_case.seconded_by IS
  'Council member who seconded. Absent where the motion died for lack of a second.';

-- Loader updated to carry the three new fields; body otherwise unchanged.
CREATE OR REPLACE FUNCTION load_duluth_cases_from_url(p_url text)
RETURNS TABLE (loaded int, distinct_cases int) LANGUAGE plpgsql AS $$
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
      -- a decision supersedes the earlier request record for the same case
      decision       = coalesce(EXCLUDED.decision,       land_use_case.decision),
      decision_date  = coalesce(EXCLUDED.decision_date,  land_use_case.decision_date),
      voted_for      = coalesce(EXCLUDED.voted_for,      land_use_case.voted_for),
      voted_against  = coalesce(EXCLUDED.voted_against,  land_use_case.voted_against),
      motion_action  = coalesce(EXCLUDED.motion_action,  land_use_case.motion_action),
      moved_by       = coalesce(EXCLUDED.moved_by,       land_use_case.moved_by),
      seconded_by    = coalesce(EXCLUDED.seconded_by,    land_use_case.seconded_by),
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
