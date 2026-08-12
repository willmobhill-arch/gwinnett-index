/**
 * Exercises the MCP envelope and the five tools against a stubbed upstream.
 * No network: fetch is replaced, so this proves the protocol wiring and the
 * shape of what we hand a model, not that Supabase is reachable.
 */
import assert from 'node:assert/strict';
import worker from '../dist-test/index.js';

const env = { SUPABASE_URL: 'https://stub.invalid', SUPABASE_ANON_KEY: 'stub-key' };

const real = globalThis.fetch;
globalThis.fetch = async (input) => {
  const url = String(input);
  if (url.includes('GC_AddressLocationService')) {
    return Response.json({ candidates: [{ address: '3175 PEACHTREE INDUSTRIAL BLVD', location: { x: -84.14, y: 34.0 } }] });
  }
  if (url.includes('rpc/resolve_jurisdiction')) {
    return Response.json([{
      slug: 'unincorporated-gwinnett', name: 'Unincorporated Gwinnett County',
      kind: 'unincorporated', code_citation: 'Gwinnett County Unified Development Ordinance',
      code_url: 'https://example.test/udo', confidence: 'high', meters_to_edge: 812.4,
      caveat: null, boundary_source: 'Derived: Gwinnett County minus 17 municipalities',
    }]);
  }
  if (url.includes('/rest/v1/jurisdiction?')) return Response.json([{ id: 1, slug: 'duluth', name: 'Duluth' }]);
  if (url.includes('/rest/v1/land_use_case?')) {
    return Response.json([{ case_number: 'REZ2025-00025', year: 2026, decision: 'APC',
      source_url: 'https://example.test/aca', jurisdiction: { slug: 'unincorporated-gwinnett' } }]);
  }
  if (url.includes('/rest/v1/code_section?')) {
    return Response.json([{ citation: 'Duluth UDC § 102.02', identifier: '102.02', title: 'Conflict with Other Regulations',
      body_md: 'a. Whenever the provisions...', adopted_date: '2025-09-08', amended_through: '2026-07-13',
      source_url: 'https://example.test/udc.pdf' }]);
  }
  if (url.includes('/rest/v1/code_table?')) return Response.json([]);
  throw new Error(`unstubbed fetch: ${url}`);
};

const rpc = (body) => worker.fetch(new Request('https://api.test/mcp', {
  method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
}), env).then((r) => r.json());

let pass = 0;
const t = async (name, fn) => {
  try { await fn(); console.log(`  ok    ${name}`); pass++; }
  catch (e) { console.log(`  FAIL  ${name}\n        ${e.message}`); process.exitCode = 1; }
};

await t('initialize returns protocol version and instructions', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} });
  assert.equal(r.result.protocolVersion, '2025-06-18');
  assert.equal(r.result.serverInfo.name, 'gwinnett-index');
  assert.match(r.result.instructions, /ALWAYS CALL resolve_jurisdiction FIRST/);
  assert.match(r.result.instructions, /NOT in the City of Duluth/);
});

await t('tools/list exposes exactly five tools', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
  const names = r.result.tools.map((x) => x.name);
  assert.deepEqual(names, ['resolve_jurisdiction', 'search_cases', 'get_case', 'get_code_section', 'list_jurisdictions']);
  for (const tool of r.result.tools) {
    assert.ok(tool.description.length > 40, `${tool.name} description too thin`);
    assert.equal(tool.inputSchema.type, 'object');
  }
  assert.match(r.result.tools[0].description, /ALWAYS CALL THIS FIRST/);
});

await t('resolve_jurisdiction returns jurisdiction, confidence and provenance', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 3, method: 'tools/call',
    params: { name: 'resolve_jurisdiction', arguments: { address: '3175 Peachtree Industrial Blvd, Duluth GA' } } });
  const s = r.result.structuredContent;
  assert.equal(r.result.isError, false);
  assert.equal(s.governing_jurisdiction.slug, 'unincorporated-gwinnett');
  assert.equal(s.is_unincorporated, true);
  assert.equal(s.confidence, 'high');
  assert.equal(s.geocoder, 'gwinnett-county');
  assert.ok(s.meters_to_nearest_boundary > 0);
  assert.match(s.note, /NOT in the City of Duluth/);
  assert.ok(s.as_of, 'every response must carry as_of');
  // the text content must be present too: not every client reads structuredContent
  assert.match(r.result.content[0].text, /unincorporated-gwinnett/);
});

await t('search_cases warns that county records are unincorporated-only', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 4, method: 'tools/call',
    params: { name: 'search_cases', arguments: { query: 'townhouses', limit: 5 } } });
  assert.match(r.result.structuredContent.note, /UNINCORPORATED Gwinnett only/);
  assert.match(r.result.structuredContent.note, /DULUTH HIGHWAY/);
});

await t('get_code_section carries an effective date', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 5, method: 'tools/call',
    params: { name: 'get_code_section', arguments: { jurisdiction: 'duluth', citation: 'Duluth UDC § 102.02' } } });
  const s = r.result.structuredContent;
  assert.equal(s.effective_date, '2026-07-13');
  assert.match(s.note, /Cite the effective date/);
});

await t('a failing tool returns isError, not a protocol error', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 6, method: 'tools/call',
    params: { name: 'resolve_jurisdiction', arguments: {} } });
  assert.equal(r.error, undefined, 'must not surface as a JSON-RPC error');
  assert.equal(r.result.isError, true);
  assert.match(r.result.content[0].text, /address or pin/);
});

await t('unknown method is a JSON-RPC error', async () => {
  const r = await rpc({ jsonrpc: '2.0', id: 7, method: 'nope/nope' });
  assert.equal(r.error.code, -32601);
});

await t('notifications get 202 with no body', async () => {
  const res = await worker.fetch(new Request('https://api.test/mcp', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
  }), env);
  assert.equal(res.status, 202);
});

await t('REST /v1/resolve mirrors the MCP tool exactly', async () => {
  const res = await worker.fetch(new Request('https://api.test/v1/resolve?address=3175+Peachtree+Industrial+Blvd'), env);
  const j = await res.json();
  assert.equal(j.governing_jurisdiction.slug, 'unincorporated-gwinnett');
  assert.equal(res.headers.get('link'), '</openapi.json>; rel="service-desc"');
});

await t('openapi advertises the MCP endpoint and all five operations', async () => {
  const res = await worker.fetch(new Request('https://api.test/openapi.json'), env);
  const j = await res.json();
  assert.equal(j['x-mcp'].authentication, 'none');
  assert.equal(j['x-mcp'].tools.length, 5);
  assert.equal(Object.keys(j.paths).length, 5);
});

globalThis.fetch = real;
console.log(`\n${pass} passed`);
