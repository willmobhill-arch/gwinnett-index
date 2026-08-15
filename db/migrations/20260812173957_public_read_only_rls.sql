-- Row Level Security: read-only public access.
--
-- Applied 2026-08-12. Verified as the anon role: SELECT works everywhere, INSERT/
-- UPDATE/DELETE all raise insufficient_privilege.
--
-- Why this was needed: the API Worker and the site both
-- authenticate with the Supabase *anon* key, which is publishable by design and
-- ends up in a Worker binding and, eventually, in anyone's network tab. With RLS
-- disabled, that key is not read-only — PostgREST exposes INSERT, UPDATE and
-- DELETE on every table in the public schema to anon. Anyone who has the project
-- URL and that key can rewrite the case corpus, and nothing about the site would
-- look any different afterwards.
--
-- The fix is not to hide the key. It is to make the key harmless: RLS on, SELECT
-- granted, everything else denied. The data is public record published under CC0,
-- so unrestricted reads are the intended posture; unrestricted writes never were.
--
-- Ingestion is unaffected. Every loader runs INSIDE Postgres (ingest_gwinnett_cases,
-- load_udc_sections_from_url, load_duluth_cases_from_url, load_meeting_docs_from_url)
-- as the owner, and RLS does not apply to the table owner. The service_role key
-- bypasses RLS too. Only anon and authenticated are constrained here.

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'jurisdiction','jurisdiction_county','geoid_map','land_use_case','applicant',
    'applicant_variant','applicant_merge_candidate','code_section','code_table',
    'meeting_body','meeting_document','resolver_probe','raw_fetch','boundary_staging'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);

    -- Read: everything. This is public record data published under CC0.
    EXECUTE format($f$
      CREATE POLICY %I ON public.%I FOR SELECT TO anon, authenticated USING (true)
    $f$, t || '_public_read', t);
  END LOOP;
END $$;

-- Belt and braces: even if a future policy is written too loosely, the grants
-- themselves do not permit writing.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM anon, authenticated;

-- spatial_ref_sys belongs to the postgis extension and is reference data. It is
-- left alone deliberately: enabling RLS on an extension-owned table is a known
-- source of breakage, and it contains nothing but published projection definitions.

COMMENT ON SCHEMA public IS
  'Public read-only. anon and authenticated may SELECT and nothing else. Ingestion
   runs in-database as the owner and is unaffected by these policies.';
