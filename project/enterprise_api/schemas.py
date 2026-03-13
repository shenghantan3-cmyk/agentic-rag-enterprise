from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Machine-readable citation reference returned by the enterprise API."""

    doc_id: Optional[str] = Field(None, description="Document id (stable identifier if available)")
    doc_name: Optional[str] = Field(None, description="Human-friendly document name")
    source: Optional[str] = Field(None, description="Document/source name, e.g. file.pdf")

    chunk_id: Optional[str] = Field(None, description="Child chunk id")
    parent_id: Optional[str] = Field(None, description="Parent chunk id")

    snippet: Optional[str] = Field(None, description="Short excerpt")
    score: Optional[float] = Field(None, description="Similarity score if available")

    span_start: Optional[int] = Field(None, description="Start offset into answer/context if available")
    span_end: Optional[int] = Field(None, description="End offset into answer/context if available")

    retriever: Optional[str] = Field(None, description="Retriever name (vector, parent_store, etc)")
    created_at: Optional[str] = Field(None, description="Citation creation timestamp (ISO8601)")
