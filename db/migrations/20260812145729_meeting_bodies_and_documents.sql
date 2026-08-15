CREATE TABLE IF NOT EXISTS meeting_body (
  id              serial PRIMARY KEY,
  jurisdiction_id int REFERENCES jurisdiction(id),
  slug            text UNIQUE NOT NULL,
  name            text NOT NULL,
  index_url       text,
  vendor          text,
  notes           text
);

CREATE TABLE IF NOT EXISTS meeting_document (
  id                bigserial PRIMARY KEY,
  body_id           int REFERENCES meeting_body(id),
  meeting_date      date,
  doc_type          text,          -- agenda | minutes | packet | notice | unknown
  label             text,          -- the anchor text on the index page
  filename          text,
  url               text NOT NULL,
  sha256            text,
  bytes             bigint,
  pages             int,
  -- Provenance of the TEXT itself. 'ocr' means the words are a reconstruction of
  -- a scanned image, not the publisher's own text layer, and must never be
  -- presented as an exact quotation of the record.
  text_source       text CHECK (text_source IN ('embedded','ocr','none')),
  text_quality      text,          -- text_ok | scanned_no_text | partially_scanned
  text_chars        int,
  scanned_pages     int,
  ocr_truncated     boolean DEFAULT false,
  body_text         text,
  date_parsed_as    text,          -- which filename pattern produced the date
  date_from_body    boolean DEFAULT false,
  case_refs         text[],
  first_seen        timestamptz DEFAULT now(),
  last_verified     timestamptz DEFAULT now(),
  UNIQUE (url)
);

CREATE INDEX IF NOT EXISTS md_body_idx  ON meeting_document (body_id);
CREATE INDEX IF NOT EXISTS md_date_idx  ON meeting_document (meeting_date DESC);
CREATE INDEX IF NOT EXISTS md_type_idx  ON meeting_document (doc_type);
CREATE INDEX IF NOT EXISTS md_cases_idx ON meeting_document USING GIN (case_refs);
CREATE INDEX IF NOT EXISTS md_fts_idx   ON meeting_document
  USING GIN (to_tsvector('english', coalesce(body_text,'')));

INSERT INTO meeting_body (jurisdiction_id, slug, name, index_url, vendor, notes) VALUES
  ((SELECT id FROM jurisdiction WHERE slug='duluth'), 'duluth-city-council',
   'Mayor & City Council',
   'https://www.duluthga.net/government/agendas___minutes/mayor___council_agendas___minutes.php',
   'Revize', 'Agenda packets published as "DuluthAgendaBinder<date>.pdf"'),
  ((SELECT id FROM jurisdiction WHERE slug='duluth'), 'duluth-planning-commission',
   'Planning Commission',
   'https://www.duluthga.net/government/agendas___minutes/planning_commission_agendas___minutes.php',
   'Revize', 'Meets 1st & 3rd Monday'),
  ((SELECT id FROM jurisdiction WHERE slug='duluth'), 'duluth-zba',
   'Zoning Board of Appeals',
   'https://www.duluthga.net/government/agendas___minutes/zoning_board_of_appeals_agendas___minutes.php',
   'Revize', 'Variance and appeal decisions')
ON CONFLICT (slug) DO NOTHING;

-- Same pattern as the UDC and case loaders: Postgres fetches the corpus itself
-- once published, because 12.5 M characters of meeting text cannot sensibly be
-- pushed through a SQL client.
CREATE OR REPLACE FUNCTION load_meeting_docs_from_url(p_url text)
RETURNS int LANGUAGE plpgsql AS $$
DECLARE v_body text; v_line text; j jsonb; n int := 0;
BEGIN
  PERFORM extensions.http_set_curlopt('CURLOPT_TIMEOUT','600');
  SELECT content INTO v_body FROM extensions.http_get(p_url);
  FOR v_line IN SELECT unnest(string_to_array(v_body, E'\n')) LOOP
    CONTINUE WHEN btrim(v_line) = '';
    j := v_line::jsonb;
    INSERT INTO meeting_document (
      body_id, meeting_date, doc_type, label, filename, url, sha256, bytes, pages,
      text_source, text_quality, text_chars, scanned_pages, ocr_truncated,
      body_text, date_parsed_as, date_from_body, case_refs, last_verified)
    VALUES (
      (SELECT id FROM meeting_body WHERE slug = j->>'body_slug'),
      nullif(j->>'meeting_date_final','')::date,
      j->>'doc_type', j->>'label', j->>'filename', j->>'url', j->>'sha256',
      (j->>'bytes')::bigint, (j->>'pages')::int,
      coalesce(j->>'text_source','none'), j->>'quality',
      (j->>'text_chars')::int, (j->>'scanned_pages')::int,
      coalesce((j->>'ocr_truncated')::boolean,false),
      coalesce(nullif(j->>'text',''), j->>'text_ocr'),
      j->>'date_parsed_as',
      (j->>'meeting_date') IS NULL AND (j->>'meeting_date_from_body') IS NOT NULL,
      ARRAY(SELECT jsonb_array_elements_text(coalesce(j->'case_refs','[]'::jsonb))),
      now())
    ON CONFLICT (url) DO UPDATE SET
      body_text = EXCLUDED.body_text, text_source = EXCLUDED.text_source,
      text_quality = EXCLUDED.text_quality, text_chars = EXCLUDED.text_chars,
      case_refs = EXCLUDED.case_refs, last_verified = now();
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
