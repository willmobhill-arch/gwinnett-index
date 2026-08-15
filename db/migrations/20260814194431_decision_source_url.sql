-- Where the DECISION was recorded, as distinct from where the case was described.
--
-- source_url is set at insert and never moves, so it holds whichever document was
-- seen first -- usually the agenda. MZ2026-001 is the clear case: the vote is in
-- the 2026-08-03 Planning Commission minutes, but source_url points at that day's
-- agenda, which contains the request and no outcome at all. Following the link to
-- verify a vote lands you somewhere the vote is not.
--
-- Overloading source_url would be worse: the agenda is the right citation for the
-- request text, the minutes for the outcome. Two documents, two fields.
ALTER TABLE land_use_case ADD COLUMN IF NOT EXISTS decision_source_url text;

COMMENT ON COLUMN land_use_case.decision_source_url IS
  'The document the decision and vote were read from -- minutes, usually. Distinct
   from source_url, which cites the document describing the request. Moves as part
   of the decision field set, so it always names the hearing actually recorded.';

-- load_duluth_cases_from_url is redefined to populate and carry it; the body is
-- otherwise identical to 20260812201000, with decision_source_url added to the
-- decision field set so it moves with the decision it belongs to.
