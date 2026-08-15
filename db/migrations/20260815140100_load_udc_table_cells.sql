-- Loader for re-extracted UDC table cells.
--
-- Separate from load_udc_tables_from_url because the payload is different: that one
-- carries whatever the old markdown extractor produced, this one carries cells taken
-- from the ruled grid, plus spanning_header, header_source and an explicit quality
-- claim per table.
--
-- A verified table is never touched. Table 2-B, 3-A, 4-A, 4-C, 7-A, 7-B and 9-B were
-- transcribed by hand against rendered pages; the extractor agrees with them on 492 of
-- 493 cells, and the one disagreement is the extractor's (a stray "(" trailing 2-B's
-- "---(9)"). An automated pass that is right 99.8% of the time must not be allowed to
-- overwrite the 100% source, so quality='verified' is a full stop here -- not just for
-- the cells, as the older loader had it, but for the flag itself. Otherwise this load
-- would silently demote seven hand-checked tables to 'unverified'.
CREATE OR REPLACE FUNCTION load_udc_table_cells_from_url(p_url text, p_slug text DEFAULT 'duluth')
RETURNS TABLE (seen int, updated int, skipped_verified int) LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
DECLARE v_jid int; v_body text; v_line text; j jsonb;
        n int := 0; upd int := 0; skip int := 0; v_quality text;
BEGIN
  SELECT id INTO v_jid FROM jurisdiction WHERE slug = p_slug;
  IF v_jid IS NULL THEN RAISE EXCEPTION 'unknown jurisdiction %', p_slug; END IF;

  PERFORM extensions.http_set_curlopt('CURLOPT_TIMEOUT','300');
  SELECT content INTO v_body FROM extensions.http_get(p_url);
  IF v_body IS NULL OR btrim(v_body) = '' THEN
    RAISE EXCEPTION 'no content from %', p_url;   -- a load of zero is a bug, not a result
  END IF;

  FOR v_line IN SELECT unnest(string_to_array(v_body, E'\n')) LOOP
    CONTINUE WHEN btrim(v_line) = '';
    j := v_line::jsonb;
    n := n + 1;

    SELECT quality INTO v_quality FROM code_table
     WHERE jurisdiction_id = v_jid
       AND citation = j->>'citation'
       AND page_from = (j->>'page_from')::int;

    IF v_quality = 'verified' THEN
      skip := skip + 1;
      CONTINUE;
    END IF;

    UPDATE code_table SET
      title             = j->>'title',
      page_to           = (j->>'page_to')::int,
      header            = ARRAY(SELECT jsonb_array_elements_text(coalesce(j->'header','[]'::jsonb))),
      spanning_header   = j->>'spanning_header',
      header_source     = j->>'header_source',
      n_cols            = (j->>'n_cols')::int,
      n_rows            = (j->>'n_rows')::int,
      rows              = coalesce(j->'rows','[]'::jsonb),
      quality           = j->>'quality',
      verification_note = j->>'verification_note',
      source_url        = j->>'source_url',
      last_verified     = now()
    WHERE jurisdiction_id = v_jid
      AND citation = j->>'citation'
      AND page_from = (j->>'page_from')::int;

    IF FOUND THEN upd := upd + 1; END IF;
  END LOOP;

  seen := n; updated := upd; skipped_verified := skip;
  RETURN NEXT;
END $$;
