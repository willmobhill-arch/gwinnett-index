/**
 * One route manifest, derived from the data.
 *
 * The sitemap, the bulk export and the markdown-twin coverage test all read
 * from here rather than each maintaining their own idea of what exists. A
 * sitemap that has drifted from the site is worse than no sitemap: it teaches a
 * crawler that this index 404s.
 */
import { jurisdictions, cases, codeSections, codeTables, developers, devSlug } from './source';
import { codeSlug } from './format';

export interface Route {
  path: string;
  /** ISO date used as sitemap lastmod — the record's own verification date */
  lastmod: string;
  /** does this route have a .md twin? */
  twin: boolean;
}

const today = () => new Date().toISOString().slice(0, 10);
const day = (v: string | null | undefined) => (v ? v.slice(0, 10) : today());

export function routes(): Route[] {
  const out: Route[] = [
    { path: '/', lastmod: today(), twin: true },
    { path: '/j', lastmod: today(), twin: true },
    { path: '/developer', lastmod: today(), twin: true },
    { path: '/status', lastmod: today(), twin: true },
  ];

  for (const j of jurisdictions()) out.push({ path: `/j/${j.slug}`, lastmod: today(), twin: true });

  for (const c of cases())
    out.push({
      path: `/case/${c.jurisdiction}/${encodeURIComponent(c.case_number)}`,
      lastmod: day(c.last_verified),
      twin: true,
    });

  const codeJurisdictions = new Set(
    [...codeSections(), ...codeTables()].map((x) => x.jurisdiction)
  );
  for (const slug of codeJurisdictions) out.push({ path: `/code/${slug}`, lastmod: today(), twin: true });

  const seen = new Set<string>();
  for (const s of codeSections()) {
    const p = `/code/${s.jurisdiction}/${codeSlug(s.citation)}`;
    if (seen.has(p)) continue;
    seen.add(p);
    out.push({ path: p, lastmod: day(s.amended_through), twin: true });
  }
  for (const t of codeTables()) {
    const p = `/code/${t.jurisdiction}/${codeSlug(t.citation)}`;
    if (seen.has(p)) continue;
    seen.add(p);
    out.push({ path: p, lastmod: today(), twin: true });
  }

  for (const d of developers())
    out.push({ path: `/developer/${devSlug(d.norm_name)}`, lastmod: today(), twin: true });

  return out;
}
