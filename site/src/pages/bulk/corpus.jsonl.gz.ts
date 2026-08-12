import type { APIRoute } from 'astro';
import { gzipSync } from 'node:zlib';
import { jurisdictions, cases, codeSections, codeTables, developers } from '../../lib/source';

/**
 * The whole corpus, one JSON object per line, gzipped.
 *
 * Every line carries a `record` discriminator and its own provenance, so a
 * consumer that streams the file never has to hold the shape of the whole
 * archive in mind — and never ends up with a code section and a case record
 * indistinguishable from each other.
 *
 * No parcel or zoning geometry appears here, by licence: Gwinnett County GIS
 * forbids redistribution. Only Census TIGER-derived jurisdiction metadata and
 * factual case/code records are exported.
 */
export const GET: APIRoute = () => {
  const lines: string[] = [];
  const push = (record: string, o: object) => lines.push(JSON.stringify({ record, ...o }));

  for (const j of jurisdictions()) push('jurisdiction', j);
  for (const c of cases()) push('land_use_case', c);
  for (const s of codeSections()) push('code_section', s);
  for (const t of codeTables()) push('code_table', t);
  for (const d of developers()) push('developer', d);

  const gz = gzipSync(Buffer.from(lines.join('\n') + '\n', 'utf8'), { level: 9 });
  return new Response(gz, {
    headers: {
      'content-type': 'application/gzip',
      'content-disposition': 'attachment; filename="gwinnett-index-corpus.jsonl.gz"',
      'access-control-allow-origin': '*',
    },
  });
};
