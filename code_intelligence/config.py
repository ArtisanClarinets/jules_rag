"""Centralized configuration for LLM + embeddings providers.

This repo originally hard-coded OpenAI usage. To support OpenRouter (and any
OpenAI-compatible endpoint), we make provider selection a runtime config.

All config is environment-variable driven so it's easy to use from a local
VS Code extension, terminal, or container.
"""

from __future__ import annotations

from dataclasses import dataclass
import os


def _env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    return val


@dataclass(frozen=True)
class ProviderConfig:
    """Common config for OpenAI-compatible APIs."""

    provider: str
    api_key: str
    base_url: str
    # OpenRouter recommends (optional) attribution headers.
    http_referer: str | None = None
    x_title: str | None = None


@dataclass(frozen=True)
class LLMConfig:
    provider: ProviderConfig
    model: str
    temperature: float = 0.0
    max_tokens: int = 2048
    # Try to force JSON mode when supported.
    prefer_json: bool = True


@dataclass(frozen=True)
class EmbeddingsConfig:
    provider: ProviderConfig
    model: str
    batch_size: int = 64


def load_provider(provider_name: str | None = None) -> ProviderConfig:
    provider = (provider_name or _env("LLM_PROVIDER", "openai") or "openai").lower()

    if provider == "openrouter":
        api_key = _env("OPENROUTER_API_KEY") or ""
        base_url = _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") or "https://openrouter.ai/api/v1"
        http_referer = _env("OPENROUTER_HTTP_REFERER")  # e.g. https://your.site
        x_title = _env("OPENROUTER_X_TITLE")  # e.g. "My VS Code RAG"
        return ProviderConfig(
            provider="openrouter",
            api_key=api_key,
            base_url=base_url,
            http_referer=http_referer,
            x_title=x_title,
        )

    # default: OpenAI
    api_key = _env("OPENAI_API_KEY") or ""
    base_url = _env("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"
    return ProviderConfig(provider="openai", api_key=api_key, base_url=base_url)


def load_llm_config() -> LLMConfig:
    provider = load_provider(_env("LLM_PROVIDER"))
    model = _env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    # Convenience: allow OpenRouter-style model IDs like "openai/gpt-4o"
    # while using OpenAI directly.
    if provider.provider == "openai" and "/" in model:
        model = model.split("/", 1)[1]
    temperature = float(_env("LLM_TEMPERATURE", "0") or 0)
    max_tokens = int(_env("LLM_MAX_TOKENS", "2048") or 2048)
    prefer_json = (_env("LLM_PREFER_JSON", "true") or "true").lower() in {"1", "true", "yes", "y"}
    return LLMConfig(provider=provider, model=model, temperature=temperature, max_tokens=max_tokens, prefer_json=prefer_json)


def load_embeddings_config() -> EmbeddingsConfig:
    # Allow separate provider/model for embeddings, but default to the LLM provider.
    provider = load_provider(_env("EMBEDDINGS_PROVIDER") or _env("LLM_PROVIDER"))
    model = _env("EMBEDDINGS_MODEL", "openai/text-embedding-3-small") or "openai/text-embedding-3-small"
    if provider.provider == "openai" and "/" in model:
        model = model.split("/", 1)[1]
    batch_size = int(_env("EMBEDDINGS_BATCH_SIZE", "64") or 64)
    return EmbeddingsConfig(provider=provider, model=model, batch_size=batch_size)
