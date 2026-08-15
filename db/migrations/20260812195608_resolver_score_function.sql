-- The resolver's regression fixture, callable as one RPC.
--
-- export_snapshot.py refuses to write a snapshot unless the high-confidence band
-- is 100% correct, which is the single check that stops a quietly-degraded
-- resolver reaching the published site. That check was only reachable over a
-- direct Postgres connection; environments that can only speak HTTPS -- this
-- container, and any CI runner behind an HTTP proxy -- had no way to run it and
-- would have had to skip the gate. Skipping it is not an option, so the query
-- moves into the database where PostgREST can expose it.
--
-- Scoring 1,915 probes takes a moment; that is fine for a per-build gate and far
-- cheaper than 1,915 separate REST round-trips.
CREATE OR REPLACE FUNCTION resolver_score()
RETURNS TABLE (confidence text, probes bigint, correct bigint)
LANGUAGE sql STABLE
SET search_path = public, extensions, pg_temp
AS $$
  SELECT coalesce(r.confidence, 'unresolved') AS confidence,
         count(*) AS probes,
         count(*) FILTER (WHERE r.slug = p.expected_slug) AS correct
  FROM resolver_probe p
  LEFT JOIN LATERAL resolve_jurisdiction(ST_X(p.pt), ST_Y(p.pt), 150) r ON true
  GROUP BY 1
  ORDER BY 1;
$$;

COMMENT ON FUNCTION resolver_score IS
  'Regression fixture for resolve_jurisdiction, scored against 1,915 probe points
   taken from the county''s own zoning layers. Expected: confidence=high is 100%
   correct (1,546/1,546). Below that, something regressed -- do not publish.';
