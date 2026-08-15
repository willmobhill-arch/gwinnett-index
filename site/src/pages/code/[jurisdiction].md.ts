import type { APIRoute, GetStaticPaths } from 'astro';
import { codeSections, codeTables, jurisdictions } from '../../lib/source';
import { frontmatter, md } from '../../lib/md';
import { abs, LICENCE, TRAP } from '../../lib/site';
import { codeSlug, tableSlug } from '../../lib/format';

export const getStaticPaths: GetStaticPaths = () => {
  const withCode = new Set([...codeSections(), ...codeTables()].map((x) => x.jurisdiction));
  return jurisdictions().filter((j) => withCode.has(j.slug)).map((j) => ({ params: { jurisdiction: j.slug }, props: { j } }));
};

export const GET: APIRoute = ({ props }) => {
  const j = (props as any).j as ReturnType<typeof jurisdictions>[number];
  const secs = codeSections().filter((s) => s.jurisdiction === j.slug && s.kind !== 'table');
  const tabs = codeTables().filter((t) => t.jurisdiction === j.slug);
  const adopted = secs[0]?.adopted_date ?? undefined;
  const amended = secs[0]?.amended_through ?? undefined;

  return md(
    frontmatter({
      title: `${j.code_citation ?? j.name + ' development code'} — Gwinnett Index`,
      jurisdiction: j.slug,
      governing_jurisdiction: j.name,
      source_url: secs[0]?.source_url,
      effective_date: amended ?? adopted,
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs(`/code/${j.slug}`),
      licence: LICENCE,
    }) +
      `# ${j.code_citation ?? `${j.name} development code`}

**Governing jurisdiction: ${j.name}.** ${TRAP}

Adopted ${adopted ?? 'unknown'}, amended through ${amended ?? 'unknown'}. Ordinance text is
mirrored in full — an edict of government carries no copyright (*Georgia v.
Public.Resource.Org*, 2020). Cite the effective date with any figure taken from here.

${tabs.length ? `## Tables\n\n${tabs.map((t) => `- [${t.citation}](${abs(`/code/${j.slug}/${tableSlug(t)}.md`)}) — ${t.title}${t.quality === 'verified' ? ' (verified cell-for-cell against the rendered page)' : t.quality === 'defective' ? ' (header verified; CELL VALUES KNOWN WRONG, withheld)' : ' (UNVERIFIED extraction)'}`).join('\n')}\n` : ''}
## Sections

${secs.map((s) => `- [${s.citation}](${abs(`/code/${j.slug}/${codeSlug(s.citation)}.md`)}) — ${s.title ?? ''}`).join('\n')}
`
  );
};
