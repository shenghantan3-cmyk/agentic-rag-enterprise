import os

# --- Directory Configuration ---
_BASE_DIR = os.path.dirname(__file__)

MARKDOWN_DIR = os.path.join(_BASE_DIR, "markdown_docs")
PARENT_STORE_PATH = os.path.join(_BASE_DIR, "parent_store")
QDRANT_DB_PATH = os.path.join(_BASE_DIR, "qdrant_db")

# --- Qdrant Configuration ---
CHILD_COLLECTION = "document_child_chunks"
SPARSE_VECTOR_NAME = "sparse"

# --- Model Configuration ---
DENSE_MODEL = "sentence-transformers/all-mpnet-base-v2"
SPARSE_MODEL = "Qdrant/bm25"
LLM_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
LLM_TEMPERATURE = 0

# --- Agent Configuration ---

def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return str(default)
    s = str(raw).strip()
    return s if s else str(default)


def _env_int(name: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    """Read an int from env with optional clamping."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        v = int(default)
    else:
        try:
            v = int(str(raw).strip())
        except Exception:
            v = int(default)
    if min_value is not None:
        v = max(int(min_value), v)
    if max_value is not None:
        v = min(int(max_value), v)
    return v


# Global budgets / guardrails (override via env)
MAX_TOOL_CALLS = _env_int("MAX_TOOL_CALLS", 8, min_value=0)
MAX_OPENBB_CALLS = _env_int("MAX_OPENBB_CALLS", 4, min_value=0)
MAX_DATE_RANGE_DAYS = _env_int("MAX_DATE_RANGE_DAYS", 3650, min_value=1)
MAX_NEWS_LIMIT = _env_int("MAX_NEWS_LIMIT", 50, min_value=1)

# --- OCR (enterprise ingestion fallback) ---
ENTERPRISE_OCR_URL = _env_str("ENTERPRISE_OCR_URL", "http://ocr-service:8001")
ENTERPRISE_OCR_ENABLED = _env_int("ENTERPRISE_OCR_ENABLED", 1, min_value=0, max_value=1)
ENTERPRISE_OCR_TEXT_THRESHOLD = _env_int("ENTERPRISE_OCR_TEXT_THRESHOLD", 200, min_value=0)

MAX_ITERATIONS = _env_int("MAX_ITERATIONS", 10, min_value=1)
BASE_TOKEN_THRESHOLD = _env_int("BASE_TOKEN_THRESHOLD", 2000, min_value=256)
TOKEN_GROWTH_FACTOR = float(os.getenv("TOKEN_GROWTH_FACTOR", "0.9"))

# --- Text Splitter Configuration ---
CHILD_CHUNK_SIZE = 500
CHILD_CHUNK_OVERLAP = 100
MIN_PARENT_SIZE = 2000
MAX_PARENT_SIZE = 4000
HEADERS_TO_SPLIT_ON = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3")
]
