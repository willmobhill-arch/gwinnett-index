import type { APIRoute, GetStaticPaths } from 'astro';
import { codeSections, codeTables, bySlug } from '../../../lib/source';
import { codeItems } from '../../../lib/routes';
import { frontmatter, facts, table as mdTable, md } from '../../../lib/md';
import { abs, LICENCE, TRAP } from '../../../lib/site';

// Same manifest as the HTML page, so the twin can never describe a different set
// of pages than the site does.
export const getStaticPaths: GetStaticPaths = () =>
  codeItems().map((it) => ({
    params: { jurisdiction: it.jurisdiction, cite: it.cite },
    props: { section: it.section, table: it.table },
  }));

export const GET: APIRoute = ({ props, params }) => {
  const section = (props as any).section as ReturnType<typeof codeSections>[number] | null;
  const tbl = (props as any).table as ReturnType<typeof codeTables>[number] | null;
  const item = section ?? tbl!;
  const j = bySlug(params.jurisdiction!)!;
  // Hand-verified range beats the prose parser's; see the .astro twin.
  const pageFrom = tbl?.page_from ?? section?.page_from;
  const pageTo = tbl?.page_to ?? section?.page_to;

  // Three states, not two. "defective" is a stronger claim than "unverified" — the
  // cells are known wrong rather than merely unchecked — and the note is emitted for
  // every state: Table 6-E's note records that the UDC cites a Table 6-D which does
  // not exist, and 6-E is defective, so gating the note on `verified` hid it.
  const note = tbl?.verification_note ? `>\n> ${tbl.verification_note}\n` : '';
  const warning = tbl
    ? tbl.quality === 'verified'
      ? `> **Verified.** Checked cell-by-cell against the rendered source page.\n${note}`
      : tbl.quality === 'defective'
        ? '> **CELL VALUES KNOWN WRONG — WITHHELD.** The header, column count and page range of\n' +
          '> this table have been checked against the rendered source page. The cell values came\n' +
          '> from an extractor that mis-assigned columns and are not published. This is stronger\n' +
          '> than "unverified": the numbers are known to be incorrect. Open the source page.\n' +
          note
        : '> **UNVERIFIED EXTRACTION.** This table was recovered from the PDF programmatically and\n' +
          '> has never been compared cell-by-cell against the rendered source page. Table extraction\n' +
          '> fails quietly: a value can land in the wrong column and still look plausible. Do not\n' +
          '> present these numbers as authoritative — open the source page.\n' +
          note
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
  ['Pages in source', `${pageFrom}${pageTo && pageTo !== pageFrom ? `–${pageTo}` : ''}`],
  ['Adopted', section?.adopted_date],
  ['Amended through', section?.amended_through],
  ['Source', item.source_url],
])}

${section?.body_md ? `## Text\n\n${section.body_md}\n` : ''}
${tbl?.spanning_header
  ? `**Spanning header:** ${tbl.spanning_header} — printed above and across the columns below.\n`
  : ''}
${tbl?.header && tbl.rows && tbl.rows.length
  ? `## Table\n\n${mdTable(tbl.header, tbl.rows)}\n`
  : tbl?.header
    ? `## Columns\n\n${tbl.header.map((h) => `- ${h}`).join('\n')}\n\n` +
      `The source page has ${tbl.n_rows} rows × ${tbl.n_cols} columns. ` +
      (tbl.quality === 'defective'
        ? 'The extracted cell values are known to be wrong and are withheld.'
        : 'The cell values have not been transcribed from the source page yet.') + '\n'
    : ''}`
  );
};
