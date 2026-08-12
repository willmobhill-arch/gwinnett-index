import type { APIRoute } from 'astro';
import { routes } from '../lib/routes';
import { abs } from '../lib/site';

/**
 * changefreq and priority are deliberately omitted. Every major consumer
 * ignores them, and emitting a guess about how often a 1991 buffer-reduction
 * case changes is noise pretending to be metadata. lastmod is real: it is the
 * record's own last_verified or amended_through date.
 */
export const GET: APIRoute = () => {
  const body = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" ' +
      'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ...routes().flatMap((r) => [
      '  <url>',
      `    <loc>${abs(r.path === '/' ? '/' : r.path)}</loc>`,
      `    <lastmod>${r.lastmod}</lastmod>`,
      r.twin
        ? `    <xhtml:link rel="alternate" type="text/markdown" href="${abs(
            r.path === '/' ? '/index.md' : r.path + '.md'
          )}"/>`
        : '',
      '  </url>',
    ]).filter(Boolean),
    '</urlset>',
    '',
  ].join('\n');
  return new Response(body, {
    headers: { 'content-type': 'application/xml; charset=utf-8', 'access-control-allow-origin': '*' },
  });
};
