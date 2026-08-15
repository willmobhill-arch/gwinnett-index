"""
Pass B: rebuild table headers from grid geometry, one subprocess per page.

Run standalone (`python3 resolve_headers.py <pdf_page>`) it prints JSON for that page.
Run with no argument it drives itself over extracted.json, spawning one child per page
and merging results.

Why subprocesses: PyMuPDF's find_tables() segfaults on page 175 of this document. An
in-process call kills the run and leaves a truncated extracted.json that looks
complete - the same "job that succeeds while doing nothing" shape this project keeps
hitting. Isolation converts a corpus-wide failure into one missing header.
"""
import json, subprocess, sys, os

HERE = os.path.abspath(__file__)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(HERE), '..', '..'))
PDF = os.environ.get('UDC_PDF', os.path.join(_ROOT, 'var', 'duluth_udc.pdf'))
EXTRACTED = os.environ.get('UDC_OUT', os.path.join(_ROOT, 'var', 'extracted_tables.json'))


def one(page, ncol_hint):
    import pymupdf
    from extract_tables import resolve_header
    doc = pymupdf.open(PDF)
    tf = doc[page - 1].find_tables()
    if not tf.tables:
        return None
    got = resolve_header(doc[page - 1], tf.tables[0], ncol_hint=ncol_hint)
    if not got:
        return None
    return {'header': got[0], 'spanning': got[1]}


def strip_markup(s):
    import re
    s = re.sub(r'<[^>]+>', '', s or '')
    s = s.replace('_', '').replace('*', '')
    return re.sub(r'\s+', ' ', s).strip()


def fragment_count(header, page_text):
    """How many adjacent header cells are halves of one split word.

    "All Other Nonresid" + "ential Properties" joins with no space into a string that
    appears verbatim in the page text - proof the label was cut across columns. This is
    an objective test, so the markdown header and the geometry header can be compared
    on evidence rather than on which one looks nicer.
    """
    import re
    flat = re.sub(r'\s+', '', page_text).lower()
    n = 0
    for a, b in zip(header, header[1:]):
        a, b = strip_markup(a), strip_markup(b)
        if not a or not b:
            continue
        joined = re.sub(r'\s+', '', a + b).lower()
        if len(joined) > 8 and joined in flat:
            n += 1
    return n


def score(header, page_text):
    """Lower is better: split labels first, then empty cells."""
    empties = sum(1 for c in header if not strip_markup(c))
    return (fragment_count(header, page_text), empties)


def main():
    if len(sys.argv) > 1:
        page = int(sys.argv[1])
        hint = int(sys.argv[2]) if len(sys.argv) > 2 else None
        print(json.dumps(one(page, hint)))
        return

    tables = json.load(open(EXTRACTED))
    ok = crashed = skipped = 0
    for t in tables:
        p, ncol = t['page_from'], t['n_cols']
        try:
            r = subprocess.run([sys.executable, HERE, str(p), str(ncol)],
                               capture_output=True, text=True, timeout=180,
                               cwd=os.path.dirname(HERE))
        except subprocess.TimeoutExpired:
            print(f"  {t['label']:6} p{p:<4} TIMEOUT"); crashed += 1; continue
        if r.returncode != 0:
            print(f"  {t['label']:6} p{p:<4} CRASHED rc={r.returncode} - header kept from pass A")
            t['header_source'] = 'markdown (geometry crashed)'
            crashed += 1
            continue
        try:
            got = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            got = None
        if not got or not any(got['header']):
            t['header_source'] = 'markdown (geometry unusable)'
            skipped += 1
            continue

        # Accept geometry only when it is measurably better. It reconstructs spanning
        # labels well but mangles the tightly-packed rotated headers of 2-B/2-C, where
        # the markdown split is correct.
        import pymupdf
        page_text = pymupdf.open(PDF)[p - 1].get_text()
        s_md, s_geo = score(t['header'], page_text), score(got['header'], page_text)
        if s_geo < s_md:
            t['header'] = got['header']
            t['header_source'] = 'geometry'
            if got['spanning']:
                t['spanning_header'] = ' '.join(got['spanning'])
            ok += 1
            print(f"  {t['label']:6} p{p:<4} GEOMETRY {s_md}->{s_geo}: {got['header']}")
        else:
            t['header_source'] = 'markdown'
            if got['spanning'] and not t.get('spanning_header'):
                t['spanning_header'] = ' '.join(got['spanning'])
            skipped += 1
            print(f"  {t['label']:6} p{p:<4} kept markdown (md={s_md} geo={s_geo})")

    json.dump(tables, open(EXTRACTED, 'w'), indent=1)
    print(f"\ngeometry-resolved={ok}  crashed={crashed}  unusable={skipped}  total={len(tables)}")


if __name__ == '__main__':
    main()
