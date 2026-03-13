"""Minimal OpenBB HTTP client with retries + caching.

This client is intentionally simple and safe-by-default:
- base_url configurable via env OPENBB_BASE_URL
- timeouts
- limited retries for transient errors
- TTL-based caching + audit logging

No external API keys are used.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import httpx

from .storage import OpenBBToolStore, stable_params_hash


class OpenBBClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        store: Optional[OpenBBToolStore] = None,
    ):
        self.base_url = (base_url or os.getenv("OPENBB_BASE_URL") or "http://127.0.0.1:6900").rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.max_retries = max(0, int(max_retries))
        self.store = store or OpenBBToolStore()

    def _cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        # method fixed to GET in this client
        return f"GET::{endpoint}::{stable_params_hash(params)}"

    def get_json(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        ttl_seconds: int,
        use_cache: bool = True,
    ) -> str:
        """GET an endpoint and return pretty JSON string."""
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{self.base_url}{endpoint}"

        cache_key = self._cache_key(endpoint, params)
        if use_cache:
            cached = self.store.get_cache(cache_key)
            if cached.hit and cached.value is not None:
                # audit cached read as zero-latency
                self.store.write_audit(
                    endpoint=endpoint,
                    params=params,
                    status_code=200,
                    latency_ms=0,
                    cache_hit=True,
                    error=None,
                )
                return cached.value

        last_exc: Optional[Exception] = None
        start = time.perf_counter()

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, params=params)
                latency_ms = int((time.perf_counter() - start) * 1000)

                if resp.status_code >= 500 and attempt < self.max_retries:
                    # transient server error, retry
                    time.sleep(0.2 * (attempt + 1))
                    continue

                resp.raise_for_status()

                # normalize output to pretty JSON string
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}

                text = json.dumps(data, ensure_ascii=False, indent=2, default=str)

                if ttl_seconds > 0:
                    self.store.set_cache(cache_key, text, ttl_seconds=ttl_seconds)

                self.store.write_audit(
                    endpoint=endpoint,
                    params=params,
                    status_code=resp.status_code,
                    latency_ms=latency_ms,
                    cache_hit=False,
                    error=None,
                )
                return text

            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue

                latency_ms = int((time.perf_counter() - start) * 1000)
                status_code = None
                if isinstance(e, httpx.HTTPStatusError):
                    status_code = e.response.status_code
                self.store.write_audit(
                    endpoint=endpoint,
                    params=params,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    cache_hit=False,
                    error=str(e),
                )
                raise

        # unreachable
        raise RuntimeError(str(last_exc) if last_exc else "OpenBBClient failed")
