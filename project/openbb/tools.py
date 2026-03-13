"""LangChain tools for OpenBB local server.

Implements three default tools:
- /api/v1/equity/price/historical
- /api/v1/equity/price/quote
- /api/v1/news/company

Provider is forced to yfinance by default to avoid external keys.

All tools:
- sanitize inputs
- constrain date ranges / limits
- use local cache + audit log

Milestone M4: return tool outputs as JSON (tool_output.v1) via
`common.citations.pack_tool_output` so the agent can extract structured
citations.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Literal, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

import config as _config
from common.citations import now_iso, pack_tool_output

from .client import OpenBBClient
from .storage import stable_params_hash


def _parse_date(d: Optional[str]) -> Optional[_dt.date]:
    if d is None:
        return None
    if isinstance(d, str) and not d.strip():
        return None
    return _dt.date.fromisoformat(str(d))


def _clamp_date_range(
    start: Optional[_dt.date],
    end: Optional[_dt.date],
    *,
    default_days: int,
    max_days: int,
) -> tuple[_dt.date, _dt.date]:
    today = _dt.date.today()
    if end is None:
        end = today
    if start is None:
        start = end - _dt.timedelta(days=default_days)

    if start > end:
        start, end = end, start

    delta = (end - start).days
    if delta > max_days:
        start = end - _dt.timedelta(days=max_days)
    return start, end


def _only_yfinance(provider: Optional[str]) -> str:
    # Safety: in this repo we only support yfinance by default to avoid external keys.
    # If someone explicitly passes another provider, we reject.
    if provider is None or str(provider).strip() == "":
        return "yfinance"
    provider = str(provider)
    if provider != "yfinance":
        raise ValueError("Only provider='yfinance' is supported in this demo environment.")
    return provider


def _pack_openbb_tool_output(*, endpoint: str, params: dict[str, Any], raw_json_text: str) -> str:
    """Pack a tool output with a structured OpenBB citation."""

    endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    p_hash = stable_params_hash(params or {})

    text = (
        f"OpenBB {endpoint}\n"
        f"params_hash={p_hash}\n"
        f"params={params}\n\n"
        f"response:\n{raw_json_text}"
    )

    citations = [
        {
            "source": "openbb",
            "endpoint": endpoint,
            "params_hash": p_hash,
            "snippet": f"OpenBB {endpoint} (params_hash={p_hash})",
            "created_at": now_iso(),
        }
    ]

    return pack_tool_output(text=text, citations=citations)


class EquityPriceHistoricalArgs(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, e.g., AAPL")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    interval: Optional[Literal["1d", "1wk", "1mo"]] = Field("1d", description="Data interval")
    provider: Optional[str] = Field("yfinance", description="Must be 'yfinance'")
    include_actions: bool = Field(True, description="Include dividends and splits when available")
    use_cache: bool = Field(True, description="Use local tool cache")


class EquityPriceQuoteArgs(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, e.g., AAPL")
    provider: Optional[str] = Field("yfinance", description="Must be 'yfinance'")
    use_cache: bool = Field(True, description="Use local tool cache")


class NewsCompanyArgs(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, e.g., AAPL")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    limit: Optional[int] = Field(10, description="Number of items to return (max 50)")
    provider: Optional[str] = Field("yfinance", description="Must be 'yfinance'")
    use_cache: bool = Field(True, description="Use local tool cache")


@tool("openbb_equity_price_historical", args_schema=EquityPriceHistoricalArgs, parse_docstring=False)
def openbb_equity_price_historical(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: Optional[str] = "1d",
    provider: Optional[str] = "yfinance",
    include_actions: bool = True,
    use_cache: bool = True,
) -> str:
    """Get historical equity prices from the local OpenBB server."""
    provider = _only_yfinance(provider)

    start, end = _clamp_date_range(
        _parse_date(start_date),
        _parse_date(end_date),
        default_days=30,
        max_days=max(1, min(3650, int(_config.MAX_DATE_RANGE_DAYS))),
    )

    if interval not in {"1d", "1wk", "1mo"}:
        interval = "1d"

    params: dict[str, Any] = {
        "provider": provider,
        "symbol": symbol,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "interval": interval,
        "include_actions": bool(include_actions),
        "use_cache": True,  # OpenBB server internal cache; safe to keep on
    }

    client = OpenBBClient()
    endpoint = "/api/v1/equity/price/historical"
    raw = client.get_json(
        endpoint,
        params=params,
        ttl_seconds=60 * 30,
        use_cache=bool(use_cache),
    )
    return _pack_openbb_tool_output(endpoint=endpoint, params=params, raw_json_text=raw)


@tool("openbb_equity_price_quote", args_schema=EquityPriceQuoteArgs, parse_docstring=False)
def openbb_equity_price_quote(
    symbol: str,
    provider: Optional[str] = "yfinance",
    use_cache: bool = True,
) -> str:
    """Get a near-real-time quote from the local OpenBB server."""
    provider = _only_yfinance(provider)

    params: dict[str, Any] = {
        "provider": provider,
        "symbol": symbol,
        "use_cache": True,
    }

    client = OpenBBClient()
    endpoint = "/api/v1/equity/price/quote"
    raw = client.get_json(
        endpoint,
        params=params,
        ttl_seconds=60 * 5,
        use_cache=bool(use_cache),
    )
    return _pack_openbb_tool_output(endpoint=endpoint, params=params, raw_json_text=raw)


@tool("openbb_news_company", args_schema=NewsCompanyArgs, parse_docstring=False)
def openbb_news_company(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = 10,
    provider: Optional[str] = "yfinance",
    use_cache: bool = True,
) -> str:
    """Get recent company news from the local OpenBB server."""
    provider = _only_yfinance(provider)

    start, end = _clamp_date_range(
        _parse_date(start_date),
        _parse_date(end_date),
        default_days=30,
        max_days=max(1, min(365, int(_config.MAX_DATE_RANGE_DAYS))),
    )

    try:
        lim = int(limit) if limit is not None else 10
    except Exception:
        lim = 10
    # Hard cap for safety; knob can only reduce.
    hard_cap = 50
    knob_cap = int(getattr(_config, "MAX_NEWS_LIMIT", hard_cap))
    lim = max(1, min(hard_cap, knob_cap, lim))

    params: dict[str, Any] = {
        "provider": provider,
        "symbol": symbol,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "limit": lim,
        "use_cache": True,
    }

    client = OpenBBClient()
    endpoint = "/api/v1/news/company"
    raw = client.get_json(
        endpoint,
        params=params,
        ttl_seconds=60 * 30,
        use_cache=bool(use_cache),
    )
    return _pack_openbb_tool_output(endpoint=endpoint, params=params, raw_json_text=raw)


def create_openbb_tools() -> list:
    return [openbb_equity_price_historical, openbb_equity_price_quote, openbb_news_company]
