/**
 * MCP over Streamable HTTP. No auth, no session state, no SSE stream required —
 * a plain POST of JSON-RPC in, JSON out. Every credential requirement is a
 * client that will not connect, and this is public-record data.
 */
import { type Env } from './db';
import {
  resolveJurisdiction, searchCases, getCase, getCodeSection, listJurisdictions,
  JURISDICTION_RULE,
} from './tools';

const PROTOCOL = '2025-06-18';

/**
 * `instructions` is loaded into the client's context on connect, before any tool
 * is called. It is the only place to put a rule that has to hold even when the
 * model decides not to call a tool at all — which is exactly the failure this
 * whole index exists to prevent.
 */
const INSTRUCTIONS = `Gwinnett Index — zoning and land use for Gwinnett County, Georgia.

ALWAYS CALL resolve_jurisdiction FIRST for any address, parcel or place in Gwinnett County,
before answering anything about zoning, setbacks, permitted uses or process.

${JURISDICTION_RULE}

When you answer:
- State the governing jurisdiction explicitly, before the substance.
- Cite the effective_date of any code text. A setback figure without a date is not an answer.
- If confidence is "low", say so. It means the point is within ~150 m of a jurisdiction
  boundary, where annexation lag makes the answer genuinely uncertain.
- Never present a county case record as a city case. County records are Board of
  Commissioners decisions covering unincorporated territory only.
- Never present data marked UNVERIFIED as authoritative.

Every response carries source_url and as_of. Pass them through to the user.`;

const TOOLS = [
  {
    name: 'resolve_jurisdiction',
    title: 'Resolve governing jurisdiction — ALWAYS CALL FIRST',
    description:
      'ALWAYS CALL THIS FIRST for any Gwinnett County address or parcel. Returns which ' +
      'government actually regulates the land — one of 17 cities, or unincorporated Gwinnett ' +
      'County (67.3% of the county) — with its code citation, a confidence band and the ' +
      'distance to the nearest jurisdiction boundary. A mailing address is NOT the ' +
      'jurisdiction: most "Duluth, GA" addresses are not in the City of Duluth.',
    inputSchema: {
      type: 'object',
      properties: {
        address: { type: 'string', description: 'Street address, e.g. "3175 Peachtree Industrial Blvd, Duluth GA"' },
        pin: { type: 'string', description: 'Gwinnett parcel PIN, e.g. "7119 100"' },
        band_m: { type: 'number', description: 'Uncertainty band in metres (default 150)' },
      },
    },
  },
  {
    name: 'search_cases',
    title: 'Search land-use cases',
    description:
      'Search 11,848 zoning and land-use cases (1970–2026) by applicant, use, address, case ' +
      'number, type, year range or zoning district. County records cover UNINCORPORATED ' +
      'Gwinnett only.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Free text: applicant, proposed use, address or case number' },
        jurisdiction: { type: 'string', description: 'Jurisdiction slug, e.g. "unincorporated-gwinnett" or "duluth"' },
        case_type: { type: 'string', description: 'REZ, SUP, RZC, RZR, RZM, CIC, MIH, CRZ, BRD …' },
        year_from: { type: 'integer' },
        year_to: { type: 'integer' },
        zone: { type: 'string', description: 'Zoning district, e.g. "R-100", "C-2", "R-TH"' },
        limit: { type: 'integer', description: '1–100, default 25' },
      },
    },
  },
  {
    name: 'get_case',
    title: 'Get one land-use case',
    description:
      'Full record for a case number, including staff recommendation, Planning Commission ' +
      'recommendation, decision, parcels and a deep link to the source record.',
    inputSchema: {
      type: 'object',
      properties: {
        case_number: { type: 'string', description: 'e.g. "REZ2025-00025"' },
        jurisdiction: { type: 'string', description: 'Disambiguates if the number exists in more than one jurisdiction' },
      },
      required: ['case_number'],
    },
  },
  {
    name: 'get_code_section',
    title: 'Get a development code section or table',
    description:
      'Ordinance text or a dimensional-standards table by citation, with its adoption and ' +
      'amendment dates. Accepts "402.03", "§ 402.03", "Duluth UDC § 402.03" or "Table 2-B". ' +
      'Tables that have not been verified against the rendered source page say so in the response.',
    inputSchema: {
      type: 'object',
      properties: {
        jurisdiction: { type: 'string', description: 'Jurisdiction slug, e.g. "duluth"' },
        citation: { type: 'string', description: 'e.g. "402.03" or "Table 2-B"' },
      },
      required: ['jurisdiction', 'citation'],
    },
  },
  {
    name: 'list_jurisdictions',
    title: 'List jurisdictions',
    description:
      'All 19 jurisdictions indexed: Gwinnett County as a container, unincorporated Gwinnett ' +
      'as a jurisdiction in its own right, and the 17 municipalities — with their codes and ' +
      'boundary sources.',
    inputSchema: { type: 'object', properties: {} },
  },
];

type Json = Record<string, any>;
const ok = (id: unknown, result: Json) => ({ jsonrpc: '2.0', id, result });
const err = (id: unknown, code: number, message: string) => ({ jsonrpc: '2.0', id, error: { code, message } });

async function call(env: Env, name: string, args: Json) {
  switch (name) {
    case 'resolve_jurisdiction': return resolveJurisdiction(env, args);
    case 'search_cases':         return searchCases(env, args);
    case 'get_case':             return getCase(env, args.case_number, args.jurisdiction);
    case 'get_code_section':     return getCodeSection(env, args.jurisdiction, args.citation);
    case 'list_jurisdictions':   return listJurisdictions(env);
    default: throw new Error(`unknown tool "${name}"`);
  }
}

export async function handleMcp(req: Request, env: Env): Promise<Response> {
  let body: Json;
  try {
    body = await req.json();
  } catch {
    return Response.json(err(null, -32700, 'parse error'), { status: 400 });
  }

  const batch = Array.isArray(body) ? body : [body];
  const out: Json[] = [];

  for (const m of batch) {
    const { id, method, params } = m ?? {};
    const isNotification = id === undefined || id === null;

    try {
      if (method === 'initialize') {
        out.push(ok(id, {
          protocolVersion: PROTOCOL,
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: 'gwinnett-index', version: '0.1.0', title: 'Gwinnett Index' },
          instructions: INSTRUCTIONS,
        }));
      } else if (method === 'notifications/initialized' || method === 'notifications/cancelled') {
        // nothing to acknowledge
      } else if (method === 'ping') {
        out.push(ok(id, {}));
      } else if (method === 'tools/list') {
        out.push(ok(id, { tools: TOOLS }));
      } else if (method === 'tools/call') {
        const result = await call(env, params?.name, params?.arguments ?? {});
        out.push(ok(id, {
          content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
          structuredContent: result,
          isError: false,
        }));
      } else if (isNotification) {
        // unknown notification: ignore, per JSON-RPC
      } else {
        out.push(err(id, -32601, `method not found: ${method}`));
      }
    } catch (e: any) {
      // A tool failure is reported as a tool result, not a protocol error: the
      // model should see "no parcel found for that PIN" and adapt, not receive
      // a transport-level failure it cannot reason about.
      if (method === 'tools/call') {
        out.push(ok(id, {
          content: [{ type: 'text', text: `Error: ${e?.message ?? String(e)}` }],
          isError: true,
        }));
      } else if (!isNotification) {
        out.push(err(id, -32603, e?.message ?? String(e)));
      }
    }
  }

  if (!out.length) return new Response(null, { status: 202 });
  return Response.json(Array.isArray(body) ? out : out[0], {
    headers: { 'access-control-allow-origin': '*' },
  });
}

export const mcpTools = TOOLS;
