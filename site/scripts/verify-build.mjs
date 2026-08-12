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

// ------------------------------------------------------------------ report
for (const o of ok) console.log(`  ok    ${o}`);
for (const w of warn) console.log(`  warn  ${w}`);
for (const f of fail) console.log(`  FAIL  ${f}`);
console.log(`\n${ok.length} passed, ${warn.length} warning(s), ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
