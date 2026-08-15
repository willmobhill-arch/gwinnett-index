import type { APIRoute } from 'astro';
import { stats, jurisdictions } from '../lib/source';
import { abs, TAGLINE } from '../lib/site';

/** Project Open Data 1.1 — the schema US federal and many local catalogues harvest. */
export const GET: APIRoute = () => {
  const s = stats();
  const modified = new Date().toISOString().slice(0, 10);
  const publisher = { name: 'Gwinnett Index' };
  const contactPoint = { '@type': 'vcard:Contact', fn: 'Gwinnett Index', hasEmail: 'mailto:index@example.invalid' };

  const dataset = (o: Record<string, unknown>) => ({
    '@type': 'dcat:Dataset',
    accessLevel: 'public',
    license: 'https://creativecommons.org/publicdomain/zero/1.0/',
    publisher, contactPoint, modified,
    spatial: 'Gwinnett County, Georgia',
    ...o,
  });

  return new Response(
    JSON.stringify(
      {
        '@context': 'https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld',
        '@type': 'dcat:Catalog',
        conformsTo: 'https://project-open-data.cio.gov/v1.1/schema',
        describedBy: 'https://project-open-data.cio.gov/v1.1/schema/catalog.json',
        dataset: [
          dataset({
            identifier: abs('/#land-use-cases'),
            title: 'Gwinnett land-use and zoning cases',
            description:
              `${s.total_cases?.toLocaleString('en-US')} land-use and zoning case records, ${s.first_year}–${s.last_year}. ` +
              `${s.county_cases?.toLocaleString('en-US')} are Board of Commissioners decisions covering unincorporated ` +
              'Gwinnett only — municipal cases are not in that source. ' +
              `${s.duluth_cases} City of Duluth records are derived from meeting documents.`,
            keyword: ['zoning', 'land use', 'rezoning', 'Gwinnett County', 'Georgia', 'planning'],
            temporal: `${s.first_year}-01-01/${s.last_year}-12-31`,
            distribution: [
              { '@type': 'dcat:Distribution', downloadURL: abs('/bulk/corpus.jsonl.gz'), mediaType: 'application/gzip', format: 'JSONL (gzip)' },
              { '@type': 'dcat:Distribution', accessURL: abs('/j'), mediaType: 'text/html', format: 'HTML' },
            ],
          }),
          dataset({
            identifier: abs('/#jurisdictions'),
            title: 'Gwinnett County jurisdiction boundaries and governing authority',
            description:
              `${jurisdictions().length} jurisdictions: Gwinnett County, unincorporated Gwinnett derived as the county ` +
              'minus the union of all 17 incorporated places, and the 17 municipalities. Boundaries are US Census ' +
              'TIGER, public domain. No Gwinnett County GIS geometry is redistributed.',
            keyword: ['jurisdiction', 'boundaries', 'municipal limits', 'unincorporated', 'TIGER'],
            distribution: [{ '@type': 'dcat:Distribution', accessURL: abs('/j'), mediaType: 'text/html', format: 'HTML' }],
          }),
          dataset({
            identifier: abs('/#duluth-udc'),
            title: 'City of Duluth Unified Development Code',
            description:
              `${s.code_sections} sections and ${s.code_tables} tables extracted from the adopted UDC PDF. ` +
              `${s.code_tables_verified} table has been verified cell-for-cell against the rendered source page; ` +
              'the rest are labelled unverified.',
            keyword: ['zoning code', 'development code', 'ordinance', 'Duluth', 'setbacks'],
            distribution: [{ '@type': 'dcat:Distribution', accessURL: abs('/code/duluth'), mediaType: 'text/html', format: 'HTML' }],
          }),
        ],
      },
      null,
      2
    ),
    { headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*' } }
  );
};
