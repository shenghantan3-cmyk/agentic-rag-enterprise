"""PDF -> Markdown 转换脚本（中文说明版）

这个脚本对应仓库里的 `pdf_to_md.ipynb`（英文）/ `pdf_to_md_zh.ipynb`（中文）。
目标：把 PDF 转成适合 RAG 的 Markdown，便于后续分块与向量化。

支持三种方式：
1) PyMuPDF4LLM：适合可选中文本的“数字版 PDF”
2) Docling：适合扫描件/表格/多栏（需要 OCR + 表格结构）
3) VLM：适合图表/视觉信息重要的复杂 PDF（这里不内置，需你自配 API）

用法示例：
  python scripts/pdf_to_md.py --engine pymupdf4llm --pdf_dir ./pdf --out_dir ./md
  python scripts/pdf_to_md.py --engine docling --pdf_dir ./pdf --out_dir ./md

注意：
- 本脚本只负责“转 Markdown”。
- 如果你想“本地 OCR 后再上传 .md 到服务器入库”，请用输出的 .md 文件上传即可。
"""

from __future__ import annotations

import argparse
from pathlib import Path


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
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except Exception as e:
        raise RuntimeError("缺少依赖 docling。请先安装：pip install docling") from e

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


def main() -> None:
    ap = argparse.ArgumentParser(description="PDF 转 Markdown（中文说明版）")
    ap.add_argument("--engine", choices=["pymupdf4llm", "docling"], default="pymupdf4llm")
    ap.add_argument("--pdf_dir", required=True, help="PDF 文件夹（仅处理 *.pdf）")
    ap.add_argument("--out_dir", required=True, help="输出 Markdown 文件夹")

    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not pdf_dir.exists():
        raise SystemExit(f"pdf_dir 不存在：{pdf_dir}")

    if args.engine == "pymupdf4llm":
        convert_pymupdf4llm(pdf_dir=pdf_dir, out_dir=out_dir)
    elif args.engine == "docling":
        convert_docling(pdf_dir=pdf_dir, out_dir=out_dir)


if __name__ == "__main__":
    main()
