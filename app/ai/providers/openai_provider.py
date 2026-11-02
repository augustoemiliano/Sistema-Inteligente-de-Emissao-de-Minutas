"""Integração com a OpenAI (Chat Completions) com timeout e retry exponencial."""

from __future__ import annotations

from typing import Any

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.providers.base import LLMProviderError, LLMResponse
from app.core.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, timeout: float, client: Any | None = None):
        if client is None:
            from openai import AsyncOpenAI

            # max_retries=0: o retry fica com o tenacity, com backoff controlado por nós
            client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        self._client = client
        self.model = model

    async def complete(self, *, system: str, prompt: str, max_tokens: int = 800) -> LLMResponse:
        import openai

        transient = (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError)
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
                retry=retry_if_exception_type(transient),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=max_tokens,
                        temperature=0.2,
                    )
        except (openai.OpenAIError, RetryError) as exc:
            logger.warning("Falha na OpenAI: %s", type(exc).__name__)
            raise LLMProviderError("Provedor de IA indisponível no momento") from exc

        content = (response.choices[0].message.content or "").strip()
        return LLMResponse(content=content, provider=self.name, model=self.model)
