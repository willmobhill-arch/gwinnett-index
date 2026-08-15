-- Scoring the resolver's 1,915-probe fixture takes 36 seconds (about 19 ms per
-- resolve, which is fine for the one call a live API request makes and hopeless
-- as a synchronous REST call). PostgREST cancels it on the anon statement
-- timeout, so a build that can only reach the database over HTTPS had no way to
-- run the gate that stops a degraded resolver reaching the published site.
--
-- Raising anon's statement_timeout would fix this build and hand every anonymous
-- caller a 36-second query to point at the public API. So the score is computed
-- where it can be, cached, and read cheaply at build time.
--
-- The danger with any cache is that it silently goes stale, which would turn the
-- gate into decoration. Freshness is therefore tied to the thing that would
-- invalidate it: the score must be newer than the most recent change to any
-- jurisdiction boundary. Reload the boundaries and the build fails until the
-- fixture is re-scored, which is the correct behaviour.

CREATE TABLE IF NOT EXISTS resolver_score_cache (
  confidence  text PRIMARY KEY,
  probes      bigint NOT NULL,
  correct     bigint NOT NULL,
  scored_at   timestamptz NOT NULL DEFAULT now(),
  boundary_as_of timestamptz
);

ALTER TABLE resolver_score_cache ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS resolver_score_cache_public_read ON resolver_score_cache;
CREATE POLICY resolver_score_cache_public_read
  ON resolver_score_cache FOR SELECT TO anon, authenticated USING (true);
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON resolver_score_cache FROM anon, authenticated;

CREATE OR REPLACE FUNCTION refresh_resolver_score()
RETURNS TABLE (confidence text, probes bigint, correct bigint)
LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
DECLARE v_boundary timestamptz;
BEGIN
  SELECT max(last_verified) INTO v_boundary FROM jurisdiction;
  DELETE FROM resolver_score_cache;
  INSERT INTO resolver_score_cache (confidence, probes, correct, scored_at, boundary_as_of)
  SELECT coalesce(r.confidence, 'unresolved'),
         count(*),
         count(*) FILTER (WHERE r.slug = p.expected_slug),
         now(), v_boundary
  FROM resolver_probe p
  LEFT JOIN LATERAL resolve_jurisdiction(ST_X(p.pt), ST_Y(p.pt), 150) r ON true
  GROUP BY 1;
  RETURN QUERY SELECT c.confidence, c.probes, c.correct FROM resolver_score_cache c
               ORDER BY c.confidence;
END $$;

COMMENT ON TABLE resolver_score_cache IS
  'Cached result of the resolver regression fixture. Expected: confidence=high is
   100% correct (1,546/1,546). A build must refuse to publish if that is not true,
   or if scored_at is older than boundary_as_of would imply -- see
   scripts/export_snapshot_rest.py.';

SELECT * FROM refresh_resolver_score();
