import { mcpTools } from './mcp';
import { JURISDICTION_RULE } from './tools';

export const openapi = (origin: string) => ({
  openapi: '3.1.0',
  info: {
    title: 'Gwinnett Index API',
    version: '0.1.0',
    summary: 'Which government actually regulates this parcel, and what has been filed on it.',
    description:
      `${JURISDICTION_RULE}\n\nPublic, read-only, unauthenticated. Every response carries ` +
      'source_url and as_of. An MCP server exposing the same five operations is at ' +
      `${origin}/mcp (Streamable HTTP, no auth).`,
    license: { name: 'CC0-1.0', url: 'https://creativecommons.org/publicdomain/zero/1.0/' },
  },
  servers: [{ url: origin }],
  paths: {
    '/v1/resolve': {
      get: {
        operationId: 'resolveJurisdiction',
        summary: 'Resolve an address or PIN to its governing jurisdiction. CALL THIS FIRST.',
        parameters: [
          { name: 'address', in: 'query', schema: { type: 'string' } },
          { name: 'pin', in: 'query', schema: { type: 'string' } },
          { name: 'band_m', in: 'query', schema: { type: 'number', default: 150 } },
        ],
        responses: { '200': { description: 'Governing jurisdiction with a confidence band' } },
      },
    },
    '/v1/cases': {
      get: {
        operationId: 'searchCases',
        summary: 'Search land-use cases',
        parameters: [
          { name: 'query', in: 'query', schema: { type: 'string' } },
          { name: 'jurisdiction', in: 'query', schema: { type: 'string' } },
          { name: 'case_type', in: 'query', schema: { type: 'string' } },
          { name: 'year_from', in: 'query', schema: { type: 'integer' } },
          { name: 'year_to', in: 'query', schema: { type: 'integer' } },
          { name: 'zone', in: 'query', schema: { type: 'string' } },
          { name: 'limit', in: 'query', schema: { type: 'integer', default: 25, maximum: 100 } },
        ],
        responses: { '200': { description: 'Matching cases' } },
      },
    },
    '/v1/cases/{case_number}': {
      get: {
        operationId: 'getCase',
        summary: 'One land-use case in full',
        parameters: [
          { name: 'case_number', in: 'path', required: true, schema: { type: 'string' } },
          { name: 'jurisdiction', in: 'query', schema: { type: 'string' } },
        ],
        responses: { '200': { description: 'The case' }, '404': { description: 'No such case' } },
      },
    },
    '/v1/code/{jurisdiction}/{citation}': {
      get: {
        operationId: 'getCodeSection',
        summary: 'Development code section or table by citation',
        parameters: [
          { name: 'jurisdiction', in: 'path', required: true, schema: { type: 'string' } },
          { name: 'citation', in: 'path', required: true, schema: { type: 'string' } },
        ],
        responses: { '200': { description: 'Section text or table, with effective dates' } },
      },
    },
    '/v1/jurisdictions': {
      get: {
        operationId: 'listJurisdictions',
        summary: 'All 19 jurisdictions',
        responses: { '200': { description: 'Jurisdiction list' } },
      },
    },
  },
  'x-mcp': {
    endpoint: `${origin}/mcp`,
    transport: 'streamable-http',
    authentication: 'none',
    tools: mcpTools.map((t) => t.name),
  },
});
