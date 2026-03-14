from __future__ import annotations

import os


def _get_env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except Exception:
        return default


def _get_env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def ocr_provider() -> str:
    # New default: tencent
    return os.getenv("OCR_PROVIDER", "tencent").strip().lower()


def ocr_table_only_invocation() -> bool:
    # When true: only call Tencent TableOCR when a table-like layout is detected.
    return _get_env_bool("OCR_TABLE_ONLY", True)


def ocr_max_pages() -> int:
    return _get_env_int("OCR_MAX_PAGES", 20)


def ocr_page_dpi() -> int:
    return _get_env_int("OCR_PAGE_DPI", 200)


def tencent_secret_id() -> str:
    return os.getenv("TENCENT_SECRET_ID", "").strip()


def tencent_secret_key() -> str:
    return os.getenv("TENCENT_SECRET_KEY", "").strip()


def tencent_region() -> str:
    # Prefer new name, keep backward compatibility.
    return (
        os.getenv("TENCENT_OCR_REGION")
        or os.getenv("TENCENT_REGION")
        or "ap-guangzhou"
    ).strip()
