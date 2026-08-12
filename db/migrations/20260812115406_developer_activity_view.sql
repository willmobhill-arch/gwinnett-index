-- "Who is building the most in unincorporated Gwinnett, and where are they now?"
-- Government applicants (county-initiated rezonings) and law firms (agents filing
-- on behalf of clients) are excluded -- including them would put the Planning
-- Division and Mahaffey Pickens Tucker at the top of a developer leaderboard.
CREATE OR REPLACE VIEW developer_activity AS
SELECT
  a.id, a.display_name, a.norm_name, a.kind,
  a.case_count                                            AS total_cases,
  a.first_year, a.last_year,
  a.last_year - a.first_year + 1                          AS span_years,
  a.variant_count                                         AS name_variants,
  sum(c.res_units)                                        AS res_units,
  round(sum(c.acres))                                     AS acres,
  sum(c.nonres_sqft)                                      AS nonres_sqft,
  count(*) FILTER (WHERE c.year >= 2020)                  AS cases_since_2020,
  count(*) FILTER (WHERE c.decision ILIKE 'AP%')          AS approved,
  count(*) FILTER (WHERE c.decision ILIKE 'DEN%')         AS denied,
  count(DISTINCT c.agent_raw) FILTER (WHERE c.agent_raw IS NOT NULL) AS agents_used
FROM applicant a
JOIN land_use_case c ON c.applicant_id = a.id
WHERE a.kind = 'company'
GROUP BY a.id, a.display_name, a.norm_name, a.kind, a.case_count,
         a.first_year, a.last_year, a.variant_count;

COMMENT ON VIEW developer_activity IS
  'Private-sector applicant activity in unincorporated Gwinnett County, 1970-2026.
   Excludes government and law-firm applicants. Source: Gwinnett County GIS
   GC_Planning layers 1/2/15, resolved to entities via applicant_norm().';
