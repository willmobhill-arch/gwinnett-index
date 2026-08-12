// @ts-check
import { defineConfig } from 'astro/config';

// Absolute URLs are load-bearing here: the sitemap, the JSON-LD, the DCAT
// catalogue and the llms.txt files all have to emit real URLs, not paths. So the
// site origin is an explicit input rather than something inferred at request
// time, and a build that forgot to set it says so instead of shipping
// localhost URLs into a public catalogue.
const SITE_URL = process.env.SITE_URL ?? 'http://localhost:4321';
if (!process.env.SITE_URL) {
  console.warn(
    '\n  SITE_URL is not set — building with ' + SITE_URL + '.\n' +
    '  Absolute URLs (sitemap, JSON-LD, llms.txt, /data.json) will point at localhost.\n' +
    '  Set SITE_URL=https://your-domain before a production build.\n'
  );
}

export default defineConfig({
  site: SITE_URL,
  output: 'static',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  devToolbar: { enabled: false },
});
