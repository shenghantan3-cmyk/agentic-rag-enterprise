from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

# Import is heavy; keep it module-level to avoid re-init per request.
from paddleocr import PaddleOCR  # type: ignore


@dataclass
class OcrMeta:
    filename: str
    pages: int
    chars: int
    engine: str
    lang: str


# Chinese model (ch). Add "en" later if needed.
_OCR = PaddleOCR(lang="ch", use_angle_cls=True, show_log=False)


def _page_pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    mode = "RGB"
    if pix.alpha:
        # drop alpha
        pix = fitz.Pixmap(pix, 0)
    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    return img


def _ocr_image_lines(img: Image.Image) -> list[str]:
    arr = np.array(img)
    # PaddleOCR returns: [ [ [box], (text, score) ], ... ] per image
    result = _OCR.ocr(arr, cls=True)
    if not result:
        return []

    # Some versions return nested list per page
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list):
        blocks = result[0]
    else:
        blocks = result  # type: ignore

    lines: list[tuple[float, str]] = []
    for b in blocks or []:
        try:
            box, (text, score) = b
            # sort by y coordinate (top-left)
            y = float(box[0][1]) if box and box[0] else 0.0
            text = str(text).strip()
            if text:
                lines.append((y, text))
        except Exception:
            continue

    lines.sort(key=lambda x: x[0])
    return [t for _, t in lines]


def ocr_pdf_bytes_to_markdown(pdf_bytes: bytes, *, filename: str = "document.pdf") -> tuple[str, dict[str, Any]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    parts: list[str] = []
    total_chars = 0

    for i in range(doc.page_count):
        page = doc.load_page(i)
        # ~200 DPI rendering: scale 2
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = _page_pixmap_to_pil(pix)

        lines = _ocr_image_lines(img)
        page_text = "\n".join(lines).strip()

        parts.append(f"## Page {i+1}\n\n{page_text}\n")
        total_chars += len(page_text)

    markdown = "\n".join(parts).strip() + "\n"
    meta = asdict(
        OcrMeta(
            filename=filename,
            pages=int(doc.page_count),
            chars=int(total_chars),
            engine="paddleocr",
            lang="ch",
        )
    )

    return markdown, meta
