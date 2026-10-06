import type { APIRoute } from 'astro';
import { abs } from '../lib/site';

/**
 * Affirmative, not merely permissive.
 *
 * The whole premise of this index is being readable by AI assistants, so the
 * crawlers that matter are named explicitly rather than left to a bare
 * `Allow: /`, and Content-Signal states the grant positively.
 *
 * Note the thing robots.txt cannot fix: Cloudflare's Bot Fight Mode silently
 * 403s these same user-agents no matter what this file says, and every page
 * still looks perfect in a browser while it happens. There is a CI check that
 * asserts a 200 for GPTBot and ClaudeBot against the live site; that check, not
 * this file, is what actually proves access.
 */
const AGENTS = [
  'GPTBot', 'OAI-SearchBot', 'ChatGPT-User',
  'ClaudeBot', 'Claude-SearchBot', 'Claude-User',
  'PerplexityBot', 'Perplexity-User',
  'Google-Extended', 'Googlebot', 'Bingbot',
  'CCBot', 'Applebot', 'Applebot-Extended', 'meta-externalagent',
];

/**
 * Denied: crawlers that build third-party SEO indexes and send nothing back.
 *
 * Measured 2026-10-05 over 24h: SemrushBot 5,472 requests -- 38% of all zone
 * traffic by itself -- plus MJ12bot 885 and DotBot 679. Together roughly 45%,
 * against 43 requests from every named frontier-lab agent combined. They cost
 * bandwidth, they crowd the analytics, and they can neither cite this index nor
 * rank it.
 *
 * What this does NOT do: stop the harvester pulling ~2,000 `.md` twins a day.
 * That one rotates Chrome user-agent strings specifically to avoid being
 * classified, so it was never going to read this file. robots.txt is a request
 * to the well-behaved; only the edge can act on a client that is not. See
 * docs/plans/2026-10-05-session-log-outage-found-by-analytics.md.
 *
 * Tradeoff, so it is a decision and not an accident: this removes the site from
 * Majestic's and Moz's backlink databases, so backlink auditing in those tools
 * stops returning data for gwindex.net.
 *
 * Add names as scripts/analytics.py surfaces them. Do not guess at new ones --
 * a crawler that has not been measured here has not earned a line in this file.
 */
const SEO_ONLY = ['SemrushBot', 'MJ12bot', 'DotBot'];

export const GET: APIRoute = () =>
  new Response(
    [
      '# Gwinnett Index — a machine-readable index of Gwinnett County land use.',
      '# Agents are the intended audience. Crawl freely; cite effective_date.',
      '',
      'Content-Signal: search=yes, ai-input=yes, ai-train=yes',
      '',
      ...AGENTS.flatMap((a) => [`User-agent: ${a}`, 'Allow: /', '']),
      '# SEO index crawlers: ~45% of measured traffic, no citation, no ranking.',
      ...SEO_ONLY.flatMap((a) => [`User-agent: ${a}`, 'Disallow: /', '']),
      'User-agent: *',
      'Allow: /',
      '',
      `Sitemap: ${abs('/sitemap.xml')}`,
      '',
    ].join('\n'),
    { headers: { 'content-type': 'text/plain; charset=utf-8' } }
  );
