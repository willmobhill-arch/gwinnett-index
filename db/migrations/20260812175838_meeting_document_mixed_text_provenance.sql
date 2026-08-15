-- Text provenance has to be able to say "part of this document is the publisher's
-- own text and part is an OCR reconstruction", because seven of the scanned Duluth
-- documents are exactly that. One is a 382-page binder with 154 scanned pages and
-- 449,287 characters of real publisher text.
--
-- The old CHECK allowed only embedded | ocr | none, which forced a choice between
-- two wrong answers: call the whole thing 'embedded' and pass off OCR guesses as
-- quotations of the record, or call it 'ocr' and throw away the ability to quote
-- the 449k characters that genuinely are quotable. Neither is acceptable for a
-- legal-reference index, so 'mixed' exists and carries the page list with it.

ALTER TABLE meeting_document DROP CONSTRAINT IF EXISTS meeting_document_text_source_check;
ALTER TABLE meeting_document ADD CONSTRAINT meeting_document_text_source_check
  CHECK (text_source IN ('embedded', 'ocr', 'mixed', 'none'));

ALTER TABLE meeting_document ADD COLUMN IF NOT EXISTS ocr_page_numbers int[];
ALTER TABLE meeting_document ADD COLUMN IF NOT EXISTS ocr_pages_dropped int[];

COMMENT ON COLUMN meeting_document.text_source IS
  'embedded = publisher text layer, quotable. ocr = wholly a reconstruction, never
   quote as the record. mixed = both; ocr_page_numbers lists the reconstructed
   pages. none = no text recovered.';
COMMENT ON COLUMN meeting_document.ocr_page_numbers IS
  '1-indexed pages whose text is an OCR reconstruction rather than the publisher''s.';
COMMENT ON COLUMN meeting_document.ocr_pages_dropped IS
  'Pages that were scanned but deliberately not OCR''d (--max-pages). Their content
   is absent from body_text entirely; this is the record of what is missing.';

CREATE OR REPLACE FUNCTION load_meeting_docs_from_url(p_url text)
RETURNS int LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
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
      ocr_page_numbers, ocr_pages_dropped,
      body_text, date_parsed_as, date_from_body, case_refs, last_verified)
    VALUES (
      (SELECT id FROM meeting_body WHERE slug = j->>'body_slug'),
      nullif(j->>'meeting_date_final','')::date,
      j->>'doc_type', j->>'label', j->>'filename', j->>'url', j->>'sha256',
      (j->>'bytes')::bigint, (j->>'pages')::int,
      coalesce(j->>'text_source','none'), j->>'quality',
      (j->>'text_chars')::int, (j->>'scanned_pages')::int,
      coalesce((j->>'ocr_truncated')::boolean,false),
      ARRAY(SELECT jsonb_array_elements_text(coalesce(j->'ocr_page_numbers','[]'::jsonb))::int),
      ARRAY(SELECT jsonb_array_elements_text(coalesce(j->'ocr_pages_dropped','[]'::jsonb))::int),
      -- Embedded text first, OCR appended. Concatenating rather than choosing is
      -- what makes a 'mixed' document searchable across both halves; the page
      -- numbers above are what keep them distinguishable.
      nullif(concat_ws(E'\n\n', nullif(j->>'text',''), nullif(j->>'text_ocr','')), ''),
      j->>'date_parsed_as',
      (j->>'meeting_date') IS NULL AND (j->>'meeting_date_from_body') IS NOT NULL,
      ARRAY(SELECT jsonb_array_elements_text(coalesce(j->'case_refs','[]'::jsonb))),
      now())
    ON CONFLICT (url) DO UPDATE SET
      body_text = EXCLUDED.body_text, text_source = EXCLUDED.text_source,
      text_quality = EXCLUDED.text_quality, text_chars = EXCLUDED.text_chars,
      ocr_page_numbers = EXCLUDED.ocr_page_numbers,
      ocr_pages_dropped = EXCLUDED.ocr_pages_dropped,
      ocr_truncated = EXCLUDED.ocr_truncated,
      case_refs = EXCLUDED.case_refs, last_verified = now();
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
