-- Loader for the 18 extracted UDC tables. Table 2-B was loaded by hand because
-- it is the one verified cell-for-cell against the rendered source page; the
-- rest carry quality='unverified' and that flag rides along into the row so a
-- consumer can tell which numbers have been eyeballed and which have not.
CREATE OR REPLACE FUNCTION load_udc_tables_from_url(p_url text, p_slug text DEFAULT 'duluth')
RETURNS TABLE (loaded int, verified int, unverified int) LANGUAGE plpgsql AS $$
DECLARE v_jid int; v_body text; v_line text; j jsonb; n int := 0;
BEGIN
  SELECT id INTO v_jid FROM jurisdiction WHERE slug = p_slug;
  IF v_jid IS NULL THEN RAISE EXCEPTION 'unknown jurisdiction %', p_slug; END IF;

  PERFORM extensions.http_set_curlopt('CURLOPT_TIMEOUT','300');
  SELECT content INTO v_body FROM extensions.http_get(p_url);

  FOR v_line IN SELECT unnest(string_to_array(v_body, E'\n')) LOOP
    CONTINUE WHEN btrim(v_line) = '';
    j := v_line::jsonb;
    INSERT INTO code_table (
      jurisdiction_id, citation, title, header, rows, markdown,
      n_cols, n_rows, page_from, page_to, source_url, last_verified)
    VALUES (
      v_jid, j->>'citation', j->>'title',
      ARRAY(SELECT jsonb_array_elements_text(coalesce(j->'header','[]'::jsonb))),
      coalesce(j->'rows','[]'::jsonb), j->>'markdown',
      (j->>'n_cols')::int, (j->>'n_rows')::int,
      (j->>'page_from')::int, (j->>'page_to')::int,
      j->>'source_url', now())
    ON CONFLICT (jurisdiction_id, citation, page_from) DO UPDATE SET
      -- never let an unverified re-extract silently overwrite the verified
      -- hand-checked Table 2-B rows
      header   = CASE WHEN code_table.quality = 'verified'
                      THEN code_table.header   ELSE EXCLUDED.header   END,
      rows     = CASE WHEN code_table.quality = 'verified'
                      THEN code_table.rows     ELSE EXCLUDED.rows     END,
      markdown = EXCLUDED.markdown,
      last_verified = now();
    n := n + 1;
  END LOOP;

  loaded := n;
  SELECT count(*)::int INTO verified   FROM code_table WHERE quality = 'verified';
  SELECT count(*)::int INTO unverified FROM code_table WHERE quality IS DISTINCT FROM 'verified';
  RETURN NEXT;
END $$;
