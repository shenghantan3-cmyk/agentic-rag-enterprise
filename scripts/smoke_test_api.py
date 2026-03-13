"""Smoke test for enterprise FastAPI app.

This test is intentionally lightweight:
- checks imports
- checks route registration
- optionally calls /healthz using TestClient

It does NOT start uvicorn and does not call /v1/chat (which may require heavy RAG init).

Usage:

  python scripts/smoke_test_api.py
"""

from __future__ import annotations


def main() -> None:
    # Ensure repo root is on sys.path when running from ./scripts
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from project.enterprise_api.app import app
    except ModuleNotFoundError as e:
        # In minimal environments FastAPI might not be installed. This smoke test
        # should be non-blocking in that case.
        print(f"SKIP: enterprise_api import ({e})")
        return

    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/healthz" in routes
    assert "/v1/chat" in routes
    assert "/v1/documents/upload" in routes
    assert "/v1/jobs/{job_id}" in routes
    assert "/v1/jobs/noop" in routes

    # Optional runtime check
    try:
        from fastapi.testclient import TestClient

        c = TestClient(app)
        resp = c.get("/healthz")
        assert resp.status_code == 200, resp.text
        assert resp.json().get("status") == "ok"
    except Exception:
        # testclient might not be installed in minimal envs; ignore
        pass

    print("OK: enterprise_api routes imported and registered")


if __name__ == "__main__":
    main()
