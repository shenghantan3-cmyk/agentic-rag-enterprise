"""Smoke test for async jobs (enterprise stack).

This script enqueues a noop background job via the enterprise API and polls for completion.

Usage:

  # with compose running:
  python scripts/smoke_test_jobs.py --base-url http://127.0.0.1:8000

  # with API key:
  python scripts/smoke_test_jobs.py --base-url http://127.0.0.1:8000 --api-key "$ENTERPRISE_API_KEY"

"""

from __future__ import annotations

import argparse
import time
from typing import Any, Dict

import requests


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--api-key", default="")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--poll", type=float, default=0.5)
    p.add_argument("--seconds", type=float, default=0.2, help="noop job duration")
    args = p.parse_args()

    base_url = args.base_url.rstrip("/")
    headers: Dict[str, str] = {}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    # enqueue noop job
    resp = requests.post(
        f"{base_url}/v1/jobs/noop",
        params={"seconds": args.seconds},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    payload: Dict[str, Any] = resp.json()
    job_id = payload["job_id"]
    status_url = payload["status_url"]

    deadline = time.time() + float(args.timeout)
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        st = requests.get(status_url, headers=headers, timeout=10)
        st.raise_for_status()
        last = st.json()
        if last.get("status") in {"completed", "failed"}:
            break
        time.sleep(float(args.poll))

    if not last:
        raise SystemExit("no status response")

    if last.get("status") != "completed":
        raise SystemExit(f"job {job_id} not completed: {last}")

    print("OK", {"job_id": job_id, "status": last.get("status"), "result": last.get("result")})


if __name__ == "__main__":
    main()
