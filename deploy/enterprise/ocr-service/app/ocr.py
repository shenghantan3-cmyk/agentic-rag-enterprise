from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .config import ocr_provider


@dataclass
class OcrMeta:
    filename: str
    pages: int
    chars: int
    engine: str
    provider: str
    table_pages: list[int]


def ocr_pdf_bytes_to_markdown(pdf_bytes: bytes, *, filename: str = "document.pdf") -> tuple[str, dict[str, Any]]:
    provider = ocr_provider()
    if provider == "tencent":
        from .tencent_ocr import ocr_pdf_bytes_to_markdown_tencent

        return ocr_pdf_bytes_to_markdown_tencent(pdf_bytes, filename=filename)

    if provider == "paddle":
        from .paddle_ocr import ocr_pdf_bytes_to_markdown as ocr_paddle

        md, meta = ocr_paddle(pdf_bytes, filename=filename)
        # normalize meta
        meta.setdefault("provider", "paddle")
        meta.setdefault("table_pages", [])
        return md, meta

    raise ValueError(f"unknown OCR_PROVIDER={provider!r}")
