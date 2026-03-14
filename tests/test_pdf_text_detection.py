from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

# PyMuPDF historically used `import fitz`. Newer versions also provide `pymupdf`.
# If missing in the environment, skip these tests.
try:
    import pymupdf as _pymupdf  # type: ignore
except Exception:  # pragma: no cover
    try:
        import fitz as _pymupdf  # type: ignore
    except Exception:  # pragma: no cover
        _pymupdf = None  # type: ignore

if _pymupdf is None:  # pragma: no cover
    raise unittest.SkipTest("PyMuPDF not installed")

from project.utils import pdf_has_sufficient_text, pdf_text_length


def _make_pdf_with_text(path: str, text: str) -> None:
    doc = _pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _make_pdf_blank(path: str) -> None:
    doc = _pymupdf.open()
    doc.new_page()
    doc.save(path)
    doc.close()


class TestPdfTextDetection(unittest.TestCase):
    def test_pdf_text_length_blank(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "blank.pdf"
            _make_pdf_blank(str(pdf))
            self.assertEqual(pdf_text_length(str(pdf), max_pages=3), 0)

    def test_pdf_text_length_with_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "text.pdf"
            _make_pdf_with_text(str(pdf), "hello world")
            self.assertGreaterEqual(pdf_text_length(str(pdf), max_pages=3), 5)

    def test_pdf_has_sufficient_text_threshold_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "blank2.pdf"
            _make_pdf_blank(str(pdf))
            self.assertTrue(pdf_has_sufficient_text(str(pdf), threshold=0))

    def test_pdf_has_sufficient_text_threshold_high(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "text2.pdf"
            _make_pdf_with_text(str(pdf), "short")
            self.assertFalse(pdf_has_sufficient_text(str(pdf), threshold=9999))


if __name__ == "__main__":
    unittest.main()
