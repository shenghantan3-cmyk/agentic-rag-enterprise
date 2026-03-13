from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(32), default="completed")

    user_message: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)

    citations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # New: structured citations payloads (list[dict])
    citations_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    openbb_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant
    content: Mapped[str] = mapped_column(Text)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    provider: Mapped[str] = mapped_column(String(32), default="openbb")
    endpoint: Mapped[str] = mapped_column(String(256))

    params_hash: Mapped[str] = mapped_column(String(128), index=True)
    params_json: Mapped[str] = mapped_column(Text)

    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Integer)  # store as 0/1 for sqlite compatibility

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
