-- Precedence between competing decision records for the same case.
--
-- land_use_case holds ONE row per case, but a case is heard repeatedly: Planning
-- Commission recommends, Council decides, the ZBA may table then rule. The loader
-- has to choose which hearing survives, and it was choosing by file order via
-- coalesce(EXCLUDED, existing).
--
-- That produced legally wrong answers. SU2025-004 was approved by the Planning
-- Commission on 2025-09-15 and DENIED by Mayor and Council on 2025-10-13; loading
-- the recommendation last recorded it as approved. Four of the corpus's five
-- denials were being overwritten this way.
--
-- Ordering by date alone is also wrong. Z2024-001 was approved by Council on
-- 2024-06-10 and the minutes say so in a motion that names the case, but a PACKET
-- record dated 2024-07-08 also carries "Motion carried" and won on recency. Packet
-- extraction takes the nearest vote within 6,000 characters of a heading, so it can
-- staple an unrelated vote to a case that merely gets a mention.
--
-- So: evidence quality outranks recency, and recency breaks ties within a class.
--   1. minutes_motion -- the case is named INSIDE the motion that was voted on
--   2. anything else  -- the case and the vote are merely near each other
-- A packet decision still wins where there is no minutes decision, which is most
-- of the corpus.
CREATE OR REPLACE FUNCTION duluth_decision_supersedes(
  new_extraction text, new_date date, new_decision text,
  old_extraction text, old_date date, old_decision text)
RETURNS boolean
LANGUAGE sql IMMUTABLE
SET search_path = public, pg_temp
AS $$
  SELECT CASE
    WHEN new_decision IS NULL THEN false          -- nothing to say
    WHEN old_decision IS NULL THEN true           -- anything beats nothing
    WHEN (new_extraction = 'minutes_motion') AND (old_extraction IS DISTINCT FROM 'minutes_motion')
      THEN true
    WHEN (old_extraction = 'minutes_motion') AND (new_extraction IS DISTINCT FROM 'minutes_motion')
      THEN false
    WHEN old_date IS NULL THEN true
    WHEN new_date IS NULL THEN false
    ELSE new_date >= old_date
  END;
$$;

COMMENT ON FUNCTION duluth_decision_supersedes IS
  'Which of two competing Duluth decision records is authoritative. Evidence
   quality first (a motion that names its case beats a vote merely near one),
   then recency.';

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
      -- every decision field moves together or not at all, so the stored votes
      -- always belong to the stored decision
      decision = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.decision ELSE land_use_case.decision END,
      decision_date = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.decision_date ELSE land_use_case.decision_date END,
      voted_for = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.voted_for ELSE land_use_case.voted_for END,
      voted_against = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.voted_against ELSE land_use_case.voted_against END,
      motion_action = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.motion_action ELSE land_use_case.motion_action END,
      moved_by = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.moved_by ELSE land_use_case.moved_by END,
      seconded_by = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.seconded_by ELSE land_use_case.seconded_by END,
      hearing_body = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.hearing_body ELSE land_use_case.hearing_body END,
      extraction_method = CASE WHEN duluth_decision_supersedes(
            EXCLUDED.extraction_method, EXCLUDED.decision_date, EXCLUDED.decision,
            land_use_case.extraction_method, land_use_case.decision_date, land_use_case.decision)
          THEN EXCLUDED.extraction_method ELSE land_use_case.extraction_method END,
      -- descriptive fields do not change by hearing: first non-null wins
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

-- Reloading after changing precedence requires clearing the decision fields first;
-- otherwise the corrected rules are layered on top of the wrong winners.
UPDATE land_use_case
   SET decision = NULL, decision_date = NULL, voted_for = NULL, voted_against = NULL,
       motion_action = NULL, moved_by = NULL, seconded_by = NULL, hearing_body = NULL,
       extraction_method = NULL
 WHERE source_system = 'duluth-agenda-mining';
