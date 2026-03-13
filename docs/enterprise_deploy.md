# Enterprise deployment (Milestone 2)

This repo ships a **local-first** enterprise-style deployment stack:

- `enterprise-api` (FastAPI)
- `postgres` (persisted volume)
- `qdrant` (persisted volume)
- `redis` (persisted volume; reserved for rate limiting / task queue later)

All exposed ports are bound to **127.0.0.1 only**.

## Quickstart

From repo root:

```bash
cd deploy/enterprise

# 1) create env file
cp ../../.env.example .env
# edit .env and set ENTERPRISE_API_KEY (recommended)

# 2) start stack
docker compose up -d --build

# 3) health check
curl -s http://127.0.0.1:8000/healthz
```

If you configured an API key, remember to pass it:

```bash
export KEY="$(grep '^ENTERPRISE_API_KEY=' .env | cut -d= -f2-)"

curl -s http://127.0.0.1:8000/healthz \
  -H "X-API-Key: $KEY"
```

## Database (Postgres by default in compose)

The compose stack sets `DATABASE_URL` to Postgres:

- `postgresql+psycopg://enterprise:enterprise@postgres:5432/enterprise`

Schema management:

- **Postgres (compose / prod):** Alembic migrations are run automatically on container start
- **SQLite (local dev):** tables are auto-created via `Base.metadata.create_all`

To run migrations manually:

```bash
docker compose exec enterprise-api alembic -c project/enterprise_api/alembic.ini current
```

## Qdrant externalization

The vector store uses:

- `QDRANT_URL` (if set) to connect to an external Qdrant instance
- otherwise falls back to the previous local-path mode (`project/qdrant_db`)

Compose default:

- `QDRANT_URL=http://qdrant:6333`

## API key auth

If `ENTERPRISE_API_KEY` is non-empty, the API requires:

- HTTP header: `X-API-Key: <value>`

Public endpoints without auth:

- `/healthz`
- `/docs`, `/openapi.json`, `/redoc`

Note: `/metrics` is **protected** when `ENTERPRISE_API_KEY` is set (recommended). Add it to `ENTERPRISE_PUBLIC_PATHS` only if you want metrics publicly accessible.

(You can extend public paths via `ENTERPRISE_PUBLIC_PATHS`, comma-separated.)

## Metrics

If `ENTERPRISE_METRICS_ENABLED=1`, metrics are exposed at:

- `GET /metrics`

It includes:

- HTTP request counters + latency histogram
- `/v1/chat` handler duration histogram
- tool-call latency + counters (from OpenBB audit log)

## Sample chat curl

```bash
export KEY="$(grep '^ENTERPRISE_API_KEY=' .env | cut -d= -f2-)"

curl -s http://127.0.0.1:8000/v1/chat \
  -H 'content-type: application/json' \
  -H "X-API-Key: $KEY" \
  -d '{"conversation_id":"demo","message":"Summarize the document sources you have."}'
```

## Concurrency (Gunicorn)

The container runs Gunicorn with Uvicorn workers.

Tune workers with:

- `WEB_CONCURRENCY` (default in compose: `2`)

For CPU-bound embeddings, increasing workers can improve throughput, but be mindful of:

- memory usage (each worker loads models)
- database connections (Postgres pool)
