-- A third class of evidence, ranked between the two that already existed.
--
-- Some motions do not name their case: "to approve ordinance O2026-26 to amend
-- the City's Unified Development Code, Article 9, as presented". Others name it
-- with a typo the whitelist rightly refuses -- "case MZA2026-001" for MZ2026-001,
-- "case TA2-26-006" for TA2026-006. Loosening the pattern to swallow those would
-- trade a missing answer for a possibly wrong one.
--
-- Instead the motion is bound to the case named by the agenda item it sits inside,
-- which is structural rather than proximity-based: the section boundary is what
-- limits it, not a character distance. Validated before being trusted -- across
-- every motion where both methods produce an answer they agree 126 times and
-- disagree 0 times.
--
-- It is still the weaker evidence, so it ranks below a motion that names its own
-- case and above a packet vote that merely sits near one.
--
--   1. minutes_motion   -- the case is named INSIDE the motion that was voted on
--   2. minutes_section  -- the case is named by the agenda item containing it
--   3. anything else    -- the case and the vote are merely near each other
CREATE OR REPLACE FUNCTION duluth_decision_supersedes(
  new_extraction text, new_date date, new_decision text,
  old_extraction text, old_date date, old_decision text)
RETURNS boolean
LANGUAGE sql IMMUTABLE
SET search_path = public, pg_temp
AS $$
  WITH rank AS (
    SELECT CASE new_extraction WHEN 'minutes_motion' THEN 2
                               WHEN 'minutes_section' THEN 1 ELSE 0 END AS n,
           CASE old_extraction WHEN 'minutes_motion' THEN 2
                               WHEN 'minutes_section' THEN 1 ELSE 0 END AS o
  )
  SELECT CASE
    WHEN new_decision IS NULL THEN false          -- nothing to say
    WHEN old_decision IS NULL THEN true           -- anything beats nothing
    WHEN (SELECT n FROM rank) > (SELECT o FROM rank) THEN true
    WHEN (SELECT n FROM rank) < (SELECT o FROM rank) THEN false
    -- same class of evidence: the later hearing is the operative one
    WHEN old_date IS NULL THEN true
    WHEN new_date IS NULL THEN false
    ELSE new_date >= old_date
  END;
$$;

COMMENT ON FUNCTION duluth_decision_supersedes IS
  'Which of two competing Duluth decision records is authoritative. Evidence
   quality first (minutes_motion > minutes_section > proximity), then recency.';
