"""Casos de uso de IA sobre minutas: sugestão de cláusulas e revisão/resumo de texto."""

from __future__ import annotations

import re

from app.ai.providers import LLMProvider, LLMResponse, get_llm_provider
from app.core.config import get_settings

SYSTEM_PROMPT = (
    "Você é um assistente jurídico que apoia a redação de minutas e contratos no direito "
    "brasileiro. Responda em português, de forma objetiva. Você não substitui a análise de "
    "um advogado: sinalize incertezas e nunca invente dados das partes."
)

_TAG_RE = re.compile(r"<[^>]+>")


def html_to_plain(html: str) -> str:
    return " ".join(_TAG_RE.sub(" ", html).split())


def _truncate(text: str) -> str:
    limit = get_settings().ai_max_input_chars
    return text if len(text) <= limit else text[:limit] + "\n[...texto truncado...]"


class MinutaAssistant:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or get_llm_provider()

    async def suggest_clause(
        self, *, contract_type: str, objective: str, context: str | None
    ) -> LLMResponse:
        prompt = (
            f"Tipo de contrato: {contract_type}\n"
            f"Objetivo da cláusula: {objective}\n"
            f"Contexto adicional: {context or 'não informado'}\n\n"
            "Redija UMA cláusula contratual pronta para uso, com título em caixa alta, "
            "e em seguida liste em até 3 tópicos os pontos que o revisor deve conferir."
        )
        return await self._provider.complete(system=SYSTEM_PROMPT, prompt=_truncate(prompt))

    async def review_text(self, *, text: str) -> LLMResponse:
        prompt = (
            "Analise o documento abaixo e responda com:\n"
            "1. Resumo em até 5 linhas;\n"
            "2. Partes, valores e prazos identificados;\n"
            "3. Riscos ou cláusulas ausentes/ambíguas.\n\n"
            f"Documento:\n{_truncate(text)}"
        )
        return await self._provider.complete(system=SYSTEM_PROMPT, prompt=prompt, max_tokens=1000)
