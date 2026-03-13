"""OpenBB tools cache + audit log.

This module provides a small SQLite-based cache and an audit log for OpenBB tool calls.

Design goals:
- No external dependencies beyond stdlib
- Safe for demo usage (no secrets)
- Simple TTL-based caching
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional, Tuple

# Context propagation for associating OpenBB tool calls with an enterprise run_id.
_CURRENT_RUN_ID: ContextVar[Optional[str]] = ContextVar("openbb_current_run_id", default=None)


def set_current_run_id(run_id: Optional[str]) -> None:
    _CURRENT_RUN_ID.set(run_id)


def get_current_run_id() -> Optional[str]:
    return _CURRENT_RUN_ID.get()


def record_budget_event(kind: str, **fields: Any) -> None:
    """Record a budget/guardrail event into the OpenBB audit log.

    This is a lightweight side-channel used by the agent graph to persist
    guardrail hits into enterprise run metadata (via audit_sync).

    - No-op when no current run_id is set.
    - Stored as an audit_log row with endpoint prefixed by "budget::".
    """
    if not get_current_run_id():
        return
    try:
        store = OpenBBToolStore()
        store.write_audit(
            endpoint=f"budget::{kind}",
            params={"kind": kind, **fields},
            status_code=429,
            latency_ms=0,
            cache_hit=False,
            error=None,
        )
    except Exception:
        # Best-effort only; never break the main run.
        return


def _default_db_path() -> str:
    # Place DB file under project/openbb/ by default
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, "openbb_tools_cache.sqlite")


def stable_params_hash(params: dict[str, Any]) -> str:
    """Compute a stable hash for params.

    - Sort keys
    - JSON-encode with stable separators
    """
    payload = json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CacheResult:
    hit: bool
    value: Optional[str] = None


class OpenBBToolStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("OPENBB_TOOLS_DB_PATH") or _default_db_path()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        # autocommit mode for simplicity
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        db_dir = os.path.dirname(self.db_path) or "."
        os.makedirs(db_dir, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    response_text TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    run_id TEXT,
                    endpoint TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    status_code INTEGER,
                    latency_ms INTEGER NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    error TEXT
                )
                """
            )

            # Backwards-compatible migration: add run_id column if missing.
            try:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
                if "run_id" not in cols:
                    conn.execute("ALTER TABLE audit_log ADD COLUMN run_id TEXT")
            except Exception:
                # Best-effort migration; ignore if locked or unsupported.
                pass

    def get_cache(self, cache_key: str) -> CacheResult:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at, ttl_seconds, response_text FROM cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if not row:
                return CacheResult(hit=False)
            created_at = int(row["created_at"])
            ttl = int(row["ttl_seconds"])
            if created_at + ttl < now:
                # expired
                conn.execute("DELETE FROM cache WHERE cache_key = ?", (cache_key,))
                return CacheResult(hit=False)
            return CacheResult(hit=True, value=str(row["response_text"]))

    def set_cache(self, cache_key: str, response_text: str, ttl_seconds: int) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache(cache_key, created_at, ttl_seconds, response_text)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    created_at=excluded.created_at,
                    ttl_seconds=excluded.ttl_seconds,
                    response_text=excluded.response_text
                """,
                (cache_key, now, int(ttl_seconds), response_text),
            )

    def write_audit(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        status_code: Optional[int],
        latency_ms: int,
        cache_hit: bool,
        error: Optional[str] = None,
    ) -> None:
        ts = int(time.time())
        params_json = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
        p_hash = stable_params_hash(params)
        run_id = get_current_run_id()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log(ts, run_id, endpoint, params_hash, params_json, status_code, latency_ms, cache_hit, error)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, run_id, endpoint, p_hash, params_json, status_code, int(latency_ms), 1 if cache_hit else 0, error),
            )
