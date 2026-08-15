-- A spanning header is a label sitting above and across several columns, e.g.
-- "Zoning District" over four district columns in Table 3-B, or
-- "1. Provide a buffer on the lot of this use" over five use columns in Table 7-A.
-- It was previously smeared into the data columns it overlapped, destroying the
-- header. It is a distinct piece of meaning and needs its own field.
ALTER TABLE code_table ADD COLUMN IF NOT EXISTS spanning_header text;

-- Where the header/rows came from, so a future run can tell a hand-checked value
-- from a parser guess without re-deriving it.
ALTER TABLE code_table ADD COLUMN IF NOT EXISTS header_source text;

COMMENT ON COLUMN code_table.spanning_header IS
  'Label spanning multiple columns, kept separate from leaf column names.';
COMMENT ON COLUMN code_table.header_source IS
  'rendered-image (hand-verified) | geometry | markdown | legacy';
COMMENT ON COLUMN code_table.quality IS
  'verified = checked cell-by-cell against the rendered source page; '
  'defective = checked and known wrong, do not publish cell values; '
  'unverified = not yet checked.';
