import type { APIRoute } from 'astro';
import { stats, jurisdictions, usingFixtures } from '../lib/source';
import { frontmatter, table, md } from '../lib/md';
import { abs, LICENCE } from '../lib/site';

export const GET: APIRoute = () => {
  const s = stats();
  const js = jurisdictions();
  const r = s.resolver ?? {};
  const dx = s.duluth_extraction;
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

${s.code_tables_verified < s.code_tables
  ? `- **${s.code_tables - s.code_tables_verified} of ${s.code_tables} code tables are unverified.** Their cell values are withheld
  until every cell has been read against the rendered source page.
`
  : ''}- **${s.merge_pending} applicant name pairs await human review**, so developer case counts are lower bounds.
- **Duluth minutes are 57–69% scanned** with no text layer. OCR text is stored separately and
  marked as a reconstruction, never as a quotation of the record. The OCR pass is incomplete.
- **Duluth case fields are agenda-mined, not database-sourced.** The city runs no case tracker,
  so these rows are pattern-matched out of agenda and minutes PDFs. Field-level quality is poor,
  measured across all ${dx?.cases ?? 0}: ${dx?.location_without_street_number ?? 0} have a "location" with no street number
  (${dx?.location_is_junk ?? 0} are plainly not addresses at all), ${dx?.request_is_boilerplate ?? 0} have a "request" that is just
  the word ORDINANCE, ${dx?.applicant_overran ?? 0} have an applicant field that ran on into a mailing address, and
  only ${dx?.with_zoning ?? 0} carry a zoning district. Treat each as an index entry pointing at a PDF, not as
  a structured record: the linked document is the authority, the fields are a finding aid.
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
