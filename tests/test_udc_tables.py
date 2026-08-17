"""
The UDC extractor against the hand-verified fixture.

Two assertions, and the first is the one that matters most.

DISCOVERY COUNT. The document announces its own tables by printing "Table N-X" as a
title line. If the number the document announces is not the number extracted, the
corpus is missing a table -- and a missing table is invisible: every page that does
exist renders perfectly. Table 4-C and Table 12-A were absent for weeks because
discovery required the literal "Table 4-C:" and the document does not always punctuate
that way. This check, alone, would have caught both on day one.

SHAPE. n_cols, header and n_rows must reproduce tests/fixtures/duluth_udc_tables.json,
which was transcribed by eye from rendered page images. Cells are NOT asserted here:
nobody has checked most of them, and a test that pretended otherwise would be the
thing this repo exists to avoid.

Needs the source PDF, which is gitignored (8.6 MB, and its filename encodes the
amendment date). Skips loudly rather than passing vacuously when it is absent:

    curl -sL https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf \\
         -o var/duluth_udc.pdf
    python3 -m pytest tests/test_udc_tables.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PDF = os.environ.get('UDC_PDF', os.path.join(ROOT, 'var', 'duluth_udc.pdf'))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'duluth_udc_tables.json')

# The filename changes on every amendment, so it is the change-detection signal and
# must never be hardcoded anywhere that fetches. Here it pins WHICH document the
# hand-verified fixture describes: a different hash means every table needs
# re-verifying against the new render, and these assertions are void until it happens.
SHA256 = '2311ae985c3f1e46cb84844fdb09bfe92b89917572e112c29b78cb9fe94a48c0'

needs_pdf = pytest.mark.skipif(
    not os.path.exists(PDF),
    reason=f'source PDF not present at {PDF} -- see this module docstring',
)


@pytest.fixture(scope='module')
def truth():
    return json.load(open(FIXTURE))['tables']


@pytest.fixture(scope='module')
def doc():
    import pymupdf
    return pymupdf.open(PDF)


@needs_pdf
def test_pdf_is_the_document_the_fixture_describes():
    digest = hashlib.sha256(open(PDF, 'rb').read()).hexdigest()
    assert digest == SHA256, (
        'the UDC has been amended since the fixture was verified; every table must be '
        're-checked against the new render before these assertions mean anything'
    )


@needs_pdf
def test_discovery_finds_exactly_the_tables_the_fixture_names(doc, truth):
    from ingest.pdf.extract_cells import discovered_tables
    found = {(label, page) for page, label, _ in discovered_tables(doc)}
    expected = {(t['label'], t['page_from']) for t in truth}
    assert len(found) == len(expected), (
        f'the document announces {len(found)} tables, the fixture describes '
        f'{len(expected)}'
    )
    assert found == expected, (
        f'announced but not in the fixture: {sorted(found - expected)}; '
        f'in the fixture but never announced: {sorted(expected - found)}'
    )


def test_superscript_fold_leaves_stacked_values_alone():
    """The marker fold must tell a footnote from a value stacked above another.

    "2\\nSingle-Family Residential" is a superscript that reading order put first
    (7-A). "3\\n5" is two parking ratios in one ruled cell (4-B row 16), and folding
    them produced "53" -- ten cells corrupted this way before anyone read the page.
    """
    from ingest.pdf.extract_cells import fix_superscripts
    assert fix_superscripts('2\nSingle-Family Residential') == 'Single-Family Residential2'
    assert fix_superscripts('3\n5') == '3\n5'
    assert fix_superscripts('20\n18') == '20\n18'
    assert fix_superscripts('4\n3\n10') == '4\n3\n10'
    assert fix_superscripts('1½\n1') == '1½\n1'


@needs_pdf
@pytest.mark.parametrize('label,page', [
    ('2-B', 52), ('2-C', 56), ('2-C', 70), ('2-D', 85), ('2-D', 89),
    ('3-A', 96), ('3-B', 102), ('4-A', 136), ('4-B', 139), ('4-C', 142),
    ('5-A', 149), ('6-A', 170), ('6-B', 172), ('6-E', 175), ('7-A', 189),
    ('7-B', 199), ('7-C', 210), ('9-A', 246), ('9-B', 262), ('12-A', 363),
])
def test_extraction_reproduces_the_fixture_shape(truth, label, page):
    from ingest.pdf.extract_cells import extract_table
    spec = next(t for t in truth if t['label'] == label and t['page_from'] == page)
    got = extract_table(spec)

    width = max((len(r) for r in got['rows']), default=spec['n_cols'])
    assert width == spec['n_cols'], f'{label}: rows are {width} wide, fixture says {spec["n_cols"]}'

    # n_rows is null where the source rows were never hand-counted. Null means "not
    # asserted", and asserting a count nobody counted is the defect this file guards.
    if spec['n_rows'] is not None:
        assert got['n_rows'] == spec['n_rows'], (
            f'{label}: extracted {got["n_rows"]} rows, fixture says {spec["n_rows"]}'
        )

    # Where the fixture lists the row labels, they must appear in order. This is a far
    # stronger check than the count: 2-B's old extraction had a plausible 15 rows that
    # simply stopped at the page boundary.
    if spec.get('row_keys'):
        keys = [r[0].replace('\n', ' ').replace('Commercia l', 'Commercial')
                for r in got['rows']]
        assert keys == spec['row_keys'], f'{label}: row labels differ from the fixture'
