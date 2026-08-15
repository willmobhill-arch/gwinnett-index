"""
Pass C: table CELLS from the ruled grid, with the verified header as the authority.

This inverts what passes A and B do, and the inversion is the point.

Pass A extracted headers from pymupdf4llm markdown and pass B tried to score a
geometry header against it and pick a winner. That heuristic is documented as having
picked wrong on 3-A and 2-C, and it still does: rerunning it accepts geometry for
2-C and yields ``['', 'PRINCIPAL USES', 'R-TH', 'RA-200 Parking, 2022', ...]`` over a
correct markdown header. There is no scoring function that reliably beats a person
looking at the page, so this module stops trying to find one.

Instead, ``tests/fixtures/duluth_udc_tables.json`` -- transcribed by eye from rendered
page images -- supplies header, n_cols and spanning_header. The PDF supplies cells.
Where the two disagree about the SHAPE of the table, that is reported as a failure
rather than reconciled, because a silent reconciliation is how a value ends up in the
wrong column while still looking plausible.

Cells come from ``find_tables()``, not from markdown. The markdown path produced every
row-count defect in the corpus, all of them by mistaking something else for a data row:

  * 4-A  16 rows vs 6. The page carries THREE tables -- Table 4-A and then a worked
         example with the same column count. The markdown path concatenated them, so
         a shared-parking percentage table gained a "TOTAL 928" row.
  * 9-A  13 rows vs 8. Rows 6-8 are single ruled cells holding three lines each
         ("Local Street / Residential Urban / Residential Urban Cul-de-sac"). Split on
         text lines they become separate rows, two of which have no values at all.
  * 3-A, 7-A, 9-B  one row too many: the spanning label was taken as the header, so
         the real header row was counted as data.
  * 4-C  one column instead of two, because the column rule is not drawn.

find_tables() gets all of these right, and it preserves newlines inside a cell, which
is required: flattening 9-A's "60 feet(3)\\n60 foot radius" into one line turns two
values for two street types into one unreadable string.

find_tables() SEGFAULTS on page 175, so every call runs in a subprocess. In-process it
takes down the whole run and leaves an output file that looks complete -- the failure
shape this repo keeps hitting.

    python3 -m ingest.pdf.extract_cells            # -> var/extracted_cells.json
    python3 -m ingest.pdf.extract_cells --page 246 # one page, for debugging
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
PDF = os.environ.get('UDC_PDF', os.path.join(_ROOT, 'var', 'duluth_udc.pdf'))
FIXTURE = os.environ.get('UDC_FIXTURE',
                         os.path.join(_ROOT, 'tests', 'fixtures', 'duluth_udc_tables.json'))
OUT = os.environ.get('UDC_CELLS', os.path.join(_ROOT, 'var', 'extracted_cells.json'))
PAGE_TIMEOUT = 180


def discovered_tables(doc) -> list[tuple[int, str, str]]:
    """[(page, label, title)] for the tables the DOCUMENT itself announces.

    Independent of the fixture on purpose. Counting the titles the document prints and
    comparing that to the number of tables extracted is the single check that would
    have caught 4-C and 12-A on day one -- both were absent from the corpus for weeks
    because discovery demanded the literal "Table 4-C:" and the document does not
    always punctuate that way. An extractor reporting 18 tables from a document that
    announces 20 is not a smaller result, it is a wrong one.

    A table that runs over a page reprints its title as a page header, so a label
    repeated on the NEXT page continues the same table. The comparison has to be
    against the previous raw sighting, not the last one kept: Table 12-A prints its
    title on 363, 364 and 365, and measuring the gap from 363 makes page 365 look like
    a second table three pages later.
    """
    from ingest.pdf.extract_tables import discover, dedupe
    out: list[tuple[int, str, str]] = []
    last_seen: dict[str, int] = {}
    for page, label, title in dedupe(discover(doc)):
        prev = last_seen.get(label)
        last_seen[label] = page
        if prev is not None and page - prev <= 1:
            continue
        out.append((page, label, title))
    return out


def norm(s: str | None) -> str:
    """Collapse runs of spaces but KEEP newlines: they separate values in a cell."""
    if not s:
        return ''
    s = s.replace(' ', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    return '\n'.join(line.strip() for line in s.split('\n')).strip()


# The UDC draws thick double borders: one visual column boundary is two ruled lines
# a few points apart (180.9 and 186.2 for the same edge), and find_tables reads each
# as its own edge -- 9-B comes out 28 columns wide for a 14-column table, with a
# sliver column between every real pair. Snapping merges them. Calibrated against
# seven tables whose column counts are hand-verified: 6 and 10 both give every count
# correctly, 2 gives none, and 14 is too far and collapses 9-B to 11. 8 is the middle
# of the working range, not a guess.
SNAP_X = float(os.environ.get('UDC_SNAP_X', 8))


# A boundary ruled across less than this fraction of the table width is not a row
# boundary, it is a division INSIDE a cell. See starts_new_row().
MERGE_COVER = float(os.environ.get('UDC_MERGE_COVER', 0.5))


def _h_segments(page, bbox):
    """Horizontal drawn segments inside bbox, as (y, x0, x1).

    The UDC does not draw a table border as one long line: every cell edge is its own
    short segment, so asking "is there a full-width line here" finds nothing. Coverage
    has to be measured as the union of the segments at that y.
    """
    x0b, y0b, x1b, y1b = bbox
    out = []
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0] == 'l':
                a, b = item[1], item[2]
                if abs(a.y - b.y) < 1.2:
                    out.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
            elif item[0] == 're':
                r = item[1]
                if r.height < 1.5:                     # a hairline rectangle IS a rule
                    out.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    return [s for s in out if s[1] >= x0b - 6 and s[2] <= x1b + 6 and y0b - 6 <= s[0] <= y1b + 6]


def _coverage(segs, y, x0b, x1b, tol=2.5):
    """Fraction of the table width ruled at height y."""
    spans = sorted((max(s[1], x0b), min(s[2], x1b)) for s in segs if abs(s[0] - y) <= tol)
    total, a0, b0 = 0.0, None, None
    for a, b in spans:
        if a0 is None:
            a0, b0 = a, b
        elif a <= b0 + 1.0:
            b0 = max(b0, b)
        else:
            total += b0 - a0
            a0, b0 = a, b
    if a0 is not None:
        total += b0 - a0
    return total / max(x1b - x0b, 1e-6)


def grids_on_page(page_no: int) -> list[dict]:
    """[{bbox, rows, starts_row}] for every ruled table on a 1-based page.

    ``starts_row[i]`` is False when grid row i is a subdivision inside the row above
    rather than a row of its own. Table 2-B's "CBD (Residential uses)" row carries
    three stacked entries in its setback columns -- Single-family, Townhouse, Apartment
    -- each ruled off from the next. find_tables sees four rows; the printed table has
    one, and the fixture's 20 district rows depend on that being understood. Measured:
    those internal rules span 0.11-0.34 of the table width, while every real row
    boundary in 2-B spans 1.00 and even 6-B's thinnest genuine boundary spans 0.75.
    """
    import pymupdf
    doc = pymupdf.open(PDF)
    page = doc[page_no - 1]
    out = []
    for t in page.find_tables(snap_x_tolerance=SNAP_X).tables:
        segs = _h_segments(page, t.bbox)
        x0b, x1b = t.bbox[0], t.bbox[2]
        starts = [i == 0 or _coverage(segs, r.bbox[1], x0b, x1b) >= MERGE_COVER
                  for i, r in enumerate(t.rows)]
        rows = [[norm(c) for c in r] for r in t.extract()]
        out.append({'bbox': list(t.bbox), 'rows': rows, 'starts_row': starts})
    return out


def fix_superscripts(cell: str) -> str:
    """Move a leading footnote marker back onto the text it annotates.

    A superscript sits slightly ABOVE its word, so reading order puts it on its own
    line first: Table 7-A's "Single-Family Residential2" arrives as "2\nSingle-Family
    Residential". Left alone the cell starts with a number, which in a table of
    setback distances reads as a measurement.
    """
    lines = cell.split('\n')
    if len(lines) >= 2 and re.fullmatch(r'\d{1,2}', lines[0].strip()):
        return '\n'.join([lines[1].strip() + lines[0].strip()] + lines[2:]).strip()
    return cell


def merge_subdivided(rows: list[list[str]], starts: list[bool]) -> list[list[str]]:
    """Fold each in-cell subdivision back into the row it belongs to.

    Cells join with a newline, which is how the source prints them and how they stay
    recoverable: "Single-family:\nDetached - 12" and "Townhouse: 5(9)" are two entries
    in one cell, and running them together on one line would read as a single value.
    """
    out: list[list[str]] = []
    for row, starts_new in zip(rows, starts):
        if out and not starts_new:
            prev = out[-1]
            for i, cell in enumerate(row):
                if not cell:
                    continue
                prev[i] = f'{prev[i]}\n{cell}' if prev[i] else cell
        else:
            out.append(list(row))
    return out


def grids_on_page_isolated(page_no: int) -> list[dict]:
    """Same, in a child process, so page 175 costs one page instead of the run."""
    r = subprocess.run([sys.executable, '-m', 'ingest.pdf.extract_cells',
                        '--page', str(page_no)],
                       capture_output=True, text=True, timeout=PAGE_TIMEOUT, cwd=_ROOT)
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


def drop_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    """Remove columns that are empty in every row.

    Merged header cells make find_tables report a phantom leading column on 4-A: the
    grid is 7 wide where the table has 6 headings and every cell of column 0 is empty.
    """
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i] for r in rows)]
    return [[r[i] for i in keep] for r in rows]


def is_header_echo(row: list[str], header: list[str], spanning: str | None) -> bool:
    """True for a repeat of the header, or of the spanning label, on a later page.

    Compared case- and punctuation-insensitively: the header is printed with footnote
    markers that the grid sometimes keeps and sometimes drops.
    """
    def key(cells):
        return [re.sub(r'[^a-z0-9]', '', (c or '').lower()) for c in cells]
    rk, hk = key(row), key(header)
    if rk == hk:
        return True
    # a spanning row: the label sits over the data columns and the rest is empty
    if spanning:
        joined = re.sub(r'[^a-z0-9]', '', ''.join(row).lower())
        if joined and joined in re.sub(r'[^a-z0-9]', '', spanning.lower()):
            return True
    # header echo where the grid merged the leading label cell away
    if len(rk) == len(hk) and sum(a == b for a, b in zip(rk, hk)) >= len(hk) - 1:
        return sum(1 for a in rk if a) > 1
    return False


def strip_header_band(rows: list[list[str]], header: list[str],
                      spanning: str | None) -> list[list[str]]:
    """Drop the leading header rows of one page's grid.

    The header is not one grid row. Horizontal rules inside the header band survive
    snapping, so 3-A's three-line header arrives as EIGHT grid rows -- "Measured in
    Horizontal" and "Footcandles" land in different rows of the same column. Counting
    those as data is what made a 3-row table report 11.

    Two rules, and the second is deliberately narrow. A leading row is header if it is
    empty, or an echo of the header, or it has AT MOST ONE non-empty cell whose text
    appears in the header text. The one-cell condition is what keeps this safe: 9-B's
    first data row is "15 | 20 | 20 | ..." and the digits "15" do appear inside its
    header ("...13 14 15 16"), so a pure substring test would delete a real row of a
    pipe-depth table. A row carrying two or more values is data, always.
    """
    vocab = re.sub(r'[^a-z0-9]', '', (' '.join(header) + ' ' + (spanning or '')).lower())
    i = 0
    while i < len(rows):
        row = rows[i]
        filled = [c for c in row if c]
        if not filled:
            i += 1
            continue
        if is_header_echo(row, header, spanning):
            i += 1
            continue
        # the printed caption sits inside the grid on 9-B: "Table 9-B: Maximum Pipe
        # Invert Depth (feet)" is a row of the table as far as the ruling is concerned
        if len(filled) == 1 and re.match(r'table\s*\d+-[a-z]\b', filled[0], re.I):
            i += 1
            continue
        # A row whose every non-empty cell is, IN ITS OWN COLUMN, a piece of that
        # column's heading. 2-B's header occupies two grid rows -- "Zoning District |
        # Lot size | Density" then "| (minimum, square feet)(8) | (maximum, dwelling
        # units per gross acre)" -- and both fill all ten columns, so the count-based
        # test below cannot see them. Positional containment can, and safely: a row of
        # lot sizes is not a substring of the words "Lot size (minimum, square feet)".
        if all(not c or re.sub(r'[^a-z0-9]', '', c.lower())
               in re.sub(r'[^a-z0-9]', '', (header[j] if j < len(header) else '').lower())
               for j, c in enumerate(row)):
            i += 1
            continue
        # A row with FEWER filled cells than the table has columns, every one of them
        # text that appears in the header, is a header fragment. The "fewer than
        # n_cols" half is the safety: 9-B's data rows fill all 14 columns, so no row
        # of real pipe depths can be swallowed however much its digits resemble the
        # column names.
        if len(filled) < len(header):
            frags = [re.sub(r'[^a-z0-9]', '', c.lower()) for c in filled]
            if all(f and f in vocab for f in frags):
                i += 1
                continue
        break
    return rows[i:]


def extract_table(spec: dict) -> dict:
    """Cells for one fixture table. Header/n_cols come from the fixture, cells from the PDF."""
    label, header = spec['label'], spec['header']
    n_cols, spanning = spec['n_cols'], spec.get('spanning_header')
    p_from = spec['page_from']
    p_to = spec.get('page_to') or p_from

    rows: list[list[str]] = []
    notes: list[str] = []
    for page_no in range(p_from, p_to + 1):
        grids = grids_on_page_isolated(page_no)
        if not grids:
            notes.append(f'p{page_no}: no ruled table found')
            continue
        # On the first page take the topmost grid: a page can carry the table AND a
        # worked example below it (4-A), and the example is not part of the table.
        # On later pages take every grid whose width matches after empty columns go,
        # because a table continuing across pages is drawn as one grid per page.
        candidates = [grids[0]] if page_no == p_from else grids
        for g in candidates:
            starts = g.get('starts_row') or [True] * len(g['rows'])
            # Order matters three ways, and each wrong order fails silently.
            #
            # Empty columns are decided from the WHOLE grid, header rows included:
            # 2-D's first column holds "NAICS 2022" in the header and nothing in most
            # data rows, so deciding after the header is stripped deletes a real
            # column and the table comes out 10 wide instead of 11.
            #
            # The header band is stripped BEFORE subdivisions are folded: folding
            # first merged 3-A's header into the first data row, so the cell holding
            # "0.5" arrived as "Measured in Horizontal\nFootcandles\n0.5" -- a real
            # value with its own column heading glued on top of it.
            gr = drop_empty_columns(g['rows'])
            dropped = len(gr) - len(strip_header_band(gr, header, spanning))
            gr = merge_subdivided(gr[dropped:], starts[dropped:])
            if not gr:
                continue
            width = max(len(r) for r in gr)
            if width != n_cols:
                if page_no == p_from:
                    notes.append(f'p{page_no}: grid is {width} wide, fixture says {n_cols}')
                continue
            for r in gr:
                r = r + [''] * (n_cols - len(r))
                if not any(r):
                    continue
                if is_header_echo(r, header, spanning):
                    continue
                rows.append([fix_superscripts(c) for c in r])

    return {
        'label': label,
        'title': spec['title'],
        'page_from': p_from,
        'page_to': p_to,
        # Hand-verified against the rendered page; NOT re-derived here. Saying
        # 'rendered-image' about a header a parser guessed would be a lie in a field
        # whose whole job is to say where the value came from.
        'header': header,
        'header_source': 'rendered-image',
        'spanning_header': spanning,
        'n_cols': n_cols,
        'n_rows': len(rows),
        'expected_rows': spec.get('n_rows'),
        'rows': rows,
        'notes': notes,
    }


def main() -> int:
    if '--page' in sys.argv:
        print(json.dumps(grids_on_page(int(sys.argv[sys.argv.index('--page') + 1]))))
        return 0

    fixture = json.load(open(FIXTURE))['tables']
    results, bad = [], 0
    print(f"{'lbl':6} {'pages':>9}  {'cols':>4}  {'rows':>13}  note")
    for spec in fixture:
        t = extract_table(spec)
        results.append(t)
        exp = t['expected_rows']
        if exp is None:
            verdict = f"{t['n_rows']:>4} (n/a)"     # fixture never counted these
        elif exp == t['n_rows']:
            verdict = f"{t['n_rows']:>4} ok    "
        else:
            verdict = f"{t['n_rows']:>4} != {exp:<4}"
            bad += 1
        note = '; '.join(t['notes'])[:44]
        print(f"{t['label']:6} {t['page_from']:>4}-{t['page_to']:<4} {t['n_cols']:>4}  {verdict:>13}  {note}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(results, open(OUT, 'w'), indent=1)
    asserted = sum(1 for t in results if t['expected_rows'] is not None)
    print(f"\n{len(results)} tables -> {OUT}")
    print(f"{asserted - bad}/{asserted} match the fixture's asserted row count "
          f"({len(results) - asserted} tables assert no count)")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
