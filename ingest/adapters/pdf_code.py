"""
pdf_code -- a code of ordinances published as one large PDF.

The first adapter, and the one the contract in base.py was written against. It wraps
the modules in ingest/pdf/, which already worked standalone; nothing about the
extraction changed here, it was given the five stages so a second PDF-published code
is a config entry rather than a new script.

Duluth's UDC is the only configured source. Peachtree Corners and Norcross are the
real test of the reuse claim: if either needs new code in this file rather than a new
entry in SOURCES, the adapter layer is leaking and that comes before adding more.

    python3 -m ingest.adapters.pdf_code --discover duluth
    python3 -m ingest.adapters.pdf_code --plan duluth
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys

from .base import Artifact, LoadPlan, raw_url, register

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# Adding a jurisdiction should only ever mean adding a block here.
#
# `url` is deliberately not a constant anywhere else: the UDC filename encodes its
# amendment date and changes on every amendment, which makes the changing filename the
# change-detection signal. Scrape the link, never hardcode it -- and when `sha256`
# stops matching, every table needs re-verifying against the new render before the
# fixture's assertions mean anything again.
SOURCES = {
    'duluth': {
        'jurisdiction': 'duluth',
        'index_url': 'https://www.duluthga.net/',
        'url': 'https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf',
        'sha256': '2311ae985c3f1e46cb84844fdb09bfe92b89917572e112c29b78cb9fe94a48c0',
        'pdf_path': 'var/duluth_udc.pdf',
        'fixture': 'tests/fixtures/duluth_udc_tables.json',
        'published': 'data/udc_table_cells.jsonl',
        'loader': 'load_udc_table_cells_from_url',
    },
}


class PdfCodeAdapter:
    """A code of ordinances published as a single PDF."""

    name = 'pdf_code'

    def _cfg(self, config: dict | str) -> dict:
        return SOURCES[config] if isinstance(config, str) else config

    def _abs(self, cfg: dict, key: str) -> str:
        return os.path.join(_ROOT, cfg[key])

    def discover(self, config: dict | str) -> list[dict]:
        """Tables the document announces, by its own printed titles.

        Independent of the fixture and of extraction, which is the whole value: the
        count the document claims and the count extracted must agree, or a table has
        been lost. 4-C and 12-A were missing from the corpus for weeks because
        discovery demanded punctuation the document does not always use.
        """
        import pymupdf

        from ingest.pdf.extract_cells import discovered_tables
        cfg = self._cfg(config)
        pdf = self._abs(cfg, 'pdf_path')
        if not os.path.exists(pdf):
            raise FileNotFoundError(f'{pdf} not fetched; run fetch() first')
        return [{'label': lab, 'page': page, 'title': title}
                for page, lab, title in discovered_tables(pymupdf.open(pdf))]

    def fetch(self, config: dict | str) -> list[Artifact]:
        """Download the PDF and record what was actually retrieved.

        The hash is checked, not assumed. A changed hash is not a failure to route
        around -- it means the ordinance was amended and the hand-verified fixture now
        describes a document that no longer exists.
        """
        import urllib.request
        cfg = self._cfg(config)
        dest = self._abs(cfg, 'pdf_path')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with urllib.request.urlopen(cfg['url']) as r:
            body = r.read()
        with open(dest, 'wb') as fh:
            fh.write(body)
        digest = hashlib.sha256(body).hexdigest()
        note = None
        if cfg.get('sha256') and digest != cfg['sha256']:
            note = (f'HASH CHANGED: expected {cfg["sha256"]}, got {digest}. The '
                    f'ordinance has been amended; re-verify every table against the '
                    f'new render before trusting the fixture.')
        return [Artifact(path=dest, source_url=cfg['url'], sha256=digest, note=note,
                         retrieved=_dt.datetime.now(_dt.timezone.utc).isoformat())]

    def parse(self, config: dict | str) -> list[dict]:
        """Cells from the ruled grid, shaped by the hand-verified fixture."""
        from ingest.pdf.extract_cells import extract_table
        cfg = self._cfg(config)
        truth = json.load(open(self._abs(cfg, 'fixture')))['tables']
        return [extract_table(spec) for spec in truth]

    def normalize(self, config: dict | str) -> list[dict]:
        """Parsed tables to loader records, with the quality claim attached."""
        from ingest.pdf.publish_cells import main as publish
        publish()
        cfg = self._cfg(config)
        return [json.loads(line) for line in open(self._abs(cfg, 'published'))]

    def upsert(self, config: dict | str) -> LoadPlan:
        """The in-database call. Postgres fetches the published file itself."""
        cfg = self._cfg(config)
        url = raw_url(cfg['published'])
        return LoadPlan(
            sql=f"{cfg['loader']}('{url}', '{cfg['jurisdiction']}')",
            url=url,
            expect={'seen': 20, 'note': 'verified tables are skipped, never overwritten'},
        )


@register('pdf_code')
def _factory() -> PdfCodeAdapter:
    return PdfCodeAdapter()


if __name__ == '__main__':
    sys.path.insert(0, _ROOT)
    a = PdfCodeAdapter()
    which = sys.argv[2] if len(sys.argv) > 2 else 'duluth'
    if '--discover' in sys.argv:
        for t in a.discover(which):
            print(f"  {t['label']:6} p{t['page']:<5} {t['title'][:60]}")
    elif '--plan' in sys.argv:
        print(a.upsert(which))
    else:
        print(__doc__)
