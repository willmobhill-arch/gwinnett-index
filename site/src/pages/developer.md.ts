import type { APIRoute } from 'astro';
import { developers, stats, devSlug } from '../lib/source';
import { frontmatter, table, md } from '../lib/md';
import { abs, LICENCE } from '../lib/site';

export const GET: APIRoute = () => {
  const ds = [...developers()].sort((a, b) => b.total_cases - a.total_cases);
  const s = stats();
  return md(
    frontmatter({
      title: 'Developers — Gwinnett Index',
      jurisdiction: 'unincorporated-gwinnett',
      governing_jurisdiction: 'Unincorporated Gwinnett County',
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs('/developer'),
      licence: LICENCE,
    }) +
      `# Developers

Private-sector applicant activity in **unincorporated Gwinnett County**, ${s.first_year}–${s.last_year}.
The county's case layers contain no municipal filings, so work done inside any city's limits is
not represented here.

${s.applicant_variants?.toLocaleString('en-US')} raw applicant spellings were resolved to
${s.applicants?.toLocaleString('en-US')} entities. Government applicants and law firms are
excluded: filings routinely read \`PARAN HOMES, LLC C/O MAHAFFEY PICKENS TUCKER, LLP\`, and
counting the agent half would put a land-use firm at the top of a developer ranking.

**${s.merge_pending} name pairs remain queued for human review** rather than merged on a
similarity score, so every count below is a lower bound.

${table(
  ['Applicant', 'Cases', 'Since 2020', 'Years', 'Res units', 'Acres', 'Page'],
  ds.map((d) => [
    d.display_name, d.total_cases, d.cases_since_2020,
    `${d.first_year}–${d.last_year}`, d.res_units, d.acres,
    abs(`/developer/${devSlug(d.norm_name)}.md`),
  ])
)}
`
  );
};
