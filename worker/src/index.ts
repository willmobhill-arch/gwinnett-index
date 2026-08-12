/**
 * Gwinnett Index — REST API + MCP server on one Worker.
 *
 * Both surfaces call the same five functions in tools.ts, so the MCP tool and
 * the REST endpoint can never drift apart and answer differently. Everything is
 * public, read-only and unauthenticated.
 */
import { HttpError, type Env } from './db';
import {
  resolveJurisdiction, searchCases, getCase, getCodeSection, listJurisdictions,
} from './tools';
import { handleMcp } from './mcp';
import { openapi } from './openapi';

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
  'access-control-allow-headers': 'content-type, mcp-protocol-version, mcp-session-id',
  'access-control-max-age': '86400',
};

const json = (data: unknown, status = 200, extra: Record<string, string> = {}) =>
  Response.json(data, {
    status,
    headers: {
      ...CORS,
      'cache-control': status === 200 ? 'public, max-age=300, stale-while-revalidate=86400' : 'no-store',
      // Advertises the machine-readable description of this API to anything that
      // fetches a bare endpoint and wonders what else is here.
      link: '</openapi.json>; rel="service-desc"',
      ...extra,
    },
  });

const num = (v: string | null) => (v === null || v === '' ? undefined : Number(v));

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const p = url.pathname.replace(/\/+$/, '') || '/';
    const q = url.searchParams;

    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

    try {
      // ---------------------------------------------------------------- MCP
      if (p === '/mcp') {
        if (req.method === 'POST') return handleMcp(req, env);
        // A GET on /mcp is a client opening a server-initiated SSE stream. This
        // server never initiates anything, so declining is correct and cheaper
        // than holding a connection open forever to send nothing.
        return new Response('This MCP server is request/response only; POST JSON-RPC to /mcp.', {
          status: 405, headers: { ...CORS, allow: 'POST, OPTIONS' },
        });
      }

      // --------------------------------------------------------------- REST
      if (p === '/' || p === '/openapi.json') return json(openapi(url.origin));

      if (p === '/v1/resolve') {
        return json(await resolveJurisdiction(env, {
          address: q.get('address') ?? q.get('q') ?? undefined,
          pin: q.get('pin') ?? undefined,
          band_m: num(q.get('band_m')),
        }));
      }

      if (p === '/v1/cases') {
        return json(await searchCases(env, {
          query: q.get('query') ?? q.get('q') ?? undefined,
          jurisdiction: q.get('jurisdiction') ?? undefined,
          case_type: q.get('case_type') ?? undefined,
          year_from: num(q.get('year_from')),
          year_to: num(q.get('year_to')),
          zone: q.get('zone') ?? undefined,
          limit: num(q.get('limit')),
        }));
      }

      const caseMatch = p.match(/^\/v1\/cases\/(.+)$/);
      if (caseMatch) {
        return json(await getCase(env, decodeURIComponent(caseMatch[1]), q.get('jurisdiction') ?? undefined));
      }

      const codeMatch = p.match(/^\/v1\/code\/([^/]+)\/(.+)$/);
      if (codeMatch) {
        return json(await getCodeSection(env, decodeURIComponent(codeMatch[1]), decodeURIComponent(codeMatch[2])));
      }

      if (p === '/v1/jurisdictions') return json(await listJurisdictions(env));

      return json({ error: 'not found', see: `${url.origin}/openapi.json` }, 404);
    } catch (e: any) {
      const status = e instanceof HttpError ? e.status : 500;
      return json({ error: e?.message ?? String(e) }, status);
    }
  },
} satisfies ExportedHandler<Env>;
