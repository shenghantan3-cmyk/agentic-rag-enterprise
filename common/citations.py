"""Structured citation helpers.

This repo historically treated "citations" as a best-effort list of filenames
parsed from the final answer text.

Milestone 3 adds *structured* citations that can be returned from /v1/chat and
persisted in the enterprise runs table.

We keep tool outputs backward-compatible (human readable text) while appending a
machine-readable payload marker that can be parsed by the graph.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypedDict

# Legacy marker format (pre-structured-citations upgrade). Still supported for
# backwards compatibility.
CITATIONS_MARKER = "\n\n[CITATIONS_JSON]\n"


class Citation(TypedDict, total=False):
    """Lightweight structured citation schema.

    NOTE: Keep this dependency-free (no pydantic). The enterprise API exposes a
    Pydantic model with the same fields.
    """

    doc_id: Optional[str]
    doc_name: Optional[str]
    source: Optional[str]

    chunk_id: Optional[str]
    parent_id: Optional[str]

    snippet: Optional[str]
    score: Optional[float]

    span_start: Optional[int]
    span_end: Optional[int]

    retriever: Optional[str]
    created_at: Optional[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# NOTE: We intentionally keep this module free of heavy/optional deps.
# The enterprise API defines a Pydantic Citation schema separately.


def make_chunk_id(*parts: str) -> str:
    """Make a stable, compact chunk id from arbitrary identifying parts."""

    h = hashlib.sha1("|".join([p for p in parts if p]).encode("utf-8"), usedforsecurity=False)
    return h.hexdigest()[:16]


def pack_tool_output(text: str, citations: List[Dict[str, Any]]) -> str:
    """Return tool output as JSON string.

    Requirements:
    - ToolMessage content should be JSON containing `answer_text` + `citations`.
    - Keep a backward-compatible `text` field for LLM readability.

    We also include `format` for easier future parsing.
    """

    obj = {
        "format": "tool_output.v1",
        "text": text or "",
        "answer_text": text or "",
        "citations": citations or [],
    }
    return json.dumps(obj, ensure_ascii=False)


def unpack_tool_output(tool_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract (text, citations) from tool output.

    Supports:
    1) New JSON object: {text, answer_text, citations}
    2) Legacy marker format: <text> + CITATIONS_MARKER + <json list>
    """

    if not tool_text:
        return "", []

    # New format: tool_text is JSON object
    stripped = tool_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                text = str(data.get("text") or data.get("answer_text") or "")
                cites = data.get("citations") or []
                if isinstance(cites, list):
                    out = [d for d in cites if isinstance(d, dict)]
                else:
                    out = []
                return text, out
        except Exception:
            # fall through to legacy parsing
            pass

    # Legacy marker format
    if CITATIONS_MARKER not in tool_text:
        return tool_text, []

    text, payload = tool_text.split(CITATIONS_MARKER, 1)
    payload = payload.strip()
    if not payload:
        return text, []

    try:
        data = json.loads(payload)
        if isinstance(data, list):
            out = [d for d in data if isinstance(d, dict)]
            return text, out
    except Exception:
        pass
    return text, []


def merge_citations(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate citations while preserving order."""

    existing = list(existing or [])
    new = list(new or [])

    def key(c: Dict[str, Any]) -> str:
        return str(
            c.get("chunk_id")
            or make_chunk_id(
                str(c.get("source") or ""),
                str(c.get("parent_id") or ""),
                str(c.get("snippet") or ""),
            )
        )

    seen = {key(c) for c in existing if isinstance(c, dict)}
    out = [c for c in existing if isinstance(c, dict)]
    for c in new:
        if not isinstance(c, dict):
            continue
        k = key(c)
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def citations_to_files(citations: Iterable[Dict[str, Any]]) -> List[str]:
    """Extract a de-duped list of `source` filenames from structured citations."""

    seen = set()
    out: List[str] = []
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        src = str(c.get("source") or "").strip()
        if not src:
            continue
        if src in seen:
            continue
        seen.add(src)
        out.append(src)
    return out
