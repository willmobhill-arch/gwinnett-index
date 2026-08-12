import type { APIRoute, GetStaticPaths } from 'astro';
import { developers, devSlug } from '../../lib/source';
import { frontmatter, facts, md } from '../../lib/md';
import { abs, LICENCE } from '../../lib/site';

export const getStaticPaths: GetStaticPaths = () =>
  developers().map((d) => ({ params: { slug: devSlug(d.norm_name) }, props: { d } }));

export const GET: APIRoute = ({ props }) => {
  const d = (props as any).d as ReturnType<typeof developers>[number];
  const rate =
    d.approved !== null && d.denied !== null && d.approved + d.denied > 0
      ? `${Math.round((d.approved / (d.approved + d.denied)) * 100)}% approved`
      : null;
  return md(
    frontmatter({
      title: `${d.display_name} — Gwinnett Index`,
      jurisdiction: 'unincorporated-gwinnett',
      governing_jurisdiction: 'Unincorporated Gwinnett County',
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs(`/developer/${devSlug(d.norm_name)}`),
      licence: LICENCE,
    }) +
      `# ${d.display_name}

**Governing jurisdiction: Unincorporated Gwinnett County.** These counts cover unincorporated
territory only — the county's case layers contain no municipal filings.

${facts([
  ['Total cases', d.total_cases],
  ['Since 2020', d.cases_since_2020],
  ['Active span', `${d.first_year}–${d.last_year} (${d.span_years} years)`],
  ['Residential units proposed', d.res_units],
  ['Acres', d.acres],
  ['Non-residential sq ft', d.nonres_sqft],
  ['Approved / denied', `${d.approved} / ${d.denied}${rate ? ` (${rate})` : ''}`],
  ['Name spellings merged', d.name_variants],
])}
`
  );
};
