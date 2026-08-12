#!/usr/bin/env python3
"""
Grid-aligned table extraction for the Duluth UDC.

pdfplumber's per-row cell lists are NOT column-stable: in Table 2-B the lot-size
value lands at index 1 for RA-200 but index 2 for R-100, because merged and
wrapped cells shift the row's own cell list. Any lookup like row[7] == "Front
Setback" is therefore wrong for some districts -- silently, and only for some
rows, which is the worst way to be wrong.

Fix: derive the table's column boundaries once by clustering all cell x-edges,
then assign every WORD on the page to a (row, column) slot by geometry. Column
identity then comes from the page, not from a row's cell count.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
OUT = HERE / "udc_tables.jsonl"
X_TOL = 6.0   # points; edges closer than this are the same rule
Y_TOL = 3.0


def cluster(vals: list[float], tol: float) -> list[float]:
    vals = sorted(vals)
    out = [vals[0]]
    for v in vals[1:]:
        if v - out[-1] > tol:
            out.append(v)
        else:
            out[-1] = (out[-1] + v) / 2
    return out


def grid_extract(page, table):
    cells = [c for r in table.rows for c in r.cells if c]
    if not cells:
        return None

    # Columns: cluster x-edges (stable -- vertical rules run the table's height).
    xedges = cluster([c[0] for c in cells] + [c[2] for c in cells], X_TOL)
    if len(xedges) < 3:
        return None

    # Rows: use each Table row's OWN bbox, never clustered y-edges. A cell with
    # two lines of text ("18,000 with sewage / 25,000 with septic tank") spans a
    # tall visual row; clustering its internal line gaps invents extra bands and
    # the second line lands in the next district's row -- which silently moved
    # R-100's lot size onto RA-200 and dropped RA-200's "75, local streets".
    bands = []
    for r in table.rows:
        bb = r.bbox
        if bb and bb[3] > bb[1]:
            bands.append((bb[1], bb[3]))
    bands.sort()
    merged = []
    for top, bot in bands:
        if merged and top < merged[-1][1] - Y_TOL:
            merged[-1] = (merged[-1][0], max(merged[-1][1], bot))
        else:
            merged.append((top, bot))
    if len(merged) < 2:
        return None

    ncol, nrow = len(xedges) - 1, len(merged)
    grid = [["" for _ in range(ncol)] for _ in range(nrow)]

    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        xm, ym = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
        if not (xedges[0] - X_TOL <= xm <= xedges[-1] + X_TOL):
            continue
        ri = next((i for i, (t0, b0) in enumerate(merged)
                   if t0 - Y_TOL <= ym <= b0 + Y_TOL), None)
        if ri is None:
            continue
        ci = max(0, min(ncol - 1, sum(1 for e in xedges[1:-1] if xm >= e)))
        grid[ri][ci] = (grid[ri][ci] + " " + w["text"]).strip()

    return [[re.sub(r"\s+", " ", c).strip() for c in row] for row in grid]


def fold_header(rows):
    """Leading rows until the first row whose column 0 is populated = header."""
    hdr, i = [], 0
    while i < len(rows) and not rows[i][0]:
        hdr.append(rows[i]); i += 1
    if i < len(rows) and not hdr:
        hdr.append(rows[i]); i += 1
    if not hdr:
        return [], rows
    width = len(rows[0])
    header = []
    for c in range(width):
        seen, parts = set(), []
        for r in hdr:
            v = r[c] if c < len(r) else ""
            if v and v not in seen:
                seen.add(v); parts.append(v)
        header.append(" ".join(parts))
    return header, rows[i:]


def merge_wrapped(rows):
    """A row with no column-0 value is a wrapped continuation of the row above."""
    out = []
    for r in rows:
        if out and not r[0] and any(r):
            for c in range(len(r)):
                if r[c]:
                    out[-1][c] = (out[-1][c] + " " + r[c]).strip()
        elif any(r):
            out.append(list(r))
    return out


def to_markdown(header, rows):
    w = len(header)
    lines = ["| " + " | ".join(h or " " for h in header) + " |",
             "|" + "|".join("---" for _ in range(w)) + "|"]
    for r in rows:
        r = (list(r) + [""] * w)[:w]
        lines.append("| " + " | ".join(c.replace("|", "\\|") or " " for c in r) + " |")
    return "\n".join(lines)


def main() -> int:
    secs = [json.loads(l) for l in (HERE / "udc_sections.jsonl").open()]
    tabs = [s for s in secs if s["kind"] == "table"]
    results = []

    with pdfplumber.open(HERE / "udc.pdf") as pdf:
        for t in tabs:
            grids = []
            for pno in range(t["page_from"] - 1, min(t["page_to"], len(pdf.pages))):
                page = pdf.pages[pno]
                for tb in page.find_tables():
                    g = grid_extract(page, tb)
                    if g and len(g) >= 2 and len(g[0]) >= 3:
                        grids.append((pno + 1, g))
            if not grids:
                continue

            width = max(len(g[0]) for _, g in grids)
            first = min(p for p, g in grids if len(g[0]) == width)
            base = max((g for p, g in grids if p == first and len(g[0]) == width), key=len)
            header, body = fold_header(base)
            body = merge_wrapped(body)
            sig = {c for c in header if c}

            for p, g in grids:
                if p == first and g is base:
                    continue
                if len(g[0]) != width:
                    continue
                _, more = fold_header(g)
                more = merge_wrapped(more)
                for r in more:
                    if sum(1 for c in r if c and c in sig) >= max(2, len(r) // 3):
                        continue
                    body.append(r)

            results.append({
                "citation": t["citation"], "title": t["title"],
                "page_from": t["page_from"], "page_to": t["page_to"],
                "n_cols": len(header), "n_rows": len(body),
                "header": header, "rows": body,
                "markdown": to_markdown(header, body),
                "source_url": t["source_url"],
            })

    with OUT.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"tables recovered: {len(results)}")
    for r in results:
        print(f"  {r['citation']:<24} {r['n_cols']:>2} cols x {r['n_rows']:>3} rows | {r['title'][:42]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
