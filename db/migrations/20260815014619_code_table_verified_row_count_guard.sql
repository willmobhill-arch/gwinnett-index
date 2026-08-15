-- Table 2-B carried quality='verified' with 15 rows while the source had 20: the
-- extractor stopped at a page boundary and the flag asserted a check that had not
-- actually happened. This makes that state unrepresentable.
--
-- n_rows is the count verified against the rendered source page. If a table claims to
-- be verified, the rows actually stored must match that count.
ALTER TABLE code_table
  ADD CONSTRAINT code_table_verified_rows_match
  CHECK (quality <> 'verified' OR n_rows = jsonb_array_length(rows));

-- Column count must likewise agree with the header it was verified against.
ALTER TABLE code_table
  ADD CONSTRAINT code_table_ncols_match
  CHECK (n_cols = coalesce(array_length(header, 1), n_cols));
