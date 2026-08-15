/**
 * One route manifest, derived from the data.
 *
 * The sitemap, the bulk export and the markdown-twin coverage test all read
 * from here rather than each maintaining their own idea of what exists. A
 * sitemap that has drifted from the site is worse than no sitemap: it teaches a
 * crawler that this index 404s.
 */
import { jurisdictions, cases, codeSections, codeTables, developers, devSlug } from './source';
import type { CodeSection, CodeTable } from './source';
import { codeSlug, tableSlug } from './format';

export interface Route {
  path: string;
  /** ISO date used as sitemap lastmod — the record's own verification date */
  lastmod: string;
  /** does this route have a .md twin? */
  twin: boolean;
}

const today = () => new Date().toISOString().slice(0, 10);
const day = (v: string | null | undefined) => (v ? v.slice(0, 10) : today());

/**
 * One page per code item, with both records that describe it.
 *
 * Every UDC table exists twice in the corpus: a `code_section` row carrying the
 * prose printed around it, and a `code_table` row carrying the structured header
 * and cells. They share a citation. Emitting them as two routes made them collide,
 * and a bare de-dup guard resolved the collision by keeping whichever came first —
 * the section. The consequence was invisible and total: `/code/duluth/table-2-b`
 * served the prose, and the hand-verified 20-row table that the whole verification
 * pass produced was on no page at all. Nothing 404'd, nothing warned.
 *
 * Citations are not unique either — the UDC prints "Table 2-C" twice, residential
 * and commercial — so pairing is on (citation, title), and the route carries the
 * title discriminator. See `tableSlug`.
 */
export interface CodeItem {
  jurisdiction: string;
  cite: string;
  section: CodeSection | null;
  table: CodeTable | null;
  lastmod: string;
}

export function codeItems(): CodeItem[] {
  const key = (x: { jurisdiction: string; citation: string; title: string | null }) =>
    `${x.jurisdiction}\u0000${x.citation}\u0000${x.title ?? ''}`;
  const tables = new Map(codeTables().map((t) => [key(t), t]));
  const out: CodeItem[] = [];
  const seen = new Set<string>();

  const push = (jurisdiction: string, cite: string, section: CodeSection | null,
                table: CodeTable | null, lastmod: string) => {
    const k = `${jurisdiction}/${cite}`;
    if (seen.has(k)) return;
    seen.add(k);
    out.push({ jurisdiction, cite, section, table, lastmod });
  };

  for (const s of codeSections()) {
    const paired = tables.get(key(s)) ?? null;
    if (paired) tables.delete(key(s));
    push(s.jurisdiction, paired ? tableSlug(s) : codeSlug(s.citation), s, paired,
         day(s.amended_through));
  }
  // Tables with no prose section of their own — 4-C and 12-A were only ever
  // extracted as tables.
  for (const t of tables.values()) push(t.jurisdiction, tableSlug(t), null, t, today());

  return out;
}

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

  for (const it of codeItems())
    out.push({ path: `/code/${it.jurisdiction}/${it.cite}`, lastmod: it.lastmod, twin: true });

  for (const d of developers())
    out.push({ path: `/developer/${devSlug(d.norm_name)}`, lastmod: today(), twin: true });

  return out;
}
