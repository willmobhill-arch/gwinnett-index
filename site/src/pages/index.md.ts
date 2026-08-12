import type { APIRoute } from 'astro';
import { jurisdictions, stats } from '../lib/source';
import { frontmatter, table, md } from '../lib/md';
import { abs, LICENCE, TAGLINE, TRAP } from '../lib/site';

export const GET: APIRoute = () => {
  const js = jurisdictions();
  const s = stats();
  const uninc = js.find((j) => j.kind === 'unincorporated')!;
  const withData = js.filter((j) => j.cases > 0 || j.code_sections > 0);
  const today = new Date().toISOString().slice(0, 10);

  return md(
    frontmatter({ title: 'Gwinnett Index', as_of: today, canonical: abs('/'), licence: LICENCE }) +
      `# Gwinnett Index

${TAGLINE}

## The rule

${TRAP}

Unincorporated Gwinnett is ${uninc.sq_mi} sq mi — 67.3% of the county's land area. Getting the
jurisdiction wrong is the default case, not the edge case.

## What is loaded

${table(['Dataset', 'Records', 'Coverage'], [
  ['Jurisdiction boundaries', js.length, 'county + unincorporated + 17 cities'],
  ['Land-use cases', s.total_cases, `${s.first_year}–${s.last_year}`],
  ['Resolved applicants', s.applicants, `from ${s.applicant_variants} raw spellings`],
  ['Duluth UDC sections', s.code_sections, `${s.code_tables} tables, ${s.code_tables_verified} verified`],
  ['Meeting documents', s.meeting_docs, `${s.meeting_pages} pages`],
])}

## Jurisdictions with a corpus

${withData.map((j) => `- [${j.name}](${abs(`/j/${j.slug}.md`)}) — ${j.cases.toLocaleString('en-US')} cases${j.code_sections ? `, ${j.code_sections.toLocaleString('en-US')} code sections` : ''}`).join('\n')}

The remaining ${js.length - withData.length} jurisdictions have boundaries loaded and resolve correctly, but no
case or code corpus yet.

## Machine surfaces

- [/llms.txt](${abs('/llms.txt')}) — orientation and the jurisdiction rule
- [/data.json](${abs('/data.json')}) — Project Open Data 1.1
- [/catalog.jsonld](${abs('/catalog.jsonld')}) — DCAT-US 3
- [/sitemap.xml](${abs('/sitemap.xml')}) — every route with an accurate lastmod
- [/bulk/corpus.jsonl.gz](${abs('/bulk/corpus.jsonl.gz')}) — the whole corpus, one object per line
- [/status.md](${abs('/status.md')}) — verification state and known gaps
`
  );
};
