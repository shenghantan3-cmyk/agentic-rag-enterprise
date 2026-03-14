from __future__ import annotations

import os
import sys
import types

import pytest


def _install_stub_langchain_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install tiny stub modules so tests don't require langchain deps installed.

    We only need to validate provider selection logic (no network calls).
    """

    m_ollama = types.ModuleType("langchain_ollama")

    class ChatOllama:  # noqa: N801 (match external class name)
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    m_ollama.ChatOllama = ChatOllama

    m_openai = types.ModuleType("langchain_openai")

    class ChatOpenAI:  # noqa: N801
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    m_openai.ChatOpenAI = ChatOpenAI

    monkeypatch.setitem(sys.modules, "langchain_ollama", m_ollama)
    monkeypatch.setitem(sys.modules, "langchain_openai", m_openai)


def test_llm_factory_default_provider_is_ollama(monkeypatch: pytest.MonkeyPatch):
    _install_stub_langchain_modules(monkeypatch)

    # Ensure LLM_PROVIDER is unset  default to ollama
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    from core.llm_factory import create_llm

    llm = create_llm()
    assert llm.__class__.__name__ == "ChatOllama"


def test_llm_factory_openai_selected_by_env(monkeypatch: pytest.MonkeyPatch):
    _install_stub_langchain_modules(monkeypatch)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.3")

    from core.llm_factory import create_llm

    llm = create_llm()
    assert llm.__class__.__name__ == "ChatOpenAI"
    assert llm.kwargs["model"] == "gpt-test"
    assert llm.kwargs["api_key"] == "sk-test"
    assert llm.kwargs["base_url"] == "https://example.com/v1"
    assert llm.kwargs["temperature"] == pytest.approx(0.3)


def test_llm_factory_openai_requires_key_and_model(monkeypatch: pytest.MonkeyPatch):
    _install_stub_langchain_modules(monkeypatch)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    from core.llm_factory import create_llm

    with pytest.raises(ValueError) as e:
        _ = create_llm()

    msg = str(e.value)
    assert "OPENAI_API_KEY" in msg
    assert "OPENAI_MODEL" in msg
