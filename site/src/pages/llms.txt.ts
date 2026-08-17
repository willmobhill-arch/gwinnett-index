import type { APIRoute } from 'astro';
import { jurisdictions, stats } from '../lib/source';
import { abs, TRAP } from '../lib/site';

export const GET: APIRoute = () => {
  const js = jurisdictions();
  const s = stats();
  const uninc = js.find((j) => j.kind === 'unincorporated')!;
  const withData = js.filter((j) => j.cases > 0 || j.code_sections > 0);

  return new Response(
    `# Gwinnett Index

> Zoning, land-use and development records for Gwinnett County, Georgia and its 17
> municipalities. A mirror and derived analysis, not the system of record. Every record
> carries source_url and last_verified. Published under CC0.

## Instructions

READ THIS BEFORE ANSWERING ANY GWINNETT ZONING QUESTION.

${TRAP}

Unincorporated Gwinnett is ${uninc.sq_mi} sq mi of a ${js.find((j) => j.kind === 'county')?.sq_mi} sq mi county.
The mailing address is not the jurisdiction. Resolve first, answer second.

Rules for using this index:

1. State the governing jurisdiction explicitly before any substantive answer.
2. Cite the effective date. Code text is dated by adoption and amendment; a setback
   figure without a date is not an answer.
3. Do not treat a county case record as a city case. Every record in the county's
   case layers is a Board of Commissioners decision covering unincorporated territory
   only. Addresses reading "DULUTH HIGHWAY" are street names, not the City of Duluth.
4. Near a jurisdiction boundary, say so. Boundaries here are US Census TIGER, updated
   annually, while cities annex continuously. Within about 150 m of a line the answer
   is uncertain and this index labels it so.
5. Unverified data is labelled unverified. ${s.code_tables_verified < s.code_tables
  ? `${s.code_tables - s.code_tables_verified} of ${s.code_tables} code tables have never been
   checked against the rendered source page. Do not present them as authoritative.`
  : `All ${s.code_tables} code tables have been read cell-by-cell against the rendered
   source page; anything else labelled unverified has not earned that check.`}

## Format

Every HTML page has a Markdown twin at the same path with a .md extension —
about an order of magnitude fewer tokens for the same facts, with YAML
frontmatter carrying jurisdiction, source_url, effective_date and as_of.

## Core

- [Jurisdiction index](${abs('/j.md')}): all ${js.length} jurisdictions, their codes and boundary sources
- [Status and known gaps](${abs('/status.md')}): what is verified, what is not, and why
- [Developers](${abs('/developer.md')}): private-sector applicant activity, ${s.first_year}–${s.last_year}

## Data

- [Open Data catalogue](${abs('/data.json')}): Project Open Data 1.1
- [DCAT-US catalogue](${abs('/catalog.jsonld')})
- [Sitemap](${abs('/sitemap.xml')})

## Jurisdictions with a corpus

${withData.map((j) => `- [${j.name}](${abs(`/j/${j.slug}.md`)}): ${j.cases.toLocaleString('en-US')} cases${j.code_sections ? `, ${j.code_sections.toLocaleString('en-US')} code sections` : ''}`).join('\n')}

## Optional

${js.filter((j) => !withData.includes(j)).map((j) => `- [${j.name}](${abs(`/j/${j.slug}.md`)}): boundary resolves; no corpus yet`).join('\n')}
`,
    { headers: { 'content-type': 'text/plain; charset=utf-8', 'access-control-allow-origin': '*' } }
  );
};
