# Enterprise async jobs (Milestone 4)

This deployment adds a background **job queue** for long-running tasks like document ingestion.

## Components

- **Redis**: queue backend (already present in compose)
- **RQ worker**: consumes jobs and executes tasks
- **Postgres `jobs` table**: source of truth for job status/progress/results

## Job lifecycle

- `queued` — created in DB and enqueued in Redis
- `running` — worker started processing
- `completed` — finished successfully
- `failed` — error during enqueue or execution

## API

### POST /v1/documents/upload

Now **enqueues** ingestion instead of doing it synchronously.

Response:

```json
{"job_id":"...","status_url":"http://127.0.0.1:8000/v1/jobs/..."}
```

### GET /v1/jobs/{job_id}

Returns DB-backed status/progress/result:

- `status`: queued|running|completed|failed
- `progress`: 0-100
- `result`: when completed (includes `doc_id`, `added`, `skipped`)
- `error`: when failed

### POST /v1/jobs/noop

Enqueues a small dummy job (useful for smoke testing without uploading files).

## Worker

The worker entrypoint is:

- `python -m project.enterprise_api.worker`

It consumes the queue name from:

- `ENTERPRISE_QUEUE_NAME` (default: `enterprise`)

And connects to Redis via:

- `ENTERPRISE_REDIS_URL` (default: `redis://localhost:6379/0`)

### Upload file path (compose)

When running under docker-compose, the API container writes uploads into a shared directory so the worker can read them:

- `ENTERPRISE_UPLOAD_DIR` (default in compose: `/var/lib/enterprise/uploads`)
