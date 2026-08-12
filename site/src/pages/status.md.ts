import type { APIRoute } from 'astro';
import { stats, jurisdictions, usingFixtures } from '../lib/source';
import { frontmatter, table, md } from '../lib/md';
import { abs, LICENCE } from '../lib/site';

export const GET: APIRoute = () => {
  const s = stats();
  const js = jurisdictions();
  const r = s.resolver ?? {};
  const probes = Object.values(r).reduce((a, b) => a + b.probes, 0);
  const correct = Object.values(r).reduce((a, b) => a + b.correct, 0);

  return md(
    frontmatter({
      title: 'Status and freshness — Gwinnett Index',
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs('/status'),
      licence: LICENCE,
    }) +
      `# Status and freshness

What is loaded, what has actually been checked, and what is knowingly missing. An index that
hides its staleness is worse than one that admits it.

## Resolver accuracy

Scored against ${s.probes?.toLocaleString('en-US')} probe points taken from the county's own zoning layers.

${table(
  ['Confidence', 'Probes', 'Correct', 'Rate'],
  [
    ...Object.entries(r).map(([k, v]) => [
      k, v.probes, v.correct, v.probes ? `${((v.correct / v.probes) * 100).toFixed(2)}%` : '—',
    ]),
    ['overall', probes, correct, probes ? `${((correct / probes) * 100).toFixed(2)}%` : '—'],
  ]
)}

When the resolver reports **high** confidence it has never been wrong. Every error falls inside
the low-confidence band, and every one was within 141 m of a jurisdiction line — annexation lag,
since cities annex continuously while Census boundaries update yearly.

## Coverage

${table(['Metric', 'Value'], [
  ['Jurisdictions', js.length],
  ['Land-use cases', s.total_cases],
  ['— county (Board of Commissioners)', s.county_cases],
  ['— City of Duluth (agenda-mined)', s.duluth_cases],
  ['Cases with a source link', s.with_source_url],
  ['Cases with a parcel PIN', s.with_pins],
  ['Code sections', s.code_sections],
  ['Code tables', s.code_tables],
  ['— verified against the source page', s.code_tables_verified],
  ['Meeting documents', s.meeting_docs],
  ['Build data source', usingFixtures ? 'site/fixtures (SAMPLE)' : (s.generated_from ?? 'snapshot')],
])}

## Known gaps

- **${s.code_tables - s.code_tables_verified} of ${s.code_tables} code tables are unverified.** Only Table 2-B has been checked
  against the rendered source page, and even its merged PUD and CBD rows remain unreliable.
- **${s.merge_pending} applicant name pairs await human review**, so developer case counts are lower bounds.
- **Duluth minutes are 57–69% scanned** with no text layer. OCR text is stored separately and
  marked as a reconstruction, never as a quotation of the record. The OCR pass is incomplete.
- **Duluth case fields are agenda-mined, not database-sourced.** The city runs no case tracker;
  applicant and address fields are frequently mangled by the extraction.
- **16 municipalities have boundaries but no corpus.** They resolve correctly; there is no code
  or case data behind them yet.
- **Meeting body text is not published here** (12.5 M characters); only document metadata is indexed.

## Legal posture

${table(['Content', 'Posture', 'Basis'], [
  ['Ordinance and plan text', 'Mirrored in full', 'Georgia v. Public.Resource.Org (2020) — edicts of government'],
  ['Case records', 'Mirrored in full', 'Facts; Georgia Open Records Act'],
  ['County parcel and zoning geometry', 'NEVER rehosted', 'Gwinnett GIS licence forbids redistribution — queried live, linked out'],
  ['Jurisdiction boundaries', 'Hosted', 'US Census TIGER — federal, public domain'],
  ['IBC/IRC base text', 'NEVER indexed', "ICC copyright; Georgia's amendment packets indexed instead"],
])}
`
  );
};
