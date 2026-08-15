import type { Case, Jurisdiction } from './source';

export const num = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : n.toLocaleString('en-US');

export const acres = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : `${Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 })} ac`;

export const date = (d: string | null | undefined) => (d ? d.slice(0, 10) : '—');

export const kindLabel = (k: Jurisdiction['kind']) =>
  k === 'unincorporated' ? 'Unincorporated county'
  : k === 'municipality' ? 'Municipality'
  : 'County (container)';

/**
 * Decision and recommendation values are reproduced EXACTLY as the county
 * publishes them (APC, DEN, REC, WD, TBL ...). The source GIS layer ships no
 * data dictionary for these codes, so expanding them here would mean guessing
 * at the meaning of a legal outcome and presenting the guess as fact. The raw
 * code plus a link to the Accela record is the honest rendering.
 */
export const rawCode = (v: string | null | undefined) => (v && v !== 'NA' && v !== 'N/A' ? v : '—');

export const zone = (v: string | null | undefined) => (v && v !== 'NA' ? v : '—');

export const caseTitle = (c: Case) =>
  [c.case_number, c.proposed_use ?? c.request_text ?? '']
    .filter(Boolean).join(' — ').trim();

export const casePath = (c: Case) => `/case/${c.jurisdiction}/${encodeURIComponent(c.case_number)}`;

/** Cases whose text fields came out of an agenda PDF rather than a database. */
export const isMined = (c: Case) => c.source_system === 'duluth-agenda-mining';

/**
 * URL segment for a code item.
 *
 * Sections key off their identifier (`101.02`) because that is what a citation
 * in a staff report or a court filing actually says. Tables have no numeric
 * identifier, so their citation tail is slugified: "Duluth UDC Table 2-B"
 * becomes "table-2-b". Both are stable across re-extractions of the PDF, which
 * matters — these URLs are meant to be cited.
 */
export const codeSlug = (citation: string) => {
  const tail = citation.replace(/^.*?UDC\s*/i, '').replace(/^§\s*/, '').trim();
  return /^[\d.]+$/.test(tail)
    ? tail
    : tail.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
};

/**
 * URL segment for a code *table*.
 *
 * A citation is not unique for tables. The UDC prints "Table 2-C" twice — once
 * for residential districts (p56) and once for commercial (p70) — and the same
 * for 2-D. Keying the route on the citation alone gave both fragments the same
 * URL, and the de-dup guard in `routes.ts` then dropped the second one: the
 * commercial half of the table that answers "can I put this use here" had no
 * page at all, and nothing in the build said so.
 *
 * The source's own discriminator is the subtitle after the colon, so use that.
 * Tables with no colon in the title are unaffected and keep their existing URL.
 */
export const tableSlug = (t: { citation: string; title: string | null }) => {
  const base = codeSlug(t.citation);
  const i = (t.title ?? '').lastIndexOf(':');
  if (i < 0) return base;
  const suffix = t.title!.slice(i + 1).toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return suffix ? `${base}-${suffix}` : base;
};


/**
 * A decision and the motion it applied to, together.
 *
 * "Motion carried" on its own is actively misleading: SU2025-004 carried a motion
 * to DENY, and SU2025-001 one to POSTPONE. Ten of Duluth's extracted decisions
 * mean something other than approved, and the outcome text says so in none of
 * them. Never render one without the other.
 */
export const decisionWithAction = (
  decision: string | null | undefined,
  action: string | null | undefined,
) => {
  if (!decision) return '—';
  if (!action) return decision;
  return `${decision} — motion to ${action}`;
};
