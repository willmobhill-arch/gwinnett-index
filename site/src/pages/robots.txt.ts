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

export const GET: APIRoute = () =>
  new Response(
    [
      '# Gwinnett Index — a machine-readable index of Gwinnett County land use.',
      '# Agents are the intended audience. Crawl freely; cite effective_date.',
      '',
      'Content-Signal: search=yes, ai-input=yes, ai-train=yes',
      '',
      ...AGENTS.flatMap((a) => [`User-agent: ${a}`, 'Allow: /', '']),
      'User-agent: *',
      'Allow: /',
      '',
      `Sitemap: ${abs('/sitemap.xml')}`,
      '',
    ].join('\n'),
    { headers: { 'content-type': 'text/plain; charset=utf-8' } }
  );
