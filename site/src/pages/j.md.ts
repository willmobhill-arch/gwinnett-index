import type { APIRoute } from 'astro';
import { jurisdictions } from '../lib/source';
import { frontmatter, table, md } from '../lib/md';
import { abs, LICENCE, TRAP } from '../lib/site';

export const GET: APIRoute = () => {
  const order = { unincorporated: 0, county: 1, municipality: 2 } as const;
  const js = [...jurisdictions()].sort(
    (a, b) => order[a.kind] - order[b.kind] || a.name.localeCompare(b.name)
  );
  return md(
    frontmatter({
      title: 'Jurisdictions — Gwinnett Index',
      as_of: new Date().toISOString().slice(0, 10),
      canonical: abs('/j'),
      licence: LICENCE,
    }) +
      `# Jurisdictions

${TRAP}

Unincorporated Gwinnett is derived geometrically — the county boundary minus the union of all
17 cities — so the resolver can name it affirmatively rather than by elimination.

${table(
  ['Jurisdiction', 'Kind', 'Sq mi', 'Cases', 'Code sections', 'Page'],
  js.map((j) => [j.name, j.kind, j.sq_mi, j.cases, j.code_sections, abs(`/j/${j.slug}.md`)])
)}

Cross-county municipalities — Braselton (4 counties), Auburn, Loganville and Rest Haven (2
each) — report their full incorporated area, not just the share inside Gwinnett, so these
figures do not sum to the county total.
`
  );
};
