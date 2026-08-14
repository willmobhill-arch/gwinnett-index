#!/usr/bin/env node
/**
 * Build gates. Run against dist/ after `astro build`.
 *
 * These check the things that fail *silently* — where the site looks perfect in
 * a browser while being useless or wrong for its actual audience:
 *
 *   - a sitemap entry whose .md twin does not exist teaches crawlers we 404
 *   - a page that answers a zoning question before naming the jurisdiction
 *     defeats the entire premise of the index
 *   - county GIS geometry in the bulk export is a licence violation, and
 *     nothing about the page would look wrong
 *
 * The one gate that cannot run here is the Cloudflare Bot Fight Mode check:
 * it needs a live origin. It lives in CI against the deployed site.
 */
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const DIST = path.resolve(process.argv[2] ?? 'dist');
const fail = [];
const warn = [];
const ok = [];

const read = (p) => fs.readFileSync(path.join(DIST, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(DIST, p));

// ---------------------------------------------------------------- sitemap
const sitemap = read('sitemap.xml');
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
if (locs.length === 0) fail.push('sitemap.xml contains no <loc> entries');
else ok.push(`sitemap lists ${locs.length} routes`);

const origin = locs[0]?.replace(/(https?:\/\/[^/]+).*/, '$1') ?? '';
const toPath = (u) => u.slice(origin.length) || '/';

// every sitemap route resolves to a built HTML file
const missingHtml = locs
  .map(toPath)
  .filter((p) => !exists(p === '/' ? 'index.html' : path.join(p, 'index.html')));
if (missingHtml.length) fail.push(`${missingHtml.length} sitemap route(s) have no HTML: ${missingHtml.slice(0, 5).join(', ')}`);
else ok.push('every sitemap route has a built HTML page');

// every sitemap route has a .md twin
const missingTwin = locs
  .map(toPath)
  .filter((p) => !exists(p === '/' ? 'index.md' : `${p}.md`));
if (missingTwin.length) fail.push(`${missingTwin.length} route(s) have no .md twin: ${missingTwin.slice(0, 5).join(', ')}`);
else ok.push('every sitemap route has a .md twin');

// lastmod present and well-formed on every entry
const urls = sitemap.split('<url>').slice(1);
const badMod = urls.filter((u) => !/<lastmod>\d{4}-\d{2}-\d{2}<\/lastmod>/.test(u));
if (badMod.length) fail.push(`${badMod.length} sitemap entries lack a valid lastmod`);
else ok.push('every sitemap entry carries an ISO lastmod');

// ------------------------------------------------- jurisdiction stated first
// Any page carrying substantive records must name its governing jurisdiction.
const substantive = locs.map(toPath).filter((p) => /^\/(j|case|code|developer)\//.test(p));
const noCallout = substantive.filter((p) => {
  const html = read(path.join(p, 'index.html'));
  const i = html.indexOf('Governing jurisdiction');
  if (i < 0) return true;
  // and it must come before the record detail, not after it
  const j = html.indexOf('<dl class="facts"');
  return j >= 0 && j < i;
});
if (noCallout.length)
  fail.push(`${noCallout.length} page(s) present records before naming the governing jurisdiction: ${noCallout.slice(0, 5).join(', ')}`);
else ok.push(`all ${substantive.length} record pages name the governing jurisdiction first`);

// the same requirement for the twins, which are what agents actually read
const twinNoJurisdiction = substantive.filter((p) => !read(`${p}.md`).includes('Governing jurisdiction:'));
if (twinNoJurisdiction.length)
  fail.push(`${twinNoJurisdiction.length} .md twin(s) omit the governing jurisdiction`);
else ok.push('all record twins state the governing jurisdiction');

// twins must carry YAML frontmatter with provenance
const badFront = locs
  .map(toPath)
  .map((p) => (p === '/' ? 'index.md' : `${p}.md`))
  .filter((f) => {
    const t = read(f);
    return !t.startsWith('---\n') || !/\nas_of: /.test(t) || !/\ncanonical: /.test(t);
  });
if (badFront.length) fail.push(`${badFront.length} twin(s) lack frontmatter with as_of + canonical: ${badFront.slice(0, 3).join(', ')}`);
else ok.push('every twin opens with frontmatter carrying as_of and canonical');

// ------------------------------------------------------------------ robots
const robots = read('robots.txt');
for (const a of ['GPTBot', 'ClaudeBot', 'OAI-SearchBot', 'Claude-SearchBot', 'PerplexityBot', 'Google-Extended', 'CCBot']) {
  if (!robots.includes(`User-agent: ${a}`)) fail.push(`robots.txt does not name ${a}`);
}
if (!/Content-Signal:.*ai-input=yes/.test(robots)) fail.push('robots.txt lacks an affirmative Content-Signal');
if (!robots.includes('Sitemap:')) fail.push('robots.txt does not declare the sitemap');
if (!fail.some((f) => f.includes('robots.txt'))) ok.push('robots.txt names every target crawler and declares the sitemap');

// -------------------------------------------------------------- llms.txt
const llms = read('llms.txt');
if (!/not in the City of Duluth/i.test(llms)) fail.push('llms.txt does not state the jurisdiction trap');
if (!/## Instructions/.test(llms)) fail.push('llms.txt has no Instructions section');
if (!/effective date/i.test(llms)) fail.push('llms.txt does not require citing the effective date');
if (!fail.some((f) => f.includes('llms.txt'))) ok.push('llms.txt states the trap, the rules and the dating requirement');

// --------------------------------------------------------- absolute URLs
if (origin.includes('localhost')) {
  warn.push(`absolute URLs point at ${origin} — set SITE_URL before a production build`);
}

// ------------------------------------------------------- legal: geometry
const gz = fs.readFileSync(path.join(DIST, 'bulk/corpus.jsonl.gz'));
const corpus = zlib.gunzipSync(gz).toString('utf8');
const lines = corpus.trim().split('\n');
const geomHits = lines.filter((l) => /"(boundary|geometry|geom|rings|wkt|coordinates)"\s*:/.test(l));
if (geomHits.length) fail.push(`${geomHits.length} bulk export line(s) contain geometry — Gwinnett GIS forbids redistribution`);
else ok.push(`bulk export carries no geometry (${lines.length} records)`);

const noProvenance = lines.filter((l) => {
  const o = JSON.parse(l);
  if (o.record === 'developer' || o.record === 'jurisdiction') return false;
  return !o.source_url;
});
if (noProvenance.length > lines.length * 0.05)
  fail.push(`${noProvenance.length} exported records lack source_url`);
else ok.push(`bulk export provenance: ${lines.length - noProvenance.length}/${lines.length} records carry source_url`);

// -------------------------------------------------------------- catalogues
for (const f of ['data.json', 'catalog.jsonld']) {
  try { JSON.parse(read(f)); ok.push(`${f} parses`); }
  catch (e) { fail.push(`${f} is not valid JSON: ${e.message}`); }
}

// ------------------------------------------------- twin size, measured not claimed
// The whole point of the twins is fewer tokens. Print the real ratio every build
// so the claim in the copy can never drift away from what is actually shipped.
const ratios = substantive.map((p) => {
  const h = fs.statSync(path.join(DIST, p, 'index.html')).size;
  const m = fs.statSync(path.join(DIST, `${p}.md`)).size;
  return h / m;
}).sort((a, b) => a - b);
if (ratios.length) {
  const median = ratios[Math.floor(ratios.length / 2)];
  ok.push(`twins are ${median.toFixed(1)}x smaller than their HTML (median of ${ratios.length}, range ${ratios[0].toFixed(1)}-${ratios.at(-1).toFixed(1)}x)`);
}

// blank lines survived assembly -- a twin whose headings are glued to the text
// above them still renders, and still looks fine, and is markedly worse to read
const glued = substantive.map((p) => `${p}.md`).filter((f) => /[^\n]\n#{1,3} /.test(read(f)));
if (glued.length) fail.push(`${glued.length} twin(s) have headings with no blank line before them: ${glued.slice(0, 3).join(', ')}`);
else ok.push('twin markdown is well-formed (headings separated)');

// --------------------------------------------------- deploy-shape limits
// Static hosts cap the number of files in a deployment, and this site emits two
// per record -- an HTML page and its .md twin -- so the count scales with the
// corpus and will cross the line long before anyone thinks to look. Finding that
// out from a failed deploy, after a 33-second build and a 247 MB upload, is the
// expensive way.
//
// Deployed as Workers Static Assets on the Workers Paid plan: 100,000 files,
// 25 MiB per individual asset. NOT Pages -- the Pages 100,000-file ceiling is
// tied to the zone plan (Pro, $20/mo per domain) rather than to Workers Paid, so
// buying Workers Paid does not lift the Pages 20,000 cap.
//
// The free tier is 20,000 either way, and wrangler older than 4.34.0 enforces
// 20,000 regardless of plan -- a stale wrangler fails a 30,000-file deploy with
// an error that reads like a billing problem. Set MAX_DEPLOY_FILES=20000 to model
// the free tier deliberately.
const MAX_FILES = Number(process.env.MAX_DEPLOY_FILES ?? 100000);
const MAX_FILE_BYTES = Number(process.env.MAX_DEPLOY_FILE_BYTES ?? 25 * 1024 * 1024);

const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
  const p = path.join(dir, e.name);
  return e.isDirectory() ? walk(p) : [p];
});
const files = walk(DIST);
const sizes = files.map((f) => fs.statSync(f).size);
const totalMb = sizes.reduce((a, b) => a + b, 0) / 1048576;
const biggest = Math.max(...sizes);
const biggestFile = files[sizes.indexOf(biggest)];

if (files.length > MAX_FILES) {
  fail.push(
    `${files.length.toLocaleString()} files exceeds the ${MAX_FILES.toLocaleString()}-file ` +
    `deploy limit. Two files per record (HTML + .md twin) means this grows with the corpus. ` +
    `Check the plan and the wrangler version before changing the build: wrangler < 4.34.0 ` +
    `enforces 20,000 whatever the plan says.`
  );
} else if (files.length > MAX_FILES * 0.85) {
  warn.push(`${files.length.toLocaleString()} files is within 15% of the ${MAX_FILES.toLocaleString()} deploy limit`);
} else {
  ok.push(`${files.length.toLocaleString()} files, ${totalMb.toFixed(0)} MB (limit ${MAX_FILES.toLocaleString()})`);
}
// 25 MiB is a hard per-asset limit: an oversized file is rejected at upload, so
// the deploy fails as a whole rather than serving a truncated corpus. The sitemap
// and the bulk export are the two that grow without bound.
const oversized = files.filter((f, i) => sizes[i] > MAX_FILE_BYTES);
if (oversized.length) {
  fail.push(
    `${oversized.length} file(s) exceed the ${(MAX_FILE_BYTES / 1048576).toFixed(0)} MiB ` +
    `per-asset limit: ${oversized.slice(0, 3).map((f) => path.relative(DIST, f)).join(', ')}. ` +
    `Shard the sitemap by jurisdiction and year, or split the bulk export.`
  );
} else {
  ok.push(
    `largest asset ${(biggest / 1048576).toFixed(1)} MiB (${path.relative(DIST, biggestFile)}), ` +
    `limit ${(MAX_FILE_BYTES / 1048576).toFixed(0)} MiB`
  );
}

// The agent surface must be reachable without invoking the Worker. wrangler.toml
// scopes run_worker_first to /v1/*, /mcp and /openapi.json; if a corpus path ever
// needs Worker code, that promise is broken and this gate should be extended.
const WORKER_SCOPED = ['/v1/', '/mcp', '/openapi.json'];
const agentSurface = ['index.html', 'llms.txt', 'robots.txt', 'sitemap.xml',
                      'data.json', 'catalog.jsonld', 'bulk/corpus.jsonl.gz'];
const missingSurface = agentSurface.filter((f) => !exists(f));
if (missingSurface.length) {
  fail.push(`agent surface missing from static output: ${missingSurface.join(', ')}`);
} else if (agentSurface.some((f) => WORKER_SCOPED.some((w) => ('/' + f).startsWith(w)))) {
  fail.push('an agent-surface path falls inside run_worker_first and would require Worker code');
} else {
  ok.push(`agent surface is fully static (${agentSurface.length} entry points, no Worker needed)`);
}

// ------------------------------------- no undefined/NaN in published text
// A template that renders `undefined` produces a page that looks completely
// normal and states a non-fact. This shipped live once: the snapshot was missing
// meeting_pages and the homepage read "353 | undefined pages". Cheap to check,
// impossible to notice by eye across 15,000 files.
const leaky = locs
  .map(toPath)
  .flatMap((p) => [p === '/' ? 'index.html' : path.join(p, 'index.html'),
                   p === '/' ? 'index.md' : `${p}.md`])
  .filter((f) => exists(f) && /\b(undefined|NaN)\b/.test(read(f)));
if (leaky.length) {
  fail.push(
    `${leaky.length} page(s) contain "undefined" or "NaN" in rendered text: ` +
    `${leaky.slice(0, 4).join(', ')}. A missing snapshot field renders as a ` +
    `non-fact rather than as an error.`
  );
} else {
  ok.push('no "undefined" or "NaN" in any rendered page');
}

// ------------------------------------------------------------------ report
for (const o of ok) console.log(`  ok    ${o}`);
for (const w of warn) console.log(`  warn  ${w}`);
for (const f of fail) console.log(`  FAIL  ${f}`);
console.log(`\n${ok.length} passed, ${warn.length} warning(s), ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
