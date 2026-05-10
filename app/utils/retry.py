"""Decorators simples para chamadas externas — ETAPA 4 usa nas integrações OpenAI."""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

# Backoff modeste: evita martelar API de terceiros quando há glitch transitório
external_api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
)
