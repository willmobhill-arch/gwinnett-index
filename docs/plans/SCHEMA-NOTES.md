# Applied migrations (Supabase project losmnziukaqptxhqnhjh)

| Version | Name |
|---|---|
| 20260812013117 | enable_postgis_and_jurisdictions |
| 20260812013323 | boundary_staging_table |
| 20260812013410 | resolve_jurisdiction_function |
| 20260812015551 | enable_http_and_geoid_map |
| 20260812015913 | land_use_case_table |
| 20260812015946 | ingest_gwinnett_cases_function |
| 20260812020310 | resolver_with_confidence_band |

Pull them into `db/migrations/` with:

    supabase link --project-ref losmnziukaqptxhqnhjh
    supabase db pull

Two tables are scratch and can be dropped once the pipeline is settled:
`boundary_staging` (unused — superseded by the in-database http fetch) and
`raw_fetch` (response cache; useful for reproducibility, safe to truncate).

`resolver_probe` holds the 1,915 scored test points and should be KEPT — it is the
regression fixture for the resolver. Re-score any time with:

    SELECT coalesce(r.confidence,'unresolved') AS confidence,
           count(*) AS probes,
           count(*) FILTER (WHERE r.slug = p.expected_slug) AS correct
    FROM resolver_probe p
    LEFT JOIN LATERAL resolve_jurisdiction(ST_X(p.pt), ST_Y(p.pt), 150) r ON true
    GROUP BY 1;

Expected: high = 100.00% correct. If that ever drops below 100%, something regressed.
