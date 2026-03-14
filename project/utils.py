import os
import glob
from pathlib import Path

import config

# PyMuPDF historically used `import fitz`. Newer versions also provide `pymupdf`.
try:
    import pymupdf as _pymupdf  # type: ignore
except Exception:  # pragma: no cover
    try:
        import fitz as _pymupdf  # type: ignore
    except Exception:  # pragma: no cover
        _pymupdf = None  # type: ignore

# Optional layout helpers (may not exist in older PyMuPDF builds)
try:  # pragma: no cover
    import pymupdf.layout  # type: ignore
except Exception:  # pragma: no cover
    pass

import pymupdf4llm
import requests
import tiktoken

os.environ["TOKENIZERS_PARALLELISM"] = "false"


def pdf_text_length(pdf_path: str, *, max_pages: int = 3) -> int:
    """Estimate whether a PDF has a usable text layer.

    We sample the first `max_pages` pages and sum extracted text length.
    """

    if _pymupdf is None:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required for PDF text detection")

    try:
        doc = _pymupdf.open(pdf_path)
    except Exception:
        return 0

    total = 0
    try:
        n = min(int(max_pages), int(doc.page_count))
        for i in range(n):
            try:
                page = doc.load_page(i)
                txt = page.get_text("text") or ""
                total += len(txt.strip())
            except Exception:
                continue
    finally:
        try:
            doc.close()
        except Exception:
            pass

    return int(total)


def pdf_has_sufficient_text(pdf_path: str, *, threshold: int | None = None, max_pages: int = 3) -> bool:
    thr = int(config.ENTERPRISE_OCR_TEXT_THRESHOLD if threshold is None else threshold)
    if thr <= 0:
        return True
    return pdf_text_length(pdf_path, max_pages=max_pages) >= thr


def _ocr_pdf_to_markdown_via_service(pdf_path: str) -> str:
    """Call ocr-service to convert PDF to markdown."""

    url = str(config.ENTERPRISE_OCR_URL).rstrip("/") + "/v1/ocr/pdf-to-md"
    with open(pdf_path, "rb") as f:
        files = {"file": (Path(pdf_path).name, f, "application/pdf")}
        resp = requests.post(url, files=files, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    md = data.get("markdown")
    if not isinstance(md, str):
        raise RuntimeError("ocr-service returned invalid response")
    return md


def pdf_to_markdown(pdf_path: str, output_dir: str | Path) -> None:
    """Convert a PDF to markdown.

    Uses pymupdf4llm for text-based PDFs. If the PDF has too little text and OCR
    is enabled, falls back to ocr-service.
    """

    md: str | None = None

    if config.ENTERPRISE_OCR_ENABLED and not pdf_has_sufficient_text(pdf_path):
        try:
            md = _ocr_pdf_to_markdown_via_service(pdf_path)
        except Exception:
            md = None

    if md is None:
        if _pymupdf is None:  # pragma: no cover
            raise RuntimeError("PyMuPDF is required for PDF to markdown")
        doc = _pymupdf.open(pdf_path)
        try:
            md = pymupdf4llm.to_markdown(
                doc,
                header=False,
                footer=False,
                page_separators=True,
                ignore_images=True,
                write_images=False,
                image_path=None,
            )
        finally:
            try:
                doc.close()
            except Exception:
                pass

    md_cleaned = md.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore")
    output_path = Path(output_dir) / Path(pdf_path).stem
    Path(output_path).with_suffix(".md").write_bytes(md_cleaned.encode("utf-8"))

def pdfs_to_markdowns(path_pattern: str, overwrite: bool = False) -> None:
    output_dir = Path(config.MARKDOWN_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in map(Path, glob.glob(path_pattern)):
        md_path = (output_dir / pdf_path.stem).with_suffix(".md")
        if overwrite or not md_path.exists():
            pdf_to_markdown(pdf_path, output_dir)

def estimate_context_tokens(messages: list) -> int:
    try:
        encoding = tiktoken.encoding_for_model("gpt-4")
    except:
        encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(str(msg.content))) for msg in messages if hasattr(msg, 'content') and msg.content)