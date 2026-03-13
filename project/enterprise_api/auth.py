from __future__ import annotations

import os
from typing import Iterable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


def _parse_public_paths() -> set[str]:
    # Allow overrides for additional public paths.
    extra = os.getenv("ENTERPRISE_PUBLIC_PATHS", "").strip()
    paths = {
        "/healthz",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    if extra:
        for p in extra.split(","):
            p = p.strip()
            if p:
                paths.add(p)
    return paths


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Simple API-key auth.

    If ENTERPRISE_API_KEY is empty, auth is disabled (local dev).
    If set, require X-API-Key header for all endpoints except a small allowlist.
    """

    def __init__(self, app, public_paths: Iterable[str] | None = None):
        super().__init__(app)
        self._public_paths = set(public_paths) if public_paths is not None else _parse_public_paths()

    async def dispatch(self, request: Request, call_next):
        api_key = os.getenv("ENTERPRISE_API_KEY", "")
        if not api_key:
            return await call_next(request)

        path = request.url.path
        if path in self._public_paths:
            return await call_next(request)

        provided = request.headers.get("x-api-key")
        if not provided or provided != api_key:
            raise HTTPException(status_code=401, detail="missing or invalid API key")

        return await call_next(request)
