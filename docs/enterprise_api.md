# Enterprise API (FastAPI)

This repo includes a lightweight **enterprise-style HTTP API** alongside the existing Gradio UI.

- Gradio UI entrypoint remains: `python project/app.py`
- Enterprise API entrypoint: `project/enterprise_api/app.py`

## Run the API locally

From repo root:

```bash
# (optional) activate venv
# source .venv/bin/activate

pip install -r requirements-py311.txt

# run FastAPI
uvicorn project.enterprise_api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Environment variables

- `DATABASE_URL` (optional)
  - default: `sqlite:///project/enterprise.db`
  - Postgres-ready example: `postgresql+psycopg://user:pass@localhost:5432/enterprise`
- `OPENBB_BASE_URL` (optional)
  - default: `http://127.0.0.1:6900`
- `OPENBB_TOOLS_DB_PATH` (optional)
  - default: `project/openbb/openbb_tools_cache.sqlite`

`.env` loading is supported if you install `python-dotenv`, but it is **optional**.

## Endpoints

### GET /healthz

```bash
curl -s http://127.0.0.1:8000/healthz
```

### POST /v1/chat

Request body:

- `conversation_id` (optional)
- `message` (required)

```bash
curl -s http://127.0.0.1:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"conversation_id":"demo-convo-1","message":"What does the document say about X?"}'
```

Response:

- `run_id`: unique run identifier
- `answer`: final assistant answer
- `citations`: list of cited source filenames (best-effort)
- `openbb_used`: summary of OpenBB tool usage (count/endpoints/cache hits)

### POST /v1/documents/upload

Multipart upload (PDF or MD). Upload triggers indexing via existing `DocumentManager`.

```bash
curl -s http://127.0.0.1:8000/v1/documents/upload \
  -F 'file=@./some_doc.pdf'
```

Response:

- `doc_id`: generated identifier for this upload

### GET /v1/runs/{run_id}

```bash
curl -s http://127.0.0.1:8000/v1/runs/<RUN_ID>
```

Returns run metadata and recorded tool calls.

## Storage schema (SQLite default)

The enterprise DB (default: `project/enterprise.db`) stores:

- `runs`:
  - `id`, `conversation_id`, `created_at`, `status`, `user_message`, `answer`
  - `citations_json`, `openbb_summary_json`, `error`
- `messages`:
  - minimal user/assistant messages per run
- `tool_calls`:
  - OpenBB audit rows copied into enterprise DB per run
  - includes `endpoint`, `params_hash`, `status_code`, `latency_ms`, `cache_hit`

OpenBB tool calls are associated to a run via a ContextVar-based `run_id` set by `/v1/chat`.
