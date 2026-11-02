"""Provedores de modelo. `get_llm_provider` escolhe OpenAI ou o fake offline."""

from __future__ import annotations

from app.ai.providers.base import LLMProvider, LLMProviderError, LLMResponse
from app.ai.providers.fake import FakeLLMProvider
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    mode = settings.ai_provider
    if mode == "fake" or (mode == "auto" and not settings.openai_api_key):
        return FakeLLMProvider()
    if not settings.openai_api_key:
        raise AppError("AI_PROVIDER=openai exige OPENAI_API_KEY", status_code=503)

    from app.ai.providers.openai_provider import OpenAIProvider

    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=settings.openai_timeout_seconds,
    )


__all__ = [
    "FakeLLMProvider",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "get_llm_provider",
]
