-- Duluth's agenda-mined cases land in the SAME land_use_case table as the
-- county's ArcGIS cases. That is the point of a unified schema: one query
-- answers "what has been filed near here" across a city with no case tracker
-- and a county with a 56-year database, and the source_system column keeps the
-- provenance honest about which is which.
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS request_text text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS voted_for text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS voted_against text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS hearing_body text;
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS extraction_method text;

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
      j->>'source_url', 'duluth-agenda-mining', j->>'doc_type',
      j->>'extraction', now())
    ON CONFLICT (jurisdiction_id, case_number) DO UPDATE SET
      -- a decision supersedes the earlier request record for the same case
      decision       = coalesce(EXCLUDED.decision,       land_use_case.decision),
      decision_date  = coalesce(EXCLUDED.decision_date,  land_use_case.decision_date),
      voted_for      = coalesce(EXCLUDED.voted_for,      land_use_case.voted_for),
      voted_against  = coalesce(EXCLUDED.voted_against,  land_use_case.voted_against),
      applicant_raw  = coalesce(land_use_case.applicant_raw, EXCLUDED.applicant_raw),
      request_text   = coalesce(land_use_case.request_text,  EXCLUDED.request_text),
      existing_zone  = coalesce(land_use_case.existing_zone, EXCLUDED.existing_zone),
      proposed_zone  = coalesce(land_use_case.proposed_zone, EXCLUDED.proposed_zone),
      location_text  = coalesce(land_use_case.location_text, EXCLUDED.location_text),
      last_verified  = now();
    n := n + 1;
  END LOOP;

  loaded := n;
  SELECT count(*)::int INTO distinct_cases
    FROM land_use_case WHERE jurisdiction_id = v_jid;
  RETURN NEXT;
END $$;
