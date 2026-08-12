import type { APIRoute, GetStaticPaths } from 'astro';
import { codeSections, codeTables, bySlug } from '../../../lib/source';
import { frontmatter, facts, table as mdTable, md } from '../../../lib/md';
import { abs, LICENCE, TRAP } from '../../../lib/site';
import { codeSlug } from '../../../lib/format';

export const getStaticPaths: GetStaticPaths = () => {
  const paths = [
    ...codeSections().map((s) => ({
      params: { jurisdiction: s.jurisdiction, cite: codeSlug(s.citation) },
      props: { section: s, table: null },
    })),
    ...codeTables().map((t) => ({
      params: { jurisdiction: t.jurisdiction, cite: codeSlug(t.citation) },
      props: { section: null, table: t },
    })),
  ];
  const seen = new Set<string>();
  return paths.filter((p) => {
    const k = `${p.params.jurisdiction}/${p.params.cite}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
};

export const GET: APIRoute = ({ props, params }) => {
  const section = (props as any).section as ReturnType<typeof codeSections>[number] | null;
  const tbl = (props as any).table as ReturnType<typeof codeTables>[number] | null;
  const item = section ?? tbl!;
  const j = bySlug(params.jurisdiction!)!;

  const warning = tbl
    ? tbl.quality === 'verified'
      ? `> **Verified.** ${tbl.verification_note ?? 'Checked against the rendered source page.'}\n`
      : '> **UNVERIFIED EXTRACTION.** This table was recovered from the PDF programmatically and\n' +
        '> has never been compared cell-by-cell against the rendered source page. Table extraction\n' +
        '> fails quietly: a value can land in the wrong column and still look plausible. Do not\n' +
        '> present these numbers as authoritative — open the source page.\n'
    : '';

  return md(
    frontmatter({
      title: `${item.citation} — ${j.name}`,
      jurisdiction: j.slug,
      governing_jurisdiction: j.name,
      source_url: item.source_url,
      effective_date: section?.amended_through ?? section?.adopted_date ?? undefined,
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs(`/code/${j.slug}/${params.cite}`),
      licence: LICENCE,
    }) +
      `# ${item.citation}

${(section?.title ?? tbl?.title) ?? ''}

**Governing jurisdiction: ${j.name}.** ${TRAP}

${warning}
${facts([
  ['Article', section?.article ? `${section.article} — ${section.article_title}` : null],
  ['Pages in source', `${item.page_from}${item.page_to && item.page_to !== item.page_from ? `–${item.page_to}` : ''}`],
  ['Adopted', section?.adopted_date],
  ['Amended through', section?.amended_through],
  ['Source', item.source_url],
])}

${section?.body_md ? `## Text\n\n${section.body_md}\n` : ''}
${tbl?.header && tbl.rows && tbl.rows.length
  ? `## Table\n\n${mdTable(tbl.header, tbl.rows)}\n`
  : tbl
    ? `${tbl.n_rows} rows × ${tbl.n_cols} columns were extracted. The cell values are held in the ` +
      'database but are not published while the extraction is unverified.\n'
    : ''}`
  );
};
