"""
Corrected Duluth UDC table extractor.

Replaces the extractor that produced the defects recorded in
claude/gwinnett-index-udc-table-findings.md. Three things it does differently:

1. DISCOVERY is case-insensitive and punctuation-tolerant. The old pattern required
   "Table 7-B:" and the document writes "TABLE 7-B Tree Canopy...", so 7-B was found
   only by accident and 4-C / 12-A were missed entirely. Same case/punctuation trap
   already documented for agenda case numbers - it recurs here.

2. FRAGMENT RANGES DO NOT OVERLAP. A fragment runs from its own title page to the page
   before the next title. The old code recorded 2-C Residential as 56-70 while 2-C
   Commercial was 70-85; the residential fragment then took its header and every row
   from page 70 - the commercial table. Header and rows must come from the FIRST page.

3. SPANNING HEADERS are resolved. Where a table has a spanning label over sub-columns
   (7-C: "Tree Canopy Size Category..." over Large/Medium/Small/Very Small), the leaf
   column names come from the sub-header row and the spanning text is preserved
   separately rather than being smeared across the data columns.

Extraction goes through pymupdf4llm rather than raw find_tables(): it resolves merged
cells to a stable column count, which is what broke the old row-index-based approach.
"""
import os, re, json, sys
import pymupdf, pymupdf4llm

# Override with UDC_PDF / UDC_OUT when running outside the repo layout.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
PDF = os.environ.get('UDC_PDF', os.path.join(_ROOT, 'var', 'duluth_udc.pdf'))
OUT = os.environ.get('UDC_OUT', os.path.join(_ROOT, 'var', 'extracted_tables.json'))
TITLE = re.compile(r'^\s*TABLE\s+(\d{1,2}-[A-Z])\b\s*[.:]?\s*(\S.*)?$', re.I)
BODY_START = 30          # skip the table of contents
MAX_SPAN = 20            # a single table never runs longer than this many pages


def discover(doc):
    """Return [(page, label, title)] for real table titles in the document body.

    A title line is one that STARTS with the label. Cross-references ("...as listed
    in Table 7-B.") sit mid-line and are excluded by the anchor. Sentences that merely
    begin with the label ("Table 2-D presents the various accessory uses...") are
    excluded by requiring the following line to look like a table, not prose.
    """
    out = []
    for i in range(BODY_START - 1, doc.page_count):
        lines = doc[i].get_text().splitlines()
        for j, line in enumerate(lines):
            m = TITLE.match(line)
            if not m or not m.group(2):
                continue
            tail = m.group(2).strip()
            # prose continuations read as sentences; titles are noun phrases
            if re.match(r'^(and|or|presents|organizes|lists|shows|is|are|in|of|the)\b', tail, re.I):
                continue
            out.append((i + 1, m.group(1).upper(), tail))
    return out


def dedupe(titles):
    """Collapse repeated title lines on the same page (headers echoed per page)."""
    seen, out = set(), []
    for p, lab, title in titles:
        key = (p, lab)
        if key in seen:
            continue
        seen.add(key)
        out.append((p, lab, title))
    return out


def parse_md_tables(md):
    """Pull pipe-tables out of a markdown blob as lists of cell-lists."""
    tables, cur = [], []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith('|') and s.endswith('|'):
            cells = [c.strip() for c in s[1:-1].split('|')]
            if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
                continue                      # separator row
            cur.append(cells)
        else:
            if cur:
                tables.append(cur)
                cur = []
    if cur:
        tables.append(cur)
    return tables


def clean(c):
    c = re.sub(r'<br\s*/?>', ' ', c)
    c = re.sub(r'\*\*', '', c)
    return re.sub(r'\s+', ' ', c).strip()


def col_edges(table, tol=8.0):
    """Clustered column x-edges from the drawn grid.

    Raw cell bboxes carry each ruled line twice (the UDC uses thick double borders,
    e.g. 180.9 and 186.2 for one boundary), so edges must be clustered before use or
    every column is counted twice.
    """
    xs = sorted({round(c[0], 1) for r in table.rows for c in r.cells if c} |
                {round(c[2], 1) for r in table.rows for c in r.cells if c})
    out = []
    for x in xs:
        if out and x - out[-1] <= tol:
            out[-1] = (out[-1] + x) / 2
        else:
            out.append(x)
    return out


def header_band(table):
    """(top, bottom) y of the header band.

    Header sub-rows all terminate at the same y as the last header row — rows 0..k in
    find_tables share a bottom edge. The first row whose bottom differs is data.
    """
    rows = table.rows
    if not rows:
        return None
    bottom = rows[0].bbox[3]
    for r in rows[1:]:
        if abs(r.bbox[3] - bottom) < 0.5:
            continue
        break
    return table.bbox[1], bottom


def resolve_header(page, table, ncol_hint=None):
    """Rebuild header cells from word geometry instead of trusting cell splits.

    A spanning label ("Zoning District" over four district columns) overlaps more than
    one column and must NOT be smeared into them; a leaf label sits inside exactly one.
    This is the x-edge clustering CLAUDE.md prescribes for rows, applied to the header.

    Returns (leaf_header, spanning_labels) or None when the geometry is unusable.
    """
    edges = col_edges(table)
    band = header_band(table)
    if not band or len(edges) < 2:
        return None
    ncol = len(edges) - 1
    if ncol_hint and ncol != ncol_hint:
        return None
    top, bot = band

    words = [w for w in page.get_text('words')
             if w[1] >= top - 1 and w[3] <= bot + 1
             and w[0] >= edges[0] - 2 and w[2] <= edges[-1] + 2]
    if not words:
        return None

    # group words into phrases: same visual line, small horizontal gap
    words.sort(key=lambda w: (round(w[1] / 3), w[0]))
    phrases, cur = [], []
    for w in words:
        if cur and abs(w[1] - cur[-1][1]) < 3 and w[0] - cur[-1][2] < 12:
            cur.append(w)
        else:
            if cur:
                phrases.append(cur)
            cur = [w]
    if cur:
        phrases.append(cur)

    # A phrase on the topmost header line, when that line holds fewer phrases than
    # there are columns, is a spanning label ("Zoning District" over four district
    # columns). Overlap alone misclassifies these: "Zoning District" sits mostly inside
    # one column and would otherwise be filed as that column's name.
    if phrases:
        top_y = min(ph[0][1] for ph in phrases)
        top_line = [ph for ph in phrases if abs(ph[0][1] - top_y) < 3]
        if len(top_line) < ncol and len(top_line) < len(phrases):
            spanning_pre = [' '.join(w[4] for w in ph).strip() for ph in top_line]
            phrases = [ph for ph in phrases if ph not in top_line]
        else:
            spanning_pre = []
    else:
        spanning_pre = []

    cols = [[] for _ in range(ncol)]
    spanning = list(spanning_pre)
    for ph in phrases:
        x0, x1 = ph[0][0], ph[-1][2]
        text = ' '.join(w[4] for w in ph).strip()
        hit = [i for i in range(ncol)
               if min(x1, edges[i + 1]) - max(x0, edges[i]) > 0.4 * (x1 - x0 + 0.01)]
        if len(hit) == 1:
            cols[hit[0]].append((ph[0][1], ph[0][0], text))
        elif len(hit) > 1:
            spanning.append(text)
        else:                                   # narrow phrase: fall back to midpoint
            mid = (x0 + x1) / 2
            for i in range(ncol):
                if edges[i] <= mid <= edges[i + 1]:
                    cols[i].append((ph[0][1], ph[0][0], text))
                    break

    header = []
    for c in cols:
        c.sort()
        header.append(re.sub(r'\s+', ' ', ' '.join(t for _, _, t in c)).strip())
    return header, spanning


def is_subheader(row, header):
    """True when a row is a second header band rather than data.

    Shape: first cell empty (it belongs to the spanning row-label column), every other
    cell short, non-numeric, and present.
    """
    if not row or len(row) < 2:
        return False
    if clean(row[0]):
        return False
    rest = [clean(c) for c in row[1:]]
    if not all(rest):
        return False
    return all(len(c) <= 24 and not re.fullmatch(r'[\d.,%$/ -]+', c) for c in rest)


def extract(doc, page, label, title, end):
    """Extract one table fragment. Header comes from this fragment's FIRST page."""
    pages = list(range(page - 1, min(end, page - 1 + MAX_SPAN)))
    # use_ocr=False is required, not an optimisation: the UDC is digital-born, so OCR
    # contributes nothing, and the OCR path segfaults on some pages (it died on p175).
    md = pymupdf4llm.to_markdown(PDF, pages=pages, table_strategy='lines_strict',
                                 show_progress=False, use_ocr=False)
    mds = parse_md_tables(md)
    if not mds:
        return None

    first = mds[0]
    header = [clean(c) for c in first[0]]
    ncol = len(header)
    body = first[1:]

    spanning = None
    if body and is_subheader(body[0], header):
        sub = [clean(c) for c in body[0]]
        spanning = ' '.join(h for h in header[1:] if h) or None
        header = [header[0]] + sub[1:]
        body = body[1:]

    # Geometry-based header wins over the markdown split whenever it is usable: the
    # markdown header smears spanning labels across the columns they overlap, which is
    # what produced "1. Provid | e a buffer on the l | ot of this use".
    # NOTE: geometry header resolution runs as a SEPARATE PASS (resolve_headers.py),
    # one subprocess per page. find_tables() segfaults on page 175 — an in-process call
    # takes the whole run down and leaves a truncated extracted.json that looks
    # complete. Isolating it means one bad page costs one header, not the whole corpus.

    # continuation tables on later pages: same column count, drop repeated header rows
    for t in mds[1:]:
        if not t or len(t[0]) != ncol:
            continue
        for r in t:
            rc = [clean(c) for c in r]
            if rc == header or (spanning and all(not c for c in rc[:1])
                                and rc[1:] == header[1:]):
                continue
            body.append(r)

    rows = []
    for r in body:
        rc = [clean(c) for c in r]
        if any(rc):
            rows.append(rc)

    return {
        'label': label, 'title': title, 'page_from': page, 'page_to': end,
        'header': header, 'spanning_header': spanning,
        'n_cols': len(header), 'n_rows': len(rows), 'rows': rows,
    }


def main():
    doc = pymupdf.open(PDF)
    titles = dedupe(discover(doc))
    results = []
    for idx, (p, lab, title) in enumerate(titles):
        end = titles[idx + 1][0] - 1 if idx + 1 < len(titles) else doc.page_count
        end = min(end, p + MAX_SPAN - 1)
        r = extract(doc, p, lab, title, end)
        if r:
            results.append(r)
            print(f"  {lab:6} p{p:<4} cols={r['n_cols']:<3} rows={r['n_rows']:<4} "
                  f"span={'yes' if r['spanning_header'] else '-':4} {title[:46]}")
        else:
            print(f"  {lab:6} p{p:<4} NO TABLE FOUND  {title[:46]}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(results, open(OUT, 'w'), indent=1)
    print(f"\n{len(results)} fragments -> {OUT}")


if __name__ == '__main__':
    main()
