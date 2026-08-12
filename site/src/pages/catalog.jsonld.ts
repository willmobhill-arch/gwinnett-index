import type { APIRoute } from 'astro';
import { stats } from '../lib/source';
import { abs, TAGLINE } from '../lib/site';

/** DCAT-US 3 / DCAT 3, for harvesters that speak RDF rather than POD 1.1. */
export const GET: APIRoute = () => {
  const s = stats();
  const now = new Date().toISOString();
  return new Response(
    JSON.stringify(
      {
        '@context': { '@vocab': 'http://www.w3.org/ns/dcat#', dct: 'http://purl.org/dc/terms/' },
        '@type': 'Catalog',
        '@id': abs('/catalog.jsonld'),
        'dct:title': 'Gwinnett Index',
        'dct:description': TAGLINE,
        'dct:license': 'https://creativecommons.org/publicdomain/zero/1.0/',
        'dct:modified': now,
        'dct:spatial': 'https://www.geonames.org/4197000/gwinnett-county.html',
        dataset: [
          {
            '@type': 'Dataset',
            '@id': abs('/#land-use-cases'),
            'dct:title': 'Gwinnett land-use and zoning cases',
            'dct:temporal': `${s.first_year}/${s.last_year}`,
            'dct:source': 'https://gis3.gwinnettcounty.com/mapvis/rest/services/GISDataBrowser/GC_Planning/MapServer',
            distribution: [
              { '@type': 'Distribution', downloadURL: abs('/bulk/corpus.jsonl.gz'), mediaType: 'application/gzip' },
            ],
          },
          {
            '@type': 'Dataset',
            '@id': abs('/#jurisdictions'),
            'dct:title': 'Jurisdiction boundaries and governing authority',
            'dct:source': 'https://www2.census.gov/geo/tiger/',
          },
          {
            '@type': 'Dataset',
            '@id': abs('/#duluth-udc'),
            'dct:title': 'City of Duluth Unified Development Code',
            'dct:source': 'https://www.duluthga.net/',
          },
        ],
      },
      null,
      2
    ),
    { headers: { 'content-type': 'application/ld+json; charset=utf-8', 'access-control-allow-origin': '*' } }
  );
};
