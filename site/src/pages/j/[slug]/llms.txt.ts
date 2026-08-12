import type { APIRoute, GetStaticPaths } from 'astro';
import { jurisdictions, casesFor, codeSections, codeTables } from '../../../lib/source';
import { abs, TRAP } from '../../../lib/site';
import { codeSlug } from '../../../lib/format';

export const getStaticPaths: GetStaticPaths = () =>
  jurisdictions().map((j) => ({ params: { slug: j.slug }, props: { j } }));

export const GET: APIRoute = ({ props }) => {
  const j = (props as any).j as ReturnType<typeof jurisdictions>[number];
  const cs = casesFor(j.slug);
  const secs = codeSections().filter((s) => s.jurisdiction === j.slug);
  const tabs = codeTables().filter((t) => t.jurisdiction === j.slug);
  const years = cs.length ? `${j.first_year}–${j.last_year}` : 'none';

  return new Response(
    `# ${j.name}

> ${j.kind === 'unincorporated'
    ? 'Unincorporated territory governed by Gwinnett County, not by any city. This is 67.3% of the county.'
    : j.kind === 'county'
      ? 'County container boundary. Not itself a governing jurisdiction.'
      : `Incorporated municipality in Gwinnett County, Georgia. Land inside these limits is governed by ${j.name}'s own code and boards.`}

## Instructions

${TRAP}

For this jurisdiction specifically: ${j.kind === 'municipality'
  ? `a "${j.name}, GA" mailing address is not evidence of being inside ${j.name}. Confirm the parcel is within the city limits before applying this code.`
  : j.kind === 'unincorporated'
    ? 'these records are Board of Commissioners decisions. Street names containing a city name are not city cases.'
    : 'resolve to a municipality or to unincorporated Gwinnett before answering.'}

## Facts

- Kind: ${j.kind}
- Land area: ${j.sq_mi ?? 'unknown'} sq mi
- Code: ${j.code_citation ?? 'not indexed here'}${j.code_url ? ` (${j.code_url})` : ''}
- Case records: ${cs.length ? cs.length.toLocaleString('en-US') : j.cases.toLocaleString('en-US')}, ${years}
- Code sections indexed: ${j.code_sections.toLocaleString('en-US')}
- Boundary: ${j.boundary_source ?? 'unknown'}${j.boundary_vintage ? `, vintage ${j.boundary_vintage}` : ''}

## Pages

- [Jurisdiction page](${abs(`/j/${j.slug}.md`)})
${j.code_sections ? `- [Code index](${abs(`/code/${j.slug}.md`)})\n` : ''}${tabs.map((t) => `- [${t.citation}](${abs(`/code/${j.slug}/${codeSlug(t.citation)}.md`)}): ${t.title}${t.quality === 'verified' ? ' (verified)' : ' (UNVERIFIED extraction)'}`).join('\n')}
${secs.slice(0, 20).map((s) => `- [${s.citation}](${abs(`/code/${j.slug}/${codeSlug(s.citation)}.md`)}): ${s.title ?? ''}`).join('\n')}
`,
    { headers: { 'content-type': 'text/plain; charset=utf-8', 'access-control-allow-origin': '*' } }
  );
};
