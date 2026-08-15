-- Reconciliation: these two columns were applied ad hoc during the Table 2-B
-- verification pass and never landed in a migration, so a rebuild from
-- db/migrations alone produced a code_table that load_udc_tables_from_url
-- could not run against (it reads code_table.quality in its ON CONFLICT arm).
--
-- 17 of the 18 extracted tables have never been checked against the rendered
-- source page. Only Table 2-B has, and even its merged PUD/CBD rows are
-- unreliable. That is what these columns exist to say out loud: an unverified
-- number that looks verified is the failure mode this project cannot afford.
ALTER TABLE code_table ADD COLUMN IF NOT EXISTS quality text DEFAULT 'unverified';
ALTER TABLE code_table ADD COLUMN IF NOT EXISTS verification_note text;

COMMENT ON COLUMN code_table.quality IS
  'verified = every cell compared against the rendered source page. unverified =
   extracted by pdfplumber and never eyeballed. Never present unverified
   dimensional standards as authoritative.';

-- Same story: land_use_case.applicant_norm was added ad hoc during entity
-- resolution. It caches applicant_norm(applicant_raw) so the 11,848-row
-- clustering pass does not recompute a plpgsql function per row per comparison.
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS applicant_norm text;
