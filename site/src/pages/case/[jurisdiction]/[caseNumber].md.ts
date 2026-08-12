import type { APIRoute, GetStaticPaths } from 'astro';
import { cases, bySlug } from '../../../lib/source';
import { frontmatter, facts, md } from '../../../lib/md';
import { abs, LICENCE, TRAP } from '../../../lib/site';
import { acres, date, zone, rawCode, isMined } from '../../../lib/format';

export const getStaticPaths: GetStaticPaths = () =>
  cases().map((c) => ({
    params: { jurisdiction: c.jurisdiction, caseNumber: c.case_number },
    props: { c },
  }));

export const GET: APIRoute = ({ props }) => {
  const c = (props as any).c as ReturnType<typeof cases>[number];
  const j = bySlug(c.jurisdiction)!;
  const path = `/case/${c.jurisdiction}/${encodeURIComponent(c.case_number)}`;

  const body = [
    frontmatter({
      title: `${c.case_number} — ${j.name}`,
      jurisdiction: j.slug,
      governing_jurisdiction: j.name,
      source_url: c.source_url ?? undefined,
      effective_date: c.decision_date ?? undefined,
      as_of: (c.last_verified ?? '').slice(0, 10),
      canonical: abs(path),
      licence: LICENCE,
    }),
    `# ${c.case_number}`,
    '',
    `**Governing jurisdiction: ${j.name}.** ${TRAP}`,
    '',
    c.proposed_use ?? c.request_text ?? '(no request text recorded)',
    '',
    isMined(c)
      ? '> **Derived from a meeting document, not a case tracker.** The City of Duluth publishes\n' +
        '> no structured case database. This record was extracted from the source PDF by\n' +
        `> \`${c.extraction_method ?? 'pattern matching'}\`, and individual fields are frequently\n` +
        '> mangled or truncated. The linked PDF is the record; this is an index entry pointing at it.\n'
      : null,
    '## Record',
    '',
    facts([
      ['Case type', c.case_type], ['Year', c.year], ['Applicant', c.applicant_raw],
      ['Location', c.location_text], ['Parcel PINs', c.pins?.join(', ')],
      ['Existing zoning', zone(c.existing_zone)], ['Proposed zoning', zone(c.proposed_zone)],
      ['Approved zoning', zone(c.approved_zone)], ['Acres', acres(c.acres)],
      ['Residential units', c.res_units], ['Non-residential sq ft', c.nonres_sqft],
    ]),
    '',
    '## Process',
    '',
    facts([
      ['Staff recommendation', rawCode(c.staff_rec)],
      ['Planning Commission', rawCode(c.pc_rec)], ['Planning Commission date', date(c.pc_date)],
      ['Decision', rawCode(c.decision)], ['Decision date', date(c.decision_date)],
      ['Status', rawCode(c.status)], ['Heard by', c.hearing_body],
      ['Voted for', c.voted_for], ['Voted against', c.voted_against],
    ]),
    '',
    'Decision codes are reproduced exactly as published; the source ships no data dictionary',
    'for them, so this index does not expand them.',
    '',
    '## Provenance',
    '',
    facts([
      ['Source system', c.source_system], ['Source URL', c.source_url],
      ['Last verified', date(c.last_verified)],
    ]),
    '',
    // NOTE: '' entries are deliberate blank lines. Only null is a suppressed
    // block — filtering out '' collapses every heading into the text above it.
  ].filter((x) => x !== null).join('\n');

  return md(body);
};
