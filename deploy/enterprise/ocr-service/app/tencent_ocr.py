from __future__ import annotations

import base64
from dataclasses import asdict
from typing import Any, Iterable

import fitz  # PyMuPDF
from PIL import Image

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import models
from tencentcloud.ocr.v20181119.ocr_client import OcrClient

from .config import (
    ocr_max_pages,
    ocr_page_dpi,
    ocr_table_only_invocation,
    tencent_region,
    tencent_secret_id,
    tencent_secret_key,
)
from .ocr import OcrMeta
from .table_detection import BBox, TextBox, detect_table_layout


def _page_pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    mode = "RGB"
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    return Image.frombytes(mode, [pix.width, pix.height], pix.samples)


def _pil_to_jpeg_bytes(img: Image.Image, *, quality: int = 85) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _tencent_client() -> OcrClient:
    sid = tencent_secret_id()
    skey = tencent_secret_key()
    if not sid or not skey:
        raise ValueError("missing Tencent OCR credentials (TENCENT_SECRET_ID/TENCENT_SECRET_KEY)")

    cred = credential.Credential(sid, skey)
    http_profile = HttpProfile()
    http_profile.endpoint = "ocr.tencentcloudapi.com"

    profile = ClientProfile()
    profile.httpProfile = http_profile
    return OcrClient(cred, tencent_region(), profile)


def _general_basic_ocr(client: OcrClient, image_b64: str) -> list[TextBox]:
    req = models.GeneralBasicOCRRequest()
    params = {
        "ImageBase64": image_b64,
        # Keep it simple; auto tends to work for mixed language docs.
        "LanguageType": "auto",
    }
    req.from_json_string(__import__("json").dumps(params))
    resp = client.GeneralBasicOCR(req)

    boxes: list[TextBox] = []
    for td in (resp.TextDetections or []):
        text = (td.DetectedText or "").strip()
        if not text:
            continue
        poly = td.Polygon or []
        xs = [p.X for p in poly if p is not None and getattr(p, "X", None) is not None]
        ys = [p.Y for p in poly if p is not None and getattr(p, "Y", None) is not None]
        if not xs or not ys:
            continue
        bbox = BBox(float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
        boxes.append(TextBox(text=text, bbox=bbox))

    return boxes


def _render_text_markdown(text_boxes: Iterable[TextBox]) -> str:
    # naive: group by y and join; good enough as fallback
    # We'll just sort by y then x and join with newlines.
    parts: list[str] = []
    for tb in sorted(text_boxes, key=lambda b: (b.bbox.y0, b.bbox.x0)):
        parts.append(tb.text)
    return "\n".join(parts).strip()


def _table_cells_to_markdown(cells: list[models.TableCellInfo]) -> str:
    if not cells:
        return ""

    max_row = max(int(c.RowBr or 0) for c in cells)
    max_col = max(int(c.ColBr or 0) for c in cells)
    rows = max_row + 1
    cols = max_col + 1

    grid: list[list[str]] = [["" for _ in range(cols)] for _ in range(rows)]

    for c in cells:
        r0 = int(c.RowTl or 0)
        c0 = int(c.ColTl or 0)
        text = (c.Text or "").strip()
        # Put merged-cell text only in top-left.
        if 0 <= r0 < rows and 0 <= c0 < cols:
            grid[r0][c0] = text.replace("\n", " ").strip()

    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    header = [esc(x) if x else "" for x in grid[0]]
    body = [[esc(x) if x else "" for x in r] for r in grid[1:]]

    out: list[str] = []
    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join(["---"] * cols) + " |")
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out).strip()


def _recognize_table_ocr(client: OcrClient, image_b64: str) -> list[str]:
    req = models.RecognizeTableAccurateOCRRequest()
    params = {
        "ImageBase64": image_b64,
        # UseNewModel could improve complex tables but costs time.
        "UseNewModel": False,
    }
    req.from_json_string(__import__("json").dumps(params))
    resp = client.RecognizeTableAccurateOCR(req)

    md_tables: list[str] = []
    for ti in (resp.TableDetections or []):
        # TableInfo.Cells: list[TableCellInfo]
        md = _table_cells_to_markdown(ti.Cells or [])
        if md:
            md_tables.append(md)

    return md_tables


def ocr_pdf_bytes_to_markdown_tencent(pdf_bytes: bytes, *, filename: str = "document.pdf") -> tuple[str, dict[str, Any]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    max_pages = min(int(doc.page_count), int(ocr_max_pages()))
    dpi = int(ocr_page_dpi())
    scale = dpi / 72.0

    client = _tencent_client()

    parts: list[str] = []
    total_chars = 0
    table_pages: list[int] = []

    for i in range(max_pages):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        img = _page_pixmap_to_pil(pix)
        jpeg = _pil_to_jpeg_bytes(img)
        image_b64 = base64.b64encode(jpeg).decode("ascii")

        text_boxes = _general_basic_ocr(client, image_b64)
        page_text = _render_text_markdown(text_boxes)

        has_table = detect_table_layout(text_boxes)
        tables_md: list[str] = []

        # Policy: only invoke TableOCR when tables are detected.
        if (not ocr_table_only_invocation()) or has_table:
            if has_table:
                table_pages.append(i + 1)
            tables_md = _recognize_table_ocr(client, image_b64) if has_table or (not ocr_table_only_invocation()) else []

        page_parts: list[str] = [f"## Page {i+1}"]

        if tables_md:
            for t_idx, t in enumerate(tables_md, start=1):
                page_parts.append(f"\n### Table {t_idx}\n\n{t}")

        if page_text:
            page_parts.append(f"\n{page_text}")

        page_md = "\n".join(page_parts).strip() + "\n"
        parts.append(page_md)
        total_chars += len(page_text)

    markdown = "\n".join(parts).strip() + "\n"
    meta = asdict(
        OcrMeta(
            filename=filename,
            pages=int(max_pages),
            chars=int(total_chars),
            engine="tencent-ocr",
            provider="tencent",
            table_pages=table_pages,
        )
    )

    return markdown, meta
