/**
 * Where the build gets its data.
 *
 * This container (and the Cowork sandbox before it) cannot open an outbound
 * connection to Supabase, so the site is built from a *snapshot on disk* rather
 * than by querying the database during the build. That is not only a
 * workaround: a static site that reads a committed snapshot builds
 * deterministically, builds offline, and can be diffed — you can see exactly
 * what changed between two deploys of a legal-reference index.
 *
 * Resolution order:
 *   1. SNAPSHOT_DIR (or ../data/snapshot) — the real export, written by
 *      scripts/export_snapshot.py against Postgres. Gitignored; produced in CI.
 *   2. ./fixtures — a small committed sample with the same shape, so the site
 *      builds and its tests run with no database at all.
 *
 * Falling back is loud on purpose. A site that silently ships ten sample cases
 * where eleven thousand were expected looks completely fine in a browser.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = path.resolve(HERE, '../..');
const FIXTURES = path.join(SITE_ROOT, 'fixtures');
const SNAPSHOT = process.env.SNAPSHOT_DIR
  ? path.resolve(process.env.SNAPSHOT_DIR)
  : path.resolve(SITE_ROOT, '../data/snapshot');

export const usingFixtures = !fs.existsSync(path.join(SNAPSHOT, 'jurisdictions.json'));
const DIR = usingFixtures ? FIXTURES : SNAPSHOT;

let announced = false;
function announce() {
  if (announced) return;
  announced = true;
  if (usingFixtures) {
    console.warn(
      '\n  Building from site/fixtures — a SAMPLE, not the corpus.\n' +
      '  Run scripts/export_snapshot.py to produce data/snapshot, or set SNAPSHOT_DIR.\n' +
      '  Case, code and developer counts on the built site will be a handful, not 11,848.\n'
    );
  } else {
    console.log(`  Data source: ${DIR}`);
  }
}

function load<T>(name: string, fallback: T): T {
  announce();
  const file = path.join(DIR, `${name}.json`);
  if (!fs.existsSync(file)) return fallback;
  return JSON.parse(fs.readFileSync(file, 'utf8')) as T;
}

export type Kind = 'county' | 'municipality' | 'unincorporated';

export interface Jurisdiction {
  slug: string; name: string; kind: Kind; state: string;
  fips_place: string | null; fips_county: string | null;
  sq_mi: number | null; cases: number; first_year: number | null; last_year: number | null;
  code_sections: number; code_tables: number;
  code_citation: string | null; code_url: string | null;
  boundary_source: string | null; boundary_vintage: string | null; notes: string | null;
}

export interface Case {
  case_number: string; jurisdiction: string; case_type: string | null; year: number | null;
  status: string | null; applicant_raw: string | null; applicant_norm: string | null;
  existing_zone: string | null; proposed_zone: string | null; approved_zone: string | null;
  acres: number | null; res_units: number | null; nonres_sqft: number | null;
  proposed_use: string | null; location_text: string | null; pins: string[] | null;
  staff_rec: string | null; pc_date: string | null; pc_rec: string | null;
  decision: string | null; decision_date: string | null; hearing_body: string | null;
  request_text: string | null; voted_for: string | null; voted_against: string | null;
  source_url: string | null; source_system: string; extraction_method: string | null;
  last_verified: string | null;
}

export interface CodeSection {
  citation: string; identifier: string; jurisdiction: string; kind: string | null;
  title: string | null; article: string | null; article_title: string | null;
  section: string | null; section_title: string | null; level: number | null;
  body_md: string | null; page_from: number | null; page_to: number | null;
  adopted_date: string | null; amended_through: string | null; source_url: string;
}

export interface CodeTable {
  citation: string; jurisdiction: string; title: string | null; header: string[] | null;
  rows: string[][] | null; n_cols: number | null; n_rows: number | null;
  page_from: number | null; page_to: number | null;
  quality: string | null; verification_note: string | null; source_url: string;
}

export interface Developer {
  display_name: string; norm_name: string; total_cases: number;
  first_year: number | null; last_year: number | null; span_years: number | null;
  name_variants: number | null; res_units: number | null; acres: number | null;
  nonres_sqft: number | null; cases_since_2020: number | null;
  approved: number | null; denied: number | null;
}

export interface Stats {
  total_cases: number; county_cases: number; duluth_cases: number;
  first_year: number; last_year: number; with_source_url: number; with_pins: number;
  res_units: number; acres: number; applicants: number; applicant_variants: number;
  merge_pending: number; code_sections: number; code_tables: number;
  code_tables_verified: number; meeting_docs: number; meeting_pages: number; probes: number;
  resolver: Record<string, { probes: number; correct: number }>;
  case_types: { case_type: string; n: number }[];
  by_decade: { decade: number; n: number }[];
  generated_from?: string; generated_at?: string;
}

export const jurisdictions = (): Jurisdiction[] => load<Jurisdiction[]>('jurisdictions', []);
export const cases        = (): Case[]         => load<Case[]>('cases', []);
export const codeSections = (): CodeSection[]  => load<CodeSection[]>('code_sections', []);
export const codeTables   = (): CodeTable[]    => load<CodeTable[]>('code_tables', []);
export const developers   = (): Developer[]    => load<Developer[]>('developers', []);
export const stats        = (): Stats          => load<Stats>('stats', {} as Stats);

export const bySlug = (slug: string) => jurisdictions().find((j) => j.slug === slug);
export const casesFor = (slug: string) => cases().filter((c) => c.jurisdiction === slug);

/** Slug a developer name for its profile URL. Stable, lowercase, ASCII. */
export const devSlug = (norm: string) =>
  norm.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
