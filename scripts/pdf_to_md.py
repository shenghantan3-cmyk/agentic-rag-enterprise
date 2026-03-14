"""PDF -> Markdown 转换脚本（中文说明版）

这个脚本对应仓库里的 `pdf_to_md.ipynb`（英文）/ `pdf_to_md_zh.ipynb`（中文）。
目标：把 PDF 转成适合 RAG 的 Markdown，便于后续分块与向量化。

支持三种方式（并提供自动路由）：
1) PyMuPDF4LLM：适合可选中文本的“数字版 PDF”
2) Docling：适合扫描件/表格/多栏（需要 OCR + 表格结构）
3) PaddleOCR：适合扫描件（本地 OCR，CPU 可跑但慢）

另外：复杂 PDF（图表/视觉信息重要）更适合 VLM（多模态大模型）。本仓库默认不内置 vLLM-VLM 路径（需要你本地 GPU/模型选择），但脚本会在 auto 模式下识别并给出提示。

用法示例：
  # 自动判断复杂度并选择转换器（推荐）
  python scripts/pdf_to_md.py --engine auto --pdf_dir ./pdf --out_dir ./md

  # 手动指定
  python scripts/pdf_to_md.py --engine pymupdf4llm --pdf_dir ./pdf --out_dir ./md
  python scripts/pdf_to_md.py --engine docling --pdf_dir ./pdf --out_dir ./md
  python scripts/pdf_to_md.py --engine paddleocr --pdf_dir ./pdf --out_dir ./md

注意：
- 本脚本只负责“转 Markdown”。
- 如果你想“本地 OCR 后再上传 .md 到服务器入库”，请用输出的 .md 文件上传即可。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfStats:
    pages: int
    sample_pages: int
    text_chars: int
    image_count: int


def _analyze_pdf(pdf_path: Path, *, sample_pages: int = 3) -> PdfStats:
    """Very lightweight PDF complexity analysis.

    Heuristics (good enough for routing):
    - If selectable text is near-zero in first N pages => likely scanned => needs OCR.
    - If many images and low text => might be visual-heavy.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError(
            "缺少依赖 PyMuPDF（fitz）。请安装：pip install pymupdf"
        ) from e

    doc = fitz.open(str(pdf_path))
    try:
        n_pages = int(doc.page_count)
        sp = min(int(sample_pages), n_pages)
        text_chars = 0
        image_count = 0
        for i in range(sp):
            page = doc.load_page(i)
            text_chars += len((page.get_text() or "").strip())
            image_count += len(page.get_images(full=True) or [])
        return PdfStats(pages=n_pages, sample_pages=sp, text_chars=text_chars, image_count=image_count)
    finally:
        doc.close()


def _choose_engine_auto(stats: PdfStats) -> str:
    # Thresholds are intentionally simple and adjustable.
    if stats.text_chars < 200:
        # likely scanned
        return "paddleocr"
    # digital text PDF
    return "pymupdf4llm"


def _iter_pdfs(pdf_dir: Path) -> list[Path]:
    return sorted([p for p in pdf_dir.glob("*.pdf") if p.is_file()])


def convert_pymupdf4llm(*, pdf_dir: Path, out_dir: Path) -> None:
    try:
        import pymupdf4llm
    except Exception as e:
        raise RuntimeError(
            "缺少依赖 pymupdf4llm。请先安装：pip install pymupdf4llm"
        ) from e

    out_dir.mkdir(parents=True, exist_ok=True)

    for pdf in _iter_pdfs(pdf_dir):
        md_text = pymupdf4llm.to_markdown(str(pdf))
        out_path = out_dir / f"{pdf.stem}.md"
        out_path.write_text(md_text, encoding="utf-8")
        print(f"✓ 转换完成（pymupdf4llm）：{pdf.name} -> {out_path}")


def convert_docling(*, pdf_dir: Path, out_dir: Path) -> None:
    """Docling：适合扫描件/表格/多栏，但依赖较重。"""
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except Exception as e:
        raise RuntimeError(
            "缺少依赖 docling。\n"
            "- 建议先确认本机 Python 版本（通常 3.10 更稳）\n"
            "- 安装：pip install docling\n"
            f"原始错误：{e}"
        ) from e

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.do_ocr = True
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_picture_images = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    for pdf in _iter_pdfs(pdf_dir):
        result = converter.convert(str(pdf))
        md = result.document.export_to_markdown()
        out_path = out_dir / f"{pdf.stem}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"✓ 转换完成（docling）：{pdf.name} -> {out_path}")


def convert_paddleocr(*, pdf_dir: Path, out_dir: Path, lang: str = "ch") -> None:
    """PaddleOCR：适合扫描件。本地 CPU 可跑，但会比较慢。"""
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("缺少依赖 PyMuPDF（fitz）。请安装：pip install pymupdf") from e

    try:
        from paddleocr import PaddleOCR
    except Exception as e:
        raise RuntimeError(
            "缺少依赖 paddleocr/paddlepaddle。\n"
            "Windows 建议用 Python 3.10 的 conda 环境安装：\n"
            "  conda create -n ocr310 python=3.10 -y\n"
            "  conda activate ocr310\n"
            "  pip install paddlepaddle -i https://www.paddlepaddle.org.cn/packages/stable/cpu/\n"
            "  pip install paddleocr\n"
            f"原始错误：{e}"
        ) from e

    out_dir.mkdir(parents=True, exist_ok=True)
    ocr = PaddleOCR(use_angle_cls=True, lang=lang)

    for pdf in _iter_pdfs(pdf_dir):
        doc = fitz.open(str(pdf))
        try:
            parts: list[str] = []
            for i in range(doc.page_count):
                page = doc.load_page(i)
                pix = page.get_pixmap()
                img_bytes = pix.tobytes("png")
                result = ocr.ocr(img_bytes, cls=True)

                parts.append(f"## Page {i+1}\n")
                if result and result[0]:
                    for line in result[0]:
                        text = (line[1][0] or "").strip()
                        if text:
                            parts.append(text)
                parts.append("\n")

            out_path = out_dir / f"{pdf.stem}.md"
            out_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
            print(f"✓ 转换完成（paddleocr）：{pdf.name} -> {out_path}")
        finally:
            doc.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="PDF 转 Markdown（中文说明版）")
    ap.add_argument(
        "--engine",
        choices=["auto", "pymupdf4llm", "docling", "paddleocr"],
        default="auto",
        help="auto 会根据 PDF 文字层粗略判断：文本少 -> OCR；否则走 pymupdf4llm",
    )
    ap.add_argument("--pdf_dir", required=True, help="PDF 文件夹（仅处理 *.pdf）")
    ap.add_argument("--out_dir", required=True, help="输出 Markdown 文件夹")
    ap.add_argument("--sample_pages", type=int, default=3, help="auto 分析时抽样页数")
    ap.add_argument("--ocr_lang", default="ch", help="paddleocr 语言（默认 ch）")

    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not pdf_dir.exists():
        raise SystemExit(f"pdf_dir 不存在：{pdf_dir}")

    engine = args.engine
    if engine == "auto":
        pdfs = _iter_pdfs(pdf_dir)
        if not pdfs:
            raise SystemExit(f"目录下没有 pdf：{pdf_dir}")
        # Use first pdf as representative for routing; print stats for transparency.
        st = _analyze_pdf(pdfs[0], sample_pages=args.sample_pages)
        engine = _choose_engine_auto(st)
        print(
            f"[auto] sample={pdfs[0].name} pages={st.pages} sample_pages={st.sample_pages} text_chars={st.text_chars} images={st.image_count} -> engine={engine}"
        )

    if engine == "pymupdf4llm":
        convert_pymupdf4llm(pdf_dir=pdf_dir, out_dir=out_dir)
    elif engine == "docling":
        convert_docling(pdf_dir=pdf_dir, out_dir=out_dir)
    elif engine == "paddleocr":
        convert_paddleocr(pdf_dir=pdf_dir, out_dir=out_dir, lang=args.ocr_lang)


if __name__ == "__main__":
    main()
