# Migrations

Applied to Supabase project `losmnziukaqptxhqnhjh`. Pull the current state with:

    supabase link --project-ref losmnziukaqptxhqnhjh
    supabase db pull

Key objects:

| Object | Purpose |
|---|---|
| `resolve_jurisdiction(lon, lat, band_m)` | point -> governing jurisdiction + confidence band |
| `ingest_gwinnett_cases(layer, name, page)` | paginated pull from county ArcGIS, in-database |
| `load_udc_sections_from_url(url)` | fetch + load the 860 UDC sections |
| `load_duluth_cases_from_url(url)` | fetch + load agenda-mined Duluth cases |
| `load_meeting_docs_from_url(url)` | fetch + load meeting document index |
| `applicant_norm / applicant_kind / applicant_principal / applicant_agent` | entity resolution |
| `build_merge_candidates / apply_applicant_merges` | fuzzy merge with review queue |
| `developer_activity` (view) | private-sector applicant leaderboard |

`resolver_probe` holds the 1,915 scored test points — the resolver's regression
fixture. Re-score any time:

    SELECT coalesce(r.confidence,'unresolved') AS confidence, count(*) probes,
           count(*) FILTER (WHERE r.slug = p.expected_slug) correct
    FROM resolver_probe p
    LEFT JOIN LATERAL resolve_jurisdiction(ST_X(p.pt), ST_Y(p.pt), 150) r ON true
    GROUP BY 1;

Expected: `high` = 100% correct. Below that, something regressed.
