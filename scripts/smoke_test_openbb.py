"""Minimal smoke test for OpenBB local server integration.

- Checks OpenBB server is reachable via /openapi.json (or /docs fallback)
- Calls one endpoint using provider=yfinance (AAPL quote)

No external keys required.

Usage:
  . .venv/bin/activate
  OPENBB_BASE_URL=http://127.0.0.1:6900 python scripts/smoke_test_openbb.py
"""

from __future__ import annotations

import os
import sys

import requests


def main() -> int:
    base_url = (os.getenv("OPENBB_BASE_URL") or "http://127.0.0.1:6900").rstrip("/")

    # 1) Spec / docs check
    spec_url = f"{base_url}/openapi.json"
    try:
        r = requests.get(spec_url, timeout=10)
        r.raise_for_status()
        print(f"OK: openapi.json reachable ({r.status_code})")
    except Exception as e:
        docs_url = f"{base_url}/docs"
        try:
            r = requests.get(docs_url, timeout=10)
            r.raise_for_status()
            print(f"OK: /docs reachable ({r.status_code})")
        except Exception:
            print(f"ERROR: OpenBB server not reachable at {spec_url} (also tried /docs).\n{e}")
            return 2

    # 2) Simple endpoint call (quote)
    quote_url = f"{base_url}/api/v1/equity/price/quote"
    params = {"provider": "yfinance", "symbol": "AAPL", "use_cache": True}
    try:
        r = requests.get(quote_url, params=params, timeout=20)
        r.raise_for_status()
        print("OK: quote endpoint reachable")
        print(r.text[:1000])
        return 0
    except Exception as e:
        print("WARN: quote call failed (server reachable, but endpoint error).")
        print(str(e))
        if getattr(e, "response", None) is not None:
            print(getattr(e.response, "text", "")[:1000])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
