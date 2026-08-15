-- Paginated ingest of Gwinnett County zoning cases straight from the county's
-- public ArcGIS REST service. Runs entirely inside Postgres via the http
-- extension -- no external worker, no credentials, nothing proxied through a
-- client. Layer 2 = Historical Zoning Cases (11,728), layer 1 = Current, 15 = Variances.
--
-- IMPORTANT: every record in these layers is a Board of Commissioners decision,
-- i.e. UNINCORPORATED county only. City cases are NOT here -- addresses reading
-- "DULUTH HIGHWAY" are street names in unincorporated territory, not the City
-- of Duluth. Attributing these to a municipality would be wrong.

CREATE OR REPLACE FUNCTION epoch_ms_to_date(v jsonb)
RETURNS date LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN v IS NULL OR jsonb_typeof(v) <> 'number' THEN NULL
    WHEN (v::text)::bigint = 0 THEN NULL
    ELSE (to_timestamp(((v::text)::bigint) / 1000.0) AT TIME ZONE 'UTC')::date
  END;
$$;

CREATE OR REPLACE FUNCTION ingest_gwinnett_cases(p_layer int, p_source_layer text, p_page int DEFAULT 1000)
RETURNS TABLE (fetched int, upserted int)
LANGUAGE plpgsql AS $$
DECLARE
  v_jid       int;
  v_offset    int := 0;
  v_total     int := 0;
  v_up        int := 0;
  v_batch     int;
  v_url       text;
  v_body      jsonb;
  v_base      text := 'https://gis3.gwinnettcounty.com/mapvis/rest/services/GISDataBrowser/GC_Planning/MapServer/';
BEGIN
  SELECT id INTO v_jid FROM jurisdiction WHERE slug = 'unincorporated-gwinnett';
  PERFORM extensions.http_set_curlopt('CURLOPT_TIMEOUT','180');

  LOOP
    v_url := v_base || p_layer || '/query?where=1%3D1&outFields=*&returnGeometry=false'
             || '&orderByFields=OBJECTID&resultOffset=' || v_offset
             || '&resultRecordCount=' || p_page || '&f=json';

    SELECT content::jsonb INTO v_body FROM extensions.http_get(v_url);
    SELECT count(*) INTO v_batch FROM jsonb_array_elements(v_body->'features');
    EXIT WHEN v_batch = 0;

    WITH rows AS (
      SELECT (jsonb_array_elements(v_body->'features'))->'attributes' AS a
    )
    INSERT INTO land_use_case (
      jurisdiction_id, case_number, case_type, year, pending, status, applicant_raw,
      proposed_use, existing_zone, proposed_zone, approved_zone, acres, comm_district,
      staff_rec, pc_date, pc_rec, decision_date, boc_hearing_date, decision, comments,
      related_cases, location_text, pins, res_units, nonres_sqft, rooms, nonres_units,
      mixed_res_units, multifamily_units, townhome_units, sfd_units, gcid_number,
      source_url, source_system, source_layer, source_objectid, last_verified)
    SELECT
      v_jid,
      a->>'CASENUM',
      substring(upper(a->>'CASENUM') from '^[A-Z]+'),
      nullif(a->>'YEAR','')::numeric::int,
      a->>'PENDING',
      a->>'STATUS',
      nullif(btrim(a->>'APPLICANT'),''),
      nullif(btrim(a->>'PROPOSED_USE'),''),
      nullif(btrim(a->>'EXISTING_ZONE'),''),
      nullif(btrim(a->>'PROPOSED_ZONE'),''),
      nullif(btrim(a->>'APPROVED_ZONE'),''),
      nullif(a->>'ACRES','')::numeric,
      a->>'COMM_DIST',
      nullif(btrim(a->>'STAFF_REC'),''),
      epoch_ms_to_date(a->'PC_DATE'),
      nullif(btrim(a->>'PC_REC'),''),
      epoch_ms_to_date(a->'BOC_DATE'),
      epoch_ms_to_date(a->'BOC_HEARING_DATE'),
      nullif(btrim(a->>'BOC_DEC'),''),
      nullif(btrim(a->>'COMMENTS'),''),
      nullif(btrim(a->>'RELATED_CASES'),''),
      nullif(btrim(concat_ws(', ',
        nullif(btrim(a->>'LOCATION_1'),''),
        nullif(btrim(a->>'LOCATION_2'),''),
        nullif(btrim(a->>'LOCATION_3'),''))),''),
      (SELECT array_agg(p) FROM unnest(ARRAY[
         nullif(btrim(a->>'PIN'),''),   nullif(btrim(a->>'PIN_2'),''),
         nullif(btrim(a->>'PIN_3'),''), nullif(btrim(a->>'PIN_4'),''),
         nullif(btrim(a->>'PIN_5'),'')]) p WHERE p IS NOT NULL),
      nullif(a->>'RES_UNITS','')::numeric::int,
      nullif(a->>'NONRES_SQFEET','')::numeric,
      nullif(a->>'ROOMS','')::numeric::int,
      nullif(a->>'NONRES_UNITS','')::numeric::int,
      nullif(a->>'MIXRESUNIT','')::numeric::int,
      nullif(a->>'MULFAMUNIT','')::numeric::int,
      nullif(a->>'ATHOMEUNIT','')::numeric::int,
      nullif(a->>'SFAMDEUNIT','')::numeric::int,
      nullif(btrim(a->>'GCIDNUM'),''),
      nullif(btrim(a->>'PDF_APPLICATION'),''),
      'gwinnett-arcgis',
      p_source_layer,
      nullif(a->>'OBJECTID','')::numeric::bigint,
      now()
    FROM rows
    WHERE a->>'CASENUM' IS NOT NULL AND btrim(a->>'CASENUM') <> ''
    ON CONFLICT (jurisdiction_id, case_number) DO UPDATE SET
      status = EXCLUDED.status, pending = EXCLUDED.pending,
      approved_zone = EXCLUDED.approved_zone, decision = EXCLUDED.decision,
      decision_date = EXCLUDED.decision_date, pc_rec = EXCLUDED.pc_rec,
      pc_date = EXCLUDED.pc_date, staff_rec = EXCLUDED.staff_rec,
      boc_hearing_date = EXCLUDED.boc_hearing_date,
      source_url = EXCLUDED.source_url, last_verified = now();

    GET DIAGNOSTICS v_up = ROW_COUNT;
    v_total := v_total + v_batch;
    v_offset := v_offset + p_page;
    EXIT WHEN v_batch < p_page;
    EXIT WHEN v_offset > 40000;
  END LOOP;

  fetched := v_total;
  SELECT count(*)::int INTO upserted FROM land_use_case WHERE source_layer = p_source_layer;
  RETURN NEXT;
END $$;
