-- Follow-ups the linter surfaced once RLS was on. None were exploitable on their
-- own, but the point of the read-only posture is that it does not rest on any
-- single control being right.

-- 1. developer_activity was a SECURITY DEFINER view, so it ran with the creator's
--    permissions and bypassed the caller's RLS entirely. Harmless while every
--    policy reads "everything", and a hole the moment one of them does not.
ALTER VIEW public.developer_activity SET (security_invoker = on);

-- 2. Pin search_path on every project function. Without it, name resolution inside
--    these bodies follows the CALLER's search_path, so an unqualified reference can
--    be captured by an object the caller controls. These functions already
--    schema-qualify their extensions.http_* calls, so behaviour is unchanged.
DO $$
DECLARE f record;
BEGIN
  FOR f IN
    SELECT p.oid::regprocedure AS sig
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname IN (
        'resolve_jurisdiction','ingest_gwinnett_cases','epoch_ms_to_date',
        'applicant_principal','applicant_agent','applicant_norm','applicant_kind',
        'build_merge_candidates','apply_applicant_merges',
        'load_udc_sections_from_url','load_udc_tables_from_url',
        'load_duluth_cases_from_url','load_meeting_docs_from_url')
  LOOP
    EXECUTE format('ALTER FUNCTION %s SET search_path = public, extensions, pg_temp', f.sig);
  END LOOP;
END $$;

-- NOT fixed, and worth knowing why rather than rediscovering it:
--
--   st_estimatedextent is SECURITY DEFINER and PostgREST exposes it at
--     /rest/v1/rpc/st_estimatedextent, where it acts as a mild table-existence
--     oracle. It cannot be revoked from here: PostGIS's grants were made by
--     supabase_admin, and a REVOKE issued as postgres is a silent no-op against
--     another grantor's grant -- it returns success and changes nothing. Check
--     pg_proc.proacl, not the absence of an error, if you retry this as
--     supabase_admin. Low stakes either way: every table it could confirm the
--     existence of is published under CC0 on the public site.
--
--   spatial_ref_sys has RLS disabled. It is owned by the postgis extension and
--     holds nothing but published projection definitions; enabling RLS on an
--     extension-owned table is a known source of breakage for no gain.
--
--   postgis and pg_trgm live in the public schema. Relocating them would rewrite
--     every spatial index and every dependent function signature. The warning is
--     about tidiness, not exposure.
