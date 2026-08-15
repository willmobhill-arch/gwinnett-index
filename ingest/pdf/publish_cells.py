"""
Publish extracted UDC table cells as JSONL for the in-database loader.

Same shape as the other published artifacts (data/*.jsonl): Postgres fetches the
repo's own raw URL with the http extension and upserts, so no credentials move and
there is no worker in the path.

The quality flag is set HERE, from an explicit list, because it is a claim about what
a person did rather than something a parser can infer. VERIFIED_AGAINST_RENDER names
the tables whose every cell was compared against a rendered page image. Everything
else ships as 'unverified' and its cells stay withheld from the site and the API.

Why the previously-'defective' tables come back as 'unverified' and not 'defective':
'defective' asserts the stored cells are known WRONG, which was true of the old
extraction and is not true of this one. The corrected extractor reproduces 492 of 493
cells of the seven independently hand-transcribed tables, and every table's column
count, header and row count matches the hand-verified fixture. That is not proof the
cells are right -- nobody has read most of them -- but "known wrong" would now be a
false statement, and this project would rather say "unchecked" than say anything false.

    python3 -m ingest.pdf.extract_cells        # -> var/extracted_cells.json
    python3 -m ingest.pdf.publish_cells        # -> data/udc_table_cells.jsonl
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
CELLS = os.environ.get('UDC_CELLS', os.path.join(_ROOT, 'var', 'extracted_cells.json'))
OUT = os.environ.get('UDC_CELLS_JSONL', os.path.join(_ROOT, 'data', 'udc_table_cells.jsonl'))
SOURCE_URL = 'https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf'

# (label, page_from) -> what was actually checked, by eye, against page_from's render.
# Adding a line here is a claim that someone read the rendered page and compared every
# cell. The database CHECK will refuse the row if n_rows and the stored count disagree,
# but nothing except this comment stops a false claim, so do not make one.
VERIFIED_AGAINST_RENDER = {
    ('9-A', 246): 'Every cell compared against rendered p246 on 2026-08-15. The three '
                  'Local Street rows are single ruled rows carrying two entries each '
                  '(the street type and its cul-de-sac); the newlines inside those '
                  'cells are the source\'s own line breaks and are load-bearing.',
    ('3-B', 102): 'Every cell compared against rendered p102 on 2026-08-15. Five of the '
                  'nine rows carry Front/Side and Rear sub-entries inside one ruled '
                  'row; no rule separates them in the source.',
}

# Findings that live in a table's verification_note and are NOT about extraction
# quality. Overwriting the note wholesale deleted the Table 6-D finding, and the build
# gate that asserts the corpus names the tables the UDC cites but does not contain
# caught it -- which is the entire reason that gate exists.
PRESERVED = {
    ('6-E', 175):
        'ORDINANCE DEFECT (not ours): UDC sections 605.05 and 605.06 both cite '
        '"Table 6-D" for project entrance sign provisions, but NO Table 6-D exists in '
        'the document, and no Table 6-C either -- the sign tables run 6-A, 6-B, then '
        '6-E. The provisions those sections describe are in THIS table (6-E). Treat '
        '6-D as a stale cross-reference left by a renumbering. An agent asked about '
        'Table 6-D should be told it does not exist and pointed here.',
    ('12-A', 363):
        'Never extracted before 2026-08-14 -- the same discovery gap as 4-C. Header, '
        'row count (17) and page span (363-365, ONE table across three pages) were '
        'verified against the rendered pages; the cells are long prose blocks and are '
        'newly extracted, not yet read.',
}

UNVERIFIED_NOTE = (
    'Re-extracted 2026-08-15 from the ruled grid. Column count, header, page range and '
    'row count match tests/fixtures/duluth_udc_tables.json, which was transcribed by eye '
    'from rendered page images, and the same extractor reproduces 492/493 cells of the '
    'seven hand-transcribed tables. The CELLS OF THIS TABLE have not been read against '
    'the rendered page, so they are withheld. Previously flagged defective; that flag '
    'asserted the values were known wrong, which is no longer accurate.'
)


def main() -> int:
    tables = json.load(open(CELLS))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n_ver = 0
    with open(OUT, 'w') as fh:
        for t in tables:
            key = (t['label'], t['page_from'])
            note = VERIFIED_AGAINST_RENDER.get(key)
            n_ver += bool(note)
            fh.write(json.dumps({
                'citation': f"Duluth UDC Table {t['label']}",
                'title': t['title'],
                'page_from': t['page_from'],
                'page_to': t['page_to'],
                'header': t['header'],
                'spanning_header': t['spanning_header'],
                'header_source': 'rendered-image',
                'n_cols': t['n_cols'],
                'n_rows': len(t['rows']),
                'rows': t['rows'],
                'quality': 'verified' if note else 'unverified',
                'verification_note': ' '.join(
                    x for x in (note or UNVERIFIED_NOTE, PRESERVED.get(key)) if x),
                'source_url': SOURCE_URL,
            }, ensure_ascii=False) + '\n')
    size = os.path.getsize(OUT)
    print(f'{len(tables)} tables -> {OUT} ({size:,} bytes)')
    print(f'  {n_ver} claimed verified against a rendered page, {len(tables) - n_ver} unverified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
