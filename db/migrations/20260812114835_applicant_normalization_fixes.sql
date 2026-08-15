-- Fix 1: classify on the PRINCIPAL, not the raw string. Classifying the raw
-- string meant "PARAN HOMES, LLC C/O MAHAFFEY PICKENS TUCKER, LLP" came back as
-- kind='law_firm' -- the exact conflation the C/O split exists to prevent.
--
-- Fix 2: collapse runs of single letters so "D.R. HORTON" -> "D R HORTON" and
-- "DR HORTON" both land on "DR HORTON".
--
-- Fix 3: junk placeholders ("NA", "N/A", ".") normalise to NULL, not to themselves.

CREATE OR REPLACE FUNCTION applicant_norm(raw text)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE s text;
BEGIN
  s := applicant_principal(raw);
  IF s IS NULL OR s = '' THEN RETURN NULL; END IF;
  IF upper(btrim(s)) IN ('NA','N/A','NONE','UNKNOWN','SAME','.','-','--','?') THEN RETURN NULL; END IF;

  s := regexp_replace(s, '\s+-\s+(ATLANTA|GEORGIA|GA|SOUTHEAST|EAST|WEST|NORTH|SOUTH)\M.*$', '', 'g');
  s := replace(s, '&', ' AND ');
  s := regexp_replace(s, '[^A-Z0-9 ]', ' ', 'g');
  s := regexp_replace(s, '\s+', ' ', 'g');
  s := btrim(s);
  s := regexp_replace(s, '^THE\s+', '');

  FOR i IN 1..4 LOOP
    s := btrim(regexp_replace(s,
      '\s+(LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|COMPANIES|LP|L P|LLP|LTD|LIMITED|PC|PA|TRUST|ET AL)$',
      '', 'g'));
  END LOOP;

  -- collapse initial runs: "D R HORTON" -> "DR HORTON", "J B C SMITH" -> "JBC SMITH"
  FOR i IN 1..4 LOOP
    s := regexp_replace(s, '\m([A-Z]) ([A-Z])\M', '\1\2', 'g');
  END LOOP;

  s := regexp_replace(s, '\s+', ' ', 'g');
  RETURN nullif(btrim(s), '');
END $$;

CREATE OR REPLACE FUNCTION applicant_kind(raw text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  WITH p AS (SELECT applicant_principal(raw) AS s)
  SELECT CASE
    WHEN (SELECT s FROM p) IS NULL OR btrim((SELECT s FROM p)) = ''
         OR upper(btrim((SELECT s FROM p))) IN ('NA','N/A','NONE','UNKNOWN','SAME','.','-','--','?')
      THEN 'unknown'
    WHEN (SELECT s FROM p) ~ '(PLANNING DIVISION|BOARD OF COMMISSIONERS|GWINNETT COUNTY|CITY OF |DEPARTMENT OF|DEPT OF|SCHOOL (DISTRICT|SYSTEM)|BOARD OF EDUCATION|HOUSING AUTHORITY|STATE OF GEORGIA|GDOT|MARTA)'
      THEN 'government'
    WHEN (SELECT s FROM p) ~ '(\mLLP\M|LAW (FIRM|OFFICE|GROUP)|ATTORNEY|\mESQ\M|MAHAFFEY PICKENS TUCKER|ANDERSEN TATE|WEISSMAN|THOMPSON OBRIEN)'
      THEN 'law_firm'
    WHEN (SELECT s FROM p) ~ '(\mLLC\M|\mINC\M|\mCORP|\mCOMPANY\M|\mCOMPANIES\M|\mLP\M|\mLTD\M|HOMES|BUILDERS?|DEVELOP|PROPERTIES|PARTNERS|INVESTMENT|CAPITAL|REALTY|ENTERPRISES|GROUP|ASSOCIATES|BANK|CHURCH|MINISTR)'
      THEN 'company'
    ELSE 'individual'
  END;
$$;
