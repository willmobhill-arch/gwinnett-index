/**
 * Markdown twins.
 *
 * Every HTML route has a `.md` sibling carrying the same facts with the chrome
 * removed. Measured across this build the twins run about 4x smaller than the
 * HTML in bytes, and markdown tokenises more densely than markup, so the saving
 * an agent actually sees is larger than that. scripts/verify-build.mjs prints
 * the real ratio on every build rather than letting the claim drift.
 *
 * Every twin opens with YAML frontmatter and states its governing jurisdiction
 * before any substance, exactly as the HTML does.
 */
export interface Front {
  title: string;
  jurisdiction?: string;
  governing_jurisdiction?: string;
  source_url?: string;
  effective_date?: string;
  as_of: string;
  canonical: string;
  licence: string;
}

const esc = (v: string) => (/[:#\-?{}\[\],&*!|>'"%@`]/.test(v) ? JSON.stringify(v) : v);

export function frontmatter(f: Front): string {
  const lines = Object.entries(f)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}: ${esc(String(v))}`);
  // trailing blank line: '---' immediately followed by '# Title' parses, but a
  // heading glued to the frontmatter fence reads badly everywhere it is rendered
  return ['---', ...lines, '---', '', ''].join('\n');
}

export const table = (header: string[], rows: (string | number | null)[][]) => {
  const cell = (v: string | number | null) =>
    v === null || v === undefined ? '' : String(v).replace(/\|/g, '\\|').replace(/\n+/g, ' ');
  return [
    `| ${header.join(' | ')} |`,
    `|${header.map(() => '---').join('|')}|`,
    ...rows.map((r) => `| ${r.map(cell).join(' | ')} |`),
  ].join('\n');
};

/** key/value block used for record detail in the twins */
export const facts = (pairs: [string, string | number | null | undefined][]) =>
  pairs
    .filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== '—')
    .map(([k, v]) => `- **${k}:** ${v}`)
    .join('\n');

export const md = (body: string) =>
  new Response(body, {
    headers: {
      'content-type': 'text/markdown; charset=utf-8',
      'access-control-allow-origin': '*',
    },
  });
