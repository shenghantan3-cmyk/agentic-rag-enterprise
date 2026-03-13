# OpenBB Tools (Local OpenBB Platform)

This project optionally integrates a **local OpenBB Platform server** as a set of LangChain tools.

- Default base URL: `http://127.0.0.1:6900`
- Override via environment variables:
  - `OPENBB_BASE_URL=http://127.0.0.1:6900`
  - `MAX_DATE_RANGE_DAYS=3650` (default; upper-bounded per endpoint)
  - `MAX_NEWS_LIMIT=50` (default; hard-capped at 50)

Agent-level budget (graph routing):
- `MAX_OPENBB_CALLS=4` (default; max executed OpenBB tool calls per agent run)
- `MAX_TOOL_CALLS=8` (default; max tool calls per agent run)

The tools are **safe-by-default** for demo usage:
- Provider is restricted to `yfinance` only (no external API keys)
- Parameters are sanitized (date range clamping, limit caps)
- Responses are cached with TTL in a local SQLite DB
- Every tool call is audited (endpoint, params hash, status, latency)

## Tools

### 1) `openbb_equity_price_quote`
Get a near-real-time quote.

**Args**
- `symbol` (str, required): e.g. `AAPL`
- `provider` (str, optional): must be `yfinance` (default)
- `use_cache` (bool, optional): local tool cache (default `true`)

### 2) `openbb_equity_price_historical`
Get historical price data.

**Args**
- `symbol` (str, required)
- `start_date` (YYYY-MM-DD, optional)
- `end_date` (YYYY-MM-DD, optional)
- `interval` (optional): `1d | 1wk | 1mo` (default `1d`)
- `include_actions` (bool, optional): dividends/splits if supported
- `provider` (str, optional): must be `yfinance`
- `use_cache` (bool, optional)

Sanitization:
- If dates are omitted, defaults to last 30 days
- Maximum range is clamped to `min(3650, MAX_DATE_RANGE_DAYS)`
  - Override via env: `MAX_DATE_RANGE_DAYS`

### 3) `openbb_news_company`
Get recent company news.

**Args**
- `symbol` (str, required)
- `start_date` (YYYY-MM-DD, optional)
- `end_date` (YYYY-MM-DD, optional)
- `limit` (int, optional): capped at 50 (default 10)
- `provider` (str, optional): must be `yfinance`
- `use_cache` (bool, optional)

Sanitization:
- If dates are omitted, defaults to last 30 days
- Maximum range is clamped to `min(365, MAX_DATE_RANGE_DAYS)`
  - Override via env: `MAX_DATE_RANGE_DAYS`
- `limit` is capped at `min(50, MAX_NEWS_LIMIT)`
  - Override via env: `MAX_NEWS_LIMIT`

## Cache + Audit log

- SQLite file path defaults to: `project/openbb/openbb_tools_cache.sqlite`
- Override via `OPENBB_TOOLS_DB_PATH=/path/to/file.sqlite`

Tables:
- `cache(cache_key, created_at, ttl_seconds, response_text)`
- `audit_log(ts, endpoint, params_hash, params_json, status_code, latency_ms, cache_hit, error)`

## Examples

### Example: quote for AAPL
```json
{
  "tool": "openbb_equity_price_quote",
  "args": {"symbol": "AAPL"}
}
```

### Example: historical for AAPL (last 90 days, weekly)
```json
{
  "tool": "openbb_equity_price_historical",
  "args": {
    "symbol": "AAPL",
    "start_date": "2025-12-01",
    "end_date": "2026-03-01",
    "interval": "1wk"
  }
}
```

### Example: news for AAPL
```json
{
  "tool": "openbb_news_company",
  "args": {"symbol": "AAPL", "limit": 10}
}
```

## Smoke test

```bash
cd /root/.openclaw/workspace/projects/agentic-rag-for-dummies
. .venv/bin/activate
OPENBB_BASE_URL=http://127.0.0.1:6900 python3 scripts/smoke_test_openbb.py
```
