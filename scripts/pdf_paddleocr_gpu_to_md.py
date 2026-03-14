from __future__ import annotations

"""PaddleOCR(GPU) PDF -> Markdown

Windows/本地使用：
- 适合扫描 PDF / 图片型 PDF
- 需要正确安装 paddlepaddle-gpu（CUDA 版本需匹配）

示例：
  conda activate ocrgpu310
  python scripts/pdf_paddleocr_gpu_to_md.py --pdf C:\pdfs\a.pdf --out C:\md\a.md --dpi 200

注意：
- 本脚本只负责把 PDF OCR 成 Markdown（每页加 "## Page N"）。
- 输出的 .md 适合上传到 enterprise-api 的 /v1/documents/upload 进行分块+向量化入库。
"""

import argparse
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR


def render_page_to_rgb(page: fitz.Page, dpi: int = 200) -> np.ndarray:
    """Render a PDF page to an RGB numpy array."""
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return np.array(img)


def ocr_pdf_to_markdown(
    pdf_path: Path,
    out_md: Path,
    *,
    lang: str = "ch",
    dpi: int = 200,
) -> None:
    # PaddleOCR will use GPU only if paddlepaddle-gpu is installed correctly.
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang=lang,
        use_gpu=True,
        show_log=False,
    )

    doc = fitz.open(str(pdf_path))
    try:
        parts: list[str] = []
        parts.append(f"# {pdf_path.stem}\n")

        for i in range(doc.page_count):
            page = doc.load_page(i)
            img = render_page_to_rgb(page, dpi=dpi)

            result = ocr.ocr(img, cls=True)

            parts.append(f"\n## Page {i+1}\n")

            if result and result[0]:
                for line in result[0]:
                    text = (line[1][0] or "").strip()
                    if text:
                        parts.append(text)
            else:
                parts.append("(本页未识别到文本)")

        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    finally:
        doc.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="PaddleOCR(GPU) PDF -> Markdown")
    ap.add_argument("--pdf", required=True, help="输入 PDF 文件路径")
    ap.add_argument("--out", required=True, help="输出 Markdown 文件路径")
    ap.add_argument("--lang", default="ch", help="OCR 语言：ch/en 等（默认 ch）")
    ap.add_argument("--dpi", type=int, default=200, help="渲染 DPI（默认 200；更高更清晰更慢）")
    args = ap.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    out_md = Path(args.out).expanduser().resolve()

    if not pdf_path.exists():
        raise SystemExit(f"PDF 不存在：{pdf_path}")

    ocr_pdf_to_markdown(pdf_path, out_md, lang=args.lang, dpi=args.dpi)
    print("OK:", out_md)


if __name__ == "__main__":
    main()
