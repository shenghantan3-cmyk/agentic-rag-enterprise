from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .db.models import ToolCall


def _default_openbb_db_path() -> str:
    base_dir = Path(__file__).resolve().parents[1] / "openbb"
    return str(base_dir / "openbb_tools_cache.sqlite")


def _connect_openbb(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def copy_openbb_audit_to_enterprise(
    *,
    run_id: str,
    db: Session,
    openbb_db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Copy OpenBB audit rows for a run_id into enterprise tool_calls.

    Returns the copied tool calls as dicts for summarization.
    """

    path = openbb_db_path or os.getenv("OPENBB_TOOLS_DB_PATH") or _default_openbb_db_path()
    if not os.path.exists(path):
        return []

    with _connect_openbb(path) as conn:
        rows = conn.execute(
            """
            SELECT ts, run_id, endpoint, params_hash, params_json, status_code, latency_ms, cache_hit, error
            FROM audit_log
            WHERE run_id = ?
            ORDER BY ts ASC
            """,
            (run_id,),
        ).fetchall()

    copied: List[Dict[str, Any]] = []
    for r in rows:
        tc = ToolCall(
            run_id=run_id,
            ts=datetime.utcfromtimestamp(int(r["ts"])),
            provider="openbb",
            endpoint=str(r["endpoint"]),
            params_hash=str(r["params_hash"]),
            params_json=str(r["params_json"]),
            status_code=(int(r["status_code"]) if r["status_code"] is not None else None),
            latency_ms=int(r["latency_ms"]),
            cache_hit=1 if int(r["cache_hit"]) else 0,
            error=(str(r["error"]) if r["error"] else None),
        )
        db.add(tc)
        copied.append(
            {
                "endpoint": tc.endpoint,
                "params_hash": tc.params_hash,
                "status_code": tc.status_code,
                "latency_ms": tc.latency_ms,
                "cache_hit": bool(tc.cache_hit),
                "error": tc.error,
            }
        )

    return copied


def list_tool_calls_for_run(*, run_id: str, db: Session) -> List[Dict[str, Any]]:
    rows = (
        db.query(ToolCall)
        .filter(ToolCall.run_id == run_id)
        .order_by(ToolCall.id.asc())
        .all()
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "provider": r.provider,
                "endpoint": r.endpoint,
                "params_hash": r.params_hash,
                "params_json": r.params_json,
                "status_code": r.status_code,
                "latency_ms": r.latency_ms,
                "cache_hit": bool(r.cache_hit),
                "error": r.error,
                "ts": r.ts.isoformat() + "Z" if r.ts else None,
            }
        )
    return out
