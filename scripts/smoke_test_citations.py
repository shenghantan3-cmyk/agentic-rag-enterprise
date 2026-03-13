"""Smoke test for structured citations parsing.

This script is intentionally self-contained and does not require external keys
or RAG initialization.

It validates that:
- Tool output packing appends a machine-readable citations payload marker
- Tool output unpacking supports both packed output and raw legacy marker format

Usage:

  python scripts/smoke_test_citations.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from common.citations import CITATIONS_MARKER, pack_tool_output, unpack_tool_output

    citations = [
        {
            "doc_id": "example.pdf",
            "doc_name": "example.pdf",
            "source": "example.pdf",
            "chunk_id": "abc123",
            "parent_id": "example_parent_0",
            "snippet": "hello world",
            "score": 0.12,
            "span_start": None,
            "span_end": None,
            "retriever": "vector",
            "created_at": "2026-03-13T00:00:00Z",
        }
    ]

    text = "Some human readable text"

    # New JSON format
    packed = pack_tool_output(text, citations)
    obj = json.loads(packed)
    assert obj["format"] == "tool_output.v1"
    assert obj["answer_text"] == text
    assert obj["text"] == text
    assert isinstance(obj["citations"], list)

    unpacked_text, unpacked_cites = unpack_tool_output(packed)
    assert unpacked_text == text
    assert unpacked_cites and unpacked_cites[0]["chunk_id"] == "abc123"

    # Legacy marker format
    legacy = text + CITATIONS_MARKER + json.dumps(citations, ensure_ascii=False)
    ltext, lcites = unpack_tool_output(legacy)
    assert ltext == text
    assert lcites and lcites[0]["source"] == "example.pdf"

    print("OK: structured citations pack/unpack")


if __name__ == "__main__":
    main()
