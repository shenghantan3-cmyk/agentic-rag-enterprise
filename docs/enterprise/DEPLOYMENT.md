# Enterprise deployment

This project supports an **enterprise-style** deployment split into an HTTP API and a background worker.

## Architecture

Core services:

- **enterprise-api**: FastAPI app (Gunicorn+Uvicorn workers)
- **worker**: RQ worker for async jobs (document ingestion, long-running tasks)
- **redis**: queue backend
- **postgres**: persistent metadata (runs/jobs/messages/tool calls)
- **prometheus (optional)**: scrapes the API `/metrics` endpoint

Typical flow:

1) Client uploads a document to `enterprise-api`.
2) API writes the upload to `ENTERPRISE_UPLOAD_DIR` and enqueues a Redis job.
3) `worker` consumes the job and updates job status in Postgres.

Notes:

- The default `docker-compose` stack also includes **Qdrant** as the vector store.
- In the provided compose file, all ports are bound to `127.0.0.1` (loopback-only) by default.

## Environment variables

Minimum required for production-like deployments:

- `DATABASE_URL`
  - Example: `postgresql+psycopg://USER:PASSWORD@HOST:5432/enterprise`
- `ENTERPRISE_API_KEY`
  - If non-empty, requests must include header `X-API-Key: <value>`
- `ENTERPRISE_UPLOAD_DIR`
  - Directory where uploaded files are written (must be shared by API + worker)

Queue / worker:

- `ENTERPRISE_REDIS_URL` (default: `redis://redis:6379/0` in compose)
- `ENTERPRISE_QUEUE_NAME` (default: `enterprise`)

Metrics:

- `ENTERPRISE_METRICS_ENABLED` (`1` to enable `GET /metrics`)
  - Recommended: keep metrics behind auth (do **not** add `/metrics` to public paths)

Useful tuning:

- `WEB_CONCURRENCY` (Gunicorn worker count)
- `LOG_LEVEL` (e.g. `INFO`, `DEBUG`)
- `ENTERPRISE_RUN_MIGRATIONS` (`1` to run Alembic migrations on container start)
- `ENTERPRISE_PUBLIC_PATHS` (comma-separated paths that bypass API key auth)

## Run locally (developer mode)

Run the API directly (no worker/redis/postgres required):

```bash
pip install -r requirements-py311.txt
uvicorn project.enterprise_api.app:app --host 127.0.0.1 --port 8000 --reload

curl -s http://127.0.0.1:8000/healthz
```

Notes:

- If `DATABASE_URL` is **unset**, local dev defaults to SQLite (`project/enterprise.db`).
- Async jobs (uploads that enqueue ingestion) require Redis + a worker.

## Run with Docker Compose (recommended for staging/prod)

From repo root:

```bash
cd deploy/enterprise
cp ../../.env.example .env
# edit .env (set ENTERPRISE_API_KEY at minimum)

docker compose up -d --build
curl -s http://127.0.0.1:8000/healthz
```

If you set an API key:

```bash
export KEY="$(grep '^ENTERPRISE_API_KEY=' .env | cut -d= -f2-)"

curl -s http://127.0.0.1:8000/healthz -H "X-API-Key: $KEY"
```

### Production notes

- **Do not commit secrets**: keep `.env` out of git (already ignored in this repo).
- Put Postgres/Redis/Qdrant on managed services if desired; set `DATABASE_URL`, `ENTERPRISE_REDIS_URL` (and `QDRANT_URL` if used).
- Consider adding TLS and auth at the edge (reverse proxy) if exposing beyond localhost.

## systemd notes (if not using Docker)

If you run natively on a VM:

- Create a dedicated user (e.g. `enterprise`) and a writable uploads directory.
- Ensure `ENTERPRISE_UPLOAD_DIR` is the same for both units.
- Run API + worker as separate services.

Minimal sketch (paths are examples):

- `enterprise-api.service`: runs `gunicorn -c deploy/enterprise/gunicorn.conf.py project.enterprise_api.app:app`
- `enterprise-worker.service`: runs `python -m project.enterprise_api.worker`

Store environment variables in a root-owned file (e.g. `/etc/enterprise-api.env`) and reference it via `EnvironmentFile=`.

## Troubleshooting

- **401 Unauthorized**
  - `ENTERPRISE_API_KEY` is set but you forgot `X-API-Key` header.

- **Uploads stuck in `queued`**
  - Worker not running, or `ENTERPRISE_REDIS_URL` mismatched between API and worker.

- **Worker can’t find uploaded file**
  - `ENTERPRISE_UPLOAD_DIR` differs between API and worker, or directory is not shared/mounted.

- **DB connection errors**
  - Verify `DATABASE_URL` and network reachability.
  - In compose, confirm `postgres` is healthy: `docker compose ps`.

- **Migrations failing on startup**
  - Set `ENTERPRISE_RUN_MIGRATIONS=0` temporarily to get the API up, then run Alembic manually.
