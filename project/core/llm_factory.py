"""LLM factory.

This project historically hard-coded Ollama (local) via `ChatOllama`.
Enterprise deployments may want to use a cloud OpenAI-compatible endpoint.

Provider selection is controlled via environment variables.
"""

from __future__ import annotations

import os
from typing import Any

import config


def _env_str(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    s = str(raw).strip()
    return s if s else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


def create_llm(**kwargs: Any):
    """Create a chat LLM instance.

    Env vars:
      - LLM_PROVIDER: ollama|openai (default: ollama)

    For provider=openai:
      - OPENAI_API_KEY (required)
      - OPENAI_MODEL (required)
      - OPENAI_BASE_URL (optional)
      - OPENAI_TEMPERATURE (optional)

    For provider=ollama:
      - Uses config.LLM_MODEL + config.LLM_TEMPERATURE

    Additional **kwargs are forwarded to the underlying Chat model.
    """

    provider = (_env_str("LLM_PROVIDER", "ollama") or "ollama").lower()

    if provider == "openai":
        api_key = _env_str("OPENAI_API_KEY")
        model = _env_str("OPENAI_MODEL")
        base_url = _env_str("OPENAI_BASE_URL")
        temperature = _env_float("OPENAI_TEMPERATURE", float(config.LLM_TEMPERATURE))

        missing = [k for k, v in {"OPENAI_API_KEY": api_key, "OPENAI_MODEL": model}.items() if not v]
        if missing:
            raise ValueError(f"LLM_PROVIDER=openai but missing env var(s): {', '.join(missing)}")

        # Lazy import so deployments that only use Ollama don't need OpenAI deps.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=str(model),
            temperature=float(temperature),
            api_key=str(api_key),
            base_url=str(base_url) if base_url else None,
            **kwargs,
        )

    if provider in ("ollama", "local"):
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            **kwargs,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
