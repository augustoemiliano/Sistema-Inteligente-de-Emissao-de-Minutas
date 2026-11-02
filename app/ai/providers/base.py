from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LLMResponse:
    content: str
    provider: str
    model: str


class LLMProviderError(RuntimeError):
    """Falha ao falar com o provedor (timeout, rate limit, credencial...)."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, *, system: str, prompt: str, max_tokens: int = 800) -> LLMResponse: ...
