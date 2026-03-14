from __future__ import annotations

from fastapi import FastAPI, File, UploadFile, HTTPException

from .paddle_ocr import ocr_pdf_bytes_to_markdown

app = FastAPI(title="ocr-service", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/v1/ocr/pdf-to-md")
async def pdf_to_md(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        markdown, meta = ocr_pdf_bytes_to_markdown(data, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ocr failed: {e}")

    return {"markdown": markdown, "meta": meta}
