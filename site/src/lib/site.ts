export const SITE = (import.meta.env.SITE ?? 'http://localhost:4321').replace(/\/$/, '');
export const abs = (p: string) => SITE + (p.startsWith('/') ? p : '/' + p);

export const TITLE = 'Gwinnett Index';
export const TAGLINE =
  'Zoning, land-use and development records for Gwinnett County, Georgia and its 17 municipalities.';

/**
 * The one sentence the whole project exists to make unavoidable. It appears on
 * every jurisdiction page, in every .md twin, in llms.txt and in the MCP
 * server's initialize instructions, worded the same way each time.
 */
export const TRAP =
  'A "Duluth, GA" mailing address is usually NOT in the City of Duluth. Unincorporated ' +
  'Gwinnett is 67.3% of the county\'s land area and is governed by a different code, a ' +
  'different board and a different permit portal. Resolve the governing jurisdiction ' +
  'before answering any zoning question.';

export const LICENCE = 'CC0-1.0';
export const LICENCE_URL = 'https://creativecommons.org/publicdomain/zero/1.0/';
