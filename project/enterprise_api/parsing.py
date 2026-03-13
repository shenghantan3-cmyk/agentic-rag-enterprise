"""Helpers for parsing citations and OpenBB usage summary."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


_SOURCES_RE = re.compile(r"^\*\*Sources:\*\*$", re.IGNORECASE)
_FILE_RE = re.compile(r"\b[^\s\*]+\.[A-Za-z0-9]{2,5}\b")


def extract_citations(answer_text: str) -> List[str]:
    """Extract citations from the final answer.

    The RAG prompts append a Sources section like:

    ---
    **Sources:**
    - file1.pdf
    - file2.md

    We return the list of file names.
    """

    lines = [l.rstrip() for l in (answer_text or "").splitlines()]
    citations: List[str] = []

    # Find a "**Sources:**" marker
    src_idx = None
    for i, line in enumerate(lines):
        if _SOURCES_RE.match(line.strip()):
            src_idx = i
            break

    if src_idx is not None:
        for line in lines[src_idx + 1 :]:
            m = _FILE_RE.search(line)
            if not m:
                continue
            citations.append(m.group(0))

    # Fallback: grab any filename-like tokens if no explicit sources marker
    if not citations:
        for m in _FILE_RE.finditer(answer_text or ""):
            citations.append(m.group(0))

    # de-dupe while preserving order
    seen = set()
    out: List[str] = []
    for c in citations:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def summarize_openbb_tool_calls(tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact summary for API response.

    Note: the agent may emit budget/guardrail events into the OpenBB audit log
    as pseudo tool calls with endpoint prefix "budget::".

    We return those separately under `budget_events` and exclude them from
    the main counts.
    """
    if not tool_calls:
        return {
            "count": 0,
            "endpoints": [],
            "cache_hits": 0,
            "avg_latency_ms": None,
            "budget_events": [],
        }

    budget_events: List[str] = []
    normal_calls: List[Dict[str, Any]] = []
    for tc in tool_calls or []:
        ep = str(tc.get("endpoint") or "")
        if ep.startswith("budget::"):
            budget_events.append(ep)
        else:
            normal_calls.append(tc)

    if not normal_calls:
        return {
            "count": 0,
            "endpoints": [],
            "cache_hits": 0,
            "avg_latency_ms": None,
            "budget_events": budget_events,
        }

    endpoints = []
    cache_hits = 0
    total_latency = 0
    for tc in normal_calls:
        ep = tc.get("endpoint")
        if ep and ep not in endpoints:
            endpoints.append(ep)
        if tc.get("cache_hit"):
            cache_hits += 1
        try:
            total_latency += int(tc.get("latency_ms") or 0)
        except Exception:
            pass

    avg = int(total_latency / max(1, len(normal_calls)))
    return {
        "count": len(normal_calls),
        "endpoints": endpoints,
        "cache_hits": cache_hits,
        "avg_latency_ms": avg,
        "budget_events": budget_events,
    }
