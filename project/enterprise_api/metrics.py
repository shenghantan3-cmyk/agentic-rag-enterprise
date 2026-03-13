from __future__ import annotations

import os
import time
from typing import Dict, Optional

from fastapi import Request
from starlette.responses import Response

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except Exception:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = None  # type: ignore
    Histogram = None  # type: ignore
    generate_latest = None  # type: ignore


_METRICS_ENABLED = os.getenv("ENTERPRISE_METRICS_ENABLED", "1") not in {"0", "false", "False"}


def metrics_enabled() -> bool:
    return bool(_METRICS_ENABLED and generate_latest)


# Keep labels low-cardinality.
_http_requests_total = Counter(
    "enterprise_http_requests_total",
    "Total HTTP requests",
    ["method", "path_template", "status"],
) if Counter else None

_http_request_duration_seconds = Histogram(
    "enterprise_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path_template"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
) if Histogram else None

_chat_duration_seconds = Histogram(
    "enterprise_chat_duration_seconds",
    "Duration of /v1/chat handler in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
) if Histogram else None

_toolcall_latency_seconds = Histogram(
    "enterprise_toolcall_latency_seconds",
    "Latency of tool calls observed from audit log",
    ["provider", "endpoint"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
) if Histogram else None

_toolcalls_total = Counter(
    "enterprise_toolcalls_total",
    "Count of tool calls observed from audit log",
    ["provider", "endpoint", "status"],
) if Counter else None


def route_template_for_request(request: Request) -> str:
    # best effort: populated by Starlette routing
    try:
        route = request.scope.get("route")
        path = getattr(route, "path", None)
        if path:
            return str(path)
    except Exception:
        pass
    return request.url.path


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not metrics_enabled() or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        # route template might not be available until later, fallback to raw path.
        path_template = scope.get("path", "")
        start = time.perf_counter()
        status_code: Optional[int] = None

        async def send_wrapper(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            dur = time.perf_counter() - start
            # Starlette route template (if any)
            try:
                req = Request(scope)
                path_template_final = route_template_for_request(req)
            except Exception:
                path_template_final = path_template

            st = str(status_code or 0)
            if _http_requests_total:
                _http_requests_total.labels(method=method, path_template=path_template_final, status=st).inc()
            if _http_request_duration_seconds:
                _http_request_duration_seconds.labels(method=method, path_template=path_template_final).observe(dur)


def observe_chat_duration(seconds: float) -> None:
    if metrics_enabled() and _chat_duration_seconds:
        _chat_duration_seconds.observe(seconds)


def observe_tool_calls(tool_calls: list[dict]) -> None:
    if not metrics_enabled():
        return
    for tc in tool_calls or []:
        provider = str(tc.get("provider") or "openbb")
        endpoint = str(tc.get("endpoint") or "")
        status = str(tc.get("status_code") or 0)
        try:
            latency_ms = float(tc.get("latency_ms") or 0)
        except Exception:
            latency_ms = 0
        if _toolcall_latency_seconds:
            _toolcall_latency_seconds.labels(provider=provider, endpoint=endpoint).observe(latency_ms / 1000.0)
        if _toolcalls_total:
            _toolcalls_total.labels(provider=provider, endpoint=endpoint, status=status).inc()


def metrics_response() -> Response:
    if not metrics_enabled():
        return Response(status_code=404, content="metrics disabled")
    assert generate_latest is not None
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
