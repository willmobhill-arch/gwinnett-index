CREATE TABLE IF NOT EXISTS code_section (
  id              bigserial PRIMARY KEY,
  jurisdiction_id int REFERENCES jurisdiction(id),
  citation        text NOT NULL,
  kind            text,              -- article|division|section|subsection|table|form|definitions_group
  identifier      text,
  title           text,
  article         text,
  article_title   text,
  section         text,
  section_title   text,
  level           int,
  body_md         text,
  page_from       int,
  page_to         int,
  adopted_date    date,
  amended_through date,
  source_url      text NOT NULL,
  last_verified   timestamptz DEFAULT now(),
  UNIQUE (jurisdiction_id, citation, page_from)
);
CREATE INDEX IF NOT EXISTS cs_jur_idx  ON code_section (jurisdiction_id);
CREATE INDEX IF NOT EXISTS cs_cite_idx ON code_section (citation);
CREATE INDEX IF NOT EXISTS cs_art_idx  ON code_section (article);
CREATE INDEX IF NOT EXISTS cs_fts_idx  ON code_section
  USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body_md,'')));

-- Dimensional tables get their own structured home. Block text extraction
-- linearises these into column soup where the value-to-column mapping is lost --
-- for Table 2-B that turns RA-200's 75 ft front setback into 20 ft. Cells are
-- recovered separately with pdfplumber and stored as real rows.
CREATE TABLE IF NOT EXISTS code_table (
  id              bigserial PRIMARY KEY,
  jurisdiction_id int REFERENCES jurisdiction(id),
  citation        text NOT NULL,
  title           text,
  header          text[],
  rows            jsonb,
  markdown        text,
  n_cols          int,
  n_rows          int,
  page_from       int,
  page_to         int,
  source_url      text NOT NULL,
  last_verified   timestamptz DEFAULT now(),
  UNIQUE (jurisdiction_id, citation, page_from)
);
CREATE INDEX IF NOT EXISTS ct_cite_idx ON code_table (citation);

-- Loader for the full section corpus. The section bodies total 1.22 M characters,
-- which is impractical to push through a SQL client; Postgres fetches the JSONL
-- itself once it is published (e.g. raw.githubusercontent.com/<repo>/main/data/
-- udc_sections.jsonl), exactly as the case ingester fetches the county's ArcGIS.
CREATE OR REPLACE FUNCTION load_udc_sections_from_url(p_url text, p_slug text DEFAULT 'duluth')
RETURNS int LANGUAGE plpgsql AS $$
DECLARE v_jid int; v_body text; v_line text; j jsonb; n int := 0;
BEGIN
  SELECT id INTO v_jid FROM jurisdiction WHERE slug = p_slug;
  IF v_jid IS NULL THEN RAISE EXCEPTION 'unknown jurisdiction %', p_slug; END IF;

  PERFORM extensions.http_set_curlopt('CURLOPT_TIMEOUT','300');
  SELECT content INTO v_body FROM extensions.http_get(p_url);

  FOR v_line IN SELECT unnest(string_to_array(v_body, E'\n')) LOOP
    CONTINUE WHEN btrim(v_line) = '';
    j := v_line::jsonb;
    INSERT INTO code_section (
      jurisdiction_id, citation, kind, identifier, title, article, article_title,
      section, section_title, level, body_md, page_from, page_to,
      adopted_date, amended_through, source_url, last_verified)
    VALUES (
      v_jid, j->>'citation', j->>'kind', j->>'identifier', j->>'title',
      j->>'article', j->>'article_title', j->>'section', j->>'section_title',
      (j->>'level')::int, j->>'body', (j->>'page_from')::int, (j->>'page_to')::int,
      (j->>'adopted')::date, (j->>'amended_through')::date, j->>'source_url', now())
    ON CONFLICT (jurisdiction_id, citation, page_from) DO UPDATE SET
      body_md = EXCLUDED.body_md, title = EXCLUDED.title,
      amended_through = EXCLUDED.amended_through, last_verified = now();
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
