#!/usr/bin/env python3
"""
Tests for the OCR pass, with the PDF reader and tesseract stubbed out.

Neither pymupdf nor tesseract is available in CI, and neither is where this
script went wrong: the failures were an empty queue reported as success, whole
documents relabelled as OCR when most of their text was the publisher's, and a
page cap that silently dropped 39% of the corpus. All three are testable with no
OCR engine at all, which is the point.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest" / "duluth_agendas"))
import ocr_scanned as ocr  # noqa: E402


class FakeDoc:
    """A PDF where each page is either publisher text or a scan (empty text)."""
    def __init__(self, pages: list[str]):
        self._pages = pages
        self.page_count = len(pages)


def fake_open(pages: list[str]):
    return lambda path: FakeDoc(pages)


def fake_text(doc, i):
    return doc._pages[i]


def fake_png(doc, i, dpi=220):
    return f"PNG:{i}".encode()


def fake_ocr(png: bytes) -> str:
    i = int(png.decode().split(":")[1])
    return f"recovered words from scanned page {i} " * 4


def run(pages, max_pages=None):
    return ocr.ocr_document(
        Path("/dev/null"), max_pages,
        _open=fake_open(pages), _text=fake_text, _png=fake_png, _ocr=fake_ocr)


class TestPageSelection(unittest.TestCase):
    def test_only_scanned_pages_are_ocred(self):
        # 5 pages: 0 and 3 are scans, the rest carry real text
        r = run(["", "x" * 500, "y" * 500, "", "z" * 500])
        self.assertEqual(r["ocr_page_numbers"], [1, 4], "1-indexed, scanned pages only")
        self.assertEqual(r["pages_total"], 5)

    def test_partially_scanned_packet_keeps_its_publisher_text(self):
        """The bug that mattered: a 382-page binder with 154 scanned pages had
        449,287 characters of genuine publisher text. Marking the whole document
        'ocr' would have destroyed the ability to quote any of it."""
        pages = ["x" * 3000] * 228 + [""] * 154
        r = run(pages)
        self.assertEqual(r["text_source"], "mixed")
        self.assertEqual(len(r["ocr_page_numbers"]), 154)
        self.assertGreater(r["embedded_chars"], 400_000)
        self.assertGreater(r["ocr_chars"], 0)

    def test_fully_scanned_minutes_are_pure_ocr(self):
        r = run([""] * 14)
        self.assertEqual(r["text_source"], "ocr")
        self.assertEqual(r["embedded_chars"], 0)
        self.assertEqual(len(r["ocr_page_numbers"]), 14)

    def test_readable_document_is_left_alone(self):
        r = run(["x" * 900] * 3)
        self.assertEqual(r["text_source"], "embedded")
        self.assertEqual(r["ocr_page_numbers"], [])
        self.assertEqual(r["ocr_status"], "nothing_to_do")

    def test_a_nearly_blank_page_counts_as_scanned(self):
        r = run(["short", "x" * 500])           # under MIN_PAGE_CHARS
        self.assertEqual(r["ocr_page_numbers"], [1])

    def test_ocr_text_is_page_labelled(self):
        r = run(["", "x" * 500, ""])
        self.assertIn("[page 1]", r["text_ocr"])
        self.assertIn("[page 3]", r["text_ocr"])
        self.assertNotIn("[page 2]", r["text_ocr"])


class TestPageCap(unittest.TestCase):
    def test_no_cap_by_default(self):
        r = run([""] * 382)
        self.assertEqual(len(r["ocr_page_numbers"]), 382)
        self.assertEqual(r["ocr_pages_dropped"], [])

    def test_cap_reports_exactly_what_it_dropped(self):
        """The old 60-page cap dropped 417 of the queue's 1,059 pages without
        naming one of them."""
        r = run([""] * 100, max_pages=60)
        self.assertEqual(len(r["ocr_page_numbers"]), 60)
        self.assertEqual(len(r["ocr_pages_dropped"]), 40)
        self.assertEqual(r["ocr_pages_dropped"][0], 61)


class TestQueue(unittest.TestCase):
    ROWS = [
        {"sha256": "a", "quality": "scanned_no_text", "filename": "mins.pdf"},
        {"sha256": "b", "quality": "partially_scanned", "filename": "binder.pdf"},
        {"sha256": "c", "quality": "text_ok", "filename": "agenda.pdf"},
    ]

    def test_no_local_pdfs_yields_an_empty_queue_and_names_the_misses(self):
        """This is the silent no-op. No row in the published corpus carries
        local_path, so the original filter produced an empty queue, wrote an
        output identical to its input, and exited 0."""
        jobs, missing, candidates = ocr.build_queue(self.ROWS, None)
        self.assertEqual(jobs, [])
        self.assertEqual(len(candidates), 2, "text_ok is correctly excluded")
        self.assertEqual({r["sha256"] for r in missing}, {"a", "b"})

    def test_pdfs_are_found_by_filename_in_pdf_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "mins.pdf").write_bytes(b"%PDF-1.4")
            jobs, missing, _ = ocr.build_queue(self.ROWS, d)
            self.assertEqual([j[0] for j in jobs], ["a"])
            self.assertEqual([r["sha256"] for r in missing], ["b"])

    def test_pdfs_are_also_found_by_sha_filename(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "b.pdf").write_bytes(b"%PDF-1.4")
            jobs, _, _ = ocr.build_queue(self.ROWS, d)
            self.assertEqual([j[0] for j in jobs], ["b"])

    def test_explicit_local_path_wins(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            row = {"sha256": "z", "quality": "scanned_no_text", "local_path": f.name}
            jobs, missing, _ = ocr.build_queue([row], None)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(missing, [])


class TestWorkerErrors(unittest.TestCase):
    def test_a_failing_document_is_reported_not_swallowed(self):
        res = ocr._worker(("sha1", "/nonexistent/does-not-exist.pdf", None))
        self.assertTrue(res["ocr_status"].startswith("error:"))
        self.assertEqual(res["sha256"], "sha1")
        self.assertIn("ocr_error", res, "the reason must survive, not just the fact")


if __name__ == "__main__":
    unittest.main(verbosity=2)
