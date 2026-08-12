-- Applicant name normalisation for entity resolution.
--
-- The county's APPLICANT field is a free-text varchar(50) that conflates two
-- different parties via the "C/O" convention: "PARAN HOMES, LLC C/O MAHAFFEY
-- PICKENS TUCKER, LLP" means Paran Homes is the applicant and Mahaffey Pickens
-- Tucker is their land-use counsel. 138 records use it.
--
-- Failing to split these makes the law firm look like the largest developer in
-- Gwinnett when it is actually the agent for dozens of unrelated developers.
-- That single mistake would invalidate the whole leaderboard.
--
-- Note also: the field truncates at 50 chars (33 records sit at the limit), so
-- some names are cut mid-word and cannot be fully recovered from this source.

-- Split off the agent half.
CREATE OR REPLACE FUNCTION applicant_principal(raw text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT btrim(regexp_replace(upper(btrim(raw)), '\mC/O\M.*$', '', 'g'));
$$;

CREATE OR REPLACE FUNCTION applicant_agent(raw text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(btrim((regexp_match(upper(btrim(raw)), '\mC/O\M\s*(.*)$'))[1]), '');
$$;

-- Canonical form: strip legal suffixes, punctuation, articles, region qualifiers.
CREATE OR REPLACE FUNCTION applicant_norm(raw text)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE s text;
BEGIN
  s := applicant_principal(raw);
  IF s IS NULL OR s = '' THEN RETURN NULL; END IF;

  s := regexp_replace(s, '\s+-\s+(ATLANTA|GEORGIA|GA|SOUTHEAST|EAST|WEST|NORTH|SOUTH)\M.*$', '', 'g');
  s := replace(s, '&', ' AND ');
  s := regexp_replace(s, '[^A-Z0-9 ]', ' ', 'g');
  s := regexp_replace(s, '\s+', ' ', 'g');
  s := btrim(s);
  s := regexp_replace(s, '^THE\s+', '');

  -- Peel trailing legal-form tokens repeatedly: "PULTE HOME COMPANY LLC" -> "PULTE HOME"
  FOR i IN 1..4 LOOP
    s := btrim(regexp_replace(s,
      '\s+(LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|COMPANIES|LP|L P|LLP|LTD|LIMITED|PC|PA|TRUST|ET AL)$',
      '', 'g'));
  END LOOP;

  s := regexp_replace(s, '\s+', ' ', 'g');
  RETURN nullif(btrim(s), '');
END $$;

-- Classify so a developer leaderboard is not polluted by county staff and counsel.
CREATE OR REPLACE FUNCTION applicant_kind(raw text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN raw IS NULL OR btrim(raw) = '' OR upper(btrim(raw)) IN ('NA','N/A','NONE','UNKNOWN','.','-')
      THEN 'unknown'
    WHEN upper(raw) ~ '(PLANNING DIVISION|BOARD OF COMMISSIONERS|GWINNETT COUNTY|CITY OF |DEPARTMENT OF|DEPT OF|SCHOOL (DISTRICT|SYSTEM)|BOARD OF EDUCATION|HOUSING AUTHORITY|STATE OF GEORGIA|GDOT|MARTA)'
      THEN 'government'
    WHEN upper(raw) ~ '(\mLLP\M|\mP\.?C\.?$|LAW (FIRM|OFFICE|GROUP)|ATTORNEY|\mESQ\M|MAHAFFEY PICKENS TUCKER|ANDERSEN TATE|WEISSMAN|THOMPSON OBRIEN)'
      THEN 'law_firm'
    WHEN upper(raw) ~ '(\mLLC\M|\mINC\M|\mCORP|\mCOMPANY\M|\mCOMPANIES\M|\mLP\M|\mLTD\M|HOMES|BUILDERS?|DEVELOP|PROPERTIES|PARTNERS|INVESTMENT|CAPITAL|REALTY|ENTERPRISES|GROUP|ASSOCIATES|BANK|CHURCH|MINISTR)'
      THEN 'company'
    ELSE 'individual'
  END;
$$;
