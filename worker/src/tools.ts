/**
 * The five operations, shared verbatim by the REST API and the MCP server.
 *
 * Five, not fifteen. Every tool description is permanent context tax in every
 * client that connects, paid on every turn whether the tool is used or not. A
 * sixth tool has to be worth more than it costs everyone who never calls it.
 *
 * Every response carries source_url, as_of, and — where the answer is a
 * jurisdiction — an explicit confidence band. A confidently wrong answer about
 * which government regulates a parcel is the worst thing this service could do,
 * so uncertainty is part of the payload rather than a caveat in prose.
 */
import { Db, HttpError, type Env } from './db';
import { geocode, pinCentroid, type Geocoded } from './geocode';

export const JURISDICTION_RULE =
  'A "Duluth, GA" mailing address is usually NOT in the City of Duluth. Unincorporated ' +
  'Gwinnett is 67.3% of the county land area and is governed by a different code, a ' +
  'different board and a different permit portal. Always resolve the governing ' +
  'jurisdiction before answering a zoning question.';

const stamp = () => new Date().toISOString();

export interface ResolveArgs { address?: string; pin?: string; band_m?: number }

export async function resolveJurisdiction(env: Env, a: ResolveArgs) {
  if (!a.address && !a.pin) throw new HttpError(400, 'give either address or pin');
  const pt: Geocoded = a.pin ? await pinCentroid(a.pin) : await geocode(a.address!);
  const db = new Db(env);
  const rows = await db.rpc<any>('resolve_jurisdiction', {
    lon: pt.lon, lat: pt.lat, band_m: a.band_m ?? 150,
  });
  const r = rows[0];

  if (!r) {
    return {
      resolved: false,
      query: { address: a.address ?? null, pin: a.pin ?? null },
      matched_address: pt.matched,
      point: { lon: pt.lon, lat: pt.lat },
      geocoder: pt.geocoder,
      message:
        'This point is not inside Gwinnett County, or falls in a sliver where the Census ' +
        'place and county-subdivision boundaries disagree. No jurisdiction is asserted.',
      note: JURISDICTION_RULE,
      as_of: stamp(),
    };
  }

  return {
    resolved: true,
    governing_jurisdiction: { slug: r.slug, name: r.name, kind: r.kind },
    code: { citation: r.code_citation, url: r.code_url },
    confidence: r.confidence,
    meters_to_nearest_boundary: r.meters_to_edge,
    caveat: r.caveat,
    is_unincorporated: r.kind === 'unincorporated',
    query: { address: a.address ?? null, pin: a.pin ?? null },
    matched_address: pt.matched,
    point: { lon: pt.lon, lat: pt.lat },
    geocoder: pt.geocoder,
    boundary_source: r.boundary_source,
    note: JURISDICTION_RULE,
    as_of: stamp(),
  };
}

const CASE_FIELDS =
  'case_number,case_type,year,status,applicant_raw,existing_zone,proposed_zone,approved_zone,' +
  'acres,res_units,nonres_sqft,proposed_use,location_text,pins,staff_rec,pc_date,pc_rec,' +
  'decision,decision_date,hearing_body,request_text,voted_for,voted_against,source_url,' +
  'source_system,last_verified,jurisdiction:jurisdiction_id(slug,name)';

export interface SearchArgs {
  query?: string; jurisdiction?: string; case_type?: string;
  year_from?: number; year_to?: number; zone?: string; limit?: number;
}

export async function searchCases(env: Env, a: SearchArgs) {
  const db = new Db(env);
  const limit = Math.min(Math.max(a.limit ?? 25, 1), 100);
  const p = new URLSearchParams();
  p.set('select', CASE_FIELDS);
  p.set('limit', String(limit));
  p.set('order', 'year.desc.nullslast,case_number.asc');

  if (a.query) {
    const q = a.query.replace(/[(),*]/g, ' ').trim();
    p.set('or', `(applicant_raw.ilike.*${q}*,proposed_use.ilike.*${q}*,location_text.ilike.*${q}*,case_number.ilike.*${q}*)`);
  }
  if (a.case_type) p.set('case_type', `eq.${a.case_type.toUpperCase()}`);
  if (a.year_from) p.append('year', `gte.${a.year_from}`);
  if (a.year_to) p.append('year', `lte.${a.year_to}`);
  if (a.zone) p.set('or', `(existing_zone.ilike.*${a.zone}*,proposed_zone.ilike.*${a.zone}*,approved_zone.ilike.*${a.zone}*)`);
  if (a.jurisdiction) {
    const j = await db.select<any>(`jurisdiction?select=id&slug=eq.${encodeURIComponent(a.jurisdiction)}`);
    if (!j.length) throw new HttpError(404, `unknown jurisdiction "${a.jurisdiction}"`);
    p.set('jurisdiction_id', `eq.${j[0].id}`);
  }

  const rows = await db.select<any>(`land_use_case?${p}`);
  return {
    count: rows.length,
    truncated: rows.length === limit,
    filters: a,
    results: rows,
    note:
      'County case records (source_system "gwinnett-arcgis") are Board of Commissioners ' +
      'decisions covering UNINCORPORATED Gwinnett only. City cases are not in that source. ' +
      'An address reading "DULUTH HIGHWAY" is a street name in unincorporated territory, ' +
      'not a City of Duluth case.',
    as_of: stamp(),
  };
}

export async function getCase(env: Env, caseNumber: string, jurisdiction?: string) {
  const db = new Db(env);
  const p = new URLSearchParams();
  p.set('select', CASE_FIELDS);
  p.set('case_number', `eq.${caseNumber}`);
  const rows = await db.select<any>(`land_use_case?${p}`);
  const hit = jurisdiction ? rows.filter((r) => r.jurisdiction?.slug === jurisdiction) : rows;
  if (!hit.length) throw new HttpError(404, `no case "${caseNumber}"`);
  return {
    ...hit[0],
    ambiguous: hit.length > 1 ? hit.map((r) => r.jurisdiction?.slug) : undefined,
    decision_codes:
      'Decision and recommendation values are reproduced exactly as the source publishes ' +
      'them. The source ships no data dictionary for these codes; open source_url for the ' +
      'authoritative wording rather than inferring their meaning.',
    as_of: stamp(),
  };
}

export async function getCodeSection(env: Env, jurisdiction: string, citation: string) {
  const db = new Db(env);
  const j = await db.select<any>(`jurisdiction?select=id,name,slug&slug=eq.${encodeURIComponent(jurisdiction)}`);
  if (!j.length) throw new HttpError(404, `unknown jurisdiction "${jurisdiction}"`);
  const id = j[0].id;

  // Accept "§ 402.03", "402.03", "Duluth UDC § 402.03" or "Table 2-B" alike:
  // an agent quoting a staff report will not normalise the citation first.
  const bare = citation.replace(/^.*?UDC\s*/i, '').replace(/^§\s*/, '').trim();

  const secs = await db.select<any>(
    `code_section?select=citation,identifier,title,article,article_title,body_md,page_from,page_to,` +
      `adopted_date,amended_through,source_url,last_verified` +
      `&jurisdiction_id=eq.${id}&or=(identifier.eq.${encodeURIComponent(bare)},citation.ilike.*${encodeURIComponent(bare)})&limit=5`
  );
  if (secs.length) {
    const s = secs[0];
    return {
      jurisdiction: { slug: j[0].slug, name: j[0].name },
      ...s,
      effective_date: s.amended_through ?? s.adopted_date,
      note: `Ordinance text mirrored in full. Cite the effective date (${s.amended_through ?? s.adopted_date}) with any figure taken from this section.`,
      also_matched: secs.length > 1 ? secs.slice(1).map((x) => x.citation) : undefined,
      as_of: stamp(),
    };
  }

  const tabs = await db.select<any>(
    `code_table?select=citation,title,header,spanning_header,header_source,rows,n_cols,n_rows,` +
      `page_from,page_to,quality,` +
      `verification_note,source_url,last_verified` +
      `&jurisdiction_id=eq.${id}&citation.ilike=*${encodeURIComponent(bare)}*` +
      `&order=page_from.asc&limit=3`
  );
  if (!tabs.length) throw new HttpError(404, `no section or table matching "${citation}" in ${jurisdiction}`);
  const t = tabs[0];
  return {
    jurisdiction: { slug: j[0].slug, name: j[0].name },
    ...t,
    // The site withholds unverified cell values; this served them. Same corpus,
    // two surfaces, opposite answers about whether the numbers can be trusted --
    // and the one that handed them over was the one agents call.
    rows: t.quality === 'verified' ? t.rows : [],
    warning:
      t.quality === 'verified'
        ? `Verified: ${t.verification_note}`
        : t.quality === 'defective'
          ? 'CELL VALUES KNOWN WRONG AND WITHHELD. The header, column count and page range of ' +
            'this table were checked against the rendered source page; the cell values came from ' +
            'an extractor that mis-assigned columns. This is stronger than "unverified" — the ' +
            `numbers are known to be incorrect. Open source_url. ${t.verification_note ?? ''}`
          : 'UNVERIFIED EXTRACTION. This table was recovered from the PDF programmatically and ' +
            'has never been checked cell-by-cell against the rendered source page. Table ' +
            'extraction fails quietly — a value can land in the wrong column and still look ' +
            `plausible. Cell values are withheld. Open source_url. ${t.verification_note ?? ''}`,
    // A citation does not identify a table. The UDC prints "Table 2-C" twice --
    // residential districts on p56, commercial on p70 -- so answering with the
    // first match and saying nothing hands back half the answer as if it were all
    // of it.
    also_matched: tabs.length > 1
      ? tabs.slice(1).map((x: any) => ({ citation: x.citation, title: x.title,
                                         page_from: x.page_from, page_to: x.page_to }))
      : undefined,
    as_of: stamp(),
  };
}

export async function listJurisdictions(env: Env) {
  const db = new Db(env);
  const rows = await db.select<any>(
    'jurisdiction?select=slug,name,kind,fips_place,code_citation,code_url,boundary_source,' +
      'boundary_vintage&order=kind.asc,name.asc'
  );
  return {
    count: rows.length,
    jurisdictions: rows,
    note:
      'Gwinnett County appears as a container boundary and is not itself a governing ' +
      'jurisdiction. Any address inside it is governed either by one of the 17 ' +
      'municipalities or by unincorporated-gwinnett. ' + JURISDICTION_RULE,
    as_of: stamp(),
  };
}
