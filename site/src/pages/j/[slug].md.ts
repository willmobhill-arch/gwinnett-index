import type { APIRoute, GetStaticPaths } from 'astro';
import { jurisdictions, casesFor, codeTables } from '../../lib/source';
import { frontmatter, facts, table, md } from '../../lib/md';
import { abs, LICENCE, TRAP } from '../../lib/site';
import { tableSlug, rawCode, zone } from '../../lib/format';

export const getStaticPaths: GetStaticPaths = () =>
  jurisdictions().map((j) => ({ params: { slug: j.slug }, props: { j } }));

export const GET: APIRoute = ({ props }) => {
  const j = (props as any).j as ReturnType<typeof jurisdictions>[number];
  const cs = [...casesFor(j.slug)].sort((a, b) => (b.year ?? 0) - (a.year ?? 0)).slice(0, 25);
  const tabs = codeTables().filter((t) => t.jurisdiction === j.slug);

  const note =
    j.kind === 'unincorporated'
      ? 'Every case below is a Board of Commissioners decision. Records whose address reads ' +
        '"DULUTH HIGHWAY" or "OLD DULUTH ROAD" are street names in unincorporated territory — ' +
        'they are not City of Duluth cases and must never be attributed to a municipality.'
      : j.kind === 'county'
        ? 'This is the county container boundary, used for area accounting. It is not itself a ' +
          'governing jurisdiction.'
        : `${/^[AEIOU]/.test(j.name) ? 'An' : 'A'} "${j.name}, GA" mailing address is not proof of ` +
          `being inside ${j.name}. Most such ` +
          'addresses fall in unincorporated Gwinnett.';

  return md(
    frontmatter({
      title: `${j.name} — Gwinnett Index`,
      jurisdiction: j.slug,
      governing_jurisdiction: j.name,
      source_url: j.code_url ?? undefined,
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs(`/j/${j.slug}`),
      licence: LICENCE,
    }) +
      `# ${j.name}

**Governing jurisdiction: ${j.name}.** ${TRAP}

${note}

## Facts

${facts([
  ['Kind', j.kind],
  ['Land area', j.sq_mi ? `${j.sq_mi} sq mi` : null],
  ['Code', j.code_citation ?? 'not indexed here'],
  ['Code URL', j.code_url],
  ['Case records', `${j.cases.toLocaleString('en-US')}${j.first_year ? ` (${j.first_year}–${j.last_year})` : ''}`],
  ['Code sections', j.code_sections],
  ['Boundary source', j.boundary_source],
  ['Boundary vintage', j.boundary_vintage],
  ['FIPS place', j.fips_place],
])}

${tabs.length ? `## Code tables\n\n${tabs.map((t) => `- [${t.citation}](${abs(`/code/${j.slug}/${tableSlug(t)}.md`)}) — ${t.title}${t.quality === 'verified' ? ' (verified)' : t.quality === 'defective' ? ' (header verified; CELL VALUES KNOWN WRONG, withheld)' : ' (UNVERIFIED extraction — do not rely on these numbers)'}`).join('\n')}\n` : ''}
${cs.length ? `## Recent cases\n\n${table(
  ['Case', 'Year', 'Applicant', 'Zoning', 'Decision', 'Page'],
  cs.map((c) => [
    c.case_number, c.year, c.applicant_raw,
    `${zone(c.existing_zone)}${c.proposed_zone && c.proposed_zone !== 'NA' ? ` → ${c.proposed_zone}` : ''}`,
    rawCode(c.decision),
    abs(`/case/${c.jurisdiction}/${encodeURIComponent(c.case_number)}.md`),
  ])
)}\n\nShowing ${cs.length} of ${j.cases.toLocaleString('en-US')}.` : ''}

## Related

- [Per-jurisdiction llms.txt](${abs(`/j/${j.slug}/llms.txt`)})
${j.code_sections ? `- [Code index](${abs(`/code/${j.slug}.md`)})` : ''}
`
  );
};
