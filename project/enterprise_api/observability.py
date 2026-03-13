from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


request_id_ctx: ContextVar[Optional[str]] = ContextVar("enterprise_request_id", default=None)
run_id_ctx: ContextVar[Optional[str]] = ContextVar("enterprise_run_id", default=None)


def get_request_id() -> Optional[str]:
    return request_id_ctx.get()


def set_request_id(request_id: Optional[str]) -> None:
    request_id_ctx.set(request_id)


def get_run_id() -> Optional[str]:
    return run_id_ctx.get()


def set_run_id(run_id: Optional[str]) -> None:
    run_id_ctx.set(run_id)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        run_id = get_run_id()
        if run_id:
            payload["run_id"] = run_id

        # Add structured fields from `extra={"fields": {...}}`
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def setup_json_logging() -> None:
    """Configure JSON logging for the application.

    Gunicorn/Uvicorn have their own loggers; we keep this scoped to our app logger.
    """

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger("enterprise_api")
    logger.setLevel(level)

    # Avoid duplicate handlers if reloaded.
    if any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.propagate = False


def log_fields(**fields: Any) -> Dict[str, Any]:
    return {"fields": fields}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_ctx.set(req_id)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["x-request-id"] = req_id
        return response
