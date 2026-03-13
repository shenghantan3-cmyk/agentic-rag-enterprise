# Enterprise Design: OpenBB + LangGraph Agentic RAG (Local-first, Single-user)

**Status:** Draft

This document proposes an enterprise-leaning (but local-first) target architecture for extending this repo’s Agentic RAG system with **OpenBB Platform** as a first-class market data source.

> Decisions already made
> - Single user initially
> - Local-only deployment now; later publish as a public service
> - OpenBB Platform API (local self-host) is the market data source
> - Persist retrieved market data as an “OpenBB database” (local now; migrate later)
> - Use API-based LLM (OpenAI-compatible); API key loaded safely from local OpenClaw config (fallback)

---

## 1) Goals / Non-goals

### Goals
- Add an **OpenBBData** capability that can:
  - Discover available endpoints from `http://127.0.0.1:6900/openapi.json`
  - Call OpenBB endpoints deterministically (typed tools) from the agent
  - Persist responses into a local “OpenBB database” for caching and re-use
- Keep the system **local-first** and runnable by a single user on one machine.
- Preserve existing RAG functionality (PDF→Markdown, hierarchical chunking, hybrid retrieval).
- Provide a **clean migration path**:
  - SQLite → Postgres
  - Local bind → public behind reverse proxy + auth
- Introduce **audit logging** and basic observability suitable for enterprise extension.

### Non-goals (for the first iteration)
- Multi-tenancy, billing, per-user quotas.
- Fully automated OpenAPI → tool generation with perfect type fidelity (we can start with a curated subset).
- High availability / horizontal scaling.
- Real-time streaming market data (initially we focus on request/response queries).

---

## 2) Current baseline (what exists today)

### Runtime + UI
- `project/app.py`: entrypoint launching Gradio UI.
- `project/ui/gradio_app.py`: upload docs + chat UI.

### Core RAG pipeline
- `project/core/rag_system.py`:
  - Initializes Qdrant collections and parent store
  - Builds LangGraph agent via `project/rag_agent/graph.py`
  - Currently uses `ChatOllama` (local LLM)
- `project/core/document_manager.py`: ingestion pipeline (convert → chunk → index).
- `project/document_chunker.py`: parent/child chunking.

### Storage
- Qdrant local store via `QdrantClient(path=project/qdrant_db)`:
  - `project/db/vector_db_manager.py`
- File-backed parent chunks:
  - `project/db/parent_store_manager.py`

### LangGraph design (baseline)
- Graph entry in `project/rag_agent/graph.py`:
  - `summarize_history` → `rewrite_query` → (optional clarification) → `agent` subgraph → `aggregate_answers`
- Agent subgraph:
  - `orchestrator` (LLM w/ tools) → `tools` → compression checks → `collect_answer`
- Tools are currently retrieval-only:
  - `search_child_chunks`, `retrieve_parent_chunks` in `project/rag_agent/tools.py`

---

## 3) Target architecture (services + data stores)

### Local-first deployment (single user)
**Process-level components** (can start as a single Python process and split later):

1) **RAG App / API** (this repo)
- Provides UI (Gradio) and/or HTTP API (future)
- Runs LangGraph workflows

2) **OpenBB Platform** (local)
- Base URL: `http://127.0.0.1:6900`
- Provides `/openapi.json` for endpoint discovery

3) **Data stores**
- **Vector DB (Qdrant local)**: already present at `project/qdrant_db/`
- **Parent store (filesystem)**: already present at `project/parent_store/`
- **OpenBB database (new)**: SQLite initially; Postgres later
  - Stores query requests, responses, normalized entities, and cache metadata

### Public-facing deployment (later)
- Put the RAG API behind a reverse proxy (Caddy/Nginx/Traefik) with TLS.
- Add auth (API keys / OAuth) and rate limits.
- Move SQLite → Postgres; consider managed Postgres.
- Optionally separate OpenBB DB and RAG DB schemas.

**Suggested new paths (proposed):**
- `project/openbb/` (OpenBB client, schemas, tool adapters)
- `project/storage/` (SQLite + later Postgres models)
- `project/llm/` (provider abstraction, key loading)
- `project/observability/` (logging, tracing wrappers)

---

## 4) LangGraph graph design (Supervisor + DocumentRAG + OpenBBData + Fusion)

We keep the existing DocumentRAG flow and add an explicit supervisor that routes to either:
- DocumentRAG (existing RAG retrieval tools)
- OpenBBData (market data tools)
- Fusion (merge market data + document context)

### Proposed graph (conceptual)

**Supervisor Graph**
- `summarize_history` (existing)
- `rewrite_query` (existing)
- `route_intent` (new)
  - Output: `{intent: document|market|fusion, rationale, required_symbols, required_date_ranges}`
- Conditional:
  - `DocumentRAG` subgraph (existing)
  - `OpenBBData` subgraph (new)
  - `Fusion` node (new)
- `aggregate_answers` (existing, but upgraded to handle multi-source citations)

### Routing heuristic (initial)
- Use an LLM-based classifier prompt (deterministic temperature=0) plus lightweight rules:
  - If query includes tickers, OHLCV, “earnings”, “options”, “macro series”… → `market`
  - If query references uploaded docs/policies/manuals… → `document`
  - If both, or asks “compare doc guidance vs market reality”… → `fusion`

### OpenBBData subgraph
Nodes:
- `plan_market_queries`
  - Convert natural language to a sequence of OpenBB calls (bounded length)
- `execute_openbb_calls` (ToolNode)
- `persist_openbb_results`
  - Write raw JSON + normalized extracts into OpenBB database
- `summarize_market_results`

### Fusion node
- Inputs: document_context (citations) + market_context (tables, timeseries summaries)
- Output: final response with clear separation:
  - **What comes from docs** vs **what comes from market data**

---

## 5) Data model: SQLite now → Postgres later, audit logging, caching

### 5.1 OpenBB database (new)
**SQLite** for local-first:
- File path (proposed): `project/data/openbb.sqlite3`

Tables (minimum viable):
- `openbb_requests`
  - `id` (uuid / integer)
  - `created_at`
  - `endpoint` (string)
  - `method` (GET/POST)
  - `params_json` (text)
  - `request_hash` (string, unique)
  - `status` (success/error)
  - `latency_ms`
- `openbb_responses`
  - `request_id` (fk)
  - `response_json` (text)
  - `etag` / `cache_control` (nullable)
- `market_entities` (optional early normalization)
  - `symbol`, `exchange`, `asset_type`
- `timeseries_points` (optional; only if we truly need queryable points)
  - `symbol`, `ts`, `field`, `value`

**Cache strategy**
- Cache key: `sha256(method + endpoint + canonical_json(params))`
- TTL policy (configurable): e.g. 1h for intraday, 24h for fundamentals
- Store “last fetched” and “expires_at” fields (or compute from TTL)

### 5.2 Audit logging
Goal: explainability and accountability even in single-user mode.

Minimum:
- Log each agent run:
  - prompt template id/version
  - tool calls (name, args, start/end, error)
  - token usage (if provider supports)

Implementation options:
- Local JSONL file (fast start): `project/logs/audit.jsonl`
- Later: table in Postgres (append-only), plus structured tracing.

### 5.3 Migration path: SQLite → Postgres
- Use an ORM with migrations from day 1 (SQLAlchemy + Alembic).
- Keep storage interface stable:
  - `project/storage/openbb_store.py` exposes `get_cached(...)`, `put_response(...)`.
- Postgres schema mirrors SQLite tables; add indexes:
  - `request_hash` unique index
  - `(endpoint, created_at)`

---

## 6) LLM provider abstraction + key loading strategy + rotation

### Target: OpenAI-compatible endpoint
We want to support any provider with an OpenAI-compatible API (OpenAI, Azure OpenAI, vLLM, Moonshot, etc.).

**Proposed module:** `project/llm/provider.py`
- Build an LLM instance from:
  - `LLM_BASE_URL` (optional)
  - `LLM_MODEL`
  - `LLM_API_KEY`

### Key loading strategy (safe)
1) Prefer environment variables (best practice for prod):
- `LLM_API_KEY` (or `OPENAI_API_KEY`)
- `LLM_BASE_URL` (optional)

2) Fallback to OpenClaw local config **without printing secrets**:
- Example path (operator-controlled): `/root/.openclaw/config.local.toml`
- Read-only, do not log file content.

Pseudo-code (illustrative, not a hard requirement):
```python
# project/llm/secrets.py
from __future__ import annotations
import os, tomllib
from pathlib import Path

def load_api_key() -> str:
    # 1) env
    key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if key:
        return key

    # 2) OpenClaw config fallback
    p = Path("/root/.openclaw/config.local.toml")
    if not p.exists():
        raise RuntimeError("No LLM API key found in env and OpenClaw config missing")

    data = tomllib.loads(p.read_text(encoding="utf-8"))
    # NOTE: exact key name is operator-defined; keep this flexible
    key = data.get("env", {}).get("OPENAI_API_KEY") or data.get("env", {}).get("LLM_API_KEY")
    if not key:
        raise RuntimeError("No LLM API key found in OpenClaw config")
    return key
```

### Rotation
- Support multiple keys separated by commas:
  - `LLM_API_KEYS=k1,k2,k3`
- Select key via round-robin or failover on 429/5xx.
- Never persist keys in DB or logs.

---

## 7) OpenBB integration details

### 7.1 Connectivity
- Base URL: `http://127.0.0.1:6900`
- Discovery:
  - `GET /openapi.json`

### 7.2 Endpoint discovery → tool schema
We will treat OpenBB as a tool provider. There are two phases:

**Phase A (MVP, curated tools)**
- Implement 5–10 explicit tools with stable Pydantic schemas.
- Benefits: less brittleness, fewer surprises.

**Phase B (semi-automated generation)**
- Parse OpenAPI and generate tool wrappers for selected tags/paths.
- Enforce allowlist to avoid exposing dangerous/irrelevant endpoints.

**Proposed modules:**
- `project/openbb/client.py`
  - HTTP client with timeout/retry/backoff
- `project/openbb/openapi.py`
  - download + cache openapi spec
- `project/openbb/tools.py`
  - tool wrappers for LangChain/LangGraph

### 7.3 HTTP patterns (recommended)
- Use `httpx` with:
  - connect timeout: 2s
  - read timeout: 20s
  - retries: 2 (idempotent)
  - backoff: exponential

### 7.4 Example discovery snippet
```python
import httpx

def fetch_openbb_openapi(base_url: str = "http://127.0.0.1:6900") -> dict:
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{base_url}/openapi.json")
        r.raise_for_status()
        return r.json()
```

---

## 8) Security

### Local-only (now)
- Bind only to loopback:
  - RAG UI (Gradio) on `127.0.0.1`
  - OpenBB on `127.0.0.1`
- No secrets in git; no secrets in logs.
- Add dependency pinning and basic SCA:
  - keep `requirements*.txt` updated

### Public (later)
- Reverse proxy + TLS
- Auth options:
  - API key header (simple)
  - OAuth/OIDC (enterprise)
- Rate limiting + request size limits
- Separate “tool allowlist” for OpenBB endpoints
- Consider network policy:
  - Only allow OpenBB base URL (no SSRF)

---

## 9) Observability + testing

### Observability
- Structured logging (JSON) with request correlation id:
  - `thread_id` from LangGraph config (`RAGSystem.get_config()`)
- Metrics (later):
  - tool call latency, cache hit rate, LLM latency, token usage
- Tracing (later): OpenTelemetry spans for:
  - agent run
  - tool calls
  - OpenBB HTTP calls

### Testing
- Unit tests:
  - OpenBB client request hashing and canonicalization
  - cache TTL logic
  - OpenAPI parsing (allowlist)
- Integration tests:
  - mock OpenBB with `respx`
  - run a minimal LangGraph flow calling a fake tool
- Smoke test script (local):
  - `python -m project.scripts.smoke_openbb`

---

## 10) Milestones (with acceptance criteria)

### M0 — Design + scaffolding
- [ ] Add this design doc.
- [ ] Add module skeleton directories (`project/openbb`, `project/llm`, `project/storage`).

**Acceptance:** repo builds; no runtime behavior change.

### M1 — API LLM provider switch (OpenAI-compatible)
- [ ] Implement LLM provider abstraction.
- [ ] Load API key from env; fallback to OpenClaw config.
- [ ] Replace `ChatOllama` in `project/core/rag_system.py` with provider factory.

**Acceptance:** RAG works end-to-end using an API LLM without leaking secrets.

### M2 — OpenBB MVP tools (curated)
- [ ] Add `OpenBBClient` (httpx).
- [ ] Add 5–10 tools (e.g., price history, quote, fundamentals, macro series).
- [ ] Add tool allowlist.

**Acceptance:** agent can call OpenBB tools and cite returned data.

### M3 — OpenBB database (SQLite) + cache
- [ ] Create SQLite schema and store interface.
- [ ] Cache OpenBB responses by request hash.

**Acceptance:** repeated queries hit cache; DB file created locally.

### M4 — Fusion responses
- [ ] Add `route_intent` + `Fusion` node.
- [ ] Ensure response separates doc vs market data.

**Acceptance:** mixed queries produce fused answers with citations.

### M5 — Hardening + migration plan
- [ ] Add audit.jsonl logging.
- [ ] Add Postgres migration plan (Alembic) and docs.

**Acceptance:** audit log records tool calls; documented migration path.

---

## 11) Open questions (for user / operator)

1) Which OpenBB endpoints are the initial must-haves (quotes, OHLCV, fundamentals, options, macro)?
2) Do we need **normalized timeseries storage** (queryable points), or is raw JSON caching enough initially?
3) What TTL policies should we use per data type (intraday vs fundamentals)?
4) Should the OpenBB database be separated from RAG audit logs, or combined into one DB?
5) What OpenAI-compatible provider are we targeting first (OpenAI, Azure, local vLLM, etc.)?
6) Do we need tool call cost controls (max OpenBB calls per run, max symbols, date range limits)?
7) For public deployment later, what auth mechanism is preferred (API key vs OIDC)?
8) Do we need a formal data lineage / reproducibility story (pin versions of OpenBB responses, prompts, model ids)?
9) Should we keep Gradio UI, or add a FastAPI backend early to support future public service?
10) Any compliance constraints (data retention, logging redaction, export/deletion needs)?
